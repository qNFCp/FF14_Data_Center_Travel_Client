#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT UI模块
负责用户界面交互和显示
"""

from .config import VERSION, ConfigManager, DEBUG_MODE
from .backend import ads_client
from .logger import get_last_transfer_from_history


def print_header():
    """打印程序头部信息"""
    print("\n" + "="*60)
    print(f"             FF14 超域传送工具 v{VERSION}\n\n")
    print("(本工具是开源免费工具, 如果你是购买获得本程序的, 那你应该被骗啦!)")
    if DEBUG_MODE:
        print("           [开发模式]")
    print("="*60)


def print_separator(char="-", length=50):
    """打印分隔线"""
    print(char * length)


def print_after_action_ads():
    """打印操作完成后的赞助内容"""
    try:
        ads = ads_client.get_after_action_ads()
        if ads:
            print("\n" + "*"*50)
            print("  [赞助内容]")
            for ad in ads:
                title = ad.get('title', '')
                content = ad.get('content', '')
                link = ad.get('link_url', '')
                
                if title:
                    print(f"{title}")
                if content:
                    print(f"     {content}")
                if link:
                    print(f"     🔗 {link}")
            print("*"*50)
    except Exception as e:
        pass  # 赞助内容获取失败不影响程序运行


def show_main_menu(config_manager):
    """显示主菜单并获取用户选择"""
    print("\n请选择操作：")
    print("-" * 40)
    print("  1. 跨区传送 (超域出发)")
    print("  2. 超域返回")
    print("  0. 退出程序")
    print("-" * 40)
    
    # 显示上次传送目标提示
    last_transfer = config_manager.get_last_transfer()
    if last_transfer:
        area = last_transfer.get('area', '')
        server = last_transfer.get('server', '')
        if area and server:
            print(f"\n  💡 上次传送目标: {area} - {server}")
    
    print()
    try:
        return input("请输入选项 (0/1/2): ").strip()
    except KeyboardInterrupt:
        print("\n[中断] 用户取消操作")
        return '0'


def show_area_selection(areas, prompt="请选择大区："):
    """显示大区选择"""
    print(f"\n{prompt}")
    for i, area in enumerate(areas, 1):
        print(f"  [{i}] {area['areaName']}")
    print("  [0] 返回")
    
    while True:
        try:
            choice = input("\n请输入选项: ").strip()
            if choice == '0':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(areas):
                return areas[idx]
            print("[错误] 无效的选项，请重新输入")
        except ValueError:
            print("[错误] 请输入数字")
        except KeyboardInterrupt:
            print("\n[中断] 用户取消选择")
            return None


def show_server_selection(servers, area_name, prompt=None):
    """显示服务器选择"""
    if prompt is None:
        prompt = f"请选择 {area_name} 的服务器："
    
    print(f"\n{prompt}")
    for i, server in enumerate(servers, 1):
        print(f"  [{i}] {server['groupName']}")
    print("  [0] 返回")
    
    while True:
        try:
            choice = input("\n请输入选项: ").strip()
            if choice == '0':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(servers):
                return servers[idx]
            print("[错误] 无效的选项，请重新输入")
        except ValueError:
            print("[错误] 请输入数字")
        except KeyboardInterrupt:
            print("\n[中断] 用户取消选择")
            return None


def show_server_selection_with_default(servers, area_name, default_server_name, prompt=None):
    """显示服务器选择（带默认值）"""
    if prompt is None:
        prompt = f"请确认您当前所在的服务器（{area_name}）："
    
    # 找到默认服务器的索引
    default_idx = None
    for i, server in enumerate(servers):
        if server['groupName'] == default_server_name:
            default_idx = i
            break
    
    print(f"\n{prompt}")
    print(f"\n[说明] 订单显示您的目的地是 [{default_server_name}]")
    print("[提示] 如果您在大区内又跨服到其他服务器，请选择实际所在服务器")
    print()
    
    for i, server in enumerate(servers, 1):
        server_name = server['groupName']
        default_marker = " (默认)" if server_name == default_server_name else ""
        print(f"  [{i}] {server_name}{default_marker}")
    print("  [0] 返回")
    
    while True:
        try:
            prompt_text = "\n请输入选项"
            if default_idx is not None:
                prompt_text += f" (回车确认 [{default_server_name}])"
            prompt_text += ": "
            
            choice = input(prompt_text).strip()
            
            # 如果用户直接回车且有默认值，返回默认服务器
            if choice == '' and default_idx is not None:
                return servers[default_idx]
            
            if choice == '0':
                return None
            
            idx = int(choice) - 1
            if 0 <= idx < len(servers):
                return servers[idx]
            print("[错误] 无效的选项，请重新输入")
        except ValueError:
            print("[错误] 请输入数字")
        except KeyboardInterrupt:
            print("\n[中断] 用户取消选择")
            return None


def show_role_selection(roles, server_name):
    """显示角色选择"""
    if not roles:
        print(f"\n[信息] 在 {server_name} 没有找到角色")
        return None
    
    print(f"\n请选择角色（{server_name}）：")
    for i, role in enumerate(roles, 1):
        role_name = role.get('roleName', role.get('name', '未知'))
        print(f"  [{i}] {role_name}")
    print("  [0] 返回")
    
    while True:
        try:
            choice = input("\n请输入选项: ").strip()
            if choice == '0':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(roles):
                return roles[idx]
            print("[错误] 无效的选项，请重新输入")
        except ValueError:
            print("[错误] 请输入数字")
        except KeyboardInterrupt:
            print("\n[中断] 用户取消选择")
            return None


def confirm_action(message):
    """确认操作"""
    print(f"\n{message}")
    try:
        choice = input("确认开始传送? (y/n): ").strip().lower()
        return choice == 'y'
    except KeyboardInterrupt:
        print("\n[中断] 用户取消操作")
        return False


def show_transfer_summary(role_name, source_area, source_server, target_area, target_server):
    """显示传送摘要"""
    print("\n" + "="*50)
    print("传送信息确认:")
    print(f"  角色: {role_name}")
    print(f"  源区服: {source_area} - {source_server}")
    print(f"  目标区服: {target_area} - {target_server}")
    print("="*50)


def show_version_update_notice(version_info):
    """显示版本更新提示"""
    print("\n" + "!"*60)
    print("  ⚠️  发现新版本!")
    print(f"  当前版本: {version_info['current_version']}")
    print(f"  最新版本: {version_info['latest_version']}")
    
    if version_info.get('changelog'):
        print(f"\n  更新日志:")
        for line in version_info['changelog'].split('\n')[:5]:
            print(f"    {line}")
    
    update_url = version_info.get('update_url', '').strip()
    if update_url:
        print(f"\n  下载地址: {update_url}")
    else:
        print(f"\n  下载地址: (暂未设置)")
    
    print("!"*60)


def show_version_blocked_notice(version_info):
    """显示版本不受支持的阻止提示（需要强制更新）"""
    print("\n" + "X"*60)
    print("  ❌ 版本过旧，需要强制更新!")
    print(f"  当前版本: {version_info['current_version']}")
    print(f"  最新版本: {version_info['latest_version']}")
    
    if version_info.get('update_url'):
        print(f"\n  请下载最新版本: {version_info['update_url']}")
    
    print("X"*60)


def show_success_message(message):
    """显示成功消息"""
    print(f"\n✅ {message}")


def show_error_message(message):
    """显示错误消息"""
    print(f"\n❌ {message}")


def show_info_message(message):
    """显示信息消息"""
    print(f"\nℹ️  {message}")


def show_warning_message(message):
    """显示警告消息"""
    print(f"\n⚠️  {message}")


def wait_for_enter(prompt="按回车键继续..."):
    """等待用户按回车"""
    try:
        input(f"\n{prompt}")
    except (KeyboardInterrupt, EOFError):
        print("\n[中断] 用户取消操作")
        pass
