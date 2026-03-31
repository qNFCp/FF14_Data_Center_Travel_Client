#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行时公共能力：版本、遥测、公告。"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ..backend import ads_client, telemetry, version_client


class RuntimeService:
    """封装 GUI/CLI 都可复用的运行时能力。"""

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._log = logger or (lambda _msg: None)

    def record_app_start(self):
        """记录应用启动遥测。"""
        telemetry.record_app_start()

    def check_version(self) -> Dict[str, object]:
        """检查版本并返回统一结果。"""
        info = version_client.check_version()
        if not info:
            return {
                "can_continue": True,
                "is_latest": True,
                "message": "版本检查失败，已按兼容模式继续。",
                "version_info": None,
            }

        if not info.get("is_supported", True):
            return {
                "can_continue": False,
                "is_latest": False,
                "message": "当前版本过旧且被强制更新，请先升级。",
                "version_info": info,
            }

        if not info.get("is_latest", True):
            return {
                "can_continue": True,
                "is_latest": False,
                "message": "发现新版本，可继续使用当前版本。",
                "version_info": info,
            }

        return {
            "can_continue": True,
            "is_latest": True,
            "message": "当前已是最新版本。",
            "version_info": info,
        }

    def get_bottom_announcements(self) -> List[dict]:
        """获取操作后公告（与CLI一致）。"""
        return ads_client.get_after_action_ads()
