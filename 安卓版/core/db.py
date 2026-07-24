"""数据库层：所有持久化操作的唯一入口（repo 模式）。

设计要点：
- 统一连接管理，单行 schema 初始化。
- 每个写操作都是一个 repo 函数；将来接飞书多维表格时，只需在这些函数里加同步钩子，
  不用改业务层（见 plan 第七节）。
- 预留 cleanup_before() 接口供 archive 模块调用（3周清理）。
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta

from core import config

logger = logging.getLogger(__name__)


# ---------- 连接 ----------
def get_conn():
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def today_weekday():
    """ISO 周几：1=周一 ... 7=周日。"""
    return datetime.now().isoweekday()


def past_dates(n):
    return [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(n)
    ]


# ---------- 初始化 ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    goal_id INTEGER,
    type TEXT DEFAULT 'fixed',          -- fixed / flexible
    time TEXT,
    duration INTEGER DEFAULT 30,
    days_of_week TEXT DEFAULT '',
    status TEXT DEFAULT 'active',        -- active / done / canceled
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    goal_id INTEGER,
    completion_rate INTEGER DEFAULT 0,
    focus_score INTEGER DEFAULT 0,
    mood TEXT,
    note TEXT,
    plan_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT DEFAULT 'xiaozhi',       -- xiaozhi / xiaonao / system
    raw_text TEXT NOT NULL,
    tags TEXT DEFAULT '[]',              -- JSON 数组
    mood TEXT,
    energy INTEGER,                      -- 1-5 可空
    context TEXT,                        -- 触发场景（开会多/熬夜等）
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,                       -- study / exam / skill / health / other
    deadline TEXT,
    success_metric TEXT,                 -- 衡量标准，如"雅思7分"
    status TEXT DEFAULT 'active',        -- active / achieved / paused / dropped
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT DEFAULT '{}',           -- AI 维护的结构化 JSON
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_type TEXT NOT NULL,           -- daily / weekly / monthly
    period_key TEXT NOT NULL,            -- 如 2026-07-04 或 2026-W27
    content TEXT,
    focus_avg INTEGER,
    completion_rate INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (period_type, period_key)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_name TEXT NOT NULL,
    role TEXT NOT NULL,                  -- user / assistant
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    suggestion TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_date ON logs(plan_date);
CREATE INDEX IF NOT EXISTS idx_logs_task ON logs(task_name);
CREATE INDEX IF NOT EXISTS idx_obs_created ON observations(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_bot ON sessions(bot_name, id);
"""


def init_db():
    """建表 + 初始化默认任务 + 初始化空画像。"""
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)

        # 初始化默认固定任务（仅首次）
        cur = conn.execute("SELECT COUNT(*) FROM tasks")
        if cur.fetchone()[0] == 0:
            inserted = 0
            for t in config.get().get("tasks", {}).get("fixed", []):
                name = t.get("name")
                if not name:
                    continue
                conn.execute(
                    "INSERT INTO tasks (name, type, time, duration, days_of_week, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (name, "fixed", t.get("remind_time", ""),
                     t.get("duration", 30), t.get("days_of_week", ""),
                     now_str(), now_str()),
                )
                inserted += 1
            logger.info("初始化了 %d 个默认任务", inserted)

        # 初始化空画像（含自我进化用到的两个空列表，避免 append_profile_strategy 首次初始化分支）
        conn.execute(
            "INSERT OR IGNORE INTO user_profile (id, content, updated_at) VALUES (1, ?, ?)",
            (json.dumps({"success_strategies": [], "failure_triggers": []}, ensure_ascii=False), now_str()),
        )
        conn.commit()
        logger.info("数据库初始化完成")
    finally:
        conn.close()


# =========================================================
# tasks repo
# =========================================================
def query_tasks(status="active"):
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY time", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY time").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_today_tasks():
    all_tasks = query_tasks("active")
    weekday = today_weekday()
    today = []
    for t in all_tasks:
        if t["type"] == "flexible":
            today.append(t)
            continue
        days = t.get("days_of_week", "")
        if not days or weekday in [
            int(x.strip()) for x in days.split(",") if x.strip()
        ]:
            today.append(t)
    return today


def add_task(name, task_type="fixed", time=None, duration=30,
             days_of_week="", goal_id=None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tasks (name, goal_id, type, time, duration, days_of_week, "
            "status, created_at, updated_at) VALUES (?,?,?,?,?,?, 'active', ?, ?)",
            (name, goal_id, task_type, time, duration, days_of_week,
             now_str(), now_str()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_task(name, field, value):
    ALLOWED = {"name", "type", "time", "duration", "days_of_week",
               "status", "goal_id", "updated_at"}
    if field not in ALLOWED:
        return False
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE tasks SET {field}=?, updated_at=? WHERE name=?",
            (value, now_str(), name),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_task(name):
    return update_task(name, "status", "canceled")


# =========================================================
# logs repo
# =========================================================
def add_log(task_name, completion_rate=0, focus_score=0, note="",
            plan_date=None, mood=None, goal_id=None):
    if plan_date is None:
        plan_date = today_str()
    created = now_str()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO logs (task_name, goal_id, completion_rate, focus_score, "
            "mood, note, plan_date, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (task_name, goal_id, completion_rate, focus_score, mood,
             note, plan_date, created),
        )
        conn.commit()
    finally:
        conn.close()


def query_logs_by_date(date_str):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM logs WHERE plan_date=? OR created_at LIKE ? "
            "ORDER BY id",
            (date_str, f"{date_str}%"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_recent_logs(days=7):
    """查最近 N 天的 logs（单次连接，按日期范围查询）。"""
    dates = past_dates(days)
    earliest = dates[-1]  # past_dates 从今天往回数，最后一个是最早的
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM logs WHERE plan_date >= ? OR created_at >= ? "
            "ORDER BY id",
            (earliest, earliest + " 00:00:00"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_recent_logs_for_task(task_name, days=7):
    """查最近 N 天某任务的 logs（单次连接，按日期范围查询）。"""
    dates = past_dates(days)
    earliest = dates[-1]
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM logs WHERE task_name=? AND "
            "(plan_date >= ? OR created_at >= ?) ORDER BY id",
            (task_name, earliest, earliest + " 00:00:00"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# =========================================================
# observations repo
# =========================================================
def add_observation(raw_text, tags=None, mood=None, energy=None,
                    context=None, source="xiaozhi"):
    created = now_str()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO observations (source, raw_text, tags, mood, energy, "
            "context, created_at) VALUES (?,?,?,?,?,?,?)",
            (source, raw_text, json.dumps(tags or [], ensure_ascii=False),
             mood, energy, context, created),
        )
        conn.commit()
    finally:
        conn.close()


def query_recent_observations(days=7):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM observations WHERE created_at >= ? ORDER BY id DESC",
            (past_dates(days)[-1] + " 00:00:00",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# =========================================================
# goals repo
# =========================================================
def add_goal(title, category="study", deadline=None,
             success_metric=None):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO goals (title, category, deadline, success_metric, "
            "status, created_at, updated_at) VALUES (?,?,?,?, 'active', ?, ?)",
            (title, category, deadline, success_metric, now_str(), now_str()),
        )
        conn.commit()
        gid = cur.lastrowid
    finally:
        conn.close()
    return gid


def query_goals(status="active"):
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status=? ORDER BY deadline", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY deadline").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_goal(goal_id, field, value):
    ALLOWED = {"title", "category", "deadline", "success_metric",
               "status", "updated_at"}
    if field not in ALLOWED:
        return False
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE goals SET {field}=?, updated_at=? WHERE id=?",
            (value, now_str(), goal_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# =========================================================
# user_profile repo
# =========================================================
def get_profile():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content, updated_at FROM user_profile WHERE id=1"
        ).fetchone()
        if not row:
            return {}, None
        try:
            return json.loads(row["content"]), row["updated_at"]
        except json.JSONDecodeError:
            return {}, row["updated_at"]
    finally:
        conn.close()


def save_profile(content):
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False, indent=2)
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE user_profile SET content=?, updated_at=? WHERE id=1",
            (text, now_str()),
        )
        conn.commit()
    finally:
        conn.close()


# 允许增量追加的画像字段（值都是字符串列表），老库缺失时自动初始化为 []。
_APPENDABLE_PROFILE_FIELDS = ("success_strategies", "failure_triggers")


def append_profile_strategy(field, text):
    """把一条新策略/陷阱增量追加进画像 JSON（去重）。

    field ∈ {"success_strategies", "failure_triggers"}，值在画像里是字符串列表。
    老库可能没有这两个字段，或值不是 list：这种情况自动初始化为 [] 再追加。
    text 为空、或已存在（相等比较）则跳过，不写库。
    """
    if field not in _APPENDABLE_PROFILE_FIELDS:
        logger.warning("append_profile_strategy: 非法字段 %s", field)
        return
    text = (text or "").strip()
    if not text:
        return
    content, _ = get_profile()
    if not isinstance(content, dict):
        content = {}
    items = content.get(field)
    if not isinstance(items, list):
        items = []
    if text in items:
        return
    items.append(text)
    content[field] = items
    save_profile(content)


# =========================================================
# summaries repo
# =========================================================
def upsert_summary(period_type, period_key, content, focus_avg=None,
                   completion_rate=None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO summaries (period_type, period_key, content, focus_avg, "
            "completion_rate, created_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(period_type, period_key) DO UPDATE SET "
            "content=excluded.content, focus_avg=excluded.focus_avg, "
            "completion_rate=excluded.completion_rate, created_at=excluded.created_at",
            (period_type, period_key, content, focus_avg, completion_rate, now_str()),
        )
        conn.commit()
    finally:
        conn.close()


def query_summaries(period_type=None, limit=30):
    conn = get_conn()
    try:
        if period_type:
            rows = conn.execute(
                "SELECT * FROM summaries WHERE period_type=? "
                "ORDER BY period_key DESC LIMIT ?",
                (period_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM summaries ORDER BY period_key DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# =========================================================
# 清理接口（archive 模块调用）
# =========================================================
def cleanup_before(days, tables=("logs", "observations", "sessions")):
    """删除指定天数前的原始明细，返回每张表删除行数。

    注意：调用前应已把这些数据压缩进 summaries。本函数只做硬删除。
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    deleted = {}
    conn = get_conn()
    try:
        for table in tables:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE created_at < ?", (cutoff,)
            )
            deleted[table] = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def cleanup_specific_dates(dates, tables=("logs", "observations")):
    """删除指定日期列表对应的原始明细，返回每张表删除行数。

    比 cleanup_before 更安全：只删除已确认归档成功的日期数据。
    logs 按 plan_date 匹配，observations 按 created_at 日期前缀匹配。
    """
    if not dates:
        return {}
    deleted = {}
    conn = get_conn()
    try:
        # logs: 按 plan_date 删除
        placeholders = ",".join("?" * len(dates))
        cur = conn.execute(
            f"DELETE FROM logs WHERE plan_date IN ({placeholders})", dates
        )
        deleted["logs"] = cur.rowcount
        # observations: 按 created_at 日期前缀删除
        like_patterns = [f"{d}%" for d in dates]
        like_placeholders = ",".join("?" * len(like_patterns))
        cur = conn.execute(
            f"DELETE FROM observations WHERE created_at LIKE "
            f"{' OR created_at LIKE '.join(['?'] * len(like_patterns))}",
            like_patterns,
        )
        deleted["observations"] = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def count_old_rows(days):
    """诊断用：查看指定天数前各表还有多少行（未压缩前）。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        counts = {}
        for table in ("logs", "observations", "sessions"):
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE created_at < ?",
                (cutoff,),
            ).fetchone()
            counts[table] = row["c"]
        return counts
    finally:
        conn.close()
