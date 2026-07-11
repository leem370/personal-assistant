"""用户画像：系统对用户的结构化理解，由小知定期刷新，永久保留。

content 是 AI 维护的 JSON，字段：
  sleep: {bedtime, wake}
  peak_hours: ["09:00-11:00", ...]
  low_energy: ["14:00-15:30", ...]
  often_procrastinated: [...]
  mood_triggers: {事件: 情绪}
  effective_techniques: [...]
  notes: 自由文本
"""
import json
import logging
from datetime import datetime, timedelta

from core import db, ai, config

logger = logging.getLogger(__name__)


def get_profile_context():
    """返回 (profile 文本, updated_at)。给小知注入上下文用。"""
    content, updated = db.get_profile()
    if not content or content == {}:
        return "", updated
    try:
        return json.dumps(content, ensure_ascii=False, indent=2), updated
    except Exception:
        return str(content), updated


def refresh_profile():
    """拉近 14 天 logs + observations + 旧画像，让 AI 输出新版结构化 JSON 写回。

    数据不足（观察 < 5 条）时跳过，避免无米之炊。
    """
    logs = db.query_recent_logs(14)
    obs = db.query_recent_observations(14)
    if len(obs) < 5 and len(logs) < 7:
        logger.info("画像刷新跳过：数据不足（obs=%d logs=%d）", len(obs), len(logs))
        return None

    old_content, _ = db.get_profile()

    log_text = "\n".join(
        f"- {l['plan_date']} {l['task_name']}: 完成{l['completion_rate']}% "
        f"专注{l['focus_score']} 情绪{l.get('mood') or '-'} 备注{l.get('note') or ''}"
        for l in logs
    )[:2000]
    obs_text = "\n".join(
        f"- {o['created_at'][:10]} {o['raw_text']} "
        f"（情绪:{o.get('mood') or '-'} 能量:{o.get('energy') or '-'}）"
        for o in obs
    )[:2000]
    old_text = json.dumps(old_content, ensure_ascii=False) if old_content else "{}"

    system = (
        "你是用户的行为分析师。基于近 14 天的任务记录和用户自述，"
        "输出对用户的结构化理解（JSON 对象）。字段：\n"
        "  sleep: {bedtime, wake}（作息，可空）\n"
        "  peak_hours: [高效时段]\n"
        "  low_energy: [低能量时段]\n"
        "  often_procrastinated: [常被拖的任务或事]\n"
        "  mood_triggers: {事件: 情绪影响}\n"
        "  effective_techniques: [对用户有效的做法]\n"
        "  notes: 一段不超过 80 字的综合判断\n"
        "只输出 JSON，保留旧画像里仍成立的部分，根据新数据更新或新增。"
    )
    prompt = (
        f"【旧画像】\n{old_text}\n\n"
        f"【近14天任务记录】\n{log_text}\n\n"
        f"【近14天用户自述】\n{obs_text}\n\n请输出新版画像 JSON。"
    )
    new_content = ai.call_ai_json(prompt, system_prompt=system, temperature=0.3)
    if not new_content or not isinstance(new_content, dict):
        logger.warning("画像刷新：AI 未返回有效 JSON")
        return None

    db.save_profile(new_content)
    logger.info("用户画像已刷新")
    return new_content


def days_since_start():
    """系统积累了多少天的数据（用于决定是否开始画像刷新）。"""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT MIN(created_at) AS first FROM logs"
        ).fetchone()
        if not row or not row["first"]:
            return 0
        first = datetime.strptime(row["first"][:10], "%Y-%m-%d")
        return max(0, (datetime.now() - first).days)
    finally:
        conn.close()
