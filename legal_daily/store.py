import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive"
STATE = ROOT / "state"


def _read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_paths(date):
    return ARCHIVE / f"{date}.json", ARCHIVE / f"{date}.md"


def load_digest(date):
    path, _markdown = digest_paths(date)
    if not path.exists():
        return None
    return _read_json(path, None)


def save_digest(date, payload, markdown):
    json_path, md_path = digest_paths(date)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    _write_json(json_path, payload)
    md_path.write_text(markdown, encoding="utf-8")


def research_paths(mode, key):
    folder = ARCHIVE / "research"
    return folder / f"{mode}-{key}.json", folder / f"{mode}-{key}.md"


def save_research(mode, key, payload, markdown):
    json_path, md_path = research_paths(mode, key)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(json_path, payload)
    md_path.write_text(markdown, encoding="utf-8")


def load_seen_research():
    return _read_json(STATE / "seen_research.json", [])


def save_seen_research(links):
    trimmed = list(dict.fromkeys(links))[-400:]
    _write_json(STATE / "seen_research.json", trimmed)


def latest_digest():
    files = sorted(ARCHIVE.glob("*.json"))
    if not files:
        return None
    return _read_json(files[-1], None)


def load_seen_jobs():
    return _read_json(STATE / "seen_jobs.json", [])


def save_seen_jobs(links):
    trimmed = list(dict.fromkeys(links))[-400:]
    _write_json(STATE / "seen_jobs.json", trimmed)


def load_delivery():
    return _read_json(STATE / "delivery.json", None)


def save_delivery(delivery):
    _write_json(STATE / "delivery.json", delivery)


def seen_message(message_id):
    if not message_id:
        return False
    payload = _read_json(STATE / "seen_messages.json", [])
    return message_id in payload


def remember_message(message_id):
    if not message_id:
        return
    payload = _read_json(STATE / "seen_messages.json", [])
    payload.append(message_id)
    _write_json(STATE / "seen_messages.json", payload[-300:])
