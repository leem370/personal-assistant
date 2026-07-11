"""目标规划：基于目标倒推 + 画像高效时段，给每日规划建议。

本期实现 suggest_daily_plan()（由小闹早间可调用，或用户主动 @小闹 问"今天怎么安排"）。
goals 的 CRUD 在 db.py + executor 里，这里只做"规划"推理。
"""
import logging
from datetime import datetime

from core import db, ai
from analysis import profile

logger = logging.getLogger(__name__)


def suggest_daily_plan():
    """生成今日规划建议文本。供定时任务或机器人调用。"""
    goals = db.query_goals("active")
    today_tasks = db.query_today_tasks()
    profile_text, _ = profile.get_profile_context()
    recent_logs = db.query_recent_logs(7)

    goal_text = "\n".join(
        f"- {g['title']}（截止 {g.get('deadline') or '未定'}，"
        f"衡量 {g.get('success_metric') or '-'}）"
        for g in goals
    ) or "（暂无设定目标）"
    task_text = "\n".join(
        f"- {t['name']}（{t.get('time') or '弹性'}）"
        for t in today_tasks
    ) or "（今日无固定任务）"
    log_text = "\n".join(
        f"- {l['plan_date']} {l['task_name']}: 完成{l['completion_rate']}% 专注{l['focus_score']}"
        for l in recent_logs[-10:]
    ) or "（近7天无记录）"

    prompt = (
        f"今天是 {db.today_str()}。请基于以下信息给出今日规划建议（不超过 200 字）：\n"
        f"1. 指出今天最该推进的 1-2 件事（结合目标截止和近况）；\n"
        f"2. 结合用户高效时段安排它们；\n"
        f"3. 提一个对抗惰性的小具体动作。\n\n"
        f"【阶段性目标】\n{goal_text}\n\n"
        f"【今日已有任务】\n{task_text}\n\n"
        f"【近7天记录】\n{log_text}\n\n"
        f"【系统对用户的理解】\n{profile_text or '（画像待建立）'}\n"
    )
    suggestion = ai.call_ai(
        prompt,
        system_prompt="你是规划教练，建议要具体、可执行、贴合用户作息。",
        temperature=0.5,
    )
    return suggestion or "今天先把最重要的一件事做掉，其他的都是奖励 🎯"
