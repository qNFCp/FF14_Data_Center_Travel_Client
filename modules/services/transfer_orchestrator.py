#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨区传送业务编排服务。"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

from ..backend import telemetry
from ..logger import log_transfer_history


class TransferOrchestrator:
    """跨区传送业务逻辑（与 GUI 解耦）。"""

    def __init__(self, api_client, config_manager):
        self.api = api_client
        self.config = config_manager

    def execute_transfer(
        self,
        source_area_name: str,
        source_server_name: str,
        role_name: str,
        target_area_name: str,
        target_server_name: str,
        log_cb: Optional[Callable[[str], None]] = None,
        sleep_cb: Callable[[float], None] = time.sleep,
    ) -> dict:
        """执行传送流程并返回统一结果。"""
        log = log_cb or (lambda _msg: None)
        areas = self.api.get_areas()
        if not areas:
            raise RuntimeError("未能获取大区列表")

        source_area = next((a for a in areas if a.get("areaName") == source_area_name), None)
        if not source_area:
            raise RuntimeError("源大区无效")

        target_areas = [a for a in areas if a.get("areaId") != source_area.get("areaId")]
        target_area = next((a for a in target_areas if a.get("areaName") == target_area_name), None)
        if not target_area:
            raise RuntimeError("目标大区无效或与源大区相同")

        source_server = self._find_server(source_area, source_server_name)
        target_server = self._find_server(target_area, target_server_name)
        if not source_server or not target_server:
            raise RuntimeError("源/目标服务器选择无效")

        roles = self.api.fetch_role_list(source_area.get("areaId"), source_server.get("groupId"))
        role = next((r for r in roles if r.get("roleName", r.get("name")) == role_name), None)
        if not role:
            raise RuntimeError("角色选择无效")

        final_role_name = role.get("roleName", role.get("name", "未知"))
        log(f"提交跨区传送：{final_role_name} | {source_area_name}-{source_server_name} -> {target_area_name}-{target_server_name}")

        self.api.page_init(migration_type=4)

        attempt = 0
        while True:
            attempt += 1
            log(f"第 {attempt} 次提交传送请求…")
            result = self.api.submit_transfer(source_area, source_server, target_area, target_server, role)

            if isinstance(result, str) and result.startswith("GM"):
                order_id = result
                log(f"订单已提交：{order_id}，开始轮询状态…")
                for idx in range(10):
                    status = self.api.check_order_status(order_id)
                    log(f"状态轮询 {idx + 1}/10：{status}")
                    if status == 5:
                        self._on_transfer_success(
                            final_role_name,
                            source_area_name,
                            source_server_name,
                            target_area_name,
                            target_server_name,
                            order_id,
                        )
                        return {
                            "success": True,
                            "order_id": order_id,
                            "message": "跨区传送成功",
                        }
                    if status == -1:
                        log("预检失败，准备重试。")
                        break
                    sleep_cb(5)

            elif isinstance(result, dict):
                result_code = result.get("resultCode", -1)
                result_msg = result.get("resultMsg", "未知")
                if result_code in (0, 5):
                    self._on_transfer_success(
                        final_role_name,
                        source_area_name,
                        source_server_name,
                        target_area_name,
                        target_server_name,
                        None,
                    )
                    return {
                        "success": True,
                        "order_id": None,
                        "message": "跨区传送成功",
                    }
                log(f"传送结果：{result_msg}，准备重试。")
            else:
                log("提交失败，准备重试。")

            wait_sec = random.randint(61, 65)
            for remaining in range(wait_sec, 0, -1):
                log(f"重试倒计时：{remaining} 秒")
                sleep_cb(1)

    def _find_server(self, area: dict, server_name: str):
        servers = area.get("groups", [])
        return next((s for s in servers if s.get("groupName") == server_name), None)

    def _on_transfer_success(
        self,
        role_name: str,
        source_area_name: str,
        source_server_name: str,
        target_area_name: str,
        target_server_name: str,
        order_id: Optional[str],
    ):
        log_transfer_history(
            role_name,
            source_area_name,
            source_server_name,
            target_area_name,
            target_server_name,
            success=True,
            order_id=order_id,
        )
        self.config.set_last_transfer(
            target_area_name,
            target_server_name,
            role_name=role_name,
            source_area_name=source_area_name,
            source_server_name=source_server_name,
        )
        telemetry.record_transfer()
