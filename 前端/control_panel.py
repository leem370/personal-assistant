"""个人助理控制面板（Tkinter 版）。

轻量 GUI 控制台，按需启停 main.py 子进程，不长期占用内存。
- main.py 只在点「启动」时运行，点「停止」立刻释放内存
- 控制面板本身约 30-40MB（Tkinter 原生组件）
- 关闭窗口默认最小化到 Dock（不退出控制面板），点 Dock 图标恢复
  → 如果你想要"关窗即退出"，可在菜单切换

运行：
    python3 前端/control_panel.py
或双击 启动控制台.command
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# 确保能 import 同目录的 process_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import process_manager as pm


class ControlPanel:
    def __init__(self, root):
        self.root = root
        self.close_to_dock = True  # 关窗最小化到 Dock，而非退出

        self._build_ui()
        self._refresh_loop()

    def _build_ui(self):
        self.root.title("个人助理")
        self.root.geometry("280x320")
        self.root.resizable(False, False)

        # 标题
        title = tk.Label(self.root, text="个人助理控制台",
                         font=("PingFang SC", 16, "bold"))
        title.pack(pady=(18, 10))

        # 状态灯 + 文字
        status_frame = tk.Frame(self.root)
        status_frame.pack(pady=5)
        self.light = tk.Label(status_frame, text="●", font=("Arial", 28),
                              fg="#999")
        self.light.pack(side=tk.LEFT, padx=(0, 8))
        self.status_label = tk.Label(status_frame, text="已停止",
                                     font=("PingFang SC", 13))
        self.status_label.pack(side=tk.LEFT)

        # 详细信息
        info_frame = tk.Frame(self.root)
        info_frame.pack(pady=10, padx=30, fill=tk.X)
        self.info_pid = tk.Label(info_frame, text="PID：—",
                                 font=("PingFang SC", 11), fg="#666",
                                 anchor="w", width=20)
        self.info_pid.pack(anchor="w")
        self.info_uptime = tk.Label(info_frame, text="运行时长：—",
                                    font=("PingFang SC", 11), fg="#666",
                                    anchor="w", width=20)
        self.info_uptime.pack(anchor="w")
        self.info_mem = tk.Label(info_frame, text="内存占用：—",
                                 font=("PingFang SC", 11), fg="#666",
                                 anchor="w", width=20)
        self.info_mem.pack(anchor="w")

        # 按钮区
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=18)
        self.btn_start = tk.Button(btn_frame, text="▶  启动",
                                   command=self.on_start,
                                   font=("PingFang SC", 12),
                                   width=10, height=2,
                                   bg="#4CAF50", fg="white",
                                   activebackground="#43A047",
                                   relief=tk.FLAT, cursor="hand2")
        self.btn_start.pack(side=tk.LEFT, padx=8)
        self.btn_stop = tk.Button(btn_frame, text="■  停止",
                                  command=self.on_stop,
                                  font=("PingFang SC", 12),
                                  width=10, height=2,
                                  bg="#F44336", fg="white",
                                  activebackground="#E53935",
                                  relief=tk.FLAT, cursor="hand2",
                                  state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=8)

        # 底部提示
        tip = tk.Label(self.root,
                       text="关闭窗口将最小化到 Dock",
                       font=("PingFang SC", 9), fg="#aaa")
        tip.pack(side=tk.BOTTOM, pady=8)

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =========================================================
    # 按钮事件
    # =========================================================
    def on_start(self):
        """在子线程启动，避免阻塞 UI。"""
        self.btn_start.config(state=tk.DISABLED, text="启动中…")
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        ok = pm.start()
        if ok:
            # 等 main.py 起来
            import time
            for _ in range(15):
                time.sleep(0.5)
                if pm.is_running():
                    break
        else:
            self.root.after(0, lambda: messagebox.showwarning(
                "提示", "助理已在运行，无需重复启动。"))
        self.root.after(0, self._update_ui)

    def on_stop(self):
        """在子线程停止，避免阻塞 UI。"""
        if not messagebox.askyesno("确认", "确定要停止个人助理吗？"):
            return
        self.btn_stop.config(state=tk.DISABLED, text="停止中…")
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        pm.stop()
        import time
        time.sleep(0.5)
        self.root.after(0, self._update_ui)

    def on_close(self):
        """关闭按钮：最小化到 Dock（而非退出）。"""
        if self.close_to_dock:
            self.root.iconify()  # 最小化到 Dock
        else:
            self.root.destroy()

    # =========================================================
    # 状态刷新
    # =========================================================
    def _refresh_loop(self):
        """每 3 秒刷新一次状态。"""
        self._update_ui()
        self.root.after(3000, self._refresh_loop)

    def _update_ui(self):
        s = pm.status()
        if s["running"]:
            self.light.config(fg="#4CAF50")  # 绿灯
            self.status_label.config(text="运行中")
            self.info_pid.config(text=f"PID：{s['pid']}")
            self.info_uptime.config(text=f"运行时长：{s['uptime']}")
            mem = s["mem_mb"]
            self.info_mem.config(text=f"内存占用：{mem} MB" if mem else "内存占用：…")
            self.btn_start.config(state=tk.DISABLED, text="▶  启动")
            self.btn_stop.config(state=tk.NORMAL, text="■  停止")
        else:
            self.light.config(fg="#F44336")  # 红灯
            self.status_label.config(text="已停止")
            self.info_pid.config(text="PID：—")
            self.info_uptime.config(text="运行时长：—")
            self.info_mem.config(text="内存占用：—")
            self.btn_start.config(state=tk.NORMAL, text="▶  启动")
            self.btn_stop.config(state=tk.DISABLED, text="■  停止")


def main():
    root = tk.Tk()
    app = ControlPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
