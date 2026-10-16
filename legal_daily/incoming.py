import base64
import json
import os

from .commands import delivery_from_event, message_text, parse_command
from .feishu import reply_text, tenant_token
from .format import DISCLAIMER, format_expand
from .llm import complete_json, expand_prompt
from .net import fetch_text
from .store import latest_digest, load_delivery, remember_message, save_delivery, seen_message
from .textutil import html_to_text

HELLO = (
    "已记下这个对话。每天 8:00（北京时间）会把日报发到这里。电脑开不开机都不影响。\n"
    "回复「展开第 2 条」看新闻，回复「展开岗位 1」看岗位。\n"
    + DISCLAIMER
)
HELP = (
    "我可以做两件事：每天 8:00 推送日报；你回复「展开第 2 条」或「展开岗位 1」，我再展开那一条。\n"
    + DISCLAIMER
)


def _token():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
    return tenant_token(app_id, app_secret)


def _reply(token, message_id, delivery, text):
    if message_id:
        try:
            reply_text(token, message_id, text)
            return
        except Exception as exc:
            print(f"回复失败，改为直接发送: {exc}")
    if delivery:
        from .feishu import send_text

        send_text(token, delivery["receive_id_type"], delivery["receive_id"], text)


def _page_excerpt(link):
    try:
        html = fetch_text(link, timeout=20)
    except Exception as exc:
        print(f"原文没取到 {link}: {exc}")
        return ""
    text = html_to_text(html)
    if len(text) < 80:
        return ""
    return text


def _expand(digest, kind, number):
    items = (digest or {}).get("news" if kind == "news" else "jobs") or []
    item = next((entry for entry in items if entry.get("n") == number), None)
    if item is None:
        return f"今天的日报里没有第 {number} 条{'岗位' if kind == 'job' else ''}。"
    title = item["title_zh"] if kind == "news" else f"{item['org']} {item['role']}"
    page = _page_excerpt(item["link"])
    raw = complete_json(expand_prompt(item, page))
    interview = raw.get("interview") if isinstance(raw.get("interview"), list) else []
    payload = {
        "structure": str(raw.get("structure") or "材料没有写"),
        "relation": str(raw.get("relation") or "材料没有写"),
        "interview": [str(point) for point in interview[:3]],
        "en": str(raw.get("en") or ""),
    }
    return format_expand(kind, number, title, payload, item["link"])


def handle_event(event):
    header = event.get("header") or {}
    if header.get("event_type") not in (None, "im.message.receive_v1"):
        print("忽略事件", header.get("event_type"))
        return
    sender_type = event.get("event", {}).get("sender", {}).get("sender_type")
    if sender_type == "app":
        print("忽略机器人自己的消息")
        return
    message = event.get("event", {}).get("message", {})
    message_id = message.get("message_id")
    if seen_message(message_id):
        print("重复消息", message_id)
        return

    delivery = delivery_from_event(event) or load_delivery()
    token = _token()
    text = message_text(event)
    if text is None:
        _reply(token, message_id, delivery, "请发文字，例如「你好」或「展开第 2 条」。")
        return
    command = parse_command(text)
    if command["type"] == "hello":
        if delivery_from_event(event):
            save_delivery(delivery_from_event(event))
        _reply(token, message_id, delivery, HELLO)
        remember_message(message_id)
        return
    if command["type"] == "help":
        _reply(token, message_id, delivery, HELP)
        remember_message(message_id)
        return
    digest = latest_digest()
    if not digest:
        _reply(token, message_id, delivery, "还没有日报。第一次会在每天 8:00 生成，也可以在 GitHub 上手动跑一次。")
        remember_message(message_id)
        return
    kind = "news" if command["type"] == "expand_news" else "job"
    _reply(token, message_id, delivery, _expand(digest, kind, command["n"]))
    remember_message(message_id)


def load_event_from_env():
    encoded = os.environ.get("FEISHU_EVENT_B64", "").strip()
    if not encoded:
        raise RuntimeError("缺少 FEISHU_EVENT_B64")
    return json.loads(base64.b64decode(encoded))


def run_message():
    handle_event(load_event_from_env())
