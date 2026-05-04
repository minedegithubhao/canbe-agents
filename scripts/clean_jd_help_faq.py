#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATE_LINE_RE = re.compile(r"^\s*(\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日)\s*$")
URL_RE = re.compile(r"https://help\.jd\.com/user/issue/(\d+)-(\d+)\.html")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_REF_RE = re.compile(r"[（(]?(如下图|如图|见下图|点击下图|图示如下|如下图所示|详见下图)[）)]?[：:]?")
QA_Q_RE = re.compile(r"^\s*Q(?:\d+)?[：:]\s*(.+?)\s*$", re.I)
QA_A_RE = re.compile(r"^\s*A(?:\d+)?[：:]\s*(.*?)\s*$", re.I)
QA_INLINE_RE = re.compile(r"^\s*Q\d+\s*[：:.]\s*(.+?)\s*$", re.I)
SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)、\s*(.{2,30}?)\s*$")
CN_SECTION_RE = re.compile(r"^\s*([一二三四五六七八九十]+)、\s*(.{2,30}?)\s*$")
NUMBERED_QUESTION_RE = re.compile(r"^\s*\d+[、.]\s*(.{4,80}?)\s*$")
CHINESE_DATE_RE = re.compile(r"(\d{4})年[【\[]?(\d{1,2})[】\]]?月[【\[]?(\d{1,2})[】\]]?日")
ISO_DATE_RE = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})")


BOILERPLATE_PATTERNS = [
    re.compile(r"^如有疑问[，,]?(您)?可以联系.*客服.*[。.]?$"),
    re.compile(r"^如需帮助[，,]?(请)?联系.*客服.*[。.]?$"),
    re.compile(r"^详情可咨询.*客服.*[。.]?$"),
    re.compile(r"^具体.*可联系.*客服.*[。.]?$"),
]


@dataclass
class SourceEntry:
    line: int
    category_l1: str
    category_l2: str
    category_l3: str
    question: str
    url: str
    answer_raw: str


@dataclass
class CleanItem:
    id: str
    url: str
    category_l1: str
    category_l2: str
    category_l3: str
    category_path: str
    question: str
    answer_raw: str
    answer_clean: str | None
    embedding_text: str | None
    index_text: str | None
    doc_type: str
    status: str
    search_enabled: bool
    page_date: str | None
    effective_date: str | None
    expired_date: str | None
    exported_at: str
    source_line: int
    source_type: str = "detail_page"
    parent_id: str | None = None
    section_path: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    removed_boilerplate: list[str] = field(default_factory=list)
    has_image_reference: bool = False
    image_missing: bool = False
    duplicate_group_id: str | None = None
    duplicate_of: str | None = None
    content_hash: str | None = None
    chunk_count: int = 0
    embedded_qa_count: int = 0


@dataclass
class ChunkItem:
    id: str
    parent_id: str
    chunk_index: int
    url: str
    category_l1: str
    category_l2: str
    category_l3: str
    question: str
    chunk_title: str
    chunk_text: str
    embedding_text: str
    index_text: str
    doc_type: str
    status: str
    search_enabled: bool
    quality_flags: list[str]


def normalize_text(text: str) -> str:
    text = (text or "").replace("\xa0", " ").replace("\u3000", " ").replace("\u200b", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ").replace("\u3000", " ")).strip()


def item_id_from_url(url: str) -> str:
    match = URL_RE.search(url)
    if not match:
        return "jd_help_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"jd_help_{match.group(1)}_{match.group(2)}"


def parse_markdown(path: Path) -> list[SourceEntry]:
    lines = path.read_text(encoding="utf-8").splitlines()
    current_h1 = ""
    current_h2 = ""
    current_h3 = ""
    current: dict[str, Any] | None = None
    entries: list[SourceEntry] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        answer_lines = current["answer_lines"]
        answer_raw = "\n".join(answer_lines).strip()
        if current.get("url") and answer_raw:
            entries.append(
                SourceEntry(
                    line=current["line"],
                    category_l1=current["category_l1"] or "未分类",
                    category_l2=current["category_l2"] or "全部",
                    category_l3=current["category_l3"] or "全部",
                    question=current["question"],
                    url=current["url"],
                    answer_raw=answer_raw,
                )
            )
        current = None

    for index, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level <= 3:
                flush()
                if level == 1:
                    current_h1, current_h2, current_h3 = title, "", ""
                elif level == 2:
                    current_h2, current_h3 = title, ""
                elif level == 3:
                    current_h3 = title
                continue
            if level == 4:
                flush()
                current = {
                    "line": index,
                    "category_l1": current_h1,
                    "category_l2": current_h2 or "全部",
                    "category_l3": current_h3 or "全部",
                    "question": title,
                    "url": "",
                    "answer_lines": [],
                }
                continue
        if current is None:
            continue
        if line.startswith("url:"):
            current["url"] = line.split("url:", 1)[1].strip()
            continue
        current["answer_lines"].append(line)

    flush()
    return entries


def extract_page_date(lines: list[str]) -> tuple[str | None, list[str]]:
    cleaned = list(lines)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    if cleaned and DATE_LINE_RE.match(cleaned[-1]):
        return normalize_date(cleaned[-1]), cleaned[:-1]
    return None, cleaned


def normalize_date(text: str) -> str | None:
    text = normalize_line(text).replace("【", "").replace("】", "")
    match = ISO_DATE_RE.search(text) or CHINESE_DATE_RE.search(text)
    if not match:
        return None
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_effective_and_expired(question: str, answer: str) -> tuple[str | None, str | None]:
    combined = f"{question}\n{answer}"
    effective_date: str | None = None
    expired_date: str | None = None

    range_match = re.search(
        r"(\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2})\s*[-至]\s*(\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2})",
        combined,
    )
    if range_match:
        effective_date = normalize_date(range_match.group(1))
        expired_date = normalize_date(range_match.group(2))

    for line in combined.splitlines():
        normalized = normalize_line(line)
        if "生效" in normalized:
            effective_date = effective_date or normalize_date(normalized)
        if "失效" in normalized or "有效期截止" in normalized:
            expired_date = expired_date or normalize_date(normalized)
    return effective_date, expired_date


def clean_answer_text(answer_raw: str) -> tuple[str, str | None, list[str], list[str], bool]:
    page_date, lines = extract_page_date(answer_raw.splitlines())
    result_lines: list[str] = []
    removed_boilerplate: list[str] = []
    flags: list[str] = []
    has_image_reference = False

    for raw_line in lines:
        line = normalize_line(raw_line)
        if not line:
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            continue
        had_image_ref = bool(IMAGE_REF_RE.search(line))
        if had_image_ref:
            has_image_reference = True
            line = normalize_line(IMAGE_REF_RE.sub("", line))
            flags.append("missing_image_context")
        if not line:
            continue
        if is_boilerplate(line):
            removed_boilerplate.append(line)
            continue
        result_lines.append(line)

    answer_clean = normalize_text("\n".join(result_lines))
    flags = sorted(set(flags))
    return answer_clean, page_date, flags, removed_boilerplate, has_image_reference


def is_boilerplate(line: str) -> bool:
    return any(pattern.match(line) for pattern in BOILERPLATE_PATTERNS)


def classify_doc_type(question: str, answer_clean: str, quality_flags: list[str]) -> str:
    text = f"{question}\n{answer_clean}"
    if "已失效" in question or "历史规则" in question or "失效" in question:
        return "historical_rule"
    if "compound_qa_source" in quality_flags:
        return "compound_qa"
    if any(word in question for word in ("协议", "隐私政策", "授权须知")):
        return "agreement"
    if any(word in question for word in ("运费", "收费", "补偿标准", "服务费", "违约金")):
        return "fee_standard"
    if any(word in question for word in ("如何", "怎么", "流程", "步骤")):
        return "operation_guide"
    if any(word in question for word in ("服务说明", "服务介绍", "什么是", "介绍")):
        return "service_intro"
    if any(word in question for word in ("规则", "细则", "须知", "标准")) or "规则" in text[:300]:
        return "policy_rule"
    return "faq"


def detect_quality_flags(question: str, answer_clean: str, doc_type: str, flags: list[str]) -> list[str]:
    result = set(flags)
    if len(answer_clean) < 80:
        result.add("short_answer")
    if len(answer_clean) > 3000 and doc_type in {"agreement", "historical_rule", "policy_rule"}:
        result.add("long_policy_text")
    if is_table_candidate(answer_clean):
        result.add("table_candidate")
    if doc_type == "historical_rule":
        result.add("historical_content")
    return sorted(result)


def is_table_candidate(text: str) -> bool:
    tokens = ("订单实付金额", "限重", "续重费", "部分城市", "其他地区", "服务费", "违约金", "费率")
    return sum(1 for token in tokens if token in text) >= 3


def build_embedding_text(item: CleanItem, answer: str | None = None) -> str | None:
    body = normalize_text(answer if answer is not None else item.answer_clean or "")
    if not body:
        return None
    section = f"\n章节：{item.section_path}" if item.section_path else ""
    return f"{item.category_path}{section}\n问题：{item.question}\n答案：{body}"


def build_index_text(item: CleanItem, answer: str | None = None) -> str | None:
    body = normalize_text(answer if answer is not None else item.answer_clean or "")
    if not body:
        return None
    tokens = [
        item.category_l1,
        item.category_l2,
        item.category_l3,
        item.section_path or "",
        item.question,
        body,
        f"source_url:{item.url}",
    ]
    return normalize_line(" ".join(token for token in tokens if token))


def extract_embedded_qas(entry: SourceEntry) -> list[dict[str, str]]:
    lines = [normalize_line(line) for line in entry.answer_raw.splitlines()]
    qas: list[dict[str, str]] = []
    current_question: str | None = None
    answer_lines: list[str] = []
    major_section = ""
    minor_section = ""

    def flush() -> None:
        nonlocal current_question, answer_lines
        if current_question and answer_lines:
            answer = normalize_text("\n".join(answer_lines))
            if answer:
                section_path = " > ".join(part for part in (major_section, minor_section) if part)
                qas.append({"question": current_question, "answer": answer, "section_path": section_path})
        current_question = None
        answer_lines = []

    for line in lines:
        if not line:
            continue
        inline_qa = parse_inline_qa(line)
        if inline_qa:
            flush()
            qas.append(
                {
                    "question": inline_qa[0],
                    "answer": inline_qa[1],
                    "section_path": " > ".join(part for part in (major_section, minor_section) if part),
                }
            )
            continue
        q_match = QA_Q_RE.match(line)
        a_match = QA_A_RE.match(line)
        section_match = SECTION_RE.match(line)
        cn_section_match = CN_SECTION_RE.match(line)
        numbered_question_match = NUMBERED_QUESTION_RE.match(line)
        if current_question and is_new_qa_section(line):
            flush()
            section_match = SECTION_RE.match(line)
            cn_section_match = CN_SECTION_RE.match(line)
        if cn_section_match and current_question is None:
            title = cn_section_match.group(2).strip()
            major_section = title
            minor_section = ""
            continue
        if section_match and current_question is None:
            number = section_match.group(1)
            title = section_match.group(2).strip()
            if "." in number:
                minor_section = title
            else:
                major_section = title
                minor_section = ""
            continue
        if (
            numbered_question_match
            and is_common_question_section(major_section, minor_section)
            and is_question_like(numbered_question_match.group(1))
        ):
            flush()
            current_question = normalize_line(numbered_question_match.group(1)).rstrip("？?")
            continue
        if q_match:
            flush()
            current_question = normalize_line(q_match.group(1)).rstrip("？?：:")
            continue
        if a_match and current_question:
            answer = normalize_line(a_match.group(1))
            if answer:
                answer_lines.append(answer)
            continue
        if current_question:
            answer_lines.append(line)
    flush()
    return qas


def parse_inline_qa(line: str) -> tuple[str, str] | None:
    match = QA_INLINE_RE.match(line)
    if not match:
        return None
    text = normalize_line(match.group(1))
    question = ""
    answer = ""
    qmark_positions = [pos for pos in (text.find("？"), text.find("?")) if pos >= 0]
    if qmark_positions:
        split_at = min(qmark_positions) + 1
        question = text[:split_at].strip().rstrip("？?")
        answer = text[split_at:].strip()
    else:
        section_match = re.search(r"\s([一二三四五六七八九十]+、|\\d+[、.])", text)
        if section_match:
            question = text[: section_match.start()].strip().rstrip("：:")
            answer = text[section_match.start() :].strip()
    if question and answer:
        return question, answer
    return None


def extract_embedded_sections(entry: SourceEntry) -> list[dict[str, str]]:
    lines = [normalize_line(line) for line in entry.answer_raw.splitlines()]
    sections: list[dict[str, str]] = []
    current_title: str | None = None
    body_lines: list[str] = []
    in_common_question_section = False

    def flush() -> None:
        nonlocal current_title, body_lines
        if current_title and body_lines and "常见问题" not in current_title:
            body = normalize_text("\n".join(body_lines))
            if len(body) >= 20:
                sections.append({"title": current_title, "answer": body, "section_path": current_title})
        current_title = None
        body_lines = []

    for line in lines:
        if not line:
            continue
        numbered_match = NUMBERED_QUESTION_RE.match(line)
        if in_common_question_section and numbered_match and is_question_like(numbered_match.group(1)):
            flush()
            continue
        if in_common_question_section and not (SECTION_RE.match(line) or CN_SECTION_RE.match(line)):
            continue
        section_match = SECTION_RE.match(line) or CN_SECTION_RE.match(line)
        if section_match:
            flush()
            title = section_match.group(2).strip()
            in_common_question_section = "常见问题" in title
            current_title = None if in_common_question_section else title
            continue
        if QA_Q_RE.match(line) or QA_A_RE.match(line) or (NUMBERED_QUESTION_RE.match(line) and is_question_like(NUMBERED_QUESTION_RE.match(line).group(1))):
            flush()
            continue
        if current_title:
            body_lines.append(line)
    flush()
    return sections


def has_numbered_qa_source(entry: SourceEntry) -> bool:
    lines = [normalize_line(line) for line in entry.answer_raw.splitlines()]
    in_common_section = False
    count = 0
    for line in lines:
        match = NUMBERED_QUESTION_RE.match(line)
        if in_common_section and match and is_question_like(match.group(1)):
            count += 1
            continue
        section_match = SECTION_RE.match(line) or CN_SECTION_RE.match(line)
        if section_match:
            in_common_section = "常见问题" in section_match.group(2)
            continue
    return count >= 2


def is_new_qa_section(line: str) -> bool:
    match = SECTION_RE.match(line) or CN_SECTION_RE.match(line)
    if not match:
        return False
    title = match.group(2)
    return title.endswith("问题") or title in {"发票问题", "账户问题", "还款问题", "结算问题", "使用问题"}


def is_common_question_section(major_section: str, minor_section: str) -> bool:
    return "常见问题" in major_section or "常见问题" in minor_section


def is_question_like(text: str) -> bool:
    text = normalize_line(text)
    if text.endswith(("？", "?")):
        return True
    question_markers = ("是否", "如何", "怎么", "什么", "哪些", "为何", "为什么", "能否", "可以", "支持", "怎么回事", "处理", "支付方式")
    return any(marker in text for marker in question_markers)


def clean_entries(entries: list[SourceEntry], exported_at: str) -> list[CleanItem]:
    items: list[CleanItem] = []
    for entry in entries:
        base_id = item_id_from_url(entry.url)
        answer_clean, page_date, initial_flags, removed, has_image_ref = clean_answer_text(entry.answer_raw)
        embedded_qas = extract_embedded_qas(entry)
        embedded_sections = extract_embedded_sections(entry)
        compound = len(embedded_qas) >= 2
        quality_flags = list(initial_flags)
        if compound:
            quality_flags.append("compound_qa_source")
            if has_numbered_qa_source(entry):
                quality_flags.append("numbered_qa_source")
        effective_date, expired_date = extract_effective_and_expired(entry.question, answer_clean)
        doc_type = classify_doc_type(entry.question, answer_clean, quality_flags)
        status = "expired" if doc_type == "historical_rule" or expired_date else "active"
        search_enabled = doc_type != "compound_qa" and status != "expired"
        quality_flags = detect_quality_flags(entry.question, answer_clean, doc_type, quality_flags)

        item = CleanItem(
            id=base_id,
            url=entry.url,
            category_l1=entry.category_l1,
            category_l2=entry.category_l2,
            category_l3=entry.category_l3,
            category_path=f"{entry.category_l1} > {entry.category_l2} > {entry.category_l3}",
            question=entry.question,
            answer_raw=entry.answer_raw,
            answer_clean=None if compound else answer_clean,
            embedding_text=None,
            index_text=None,
            doc_type=doc_type,
            status=status,
            search_enabled=search_enabled,
            page_date=page_date,
            effective_date=effective_date,
            expired_date=expired_date,
            exported_at=exported_at,
            source_line=entry.line,
            quality_flags=quality_flags,
            removed_boilerplate=removed,
            has_image_reference=has_image_ref,
            image_missing=has_image_ref,
            content_hash=sha256(answer_clean),
            embedded_qa_count=len(embedded_qas) if compound else 0,
        )
        item.embedding_text = build_embedding_text(item)
        item.index_text = build_index_text(item)
        items.append(item)

        if compound:
            for idx, section in enumerate(embedded_sections, start=1):
                section_answer, _, section_flags, section_removed, section_image_ref = clean_answer_text(section["answer"])
                section_doc_type = classify_doc_type(section["title"], section_answer, section_flags)
                section_child = CleanItem(
                    id=f"{base_id}_section_{idx:03d}",
                    parent_id=base_id,
                    url=entry.url,
                    category_l1=entry.category_l1,
                    category_l2=entry.category_l2,
                    category_l3=entry.category_l3,
                    category_path=f"{entry.category_l1} > {entry.category_l2} > {entry.category_l3}",
                    question=section["title"],
                    answer_raw=section["answer"],
                    answer_clean=section_answer,
                    embedding_text=None,
                    index_text=None,
                    doc_type=section_doc_type,
                    status="active",
                    search_enabled=True,
                    page_date=page_date,
                    effective_date=None,
                    expired_date=None,
                    exported_at=exported_at,
                    source_line=entry.line,
                    source_type="embedded_section",
                    section_path=section["section_path"],
                    quality_flags=detect_quality_flags(section["title"], section_answer, section_doc_type, section_flags),
                    removed_boilerplate=section_removed,
                    has_image_reference=section_image_ref,
                    image_missing=section_image_ref,
                    content_hash=sha256(section_answer),
                )
                section_child.embedding_text = build_embedding_text(section_child)
                section_child.index_text = build_index_text(section_child)
                items.append(section_child)
            for idx, qa in enumerate(embedded_qas, start=1):
                child_answer, _, child_flags, child_removed, child_image_ref = clean_answer_text(qa["answer"])
                child = CleanItem(
                    id=f"{base_id}_qa_{idx:03d}",
                    parent_id=base_id,
                    url=entry.url,
                    category_l1=entry.category_l1,
                    category_l2=entry.category_l2,
                    category_l3=entry.category_l3,
                    category_path=f"{entry.category_l1} > {entry.category_l2} > {entry.category_l3}",
                    question=qa["question"],
                    answer_raw=qa["answer"],
                    answer_clean=child_answer,
                    embedding_text=None,
                    index_text=None,
                    doc_type=classify_doc_type(qa["question"], child_answer, child_flags),
                    status="active",
                    search_enabled=True,
                    page_date=page_date,
                    effective_date=None,
                    expired_date=None,
                    exported_at=exported_at,
                    source_line=entry.line,
                    source_type="embedded_qa",
                    section_path=qa["section_path"] or None,
                    quality_flags=detect_quality_flags(qa["question"], child_answer, "faq", child_flags),
                    removed_boilerplate=child_removed,
                    has_image_reference=child_image_ref,
                    image_missing=child_image_ref,
                    content_hash=sha256(child_answer),
                )
                child.embedding_text = build_embedding_text(child)
                child.index_text = build_index_text(child)
                items.append(child)

    apply_duplicate_marks(items)
    return items


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def apply_duplicate_marks(items: list[CleanItem]) -> None:
    groups: dict[str, list[CleanItem]] = {}
    for item in items:
        groups.setdefault(item.question, []).append(item)
    for question, group in groups.items():
        if len(group) <= 1:
            continue
        group_id = "dup_" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]
        first_by_hash: dict[str, CleanItem] = {}
        for item in group:
            item.duplicate_group_id = group_id
            if item.content_hash in first_by_hash:
                item.duplicate_of = first_by_hash[item.content_hash].id
            else:
                first_by_hash[item.content_hash or item.id] = item


def build_chunks(items: list[CleanItem]) -> list[ChunkItem]:
    chunks: list[ChunkItem] = []
    for item in items:
        if item.doc_type == "compound_qa":
            continue
        answer = item.answer_clean or ""
        if not answer:
            continue
        parts = split_answer(answer)
        item.chunk_count = len(parts)
        for idx, part in enumerate(parts, start=1):
            title = item.question if len(parts) == 1 else f"{item.question} - {idx}"
            embedding = build_embedding_text(item, part) or ""
            index = build_index_text(item, part) or ""
            chunks.append(
                ChunkItem(
                    id=f"{item.id}_chunk_{idx:03d}",
                    parent_id=item.id,
                    chunk_index=idx,
                    url=item.url,
                    category_l1=item.category_l1,
                    category_l2=item.category_l2,
                    category_l3=item.category_l3,
                    question=item.question,
                    chunk_title=title,
                    chunk_text=part,
                    embedding_text=embedding,
                    index_text=index,
                    doc_type=item.doc_type,
                    status=item.status,
                    search_enabled=item.search_enabled,
                    quality_flags=item.quality_flags,
                )
            )
    return chunks


def split_answer(answer: str, target_size: int = 1200, hard_size: int = 3000) -> list[str]:
    answer = normalize_text(answer)
    if len(answer) <= target_size:
        return [answer]
    paragraphs = [part.strip() for part in answer.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    limit = target_size if len(answer) <= hard_size else 1600
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) > limit:
            chunks.append(normalize_text("\n\n".join(current)))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        chunks.append(normalize_text("\n\n".join(current)))
    return chunks or [answer]


def write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def render_cleaned_markdown(items: list[CleanItem]) -> str:
    tree: dict[str, Any] = OrderedDict()
    for item in items:
        if item.doc_type == "compound_qa":
            continue
        node = tree.setdefault(item.category_l1, OrderedDict())
        node = node.setdefault(item.category_l2, OrderedDict())
        node = node.setdefault(item.category_l3, [])
        node.append(item)

    lines = ["# 京东帮助中心 FAQ 清洗版", ""]
    for h1, level2 in tree.items():
        lines.extend([f"# {h1}", ""])
        for h2, level3 in level2.items():
            lines.extend([f"## {h2}", ""])
            for h3, docs in level3.items():
                lines.extend([f"### {h3}", ""])
                for item in docs:
                    lines.extend(
                        [
                            f"#### {item.question}",
                            "",
                            f"url: {item.url}",
                            f"doc_type: {item.doc_type}",
                            f"status: {item.status}",
                            "",
                            item.answer_clean or "",
                            "",
                        ]
                    )
    return "\n".join(lines).rstrip() + "\n"


def build_quality_report(source_entries: list[SourceEntry], items: list[CleanItem], chunks: list[ChunkItem], source: str) -> dict[str, Any]:
    flag_counts: dict[str, int] = {}
    doc_type_counts: dict[str, int] = {}
    for item in items:
        doc_type_counts[item.doc_type] = doc_type_counts.get(item.doc_type, 0) + 1
        for flag in item.quality_flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    removed_examples = [
        {"url": item.url, "question": item.question, "text": text}
        for item in items
        for text in item.removed_boilerplate
    ][:20]
    return {
        "source": source,
        "source_entry_count": len(source_entries),
        "clean_item_count": len(items),
        "chunk_count": len(chunks),
        "search_enabled_count": sum(1 for item in items if item.search_enabled),
        "doc_type_counts": doc_type_counts,
        "quality_flag_counts": flag_counts,
        "removed_boilerplate_count": sum(len(item.removed_boilerplate) for item in items),
        "removed_boilerplate_examples": removed_examples,
        "compound_qa_parent_count": sum(1 for item in items if item.doc_type == "compound_qa"),
        "embedded_qa_count": sum(1 for item in items if item.source_type == "embedded_qa"),
        "embedded_section_count": sum(1 for item in items if item.source_type == "embedded_section"),
        "expired_count": sum(1 for item in items if item.status == "expired"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean exported JD Help FAQ Markdown into structured knowledge files.")
    parser.add_argument("--input", default="exports/jd_help_faq.md")
    parser.add_argument("--cleaned-jsonl", default="exports/jd_help_faq.cleaned.jsonl")
    parser.add_argument("--chunks-jsonl", default="exports/jd_help_faq.chunks.jsonl")
    parser.add_argument("--cleaned-md", default="exports/jd_help_faq.cleaned.md")
    parser.add_argument("--quality-report", default="exports/jd_help_faq_quality_report.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    exported_at = datetime.now(timezone.utc).isoformat()
    entries = parse_markdown(input_path)
    items = clean_entries(entries, exported_at)
    chunks = build_chunks(items)

    write_jsonl(Path(args.cleaned_jsonl), items)
    write_jsonl(Path(args.chunks_jsonl), chunks)
    Path(args.cleaned_md).write_text(render_cleaned_markdown(items), encoding="utf-8")
    report = build_quality_report(entries, items, chunks, str(input_path))
    Path(args.quality_report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
