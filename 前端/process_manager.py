"""进程管理器：纯外部控制 main.py 子进程，不依赖 main.py 配合。

所有方法都是静态的，可独立 import 测试，不依赖 rumps。
找进程用 pgrep（不依赖 PID 文件），所以后端 main.py 不需要任何改动。
"""
import os
import sys
import time
import signal
import subprocess

# 后端 main.py 的绝对路径（前端目录的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(ROOT, "main.py")
PYTHON = sys.executable  # 用当前解释器，保证依赖一致


def find_pid():
    """找到正在运行的 main.py 进程 PID，没有返回 None。

    用 main.py 的绝对路径作为特征匹配，避免误杀其它同名进程。
    """
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,command="], stderr=subprocess.DEVNULL
        ).decode()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # 特征：命令行包含 main.py 的绝对路径，且是 python 进程
    needle = MAIN_PY
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if needle in line and "python" in line.lower():
            # 排除 grep/pgrep 自身（虽然 ps 不会列自己，保险起见）
            if "grep" in line:
                continue
            try:
                return int(line.split()[0])
            except (ValueError, IndexError):
                continue
    return None


def is_running():
    return find_pid() is not None


def start():
    """后台启动 main.py。已运行则返回 False。"""
    if is_running():
        return False
    try:
        # 用 setsid 脱离父进程会话，托盘退出时 main.py 不被牵连
        subprocess.Popen(
            [PYTHON, MAIN_PY],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # POSIX: 等价于 setsid
        )
        return True
    except Exception as e:
        print(f"启动失败: {e}")
        return False


def stop(timeout=8):
    """优雅停止 main.py：先 SIGTERM，timeout 秒不退再 SIGKILL。返回是否成功。

    判定成功的标准是「停止后 find_pid() 找不到」，比 _pid_alive 更可靠，
    因为 macOS 下僵尸进程会骗过 os.kill(pid, 0)。
    """
    pid = find_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True  # 已经不在了
    # 用 find_pid() 轮询，比 _pid_alive 可靠
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not find_pid():
            return True
        time.sleep(0.4)
    # 还没退，强杀
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    time.sleep(0.5)
    return not find_pid()
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return not _pid_alive(pid)


def status():
    """返回状态字典：running, pid, uptime_str, mem_mb。"""
    pid = find_pid()
    if not pid:
        return {"running": False, "pid": None, "uptime": "", "mem_mb": 0}
    uptime, mem = _proc_info(pid)
    return {
        "running": True,
        "pid": pid,
        "uptime": _fmt_duration(uptime),
        "mem_mb": mem,
    }


# =========================================================
# 内部工具
# =========================================================
def _pid_alive(pid):
    try:
        os.kill(pid, 0)  # signal 0 = 探测不真发信号
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _proc_info(pid):
    """用 ps 取运行时长（秒）和内存（MB）。失败返回 (0, 0)。"""
    try:
        # macOS ps 语法：-o 后面用逗号分隔字段，= 去表头
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "etime=,rss="],
            stderr=subprocess.DEVNULL,
        ).decode().strip().split()
        if len(out) >= 2:
            return _parse_etime(out[0]), int(out[1]) // 1024
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        pass
    return 0, 0


def _parse_etime(s):
    """解析 ps etime 格式：[[dd-]hh:]mm:ss → 秒。"""
    secs = 0
    days = hours = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = s.split(":")
    parts = [int(p) for p in parts]
    if len(parts) == 3:
        hours, mins, sec = parts
    elif len(parts) == 2:
        hours, mins, sec = 0, parts[0], parts[1]
    else:
        hours, mins, sec = 0, 0, parts[0]
    return days * 86400 + hours * 3600 + mins * 60 + sec


def _fmt_duration(seconds):
    """秒 → '2小时15分' / '3分' / '45秒'。"""
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分"
    h, m = seconds // 3600, (seconds % 3600) // 60
    return f"{h}小时{m}分"
