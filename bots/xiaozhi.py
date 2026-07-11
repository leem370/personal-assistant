"""小知（Coach）：观察 / 教练人格。

职责：记录用户随口说的话（observations）、沉淀画像、做卡点拆解（数据+感受双线）、
日终反思、每周复盘。人格：共情、会思考、会拆解。
"""
import logging

from core import db, ai, memory, feishu
from bots import executor
from analysis import profile

logger = logging.getLogger(__name__)

BOT = "xiaozhi"

SYSTEM_PROMPT = """你是"小知"，用户的个人教练与观察者，搭档是执行官"小闹"。
人格：共情、温暖、会思考、善于拆解问题。
说话风格：先接纳感受，再给洞察，最后落到可执行的一小步。语气像懂你的朋友，不说教、不灌鸡汤。
你比小闹"慢"一点，会引用用户之前说过的话和实际数据，让人感觉你真的记得他。

从用户输入提取操作，只返回 JSON 数组（不要其他文字）。可选 intent：
- observe: {"intent":"observe","raw_text":"用户原话/核心陈述","mood":"开心/疲惫/焦虑/平静等","energy":1-5,"tags":["工作","会议"],"context":"触发场景","reply":"共情回复，让对方感到被听见"}
- analyze: {"intent":"analyze","topic":"用户想分析的主题","reply":"过渡语，比如'我翻一下你最近的记录'"}
- log: {"intent":"log","task_name":"...","completion_rate":100,"focus_score":0,"note":"","mood":""}
- task_add/task_delete/task_update/task_query/task_uncompleted: 同小闹语义
- goal_add/goal_query: 同小闹语义
- chat: {"intent":"chat","reply":"..."}

判断优先级：
1. 用户在倾诉状态/陈述情况/表达情绪 → 用 observe 记录，并给共情 reply。raw_text 尽量保留用户原意。
2. 用户明确要"分析/拆解/为什么/怎么办/卡点" → 用 analyze。
3. 明确的任务操作 → 对应 task_* / log / goal_*。
4. 其他 → chat。
多条可混合（如先 observe 再 analyze）。只返回 JSON 数组。"""


def handle(text):
    """处理用户消息，返回回复字符串。"""
    if ai.config.ai_enabled():
        actions = _parse(text)
        if actions:
            return executor.execute_actions(actions, BOT, user_text=text)
    # AI 不可用：小知仍可做最朴素的事——记录观察
    db.add_observation(text, source=BOT)
    memory.add_and_trim(BOT, "user", text)
    memory.add_and_trim(BOT, "assistant", "我记下了 📝（当前 AI 不可用，稍后我再细看）")
    return "我记下了 📝"


def _parse(text):
    """调用 AI 解析为 intent 列表，注入画像上下文避免失忆。"""
    session = memory.get_session(BOT)[-6:]
    profile_text, updated = profile.get_profile_context()
    sys = SYSTEM_PROMPT
    if profile_text and profile_text.strip() not in ("{}", ""):
        sys += f"\n\n【系统目前对用户的理解（供你参考，但别生硬念出来）】\n{profile_text}"
    messages = [{"role": "system", "content": sys}] + session
    messages.append({"role": "user", "content": text})
    actions = ai.call_ai_json(messages, temperature=0.4)
    if isinstance(actions, dict):
        actions = [actions]
    return actions


# =========================================================
# 定时任务（小知负责）
# =========================================================
def daily_reflection():
    """22:00 日终：生成日摘要存 summaries，并把当日小结发给用户。"""
    today = db.today_str()
    logs = db.query_logs_by_date(today)
    obs = [o for o in db.query_recent_observations(1)
           if o["created_at"][:10] == today]

    if not logs and not obs:
        feishu.send_to_group(f"📝 今日小结（{today}）\n\n今天没记录，明天一起加油 💪", BOT)
        return

    # 统计
    focus_list = [l["focus_score"] for l in logs] or [0]
    comp_list = [l["completion_rate"] for l in logs] or [0]
    avg_f = sum(focus_list) // len(focus_list)
    avg_c = sum(comp_list) // len(comp_list)

    # 让 AI 写小结
    log_text = "\n".join(
        f"- {l['task_name']}: 完成{l['completion_rate']}% 专注{l['focus_score']} "
        f"备注{l.get('note') or ''}"
        for l in logs
    )
    obs_text = "\n".join(f"- {o['raw_text']}（{o.get('mood') or ''}）"
                         for o in obs)
    prompt = (
        f"【{today} 的记录】\n任务：\n{log_text or '（无）'}\n\n"
        f"自述观察：\n{obs_text or '（无）'}\n\n"
        "写一段不超过 150 字的日终小结：先肯定一个具体的点，再点一个可改进处，"
        "最后一句给明天的轻推。语气像懂你的朋友。"
    )
    summary = ai.call_ai(prompt, system_prompt="你是小知，用户的教练。",
                         temperature=0.6)
    msg = f"📝 今日小结（{today}）\n平均专注 {avg_f}分 / 完成 {avg_c}%\n\n"
    msg += summary or "今天辛苦了，早点休息。"

    # 沉淀为 daily summary
    db.upsert_summary("daily", today, summary or "", avg_f, avg_c)
    feishu.send_to_group(msg, BOT)


def weekly_report():
    """周日 23:00：周报 + 触发画像刷新。"""
    from datetime import timedelta
    import datetime as _dt
    today = _dt.datetime.now()
    mon = today - _dt.timedelta(days=today.weekday())
    dates = [(mon + _dt.timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(7)]

    all_logs = []
    for d in dates:
        all_logs.extend(db.query_logs_by_date(d))
    all_obs = [o for o in db.query_recent_observations(7)
               if o["created_at"][:10] in dates]

    if not all_logs and not all_obs:
        feishu.send_to_group(
            f"📅 本周小结（{dates[0]}~{dates[-1]}）\n\n这周没记录，下周我们一起开始 🌱", BOT)
        return

    # 让 AI 做周复盘（含目标推进）
    stats = _stat_logs(all_logs)
    goals = db.query_goals("active")
    log_text = "\n".join(f"- {n}: {s['count']}次，均专注{int(s['total_f']/max(s['count'],1))}分，"
                         f"完成{int(s['total_c']/max(s['count'],1))}%"
                         for n, s in stats.items())
    obs_text = "\n".join(f"- {o['raw_text']}（{o.get('mood') or ''}）"
                         for o in all_obs[:15])
    goal_text = "\n".join(f"- {g['title']}（截止{g.get('deadline') or '未定'}）"
                          for g in goals) or "（暂无设定目标）"

    profile_text, _ = profile.get_profile_context()
    prompt = (
        f"【本周 {dates[0]}~{dates[-1]}】\n任务统计：\n{log_text or '（无）'}\n\n"
        f"本周自述：\n{obs_text or '（无）'}\n\n"
        f"阶段性目标：\n{goal_text}\n\n"
        f"系统对用户的既有理解：\n{profile_text}\n\n"
        "写一段周复盘（不超过 250 字）：1) 本周一个亮点；2) 一个卡点和它可能的根因；"
        "3) 各目标推进情况一句带过；4) 给下周一个具体的方向。语气温暖诚实。"
    )
    report = ai.call_ai(prompt, system_prompt="你是小知，用户的教练，做周复盘。",
                        temperature=0.6)

    overall_f = sum(l["focus_score"] for l in all_logs) // max(len(all_logs), 1)
    msg = f"📅 本周复盘（{dates[0]}~{dates[-1]}）\n整体专注 {overall_f}分\n\n"
    msg += report or "本周辛苦了。"

    week_key = f"{dates[0][:4]}-W{_iso_week(dates[0])}"
    db.upsert_summary("weekly", week_key, report or "", overall_f, None)
    feishu.send_to_group(msg, BOT)

    # 顺手刷新画像
    try:
        profile.refresh_profile()
    except Exception as e:
        logger.error("周报复盘时刷新画像失败: %s", e)


# =========================================================
# 工具
# =========================================================
def _stat_logs(logs):
    stats = {}
    for l in logs:
        n = l["task_name"]
        s = stats.setdefault(n, {"count": 0, "total_f": 0, "total_c": 0})
        s["count"] += 1
        s["total_f"] += l["focus_score"]
        s["total_c"] += l["completion_rate"]
    return stats


def _iso_week(date_str):
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d").isocalendar().week
