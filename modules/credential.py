#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 凭据管理模块
负责Cookies的安全存储和读取（使用系统密钥环）

Windows测试可在运行窗口输入 rundll32.exe keymgr.dll,KRShowKeyMgr 开启凭据管理器
"""

import json
import keyring
from .config import DEBUG_MODE, APP_NAME
from .logger import debug_log

# 密钥环服务名称
KEYRING_SERVICE = "FF14DCT"
KEYRING_USERNAME = "sdo_cookies"


class CredentialManager:
    """凭据管理器 - 使用系统密钥环安全存储Cookies"""
    
    def __init__(self):
        self.service = KEYRING_SERVICE
        self.username = KEYRING_USERNAME
    
    def save_cookies(self, cookies_dict):
        """
        将Cookies保存到系统密钥环
        
        Args:
            cookies_dict: Cookie字典 {name: value, ...}
        
        Returns:
            bool: 保存是否成功
        """
        try:
            if not cookies_dict:
                debug_log("Cookies为空，不保存")
                return False
            
            # 将Cookies字典序列化为JSON字符串
            cookies_json = json.dumps(cookies_dict, ensure_ascii=False)
            
            # 保存到密钥环
            keyring.set_password(self.service, self.username, cookies_json)
            
            debug_log(f"已保存 {len(cookies_dict)} 个Cookies到系统密钥环")
            return True
            
        except Exception as e:
            debug_log(f"保存Cookies到密钥环失败: {e}")
            if DEBUG_MODE:
                print(f"[DEBUG] 保存Cookies失败: {e}")
            return False
    
    def load_cookies(self):
        """
        从系统密钥环加载Cookies
        
        Returns:
            dict or None: Cookie字典，如果不存在或加载失败则返回None
        """
        try:
            # 从密钥环读取
            cookies_json = keyring.get_password(self.service, self.username)
            
            if cookies_json is None:
                debug_log("密钥环中没有保存的Cookies")
                return None
            
            # 反序列化JSON字符串
            cookies_dict = json.loads(cookies_json)
            
            debug_log(f"从密钥环加载了 {len(cookies_dict)} 个Cookies")
            return cookies_dict
            
        except json.JSONDecodeError as e:
            debug_log(f"Cookies JSON解析失败: {e}")
            return None
        except Exception as e:
            debug_log(f"从密钥环加载Cookies失败: {e}")
            if DEBUG_MODE:
                print(f"[DEBUG] 加载Cookies失败: {e}")
            return None
    
    def delete_cookies(self):
        """
        从系统密钥环删除Cookies
        
        Returns:
            bool: 删除是否成功
        """
        try:
            keyring.delete_password(self.service, self.username)
            debug_log("已从密钥环删除Cookies")
            return True
        except keyring.errors.PasswordDeleteError:
            # 密码不存在，也算删除成功
            debug_log("密钥环中没有Cookies可删除")
            return True
        except Exception as e:
            debug_log(f"从密钥环删除Cookies失败: {e}")
            if DEBUG_MODE:
                print(f"[DEBUG] 删除Cookies失败: {e}")
            return False
    
    def has_cookies(self):
        """
        检查密钥环中是否有保存的Cookies
        
        Returns:
            bool: 是否有保存的Cookies
        """
        try:
            cookies_json = keyring.get_password(self.service, self.username)
            return cookies_json is not None
        except Exception:
            return False


# 全局凭据管理器实例
credential_manager = CredentialManager()
