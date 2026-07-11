"""配置加载：config.yaml 为基础，环境变量覆盖敏感字段。"""
import os
import yaml
import logging

logger = logging.getLogger(__name__)

CONFIG = {}


def load_config(config_path="config.yaml"):
    """加载配置文件，并用环境变量覆盖敏感字段。

    敏感字段覆盖规则（环境变量优先于 yaml）：
      - FEISHU_XIAONAO_APP_ID / FEISHU_XIAONAO_SECRET
      - FEISHU_XIAOZHI_APP_ID / FEISHU_XIAOZHI_SECRET
      - AI_API_KEY / AI_API_BASE / AI_MODEL
      - FEISHU_CHAT_ID
    """
    global CONFIG
    with open(config_path, "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f) or {}

    feishu = CONFIG.setdefault("feishu_apps", {})
    for app_key in ("xiaonao", "xiaozhi"):
        app = feishu.setdefault(app_key, {})
        env_prefix = f"FEISHU_{app_key.upper()}"
        for field, env_suffix in (("app_id", "APP_ID"), ("app_secret", "SECRET")):
            env_val = os.getenv(f"{env_prefix}_{env_suffix}")
            if env_val:
                app[field] = env_val

    ai = CONFIG.setdefault("ai", {})
    if os.getenv("AI_API_KEY"):
        ai["api_key"] = os.getenv("AI_API_KEY")
    if os.getenv("AI_API_BASE"):
        ai["api_base"] = os.getenv("AI_API_BASE")
    if os.getenv("AI_MODEL"):
        ai["model_name"] = os.getenv("AI_MODEL")

    group = CONFIG.setdefault("group", {})
    if os.getenv("FEISHU_CHAT_ID"):
        group["chat_id"] = os.getenv("FEISHU_CHAT_ID")

    # 多维表格同步应用（史官）配置
    bitable = CONFIG.setdefault("bitable", {})
    if os.getenv("BITABLE_APP_ID"):
        bitable["app_id"] = os.getenv("BITABLE_APP_ID")
    if os.getenv("BITABLE_APP_SECRET"):
        bitable["app_secret"] = os.getenv("BITABLE_APP_SECRET")
    if os.getenv("BITABLE_APP_TOKEN"):
        bitable["app_token"] = os.getenv("BITABLE_APP_TOKEN")
    # table_ids 是 dict，用 JSON 串传，如：{"log":"tblXXX","observation":"tblYYY",...}
    if os.getenv("BITABLE_TABLE_IDS"):
        import json as _json
        try:
            bitable["table_ids"] = _json.loads(os.getenv("BITABLE_TABLE_IDS"))
        except (ValueError, TypeError):
            logger.warning("BITABLE_TABLE_IDS JSON 解析失败，已忽略")

    logger.info("配置加载完成: %s", list(CONFIG.keys()))
    return CONFIG


def get():
    return CONFIG


# ---------- 便捷访问 ----------
def feishu_app(app_name):
    return CONFIG["feishu_apps"][app_name]


def chat_id():
    return CONFIG["group"]["chat_id"]


def ai_enabled():
    return CONFIG.get("system", {}).get("enable_ai", False)


def schedules():
    return CONFIG.get("schedules", {})


def db_path():
    return CONFIG.get("system", {}).get("db_path", "./data/habit_tracker.db")
