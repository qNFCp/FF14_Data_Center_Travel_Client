#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 跨区传送模块
负责超域传送的主要业务逻辑
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


class TransferService:
    """跨区传送服务"""
    
    def __init__(self, api_client, config_manager):
        """
        初始化传送服务
        :param api_client: FF14APIClient实例
        :param config_manager: ConfigManager实例
        """
        self.api = api_client
        self.config = config_manager
    
    def execute_transfer(self):
        """
        执行跨区传送流程
        返回: True=成功, False=失败, None=用户取消
        """
        # 1. 获取大区列表
        areas = self.api.get_areas()
        if not areas:
            show_error_message("未能获取大区列表，请重试")
            return False
        
        # 2. 选择源大区
        print("\n=== 第1步: 选择当前所在大区 ===")
        source_area = show_area_selection(areas, "请选择当前所在的大区：")
        if not source_area:
            return None
        
        # 3. 选择源服务器
        source_servers = self.api.get_servers(source_area)
        if not source_servers:
            show_error_message(f"未能获取 {source_area['areaName']} 的服务器列表")
            return False
        
        source_server = show_server_selection(
            source_servers, 
            source_area['areaName'],
            f"请选择当前角色所在的服务器（{source_area['areaName']}）："
        )
        if not source_server:
            return None
        
        # 4. 获取角色列表
        print("\n[信息] 正在获取角色列表...")
        roles = self.api.fetch_role_list(
            source_area['areaId'], 
            source_server['groupId']
        )
        
        if not roles:
            show_error_message(f"在 {source_server['groupName']} 没有找到角色")
            return False
        
        # 5. 选择角色
        role = show_role_selection(roles, source_server['groupName'])
        if not role:
            return None
        
        role_name = role.get('roleName', role.get('name', '未知'))
        
        # 6. 选择目标大区
        print("\n=== 第2步: 选择目标大区 ===")
        
        # 获取上次传送目标作为提示
        last_transfer = self.config.get_last_transfer()
        if last_transfer:
            show_info_message(f"上次传送目标: {last_transfer.get('area', '')} - {last_transfer.get('server', '')}")
        
        # 过滤掉源大区（不能传送到同一大区）
        target_areas = [a for a in areas if a['areaId'] != source_area['areaId']]
        
        target_area = show_area_selection(target_areas, "请选择要前往的大区：")
        if not target_area:
            return None
        
        # 7. 选择目标服务器
        target_servers = self.api.get_servers(target_area)
        if not target_servers:
            show_error_message(f"未能获取 {target_area['areaName']} 的服务器列表")
            return False
        
        target_server = show_server_selection(
            target_servers,
            target_area['areaName'],
            f"请选择目标服务器（{target_area['areaName']}）："
        )
        if not target_server:
            return None
        
        # 8. 显示确认信息
        show_transfer_summary(
            role_name,
            source_area['areaName'],
            source_server['groupName'],
            target_area['areaName'],
            target_server['groupName']
        )
        
        if not confirm_action("确认要执行跨区传送吗？"):
            show_info_message("操作已取消")
            return None
        
        # 9. 触发页面初始化
        print("\n[信息] 正在初始化...")
        self.api.page_init(migration_type=4)
        
        # 10. 执行传送循环（支持自动重试）
        success = self._run_transfer_loop(
            source_area, source_server,
            target_area, target_server,
            role, role_name
        )
        
        return success
    
    def _run_transfer_loop(self, source_area, source_server, target_area, target_server, role, role_name):
        """
        执行跨区传送循环，支持自动重试
        每次间隔随机61~65秒
        """
        attempt = 0
        order_id = None
        
        while True:
            attempt += 1
            print()
            print(f"{'='*50}")
            print(f"[尝试] 第 {attempt} 次提交跨区传送请求...")
            print(f"{'='*50}")
            
            result = self.api.submit_transfer(
                source_area, source_server,
                target_area, target_server,
                role
            )
            
            if isinstance(result, str) and result.startswith('GM'):
                # 成功获取订单号
                order_id = result
                
                # 轮询订单状态
                print()
                print("[信息] 正在检查订单状态...")
                
                for check_attempt in range(10):
                    print(f"[检查] 第 {check_attempt + 1}/10 次状态查询...")
                    status = self.api.check_order_status(order_id)
                    
                    if status == 5:  # 传送成功
                        print()
                        print("*" * 50)
                        print(f"*       跨区传送成功！已传送至 {target_server['groupName']} ")
                        print("*" * 50)
                        print()
                        
                        # 记录历史
                        log_transfer_history(
                            role_name,
                            source_area['areaName'], source_server['groupName'],
                            target_area['areaName'], target_server['groupName'],
                            success=True,
                            order_id=order_id
                        )
                        
                        # 保存上次传送目标
                        self.config.set_last_transfer(
                            target_area['areaName'],
                            target_server['groupName']
                        )
                        
                        # 记录遥测统计
                        telemetry.record_transfer()
                        
                        # 显示操作后广告
                        print_after_action_ads()
                        
                        return True
                    elif status == -1:  # 预检失败
                        print("[信息] 预检失败，将在61~65秒后重试...")
                        break
                    
                    time.sleep(5)  # 每5秒检查一次状态
                    
            elif isinstance(result, dict):
                # 返回了数据但没有订单号
                result_code = result.get('resultCode', -1)
                result_msg = result.get('resultMsg', '未知')
                if result_code == 0 or result_code == 5:  # 成功状态
                    print()
                    print("*" * 50)
                    print(f"*       跨区传送成功！已传送至 {target_server['groupName']} ")
                    print("*" * 50)
                    print()
                    
                    # 记录历史
                    log_transfer_history(
                        role_name,
                        source_area['areaName'], source_server['groupName'],
                        target_area['areaName'], target_server['groupName'],
                        success=True
                    )
                    
                    # 保存上次传送目标
                    self.config.set_last_transfer(
                        target_area['areaName'],
                        target_server['groupName']
                    )
                    
                    # 记录遥测统计
                    telemetry.record_transfer()
                    
                    # 显示操作后广告
                    print_after_action_ads()
                    
                    return True
                else:
                    print(f"[信息] 传送结果: {result_msg}，将继续重试...")
            else:
                print("[信息] 提交失败，将在61~65秒后重试...")
            
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
                print("[中断] 用户取消操作")
                # 记录失败历史
                log_transfer_history(
                    role_name,
                    source_area['areaName'], source_server['groupName'],
                    target_area['areaName'], target_server['groupName'],
                    success=False
                )
                return None
