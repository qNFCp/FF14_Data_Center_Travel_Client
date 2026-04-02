#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""超域返回业务编排服务。"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

from ..backend import telemetry
from ..logger import log_transfer_history


class ReturnOrchestrator:
    """超域返回业务逻辑（与 GUI 解耦）。"""

    def __init__(self, api_client, config_manager):
        self.api = api_client
        self.config = config_manager

    def fetch_active_orders(self):
        """拉取并筛选可返回订单。"""
        self.api.page_init(migration_type=0)
        orders_data = self.api.fetch_migration_orders()
        if not orders_data:
            return []

        active_orders = []
        for order in orders_data.get("orderlist", []):
            migration_type = order.get("migrationType", -1)
            migration_status = order.get("migrationStatus", -1)
            travel_status = order.get("travelStatus", -1)
            status_desc = order.get("migrationStatusDesc", "")

            is_travel_order = migration_type == 4
            is_active = (migration_status == 5 and travel_status == 1) or ("旅行中" in status_desc)
            if is_travel_order and is_active:
                detail_list = order.get("migrationDetailList", [])
                if detail_list and not order.get("roleName"):
                    order["roleName"] = detail_list[0].get("roleName", "未知角色")
                active_orders.append(order)
        return active_orders

    def resolve_current_server_options(self, order: dict):
        """根据订单解析当前所在大区与可选服务器。"""
        current_area_id = order.get("targetAreaId")
        current_area_name = order.get("targetAreaName")
        current_server_id = order.get("targetGroupId")
        current_server_name = order.get("targetGroupName")

        return_areas = self.api.fetch_return_area_list()
        if not return_areas:
            raise RuntimeError("未能获取可返回服务器列表")

        current_area = None
        for area in return_areas:
            if area.get("areaId") == current_area_id or area.get("areaName") == current_area_name:
                current_area = area
                break
        if not current_area:
            raise RuntimeError("无法匹配订单中的目的地大区")

        servers = current_area.get("groups", [])
        if not servers:
            raise RuntimeError("当前大区没有可选服务器")

        default_server = next((s for s in servers if s.get("groupId") == current_server_id), None)
        if not default_server:
            default_server = next((s for s in servers if s.get("groupName") == current_server_name), None)
        if not default_server:
            default_server = servers[0]

        return current_area, servers, default_server

    def execute_return(
        self,
        order: dict,
        current_area: dict,
        current_server: dict,
        log_cb: Optional[Callable[[str], None]] = None,
        sleep_cb: Callable[[float], None] = time.sleep,
    ) -> dict:
        """执行返回流程并轮询返回状态。"""
        log = log_cb or (lambda _msg: None)

        order_id = order.get("orderId")
        role_name = order.get("roleName") or (order.get("migrationDetailList") or [{}])[0].get("roleName", "未知")
        home_area_name = order.get("areaName", "未知")
        home_server_name = order.get("groupName", "未知")

        attempt = 0
        while True:
            attempt += 1
            log(f"第 {attempt} 次提交超域返回…")
            resp = self.api.submit_travel_back(
                travel_order_id=order_id,
                group_id=current_server.get("groupId"),
                group_code=current_server.get("groupCode"),
                group_name=current_server.get("groupName"),
            )

            if resp and resp.get("success"):
                return_order_id = resp.get("orderId", "")
                log("返回请求提交成功，开始轮询状态…")
                if self._poll_return_status(order_id, return_order_id, log, sleep_cb=sleep_cb):
                    log_transfer_history(
                        role_name,
                        current_area.get("areaName", "未知"),
                        current_server.get("groupName", "未知"),
                        home_area_name,
                        home_server_name,
                        success=True,
                        order_id=return_order_id or order_id,
                    )
                    telemetry.record_return()
                    return {
                        "success": True,
                        "order_id": return_order_id or order_id,
                        "message": "超域返回成功",
                    }

                log("返回状态未确认成功，将重试提交。")
            else:
                log("返回提交失败，将重试。")

            wait_sec = random.randint(61, 65)
            for remaining in range(wait_sec, 0, -1):
                log(f"重试倒计时：{remaining} 秒")
                sleep_cb(1)

    def _poll_return_status(
        self,
        travel_order_id: str,
        return_order_id: str,
        log_cb: Callable[[str], None],
        max_attempts: int = 12,
        interval: int = 5,
        sleep_cb: Callable[[float], None] = time.sleep,
    ) -> bool:
        """轮询订单状态，确认返回成功。"""
        for attempt in range(1, max_attempts + 1):
            log_cb(f"返回状态轮询 {attempt}/{max_attempts}…")
            try:
                orders_data = self.api.fetch_migration_orders()
                if not orders_data:
                    log_cb("轮询时获取订单列表失败，继续重试。")
                    if attempt < max_attempts:
                        sleep_cb(interval)
                    continue

                order_list = orders_data.get("orderlist", [])

                for order in order_list:
                    order_id = order.get("orderId", "")
                    migration_type = order.get("migrationType", -1)
                    status_desc = order.get("migrationStatusDesc", "")
                    if migration_type == 5 and (order_id == return_order_id or order_id == travel_order_id):
                        if "返回成功" in status_desc:
                            return True
                        if "失败" in status_desc:
                            return False

                for order in order_list:
                    order_id = order.get("orderId", "")
                    migration_type = order.get("migrationType", -1)
                    status_desc = order.get("migrationStatusDesc", "")
                    travel_status = order.get("travelStatus", -1)
                    if order_id == travel_order_id and migration_type == 4:
                        if "旅行结束" in status_desc or travel_status == 3:
                            return True
            except Exception as e:
                log_cb(f"轮询订单状态异常: {e}")

            if attempt < max_attempts:
                sleep_cb(interval)
        return False
