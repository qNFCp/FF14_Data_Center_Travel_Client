#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 网络接口模块
负责所有HTTP请求的封装
"""

import json
import urllib.parse
import requests
from .config import (
    DEBUG_MODE, USER_AGENT, USE_HTTP_PROXY, HTTP_PROXY,
    FF14_APP_ID, FF14_API_PAGE_INIT, FF14_API_GROUP_LIST,
    FF14_API_ROLE_LIST, FF14_API_TRAVEL_ORDER, FF14_API_ORDER_STATUS,
    FF14_API_GROUP_LIST_CROSS_SOURCE, FF14_API_TRAVEL_BACK, FF14_API_MIGRATION_ORDERS
)
from .logger import debug_log, log_request


class FF14APIClient:
    """FF14 API客户端"""
    
    def __init__(self):
        self.session = requests.Session()
        self.cookies = {}
        self.area_list = []
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        
        # 设置HTTP代理
        if USE_HTTP_PROXY and HTTP_PROXY:
            self.session.proxies = {
                'http': HTTP_PROXY,
                'https': HTTP_PROXY
            }
    
    def set_cookies(self, cookies_dict):
        """设置Cookies"""
        self.cookies = cookies_dict
        for name, value in cookies_dict.items():
            self.session.cookies.set(name, value, domain='.sdo.com')
    
    def fetch_area_list(self):
        """获取区服列表"""
        try:
            url = f"{FF14_API_GROUP_LIST}?appId={FF14_APP_ID}"
            
            debug_log(f"请求区服列表: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') != 0:
                print(f"[错误] 获取区服列表失败: {data.get('return_message', '未知错误')}")
                return False
            
            # 解析区服列表
            group_list_str = data.get('data', {}).get('groupList', '[]')
            self.area_list = json.loads(group_list_str)
            
            if not self.area_list:
                print("[错误] 区服列表为空")
                return False
            
            print(f"[成功] 已获取 {len(self.area_list)} 个大区信息")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"[错误] 网络请求失败: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"[错误] 解析响应失败: {e}")
            return False
        except Exception as e:
            print(f"[错误] 获取区服列表时发生错误: {e}")
            return False
    
    def page_init(self, migration_type=4):
        """触发页面初始化接口"""
        try:
            url = f"{FF14_API_PAGE_INIT}?migrationType={migration_type}"
            
            debug_log(f"页面初始化请求: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') == 0:
                print("[信息] 页面初始化成功")
                return True
            else:
                print(f"[警告] 页面初始化返回: {data.get('return_message', '未知')}")
                return True  # 不影响后续流程
                
        except Exception as e:
            print(f"[警告] 页面初始化失败: {e}")
            return True  # 不影响后续流程
    
    def fetch_role_list(self, area_id, group_id):
        """获取角色列表"""
        try:
            url = f"{FF14_API_ROLE_LIST}?appId={FF14_APP_ID}&areaId={area_id}&groupId={group_id}"
            
            debug_log(f"获取角色列表: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') != 0:
                print(f"[错误] 获取角色列表失败: {data.get('return_message', '未知错误')}")
                return []
            
            # 解析角色列表
            role_list = data.get('data', {}).get('roleList', [])
            
            # 如果roleList是字符串，尝试解析
            if isinstance(role_list, str):
                try:
                    role_list = json.loads(role_list)
                except:
                    role_list = []
            
            return role_list
            
        except Exception as e:
            print(f"[错误] 获取角色列表失败: {e}")
            return []
    
    def submit_transfer(self, source_area, source_server, target_area, target_server, role):
        """提交跨区传送请求"""
        try:
            debug_log(f"源大区: {source_area}")
            debug_log(f"源服务器: {source_server}")
            debug_log(f"目标大区: {target_area}")
            debug_log(f"目标服务器: {target_server}")
            debug_log(f"角色: {role}")
            
            # 构建roleList参数
            role_list = [{
                "roleId": str(role.get('roleId', role.get('id', ''))),
                "roleName": role.get('roleName', role.get('name', '')),
                "key": 0
            }]
            role_list_json = json.dumps(role_list, ensure_ascii=False)
            
            # 构建请求URL
            params = [
                f"appId={FF14_APP_ID}",
                f"areaId={source_area['areaId']}",
                f"areaName={urllib.parse.quote(str(source_area['areaName']))}",
                f"groupId={source_server['groupId']}",
                f"groupCode={source_server['groupCode']}",
                f"groupName={urllib.parse.quote(str(source_server['groupName']))}",
                f"productId=1",
                f"productNum=1",
                f"migrationType=4",
                f"targetArea={target_area['areaId']}",
                f"targetAreaName={urllib.parse.quote(str(target_area['areaName']))}",
                f"targetGroupId={target_server['groupId']}",
                f"targetGroupCode={target_server['groupCode']}",
                f"targetGroupName={urllib.parse.quote(str(target_server['groupName']))}",
                f"roleList={urllib.parse.quote(role_list_json)}",
                f"isMigrationTimes=0"
            ]
            
            url = f"{FF14_API_TRAVEL_ORDER}?{'&'.join(params)}"
            
            debug_log(f"提交跨区传送请求URL: {url}")
            response = self.session.get(url, timeout=15)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') == 0:
                result_data = data.get('data', {})
                order_id = result_data.get('orderId', '')
                if order_id:
                    print(f"[成功] 跨区传送订单已提交，订单号: {order_id}")
                    return order_id
                else:
                    result_code = result_data.get('resultCode', -1)
                    result_msg = result_data.get('resultMsg', '未知')
                    print(f"[信息] 提交结果: {result_msg} (code: {result_code})")
                    return result_data
            else:
                print(f"[错误] 提交失败: {data.get('return_message', '未知错误')}")
                return None
                
        except Exception as e:
            debug_log(f"提交跨区传送请求异常: {e}")
            print(f"[错误] 提交跨区传送请求失败: {e}")
            return None
    
    def check_order_status(self, order_id):
        """查询订单状态"""
        try:
            url = f"{FF14_API_ORDER_STATUS}?orderId={order_id}"
            
            debug_log(f"查询订单状态: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') == 0:
                result_data = data.get('data', {})
                migration_status = result_data.get('migrationStatus', -1)
                order_status = result_data.get('orderStatus', -1)
                
                status_desc = {
                    -1: "预检失败",
                    0: "等待处理",
                    1: "处理中",
                    4: "传送中",
                    5: "传送成功"
                }
                
                desc = status_desc.get(migration_status, f"未知状态({migration_status})")
                print(f"[状态] 订单状态: {desc}")
                if DEBUG_MODE:
                    print(f"[DEBUG] [状态] migrationStatus={migration_status}, orderStatus={order_status}")
                
                return migration_status
            else:
                print(f"[错误] 查询订单状态失败: {data.get('return_message', '未知')}")
                return -1
                
        except Exception as e:
            print(f"[错误] 查询订单状态失败: {e}")
            return -1
    
    def get_areas(self):
        """获取大区列表"""
        return [{'areaId': a['areaId'], 'areaName': a['areaName'], 'groups': a['groups']} 
                for a in self.area_list]
    
    def get_servers(self, area):
        """获取服务器列表"""
        return area.get('groups', [])
    
    # ==================== 超域返回相关API ====================
    
    def fetch_return_area_list(self):
        """
        获取超域返回可用的区服列表
        使用 queryGroupListCrossSource 接口
        """
        try:
            url = f"{FF14_API_GROUP_LIST_CROSS_SOURCE}?appId={FF14_APP_ID}"
            
            debug_log(f"请求超域返回区服列表: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') != 0:
                print(f"[错误] 获取超域返回区服列表失败: {data.get('return_message', '未知错误')}")
                return None
            
            # 解析区服列表
            group_list_str = data.get('data', {}).get('groupList', '[]')
            area_list = json.loads(group_list_str)
            
            if not area_list:
                print("[错误] 超域返回区服列表为空")
                return None
            
            print(f"[成功] 已获取 {len(area_list)} 个可返回的大区信息")
            return area_list
            
        except requests.exceptions.RequestException as e:
            print(f"[错误] 网络请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"[错误] 解析响应失败: {e}")
            return None
        except Exception as e:
            print(f"[错误] 获取超域返回区服列表时发生错误: {e}")
            return None
    
    def fetch_migration_orders(self, page_index=1, page_num=10):
        """
        获取迁移订单列表
        用于查找当前旅行中的订单
        """
        try:
            url = f"{FF14_API_MIGRATION_ORDERS}?appId={FF14_APP_ID}&pageIndex={page_index}&pageNum={page_num}"
            
            debug_log(f"请求迁移订单列表: {url}")
            response = self.session.get(url, timeout=10)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            
            if data.get('return_code') != 0:
                print(f"[错误] 获取订单列表失败: {data.get('return_message', '未知错误')}")
                return None
            
            result_data = data.get('data', {})
            
            # orderlist 是一个 JSON 字符串，需要解析
            orderlist_str = result_data.get('orderlist', '[]')
            if isinstance(orderlist_str, str):
                try:
                    order_list = json.loads(orderlist_str)
                    debug_log(f"解析到 {len(order_list)} 个订单")
                except json.JSONDecodeError as e:
                    debug_log(f"解析orderlist失败: {e}")
                    order_list = []
            else:
                order_list = orderlist_str if orderlist_str else []
            
            # 返回包含解析后订单列表的数据
            return {
                'orderlist': order_list,
                'totalPageNum': result_data.get('totalPageNum', 0),
                'totalCount': result_data.get('totalCount', 0)
            }
            
        except Exception as e:
            print(f"[错误] 获取订单列表失败: {e}")
            return None
    
    def submit_travel_back(self, travel_order_id, group_id, group_code, group_name):
        """
        提交超域返回请求
        
        :param travel_order_id: 旅行订单编号
        :param group_id: 当前服务器ID
        :param group_code: 当前服务器代码
        :param group_name: 当前服务器名称
        :return: 返回结果字典或None
        """
        try:
            # URL编码服务器名称
            encoded_group_name = urllib.parse.quote(str(group_name))
            
            url = f"{FF14_API_TRAVEL_BACK}?travelOrderId={travel_order_id}&groupId={group_id}&groupCode={group_code}&groupName={encoded_group_name}"
            
            debug_log(f"提交超域返回请求: {url}")
            response = self.session.get(url, timeout=15)
            log_request("GET", url, dict(self.session.cookies), response)
            
            data = response.json()
            debug_log(f"超域返回响应: {data}")
            
            if data.get('return_code') == 0:
                result_data = data.get('data', {})
                result_code = result_data.get('resultCode', -1)
                result_msg = result_data.get('resultMsg', '未知')
                order_id = result_data.get('orderId', '')
                
                if result_code == 0:
                    print(f"[成功] 超域返回请求已提交")
                    if order_id:
                        print(f"[信息] 返回订单号: {order_id}")
                    return {
                        'success': True,
                        'resultCode': result_code,
                        'resultMsg': result_msg,
                        'orderId': order_id
                    }
                else:
                    print(f"[失败] 超域返回失败: {result_msg} (code: {result_code})")
                    return {
                        'success': False,
                        'resultCode': result_code,
                        'resultMsg': result_msg
                    }
            else:
                print(f"[错误] 提交失败: {data.get('return_message', '未知错误')}")
                return None
                
        except Exception as e:
            debug_log(f"提交超域返回请求异常: {e}")
            print(f"[错误] 提交超域返回请求失败: {e}")
            return None
