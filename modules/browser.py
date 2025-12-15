#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 浏览器模块
负责浏览器初始化、登录Cookie获取
"""

import time
import webbrowser

# 尝试导入selenium
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from .config import (
    ConfigManager, FF14_LOGIN_URL, DEBUG_MODE,
    USE_HTTP_PROXY, HTTP_PROXY
)
from .logger import debug_log


class BrowserManager:
    """浏览器管理器"""
    
    def __init__(self, config_manager=None):
        self.driver = None
        self.config = config_manager or ConfigManager()
        self.default_browser = self.config.get_browser()
        
        # 记录代理设置（如果启用）
        if USE_HTTP_PROXY and HTTP_PROXY:
            debug_log(f"浏览器将使用HTTP代理: {HTTP_PROXY}")
    
    def init_browser(self):
        """初始化浏览器，询问用户选择"""
        if not SELENIUM_AVAILABLE:
            print("[提示] 未安装selenium，将使用系统默认浏览器打开页面")
            print("[提示] 请手动完成登录后回到此处继续")
            webbrowser.open(FF14_LOGIN_URL)
            return False
        
        browsers = [
            ("Edge", self._init_edge),
            ("Chrome", self._init_chrome),
            ("Firefox", self._init_firefox),
        ]
        
        while True:
            selection = self._prompt_browser_choice(browsers)
            if selection is None:
                # 用户取消选择，直接返回False不打开浏览器
                return False
            name, init_func = selection
            try:
                print(f"[信息] 正在启动 {name} 浏览器...")
                if init_func():
                    print(f"[成功] {name} 浏览器启动成功")
                    self._save_default_browser(name)
                    return True
            except Exception as e:
                debug_log(f"{name} 启动失败详情: {e}")
                print(f"[警告] {name} 启动失败: {str(e)[:80]}")
                try:
                    if self.driver:
                        self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                print("[提示] 请重新选择其他浏览器")
        
        return False
    
    def _prompt_browser_choice(self, browsers):
        """询问用户选择浏览器，支持默认值"""
        browser_names = [name for name, _ in browsers]
        default_available = self.default_browser if self.default_browser in browser_names else None
        print()
        print("[选择] 请选择要使用的浏览器：")
        for idx, name in enumerate(browser_names, 1):
            extra = " (默认)" if default_available == name else ""
            print(f"  {idx}. {name}{extra}")
        print("  q. 取消选择并使用系统默认浏览器")
        
        while True:
            prompt = "请输入序号"
            if default_available:
                prompt += f" (回车选择 {default_available})"
            prompt += ": "
            try:
                choice = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[中断] 用户取消选择")
                return None
            
            if choice == '' and default_available:
                idx = browser_names.index(default_available)
                return browsers[idx]
            if choice.lower() == 'q':
                return None
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(browsers):
                    return browsers[idx]
            except ValueError:
                pass
            print("[错误] 请输入有效的选项")
    
    def _save_default_browser(self, browser_name):
        """保存默认浏览器到配置文件"""
        if browser_name:
            self.config.set_browser(browser_name)
            self.default_browser = browser_name
    
    def _init_chrome(self):
        """初始化Chrome浏览器"""
        try:
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            if USE_HTTP_PROXY and HTTP_PROXY:
                options.add_argument(f'--proxy-server={HTTP_PROXY}')
            
            if not DEBUG_MODE:
                options.add_argument('--log-level=3')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            debug_log("Chrome浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"[错误] Chrome初始化失败: {e}")
            return False
    
    def _init_edge(self):
        """初始化Edge浏览器"""
        try:
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.edge.service import Service
            
            options = Options()
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            if USE_HTTP_PROXY and HTTP_PROXY:
                options.add_argument(f'--proxy-server={HTTP_PROXY}')
            
            if not DEBUG_MODE:
                options.add_argument('--log-level=3')
            
            self.driver = webdriver.Edge(options=options)
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            debug_log("Edge浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"[错误] Edge初始化失败: {e}")
            return False
    
    def _init_firefox(self):
        """初始化Firefox浏览器"""
        try:
            from selenium.webdriver.firefox.options import Options
            
            options = Options()
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference('useAutomationExtension', False)
            
            if USE_HTTP_PROXY and HTTP_PROXY:
                # 解析代理设置
                proxy_parts = HTTP_PROXY.replace('http://', '').split(':')
                if len(proxy_parts) == 2:
                    options.set_preference("network.proxy.type", 1)
                    options.set_preference("network.proxy.http", proxy_parts[0])
                    options.set_preference("network.proxy.http_port", int(proxy_parts[1]))
                    options.set_preference("network.proxy.ssl", proxy_parts[0])
                    options.set_preference("network.proxy.ssl_port", int(proxy_parts[1]))
            
            self.driver = webdriver.Firefox(options=options)
            
            debug_log("Firefox浏览器初始化成功")
            return True
            
        except Exception as e:
            print(f"[错误] Firefox初始化失败: {e}")
            return False
    
    def open_login_page(self):
        """打开登录页面"""
        if not self.driver:
            print("[错误] 浏览器未初始化")
            return False
        
        try:
            print("[信息] 正在打开登录页面...")
            self.driver.get(FF14_LOGIN_URL)
            debug_log(f"已打开登录页面: {FF14_LOGIN_URL}")
            
            # 等待页面加载后尝试点击登录按钮
            time.sleep(3)
            self._click_login_button()
            
            return True
        except Exception as e:
            print(f"[错误] 打开登录页面失败: {e}")
            return False
    
    def _click_login_button(self):
        """自动点击登录按钮"""
        if not self.driver:
            print("[提示] 请在浏览器中手动点击登录按钮")
            return
        
        try:
            # 首先检查是否存在遮罩层
            has_modal = False
            modal_check_selectors = [
                ".modal-backdrop",
                ".ant-modal-mask",
                ".ant-modal-wrap",
                "//div[contains(@class, 'modal-backdrop')]",
                "//div[contains(@class, 'ant-modal-mask')]",
            ]
            
            for selector in modal_check_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # 检查元素是否可见
                    if element.is_displayed():
                        has_modal = True
                        debug_log(f"检测到遮罩层: {selector}")
                        break
                except NoSuchElementException:
                    continue
                except Exception as e:
                    debug_log(f"检查遮罩层时出错 ({selector}): {e}")
                    continue
            
            if has_modal:
                debug_log("[DEBUG] 检测到页面遮罩层，跳过自动点击登录按钮")
                return
            
            # 未检测到遮罩层，尝试查找并点击登录按钮
            debug_log("未检测到遮罩层，尝试自动点击登录按钮")
            login_button_selectors = [
                "//button[contains(@class, 'ant-btn') and contains(@class, 'blueButton')]//span[contains(text(), '登')]/..",
                "//button[contains(text(), '登')]",
                "//span[contains(text(), '登 录')]/parent::button",
                ".ant-btn.blueButton.ant-btn-primary"
            ]
            
            for selector in login_button_selectors:
                try:
                    if selector.startswith("//"):
                        button = self.driver.find_element(By.XPATH, selector)
                    else:
                        button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # 使用JavaScript点击来避免元素被遮挡的问题
                    self.driver.execute_script("arguments[0].click();", button)
                    print("[信息] 已自动点击登录按钮，请在浏览器中完成登录")
                    return
                except NoSuchElementException:
                    continue
                except ElementClickInterceptedException:
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        print("[信息] 已自动点击登录按钮，请在浏览器中完成登录")
                        return
                    except:
                        continue
            
            print("[提示] 未找到登录按钮，可能已经登录或页面结构变化")
            print("[提示] 请检查浏览器页面状态")
            
        except Exception as e:
            debug_log(f"点击登录按钮详细错误: {e}")
            print(f"[提示] 请手动点击登录按钮完成登录")
    
    def wait_for_login(self, timeout=300):
        """等待用户完成登录"""
        if not self.driver:
            return False
        
        print("[信息] 请在浏览器中完成登录...")
        print("[信息] 登录成功后会自动检测并继续")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 检查登录状态的Cookie
                cookies = self.driver.get_cookies()
                cookie_names = [c['name'] for c in cookies]
                
                # SDO登录后会有这些Cookie
                login_indicators = ['STID', 'tgc', 'sdoId']
                
                for indicator in login_indicators:
                    if indicator in cookie_names:
                        debug_log(f"检测到登录Cookie: {indicator}")
                        print("[成功] 检测到登录状态")
                        return True
                
                # 也可以检查页面元素变化
                current_url = self.driver.current_url
                if 'login' not in current_url.lower() and 'ff14bjz.sdo.com' in current_url:
                    debug_log(f"页面已跳转: {current_url}")
                    print("[成功] 检测到页面跳转，登录可能已完成")
                    time.sleep(2)  # 等待Cookie完全设置
                    return True
                
            except Exception as e:
                debug_log(f"检查登录状态时出错: {e}")
            
            time.sleep(2)  # 每2秒检查一次
        
        print("[错误] 登录超时")
        return False
    
    def get_cookies(self):
        """获取当前所有Cookie"""
        if not self.driver:
            return {}
        
        try:
            cookies = self.driver.get_cookies()
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie['name']] = cookie['value']
            
            debug_log(f"获取到 {len(cookie_dict)} 个Cookie")
            return cookie_dict
            
        except Exception as e:
            print(f"[错误] 获取Cookie失败: {e}")
            return {}
    
    def get_sdo_cookies(self):
        """获取SDO相关的Cookie"""
        all_cookies = self.get_cookies()
        
        # SDO登录相关的重要Cookie
        important_keys = ['STID', 'tgc', 'sdoId', 'sessionId', 'JSESSIONID']
        sdo_cookies = {}
        
        for key in all_cookies:
            # 保留所有Cookie，但标记重要的
            sdo_cookies[key] = all_cookies[key]
        
        return sdo_cookies
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                debug_log("浏览器已关闭")
            except Exception as e:
                debug_log(f"关闭浏览器时出错: {e}")
            finally:
                self.driver = None
    
    def __del__(self):
        """析构函数，确保浏览器被关闭"""
        self.close()
