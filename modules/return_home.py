#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 超域返回模块
负责超域返回的业务逻辑

超域返回流程：
1. 调用 pageInit(migrationType=0) 初始化页面
2. 调用 queryMigrationOrders 获取旅行中的订单
3. 调用 queryGroupListCrossSource 获取可返回的服务器列表
4. 用户选择当前所在的服务器
5. 调用 travelBack 提交返回请求
"""

import time
import random
from .config import ConfigManager, DEBUG_MODE
from .api import FF14APIClient
from .backend import telemetry
from .logger import log_transfer_history, debug_log
from .ui import (
    show_area_selection, show_server_selection, show_role_selection,
    show_transfer_summary, confirm_action, show_success_message,
    show_error_message, show_info_message, print_after_action_ads
)


class ReturnService:
    """超域返回服务"""
    
    def __init__(self, api_client, config_manager):
        """
        初始化返回服务
        :param api_client: FF14APIClient实例
        :param config_manager: ConfigManager实例
        """
        self.api = api_client
        self.config = config_manager
    
    def execute_return(self):
        """
        执行超域返回流程
        返回: True=成功, False=失败, None=用户取消
        """
        print("\n" + "="*50)
        print("           === 超域返回 ===")
        print("="*50)
        
        # 1. 页面初始化 (migrationType=0 用于订单列表页面)
        print("\n[步骤1] 初始化页面...")
        self.api.page_init(migration_type=0)
        
        # 2. 获取订单列表，查找旅行中的订单
        print("\n[步骤2] 获取旅行订单列表...")
        orders_data = self.api.fetch_migration_orders()
        
        if not orders_data:
            show_error_message("未能获取订单列表，请确保已正确登录")
            return False
        
        # 查找旅行中的订单
        travel_orders = self._find_active_travel_orders(orders_data)
        
        if not travel_orders:
            print()
            print("[信息] 未找到进行中的超域旅行订单")
            print("[提示] 只有状态为【旅行中】或【已达到目的地】的订单才能执行超域返回")
            return False
        
        # 3. 让用户选择要返回的订单
        print(f"\n[步骤3] 找到 {len(travel_orders)} 个进行中的旅行订单")
        
        selected_order = self._select_travel_order(travel_orders)
        if not selected_order:
            return None
        
        order_id = selected_order['orderId']
        role_name = selected_order.get('roleName', '未知角色')
        # 原区服（返回目标）
        home_area_name = selected_order.get('areaName', '未知')
        home_server_name = selected_order.get('groupName', '未知')
        # 当前位置（目的地）- 从订单中直接获取
        current_area_name = selected_order.get('targetAreaName', '未知')
        current_area_id = selected_order.get('targetAreaId')
        current_server_name = selected_order.get('targetGroupName', '未知')
        current_server_id = selected_order.get('targetGroupId')
        current_server_code = selected_order.get('targetGroupCode', '')
        
        debug_log(f"选择的订单: {selected_order}")
        
        # 4. 获取可返回的服务器列表（用于验证和获取完整服务器信息）
        print("\n[步骤4] 获取可返回的服务器列表...")
        return_areas = self.api.fetch_return_area_list()
        
        if not return_areas:
            show_error_message("未能获取可返回的服务器列表")
            return False
        
        # 5. 从服务器列表中找到当前所在的服务器（根据订单中的目的地信息）
        current_server = None
        current_area = None
        
        for area in return_areas:
            if area.get('areaId') == current_area_id or area.get('areaName') == current_area_name:
                current_area = area
                for server in area.get('groups', []):
                    if server.get('groupId') == current_server_id or server.get('groupName') == current_server_name:
                        current_server = server
                        break
                break
        
        # 如果找不到精确匹配，让用户手动选择服务器
        if not current_server:
            print(f"\n[信息] 订单显示当前位置: {current_area_name} - {current_server_name}")
            print("[信息] 需要确认当前所在的服务器...")
            
            # 找到对应大区
            if current_area:
                current_servers = current_area.get('groups', [])
            else:
                # 让用户选择大区
                current_area = show_area_selection(return_areas, "\n请选择当前所在的大区：")
                if not current_area:
                    return None
                current_servers = current_area.get('groups', [])
            
            if not current_servers:
                show_error_message(f"{current_area['areaName']} 没有可选的服务器")
                return False
            
            current_server = show_server_selection(
                current_servers,
                current_area['areaName'],
                f"\n请选择当前所在的服务器（{current_area['areaName']}）："
            )
            if not current_server:
                return None
        else:
            print(f"\n[信息] 当前位置: {current_area['areaName']} - {current_server['groupName']}")
        
        # 6. 显示确认信息
        print("\n" + "="*50)
        print("         超域返回确认信息")
        print("="*50)
        print(f"  旅行订单号: {order_id}")
        print(f"  角色名称: {role_name}")
        print(f"  当前位置: {current_area['areaName']} - {current_server['groupName']}")
        print(f"  返回目标: {home_area_name} - {home_server_name}")
        print("="*50)
        
        if not confirm_action("\n确认要执行超域返回吗？"):
            show_info_message("操作已取消")
            return None
        
        # 7. 执行返回操作（支持自动重试）
        print("\n[步骤5] 开始执行超域返回...")
        success = self._run_return_loop(
            order_id=order_id,
            role_name=role_name,
            current_area=current_area,
            current_server=current_server,
            home_area_name=home_area_name,
            home_server_name=home_server_name
        )
        
        return success
    
    def _find_active_travel_orders(self, orders_data):
        """
        从订单数据中查找活跃的旅行订单
        状态说明：
        - migrationType=4: 超域旅行出发服务
        - migrationType=5: 超域旅行返回服务
        - migrationStatus=5 + travelStatus=1: 旅行中【已达到目的地】
        - migrationStatusDesc="旅行中【已达到目的地】"
        """
        active_orders = []
        
        # 使用正确的字段名 orderlist
        order_list = orders_data.get('orderlist', [])
        
        for order in order_list:
            order_id = order.get('orderId', 'N/A')
            migration_type = order.get('migrationType', -1)
            migration_status = order.get('migrationStatus', -1)
            travel_status = order.get('travelStatus', -1)
            status_desc = order.get('migrationStatusDesc', '')
            
            debug_log(f"订单 {order_id}: migrationType={migration_type}, "
                     f"migrationStatus={migration_status}, travelStatus={travel_status}, "
                     f"statusDesc={status_desc}")
            
            # 筛选条件：
            # 1. migrationType=4 (超域旅行出发服务)
            # 2. migrationStatus=5 且 travelStatus=1 (旅行中/已达到目的地)
            # 或者直接判断 statusDesc 包含 "旅行中"
            is_travel_order = (migration_type == 4)  # 出发服务
            is_active = (migration_status == 5 and travel_status == 1) or ('旅行中' in status_desc)
            
            if is_travel_order and is_active:
                # 从 migrationDetailList 提取角色名
                detail_list = order.get('migrationDetailList', [])
                if detail_list:
                    order['roleName'] = detail_list[0].get('roleName', '未知角色')
                active_orders.append(order)
                debug_log(f"  -> 符合条件，加入活跃订单列表")
        
        return active_orders
    
    def _select_travel_order(self, travel_orders):
        """让用户选择要返回的订单"""
        if len(travel_orders) == 1:
            order = travel_orders[0]
            print()
            print("─" * 50)
            print(f"  订单号: {order.get('orderId', 'N/A')}")
            print(f"  角色: {order.get('roleName', '未知')}")
            print(f"  原区服: {order.get('areaName', '未知')} - {order.get('groupName', '未知')}")
            print(f"  目的地: {order.get('targetAreaName', '未知')} - {order.get('targetGroupName', '未知')}")
            print(f"  状态: {order.get('migrationStatusDesc', '未知')}")
            print(f"  创建时间: {order.get('createTime', '未知')}")
            print("─" * 50)
            return order
        
        # 多个订单，让用户选择
        print()
        print("找到多个旅行中的订单，请选择：")
        print()
        
        for i, order in enumerate(travel_orders, 1):
            print(f"  [{i}] 角色: {order.get('roleName', '未知')}")
            print(f"      原区服: {order.get('areaName', '未知')} - {order.get('groupName', '未知')}")
            print(f"      目的地: {order.get('targetAreaName', '未知')} - {order.get('targetGroupName', '未知')}")
            print(f"      状态: {order.get('migrationStatusDesc', '未知')}")
            print(f"      订单号: {order.get('orderId', 'N/A')}")
            print()
        
        print("  [0] 取消")
        print()
        
        while True:
            try:
                choice = input("请输入选项编号: ").strip()
                if choice == '0':
                    return None
                
                idx = int(choice) - 1
                if 0 <= idx < len(travel_orders):
                    return travel_orders[idx]
                else:
                    print("[错误] 无效的选项，请重新输入")
            except ValueError:
                print("[错误] 请输入有效的数字")
    
    def _run_return_loop(self, order_id, role_name, current_area, current_server, 
                         home_area_name, home_server_name):
        """
        执行超域返回循环，支持自动重试
        每次间隔随机61~65秒
        """
        attempt = 0
        
        while True:
            attempt += 1
            print()
            print(f"{'='*50}")
            print(f"[尝试] 第 {attempt} 次提交超域返回请求...")
            print(f"{'='*50}")
            
            # 提交返回请求
            result = self.api.submit_travel_back(
                travel_order_id=order_id,
                group_id=current_server['groupId'],
                group_code=current_server['groupCode'],
                group_name=current_server['groupName']
            )
            
            if result and result.get('success'):
                # 请求提交成功，开始轮询订单状态
                return_order_id = result.get('orderId', '')
                print(f"\n[成功] 返回请求已提交")
                if return_order_id:
                    print(f"[信息] 返回订单号: {return_order_id}")
                
                # 轮询订单状态，等待返回完成
                print("\n[信息] 正在等待返回完成，轮询订单状态...")
                
                poll_success = self._poll_return_status(order_id, return_order_id)
                
                if poll_success:
                    # 返回成功
                    print()
                    print("*" * 50)
                    print("*")
                    print(f"*    超域返回成功！")
                    print(f"*    角色 [{role_name}] 已返回至 {home_server_name}")
                    print("*")
                    if return_order_id:
                        print(f"*    返回订单号: {return_order_id}")
                    print("*")
                    print("*" * 50)
                    print()
                    
                    # 记录历史
                    log_transfer_history(
                        role_name,
                        current_area['areaName'], current_server['groupName'],
                        home_area_name, home_server_name,
                        success=True,
                        order_id=return_order_id or order_id
                    )
                    
                    # 记录遥测统计
                    telemetry.record_return()
                    
                    # 显示操作后广告
                    print_after_action_ads()
                    
                    return True
                else:
                    # 轮询超时或失败，继续重试
                    print("\n[信息] 返回状态未确认，将继续重试...")
            
            elif result and not result.get('success'):
                # 返回了结果但失败了
                result_msg = result.get('resultMsg', '未知错误')
                result_code = result.get('resultCode', -1)
                
                print(f"\n[信息] 返回失败: {result_msg} (code: {result_code})")
                print("[信息] 将在61~65秒后自动重试...")
            
            else:
                # 请求失败
                print("\n[信息] 提交请求失败，将在61~65秒后自动重试...")
            
            # 等待随机间隔后重试
            wait_sec = random.randint(61, 65)
            print()
            print(f"[等待] 等待 {wait_sec} 秒后进行下一次尝试...")
            print("[提示] 按 Ctrl+C 可以中断程序")
            
            try:
                for remaining in range(wait_sec, 0, -1):
                    print(f"\r[倒计时] {remaining} 秒...", end='', flush=True)
                    time.sleep(1)
                print()
            except KeyboardInterrupt:
                print()
                print("\n[中断] 用户取消操作")
                
                # 记录失败历史
                log_transfer_history(
                    role_name,
                    current_area['areaName'], current_server['groupName'],
                    home_area_name, home_server_name,
                    success=False
                )
                
                return None
    
    def _poll_return_status(self, travel_order_id, return_order_id, max_attempts=12, interval=5):
        """
        轮询订单状态，检查返回是否成功
        
        :param travel_order_id: 原旅行订单号
        :param return_order_id: 返回订单号
        :param max_attempts: 最大轮询次数（默认12次，共60秒）
        :param interval: 轮询间隔秒数
        :return: True=返回成功, False=未成功或超时
        """
        for attempt in range(1, max_attempts + 1):
            print(f"[轮询] 第 {attempt}/{max_attempts} 次查询订单状态...")
            
            try:
                orders_data = self.api.fetch_migration_orders()
                
                if not orders_data:
                    debug_log("轮询时获取订单列表失败")
                    time.sleep(interval)
                    continue
                
                order_list = orders_data.get('orderlist', [])
                
                # 查找返回订单的状态
                for order in order_list:
                    order_id = order.get('orderId', '')
                    migration_type = order.get('migrationType', -1)
                    status_desc = order.get('migrationStatusDesc', '')
                    
                    # 检查是否是返回订单 (migrationType=5)
                    # 并且订单号匹配（返回订单号或原旅行订单号）
                    if migration_type == 5:
                        if order_id == return_order_id or order_id == travel_order_id:
                            debug_log(f"找到返回订单: {order_id}, 状态: {status_desc}")
                            
                            if '返回成功' in status_desc:
                                print(f"[状态] 订单状态: {status_desc}")
                                return True
                            elif '失败' in status_desc:
                                print(f"[状态] 订单状态: {status_desc}")
                                return False
                            else:
                                print(f"[状态] 订单状态: {status_desc}，继续等待...")
                
                # 也检查原旅行订单是否变为"旅行结束"
                for order in order_list:
                    order_id = order.get('orderId', '')
                    migration_type = order.get('migrationType', -1)
                    status_desc = order.get('migrationStatusDesc', '')
                    travel_status = order.get('travelStatus', -1)
                    
                    if order_id == travel_order_id and migration_type == 4:
                        if '旅行结束' in status_desc or travel_status == 3:
                            print(f"[状态] 原旅行订单状态: {status_desc}")
                            # 原订单变为旅行结束，说明返回成功
                            return True
                
            except Exception as e:
                debug_log(f"轮询订单状态异常: {e}")
            
            if attempt < max_attempts:
                time.sleep(interval)
        
        print("[超时] 订单状态轮询超时")
        return False


# 便捷函数
def create_return_service(api_client, config_manager):
    """创建返回服务实例"""
    return ReturnService(api_client, config_manager)
