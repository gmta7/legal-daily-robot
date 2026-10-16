import json
import urllib.request

from .net import UA

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


def _post(url, payload, token=None, timeout=30):
    headers = {"Content-Type": "application/json; charset=utf-8", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("code") not in (0, None):
        raise RuntimeError(f"飞书接口失败 {body.get('code')} {body.get('msg')}")
    return body


def tenant_token(app_id, app_secret):
    body = _post(TOKEN_URL, {"app_id": app_id, "app_secret": app_secret})
    token = body.get("tenant_access_token")
    if not token:
        raise RuntimeError("没有拿到飞书 tenant_access_token")
    return token


def send_text(token, receive_id_type, receive_id, text):
    return _post(
        f"{SEND_URL}?receive_id_type={receive_id_type}",
        {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        token=token,
    )


def reply_text(token, message_id, text):
    return _post(
        f"{SEND_URL}/{message_id}/reply",
        {
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        token=token,
    )
