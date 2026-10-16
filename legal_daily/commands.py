import json
import re

GREETING = re.compile(r"^(你好|您好|hello|hi|在吗)[!！。.\s]*$", re.I)
EXPAND_JOB = re.compile(r"^展开\s*岗位\s*第?\s*(\d+)\s*条?$")
EXPAND_NEWS = re.compile(r"^展开\s*第?\s*(\d+)\s*条?$")


def strip_mention(text):
    return re.sub(r"@_user_\d+\s*", "", text or "").strip()


def parse_command(text):
    cleaned = strip_mention(text)
    job = EXPAND_JOB.match(cleaned)
    if job:
        return {"type": "expand_job", "n": int(job.group(1))}
    news = EXPAND_NEWS.match(cleaned)
    if news:
        return {"type": "expand_news", "n": int(news.group(1))}
    if GREETING.match(cleaned):
        return {"type": "hello"}
    return {"type": "help"}


def message_text(event):
    message = event.get("event", {}).get("message", {})
    if message.get("message_type") not in (None, "text"):
        return None
    content = message.get("content") or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return strip_mention(content)
    return strip_mention(payload.get("text") or "")


def delivery_from_event(event):
    body = event.get("event", {})
    message = body.get("message", {})
    sender = body.get("sender", {})
    chat_type = message.get("chat_type")
    if chat_type == "group":
        chat_id = message.get("chat_id")
        if not chat_id:
            return None
        return {"receive_id_type": "chat_id", "receive_id": chat_id}
    open_id = sender.get("sender_id", {}).get("open_id")
    if not open_id:
        return None
    return {"receive_id_type": "open_id", "receive_id": open_id}
