"""操作执行器：把 AI 返回的 intent 列表落地为数据库操作并生成回复文案。

两个 bot 共用，差异通过 caller（"xiaonao" / "xiaozhi"）区分：
- log / task_* intent 两个 bot 都执行
- observe / analyze intent 仅小知语义（小闹里被 AI 模板限制不会产生）
"""
import logging

from core import db, memory, ai
from analysis import profile

logger = logging.getLogger(__name__)


def execute_actions(actions, caller, user_text=None):
    """执行 intent 列表，返回拼接好的回复字符串。"""
    replies = []
    for act in actions:
        intent = act.get("intent", "chat")
        if intent == "log":
            replies.append(_do_log(act))
        elif intent == "task_add":
            replies.append(_do_task_add(act))
        elif intent == "task_delete":
            replies.append(_do_task_delete(act))
        elif intent == "task_update":
            replies.append(_do_task_update(act))
        elif intent == "task_query":
            replies.append(_do_task_query())
        elif intent == "goal_add":
            replies.append(_do_goal_add(act))
        elif intent == "goal_query":
            replies.append(_do_goal_query())
        elif intent == "task_uncompleted":
            replies.append(_do_uncompleted())
        elif intent == "observe":
            # 仅小知语义：记录观察 + 生成共情回复
            replies.append(_do_observe(act, caller))
        elif intent == "analyze":
            replies.append(_do_analyze(act, caller))
        elif intent == "chat":
            replies.append(act.get("reply", "嗯嗯，我在。"))
        else:
            replies.append(act.get("reply", "收到。"))

    # 记录对话记忆
    if user_text:
        memory.add_and_trim(caller, "user", user_text)
    memory.add_and_trim(caller, "assistant", "\n".join(replies))
    return "\n".join(replies) if replies else "操作完成"


# =========================================================
# 各 intent 落地
# =========================================================
def _do_log(act):
    name = ai.strip_task_suffix(act.get("task_name", "未命名任务"))
    comp = act.get("completion_rate", 100)
    focus = act.get("focus_score", 0)
    note = act.get("note", "")
    mood = act.get("mood")
    db.add_log(name, comp, focus, note=note, mood=mood)
    line = f"✅ 已记录：{name}（完成{comp}%，专注{focus}分）"
    if note:
        line += f"  备注：{note}"
    return line


def _do_task_add(act):
    name = ai.strip_task_suffix(act.get("task_name"))
    if not name:
        return "❌ 任务名不能为空"
    t = act.get("task_time")
    ttype = act.get("task_type", "fixed")
    duration = act.get("duration", 30)
    days = act.get("days_of_week", "")
    ok = db.add_task(name, ttype, time=t, duration=duration, days_of_week=days)
    return f"✅ 已添加任务：{name}" if ok else f"❌ 任务'{name}'已存在"


def _do_task_delete(act):
    name = ai.strip_task_suffix(act.get("task_name"))
    ok = db.delete_task(name)
    if not ok:
        all_tasks = db.query_tasks("active")
        matched = [t for t in all_tasks if name in t["name"]]
        if len(matched) == 1:
            ok = db.delete_task(matched[0]["name"])
            name = matched[0]["name"]
        elif len(matched) > 1:
            return (f"❌ 找到多个匹配任务："
                    f"{', '.join(t['name'] for t in matched)}，请指定具体名称")
    return f"✅ 已删除任务：{name}" if ok else f"❌ 未找到任务：{name}"


def _do_task_update(act):
    name = ai.strip_task_suffix(act.get("task_name"))
    field = act.get("field", "time")
    value = act.get("value")
    ok = db.update_task(name, field, value)
    return f"✅ 已修改 {name}" if ok else f"❌ 修改失败，可能未找到'{name}'"


def _do_task_query():
    tasks = db.query_tasks("active")
    if not tasks:
        return "📋 当前没有活跃任务"
    return _format_tasks(tasks)


def _do_goal_add(act):
    title = act.get("goal_title") or act.get("task_name")
    if not title:
        return "❌ 目标标题不能为空"
    category = act.get("category", "study")
    deadline = act.get("deadline")
    metric = act.get("success_metric")
    gid = db.add_goal(title, category=category, deadline=deadline,
                      success_metric=metric)
    return f"🎯 已添加目标：{title}（截止 {deadline or '未定'}）"


def _do_goal_query():
    goals = db.query_goals("active")
    if not goals:
        return "🎯 暂无阶段性目标，可以跟我说「加目标 …」"
    lines = ["🎯 当前目标："]
    for g in goals:
        line = f"- {g['title']}"
        if g["deadline"]:
            line += f"（截止 {g['deadline']}）"
        if g["success_metric"]:
            line += f"  衡量：{g['success_metric']}"
        lines.append(line)
    return "\n".join(lines)


def _do_uncompleted():
    today = db.today_str()
    all_today = db.query_today_tasks()
    logs = db.query_logs_by_date(today)
    done = {l["task_name"] for l in logs if l["completion_rate"] > 0}
    uncompleted = [t for t in all_today if t["name"] not in done]
    if not uncompleted:
        return "✅ 今日任务全部完成！太棒了！"
    lines = ["📋 今日未完成："]
    for t in uncompleted:
        lines.append(f"- {t['name']}")
    return "\n".join(lines)


def _do_observe(act, caller):
    """记录一条观察，返回共情回复。"""
    raw = act.get("raw_text") or act.get("reply", "")
    mood = act.get("mood")
    energy = act.get("energy")
    tags = act.get("tags", [])
    context = act.get("context")
    if raw:
        db.add_observation(raw, tags=tags, mood=mood, energy=energy,
                           context=context, source=caller)
    reply = act.get("reply", "我记下了 📝")
    return reply


def _do_analyze(act, caller):
    """触发深度分析：拉数据 + 画像 + 让 AI 拆解。"""
    topic = act.get("topic") or act.get("reply", "")
    logs = db.query_recent_logs(14)
    obs = db.query_recent_observations(14)
    profile_data, _ = profile.get_profile_context()

    log_text = "\n".join(
        f"- {l['plan_date']} {l['task_name']}: 完成{l['completion_rate']}% "
        f"专注{l['focus_score']} 备注{l.get('note') or ''}"
        for l in logs[-30:]
    ) or "（近14天无任务记录）"
    obs_text = "\n".join(
        f"- {o['created_at'][:16]} {o['raw_text']}（情绪:{o.get('mood') or '未标'}）"
        for o in obs[:20]
    ) or "（近14天无观察记录）"

    prompt = (
        f"用户想分析：{topic}\n\n"
        f"【近期任务记录】\n{log_text}\n\n"
        f"【近期用户自述观察】\n{obs_text}\n\n"
        f"【系统对用户的既有理解】\n{profile_data}\n\n"
        "请结合 实际数据 + 用户感受 双线分析，找出卡点并拆解成可执行的下一步。"
        "语气共情、具体、不说教。分段清晰，不超过 300 字。"
    )
    result = ai.call_ai(
        prompt,
        system_prompt="你是用户的人生教练，善于从行为数据和自述感受中发现卡点，"
                      "并把大问题拆成明天就能做的小步骤。",
        temperature=0.6,
    )
    return result or act.get("reply", "我先看看数据，稍等。")


# =========================================================
# 文案工具
# =========================================================
def _format_tasks(tasks, title="📋 当前任务"):
    lines = [title + "："]
    for i, t in enumerate(tasks, 1):
        tt = "固定" if t["type"] == "fixed" else "弹性"
        line = f"{i}. [{tt}] {t['name']}"
        if t.get("time"):
            line += f" - {t['time']}"
        if t.get("duration"):
            line += f" ({t['duration']}分钟)"
        if t.get("days_of_week"):
            line += f" [周{t['days_of_week']}]"
        lines.append(line)
    return "\n".join(lines)
