#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 配置管理模块
负责配置文件读写、常量定义
"""

import os
import json
import winreg
from datetime import datetime

# ==================== 版本信息 ====================
VERSION = "0.1.1"
APP_NAME = "FF14 超域传送工具"

# ==================== 运行配置 ====================
# 运行模式: True=开发模式(输出详细调试信息并输出日志文件), False=发行模式
DEBUG_MODE = False

# ==================== 后端API配置 ====================
BACKEND_BASE_URL = "https://ff14dct.233.be/main.php"

# ==================== FF14 API配置 ====================
FF14_BASE_URL = "https://ff14bjz.sdo.com"
FF14_APP_ID = "100001900"
FF14_TRANSFER_PAGE = f"{FF14_BASE_URL}/RegionKanTelepo"
FF14_ORDER_LIST_PAGE = f"{FF14_BASE_URL}/orderList"
FF14_LOGIN_URL = FF14_TRANSFER_PAGE  # 登录页面URL

# API端点
FF14_API_PAGE_INIT = f"{FF14_BASE_URL}/api/orderserivce/pageInit"
FF14_API_GROUP_LIST = f"{FF14_BASE_URL}/api/orderserivce/queryGroupListTravelSource"
FF14_API_ROLE_LIST = f"{FF14_BASE_URL}/api/gmallgateway/queryRoleList4Migration"
FF14_API_TRAVEL_ORDER = f"{FF14_BASE_URL}/api/orderserivce/travelOrder"
FF14_API_ORDER_STATUS = f"{FF14_BASE_URL}/api/gmallgateway/queryOrderStatus"

# 超域返回专用API端点
FF14_API_GROUP_LIST_CROSS_SOURCE = f"{FF14_BASE_URL}/api/gmallgateway/queryGroupListCrossSource"
FF14_API_TRAVEL_BACK = f"{FF14_BASE_URL}/api/orderserivce/travelBack"
FF14_API_MIGRATION_ORDERS = f"{FF14_BASE_URL}/api/orderserivce/queryMigrationOrders"

# ==================== HTTP配置 ====================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"

# HTTP代理配置（初始值，将被自动检测覆盖）
USE_HTTP_PROXY = False
HTTP_PROXY = None


def detect_system_proxy():
    """
    检测系统HTTP代理设置
    优先级：环境变量 > Windows注册表
    返回: (use_proxy: bool, proxy_url: str or None)
    """
    # 1. 检查环境变量
    env_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or \
                os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    
    if env_proxy:
        if DEBUG_MODE:
            print(f"[DEBUG] 检测到环境变量代理: {env_proxy}")
        return True, env_proxy
    
    # 2. 检查Windows注册表（仅Windows系统）
    try:
        import platform
        if platform.system() == 'Windows':
            # 访问Internet Settings注册表项
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_READ
            )
            
            # 检查是否启用代理
            try:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except FileNotFoundError:
                proxy_enable = 0
            
            # 如果启用了代理，获取代理服务器地址
            if proxy_enable:
                try:
                    proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                    winreg.CloseKey(key)
                    
                    # 处理代理服务器地址格式
                    # 可能的格式: "127.0.0.1:7890" 或 "http=127.0.0.1:7890;https=127.0.0.1:7890"
                    if '=' in proxy_server:
                        # 多协议代理，提取http代理
                        for part in proxy_server.split(';'):
                            if part.startswith('http='):
                                proxy_server = part.split('=', 1)[1]
                                break
                            elif part.startswith('https='):
                                proxy_server = part.split('=', 1)[1]
                                break
                    
                    # 确保代理地址有协议前缀
                    if not proxy_server.startswith('http://') and not proxy_server.startswith('https://'):
                        proxy_server = f"http://{proxy_server}"
                    
                    if DEBUG_MODE:
                        print(f"[DEBUG] 检测到Windows系统代理: {proxy_server}")
                    
                    return True, proxy_server
                except FileNotFoundError:
                    pass
                finally:
                    try:
                        winreg.CloseKey(key)
                    except:
                        pass
    except ImportError:
        # 非Windows系统，winreg不可用
        pass
    except Exception as e:
        if DEBUG_MODE:
            print(f"[DEBUG] 检测Windows代理失败: {e}")
    
    return False, None


# 初始化时自动检测代理
USE_HTTP_PROXY, HTTP_PROXY = detect_system_proxy()

# ==================== 文件路径 ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
CONFIG_FILE = os.path.join(BASE_DIR, "FF14_DCT_Config.json")
LOG_TRANSFER_HISTORY_FILE = os.path.join(LOG_DIR, "transfer_history.log")


class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_path=None):
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        default_config = {
            "default_browser": "Edge",
            "last_transfer": None  # 上次传送记录
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并默认配置和加载的配置
                    default_config.update(loaded)
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 加载配置文件失败: {e}")
        
        return default_config
    
    def _save_config(self):
        """保存配置文件"""
        try:
            # 确保配置文件所在目录存在
            config_dir = os.path.dirname(self.config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 保存配置文件失败: {e}")
            return False
    
    def get(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """设置配置项并保存"""
        self.config[key] = value
        return self._save_config()
    
    def get_browser(self):
        """获取默认浏览器"""
        return self.get("default_browser", "Edge")
    
    def set_browser(self, browser_name):
        """设置默认浏览器"""
        return self.set("default_browser", browser_name)
    
    def get_last_transfer(self):
        """获取上次传送记录"""
        return self.get("last_transfer")
    
    def set_last_transfer(self, area_name, server_name):
        """
        设置上次传送记录
        """
        transfer_info = {
            "area": area_name,
            "server": server_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return self.set("last_transfer", transfer_info)


# 全局配置管理器实例
config_manager = ConfigManager()

