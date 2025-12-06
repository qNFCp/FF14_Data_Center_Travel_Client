#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14 跨数据中心旅行工具 (Data Center Travel)

功能:
- 跨区旅行（传送到其他大区）
- 返回母区
- 遥测统计
- 版本检查
- 广告展示
- 传送历史记录
"""

import sys
import signal

# 导入模块
from modules import (
    VERSION, ConfigManager, DEBUG_MODE,
    debug_log, init_log_file, FF14APIClient,
    telemetry, version_client,
    BrowserManager, TransferService, ReturnService,
    print_header, show_main_menu,
    show_version_update_notice, show_version_blocked_notice,
    show_success_message, show_error_message, show_info_message,
    wait_for_enter
)


class FF14DCTApp:
    """FF14 跨数据中心旅行工具主应用"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.browser = None
        self.api_client = None
        self._interrupted = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理Ctrl+C信号"""
        print()
        print("[中断] 检测到 Ctrl+C，正在安全退出...")
        self._interrupted = True
    
    def check_version(self):
        """
        检查版本更新
        返回: True=可以继续, False=版本过旧需要阻止
        """
        print("[信息] 正在检查版本...")
        
        version_info = version_client.check_version()
        
        if version_info is None:
            # 无法检查版本，允许继续
            debug_log("版本检查失败，允许继续")
            return True
        
        # 开发模式下输出详细版本信息
        debug_log(f"版本检查结果:")
        debug_log(f"  当前版本: {version_info['current_version']}")
        debug_log(f"  最新版本: {version_info['latest_version']}")
        debug_log(f"  是否最新: {version_info['is_latest']}")
        debug_log(f"  强制更新: {version_info['is_force_update']}")
        debug_log(f"  版本受支持: {version_info['is_supported']}")
        
        if not version_info['is_supported']:
            # 版本过旧，阻止运行
            debug_log("版本过旧且需要强制更新，阻止运行")
            show_version_blocked_notice(version_info)
            return False
        
        if not version_info['is_latest']:
            # 有新版本，提示但允许继续
            debug_log("有新版本可用，但不强制更新")
            show_version_update_notice(version_info)
        else:
            print(f"[信息] 当前版本 v{VERSION} 是最新版本")
        
        return True
    
    def init_browser_and_login(self):
        """初始化浏览器并等待用户登录"""
        print("\n[步骤1] 初始化浏览器...")
        
        self.browser = BrowserManager(self.config)
        
        if not self.browser.init_browser():
            show_error_message("浏览器初始化失败")
            return False
        
        print("[步骤2] 打开登录页面...")
        if not self.browser.open_login_page():
            show_error_message("无法打开登录页面")
            return False
        
        print("[步骤3] 等待用户登录...")
        print("-" * 40)
        print("[提示] 请在浏览器中完成登录操作")
        print("[提示] 登录完成后按回车键继续...")
        print("-" * 40)
        
        try:
            input()
        except EOFError:
            pass
        
        if self._interrupted:
            return False
        
        # 获取Cookie
        print("[步骤4] 获取登录Cookie...")
        cookies = self.browser.get_sdo_cookies()
        
        if not cookies:
            show_error_message("无法获取Cookie，请确保已登录")
            return False
        
        print(f"[成功] 获取到 {len(cookies)} 个Cookie")
        
        # 初始化API客户端并设置Cookie
        self.api_client = FF14APIClient()
        self.api_client.set_cookies(cookies)
        
        return True
    
    def fetch_game_data(self):
        """获取游戏数据（区服列表）"""
        print("\n[步骤5] 获取区服列表...")
        
        if not self.api_client.fetch_area_list():
            show_error_message("获取区服列表失败，请检查登录状态")
            return False
        
        return True
    
    def run_main_loop(self):
        """主循环"""
        transfer_service = TransferService(self.api_client, self.config)
        return_service = ReturnService(self.api_client, self.config)
        
        while not self._interrupted:
            # 显示主菜单
            choice = show_main_menu(self.config)
            
            if choice == '0':
                print("\n[退出] 感谢使用，再见！")
                break
            elif choice == '1':
                # 跨区旅行
                result = transfer_service.execute_transfer()
                if result is False:
                    show_error_message("跨区传送失败")
            elif choice == '2':
                # 返回母区
                result = return_service.execute_return()
                if result is False:
                    show_error_message("返回母区失败")
            else:
                print("[错误] 无效的选项，请重新输入")
            
            if self._interrupted:
                break
            
            # 传送业务结束后直接退出
            break
    
    def run(self):
        """主运行流程"""
        try:
            # 初始化日志文件（开发模式）
            init_log_file()
            
            # 显示程序头部
            print_header()
            
            # 记录应用启动遥测
            telemetry.record_app_start()
            debug_log("已记录应用启动统计")
            
            # 检查版本
            if not self.check_version():
                wait_for_enter("按回车键退出...")
                return
            
            if self._interrupted:
                return
            
            # 初始化浏览器并登录
            if not self.init_browser_and_login():
                wait_for_enter("按回车键退出...")
                return
            
            if self._interrupted:
                return
            
            # 获取游戏数据
            if not self.fetch_game_data():
                wait_for_enter("按回车键退出...")
                return
            
            if self._interrupted:
                return
            
            # 运行主循环
            self.run_main_loop()
            
        except KeyboardInterrupt:
            print("\n[中断] 用户中断程序")
        except Exception as e:
            show_error_message(f"程序异常: {e}")
            if DEBUG_MODE:
                import traceback
                traceback.print_exc()
        finally:
            self.cleanup()
    
    def cleanup(self, close_browser=False):
        """清理资源"""
        print("\n[清理] 正在关闭资源...")
        
        if close_browser and self.browser:
            self.browser.close()
        
        print("[完成] 程序运行结束")
        wait_for_enter()


def main():
    """程序入口"""
    app = FF14DCTApp()
    app.run()


if __name__ == "__main__":
    main()
