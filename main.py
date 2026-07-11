"""个人助理系统入口。

启动：飞书 WebSocket 长连接（收消息）+ 定时调度线程 + 命令行。
路由：按 @ 到哪个 bot 分发到 bots.xiaonao / bots.xiaozhi。
"""
import os
import sys
import time
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

# 把项目根目录加入 sys.path，确保 core/bots/analysis 可 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import config, db, feishu
from core import scheduler
from bots import xiaonao, xiaozhi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("habit_tracker.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
# 降低第三方库噪音
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("schedule").setLevel(logging.WARNING)

logger = logging.getLogger("main")

is_running = True

# ---------- 消息处理线程池与去重 ----------
# 关键架构：on_message_received 在飞书 WebSocket 事件循环里同步执行，
# 必须立刻返回，否则会阻塞 ping 心跳导致断连重连、消息重推。
# 因此：回调里只做去重 + 派发到线程池，真正的 AI 处理在线程池里跑。
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="msg")

# 去重：message_id -> 收到时间戳。保留 1 小时窗口，远大于重连重推的延迟。
_processed_ids = {}  # {message_id: timestamp}
_last_text_time = {}  # text -> ts，60 秒内同内容只处理一次
_dedup_lock = threading.Lock()  # 保证"检查+加入"原子，防并发竞态
_DEDUP_TTL = 3600      # message_id 保留 1 小时
_TEXT_DEDUP_TTL = 60   # 内容去重窗口 60 秒（原 10 秒太短，挡不住重连重推）


def _load_dotenv_if_any():
    """轻量 .env 加载（不依赖 python-dotenv，避免新增依赖）。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def on_message_received(event):
    """飞书消息事件回调。

    架构关键：此函数在飞书 WebSocket 事件循环里同步执行，必须立刻返回，
    否则阻塞 ping 心跳 → 飞书判定超时 → 断连重连 → 重推消息 → 重复回复。
    所以这里只做：解析 → 去重 → 派发到线程池，立刻返回。
    真正的 AI 处理和回复在 _process_message 里异步执行。
    """
    try:
        msg = event.event.message
        message_id = msg.message_id
        content = json.loads(msg.content)
        text = content.get("text", "")

        # 原子去重：检查+加入必须在同一把锁里，防并发竞态
        now = time.time()
        with _dedup_lock:
            _gc_dedup(now)
            if message_id in _processed_ids:
                logger.info("重复消息ID跳过: %s", message_id)
                return
            # 内容去重（60 秒窗口，挡住重连重推）
            if text and text in _last_text_time and now - _last_text_time[text] < _TEXT_DEDUP_TTL:
                logger.info("重复内容跳过: '%s'", text[:30])
                return
            _processed_ids[message_id] = now
            if text:
                _last_text_time[text] = now

        logger.info("[RAW] id=%s text='%s'", message_id, text[:50])

        # 基础过滤（轻量，不阻塞）
        sender = event.event.sender
        if sender.sender_type != "user":
            return
        chat = msg.chat_id
        if chat != config.chat_id():
            return
        mentioned = _detect_mentioned_bot(msg)
        if not mentioned:
            return

        # 剥离 @ 占位符
        clean = text
        for m in (msg.mentions or []):
            clean = clean.replace(m.key, "").strip()

        logger.info("收到 @%s: %s", mentioned, clean)
        # 派发到线程池异步处理，回调立即返回，不阻塞事件循环
        _executor.submit(_process_message, chat, mentioned, clean)

    except Exception as e:
        logger.error("消息分发错误: %s", e, exc_info=True)


def _process_message(chat, mentioned, clean):
    """实际消息处理（在线程池里跑，可安全阻塞做 AI 调用）。"""
    try:
        if mentioned == "xiaonao":
            reply = xiaonao.handle(clean)
        else:
            reply = xiaozhi.handle(clean)
        logger.info("回复: %s", reply[:80])
        feishu.send_message(chat, reply, mentioned)
    except Exception as e:
        logger.error("消息处理错误: %s", e, exc_info=True)


def _gc_dedup(now):
    """清理过期的去重记录。调用前必须已持有 _dedup_lock。"""
    expired_ids = [mid for mid, ts in _processed_ids.items()
                   if now - ts > _DEDUP_TTL]
    for mid in expired_ids:
        del _processed_ids[mid]
    expired_texts = [t for t, ts in _last_text_time.items()
                     if now - ts > _TEXT_DEDUP_TTL]
    for t in expired_texts:
        del _last_text_time[t]


def _detect_mentioned_bot(msg):
    bots = config.get()["feishu_apps"]
    name_map = {
        bots["xiaonao"]["bot_name"]: "xiaonao",
        bots["xiaozhi"]["bot_name"]: "xiaozhi",
    }
    for m in (msg.mentions or []):
        if m.mentioned_type == "bot" and m.name in name_map:
            return name_map[m.name]
    return None


def start_feishu_client():
    """启动飞书 WebSocket 长连接。失败自动重连。

    架构说明（重要，避免后人误改）：
    - 全局只建立一条长连接，用「小闹」的凭证。
    - 飞书群消息事件会带着完整 mentions 列表推送，一条连接就能收到群里
      @小闹 和 @小知 的所有消息，由 on_message_received 按 @ 了谁分发。
    - 因此「小知」在飞书后台无需单独开长连接订阅；小知的 app_id/secret
      只用于"以小知身份发送回复消息"（见 core/feishu.send_message(app_name='xiaozhi')），
      不参与事件接收。曾经尝试为小知单独建长连接会触发
      "This event loop is already running"，属预期，无需修复。
    """
    try:
        from lark_oapi.ws.client import Client
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    except ImportError:
        logger.error("未安装 lark_oapi，无法启动飞书连接。请 pip install lark-oapi")
        return

    app = config.feishu_app("xiaonao")  # 仅用小闹凭证建一条长连接，见上方架构说明
    handler = (
        EventDispatcherHandler.builder(
            app.get("encrypt_key", ""), app.get("verification_token", ""))
        .register_p2_im_message_receive_v1(on_message_received)
        .build()
    )
    client = Client(app["app_id"], app["app_secret"], event_handler=handler)

    while is_running:
        try:
            logger.info("飞书长连接启动中...")
            client.start()  # 阻塞
        except Exception as e:
            logger.error("飞书连接异常: %s，5 秒后重连", e)
            time.sleep(5)


def main():
    global is_running
    print("🚀 启动个人助理系统...")

    _load_dotenv_if_any()
    config.load_config()
    db.init_db()

    # 定时任务
    jobs = scheduler.default_jobs_from_config() + scheduler.fitness_jobs_from_config()
    scheduler.setup(jobs)
    threading.Thread(target=scheduler.run_forever, daemon=True).start()

    # 飞书连接
    threading.Thread(target=start_feishu_client, daemon=True).start()

    print("✅ 系统已启动，等待飞书消息")
    # 有交互终端时提供命令行；无 TTY（后台运行）时纯阻塞保活
    if sys.stdin.isatty():
        print("命令：status / tasks / profile / exit")
        _command_loop()
    else:
        logger.info("无交互终端，进入守护模式（后台运行）")
        print("（后台守护模式运行中，停止请用 kill 或 Ctrl+C）")
        try:
            while is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    scheduler.stop()
    print("系统已退出")


def _command_loop():
    """交互式命令循环（仅在有 TTY 时调用）。"""
    global is_running
    while is_running:
        try:
            cmd = input("> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            is_running = False
            break
        if cmd in ("exit", "quit"):
            is_running = False
            break
        elif cmd == "status":
            print(f"活跃任务: {len(db.query_tasks('active'))}  "
                  f"目标: {len(db.query_goals('active'))}  "
                  f"近7天日志: {len(db.query_recent_logs(7))}")
        elif cmd == "tasks":
            for t in db.query_tasks("active"):
                print(f"  - [{t['type']}] {t['name']} {t.get('time') or ''}")
        elif cmd == "profile":
            from analysis import profile
            txt, updated = profile.get_profile_context()
            print(f"画像 (更新于 {updated}):\n{txt or '（尚未建立）'}")
        elif cmd == "help":
            print("@小闹：加任务/完成任务/查看任务/加目标")
            print("@小知：随便说（会记录）/ 分析…/ 总结这周")
        elif cmd:
            print("未知命令，输入 help")


if __name__ == "__main__":
    main()
