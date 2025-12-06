#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF14DCT 日志模块
负责调试日志、HTTP请求日志和传送历史记录
"""

import os
import json
import atexit
from datetime import datetime
from .config import DEBUG_MODE, LOG_DIR, LOG_TRANSFER_HISTORY_FILE, APP_NAME


# 日志文件句柄（全局变量）
_log_file = None
_log_file_path = None


def ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


def init_log_file():
    """初始化日志文件（仅开发模式）"""
    global _log_file, _log_file_path
    
    if not DEBUG_MODE:
        return
    
    if _log_file is not None:
        return  # 已初始化
    
    try:
        ensure_log_dir()
        
        # 生成日志文件名 (按时间戳)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_file_path = os.path.join(LOG_DIR, f"FF14_DCT_{timestamp}.log")
        
        _log_file = open(_log_file_path, 'w', encoding='utf-8')
        _write_log_raw(f"{APP_NAME} - 日志开始")
        _write_log_raw(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _write_log_raw("=" * 60)
        print(f"[信息] 日志文件: {_log_file_path}")
        
        # 注册退出时关闭日志文件
        atexit.register(close_log_file)
        
    except Exception as e:
        print(f"[警告] 无法创建日志文件: {e}")
        _log_file = None


def _write_log_raw(message):
    """写入日志文件（内部使用）"""
    global _log_file
    if _log_file:
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            _log_file.write(f"[{timestamp}] {message}\n")
            _log_file.flush()
        except:
            pass


def close_log_file():
    """关闭日志文件"""
    global _log_file
    if _log_file:
        try:
            _write_log_raw("=" * 60)
            _write_log_raw(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            _log_file.close()
        except:
            pass
        _log_file = None


def debug_log(message):
    """输出调试日志"""
    if DEBUG_MODE:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[DEBUG {timestamp}] {message}")
        # 同时写入日志文件
        _write_log_raw(f"[DEBUG] {message}")


def log_request(method, url, cookies, response):
    """记录HTTP请求日志"""
    if not DEBUG_MODE:
        return
    
    print(f"\n{'='*60}")
    print(f"[HTTP] {method} {url[:100]}...")
    print(f"[Cookies] {len(cookies)} 个")
    print(f"[Status] {response.status_code}")
    try:
        resp_data = response.json()
        # 简化输出，只显示关键信息
        if 'return_code' in resp_data:
            print(f"[Response] return_code={resp_data.get('return_code')}, return_message={resp_data.get('return_message', '')}")
        else:
            print(f"[Response] {json.dumps(resp_data, ensure_ascii=False)[:200]}...")
    except:
        print(f"[Response] {response.text[:200]}...")
    print('='*60 + '\n')


def log_transfer_history(role_name, source_area, source_server, target_area, target_server, success=True, order_id=None):
    """
    记录传送历史到日志文件
    日志以倒序方式记录（最新的在最前面）
    """
    ensure_log_dir()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "成功" if success else "失败"
    
    # 构建日志条目
    log_entry = (
        f"[{timestamp}] [{status}]\n"
        f"  角色: {role_name}\n"
        f"  源服: {source_area} - {source_server}\n"
        f"  目标: {target_area} - {target_server}\n"
    )
    if order_id:
        log_entry += f"  订单: {order_id}\n"
    log_entry += "-" * 50 + "\n"
    
    # 读取现有日志内容
    existing_content = ""
    if os.path.exists(LOG_TRANSFER_HISTORY_FILE):
        try:
            with open(LOG_TRANSFER_HISTORY_FILE, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        except:
            existing_content = ""
    
    # 将新日志条目添加到开头（倒序）
    new_content = log_entry + existing_content
    
    # 写入文件
    try:
        with open(LOG_TRANSFER_HISTORY_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
        debug_log(f"传送历史已记录到: {LOG_TRANSFER_HISTORY_FILE}")
    except Exception as e:
        print(f"[警告] 记录传送历史失败: {e}")


def get_last_transfer_from_history():
    """从日志文件获取最近一次传送记录"""
    if not os.path.exists(LOG_TRANSFER_HISTORY_FILE):
        return None
    
    try:
        with open(LOG_TRANSFER_HISTORY_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            return None
        
        # 解析第一条记录
        lines = content.strip().split('\n')
        if len(lines) < 4:
            return None
        
        # 查找目标行
        for line in lines:
            if line.strip().startswith("目标:"):
                target_info = line.replace("目标:", "").strip()
                parts = target_info.split(" - ")
                if len(parts) == 2:
                    return {
                        'area': parts[0].strip(),
                        'server': parts[1].strip()
                    }
        
        return None
        
    except Exception as e:
        debug_log(f"读取传送历史失败: {e}")
        return None
