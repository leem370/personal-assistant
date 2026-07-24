"""AI 调用封装：单轮对话 / JSON 模式解析 / 重试。"""
import json
import re
import time
import logging
import requests

from core import config

logger = logging.getLogger(__name__)


def call_ai(messages, system_prompt=None, temperature=0.7, timeout=45,
            retries=1):
    """调用 OpenAI 兼容接口，返回文本或 None。

    messages 可为 str（当单条 user 消息）或标准 messages 列表。
    """
    if not config.ai_enabled():
        return None

    ai = config.get().get("ai", {})
    api_key = ai.get("api_key", "")
    api_base = ai.get("api_base", "").rstrip("/") or "https://api.openai.com/v1"
    model = ai.get("model_name", "gpt-4o-mini")

    if not api_key:
        logger.error("AI API 密钥未配置")
        return None

    if isinstance(messages, str):
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": messages})
    else:
        msgs = list(messages)
        if system_prompt and not any(m["role"] == "system" for m in msgs):
            msgs.insert(0, {"role": "system", "content": system_prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {"model": model, "messages": msgs, "temperature": temperature}

    url = f"{api_base}/chat/completions"
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()
            if "choices" in result:
                return result["choices"][0]["message"]["content"].strip()
            logger.error("AI 返回异常: %s", result)
            return None
        except requests.exceptions.Timeout:
            logger.warning("AI 调用超时（第 %d 次）", attempt + 1)
        except Exception as e:
            logger.error("AI 调用失败（第 %d 次）: %s", attempt + 1, e)
        if attempt < retries:
            time.sleep(1.5)
    return None


def call_ai_json(messages, system_prompt=None, temperature=0.3, timeout=45):
    """调用 AI 并解析为 JSON 对象/数组，解析失败返回 None。"""
    raw = call_ai(messages, system_prompt=system_prompt,
                  temperature=temperature, timeout=timeout)
    if not raw:
        return None
    return parse_json_lenient(raw)


def parse_json_lenient(raw):
    """容错 JSON 解析：剥离 ```json 代码块、抓取首个 { 或 [。"""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        # 去掉首行 ``` 和末尾 ```
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 兜底：抓取第一个 { ... } 或 [ ... ]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    logger.error("JSON 解析失败: %s", raw[:200])
    return None


def strip_task_suffix(name):
    """去掉任务名末尾的"任务/待办/事项"冗余词。"""
    if not name:
        return name
    return re.sub(r"\s*(任务|待办|事项)$", "", name).strip()
