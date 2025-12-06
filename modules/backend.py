#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 后端API模块
负责与后端服务器通信（遥测统计、版本检查、广告获取）
"""

import requests
from .config import (
    BACKEND_BASE_URL, VERSION, DEBUG_MODE,
    USE_HTTP_PROXY, HTTP_PROXY
)
from .logger import debug_log


class BackendClient:
    """后端API客户端"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json'
        })
        
        # 设置HTTP代理
        if USE_HTTP_PROXY and HTTP_PROXY:
            self.session.proxies = {
                'http': HTTP_PROXY,
                'https': HTTP_PROXY
            }
    
    def _make_request(self, method, endpoint, params=None, timeout=10):
        """发送请求到后端"""
        url = f"{BACKEND_BASE_URL}{endpoint}"
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=timeout)
            else:
                response = self.session.post(url, data=params, timeout=timeout)
            
            debug_log(f"Backend API: {method} {url}")
            debug_log(f"Backend Response: {response.status_code}")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            debug_log(f"Backend API Error: {e}")
            return None
        except Exception as e:
            debug_log(f"Backend API Exception: {e}")
            return None


class TelemetryClient(BackendClient):
    """遥测统计客户端"""
    
    STAT_TYPE_APP_START = 'app_start'
    STAT_TYPE_TRANSFER = 'cross_dc_transfer'
    STAT_TYPE_RETURN = 'cross_dc_return'
    
    def record_stat(self, stat_type):
        """记录统计数据"""
        try:
            result = self._make_request('GET', '/api/stats/record', {
                'type': stat_type
            })
            
            if result and result.get('success'):
                debug_log(f"统计已记录: {stat_type}")
                return True
            else:
                debug_log(f"统计记录失败: {result}")
                return False
        except Exception as e:
            debug_log(f"统计记录异常: {e}")
            return False
    
    def record_app_start(self):
        """记录应用启动"""
        return self.record_stat(self.STAT_TYPE_APP_START)
    
    def record_transfer(self):
        """记录跨区传送"""
        return self.record_stat(self.STAT_TYPE_TRANSFER)
    
    def record_return(self):
        """记录超域返回"""
        return self.record_stat(self.STAT_TYPE_RETURN)


class VersionClient(BackendClient):
    """版本检查客户端"""
    
    def check_version(self):
        """
        检查版本更新
        返回: {
            'is_latest': bool,           # 是否是最新版本
            'current_version': str,      # 当前版本
            'latest_version': str,       # 最新版本
            'is_force_update': bool,     # 是否强制更新
            'is_supported': bool,        # 当前版本是否还受支持
            'update_url': str,           # 更新地址
            'changelog': str             # 更新日志
        }
        """
        try:
            debug_log(f"开始版本检查，当前版本: {VERSION}")
            result = self._make_request('GET', '/api/version/latest')
            
            if not result or not result.get('success'):
                debug_log(f"版本检查API返回失败: {result}")
                return None
            
            data = result.get('data', {})
            latest_version = data.get('version', VERSION)
            is_force_update = bool(data.get('is_force_update', 0))
            
            debug_log(f"服务端最新版本: {latest_version}, 强制更新: {is_force_update}")
            
            is_latest = self._compare_version(VERSION, latest_version) >= 0
            # 如果不是最新版本且需要强制更新，则不受支持
            is_supported = is_latest or not is_force_update
            
            debug_log(f"版本比较结果: is_latest={is_latest}, is_supported={is_supported}")
            
            return {
                'is_latest': is_latest,
                'current_version': VERSION,
                'latest_version': latest_version,
                'is_force_update': is_force_update,
                'is_supported': is_supported,
                'update_url': data.get('download_url', ''),
                'changelog': data.get('release_notes', ''),
                'release_date': data.get('created_at', '')
            }
        except Exception as e:
            debug_log(f"版本检查异常: {e}")
            return None
    
    def _compare_version(self, v1, v2):
        """
        比较两个版本号
        返回: 1 (v1 > v2), -1 (v1 < v2), 0 (v1 == v2)
        """
        def parse_version(v):
            parts = v.replace('v', '').split('.')
            return [int(p) for p in parts[:3]]  # 只取主要版本号
        
        try:
            p1 = parse_version(v1)
            p2 = parse_version(v2)
            
            for a, b in zip(p1, p2):
                if a > b:
                    return 1
                elif a < b:
                    return -1
            return 0
        except:
            return 0


class AdsClient(BackendClient):
    """广告客户端"""
    
    def get_ads(self, ad_type=None):
        """
        获取广告列表
        ad_type: 'bottom' | 'after_action' | None (获取所有)
        
        后端返回格式:
        [
            {
                "type_code": "bottom",
                "type_name": "底部固定广告",
                "ads": [{...}, {...}]
            },
            ...
        ]
        """
        try:
            params = {}
            if ad_type:
                params['type'] = ad_type
            
            result = self._make_request('GET', '/api/ads', params)
            
            if not result or not result.get('success'):
                debug_log(f"获取广告失败: {result}")
                return []
            
            # 后端返回按类型分组的数组
            data = result.get('data', [])
            
            # 如果指定了类型，只返回该类型的广告
            if ad_type and data:
                for group in data:
                    if group.get('type_code') == ad_type:
                        ads = group.get('ads', [])
                        debug_log(f"获取到 {len(ads)} 条 {ad_type} 广告")
                        return ads
                return []
            
            # 否则返回所有广告（合并所有类型）
            all_ads = []
            for group in data:
                all_ads.extend(group.get('ads', []))
            
            debug_log(f"获取到 {len(all_ads)} 条广告")
            return all_ads
            
        except Exception as e:
            debug_log(f"获取广告异常: {e}")
            return []
    
    def get_after_action_ads(self):
        """获取操作后广告"""
        return self.get_ads(ad_type='after_action')


# 创建单例实例
telemetry = TelemetryClient()
version_client = VersionClient()
ads_client = AdsClient()
