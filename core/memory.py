"""对话记忆：落库，每个 bot 独立 session，进程重启不丢。"""
import logging

from core import db

logger = logging.getLogger(__name__)

MAX_TURNS = 10  # 每个 bot 保留最近 10 轮（user+assistant 各算一条）


def get_session(bot_name):
    """返回最近对话，作为 messages 列表。"""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM sessions WHERE bot_name=? "
            "ORDER BY id DESC LIMIT ?",
            (bot_name, MAX_TURNS),
        ).fetchall()
        # 反转为时间正序
        return [{"role": r["role"], "content": r["content"]}
                for r in reversed(rows)]
    finally:
        conn.close()


def add_message(bot_name, role, content):
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (bot_name, role, content, created_at) "
            "VALUES (?,?,?,?)",
            (bot_name, role, content, db.now_str()),
        )
        conn.commit()
    finally:
        conn.close()


def trim_session(bot_name, keep=MAX_TURNS):
    """超出保留条数的旧消息删除。"""
    conn = db.get_conn()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions WHERE bot_name=?",
            (bot_name,),
        ).fetchone()["c"]
        if total > keep * 2:
            conn.execute(
                "DELETE FROM sessions WHERE bot_name=? AND id NOT IN ("
                "SELECT id FROM sessions WHERE bot_name=? "
                "ORDER BY id DESC LIMIT ?)",
                (bot_name, bot_name, keep * 2),
            )
            conn.commit()
    finally:
        conn.close()


def add_and_trim(bot_name, role, content):
    """记录一条对话并自动裁剪。"""
    add_message(bot_name, role, content)
    trim_session(bot_name)
