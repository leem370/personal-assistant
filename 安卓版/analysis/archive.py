"""数据压缩归档：实现用户要求的"3周清理"。

策略：
  1. 把 >21 天的 logs + observations 按日聚合，生成/更新 daily summary。
  2. 已聚合的原始明细硬删除。
  3. weekly summary 由 daily summary 汇总生成（不依赖原始明细）。
这样系统永不膨胀，但历史认知通过 summaries 保留。
"""
import logging
from datetime import datetime, timedelta

from core import db, ai
from core.utils import iso_week

logger = logging.getLogger(__name__)

RETENTION_DAYS = 21


def run_archive():
    """每天 03:00 跑：压缩并清理超过保留期的数据。

    安全策略：只删除已成功生成 daily summary 的日期对应的原始明细，
    归档失败的日期数据保留，等下次重试。
    """
    today = datetime.now()
    # 找出所有需要处理的"老日期"
    dates = _collect_old_dates(today)
    if not dates:
        return

    archived_dates = []
    for d in dates:
        if _archive_one_day(d):
            archived_dates.append(d)

    if archived_dates:
        # 只删除已成功归档日期的原始明细
        deleted = db.cleanup_specific_dates(archived_dates)
        logger.info("归档完成：%d 个日期已压缩，删除明细 %s",
                    len(archived_dates), deleted)


def _collect_old_dates(today):
    """返回所有 >RETENTION_DAYS 天前、且 logs/observations 里仍存在明细的日期。"""
    cutoff = today - timedelta(days=RETENTION_DAYS)
    conn = db.get_conn()
    dates = set()
    try:
        for row in conn.execute(
            "SELECT DISTINCT plan_date FROM logs WHERE plan_date < ?",
            (cutoff.strftime("%Y-%m-%d"),),
        ):
            if row["plan_date"]:
                dates.add(row["plan_date"])
        for row in conn.execute(
            "SELECT DISTINCT substr(created_at,1,10) AS d FROM observations "
            "WHERE created_at < ?",
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        ):
            if row["d"]:
                dates.add(row["d"])
        return sorted(dates)
    finally:
        conn.close()


def _archive_one_day(date_str):
    """把某一天的明细压缩成 daily summary。返回是否真的生成了摘要。"""
    logs = db.query_logs_by_date(date_str)
    conn = db.get_conn()
    try:
        obs_rows = conn.execute(
            "SELECT * FROM observations WHERE created_at LIKE ?",
            (f"{date_str}%",),
        ).fetchall()
    finally:
        conn.close()
    obs = [dict(o) for o in obs_rows]

    if not logs and not obs:
        return False

    focus_list = [l["focus_score"] for l in logs] or [0]
    comp_list = [l["completion_rate"] for l in logs] or [0]
    avg_f = sum(focus_list) // len(focus_list)
    avg_c = sum(comp_list) // len(comp_list)

    log_text = "\n".join(
        f"- {l['task_name']}: 完成{l['completion_rate']}% 专注{l['focus_score']} "
        f"备注{l.get('note') or ''}"
        for l in logs
    )
    obs_text = "\n".join(f"- {o['raw_text']}（{o.get('mood') or ''}）"
                         for o in obs)
    prompt = (
        f"把 {date_str} 这一天的记录压缩成一段不超过 120 字的摘要，"
        f"保留关键事件、情绪、专注表现和任何卡点。\n"
        f"任务：\n{log_text or '（无）'}\n\n自述：\n{obs_text or '（无）'}"
    )
    summary = ai.call_ai(prompt, system_prompt="你是数据归档助手。",
                         temperature=0.3) or (
        log_text + "\n" + obs_text
    )

    db.upsert_summary("daily", date_str, summary, avg_f, avg_c)
    return True


def rebuild_weekly_from_daily(weeks_back=8):
    """从已有的 daily summary 重建最近若干周的 weekly summary。

    在原始明细已被清理后，仍可凭 daily summary 做周聚合。
    """
    today = datetime.now()
    for w in range(weeks_back):
        ref = today - timedelta(weeks=w)
        mon = ref - timedelta(days=ref.weekday())
        dates = [(mon + timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range(7)]
        dailies = [d for d in db.query_summaries("daily")
                   if d["period_key"] in dates]
        if not dailies:
            continue
        contents = "\n".join(f"- {d['period_key']}: {d['content']}"
                             for d in dailies)
        focus_vals = [d["focus_avg"] for d in dailies
                      if d.get("focus_avg") is not None]
        avg_f = sum(focus_vals) // len(focus_vals) if focus_vals else None
        prompt = (
            f"以下是某周（{dates[0]}~{dates[-1]}）的每日摘要，"
            f"请汇总成一段不超过 180 字的周摘要，点出亮点和卡点：\n{contents}"
        )
        weekly = ai.call_ai(prompt, system_prompt="你是数据归档助手。",
                            temperature=0.3) or contents
        week_key = f"{dates[0][:4]}-W{iso_week(dates[0])}"
        db.upsert_summary("weekly", week_key, weekly, avg_f, None)
