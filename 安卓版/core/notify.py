"""本地通知封装（桌面测试时仅打日志，Android 上通过 plyer 发送）。"""
import logging

logger = logging.getLogger(__name__)


def notify(title, message):
    """发送 Android 本地通知（桌面测试时仅打日志）。"""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message[:200],
            app_name="个人助理",
            timeout=10,
        )
    except Exception:
        pass
    logger.info("[通知] %s: %s", title, message[:80])
