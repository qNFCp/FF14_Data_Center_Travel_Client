#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FF14 DCT 图形界面启动器

from __future__ import annotations

import queue
import threading
import time
import traceback
import webbrowser
from functools import partial
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from modules import (
    ConfigManager,
    DEBUG_MODE,
    LoginService,
    ReturnOrchestrator,
    RuntimeService,
    TransferOrchestrator,
    VERSION,
    debug_log,
    init_log_file,
)
from modules.config import USE_HTTP_PROXY, HTTP_PROXY


class UILogger:
    def __init__(self, text: tk.Text):
        """初始化日志队列与日志输出控件。"""
        self.text = text
        self.q: queue.Queue[str] = queue.Queue()

    def write(self, msg: str):
        """将日志文本写入队列，等待主线程刷新。"""
        if msg:
            self.q.put(msg)

    def flush_to_ui(self):
        """将日志队列内容批量刷新到UI文本框。"""
        try:
            while True:
                msg = self.q.get_nowait()
                self.text.configure(state="normal")
                self.text.insert("end", msg)
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            pass


class FF14DCTGUI(tk.Tk):
    def __init__(self):
        """初始化主窗口、服务实例与后台启动流程。"""
        super().__init__()
        title_suffix = " [开发模式]" if DEBUG_MODE else ""
        self.title(f"FF14 超域传送/返回 (GUI){title_suffix}")
        self.geometry("920x720")
        self.minsize(860, 620)

        self.config_mgr = ConfigManager()
        self.api = None
        self._worker_lock = threading.Lock()
        self._blocked = False
        self._logged_in = False
        self._last_transfer_prefill_checked = False

        self._build_ui()

        self.login_service = LoginService(self.config_mgr, logger=self._log)
        self.runtime_service = RuntimeService(logger=self._log)
        self.transfer_service = None
        self.return_service = None

        self._areas_cache = None  # 缓存所有原始大区列表
        self.after(100, self._tick)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._run_bg(self._startup)

    # ---------------- UI ----------------
    def _build_ui(self):
        """构建GUI布局与控件。"""
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="浏览器:").pack(side="left")
        self.browser_var = tk.StringVar(value=self.config_mgr.get_browser())
        self.browser_combo = ttk.Combobox(
            top,
            textvariable=self.browser_var,
            values=["Edge", "Chrome", "Firefox"],
            width=12,
            state="readonly",
        )
        self.browser_combo.pack(side="left", padx=(6, 16))

        self.status_var = tk.StringVar(value="状态：未登录")
        ttk.Label(top, textvariable=self.status_var).pack(side="left")

        ttk.Label(top, text="").pack(side="left", expand=True)

        self.btn_check_update = ttk.Button(top, text="检查更新", command=self.on_check_update)
        self.btn_check_update.pack(side="right", padx=4)
        
        # 版本号标签，支持红色更新提示
        self.version_label = tk.Label(top, text=f"v{VERSION}", foreground="black", font=("TkDefaultFont", 9))
        self.version_label.pack(side="right", padx=(4, 8))

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_login = ttk.Button(btns, text="1) 打开登录页面", command=self.on_open_login)
        self.btn_login.pack(side="left")

        self.btn_confirm_login = ttk.Button(btns, text="2) 我已登录，继续", command=self.on_confirm_login)
        self.btn_confirm_login.pack(side="left", padx=8)

        self.btn_transfer = ttk.Button(btns, text="跨区传送", command=self.on_transfer)
        self.btn_transfer.pack(side="left", padx=8)

        self.btn_return = ttk.Button(btns, text="超域返回", command=self.on_return)
        self.btn_return.pack(side="left", padx=8)

        self.btn_clear = ttk.Button(btns, text="清除缓存登录", command=self.on_clear_cache)
        self.btn_clear.pack(side="right")

        sep = ttk.Separator(self)
        sep.pack(fill="x", padx=12, pady=8)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left = ttk.LabelFrame(body, text="跨区传送（向导）")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        grid = ttk.Frame(left)
        grid.pack(fill="both", expand=True, padx=10, pady=10)

        self.src_area_var = tk.StringVar()
        self.src_server_var = tk.StringVar()
        self.role_var = tk.StringVar()
        self.dst_area_var = tk.StringVar()
        self.dst_server_var = tk.StringVar()

        def add_row(r: int, label: str, widget: ttk.Widget):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=6)
            widget.grid(row=r, column=1, sticky="ew", pady=6)

        grid.columnconfigure(1, weight=1)

        self.src_area_cb = ttk.Combobox(grid, textvariable=self.src_area_var, state="readonly")
        self.src_server_cb = ttk.Combobox(grid, textvariable=self.src_server_var, state="readonly")
        self.role_cb = ttk.Combobox(grid, textvariable=self.role_var, state="readonly")
        self.dst_area_cb = ttk.Combobox(grid, textvariable=self.dst_area_var, state="readonly")
        self.dst_server_cb = ttk.Combobox(grid, textvariable=self.dst_server_var, state="readonly")

        add_row(0, "源大区", self.src_area_cb)
        add_row(1, "源服务器", self.src_server_cb)
        add_row(2, "角色", self.role_cb)
        ttk.Separator(grid).grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        add_row(4, "目标大区", self.dst_area_cb)
        add_row(5, "目标服务器", self.dst_server_cb)

        self.btn_refresh = ttk.Button(grid, text="刷新区服/角色列表", command=self.on_refresh_lists)
        self.btn_refresh.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        self.btn_do_transfer = ttk.Button(grid, text="执行跨区传送", command=self.on_do_transfer)
        self.btn_do_transfer.grid(row=7, column=0, columnspan=2, sticky="ew", pady=8)

        self.src_area_cb.bind("<<ComboboxSelected>>", self._on_src_area_changed)
        self.src_server_cb.bind("<<ComboboxSelected>>", self._on_src_server_changed)
        self.dst_area_cb.bind("<<ComboboxSelected>>", self._on_dst_area_changed)

        right = ttk.LabelFrame(body, text="运行日志")
        right.pack(side="right", fill="both", expand=True)

        self.log_text = tk.Text(right, height=20, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.logger = UILogger(self.log_text)

        ann = ttk.LabelFrame(self, text="公告")
        ann.pack(fill="x", padx=12, pady=(0, 12))

        self.ann_text = tk.Text(ann, height=5, wrap="word", state="disabled")
        self.ann_text.pack(fill="both", expand=True, padx=8, pady=8)

        self._set_logged_in(False)

    def _on_src_area_changed(self, _event=None):
        """源大区变化时异步刷新源服务器列表。"""
        self._run_bg(self._load_src_servers)

    def _on_src_server_changed(self, _event=None):
        """源服务器变化时异步刷新角色列表。"""
        self._run_bg(self._load_roles)

    def _on_dst_area_changed(self, _event=None):
        """目标大区变化时异步刷新目标服务器列表。"""
        self._run_bg(self._load_dst_servers)

    # ---------------- threading helpers ----------------
    def _tick(self):
        """定时刷新日志显示心跳。"""
        self.logger.flush_to_ui()
        self.after(120, self._tick)

    def _log(self, msg: str):
        """写入带时间戳的GUI日志。"""
        ts = time.strftime("%H:%M:%S")
        self.logger.write(f"[{ts}] {msg}\n")

    def _debug(self, msg: str):
        """仅在开发模式输出调试日志（GUI与文件）。"""
        if not DEBUG_MODE:
            return
        self._log(f"[DEBUG] {msg}")
        debug_log(msg)

    def _call_in_ui_thread(self, func, *args, **kwargs):
        """确保目标函数在UI主线程执行，并返回结果。"""
        fn = partial(func, *args, **kwargs) if args or kwargs else func
        if threading.current_thread() is threading.main_thread():
            return fn()

        done = threading.Event()
        result = {}

        def runner():
            try:
                result["value"] = fn()
            except Exception as e:
                result["error"] = e
            finally:
                done.set()

        self.after(0, runner)
        done.wait()

        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _ui_show_error(self, title: str, msg: str):
        """在主线程弹出错误对话框。"""
        self._call_in_ui_thread(messagebox.showerror, title, msg)

    def _ui_show_info(self, title: str, msg: str):
        """在主线程弹出信息对话框。"""
        self._call_in_ui_thread(messagebox.showinfo, title, msg)

    def _ui_ask_yes_no(self, title: str, msg: str) -> bool:
        """在主线程弹出确认对话框并返回布尔结果。"""
        return bool(self._call_in_ui_thread(messagebox.askyesno, title, msg))

    def _run_bg(self, fn, *args, **kwargs):
        """串行启动后台任务，避免并发执行冲突。"""
        def runner():
            if not self._worker_lock.acquire(blocking=False):
                self._log("已有任务在运行，请稍候…")
                return
            try:
                fn(*args, **kwargs)
            except Exception as e:
                self._log(f"异常: {e}")
                if DEBUG_MODE:
                    stack = traceback.format_exc()
                    self._log(stack)
                    debug_log(stack)
                self._ui_show_error("发生异常", str(e))
            finally:
                self._worker_lock.release()

        t = threading.Thread(target=runner, daemon=True)
        t.start()

    # ---------------- app lifecycle ----------------
    def _startup(self):
        """执行启动初始化：日志、代理、版本检查、公告与缓存登录。"""
        init_log_file()
        self._log("启动初始化中…")
        if DEBUG_MODE:
            self._log("[开发模式] 已启用详细调试输出。")
            self._debug(f"当前GUI版本: v{VERSION}")

        # 显示系统代理信息
        if USE_HTTP_PROXY and HTTP_PROXY:
            self._log(f"检测到系统HTTP代理: {HTTP_PROXY}")
            self._debug(f"代理已应用: {HTTP_PROXY}")
        else:
            self._log("未检测到系统HTTP代理")
            self._debug("代理模式: 直连")

        self.runtime_service.record_app_start()

        version_result = self.runtime_service.check_version()
        version_info = version_result.get("version_info")
        latest_version = None

        if version_info:
            self._debug("版本检查结果:")
            self._debug(f"  当前版本: {version_info.get('current_version')}")
            self._debug(f"  最新版本: {version_info.get('latest_version')}")
            self._debug(f"  是否最新: {version_info.get('is_latest')}")
            self._debug(f"  强制更新: {version_info.get('is_force_update')}")
            self._debug(f"  版本受支持: {version_info.get('is_supported')}")
            self._debug(f"  更新地址: {version_info.get('update_url', '(无)')}")
        else:
            self._debug("版本检查失败，按兼容模式继续。")

        if not version_result.get("can_continue", True):
            latest_version = "未知"
            update_url = ""
            if version_info:
                latest_version = version_info.get("latest_version", "未知")
                update_url = version_info.get("update_url", "")
            self._mark_version_update_label(latest_version)
            self._set_blocked(True)
            self._log(f"版本检查阻断：检测到强制更新，最新版本 v{latest_version}。")
            action = self._call_in_ui_thread(self._show_force_update_dialog, latest_version, update_url)
            if action == "close":
                self._call_in_ui_thread(self.destroy)
            return

        if version_info and not version_result.get("is_latest", True):
            latest_version = version_info.get("latest_version", "未知")
            self._mark_version_update_label(latest_version)
            self._log("版本检查：有新版本可用。")
        else:
            self._log("版本检查：当前为可用版本。")

        self._refresh_announcements()
        self._try_cached_login()

    def on_close(self):
        """关闭窗口前清理浏览器资源。"""
        try:
            self.login_service.close_browser()
        finally:
            self.destroy()

    def _set_blocked(self, blocked: bool):
        """设置版本受限状态并同步关键按钮可用性。"""
        self._blocked = blocked
        state = "disabled" if blocked else "normal"
        for button in (self.btn_login, self.btn_confirm_login, self.btn_clear):
            self._call_in_ui_thread(button.configure, state=state)
        if blocked:
            self._set_logged_in(False)

    def _set_logged_in(self, ok: bool):
        """根据登录状态刷新主操作按钮状态。"""
        self._logged_in = ok

        if self._blocked:
            self.status_var.set("状态：版本受限")
            for btn in [self.btn_transfer, self.btn_return, self.btn_refresh, self.btn_do_transfer]:
                btn.configure(state="disabled")
            return

        if ok:
            self.status_var.set("状态：已登录")
            self.btn_transfer.configure(state="normal")
            self.btn_return.configure(state="normal")
            self.btn_refresh.configure(state="normal")
            self.btn_do_transfer.configure(state="normal")
        else:
            self.status_var.set("状态：未登录")
            self.btn_transfer.configure(state="disabled")
            self.btn_return.configure(state="disabled")
            self.btn_refresh.configure(state="disabled")
            self.btn_do_transfer.configure(state="disabled")

    def _set_api_client(self, api_client):
        """设置API客户端并重建对应业务编排服务。"""
        self.api = api_client
        self._last_transfer_prefill_checked = False
        if self.api is None:
            self.transfer_service = None
            self.return_service = None
            self._set_logged_in(False)
            return

        self.transfer_service = TransferOrchestrator(self.api, self.config_mgr)
        self.return_service = ReturnOrchestrator(self.api, self.config_mgr)
        self._set_logged_in(True)

    # ---------------- login ----------------
    def _try_cached_login(self):
        """尝试使用本地缓存凭据完成自动登录。"""
        api = self.login_service.try_cached_login()
        if not api:
            self._set_api_client(None)
            self._log("请先点击“打开登录页面”。")
            return

        self._set_api_client(api)
        self._log("缓存登录成功。")
        self._populate_areas()

    def on_open_login(self):
        """响应“打开登录页面”按钮事件。"""
        if self._blocked:
            return
        self._run_bg(self._open_login)

    def _open_login(self):
        """初始化指定浏览器并打开登录页面。"""
        choice = self._call_in_ui_thread(self.browser_var.get)
        self._log(f"初始化浏览器：{choice}")
        self.login_service.open_login_page(choice)

    def on_confirm_login(self):
        """响应“我已登录，继续”按钮事件。"""
        if self._blocked:
            return
        self._run_bg(self._confirm_login)

    def _confirm_login(self):
        """确认浏览器登录状态并写入本地凭据。"""
        self._log("确认登录并验证Cookie…")
        api = self.login_service.confirm_login()
        self._set_api_client(api)
        self._log("登录成功。")
        self._populate_areas()

    def on_clear_cache(self):
        """响应“清除缓存登录”按钮事件。"""
        if self._blocked:
            return
        if not self._ui_ask_yes_no("确认", "确认清除缓存登录并退出当前会话吗？"):
            return
        self.login_service.clear_cached_login()
        self._set_api_client(None)

    # ---------------- area/server/role ----------------
    def on_refresh_lists(self):
        """手动刷新大区、服务器和角色列表。"""
        if not self._logged_in:
            return
        self._run_bg(self._populate_areas)

    def _get_selected(self, var: tk.StringVar) -> str:
        """读取指定 StringVar 的当前值。"""
        return self._call_in_ui_thread(var.get)

    def _set_combobox_values(self, cb: ttk.Combobox, values):
        """更新下拉框可选项列表。"""
        self._call_in_ui_thread(cb.configure, values=values)

    def _set_var(self, var: tk.StringVar, value: str):
        """设置指定 StringVar 的值。"""
        self._call_in_ui_thread(var.set, value)

    def _sync_combobox_default(self, cb: ttk.Combobox, var: tk.StringVar, values):
        """同步下拉框选项并修正默认选中值。"""
        self._set_combobox_values(cb, values)
        if values:
            current = self._get_selected(var)
            if current not in values:
                self._set_var(var, values[0])

    def _get_combobox_values(self, cb: ttk.Combobox):
        """读取下拉框可选项列表。"""
        return list(self._call_in_ui_thread(lambda: cb.cget("values")))

    def _read_last_transfer_record(self):
        """读取并标准化上次传送记录。"""
        raw = self.config_mgr.get_last_transfer()
        if not isinstance(raw, dict):
            self._log("未读取到上次传送记录。")
            return None

        target_area = str(raw.get("target_area") or raw.get("area") or "").strip()
        target_server = str(raw.get("target_server") or raw.get("server") or "").strip()
        source_area = str(raw.get("source_area") or "").strip()
        source_server = str(raw.get("source_server") or "").strip()
        role_name = str(raw.get("role_name") or "").strip()

        if not target_area or not target_server:
            self._log("上次传送记录不完整，跳过自动应用。")
            return None

        src_desc = f"{source_area}-{source_server}" if source_area and source_server else "(未记录)"
        role_desc = role_name if role_name else "(未记录)"
        self._log(f"读取上次传送记录：角色={role_desc} | 源={src_desc} | 目标={target_area}-{target_server}")
        return {
            "source_area": source_area,
            "source_server": source_server,
            "role_name": role_name,
            "target_area": target_area,
            "target_server": target_server,
        }

    def _is_role_pending_return(self, role_name: str) -> bool:
        """检查角色是否处于已进行超域传送待返回状态。"""
        if not self.return_service:
            return False

        try:
            orders = self.return_service.fetch_active_orders()
        except Exception as e:
            self._log(f"检查待返回状态失败，按可继续处理: {e}")
            return False

        for order in orders:
            order_role = order.get("roleName") or (order.get("migrationDetailList") or [{}])[0].get("roleName", "")
            if order_role == role_name:
                return True
        return False

    def _try_apply_last_transfer_selection(self):
        """在满足条件时自动回填上次传送选项。"""
        record = self._read_last_transfer_record()
        if not record:
            return

        source_area = record.get("source_area", "")
        source_server = record.get("source_server", "")
        role_name = record.get("role_name", "")
        target_area = record.get("target_area", "")
        target_server = record.get("target_server", "")

        if not role_name:
            self._log("上次记录缺少角色信息，跳过自动应用。")
            return

        if source_area:
            src_areas = self._get_combobox_values(self.src_area_cb)
            if source_area not in src_areas:
                self._log(f"上次源大区 [{source_area}] 不在当前列表，跳过自动应用。")
                return
            self._set_var(self.src_area_var, source_area)
            self._load_src_servers()

        if source_server:
            src_servers = self._get_combobox_values(self.src_server_cb)
            if source_server not in src_servers:
                self._log(f"上次源服务器 [{source_server}] 不在当前列表，跳过自动应用。")
                return
            self._set_var(self.src_server_var, source_server)
            self._load_roles()

        role_names = self._get_combobox_values(self.role_cb)
        if role_name not in role_names:
            self._log(f"上次角色 [{role_name}] 当前查询不到，跳过自动应用。")
            return

        self._log(f"检查角色 [{role_name}] 是否处于待返回状态…")
        if self._is_role_pending_return(role_name):
            self._log(f"角色 [{role_name}] 已处于超域传送待返回状态，跳过自动应用。")
            return

        dst_areas = self._get_combobox_values(self.dst_area_cb)
        if target_area not in dst_areas:
            self._log(f"上次目标大区 [{target_area}] 不在当前列表，跳过自动应用。")
            return

        self._set_var(self.role_var, role_name)
        self._set_var(self.dst_area_var, target_area)
        self._load_dst_servers()

        dst_servers = self._get_combobox_values(self.dst_server_cb)
        if target_server not in dst_servers:
            self._log(f"上次目标服务器 [{target_server}] 不在当前列表，跳过自动应用。")
            return

        self._set_var(self.dst_server_var, target_server)
        current_src_area = self._get_selected(self.src_area_var)
        current_src_server = self._get_selected(self.src_server_var)
        self._log(
            f"已自动应用上次选项：{current_src_area}-{current_src_server} / {role_name} -> {target_area}-{target_server}"
        )

    def _populate_areas(self):
        """加载并筛选有角色的大区，随后刷新相关联下拉框。"""
        if not self.api:
            return

        areas = self.api.get_areas()
        if not areas:
            raise RuntimeError("未能获取大区列表")

        # 缓存原始大区列表
        self._areas_cache = areas

        # 预加载大区列表，过滤出有角色的大区
        self._log("预加载大区角色信息…")
        areas_with_roles = []
        for area in areas:
            try:
                servers = self.api.get_servers(area)
                has_role = False
                for server in servers:
                    try:
                        roles = self.api.fetch_role_list(area.get("areaId"), server.get("groupId"))
                        if roles:
                            has_role = True
                            break
                    except Exception:
                        pass
                if has_role:
                    areas_with_roles.append(area)
            except Exception as e:
                self._log(f"检查大区 {area.get('areaName', '')} 角色时出错: {e}")

        if not areas_with_roles:
            self._log("未找到有角色的大区")
            return

        area_names = [a.get("areaName", "") for a in areas_with_roles]
        self._set_combobox_values(self.src_area_cb, area_names)
        self._log(f"找到 {len(areas_with_roles)} 个有角色的大区")

        current_src = self._get_selected(self.src_area_var)
        if not current_src and area_names:
            self._set_var(self.src_area_var, area_names[0])

        self._refresh_target_areas()
        self._load_src_servers()
        self._load_dst_servers()

        if not self._last_transfer_prefill_checked:
            self._last_transfer_prefill_checked = True
            self._try_apply_last_transfer_selection()

    def _find_area_by_name(self, name: str):
        """按大区名称查找大区对象。"""
        if not self.api:
            return None
        # 从缓存的大区列表中查找，如果没有缓存则从API获取
        areas = self._areas_cache if self._areas_cache else self.api.get_areas()
        for area in areas:
            if area.get("areaName") == name:
                return area
        return None

    def _refresh_target_areas(self):
        """刷新目标大区列表（排除当前源大区）。"""
        if not self.api:
            return
        source_name = self._get_selected(self.src_area_var)
        # 从原始大区列表中选择目标大区（排除源大区）
        areas = self._areas_cache if self._areas_cache else self.api.get_areas()
        target_names = [a.get("areaName", "") for a in areas if a.get("areaName") != source_name]
        self._set_combobox_values(self.dst_area_cb, target_names)

        current_dst = self._get_selected(self.dst_area_var)
        if target_names and current_dst not in target_names:
            self._set_var(self.dst_area_var, target_names[0])

    def _load_src_servers(self):
        """加载并筛选有角色的源服务器列表。"""
        if not self.api:
            return
        self._refresh_target_areas()

        area = self._find_area_by_name(self._get_selected(self.src_area_var))
        if not area:
            return
        servers = self.api.get_servers(area)
        
        # 过滤出有角色的服务器
        servers_with_roles = []
        for server in servers:
            try:
                roles = self.api.fetch_role_list(area.get("areaId"), server.get("groupId"))
                if roles:
                    servers_with_roles.append(server)
            except Exception as e:
                self._log(f"检查服务器 {server.get('groupName', '')} 角色时出错: {e}")
        
        if not servers_with_roles:
            self._log("该大区没有找到有角色的服务器")
            self._set_combobox_values(self.src_server_cb, [])
            self._set_combobox_values(self.role_cb, [])
            return
        
        names = [s.get("groupName", "") for s in servers_with_roles]
        self._sync_combobox_default(self.src_server_cb, self.src_server_var, names)

        self._load_roles()

    def _load_dst_servers(self):
        """加载目标大区对应的目标服务器列表。"""
        if not self.api:
            return

        area = self._find_area_by_name(self._get_selected(self.dst_area_var))
        if not area:
            return

        servers = self.api.get_servers(area)
        names = [s.get("groupName", "") for s in servers]
        self._sync_combobox_default(self.dst_server_cb, self.dst_server_var, names)

    def _load_roles(self):
        """加载当前源大区/源服务器下的角色列表。"""
        if not self.api:
            return

        area = self._find_area_by_name(self._get_selected(self.src_area_var))
        if not area:
            return

        servers = self.api.get_servers(area)
        selected_server = self._get_selected(self.src_server_var)
        server = next((s for s in servers if s.get("groupName") == selected_server), None)
        if not server:
            return

        self._log("获取角色列表…")
        roles = self.api.fetch_role_list(area.get("areaId"), server.get("groupId"))
        names = [r.get("roleName", r.get("name", "")) for r in roles]
        self._log("获取角色列表完毕。")
        self._sync_combobox_default(self.role_cb, self.role_var, names)

    # ---------------- transfer ----------------
    def on_transfer(self):
        """显示跨区传送向导使用说明。"""
        self._ui_show_info(
            "提示",
            "请在左侧‘跨区传送（向导）’中选择源大区/服务器/角色与目标大区/服务器，然后点击‘执行跨区传送’。\n\n"
            "（如果列表为空，请先点击‘刷新区服/角色列表’）",
        )

    def on_do_transfer(self):
        """响应“执行跨区传送”按钮事件。"""
        if not self.transfer_service:
            self._ui_show_error("未登录", "请先完成登录。")
            return

        ok = self._ui_ask_yes_no("确认", "确认提交跨区传送请求吗？\n\n失败将按 61-65 秒随机间隔自动重试。")
        if not ok:
            return
        self._run_bg(self._do_transfer)

    def _do_transfer(self):
        """执行跨区传送流程并处理结果反馈。"""
        if not self.transfer_service:
            return

        source_area = self._get_selected(self.src_area_var)
        source_server = self._get_selected(self.src_server_var)
        role_name = self._get_selected(self.role_var)
        target_area = self._get_selected(self.dst_area_var)
        target_server = self._get_selected(self.dst_server_var)

        self._debug(
            f"传送参数: 源={source_area}/{source_server}, 角色={role_name}, 目标={target_area}/{target_server}"
        )

        result = self.transfer_service.execute_transfer(
            source_area_name=source_area,
            source_server_name=source_server,
            role_name=role_name,
            target_area_name=target_area,
            target_server_name=target_server,
            log_cb=self._log,
        )

        if result.get("success"):
            order_id = result.get("order_id")
            msg = "跨区传送成功。"
            if order_id:
                msg += f"\n\n订单号：{order_id}"
            self._log(f"跨区传送成功。{f'订单号：{order_id}' if order_id else ''}")
            self._ui_show_info("成功", msg)
            self._refresh_announcements()
            return

        self._ui_show_error("失败", result.get("message", "跨区传送失败"))

    # ---------------- return ----------------
    def on_return(self):
        """响应“超域返回”按钮事件。"""
        if not self.return_service:
            self._ui_show_error("未登录", "请先完成登录。")
            return
        self._run_bg(self._do_return)

    def _choose_order(self, orders):
        """在多个可返回订单中让用户选择目标订单。"""
        if len(orders) == 1:
            return orders[0]

        lines = ["检测到多个旅行中的订单，请输入序号：", ""]
        for idx, order in enumerate(orders, 1):
            role = order.get("roleName", "未知")
            src = f"{order.get('areaName', '未知')}-{order.get('groupName', '未知')}"
            dst = f"{order.get('targetAreaName', '未知')}-{order.get('targetGroupName', '未知')}"
            status = order.get("migrationStatusDesc", "未知")
            lines.append(f"[{idx}] 角色:{role} | 原区服:{src} | 目的地:{dst} | 状态:{status}")

        prompt = "\n".join(lines)

        choice = self._call_in_ui_thread(
            simpledialog.askinteger,
            "选择订单",
            prompt,
            minvalue=1,
            maxvalue=len(orders),
        )
        if not choice:
            return None
        return orders[choice - 1]

    def _choose_server_with_fallback(self, servers, default_server, role_name: str):
        """确认当前服务器，必要时允许用户手动兜底选择。"""
        default_name = default_server.get("groupName", "未知")
        use_default = self._ui_ask_yes_no(
            "确认当前服务器",
            f"角色：{role_name}\n"
            f"订单默认服务器为：{default_name}\n\n"
            f"若你在当前大区内又跨服，请点“否”自行选择。\n是否使用默认服务器？",
        )
        if use_default:
            return default_server

        lines = ["请选择你当前实际所在服务器：", ""]
        for idx, server in enumerate(servers, 1):
            mark = " (默认)" if server.get("groupName") == default_name else ""
            lines.append(f"[{idx}] {server.get('groupName', '未知')}{mark}")

        choice = self._call_in_ui_thread(
            simpledialog.askinteger,
            "选择服务器",
            "\n".join(lines),
            minvalue=1,
            maxvalue=len(servers),
        )
        if not choice:
            return None
        return servers[choice - 1]

    def _do_return(self):
        """执行超域返回流程并处理结果反馈。"""
        if not self.return_service:
            return

        self._log("拉取可返回订单…")
        orders = self.return_service.fetch_active_orders()
        if not orders:
            self._ui_show_info("提示", "未找到可执行超域返回的订单。")
            return

        order = self._choose_order(orders)
        if not order:
            self._log("用户取消订单选择。")
            return

        role_name = order.get("roleName") or (order.get("migrationDetailList") or [{}])[0].get("roleName", "未知")

        current_area, servers, default_server = self.return_service.resolve_current_server_options(order)
        selected_server = self._choose_server_with_fallback(servers, default_server, role_name)
        if not selected_server:
            self._log("用户取消服务器选择。")
            return

        order_id = order.get("orderId", "")
        self._debug(
            f"返回参数: 订单={order_id}, 角色={role_name}, 当前={current_area.get('areaName', '未知')}-{selected_server.get('groupName', '未知')}"
        )
        confirm_text = (
            f"确认执行超域返回？\n\n"
            f"订单号：{order_id}\n"
            f"角色：{role_name}\n"
            f"当前：{current_area.get('areaName', '未知')} - {selected_server.get('groupName', '未知')}\n"
            f"返回：{order.get('areaName', '未知')} - {order.get('groupName', '未知')}"
        )
        if not self._ui_ask_yes_no("确认返回", confirm_text):
            self._log("用户取消返回。")
            return

        result = self.return_service.execute_return(
            order=order,
            current_area=current_area,
            current_server=selected_server,
            log_cb=self._log,
        )

        if result.get("success"):
            self._log("超域返回成功。")
            self._ui_show_info("成功", "超域返回成功。")
            self._refresh_announcements()
            return

        self._ui_show_error("失败", result.get("message", "超域返回失败"))

    # ---------------- announcements ----------------
    def on_refresh_announcements(self):
        """响应公告刷新请求。"""
        self._run_bg(self._refresh_announcements)

    def _refresh_announcements(self):
        """加载并显示公告文本内容。"""
        ads = self.runtime_service.get_bottom_announcements()
        if not ads:
            content = "暂无公告。"
        else:
            lines = []
            for ad in ads:
                title = ad.get("title", "")
                text = ad.get("content", "")
                link = ad.get("link_url", "")
                if title:
                    lines.append(f"【{title}】")
                if text:
                    lines.append(text)
                if link:
                    lines.append(f"链接: {link}")
                lines.append("")
            content = "\n".join(lines).strip()

        def apply_text():
            self.ann_text.configure(state="normal")
            self.ann_text.delete("1.0", "end")
            self.ann_text.insert("end", content)
            self.ann_text.configure(state="disabled")

        self._call_in_ui_thread(apply_text)

    # ---------------- version check ----------------
    def _mark_version_update_label(self, latest_version: str):
        """将版本号标签标记为红色并展示最新版本。"""
        latest = latest_version or "未知"
        self._call_in_ui_thread(
            self.version_label.configure,
            text=f"v{VERSION} → v{latest}",
            foreground="red",
        )

    def _show_force_update_dialog(self, latest_version: str, update_url: str) -> str:
        """显示强制更新阻断弹窗并返回用户操作。"""
        dialog = tk.Toplevel(self)
        dialog.title("需要更新")
        dialog.geometry("520x260")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        result = {"action": "close"}

        msg = (
            "检测到当前版本已不受支持，需要更新后才能继续使用。\n\n"
            f"当前版本: v{VERSION}\n"
            f"最新版本: v{latest_version or '未知'}"
        )
        if update_url:
            msg += f"\n\n下载地址:\n{update_url}"

        ttk.Label(dialog, text=msg, justify="left", wraplength=490).pack(fill="x", padx=16, pady=(16, 8))

        btns = ttk.Frame(dialog)
        btns.pack(fill="x", padx=16, pady=(8, 16))

        def on_close_program():
            result["action"] = "close"
            dialog.destroy()

        def on_download_update():
            if update_url:
                webbrowser.open(update_url)
                self._log(f"已打开下载链接: {update_url}")
            result["action"] = "download"
            dialog.destroy()

        ttk.Button(btns, text="关闭程序", command=on_close_program).pack(side="right", padx=5)
        ttk.Button(
            btns,
            text="前往下载更新",
            command=on_download_update,
            state="normal" if update_url else "disabled",
        ).pack(side="right", padx=5)

        dialog.protocol("WM_DELETE_WINDOW", on_close_program)
        self.wait_window(dialog)
        return result["action"]

    def on_check_update(self):
        """响应“检查更新”按钮事件。"""
        self._run_bg(self._check_update)

    def _check_update(self):
        """执行版本检查并按结果展示提示。"""
        self._log("正在检查更新…")
        version_result = self.runtime_service.check_version()
        version_info = version_result.get("version_info")
        self._debug(
            f"检查更新结果: can_continue={version_result.get('can_continue')}, is_latest={version_result.get('is_latest')}"
        )

        if version_info and not version_result.get("can_continue", True):
            latest = version_info.get("latest_version", "未知")
            update_url = version_info.get("update_url", "")
            self._mark_version_update_label(latest)
            self._set_blocked(True)
            self._log(f"检测到强制更新，最新版本：{latest}")
            action = self._call_in_ui_thread(self._show_force_update_dialog, latest, update_url)
            if action == "close":
                self._call_in_ui_thread(self.destroy)
            return

        if version_info and not version_result.get("is_latest", True):
            latest = version_info.get("latest_version", "未知")
            changelog = version_info.get("changelog", "暂无更新日志")
            update_url = version_info.get("update_url", "")
            self._mark_version_update_label(latest)
            
            # 构造详细的更新信息
            msg = f"当前版本: v{VERSION}\n最新版本: v{latest}"
            if changelog:
                msg += f"\n\n更新日志:\n{changelog}"
            
            self._log(f"发现新版本：{latest}")
            self._call_in_ui_thread(self._show_update_dialog, msg, update_url)
        else:
            self._ui_show_info("版本检查", "当前已是最新版本。")
            self._log("当前已是最新版本。")

    def _show_update_dialog(self, content: str, update_url: str):
        """显示带更新日志与下载入口的更新对话框。"""
        dialog = tk.Toplevel(self)
        dialog.title("版本更新")
        dialog.geometry("450x300")
        dialog.transient(self)
        dialog.grab_set()

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        text_widget = tk.Text(text_frame, height=10, width=50, yscrollcommand=scrollbar.set, wrap="word")
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_widget.yview)

        text_widget.insert("end", content)
        text_widget.config(state="disabled")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", padx=10, pady=10)

        if update_url:
            ttk.Button(
                btn_frame,
                text="前往下载",
                command=partial(self._open_download_and_close, update_url, dialog),
            ).pack(side="right", padx=5)

        ttk.Button(btn_frame, text="关闭", command=dialog.destroy).pack(side="right", padx=5)

    def _open_download_and_close(self, update_url: str, dialog):
        """打开下载链接并关闭更新对话框。"""
        webbrowser.open(update_url)
        self._log(f"已打开下载链接: {update_url}")
        dialog.destroy()


def main():
    """GUI程序入口。"""
    app = FF14DCTGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
