"""反思与画像刷新调度。

- weekly_profile_refresh_if_due: 每天 22:30 跑，判断是否到了该刷新画像的时候
  （启动满 3 天 且 距上次刷新 >= 7 天）。这样既能在冷启动后尽快建立画像，
  又不会每天乱刷。
"""
import logging
from datetime import datetime, timedelta

from core import db
from analysis import profile

logger = logging.getLogger(__name__)

PROFILE_MIN_DAYS = 3      # 至少积累 3 天数据才刷画像
PROFILE_INTERVAL_HOURS = 168  # 默认 7 天刷一次


def weekly_profile_refresh_if_due():
    """每日定时检查：是否该刷新画像。"""
    # 数据积累不足，先不刷
    if profile.days_since_start() < PROFILE_MIN_DAYS:
        return

    _, updated = db.get_profile()
    if updated:
        try:
            last = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last = datetime.min
        if (datetime.now() - last).total_seconds() < PROFILE_INTERVAL_HOURS * 3600:
            return  # 还没到刷新间隔

    try:
        new = profile.refresh_profile()
        if new:
            logger.info("定时任务触发了画像刷新")
    except Exception as e:
        logger.error("画像刷新失败: %s", e, exc_info=True)
