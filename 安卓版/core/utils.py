"""通用工具函数（不依赖 Kivy / 业务逻辑）。"""
from datetime import datetime


def iso_week(date_str):
    """从 'YYYY-MM-DD' 字符串返回 ISO 周数。"""
    return datetime.strptime(date_str, "%Y-%m-%d").isocalendar().week


def parse_weekday(date_str):
    """从 'YYYY-MM-DD' 字符串返回 ISO 周几（1=周一 ... 7=周日）。"""
    return datetime.strptime(date_str, "%Y-%m-%d").isoweekday()
