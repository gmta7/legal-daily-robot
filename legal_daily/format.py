DISCLAIMER = "以上为公开信息整理，供学习求职使用，不构成法律意见。"

SECTION_TITLES = (
    ("新规", "新规"),
    ("案件", "案件"),
    ("评论", "评论"),
    ("国外", "国外速览"),
)


def news_block(item):
    flag = "【重要】" if item.get("important") else ""
    lines = [
        f"{item['n']}. {flag}[{item['track']}·{item['category']}] {item['title_zh']}",
        item["one_line_zh"],
    ]
    lines.extend(f"· {point}" for point in item.get("points") or [])
    lines.append(f"对你：{item['for_you']}")
    lines.append(f"EN: {item['title_en']} — {item['one_line_en']}")
    lines.append(item["link"])
    return lines


def _job_label(job):
    parts = [job.get("employment") or "正式"]
    if job.get("experience"):
        parts.append(job["experience"])
    if job.get("tier"):
        parts.append(job["tier"])
    return "·".join(parts)


def job_block(job):
    deadline = f" | 截止 {job['deadline']}" if job.get("deadline") else ""
    city = job.get("city") or "城市材料未写明"
    lines = [
        f"岗位{job['n']}. [{_job_label(job)}] {job['org']} | {job['role']} | {city}{deadline}",
        job["practice"],
    ]
    if job.get("requirements"):
        lines.append("要求：" + "；".join(job["requirements"]))
    lines.append(f"EN: {job['one_line_en']}")
    lines.append(job["link"])
    return lines


def _source_lines(items, limit=10):
    lines = []
    for item in (items or [])[:limit]:
        mark = "·".join(part for part in (item.get("employment"), item.get("experience")) if part)
        title = item.get("title") or "无标题"
        if mark:
            title = f"{title} [{mark}]"
        lines.append(f"· {title}")
        if item.get("link"):
            lines.append(item["link"])
    extra = len(items or []) - limit
    if extra > 0:
        lines.append(f"其余 {extra} 条在当天的 archive JSON 里。")
    return lines


def format_digest(date, news, jobs, news_sources=None, job_sources=None):
    lines = [f"法律×AI 日报 | {date}", ""]
    if not news and news_sources:
        lines.extend(
            [
                "今天检索到了相关新闻，但没有筛进正文，所以还不能「展开第 N 条」。",
                "",
                "【检索到的新闻】",
            ]
        )
        lines.extend(_source_lines(news_sources))
        lines.append("")
    elif not news:
        lines.extend(["今日无重大更新 / No major update today.", ""])
    else:
        lines.append("【今日必读】")
        lines.extend(f"{item['n']}. {item['title_zh']}" for item in news[:3])
        lines.append("")
        for category, title in SECTION_TITLES:
            group = [item for item in news if item["category"] == category]
            if not group:
                continue
            lines.append(f"【{title}】")
            for item in group:
                lines.extend(news_block(item))
                lines.append("")
    lines.append("【岗位】")
    if not jobs and job_sources:
        lines.extend(
            [
                "没有收录成岗位，不能回复「展开岗位」。下面只保留标题里带招聘或实习、且和合规或法律科技有关的线索：",
                "",
            ]
        )
        lines.extend(_source_lines(job_sources, limit=8))
        lines.append("")
    elif not jobs:
        lines.append("今日无新岗位")
        lines.append("")
    else:
        lines.append("")
        for job in jobs:
            lines.extend(job_block(job))
            lines.append("")
    lines.append(DISCLAIMER)
    if news or jobs:
        lines.append("回复「展开第 2 条」看新闻，回复「展开岗位 1」看岗位。")
    return "\n".join(lines).strip() + "\n"


def format_alerts(news, jobs):
    bits = []
    for item in news or []:
        if item.get("important"):
            bits.append(f"{item['n']}. {item['title_zh']}\n{item['one_line_zh']}\n{item['link']}")
    for job in jobs or []:
        if job.get("alert"):
            bits.append(f"岗位{job['n']}. {job['org']} {job['role']}\n{job['practice']}\n{job['link']}")
    if not bits:
        return ""
    body = "\n\n".join(bits[:4])
    return f"重要变化\n\n{body}\n\n{DISCLAIMER}\n"


def format_expand(kind, number, title, payload, link):
    label = f"展开第 {number} 条" if kind == "news" else f"展开岗位 {number}"
    interview = payload.get("interview") or []
    interview_lines = [f"{index}. {text}" for index, text in enumerate(interview, start=1)]
    parts = [
        f"{label}｜{title}",
        "",
        "结构",
        payload.get("structure") or "材料没有写",
        "",
        "和既有规则的关系",
        payload.get("relation") or "材料没有写",
        "",
        "面试可以讲",
        "\n".join(interview_lines) or "材料没有写",
        "",
        "EN",
        payload.get("en") or "The source did not provide enough text.",
        "",
        link,
        "",
        DISCLAIMER,
    ]
    return "\n".join(parts).strip() + "\n"
