"""配置加载：config.yaml 为基础，环境变量覆盖敏感字段。"""
import os
import yaml
import logging

logger = logging.getLogger(__name__)

CONFIG = {}

# 默认配置：用于补全缺失的必填项
_DEFAULT_CONFIG = {
    "system": {
        "enable_ai": False,
        "db_path": "./data/personal_assistant.db",
    },
    "ai": {
        "api_key": "",
        "api_base": "",
        "model_name": "gpt-4o-mini",
    },
    "schedules": {
        "morning_reminder": "09:00",
        "night_check": "21:00",
        "daily_summary": "22:00",
        "weekly_report": "23:00",
        "archive": "03:00",
        "fitness_reminder_monday": "16:00",
        "fitness_reminder_thursday": "16:00",
    },
    "tasks": {"fixed": []},
}


def _deep_merge(base, override):
    """递归合并配置，override 为空时保留 base。"""
    if not isinstance(override, dict):
        return base
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path="config.yaml"):
    """加载配置文件，并用环境变量覆盖 AI 敏感字段。

    安卓版不需要飞书，只保留 AI 相关配置覆盖：
      - AI_API_KEY / AI_API_BASE / AI_MODEL
    """
    global CONFIG
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    CONFIG = _deep_merge(_DEFAULT_CONFIG, raw)

    ai = CONFIG.setdefault("ai", {})
    if os.getenv("AI_API_KEY"):
        ai["api_key"] = os.getenv("AI_API_KEY")
    if os.getenv("AI_API_BASE"):
        ai["api_base"] = os.getenv("AI_API_BASE")
    if os.getenv("AI_MODEL"):
        ai["model_name"] = os.getenv("AI_MODEL")

    logger.info("配置加载完成: %s", list(CONFIG.keys()))
    return CONFIG


def get():
    return CONFIG


# ---------- 便捷访问 ----------
def ai_enabled():
    return CONFIG.get("system", {}).get("enable_ai", False)


def schedules():
    return CONFIG.get("schedules", {})


def db_path():
    return CONFIG.get("system", {}).get("db_path", "./data/personal_assistant.db")
