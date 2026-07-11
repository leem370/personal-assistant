"""连接测试器：配置向导里「测试连接」按钮调用，验证各项配置是否填对。

不依赖完整后端启动，直接用 requests 调飞书/AI 接口验证。
"""
import json
import requests


def test_feishu_app(app_id, app_secret, label=""):
    """测试飞书应用 token 获取。返回 (ok, msg)。"""
    if not app_id or not app_secret:
        return False, f"{label}：app_id 或 secret 为空"
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            return True, f"{label}：连接成功 ✅"
        return False, f"{label}：{data.get('msg', '未知错误')}"
    except Exception as e:
        return False, f"{label}：网络错误 {e}"


def test_ai(api_key, api_base, model):
    """测试 AI 接口（发一条简单消息验证）。返回 (ok, msg)。"""
    if not api_key:
        return False, "AI：api_key 为空"
    base = (api_base or "").rstrip("/") or "https://api.openai.com/v1"
    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model or "gpt-4o-mini",
                  "messages": [{"role": "user", "content": "测试"}],
                  "max_tokens": 5},
            timeout=20,
        )
        data = r.json()
        if "choices" in data:
            return True, f"AI：连接成功 ✅（模型 {model}）"
        return False, f"AI：{data.get('error', {}).get('message', data.get('msg', '未知错误'))}"
    except Exception as e:
        return False, f"AI：网络错误 {e}"


def test_bitable(app_id, app_secret, app_token):
    """测试多维表格访问（列一下表验证权限）。返回 (ok, msg)。"""
    if not app_id or not app_secret or not app_token:
        return False, "多维表格：配置不完整"
    # 先拿 token
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        tdata = r.json()
        if tdata.get("code") != 0:
            return False, f"多维表格：token 获取失败 - {tdata.get('msg')}"
        token = tdata["tenant_access_token"]
    except Exception as e:
        return False, f"多维表格：网络错误 {e}"
    # 列表
    try:
        r = requests.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        data = r.json()
        if data.get("code") == 0:
            count = len(data["data"].get("items", []))
            return True, f"多维表格：连接成功 ✅（{count} 张表）"
        return False, f"多维表格：{data.get('msg', '未知错误')}"
    except Exception as e:
        return False, f"多维表格：网络错误 {e}"


def parse_bitable_url(url):
    """从多维表格 URL 解析 app_token。

    支持两种格式：
      https://xxx.feishu.cn/base/BASExxxx?table=tblYYY
      https://xxx.feishu.cn/wiki/WIKIXXXX
    返回 app_token 或 None。
    """
    if not url:
        return None
    # /base/ 后面
    if "/base/" in url:
        part = url.split("/base/")[1]
        return part.split("?")[0].split("/")[0]
    # /wiki/ 后面
    if "/wiki/" in url:
        part = url.split("/wiki/")[1]
        return part.split("?")[0].split("/")[0]
    return None
