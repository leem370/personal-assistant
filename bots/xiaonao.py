"""小闹（Executor）：执行 / 催办人格。

职责：管待办、按时提醒、晚间未完成追问（适度强度）、命令处理。
人格：简洁、坚定、不啰嗦，带轻量 emoji。不做深度分析（那是小知的活）。
"""
import re
import logging

from core import db, ai, memory, feishu
from bots import executor

logger = logging.getLogger(__name__)

BOT = "xiaonao"

# 人格 system prompt
SYSTEM_PROMPT = """你是"小闹"，用户的执行助理，负责待办和催办。
人格：简洁、坚定、不啰嗦，像个靠谱的执行官。
说话风格：短句为主，可以用 ✅ ❌ 📋 ⏰ 等轻量 emoji，但不要长篇大论。
你只管"做什么、什么时候做、做没做"，不做心理分析和深度复盘——那是搭档"小知"的工作。
如果用户说的话明显是倾诉情绪或想聊天，礼貌说一句"这块可以让小知帮你看看"，然后把任务相关部分处理掉。

从用户输入提取操作，只返回 JSON 数组（不要其他文字）。可选 intent：
- log: {"intent":"log","task_name":"...","completion_rate":100,"focus_score":0,"note":"","mood":"开心/平静/疲惫等"}
- task_add: {"intent":"task_add","task_name":"...","task_time":"15:00或空","task_type":"fixed|flexible","duration":30,"days_of_week":""}
- task_delete: {"intent":"task_delete","task_name":"..."}
- task_update: {"intent":"task_update","task_name":"...","field":"time|duration|type|status|days_of_week","value":"..."}
- task_query: {"intent":"task_query"}
- task_uncompleted: {"intent":"task_uncompleted"}
- goal_add: {"intent":"goal_add","goal_title":"...","deadline":"YYYY-MM-DD","success_metric":"...","category":"study|exam|skill|health"}
- goal_query: {"intent":"goal_query"}
- chat: {"intent":"chat","reply":"...简短回复..."}

规则：
1. 多个任务完成，每个生成独立 log。
2. 若用户没明确完成度，log 的 completion_rate 用 100。
3. 任务名去掉末尾"任务/待办/事项"。
4. 无法判断为操作时，用 chat 简短回复。
只返回 JSON 数组。"""


def handle(text):
    """处理用户消息，返回回复字符串。"""
    if ai.config.ai_enabled():
        actions = _parse(text)
        if actions:
            return executor.execute_actions(actions, BOT, user_text=text)
        # AI 不可用或解析失败：降级规则
    return _rule_fallback(text)


def _parse(text):
    """调用 AI 解析为 intent 列表。"""
    session = memory.get_session(BOT)[-6:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + session
    messages.append({"role": "user", "content": text})
    actions = ai.call_ai_json(messages, temperature=0.2)
    if isinstance(actions, dict):
        actions = [actions]
    return actions


# =========================================================
# 规则后备（AI 不可用时）
# =========================================================
def _rule_fallback(msg):
    m = re.match(r"增加任务[：:]?\s*(.+?)\s+([0-9:]+)", msg)
    if m:
        name, t = m.group(1).strip(), m.group(2).strip()
        ok = db.add_task(name, "fixed", time=t)
        return f"✅ 已添加任务：{name}，时间：{t}" if ok else f"❌ 任务'{name}'已存在"
    m = re.match(r"删除任务[：:]?\s*(.+)", msg)
    if m:
        name = m.group(1).strip()
        ok = db.delete_task(name)
        return f"✅ 已删除任务：{name}" if ok else f"❌ 未找到任务：{name}"
    if "查看任务" in msg:
        tasks = db.query_tasks("active")
        return executor._format_tasks(tasks) if tasks else "当前没有活跃任务"
    # 任务名贪婪到第一个「 专注N / 完成N% / 行尾」之前，避免吞掉任务名末字
    m = re.match(r"完成\s+(.+?)(?:\s+(?:专注(\d+)|完成(\d+)%?))?$", msg)
    if m:
        name = m.group(1).strip()
        focus = int(m.group(2)) if m.group(2) else 0
        comp = int(m.group(3)) if m.group(3) else 100
        db.add_log(name, comp, focus)
        return f"✅ 已记录：{name}（完成{comp}%，专注{focus}分）"
    return "❌ 没太懂，试试：增加任务 背单词 15:00 / 完成 听力 专注8 / 查看任务"


# =========================================================
# 定时任务（小闹负责）
# =========================================================
def morning_plan():
    """09:00 早间：今日待办 + 昨日未完成的轻量追问。"""
    today = db.query_today_tasks()
    yesterday = db.today_weekday()  # 仅占位
    # 昨日未完成
    from datetime import timedelta
    ydate = (db.now_str()[:10])
    # 取昨天日期
    import datetime as _dt
    yesterday_str = (_dt.datetime.now() - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    y_logs = db.query_logs_by_date(yesterday_str)
    y_tasks = []  # 简化：列出昨天有计划但未完成的
    # 取昨天活跃任务里未完成的（按当日任务集近似）
    all_active = db.query_tasks("active")
    done_yesterday = {l["task_name"] for l in y_logs if l["completion_rate"] > 0}
    for t in all_active:
        if t["name"] not in done_yesterday and _task_due_on(t, _parse_weekday(yesterday_str)):
            y_tasks.append(t["name"])

    msg = "🌅 早上好！\n\n📋 今日待办：\n"
    if today:
        for i, t in enumerate(today, 1):
            tt = "固定" if t["type"] == "fixed" else "弹性"
            msg += f"{i}. [{tt}] {t['name']}"
            if t.get("time"):
                msg += f" - {t['time']}"
            msg += "\n"
    else:
        msg += "今天没有固定安排，主动规划一下吧 💪\n"

    if y_tasks:
        msg += "\n⏰ 昨天这几个没完成，今天要不要续上？\n"
        for n in y_tasks[:5]:
            msg += f"- {n}\n"
    feishu.send_to_group(msg, BOT)


def night_check():
    """21:00 晚间：未完成项适度追问。"""
    today = db.today_str()
    tasks = db.query_today_tasks()
    logs = db.query_logs_by_date(today)
    done = set()
    for l in logs:
        if l["completion_rate"] > 0:
            done.add(l["task_name"])
    uncompleted = [t for t in tasks if t["name"] not in done]
    if not uncompleted:
        feishu.send_to_group("🌙 今天都搞定了，早点休息 🎉", BOT)
        return
    msg = "🌙 晚间 check，这几个还没动：\n"
    for t in uncompleted:
        msg += f"- {t['name']}\n"
    msg += "\n是什么挡住你了？告诉我，我让小知帮你看看 👀"
    feishu.send_to_group(msg, BOT)


def fitness_reminder():
    feishu.send_to_group("🏋️ 健身时间到！放下手里的活，动一下！", BOT)


# =========================================================
# 工具
# =========================================================
def _parse_weekday(date_str):
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d").isoweekday()


def _task_due_on(task, weekday):
    if task["type"] == "flexible":
        return True
    days = task.get("days_of_week", "")
    if not days:
        return True
    return weekday in [int(x.strip()) for x in days.split(",") if x.strip()]
