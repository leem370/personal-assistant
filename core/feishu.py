"""飞书 API：tenant token 缓存 + 发消息。"""
import time
import json
import logging
import requests

from core import config

logger = logging.getLogger(__name__)

_token_cache = {}  # app_id -> {"token": str, "ts": float}


def get_tenant_access_token(app_id, app_secret):
    cached = _token_cache.get(app_id)
    if cached and time.time() - cached["ts"] < 7100:
        return cached["token"]
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        logger.error("获取 token 失败: %s", e)
        return None
    if data.get("code") == 0:
        token = data["tenant_access_token"]
        _token_cache[app_id] = {"token": token, "ts": time.time()}
        return token
    logger.error("获取 token 失败: %s", data.get("msg"))
    return None


def send_message(chat_id, text, app_name):
    """用 app_name(xiaonao/xiaozhi) 对应的应用发文本消息到群。"""
    app = config.feishu_app(app_name)
    token = get_tenant_access_token(app["app_id"], app["app_secret"])
    if not token:
        return False
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        logger.error("发消息异常: %s", e)
        return False
    if data.get("code") == 0:
        return True
    logger.error("发消息失败: %s", data.get("msg"))
    return False


def send_to_group(text, app_name="xiaonao"):
    """便捷方法：发到配置的群。"""
    return send_message(config.chat_id(), text, app_name)
