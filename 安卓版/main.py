"""安卓版个人助理入口。

使用 Kivy + KivyMD 构建 Material Design 界面。
核心逻辑从本地 core/、bots/、analysis/ 模块导入。
全局异常捕获，崩溃日志写入可写目录。
"""
import os
import sys
import traceback
import logging
import threading
from datetime import datetime

# 日志配置：必须在其他模块 import 前设置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp

from core import db, config as core_config
from core import scheduler
from bots import xiaonao, xiaozhi
from analysis import reflect, archive
from ui.screens import TodayScreen, AddTaskScreen, CompleteScreen

logger = logging.getLogger("main")


# =========================================================
# .env 加载（不依赖 python-dotenv，避免新增依赖）
# =========================================================
def _load_dotenv_if_any():
    """轻量 .env 加载：把 KEY=VALUE 写入环境变量（不覆盖已有的）。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


# =========================================================
# 全局异常捕获：崩溃日志写入可写目录
# =========================================================
def _get_crash_log_path():
    """获取崩溃日志文件路径。

    Android: ~/PersonalAssistant/crash.log（~ 自动指向 app 私有存储）
    桌面测试: ~/PersonalAssistant/crash.log
    """
    base = os.path.expanduser("~")
    crash_dir = os.path.join(base, "PersonalAssistant")
    os.makedirs(crash_dir, exist_ok=True)
    return os.path.join(crash_dir, "crash.log")


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """全局未捕获异常处理：写崩溃日志 + 调用原始 handler。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log_line = f"\n{'='*60}\n[{timestamp}] FATAL CRASH\n{tb_text}\n"

    try:
        log_path = _get_crash_log_path()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
        logger.critical("崩溃日志已写入: %s", log_path)
    except Exception as e:
        logger.critical("写入崩溃日志失败: %s", e)

    # 调用原始 handler（让程序正常崩溃退出）
    if _original_excepthook:
        _original_excepthook(exc_type, exc_value, exc_tb)


_original_excepthook = sys.excepthook
sys.excepthook = _global_exception_handler


class PersonalAssistantApp(MDApp):
    """安卓版个人助理 App。"""

    def build(self):
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"

        # 加载 .env
        _load_dotenv_if_any()

        # 确定可写数据目录（桌面测试用项目目录，Android用user_data_dir）
        app_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(app_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        # 加载配置
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        core_config.load_config(config_path)

        # 覆盖数据库路径为可写目录
        db_path = os.path.join(data_dir, "personal_assistant.db")
        core_config.get().setdefault("system", {})["db_path"] = db_path
        logger.info("数据库路径: %s", db_path)

        # 初始化数据库
        db.init_db()

        # 启动定时任务调度线程
        jobs = scheduler.default_jobs_from_config() + scheduler.fitness_jobs_from_config()
        scheduler.setup(jobs)
        threading.Thread(target=scheduler.run_forever, daemon=True).start()
        logger.info("定时任务调度已启动")

        # 创建页面管理器
        sm = ScreenManager()
        sm.add_widget(TodayScreen())
        sm.add_widget(AddTaskScreen())
        sm.add_widget(CompleteScreen())

        return sm

    def on_start(self):
        logger.info("个人助理安卓版启动")


if __name__ == "__main__":
    PersonalAssistantApp().run()