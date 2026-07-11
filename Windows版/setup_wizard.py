"""首次配置向导 GUI。

4 步分页：
  1. 飞书应用配置（小闹/小知 app_id+secret + chat_id）
  2. AI 模型配置（api_key/api_base/model）
  3. 多维表格配置（可选）
  4. 完成

每步有「测试连接」按钮验证配置。完成后调用 config_loader.write_env 生成 .env。

字体跨平台：Mac 用 PingFang SC，Windows 用 Microsoft YaHei。
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_loader as cl
import connection_tester as ct


def get_font():
    """跨平台中文字体名。"""
    available = tk.font.families() if hasattr(tk, "font") else []
    for name in ("PingFang SC", "Microsoft YaHei", "微软雅黑", "Heiti SC", "SimHei"):
        if name in available:
            return name
    return ""  # 系统默认


class SetupWizard:
    def __init__(self, root, on_complete=None):
        self.root = root
        self.on_complete = on_complete  # 配置完成后的回调
        self.step = 0  # 当前步骤 0-3
        self.config = {}  # 收集的配置

        self.font = get_font()
        self._build_ui()
        self._show_step()

    def _f(self, size=11, bold=False):
        """生成字体 tuple。"""
        return (self.font, size, "bold") if bold else (self.font, size)

    def _build_ui(self):
        self.root.title("个人助理 - 初始配置")
        self.root.geometry("520x560")
        self.root.resizable(False, False)

        # 标题
        self.title_label = tk.Label(self.root, text="",
                                    font=self._f(18, True))
        self.title_label.pack(pady=(20, 5))

        # 进度提示
        self.progress_label = tk.Label(self.root, text="", font=self._f(9),
                                       fg="#999")
        self.progress_label.pack(pady=(0, 10))

        # 内容容器（每步切换内容）
        self.content = tk.Frame(self.root)
        self.content.pack(fill=tk.BOTH, expand=True, padx=30)

        # 底部按钮
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(side=tk.BOTTOM, pady=15)
        self.btn_back = tk.Button(btn_frame, text="上一步", command=self._prev,
                                  font=self._f(11), width=10, state=tk.DISABLED)
        self.btn_back.pack(side=tk.LEFT, padx=5)
        self.btn_next = tk.Button(btn_frame, text="下一步", command=self._next,
                                  font=self._f(11), width=10)
        self.btn_next.pack(side=tk.LEFT, padx=5)

    def _show_step(self):
        """显示当前步骤。"""
        # 清空内容区
        for widget in self.content.winfo_children():
            widget.destroy()

        steps = ["飞书应用", "AI 模型", "多维表格", "完成"]
        self.title_label.config(text=steps[self.step])
        self.progress_label.config(text=f"第 {self.step + 1} / 4 步")

        if self.step == 0:
            self._step_feishu()
        elif self.step == 1:
            self._step_ai()
        elif self.step == 2:
            self._step_bitable()
        elif self.step == 3:
            self._step_done()

        # 按钮状态
        self.btn_back.config(state=tk.NORMAL if self.step > 0 else tk.DISABLED)
        self.btn_next.config(text="完成" if self.step == 3 else "下一步")

    # =========================================================
    # 步骤1：飞书应用
    # =========================================================
    def _step_feishu(self):
        tk.Label(self.content, text="小闹（执行助理）应用配置",
                 font=self._f(12, True)).pack(anchor="w", pady=(0, 5))
        self._fe_entry("FEISHU_XIAONAO_APP_ID", "小闹 App ID:", "cli_...")
        self._fe_entry("FEISHU_XIAONAO_SECRET", "小闹 App Secret:", "")

        tk.Label(self.content, text="").pack()
        tk.Label(self.content, text="小知（教练助理）应用配置",
                 font=self._f(12, True)).pack(anchor="w", pady=(0, 5))
        self._fe_entry("FEISHU_XIAOZHI_APP_ID", "小知 App ID:", "cli_...")
        self._fe_entry("FEISHU_XIAOZHI_SECRET", "小知 App Secret:", "")

        tk.Label(self.content, text="").pack()
        tk.Label(self.content, text="群聊配置",
                 font=self._f(12, True)).pack(anchor="w", pady=(0, 5))
        self._fe_entry("FEISHU_CHAT_ID", "群 Chat ID:", "oc_...")

        self._test_button("测试飞书连接", self._test_feishu)

    def _test_feishu(self):
        threading.Thread(target=self._do_test_feishu, daemon=True).start()

    def _do_test_feishu(self):
        c = self.config
        results = []
        for key, label in [("FEISHU_XIAONAO_APP_ID", "小闹"),
                           ("FEISHU_XIAOZHI_APP_ID", "小知")]:
            app_id = c.get(key, "").get()
            app_id = app_id if hasattr(app_id, "get") else app_id
        # 简化：直接读 entry 值
        ok1, msg1 = ct.test_feishu_app(
            self._entries["FEISHU_XIAONAO_APP_ID"].get(),
            self._entries["FEISHU_XIAONAO_SECRET"].get(), "小闹")
        ok2, msg2 = ct.test_feishu_app(
            self._entries["FEISHU_XIAOZHI_APP_ID"].get(),
            self._entries["FEISHU_XIAOZHI_SECRET"].get(), "小知")
        msg = msg1 + "\n" + msg2
        self.root.after(0, lambda: messagebox.showinfo("测试结果", msg))

    # =========================================================
    # 步骤2：AI 模型
    # =========================================================
    def _step_ai(self):
        tk.Label(self.content, text="大模型配置（OpenAI 兼容接口）",
                 font=self._f(12, True)).pack(anchor="w", pady=(0, 5))
        tk.Label(self.content,
                 text="推荐 DeepSeek：api_base 填 https://api.deepseek.com/v1\n"
                      "model 填 deepseek-chat",
                 font=self._f(9), fg="#888", justify=tk.LEFT).pack(anchor="w", pady=(0, 10))
        self._fe_entry("AI_API_KEY", "API Key:", "sk-...")
        self._fe_entry("AI_API_BASE", "API Base:", "https://api.deepseek.com/v1")
        self._fe_entry("AI_MODEL", "模型名:", "deepseek-chat")

        self._test_button("测试 AI 连接", self._test_ai)

    def _test_ai(self):
        threading.Thread(target=self._do_test_ai, daemon=True).start()

    def _do_test_ai(self):
        ok, msg = ct.test_ai(
            self._entries["AI_API_KEY"].get(),
            self._entries["AI_API_BASE"].get(),
            self._entries["AI_MODEL"].get())
        self.root.after(0, lambda: messagebox.showinfo("测试结果", msg))

    # =========================================================
    # 步骤3：多维表格（可选）
    # =========================================================
    def _step_bitable(self):
        tk.Label(self.content, text="多维表格配置（可选）",
                 font=self._f(12, True)).pack(anchor="w", pady=(0, 5))
        tk.Label(self.content,
                 text="同步数据到飞书多维表格，方便可视化查看。\n"
                      "如不需要可跳过此步。",
                 font=self._f(9), fg="#888", justify=tk.LEFT).pack(anchor="w", pady=(0, 10))

        self._fe_entry("BITABLE_APP_ID", "史官 App ID:", "cli_...")
        self._fe_entry("BITABLE_APP_SECRET", "史官 App Secret:", "")
        self._fe_entry("BITABLE_APP_TOKEN", "多维表格 URL 或 Token:", "粘贴完整URL自动解析")

        # 自动解析 URL
        def on_url_change(*_):
            val = self._entries["BITABLE_APP_TOKEN"].get()
            token = ct.parse_bitable_url(val)
            if token and token != val:
                self._entries["BITABLE_APP_TOKEN"].delete(0, tk.END)
                self._entries["BITABLE_APP_TOKEN"].insert(0, token)

        self._entries["BITABLE_APP_TOKEN"].bind("<FocusOut>", on_url_change)

        self._test_button("测试多维表格连接", self._test_bitable)

    def _test_bitable(self):
        threading.Thread(target=self._do_test_bitable, daemon=True).start()

    def _do_test_bitable(self):
        ok, msg = ct.test_bitable(
            self._entries["BITABLE_APP_ID"].get(),
            self._entries["BITABLE_APP_SECRET"].get(),
            self._entries["BITABLE_APP_TOKEN"].get())
        self.root.after(0, lambda: messagebox.showinfo("测试结果", msg))

    # =========================================================
    # 步骤4：完成
    # =========================================================
    def _step_done(self):
        # 收集所有配置
        self._collect_all()
        tk.Label(self.content, text="配置完成！",
                 font=self._f(14, True), fg="#4CAF50").pack(pady=(30, 10))
        tk.Label(self.content,
                 text="点击「完成」保存配置并进入控制台。\n"
                      "之后可以随时点「重新配置」修改。",
                 font=self._f(11), justify=tk.LEFT).pack(pady=10)

        # 显示配置摘要
        summary = []
        if self.config.get("FEISHU_XIAONAO_APP_ID"):
            summary.append("✓ 飞书应用配置")
        if self.config.get("AI_API_KEY"):
            summary.append("✓ AI 模型配置")
        if self.config.get("BITABLE_APP_ID"):
            summary.append("✓ 多维表格配置")
        tk.Label(self.content, text="\n".join(summary),
                 font=self._f(11), fg="#666", justify=tk.LEFT).pack(pady=10)

    # =========================================================
    # 导航与保存
    # =========================================================
    def _next(self):
        if self.step < 3:
            self._collect_current()
            self.step += 1
            self._show_step()
        else:
            # 完成：保存配置
            self._collect_all()
            cl.write_env(self.config)
            cl.ensure_default_config()
            messagebox.showinfo("成功", "配置已保存！")
            if self.on_complete:
                self.on_complete()
            self.root.destroy()

    def _prev(self):
        if self.step > 0:
            self._collect_current()
            self.step -= 1
            self._show_step()

    def _collect_current(self):
        """收集当前步骤的 entry 值到 self.config。"""
        for key, entry in getattr(self, "_entries", {}).items():
            val = entry.get().strip()
            if val:
                self.config[key] = val

    def _collect_all(self):
        """收集所有步骤的配置（切回各步 entry 已销毁，从 self.config 取已有的）。"""
        self._collect_current()

    # =========================================================
    # UI 辅助
    # =========================================================
    def _fe_entry(self, key, label_text, placeholder=""):
        """创建一个 label + entry 组合，记录到 self._entries[key]。"""
        if not hasattr(self, "_entries"):
            self._entries = {}
        f = tk.Frame(self.content)
        f.pack(fill=tk.X, pady=3)
        tk.Label(f, text=label_text, font=self._f(10), width=16, anchor="w").pack(side=tk.LEFT)
        entry = tk.Entry(f, font=self._f(10), width=32)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if placeholder:
            entry.insert(0, self.config.get(key, placeholder))
            if not self.config.get(key):
                entry.config(fg="#999")
                entry.bind("<FocusIn>", lambda e: self._clear_placeholder(entry, placeholder))
        else:
            entry.insert(0, self.config.get(key, ""))
        self._entries[key] = entry

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg="black")

    def _test_button(self, text, command):
        btn = tk.Button(self.content, text=text, command=command,
                        font=self._f(10), width=16, cursor="hand2")
        btn.pack(anchor="w", pady=10)
