"""个人助理 App 入口（Windows + macOS 通用）。

启动逻辑：
  1. 检测配置完整性（~/个人助理数据/.env）
  2. 不完整 → 弹配置向导；完整 → 显示控制台
  3. 控制台：启动/停止助理 + 状态显示 + 重新配置入口

字体跨平台：Mac 用 PingFang SC，Windows 用 Microsoft YaHei。
进程管理：用 process_manager_win（psutil），跨平台。
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_loader as cl
import process_manager_win as pm


def get_font():
    """跨平台中文字体名。"""
    import tkinter.font as tkfont
    available = tkfont.families()
    for name in ("PingFang SC", "Microsoft YaHei", "微软雅黑", "Heiti SC", "SimHei"):
        if name in available:
            return name
    return ""


class ControlPanel:
    def __init__(self, root):
        self.root = root
        self.font = get_font()
        # 启动时先确保默认配置就绪
        cl.ensure_default_config()
        self._build_ui()
        self._refresh_loop()

    def _f(self, size=11, bold=False):
        return (self.font, size, "bold") if bold else (self.font, size)

    def _build_ui(self):
        self.root.title("个人助理")
        self.root.geometry("300x380")
        self.root.resizable(False, False)

        # 标题
        tk.Label(self.root, text="个人助理控制台",
                 font=self._f(16, True)).pack(pady=(18, 10))

        # 状态灯 + 文字
        status_frame = tk.Frame(self.root)
        status_frame.pack(pady=5)
        self.light = tk.Label(status_frame, text="●", font=("Arial", 28), fg="#999")
        self.light.pack(side=tk.LEFT, padx=(0, 8))
        self.status_label = tk.Label(status_frame, text="已停止", font=self._f(13))
        self.status_label.pack(side=tk.LEFT)

        # 详细信息
        info_frame = tk.Frame(self.root)
        info_frame.pack(pady=10, padx=30, fill=tk.X)
        self.info_pid = tk.Label(info_frame, text="PID：—", font=self._f(11),
                                 fg="#666", anchor="w", width=20)
        self.info_pid.pack(anchor="w")
        self.info_uptime = tk.Label(info_frame, text="运行时长：—", font=self._f(11),
                                    fg="#666", anchor="w", width=20)
        self.info_uptime.pack(anchor="w")
        self.info_mem = tk.Label(info_frame, text="内存占用：—", font=self._f(11),
                                 fg="#666", anchor="w", width=20)
        self.info_mem.pack(anchor="w")

        # 启动/停止按钮
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=18)
        self.btn_start = tk.Button(btn_frame, text="▶  启动", command=self.on_start,
                                   font=self._f(12), width=10, height=2,
                                   bg="#4CAF50", fg="white",
                                   activebackground="#43A047",
                                   relief=tk.FLAT, cursor="hand2")
        self.btn_start.pack(side=tk.LEFT, padx=8)
        self.btn_stop = tk.Button(btn_frame, text="■  停止", command=self.on_stop,
                                  font=self._f(12), width=10, height=2,
                                  bg="#F44336", fg="white",
                                  activebackground="#E53935",
                                  relief=tk.FLAT, cursor="hand2",
                                  state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=8)

        # 底部：重新配置
        bottom = tk.Frame(self.root)
        bottom.pack(side=tk.BOTTOM, pady=10)
        tk.Button(bottom, text="重新配置", command=self.on_reconfig,
                  font=self._f(9), relief=tk.FLAT, cursor="hand2",
                  fg="#2196F3").pack()

    # =========================================================
    # 按钮事件
    # =========================================================
    def on_start(self):
        # 启动前再检查一次配置完整性
        if not cl.env_is_complete():
            messagebox.showwarning("配置不完整",
                                   "请先完成配置（飞书应用、AI 密钥等）。\n点击「重新配置」。")
            return
        cl.ensure_default_config()
        self.btn_start.config(state=tk.DISABLED, text="启动中…")
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        ok = pm.start()
        if ok:
            import time
            for _ in range(15):
                time.sleep(0.5)
                if pm.is_running():
                    break
        else:
            self.root.after(0, lambda: messagebox.showwarning("提示", "助理已在运行。"))
        self.root.after(0, self._update_ui)

    def on_stop(self):
        if not messagebox.askyesno("确认", "确定停止个人助理吗？"):
            return
        self.btn_stop.config(state=tk.DISABLED, text="停止中…")
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        pm.stop()
        import time
        time.sleep(0.5)
        self.root.after(0, self._update_ui)

    def on_reconfig(self):
        """重新配置：弹出配置向导。"""
        if pm.is_running():
            messagebox.showwarning("提示", "请先停止助理，再重新配置。")
            return
        top = tk.Toplevel(self.root)
        from setup_wizard import SetupWizard
        SetupWizard(top, on_complete=lambda: None)

    # =========================================================
    # 状态刷新
    # =========================================================
    def _refresh_loop(self):
        self._update_ui()
        self.root.after(3000, self._refresh_loop)

    def _update_ui(self):
        s = pm.status()
        if s["running"]:
            self.light.config(fg="#4CAF50")
            self.status_label.config(text="运行中")
            self.info_pid.config(text=f"PID：{s['pid']}")
            self.info_uptime.config(text=f"运行时长：{s['uptime']}")
            mem = s["mem_mb"]
            self.info_mem.config(text=f"内存占用：{mem} MB" if mem else "内存占用：…")
            self.btn_start.config(state=tk.DISABLED, text="▶  启动")
            self.btn_stop.config(state=tk.NORMAL, text="■  停止")
        else:
            self.light.config(fg="#F44336")
            self.status_label.config(text="已停止")
            self.info_pid.config(text="PID：—")
            self.info_uptime.config(text="运行时长：—")
            self.info_mem.config(text="内存占用：—")
            self.btn_start.config(state=tk.NORMAL, text="▶  启动")
            self.btn_stop.config(state=tk.DISABLED, text="■  停止")


def main():
    root = tk.Tk()
    # 首次启动检测配置
    if not cl.env_is_complete():
        # 配置不完整，先弹向导
        wizard_top = tk.Toplevel(root)
        root.withdraw()  # 先隐藏主窗口
        from setup_wizard import SetupWizard
        def on_wizard_done():
            root.deiconify()  # 向导完成后显示主窗口
        wizard = SetupWizard(wizard_top, on_complete=on_wizard_done)
        wizard_top.protocol("WM_DELETE_WINDOW", lambda: (root.destroy()))
    app = ControlPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
