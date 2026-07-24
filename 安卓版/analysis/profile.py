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


def get_evolution_context():
    """返回 success_strategies / failure_triggers 的格式化文本。

    供小知 _parse 用：用更强约束的措辞注入到 system 提示词末尾，驱动
    「主动点名陷阱」和「发现新规律就 learn」的行为。任一为空时整段省略。
    """
    content, _ = db.get_profile()
    if not isinstance(content, dict):
        return ""
    strategies = content.get("success_strategies") or []
    triggers = content.get("failure_triggers") or []
    if not strategies and not triggers:
        return ""
    strategies_text = "；".join(strategies) if strategies else "（暂无）"
    triggers_text = "；".join(triggers) if triggers else "（暂无）"
    return (
        f"【已知的成功策略（高光时刻）】：{strategies_text}\n"
        f"【已知的失败陷阱（翻车时刻）】：{triggers_text}\n"
        "注意：如果用户今天又掉进上述陷阱，reply 中必须直接点名指出；"
        "如果用户今天用新的有效方法成功了，判断是否值得用 learn 意图沉淀。"
    )


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
        "  success_strategies: [对用户具体有效的成功策略，保留旧画像已有项]\n"
        "  failure_triggers: [导致用户翻车的具体情境/思维模式，保留旧画像已有项]\n"
        "  notes: 一段不超过 80 字的综合判断\n"
        "只输出 JSON，保留旧画像里仍成立的部分，根据新数据更新或新增。\n"
        "特别地：success_strategies 和 failure_triggers 要与旧画像去重合并，"
        "最多各保留 15 条最典型的，不要丢弃已有的有效沉淀。"
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

    # 合并保护：把旧画像里的 success_strategies / failure_triggers 与 AI 返回的做合并去重，
    # 防止 AI 遗漏导致已有沉淀丢失。最多各保留 15 条。
    for field in ("success_strategies", "failure_triggers"):
        old_items = old_content.get(field, []) if isinstance(old_content, dict) else []
        new_items = new_content.get(field, [])
        if not isinstance(new_items, list):
            new_items = []
        if not isinstance(old_items, list):
            old_items = []
        merged = list(old_items)
        for item in new_items:
            if item and item not in merged:
                merged.append(item)
        new_content[field] = merged[:15]

    db.save_profile(new_content)
    logger.info("用户画像已刷新")
    return new_content


def days_since_start():
    """系统积累了多少天的数据（用于决定是否开始画像刷新）。

    同时检查 logs 和 observations，避免用户只聊天不打卡时永远不刷新。
    """
    conn = db.get_conn()
    try:
        first_log = conn.execute(
            "SELECT MIN(created_at) AS first FROM logs"
        ).fetchone()["first"]
        first_obs = conn.execute(
            "SELECT MIN(created_at) AS first FROM observations"
        ).fetchone()["first"]
        first = min(
            (x for x in (first_log, first_obs) if x),
            default=None,
        )
        if not first:
            return 0
        first = first[:10]
        first_dt = datetime.strptime(first, "%Y-%m-%d")
        return max(0, (datetime.now() - first_dt).days)
    finally:
        conn.close()


# 自我进化标记，由小知 learn 意图之外的后备路径识别（AI 偶尔会把标记塞进 reply 文本）。
_UPDATE_MARKER = "<<<UPDATE>>>"


def parse_update_marker(text):
    """从文本里抽取 <<<UPDATE>>> {new_strategy, new_trigger} 指令。

    成功返回 {"new_strategy": ..., "new_trigger": ...}（值可能为 None），
    解析失败或无标记返回 None。永不抛异常，保证不影响主流程。
    """
    if not text or _UPDATE_MARKER not in text:
        return None
    try:
        update_part = text.split(_UPDATE_MARKER)[-1].strip()
        data = json.loads(update_part)
        if not isinstance(data, dict):
            return None
        return {
            "new_strategy": data.get("new_strategy"),
            "new_trigger": data.get("new_trigger"),
        }
    except (json.JSONDecodeError, ValueError):
        return None


def strip_update_marker(text):
    """剥掉 <<<UPDATE>>> 及其后的指令文本，只保留给用户看的正文。"""
    if not text or _UPDATE_MARKER not in text:
        return text
    return text.split(_UPDATE_MARKER)[0].strip()
