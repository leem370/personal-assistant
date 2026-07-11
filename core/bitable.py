"""飞书多维表格同步：本地 SQLite → 多维表格（单向，实时）。

设计要点：
- 异步推送：本地写入后开一个 daemon 线程推送，不阻塞机器人回复。
- 失败静默：同步失败只记日志，不影响本地写入和用户体验（本地是权威源）。
- 字段名映射：本地字段名 → 多维表格字段名（见 _FIELD_MAP）。
  建多维表格时务必按 core/bitable.py 顶部的字段名建，否则映射不上。
- 日期时间字段：飞书要求毫秒时间戳，本模块统一转换。

只暴露 4 个函数给 db.py 调用：
  sync_log / sync_observation / sync_task / sync_goal
"""
import time
import logging
import threading
import requests
from datetime import datetime

from core import config

logger = logging.getLogger(__name__)

# =========================================================
# 多维表格字段定义（建表时务必与此一致）
# 字段名 = 多维表格表头名（中文），value 是飞书字段写入格式提示
# =========================================================
TABLES = {
    "log":         {"name": "任务完成记录", "fields": [
        "任务名", "完成度", "专注分", "情绪", "备注", "日期", "记录时间"]},
    "observation": {"name": "观察记录", "fields": [
        "内容", "情绪", "能量", "标签", "场景", "来源", "时间"]},
    "task":        {"name": "任务清单", "fields": [
        "任务名", "类型", "时间", "时长", "周几", "状态"]},
    "goal":        {"name": "目标", "fields": [
        "目标", "类别", "截止日期", "衡量标准", "状态"]},
}

# 状态/类型枚举映射（本地值 → 多维表格选项名）
_STATUS_MAP_TASK = {"active": "活跃", "done": "完成", "canceled": "取消"}
_STATUS_MAP_GOAL = {"active": "进行中", "achieved": "达成", "paused": "暂停"}
_TYPE_MAP = {"fixed": "固定", "flexible": "弹性"}

_token_cache = {}  # app_id -> {"token": str, "ts": float}


def _enabled():
    """多维表格同步是否启用（配置齐全才算启用）。"""
    b = config.get().get("bitable", {})
    return bool(b.get("app_id") and b.get("app_secret") and b.get("app_token"))


def _get_token():
    b = config.get()["bitable"]
    app_id, app_secret = b["app_id"], b["app_secret"]
    cached = _token_cache.get(app_id)
    if cached and time.time() - cached["ts"] < 7100:
        return cached["token"]
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret}, timeout=10)
        data = r.json()
    except Exception as e:
        logger.error("多维表格 token 获取失败: %s", e)
        return None
    if data.get("code") == 0:
        token = data["tenant_access_token"]
        _token_cache[app_id] = {"token": token, "ts": time.time()}
        return token
    logger.error("多维表格 token 获取失败: %s", data.get("msg"))
    return None


def _table_id(key):
    return config.get()["bitable"]["table_ids"][key]


def _to_timestamp_ms(date_str):
    """本地日期/日期时间字符串 → 飞书毫秒时间戳。"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(date_str, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def _create_record(table_key, fields_dict):
    """往指定表插入一行。fields_dict 的 key 必须是多维表格字段名。"""
    if not _enabled():
        return False
    token = _get_token()
    if not token:
        return False
    b = config.get()["bitable"]
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{b['app_token']}/tables/{_table_id(table_key)}/records"
    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"fields": {k: v for k, v in fields_dict.items() if v is not None}},
            timeout=10)
        data = r.json()
    except Exception as e:
        logger.warning("多维表格写入失败[%s]: %s", table_key, e)
        return False
    if data.get("code") != 0:
        logger.warning("多维表格写入失败[%s]: %s", table_key, data.get("msg"))
        return False
    return True


def _async(fn):
    """装饰器：把同步函数丢到 daemon 线程异步执行，不阻塞调用方。"""
    def wrapper(*args, **kwargs):
        if not _enabled():
            return
        t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        t.start()
    return wrapper


# =========================================================
# 4 个对外同步函数（被 db.py 调用）
# =========================================================
@_async
def sync_log(task_name, completion_rate, focus_score, mood, note,
             plan_date, created_at):
    fields = {
        "任务名": task_name,
        "完成度": int(completion_rate) if completion_rate is not None else None,
        "专注分": int(focus_score) if focus_score is not None else None,
        "情绪": mood or None,
        "备注": note or None,
        "日期": _to_timestamp_ms(plan_date),
        "记录时间": _to_timestamp_ms(created_at),
    }
    _create_record("log", fields)


@_async
def sync_observation(raw_text, mood, energy, tags, context, source, created_at):
    fields = {
        "内容": raw_text,
        "情绪": mood or None,
        "能量": int(energy) if energy is not None else None,
        "标签": tags if tags else None,
        "场景": context or None,
        "来源": source or None,
        "时间": _to_timestamp_ms(created_at),
    }
    _create_record("observation", fields)


@_async
def sync_task(name, task_type, time_str, duration, days_of_week, status):
    fields = {
        "任务名": name,
        "类型": _TYPE_MAP.get(task_type, task_type),
        "时间": time_str or None,
        "时长": int(duration) if duration is not None else None,
        "周几": [d.strip() for d in days_of_week.split(",") if d.strip()]
               if days_of_week else None,
        "状态": _STATUS_MAP_TASK.get(status, status),
    }
    _create_record("task", fields)


@_async
def sync_goal(title, category, deadline, success_metric, status):
    fields = {
        "目标": title,
        "类别": category or None,
        "截止日期": _to_timestamp_ms(deadline) if deadline else None,
        "衡量标准": success_metric or None,
        "状态": _STATUS_MAP_GOAL.get(status, status),
    }
    _create_record("goal", fields)
