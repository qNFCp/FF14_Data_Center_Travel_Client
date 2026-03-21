#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#FF14 DCT 图形界面启动器 

from __future__ import annotations

import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

from modules import ConfigManager, FF14APIClient, credential_manager
from modules.browser import BrowserManager


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
        self.geometry("900x650")
        self.minsize(860, 620)

        self.config_mgr = ConfigManager()
        self.browser_mgr: BrowserManager | None = None
        self.api: FF14APIClient | None = None

        self._worker_lock = threading.Lock()

        self._build_ui()
        self.after(100, self._tick)

        self._run_bg(self._try_cached_login)

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="浏览器:").pack(side="left")
        self.browser_var = tk.StringVar(value="Edge")
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


        self.src_area_cb.bind("<<ComboboxSelected>>", lambda e: self._run_bg(self._load_src_servers))
        self.src_server_cb.bind("<<ComboboxSelected>>", lambda e: self._run_bg(self._load_roles))
        self.dst_area_cb.bind("<<ComboboxSelected>>", lambda e: self._run_bg(self._load_dst_servers))


        right = ttk.LabelFrame(body, text="运行日志")
        right.pack(side="right", fill="both", expand=True)

        self.log_text = tk.Text(right, height=20, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.logger = UILogger(self.log_text)


        self._set_logged_in(False)

    def _tick(self):
        self.logger.flush_to_ui()
        self.after(120, self._tick)

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.logger.write(f"[{ts}] {msg}\n")

    def _set_logged_in(self, ok: bool):
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
                messagebox.showerror("发生异常", str(e))
            finally:
                self._worker_lock.release()

        t = threading.Thread(target=runner, daemon=True)
        t.start()

    #登录
    def _try_cached_login(self):
        self._log("检查缓存登录凭据…")
        cookies = credential_manager.load_cookies()
        if not cookies:
            self._log("未找到缓存Cookie，请点击“打开登录页面”。")
            return

        self._log(f"找到缓存Cookie({len(cookies)}个)，验证中…")
        api = FF14APIClient()
        api.set_cookies(cookies)
        if api.fetch_area_list():
            self.api = api
            self._log("缓存登录有效：已登录。")
            self._set_logged_in(True)
            self._populate_areas()
        else:
            self._log("缓存登录已失效，已清除。")
            credential_manager.delete_cookies()

    def on_open_login(self):
        self._run_bg(self._open_login)

    def _open_login(self):
        self._log("初始化浏览器…")
        self.browser_mgr = BrowserManager(self.config_mgr)
        choice = self.browser_var.get()
        ok = self.browser_mgr.init_browser_with_choice(choice)
        if not ok:
            raise RuntimeError("浏览器初始化失败")
        self._log("打开登录页面…")
        if not self.browser_mgr.open_login_page():
            raise RuntimeError("无法打开登录页面")
        self._log("请在弹出的浏览器中完成登录，然后回到本窗口点击“我已登录，继续”。")

    def on_confirm_login(self):
        self._run_bg(self._confirm_login)

    def _confirm_login(self):
        if not self.browser_mgr:
            messagebox.showwarning("提示", "请先点击“打开登录页面”。")
            return

        self._log("获取登录Cookie…")
        cookies = self.browser_mgr.get_sdo_cookies()
        if not cookies:
            messagebox.showerror("未登录", "未获取到Cookie，请确认已在浏览器中完成登录。")
            return

        api = FF14APIClient()
        api.set_cookies(cookies)

        self._log("验证登录并获取区服列表…")
        if not api.fetch_area_list():
            messagebox.showerror("登录验证失败", "获取区服列表失败：请确认登录成功，或稍后重试。")
            return

        # 保存cookies
        credential_manager.save_cookies(cookies)

        self.api = api
        self._set_logged_in(True)
        self._log("登录成功。")
        self._populate_areas()

    def on_clear_cache(self):
        try:
            credential_manager.delete_cookies()
            self._log("已清除缓存Cookie。")
            self.api = None
            self._set_logged_in(False)
        except Exception as e:
            messagebox.showerror("清除失败", str(e))

    #传送 
    def on_refresh_lists(self):
        self._run_bg(self._populate_areas)

    def _populate_areas(self):
        if not self.api:
            return
        areas = self.api.get_areas()
        if not areas:
            raise RuntimeError("未能获取大区列表")

        area_names = [a.get("areaName", "") for a in areas]
        self.src_area_cb["values"] = area_names
        self.dst_area_cb["values"] = area_names

        if area_names and not self.src_area_var.get():
            self.src_area_var.set(area_names[0])
        if area_names and not self.dst_area_var.get():
            self.dst_area_var.set(area_names[1] if len(area_names) > 1 else area_names[0])

        self._load_src_servers()
        self._load_dst_servers()

    def _find_area_by_name(self, name: str):
        assert self.api
        for a in self.api.get_areas():
            if a.get("areaName") == name:
                return a
        return None

    def _load_src_servers(self):
        if not self.api:
            return
        area = self._find_area_by_name(self.src_area_var.get())
        if not area:
            return
        servers = self.api.get_servers(area)
        names = [s.get("groupName", "") for s in servers]
        self.src_server_cb["values"] = names
        if names:
            self.src_server_var.set(names[0])
        self._load_roles()

    def _load_dst_servers(self):
        if not self.api:
            return
        area = self._find_area_by_name(self.dst_area_var.get())
        if not area:
            return
        servers = self.api.get_servers(area)
        names = [s.get("groupName", "") for s in servers]
        self.dst_server_cb["values"] = names
        if names:
            self.dst_server_var.set(names[0])

    def _load_roles(self):
        if not self.api:
            return
        area = self._find_area_by_name(self.src_area_var.get())
        if not area:
            return
        servers = self.api.get_servers(area)
        server = next((s for s in servers if s.get("groupName") == self.src_server_var.get()), None)
        if not server:
            return

        self._log("获取角色列表…")
        roles = self.api.fetch_role_list(area.get("areaId"), server.get("groupId"))
        role_names = [r.get("roleName", r.get("name", "")) for r in roles]
        self.role_cb["values"] = role_names
        if role_names:
            self.role_var.set(role_names[0])

    def on_transfer(self):
        messagebox.showinfo(
            "提示",
            "请在左侧‘跨区传送（向导）’中选择源大区/服务器/角色与目标大区/服务器，然后点击‘执行跨区传送’。\n\n"
            "（如果列表为空，请先点击‘刷新区服/角色列表’）",
        )

    def on_do_transfer(self):
        if not self.api:
            messagebox.showwarning("未登录", "请先完成登录。")
            return
        if not messagebox.askyesno("确认", "确认要提交跨区传送请求吗？\n\n注意：后端限制 1 分钟 1 次，失败会自动重试。"):
            return
        self._run_bg(self._do_transfer)

    def _do_transfer(self):
        assert self.api
        areas = self.api.get_areas()
        src_area = next((a for a in areas if a.get("areaName") == self.src_area_var.get()), None)
        dst_area = next((a for a in areas if a.get("areaName") == self.dst_area_var.get()), None)
        if not src_area or not dst_area:
            raise RuntimeError("源/目标大区选择无效")

        src_servers = self.api.get_servers(src_area)
        dst_servers = self.api.get_servers(dst_area)
        src_server = next((s for s in src_servers if s.get("groupName") == self.src_server_var.get()), None)
        dst_server = next((s for s in dst_servers if s.get("groupName") == self.dst_server_var.get()), None)
        if not src_server or not dst_server:
            raise RuntimeError("源/目标服务器选择无效")

        roles = self.api.fetch_role_list(src_area.get("areaId"), src_server.get("groupId"))
        role = next(
            (r for r in roles if (r.get("roleName", r.get("name")) == self.role_var.get())),
            None,
        )
        if not role:
            raise RuntimeError("角色选择无效")

        role_name = role.get("roleName", role.get("name", "未知"))
        self._log(f"提交跨区传送：{role_name} | {src_area['areaName']}-{src_server['groupName']} -> {dst_area['areaName']}-{dst_server['groupName']}")

        # 初始化
        self.api.page_init(migration_type=4)

        attempt = 0
        while True:
            attempt += 1
            self._log(f"第 {attempt} 次提交请求…")
            result = self.api.submit_transfer(src_area, src_server, dst_area, dst_server, role)

            if isinstance(result, str) and result.startswith("GM"):
                order_id = result
                self._log(f"已提交订单: {order_id}，开始查询状态…")
                for i in range(10):
                    status = self.api.check_order_status(order_id)
                    self._log(f"状态查询 {i+1}/10：{status}")
                    if status == 5:
                        messagebox.showinfo("成功", f"跨区传送成功！\n\n订单号：{order_id}")
                        self._log("跨区传送成功。")
                        return
                    if status == -1:
                        self._log("预检失败，准备重试…")
                        break
                    time.sleep(5)


            if isinstance(result, dict) and (result.get("resultCode") in (0, 5)):
                messagebox.showinfo("成功", "跨区传送成功！")
                self._log("跨区传送成功（无订单号返回）。")
                return

            wait_sec = 62
            self._log(f"提交未成功，将在 {wait_sec}s 后自动重试（按窗口右上角 X 可退出）。")
            time.sleep(wait_sec)

    #返回
    def on_return(self):
        self._run_bg(self._do_return)

    def _do_return(self):
        """简化版超域返回：直接复用 API，自动选择第一个‘旅行中’订单并执行返回。

        为了降低初次GUI复杂度，这里先提供“傻瓜模式”。
        如需完整订单/服务器选择，可继续扩展为向导窗口。
        """
        if not self.api:
            messagebox.showwarning("未登录", "请先完成登录。")
            return

        self._log("初始化返回页面…")
        self.api.page_init(migration_type=0)

        self._log("拉取旅行订单…")
        orders = self.api.fetch_migration_orders()
        if not orders:
            messagebox.showerror("失败", "未能获取订单列表，请检查登录状态。")
            return

        # 复用 ReturnService 的筛选逻辑会更好，但为了不引入CLI交互，这里做最小筛选
        order_list = orders.get("orderlist", [])
        active = []
        for o in order_list:
            if o.get("migrationType") == 4 and ("旅行中" in (o.get("migrationStatusDesc") or "")):
                active.append(o)

        if not active:
            messagebox.showinfo("没有可返回订单", "未找到‘旅行中’的超域旅行订单。")
            return

        if len(active) > 1:
            messagebox.showinfo(
                "提示",
                f"检测到 {len(active)} 个旅行订单。GUI当前会默认选择第 1 个。\n\n"
                "（如你需要选择具体订单，我可以把这里扩展成列表选择窗口。）",
            )

        order = active[0]
        order_id = order.get("orderId")
        role_name = order.get("roleName") or (order.get("migrationDetailList") or [{}])[0].get("roleName", "未知")

        if not messagebox.askyesno("确认", f"确认对以下订单执行超域返回？\n\n订单号：{order_id}\n角色：{role_name}"):
            return

        self._log(f"准备返回：订单 {order_id} / 角色 {role_name}")
        return_areas = self.api.fetch_return_area_list()
        if not return_areas:
            messagebox.showerror("失败", "未能获取可返回服务器列表")
            return


        current_area_id = order.get("targetAreaId")
        current_group_id = order.get("targetGroupId")

        current_area = next((a for a in return_areas if a.get("areaId") == current_area_id), None)
        if not current_area:
            messagebox.showerror("失败", "无法匹配订单目的地大区")
            return

        current_server = next((g for g in current_area.get("groups", []) if g.get("groupId") == current_group_id), None)
        if not current_server:

            cur_name = order.get("targetGroupName")
            current_server = next((g for g in current_area.get("groups", []) if g.get("groupName") == cur_name), None)

        if not current_server:
            messagebox.showerror("失败", "无法匹配订单目的地服务器")
            return

        self._log(f"当前所在：{current_area.get('areaName')} - {current_server.get('groupName')}")
        self._log("提交超域返回请求…")

        attempt = 0
        while True:
            attempt += 1
            self._log(f"第 {attempt} 次提交返回…")
            resp = self.api.submit_travel_back(
                travel_order_id=order_id,
                group_id=current_server.get("groupId"),
                group_code=current_server.get("groupCode"),
                group_name=current_server.get("groupName"),
            )
            if resp and resp.get("success"):
                messagebox.showinfo("成功", "超域返回请求已提交！请在游戏内等待完成。")
                self._log("超域返回提交成功。")
                return
            wait_sec = 62
            self._log(f"提交失败，将在 {wait_sec}s 后重试…")
            time.sleep(wait_sec)


def main():
    app = FF14DCTGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
