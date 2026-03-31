#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录相关服务编排。"""

from __future__ import annotations

from typing import Callable, Optional

from ..api import FF14APIClient
from ..browser import BrowserManager
from ..config import ConfigManager
from ..credential import credential_manager


class LoginService:
    """封装缓存登录和浏览器登录流程。"""

    def __init__(self, config_manager: Optional[ConfigManager] = None, logger: Optional[Callable[[str], None]] = None):
        self.config = config_manager or ConfigManager()
        self._log = logger or (lambda _msg: None)
        self.browser_mgr: Optional[BrowserManager] = None

    def try_cached_login(self) -> Optional[FF14APIClient]:
        """尝试缓存登录，成功返回已登录的 API 客户端。"""
        self._log("检查缓存登录凭据…")
        cookies = credential_manager.load_cookies()
        if not cookies:
            self._log("未找到缓存Cookie。")
            return None

        self._log(f"找到缓存Cookie({len(cookies)}个)，正在验证…")
        api = FF14APIClient()
        api.set_cookies(cookies)
        if api.fetch_area_list():
            self._log("缓存登录有效。")
            return api

        self._log("缓存登录失效，已清除。")
        credential_manager.delete_cookies()
        return None

    def open_login_page(self, browser_choice: str) -> BrowserManager:
        """初始化指定浏览器并打开登录页。"""
        self.browser_mgr = BrowserManager(self.config)
        if not self.browser_mgr.init_browser_with_choice(browser_choice):
            raise RuntimeError("浏览器初始化失败")
        if not self.browser_mgr.open_login_page():
            raise RuntimeError("无法打开登录页面")
        self._log("请在浏览器中完成登录，再回到程序继续。")
        return self.browser_mgr

    def confirm_login(self) -> FF14APIClient:
        """确认浏览器登录，拉取 Cookie 并验证。"""
        if not self.browser_mgr:
            raise RuntimeError("请先打开登录页面")

        cookies = self.browser_mgr.get_sdo_cookies()
        if not cookies:
            raise RuntimeError("未获取到Cookie，请确认浏览器登录是否成功")

        api = FF14APIClient()
        api.set_cookies(cookies)
        if not api.fetch_area_list():
            raise RuntimeError("登录验证失败，请稍后重试")

        credential_manager.save_cookies(cookies)
        self._log("登录凭据已保存。")
        return api

    def clear_cached_login(self):
        """清除本地缓存凭据。"""
        credential_manager.delete_cookies()
        self._log("已清除缓存Cookie。")

    def close_browser(self):
        """关闭浏览器资源。"""
        if self.browser_mgr:
            self.browser_mgr.close()
            self.browser_mgr = None
