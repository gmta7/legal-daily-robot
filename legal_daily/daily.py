import os

from .feishu import send_text, tenant_token
from .format import format_alerts, format_digest
from .llm import complete_json, news_prompt
from .select import select_jobs, select_news
from .sources import allowed_links, collect_all, material_block
from .store import digest_paths, load_seen_jobs, save_digest, save_seen_jobs, load_delivery
from .textutil import norm_link, today_shanghai


def _brief(item):
    return {
        "title": item.get("title") or "",
        "link": item.get("link") or "",
        "date": item.get("date") or "",
    }


def _credentials():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
    return app_id, app_secret


def _notify(text):
    delivery = load_delivery()
    if not delivery:
        print("还没有私聊或群聊地址，这次不发飞书")
        return
    app_id, app_secret = _credentials()
    token = tenant_token(app_id, app_secret)
    send_text(token, delivery["receive_id_type"], delivery["receive_id"], text)


def _build(date, collector):
    news_sources, job_sources = collector()
    print(f"材料 新闻 {len(news_sources)} 条，岗位 {len(job_sources)} 条")
    if not news_sources and not job_sources:
        markdown = format_digest(date, [], []).replace(
            "今日无重大更新 / No major update today.",
            "今日公开检索没有返回结果，所以没有编日报。 / No public results today.",
        )
        return {"date": date, "news": [], "jobs": [], "empty_fetch": True}, markdown

    for item in news_sources:
        print(f"新闻材料 {item.get('date') or ''} {item['title']}")
    for item in job_sources:
        print(f"岗位材料 {item.get('date') or ''} {item['title']}")
    materials = material_block(news_sources + job_sources)
    raw = complete_json(news_prompt(materials))
    raw_news = raw.get("news") or []
    raw_jobs = raw.get("jobs") or []
    news = select_news(raw_news, allowed_links(news_sources), news_sources)
    jobs = select_jobs(raw_jobs, allowed_links(job_sources), load_seen_jobs(), job_sources)
    print(f"模型返回新闻 {len(raw_news)} 条，岗位 {len(raw_jobs)} 条")
    print(f"收录新闻 {len(news)} 条，岗位 {len(jobs)} 条")
    payload = {
        "date": date,
        "news": news,
        "jobs": jobs,
        "empty_fetch": False,
        "sources": {
            "news": [_brief(item) for item in news_sources],
            "jobs": [_brief(item) for item in job_sources],
        },
    }
    return payload, format_digest(date, news, jobs, news_sources, job_sources)


def run_daily(force=False, collector=collect_all):
    date = today_shanghai()
    json_path, _markdown = digest_paths(date)
    if json_path.exists() and not force:
        print(f"{date} 已有日报，跳过")
        return
    try:
        payload, markdown = _build(date, collector)
        alert = format_alerts(payload["news"], payload["jobs"])
        if alert:
            _notify(alert)
        _notify(markdown)
        save_digest(date, payload, markdown)
        seen = load_seen_jobs()
        seen.extend(norm_link(job["link"]) for job in payload["jobs"])
        save_seen_jobs(seen)
        print(f"已生成 {date}，新闻 {len(payload['news'])} 条，岗位 {len(payload['jobs'])} 条")
    except Exception:
        if not json_path.exists():
            try:
                _notify("今天的日报没有生成成功。材料里没有的内容不会被编造。可以到 GitHub 的 Actions 里查看原因。")
            except Exception as exc:
                print(f"失败通知没有发出去: {exc}")
        raise
