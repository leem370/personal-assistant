"""定时任务调度。

每个定时任务都注册到一个统一入口，便于在 main.py 里启一个线程跑 run_pending()。
具体任务函数定义在 bots/ 和 analysis/ 里，这里只负责装配。
"""
import time
import logging
import threading
import schedule

from core import config

logger = logging.getLogger(__name__)

_setup_done = False
_run_flag = threading.Event()


def setup(jobs):
    """注册定时任务。

    jobs: list of dict，每个形如：
        {"when": schedule.every().day.at("09:00"), "task": callable, "name": "早间提醒"}
    本函数会确保只装配一次。
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True
    for j in jobs:
        j["when"].do(_safe_run, j["task"], j.get("name", j["task"].__name__))
    logger.info("已注册 %d 个定时任务", len(jobs))


def _safe_run(task, name):
    try:
        task()
    except Exception as e:
        logger.error("定时任务 [%s] 异常: %s", name, e, exc_info=True)


def run_forever():
    """阻塞线程：每秒检查一次到点任务。"""
    _run_flag.set()
    while _run_flag.is_set():
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error("调度循环异常: %s", e)
        time.sleep(1)


def stop():
    _run_flag.clear()


def default_jobs_from_config():
    """从 config.schedules() 构造定时任务清单（时间来自配置）。

    任务函数引用放在装配阶段做，避免循环导入：在 main.py 里先 import 好任务函数，
    再调用 setup(default_jobs_from_config())。
    """
    from bots import xiaonao, xiaozhi
    from analysis import reflect, archive
    from datetime import datetime

    s = config.schedules()
    return [
        {"when": schedule.every().day.at(s.get("morning_reminder", "09:00")),
         "task": xiaonao.morning_plan, "name": "早间plan"},
        {"when": schedule.every().day.at(s.get("night_check", "21:00")),
         "task": xiaonao.night_check, "name": "晚间check"},
        {"when": schedule.every().day.at(s.get("daily_summary", "22:00")),
         "task": xiaozhi.daily_reflection, "name": "日终反思"},
        {"when": schedule.every().day.at("22:30"),
         "task": reflect.weekly_profile_refresh_if_due, "name": "画像周刷新"},
        {"when": schedule.every().sunday.at(s.get("weekly_report", "23:00")),
         "task": xiaozhi.weekly_report, "name": "周报"},
        {"when": schedule.every().day.at(s.get("archive", "03:00")),
         "task": archive.run_archive, "name": "数据归档清理"},
    ]


def fitness_jobs_from_config():
    """健身提醒（周一、周四），独立出来因为 schedule API 不同。"""
    from bots import xiaonao
    s = config.schedules()
    jobs = []
    # 用闭包包装 send_to_group 以保持任务签名一致
    jobs.append({
        "when": schedule.every().monday.at(s.get("fitness_reminder_monday", "16:00")),
        "task": xiaonao.fitness_reminder, "name": "健身提醒(周一)",
    })
    jobs.append({
        "when": schedule.every().thursday.at(s.get("fitness_reminder_thursday", "16:00")),
        "task": xiaonao.fitness_reminder, "name": "健身提醒(周四)",
    })
    return jobs
