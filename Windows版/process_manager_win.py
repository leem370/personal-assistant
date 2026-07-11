"""跨平台进程管理器（Windows + macOS 通用）。

与 前端/process_manager.py 功能等价，但用 psutil 替代 Unix 专用的 pgrep/ps/signal，
使其在 Windows 上也能工作。

设计原则：不改后端 main.py。通过设置子进程的工作目录(cwd)到用户数据目录，
让 main.py 里的相对路径（config.yaml / .env / habit_tracker.log / ./data/）
自然落在用户数据目录下。
"""
import os
import sys
import time
import signal
import subprocess

import psutil


def _resolve_root():
    """解析项目根目录（含 main.py / core / bots / analysis）。

    两种环境：
    1. 开发环境：__file__ 在 Windows版/ 下，根目录是上一级
    2. PyInstaller 打包环境：后端代码被解压到 sys._MEIPASS（onedir 下是 exe 同级目录）
    """
    # PyInstaller onedir 模式：sys._MEIPASS 指向 exe 同级目录（COLLECT 目录）
    if hasattr(sys, "_MEIPASS"):
        meipass = sys._MEIPASS
        if os.path.isfile(os.path.join(meipass, "main.py")):
            return meipass
    # 开发环境：Windows版/app.py → 上一级是项目根
    dev_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(dev_root, "main.py")):
        return dev_root
    # 兜底
    return dev_root


# 后端 main.py 的绝对路径
ROOT = _resolve_root()
MAIN_PY = os.path.join(ROOT, "main.py")
PYTHON = sys.executable  # 打包后是内嵌解释器；开发时是当前 python

# 用户数据目录：所有配置/数据库/日志都放这里，升级 app 不丢数据
DATA_DIR = os.path.join(os.path.expanduser("~"), "个人助理数据")


def ensure_data_dir():
    """确保用户数据目录存在。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR


def find_pid():
    """找到正在运行的 main.py 进程 PID，没有返回 None。

    用 psutil 遍历进程，匹配命令行包含 main.py 绝对路径的 python 进程。
    跨平台：psutil 在 Windows/macOS/Linux 行为一致。
    """
    needle = MAIN_PY
    myself = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            if proc.info["pid"] == myself:
                continue
            cmdline = " ".join(proc.info["cmdline"] or [])
            if needle in cmdline and "python" in (cmdline + proc.info.get("name", "")).lower():
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_running():
    return find_pid() is not None


def start():
    """后台启动 main.py，工作目录设为用户数据目录。

    把 cwd 设为 DATA_DIR 是关键：这样 main.py 里的相对路径
    (config.yaml / .env / habit_tracker.log / ./data/) 全部落在用户数据目录，
    不需要改 main.py 一行代码。
    """
    if is_running():
        return False
    ensure_data_dir()
    try:
        # 平台分支：Windows 用 CREATE_NEW_PROCESS_GROUP，Unix 用 start_new_session
        kwargs = dict(
            cwd=DATA_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([PYTHON, MAIN_PY], **kwargs)
        return True
    except Exception as e:
        print(f"启动失败: {e}")
        return False


def stop(timeout=8):
    """优雅停止 main.py：先 terminate，timeout 秒不退再 kill。

    用 psutil 统一处理，跨平台：
      - Windows: terminate() 发送 CTRL_BREAK_EVENT 的等价；kill() 强杀
      - macOS:   terminate() 发 SIGTERM；kill() 发 SIGKILL
    """
    pid = find_pid()
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True

    try:
        proc.terminate()  # 优雅停止（跨平台）
    except psutil.AccessDenied:
        return False

    # 等待退出
    try:
        proc.wait(timeout=timeout)
        return True
    except psutil.TimeoutExpired:
        pass

    # 还没退，强杀
    try:
        proc.kill()
        proc.wait(timeout=3)
        return True
    except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
        return not _pid_exists(pid)


def status():
    """返回状态字典：running, pid, uptime_str, mem_mb。"""
    pid = find_pid()
    if not pid:
        return {"running": False, "pid": None, "uptime": "", "mem_mb": 0}
    try:
        proc = psutil.Process(pid)
        # 运行时长
        create_time = proc.create_time()
        uptime_sec = int(time.time() - create_time)
        # 内存（MB）
        mem_mb = int(proc.memory_info().rss / 1024 / 1024)
        return {
            "running": True,
            "pid": pid,
            "uptime": _fmt_duration(uptime_sec),
            "mem_mb": mem_mb,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {"running": False, "pid": None, "uptime": "", "mem_mb": 0}


# =========================================================
# 内部工具
# =========================================================
def _pid_exists(pid):
    try:
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _fmt_duration(seconds):
    """秒 → '2小时15分' / '3分' / '45秒'。"""
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分"
    h, m = seconds // 3600, (seconds % 3600) // 60
    return f"{h}小时{m}分"
