#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup


START_URL = "https://help.jd.com/user/issue.html"
HEADERS = {
    "User-Agent": "faq-rag-public-data-export/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
NOISE_TITLES = {"全部", "下载该帮助文档"}


@dataclass
class FaqDoc:
    url: str
    category_l1: str
    category_l2: str
    category_l3: str
    question: str
    answer: str

    @property
    def category_path(self) -> tuple[str, str, str]:
        return (self.category_l1, self.category_l2, self.category_l3)


def canonical_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    if not parts.scheme and parts.netloc:
        scheme = "https"
    else:
        scheme = parts.scheme.lower()
    return f"{scheme}://{parts.netloc.lower()}{parts.path}"


def normalize_url(url: str, base_url: str = START_URL) -> str:
    return canonical_url(urljoin(base_url, url))


def is_issue_url(url: str) -> bool:
    url = canonical_url(url)
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc == "help.jd.com" and (
        parts.path == "/user/issue.html" or (parts.path.startswith("/user/issue/") and parts.path.endswith(".html"))
    )


def is_list_url(url: str) -> bool:
    return "/user/issue/list-" in canonical_url(url)


def is_detail_url(url: str) -> bool:
    url = canonical_url(url)
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == "help.jd.com"
        and parts.path.startswith("/user/issue/")
        and parts.path.endswith(".html")
        and "/list-" not in parts.path
    )


def clean_text(text: str) -> str:
    text = (text or "").replace("\xa0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def markdown_escape_heading(text: str) -> str:
    return clean_text(text).replace("\n", " ").strip() or "未分类"


def markdown_escape_text(text: str) -> str:
    return clean_text(text)


def decode_response(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "gbk" in content_type or "gb2312" in content_type:
        return response.content.decode("gbk", errors="replace")
    response.encoding = response.encoding or "utf-8"
    return response.text


async def polite_get(client: httpx.AsyncClient, url: str, delay_min: float, delay_max: float) -> str:
    await asyncio.sleep(random.uniform(delay_min, delay_max))
    response = await client.get(url)
    response.raise_for_status()
    return decode_response(response)


def extract_sidebar_paths(soup: BeautifulSoup, base_url: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for item in soup.select(".subside-list li.list-item[data-id]"):
        link = item.find("a", href=True)
        if not link:
            continue
        url = normalize_url(str(link["href"]), base_url)
        if not is_list_url(url):
            continue
        parent = clean_text(str(item.get("data-parent-name") or ""))
        name = clean_text(str(item.get("data-name") or link.get_text(" ", strip=True)))
        path = tuple(part for part in (parent, name) if part)
        if path:
            result[url] = path
    return result


def extract_tab_paths(soup: BeautifulSoup, base_url: str, current_path: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    if not current_path:
        return result
    for link in soup.select("#all-ques-tab .tab a[href]"):
        name = clean_text(link.get_text(" ", strip=True))
        url = normalize_url(str(link["href"]), base_url)
        if not is_list_url(url) or not name or name in NOISE_TITLES:
            continue
        result[url] = (*current_path, name)
    return result


def extract_issue_links(soup: BeautifulSoup, base_url: str, current_path: tuple[str, ...]) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    detail_paths: dict[str, tuple[str, ...]] = {}
    detail_titles: dict[str, str] = {}
    for link in soup.select("#all-ques-tab .help_list a[href]"):
        text = clean_text(link.get_text(" ", strip=True)).lstrip("·").strip()
        url = normalize_url(str(link["href"]), base_url)
        if not is_issue_url(url):
            continue
        if is_detail_url(url):
            detail_paths[url] = current_path
            if text:
                detail_titles[url] = text
    return detail_paths, detail_titles


def extract_current_category(soup: BeautifulSoup, url: str, current_path: tuple[str, ...]) -> tuple[str, str, str]:
    parts = list(normalize_category_path(current_path))
    current_tab = clean_text(soup.select_one(".currentCata").get_text(" ", strip=True)) if soup.select_one(".currentCata") else ""
    if current_tab:
        parts[2] = current_tab
    return (parts[0], parts[1], parts[2])


def extract_detail_category(soup: BeautifulSoup) -> tuple[str, str, str]:
    cat_id = extract_detail_cat_id(soup)
    category_l1 = ""
    category_l2 = ""
    if cat_id:
        item = soup.select_one(f'li.list-item[data-id="{cat_id}"]')
        if item:
            category_l1 = clean_text(str(item.get("data-parent-name") or ""))
            category_l2 = clean_text(str(item.get("data-name") or ""))

    category_l3 = extract_detail_breadcrumb_l3(soup)
    return normalize_category_path((category_l1, category_l2, category_l3))


def extract_detail_cat_id(soup: BeautifulSoup) -> str:
    scripts = "\n".join(script.get_text("\n", strip=False) for script in soup.find_all("script"))
    patterns = [
        r"list-item\[data-id\s*=\s*(\d+)\]",
        r"list-item\[data-id\s*=\s*['\"]?(\d+)['\"]?\]",
    ]
    for pattern in patterns:
        match = re.search(pattern, scripts)
        if match:
            return match.group(1)
    link = soup.select_one('.breadcrumb a[href*="/user/issue/list-"]')
    if link:
        match = re.search(r"list-(\d+)(?:-\d+)?\.html", str(link.get("href") or ""))
        if match:
            return match.group(1)
    return ""


def extract_detail_breadcrumb_l3(soup: BeautifulSoup) -> str:
    for link in soup.select('.breadcrumb a[href*="/user/issue/list-"]'):
        href = str(link.get("href") or "")
        text = clean_text(link.get_text(" ", strip=True))
        if re.search(r"list-\d+-\d+\.html", href) and text:
            return text
    return "全部"


def extract_detail(html: str, url: str, fallback_question: str = "") -> FaqDoc | None:
    soup = BeautifulSoup(html, "lxml")
    category_l1, category_l2, category_l3 = extract_detail_category(soup)
    container = soup.select_one("#pdfContainer .contxt") or soup.select_one(".contxt")
    if not container:
        return None
    for tag in container(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for img in container.find_all("img"):
        img.decompose()
    title_node = container.select_one(".help-tit1") or container.find(["h1", "h2", "h3"])
    question = clean_text(title_node.get_text(" ", strip=True) if title_node else fallback_question)
    if not question:
        return None
    if title_node:
        title_node.decompose()
    lines: list[str] = []
    for block in container.find_all(["p", "div", "li", "tr"], recursive=True):
        if block.find(["p", "div", "li", "tr"]):
            continue
        text = clean_text(block.get_text(" ", strip=True))
        if text and text != question:
            lines.append(text)
    if not lines:
        text = clean_text(container.get_text("\n", strip=True))
        lines = [line for line in text.splitlines() if line.strip() and line.strip() != question]
    answer = clean_text("\n\n".join(OrderedDict.fromkeys(lines)))
    answer = strip_detail_tail(answer)
    if len(answer) < 4:
        return None
    return FaqDoc(
        url=url,
        category_l1=category_l1,
        category_l2=category_l2,
        category_l3=category_l3,
        question=question,
        answer=answer,
    )


def strip_detail_tail(answer: str) -> str:
    stop_patterns = [
        "这条帮助是否解决了您的问题？",
        "已有",
        "品类齐全，轻松购物",
        "多仓直发，极速配送",
        "正品行货，精致服务",
        "天天低价，畅选无忧",
    ]
    cut = len(answer)
    for pattern in stop_patterns:
        index = answer.find(pattern)
        if index >= 0:
            cut = min(cut, index)
    return clean_text(answer[:cut])


def insert_tree(tree: dict[str, Any], doc: FaqDoc) -> None:
    node = tree
    for part in normalize_category_path(doc.category_path):
        node = node.setdefault(part, OrderedDict())
    node.setdefault("__items__", []).append(doc)


def normalize_category_path(path: tuple[str, ...]) -> tuple[str, str, str]:
    parts = [clean_text(part) for part in path if clean_text(part)]
    if not parts:
        parts = ["未分类"]
    parts = parts[:3]
    while len(parts) < 3:
        parts.append("全部")
    return (parts[0], parts[1], parts[2])


def render_tree(tree: dict[str, Any], level: int = 1) -> list[str]:
    lines: list[str] = []
    for key, value in tree.items():
        if key == "__items__":
            for doc in value:
                lines.append(f"#### {markdown_escape_heading(doc.question)}")
                lines.append("")
                lines.append(f"url: {doc.url}")
                lines.append("")
                lines.append(markdown_escape_text(doc.answer))
                lines.append("")
            continue
        lines.append(f"{'#' * min(level, 6)} {markdown_escape_heading(str(key))}")
        lines.append("")
        lines.extend(render_tree(value, level + 1))
    return lines


async def export_markdown(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output)
    stats_output = Path(args.stats_output)
    start = time.monotonic()
    list_paths: dict[str, tuple[str, ...]] = {}
    detail_paths: dict[str, tuple[str, ...]] = {}
    detail_titles: dict[str, str] = {}
    seen_lists: set[str] = set()
    list_queue: deque[str] = deque([START_URL])
    errors: list[dict[str, str]] = []
    empty_categories: list[dict[str, Any]] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=args.timeout, follow_redirects=True) as client:
        while list_queue and len(seen_lists) < args.max_list_pages:
            url = list_queue.popleft()
            if url in seen_lists:
                continue
            seen_lists.add(url)
            try:
                html = await polite_get(client, url, args.delay_min, args.delay_max)
            except Exception as exc:
                errors.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
                continue
            soup = BeautifulSoup(html, "lxml")
            sidebar_paths = extract_sidebar_paths(soup, url)
            for path_url, path in sidebar_paths.items():
                list_paths.setdefault(path_url, path)
            current_path = list_paths.get(url, ())
            tab_paths = extract_tab_paths(soup, url, current_path)
            for path_url, path in tab_paths.items():
                list_paths[path_url] = path
            page_detail_paths, page_detail_titles = extract_issue_links(soup, url, current_path)
            if is_list_url(url) and not page_detail_paths:
                category_l1, category_l2, category_l3 = extract_current_category(soup, url, current_path)
                empty_categories.append(
                    {
                        "list_url": url,
                        "category_l1": category_l1,
                        "category_l2": category_l2,
                        "category_l3": category_l3,
                        "faq_count": 0,
                        "child_list_count": len(tab_paths),
                        "type": "category_only" if tab_paths else "empty_category",
                    }
                )
            for detail_url, path in page_detail_paths.items():
                if path and len(path) >= len(detail_paths.get(detail_url, ())):
                    detail_paths[detail_url] = path
            detail_titles.update(page_detail_titles)
            for next_url in sorted({*sidebar_paths.keys(), *tab_paths.keys()}):
                if next_url not in seen_lists and next_url not in list_queue:
                    list_queue.append(next_url)
            if len(seen_lists) % 50 == 0:
                print(
                    json.dumps(
                        {
                            "stage": "discover_lists",
                            "seenLists": len(seen_lists),
                            "queuedLists": len(list_queue),
                            "detailUrls": len(detail_paths),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        docs, detail_errors = await fetch_details_concurrently(client, detail_paths, detail_titles, args)
        errors.extend(detail_errors)

    tree: dict[str, Any] = OrderedDict()
    for doc in docs:
        insert_tree(tree, doc)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 京东帮助中心 FAQ 导出",
        "",
        f"- 数据源：{START_URL}",
        f"- 导出方式：重新访问官网列表页和详情页，不使用 Mongo 中的清洗结果",
        f"- FAQ 数量：{len(docs)}",
        f"- 详情页发现数：{len(detail_paths)}",
        "",
    ]
    lines.extend(render_tree(tree, level=1))
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    stats = {
        "source": START_URL,
        "output": str(output),
        "faqCount": len(docs),
        "discoveredDetailUrls": len(detail_paths),
        "seenListPages": len(seen_lists),
        "emptyCategories": empty_categories,
        "emptyCategoryCount": len(empty_categories),
        "errors": errors,
        "errorCount": len(errors),
        "elapsedSeconds": round(time.monotonic() - start, 2),
    }
    stats_output.parent.mkdir(parents=True, exist_ok=True)
    stats_output.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


async def fetch_details_concurrently(
    client: httpx.AsyncClient,
    detail_paths: dict[str, tuple[str, ...]],
    detail_titles: dict[str, str],
    args: argparse.Namespace,
) -> tuple[list[FaqDoc], list[dict[str, str]]]:
    urls = sorted(detail_paths)[: args.max_detail_pages]
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
    for index, url in enumerate(urls, start=1):
        queue.put_nowait((index, url))
    docs_by_index: dict[int, FaqDoc] = {}
    errors: list[dict[str, str]] = []
    lock = asyncio.Lock()
    progress = {"visited": 0}

    async def worker() -> None:
        while True:
            try:
                index, detail_url = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                html = await polite_get(client, detail_url, args.delay_min, args.delay_max)
                doc = extract_detail(
                    html,
                    detail_url,
                    fallback_question=detail_titles.get(detail_url, ""),
                )
                async with lock:
                    if doc:
                        docs_by_index[index] = doc
            except Exception as exc:
                async with lock:
                    errors.append({"url": detail_url, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                async with lock:
                    progress["visited"] += 1
                    visited = progress["visited"]
                    if visited % 50 == 0 or visited == len(urls):
                        print(
                            json.dumps(
                                {
                                    "stage": "fetch_details",
                                    "visitedDetails": visited,
                                    "exportedFaqs": len(docs_by_index),
                                    "errors": len(errors),
                                    "concurrency": args.concurrency,
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(max(1, args.concurrency))]
    await queue.join()
    for task in workers:
        task.cancel()
    return [docs_by_index[index] for index in sorted(docs_by_index)], errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export JD Help public FAQ pages to categorized Markdown.")
    parser.add_argument("--output", default="exports/jd_help_faq.md")
    parser.add_argument("--stats-output", default="exports/jd_help_faq_stats.json")
    parser.add_argument("--max-list-pages", type=int, default=5000)
    parser.add_argument("--max-detail-pages", type=int, default=5000)
    parser.add_argument("--delay-min", type=float, default=0.3)
    parser.add_argument("--delay-max", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    stats = asyncio.run(export_markdown(args))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
