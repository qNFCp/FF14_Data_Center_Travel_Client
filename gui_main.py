#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# FF14 DCT 图形界面启动器

from __future__ import annotations

import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from modules import (
    ConfigManager,
    LoginService,
    ReturnOrchestrator,
    RuntimeService,
    TransferOrchestrator,
    VERSION,
    init_log_file,
)
from modules.config import USE_HTTP_PROXY, HTTP_PROXY


class UILogger:
    def __init__(self, text: tk.Text):
        self.text = text
        self.q: queue.Queue[str] = queue.Queue()

    def write(self, msg: str):
        if msg:
            self.q.put(msg)

    def flush_to_ui(self):
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
        super().__init__()
        self.title("FF14 超域传送/返回 (GUI)")
        self.geometry("920x720")
        self.minsize(860, 620)

        self.config_mgr = ConfigManager()
        self.api = None
        self._worker_lock = threading.Lock()
        self._blocked = False
        self._logged_in = False

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

        self.src_area_cb.bind("<<ComboboxSelected>>", lambda _e: self._run_bg(self._load_src_servers))
        self.src_server_cb.bind("<<ComboboxSelected>>", lambda _e: self._run_bg(self._load_roles))
        self.dst_area_cb.bind("<<ComboboxSelected>>", lambda _e: self._run_bg(self._load_dst_servers))

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

    # ---------------- threading helpers ----------------
    def _tick(self):
        self.logger.flush_to_ui()
        self.after(120, self._tick)

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.logger.write(f"[{ts}] {msg}\n")

    def _call_in_ui_thread(self, fn):
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
        self._call_in_ui_thread(lambda: messagebox.showerror(title, msg))

    def _ui_show_info(self, title: str, msg: str):
        self._call_in_ui_thread(lambda: messagebox.showinfo(title, msg))

    def _ui_ask_yes_no(self, title: str, msg: str) -> bool:
        return bool(self._call_in_ui_thread(lambda: messagebox.askyesno(title, msg)))

    def _run_bg(self, fn, *args, **kwargs):
        def runner():
            if not self._worker_lock.acquire(blocking=False):
                self._log("已有任务在运行，请稍候…")
                return
            try:
                fn(*args, **kwargs)
            except Exception as e:
                self._log(f"异常: {e}")
                self._log(traceback.format_exc())
                self._ui_show_error("发生异常", str(e))
            finally:
                self._worker_lock.release()

        t = threading.Thread(target=runner, daemon=True)
        t.start()

    # ---------------- app lifecycle ----------------
    def _startup(self):
        init_log_file()
        self._log("启动初始化中…")

        # 显示系统代理信息
        if USE_HTTP_PROXY and HTTP_PROXY:
            self._log(f"检测到系统HTTP代理: {HTTP_PROXY}")
        else:
            self._log("未检测到系统HTTP代理")

        self.runtime_service.record_app_start()

        version_result = self.runtime_service.check_version()
        version_info = version_result.get("version_info")
        latest_version = None

        if not version_result.get("can_continue", True):
            self._set_blocked(True)
            update_url = ""
            if version_info:
                update_url = version_info.get("update_url", "")
            msg = "检测到当前版本已不受支持，请升级后再使用。"
            if update_url:
                msg += f"\n\n更新地址：{update_url}"
            self._ui_show_error("需要更新", msg)
            self._log("版本检查阻断：当前版本不受支持。")
            return

        if version_info and not version_result.get("is_latest", True):
            latest_version = version_info.get("latest_version", "未知")
            # 更新版本号标签为红色，显示最新版本
            self._call_in_ui_thread(lambda: self.version_label.configure(
                text=f"v{VERSION} → v{latest_version}",
                foreground="red"
            ))
            self._log("版本检查：有新版本可用。")
        else:
            self._log("版本检查：当前为可用版本。")

        self._refresh_announcements()
        self._try_cached_login()

    def on_close(self):
        try:
            self.login_service.close_browser()
        finally:
            self.destroy()

    def _set_blocked(self, blocked: bool):
        self._blocked = blocked
        state = "disabled" if blocked else "normal"
        self._call_in_ui_thread(lambda: self.btn_login.configure(state=state))
        self._call_in_ui_thread(lambda: self.btn_confirm_login.configure(state=state))
        self._call_in_ui_thread(lambda: self.btn_clear.configure(state=state))
        if blocked:
            self._set_logged_in(False)

    def _set_logged_in(self, ok: bool):
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
        self.api = api_client
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
        api = self.login_service.try_cached_login()
        if not api:
            self._set_api_client(None)
            self._log("请先点击“打开登录页面”。")
            return

        self._set_api_client(api)
        self._log("缓存登录成功。")
        self._populate_areas()

    def on_open_login(self):
        if self._blocked:
            return
        self._run_bg(self._open_login)

    def _open_login(self):
        choice = self._call_in_ui_thread(lambda: self.browser_var.get())
        self._log(f"初始化浏览器：{choice}")
        self.login_service.open_login_page(choice)

    def on_confirm_login(self):
        if self._blocked:
            return
        self._run_bg(self._confirm_login)

    def _confirm_login(self):
        self._log("确认登录并验证Cookie…")
        api = self.login_service.confirm_login()
        self._set_api_client(api)
        self._log("登录成功。")
        self._populate_areas()

    def on_clear_cache(self):
        if self._blocked:
            return
        if not self._ui_ask_yes_no("确认", "确认清除缓存登录并退出当前会话吗？"):
            return
        self.login_service.clear_cached_login()
        self._set_api_client(None)

    # ---------------- area/server/role ----------------
    def on_refresh_lists(self):
        if not self._logged_in:
            return
        self._run_bg(self._populate_areas)

    def _get_selected(self, var: tk.StringVar) -> str:
        return self._call_in_ui_thread(lambda: var.get())

    def _set_combobox_values(self, cb: ttk.Combobox, values):
        self._call_in_ui_thread(lambda: cb.configure(values=values))

    def _set_var(self, var: tk.StringVar, value: str):
        self._call_in_ui_thread(lambda: var.set(value))

    def _populate_areas(self):
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

    def _find_area_by_name(self, name: str):
        if not self.api:
            return None
        # 从缓存的大区列表中查找，如果没有缓存则从API获取
        areas = self._areas_cache if self._areas_cache else self.api.get_areas()
        for area in areas:
            if area.get("areaName") == name:
                return area
        return None

    def _refresh_target_areas(self):
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
        self._set_combobox_values(self.src_server_cb, names)

        if names:
            current = self._get_selected(self.src_server_var)
            if current not in names:
                self._set_var(self.src_server_var, names[0])

        self._load_roles()

    def _load_dst_servers(self):
        if not self.api:
            return

        area = self._find_area_by_name(self._get_selected(self.dst_area_var))
        if not area:
            return

        servers = self.api.get_servers(area)
        names = [s.get("groupName", "") for s in servers]
        self._set_combobox_values(self.dst_server_cb, names)

        if names:
            current = self._get_selected(self.dst_server_var)
            if current not in names:
                self._set_var(self.dst_server_var, names[0])

    def _load_roles(self):
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
        self._set_combobox_values(self.role_cb, names)

        if names:
            current = self._get_selected(self.role_var)
            if current not in names:
                self._set_var(self.role_var, names[0])

    # ---------------- transfer ----------------
    def on_transfer(self):
        self._ui_show_info(
            "提示",
            "请在左侧‘跨区传送（向导）’中选择源大区/服务器/角色与目标大区/服务器，然后点击‘执行跨区传送’。\n\n"
            "（如果列表为空，请先点击‘刷新区服/角色列表’）",
        )

    def on_do_transfer(self):
        if not self.transfer_service:
            self._ui_show_error("未登录", "请先完成登录。")
            return

        ok = self._ui_ask_yes_no("确认", "确认提交跨区传送请求吗？\n\n失败将按 61-65 秒随机间隔自动重试。")
        if not ok:
            return
        self._run_bg(self._do_transfer)

    def _do_transfer(self):
        if not self.transfer_service:
            return

        source_area = self._get_selected(self.src_area_var)
        source_server = self._get_selected(self.src_server_var)
        role_name = self._get_selected(self.role_var)
        target_area = self._get_selected(self.dst_area_var)
        target_server = self._get_selected(self.dst_server_var)

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
        if not self.return_service:
            self._ui_show_error("未登录", "请先完成登录。")
            return
        self._run_bg(self._do_return)

    def _choose_order(self, orders):
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
            lambda: simpledialog.askinteger(
                "选择订单",
                prompt,
                minvalue=1,
                maxvalue=len(orders),
            )
        )
        if not choice:
            return None
        return orders[choice - 1]

    def _choose_server_with_fallback(self, servers, default_server):
        default_name = default_server.get("groupName", "未知")
        use_default = self._ui_ask_yes_no(
            "确认当前服务器",
            f"订单默认服务器为：{default_name}\n\n若你在当前大区内又跨服，请点“否”自行选择。\n是否使用默认服务器？",
        )
        if use_default:
            return default_server

        lines = ["请选择你当前实际所在服务器：", ""]
        for idx, server in enumerate(servers, 1):
            mark = " (默认)" if server.get("groupName") == default_name else ""
            lines.append(f"[{idx}] {server.get('groupName', '未知')}{mark}")

        choice = self._call_in_ui_thread(
            lambda: simpledialog.askinteger(
                "选择服务器",
                "\n".join(lines),
                minvalue=1,
                maxvalue=len(servers),
            )
        )
        if not choice:
            return None
        return servers[choice - 1]

    def _do_return(self):
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

        current_area, servers, default_server = self.return_service.resolve_current_server_options(order)
        selected_server = self._choose_server_with_fallback(servers, default_server)
        if not selected_server:
            self._log("用户取消服务器选择。")
            return

        role_name = order.get("roleName") or (order.get("migrationDetailList") or [{}])[0].get("roleName", "未知")
        order_id = order.get("orderId", "")
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
        self._run_bg(self._refresh_announcements)

    def _refresh_announcements(self):
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
    def on_check_update(self):
        self._run_bg(self._check_update)

    def _check_update(self):
        self._log("正在检查更新…")
        version_result = self.runtime_service.check_version()
        version_info = version_result.get("version_info")

        if version_info and not version_result.get("is_latest", True):
            latest = version_info.get("latest_version", "未知")
            changelog = version_info.get("changelog", "暂无更新日志")
            update_url = version_info.get("update_url", "")
            
            # 构造详细的更新信息
            msg = f"当前版本: v{VERSION}\n最新版本: v{latest}"
            if changelog:
                msg += f"\n\n更新日志:\n{changelog}"
            
            self._log(f"发现新版本：{latest}")
            
            # 显示含有下载链接的信息框
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes('-topmost', True)  # 将窗口置顶
            
            # 创建自定义对话框
            dialog = tk.Toplevel(root)
            dialog.title("版本更新")
            dialog.geometry("450x300")
            dialog.attributes('-topmost', True)
            dialog.transient(root)
            dialog.grab_set()
            
            # 创建文本显示区域（带滚动条）
            text_frame = ttk.Frame(dialog)
            text_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            scrollbar = ttk.Scrollbar(text_frame)
            scrollbar.pack(side="right", fill="y")
            
            text_widget = tk.Text(text_frame, height=10, width=50, yscrollcommand=scrollbar.set, wrap="word")
            text_widget.pack(side="left", fill="both", expand=True)
            scrollbar.config(command=text_widget.yview)
            
            text_widget.insert("end", msg)
            text_widget.config(state="disabled")
            
            # 创建按钮框
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(fill="x", padx=10, pady=10)
            
            def open_download():
                if update_url:
                    import webbrowser
                    webbrowser.open(update_url)
                    self._log(f"已打开下载链接: {update_url}")
                dialog.destroy()
                root.destroy()
            
            if update_url:
                ttk.Button(btn_frame, text="前往下载", command=open_download).pack(side="right", padx=5)
            
            ttk.Button(btn_frame, text="关闭", command=lambda: (dialog.destroy(), root.destroy())).pack(side="right", padx=5)
            
            root.mainloop()
        else:
            self._ui_show_info("版本检查", "当前已是最新版本。")
            self._log("当前已是最新版本。")


def main():
    app = FF14DCTGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
