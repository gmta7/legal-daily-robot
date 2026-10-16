import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_config():
    path = Path(os.environ.get("LEGAL_DAILY_CONFIG", ROOT / "config.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"缺少配置文件 {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件不是合法 JSON：{path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("配置文件的最外层必须是对象")
    return data


def reader():
    return load_config().get("reader") or {}


def job_settings():
    return load_config().get("jobs") or {}


def news_settings():
    return load_config().get("news") or {}


def journals():
    names = []
    for name in load_config().get("journals") or []:
        cleaned = str(name).strip().strip("《》\"' ")
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return tuple(names)


def fresh_graduate_only():
    return bool(job_settings().get("fresh_graduate_only", True))


def job_limit():
    try:
        return max(1, int(job_settings().get("max_items", 5)))
    except (TypeError, ValueError):
        return 5


def news_limit():
    try:
        return max(1, int(news_settings().get("max_items", 8)))
    except (TypeError, ValueError):
        return 8


def regions():
    return [str(name).strip() for name in (news_settings().get("regions") or []) if str(name).strip()]


def enabled_companies():
    return [str(name).strip() for name in (job_settings().get("companies") or []) if str(name).strip()]


def _strings(value):
    found = []
    for item in value or []:
        text = str(item).strip()
        if text and text not in found:
            found.append(text)
    return tuple(found)


def _text(key, fallback):
    value = str(load_config().get(key) or "").strip()
    return value or fallback


def product_name():
    return _text("product_name", "法律日报")


def digest_title():
    return _text("digest_title", product_name())


def research_daily_title():
    return _text("research_daily_title", "专题材料")


def research_weekly_title():
    return _text("research_weekly_title", "期刊目录")


def topic_label():
    return _text("topic_label", "主题")


def topics():
    return _strings(load_config().get("topics"))


def news_queries():
    return _strings(load_config().get("news_queries"))


def job_queries():
    return _strings(load_config().get("job_queries"))


def research_queries():
    return _strings(load_config().get("research_queries"))


def news_terms():
    return _strings(load_config().get("news_terms")) or topics()


def job_title_terms():
    return _strings(load_config().get("job_title_terms")) or ("法务", "律师", "法律")


def job_search_terms():
    return _strings(load_config().get("job_search_terms")) or job_title_terms()


def job_topic_terms():
    return _strings(load_config().get("job_topic_terms")) or topics()


def journal_topics():
    return _strings(load_config().get("journal_topics")) or topics()
