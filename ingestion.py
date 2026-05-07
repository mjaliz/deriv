from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass

from bs4 import BeautifulSoup
from loguru import logger

from models import (
    CorpusArtifact,
    CorpusDocumentStatus,
    CorpusSection,
    DocumentSource,
    FetchFailure,
    SourcesConfig,
)
from settings import Settings
from utils import normalize_text, stable_hash, utc_now


REMOVABLE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "form",
    "button",
    "input",
    "select",
    "nav",
    "footer",
    "aside",
}

CHROME_TOKEN_RE = re.compile(
    r"(cookie|consent|banner|navbar|navigation|footer|menu|modal|popup|dialog|"
    r"subscribe|newsletter|breadcrumb|language|locale|app-download|download-app|"
    r"social|share|chat|intercom|zendesk)",
    re.IGNORECASE,
)

NOISE_RE = re.compile(
    r"^(accept all|accept cookies|reject all|manage cookies|all rights reserved|"
    r"copyright|privacy policy|terms of use|skip to content)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FetchedDocument:
    source: DocumentSource
    html: str | None
    failure: FetchFailure | None = None


def fetch_live_documents(sources: SourcesConfig, settings: Settings) -> list[FetchedDocument]:
    try:
        return _fetch_with_playwright(sources, settings)
    except Exception as exc:
        logger.warning("Playwright fetch failed before completion; falling back to urllib: {}", exc)
        return [_fetch_with_urllib(source, "playwright_fallback") for source in sources.documents]


def _fetch_with_playwright(sources: SourcesConfig, settings: Settings) -> list[FetchedDocument]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logger.warning("Playwright is not importable: {}", exc)
        return [_fetch_with_urllib(source, "playwright_unavailable") for source in sources.documents]

    fetched: list[FetchedDocument] = []
    timeout_ms = max(settings.fetch_timeout_seconds, 1) * 1000
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        for source in sources.documents:
            logger.info("Fetching {} from {}", source.document_id, source.url)
            page = context.new_page()
            try:
                page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
                except Exception:
                    logger.debug("Network idle wait timed out for {}; using DOM content", source.url)
                html = page.content()
                fetched.append(FetchedDocument(source=source, html=html))
            except Exception as exc:
                logger.warning("Playwright failed for {}: {}", source.url, exc)
                fetched.append(_fetch_with_urllib(source, "playwright_page_fetch"))
            finally:
                page.close()
        context.close()
        browser.close()
    return fetched


def _fetch_with_urllib(source: DocumentSource, stage: str) -> FetchedDocument:
    logger.info("Fallback HTTP fetch for {} from {}", source.document_id, source.url)
    try:
        request = urllib.request.Request(
            source.url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
        return FetchedDocument(source=source, html=raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        failure = FetchFailure(
            document_id=source.document_id,
            document_name=source.name,
            source_url=source.url,
            stage=stage,
            error=str(exc),
        )
        return FetchedDocument(source=source, html=None, failure=failure)


def build_corpus(fetched_documents: list[FetchedDocument], settings: Settings) -> CorpusArtifact:
    all_sections: list[CorpusSection] = []
    failures: list[FetchFailure] = []
    statuses: list[CorpusDocumentStatus] = []

    for fetched in fetched_documents:
        if not fetched.html:
            failure = fetched.failure or FetchFailure(
                document_id=fetched.source.document_id,
                document_name=fetched.source.name,
                source_url=fetched.source.url,
                stage="empty_html",
                error="No HTML was fetched for the document.",
            )
            failures.append(failure)
            failure_section = _failure_section(fetched.source, failure)
            all_sections.append(failure_section)
            statuses.append(
                CorpusDocumentStatus(
                    document_id=fetched.source.document_id,
                    document_name=fetched.source.name,
                    source_url=fetched.source.url,
                    fetched=False,
                    section_count=1,
                    failure=failure.error,
                )
            )
            continue

        try:
            sections = clean_and_segment(fetched.source, fetched.html, settings)
        except Exception as exc:
            failure = FetchFailure(
                document_id=fetched.source.document_id,
                document_name=fetched.source.name,
                source_url=fetched.source.url,
                stage="clean_and_segment",
                error=str(exc),
            )
            failures.append(failure)
            statuses.append(
                CorpusDocumentStatus(
                    document_id=fetched.source.document_id,
                    document_name=fetched.source.name,
                    source_url=fetched.source.url,
                    fetched=False,
                    section_count=0,
                    failure=failure.error,
                )
            )
            continue

        if not sections:
            failure = FetchFailure(
                document_id=fetched.source.document_id,
                document_name=fetched.source.name,
                source_url=fetched.source.url,
                stage="segment",
                error="Fetched page did not yield any meaningful content sections.",
            )
            failures.append(failure)
            failure_section = _failure_section(fetched.source, failure)
            all_sections.append(failure_section)
            statuses.append(
                CorpusDocumentStatus(
                    document_id=fetched.source.document_id,
                    document_name=fetched.source.name,
                    source_url=fetched.source.url,
                    fetched=False,
                    section_count=1,
                    failure=failure.error,
                )
            )
            continue

        all_sections.extend(sections)
        statuses.append(
            CorpusDocumentStatus(
                document_id=fetched.source.document_id,
                document_name=fetched.source.name,
                source_url=fetched.source.url,
                fetched=True,
                section_count=len(sections),
            )
        )

    return CorpusArtifact(
        generated_at=utc_now(),
        documents=statuses,
        sections=all_sections,
        failures=failures,
    )


def clean_and_segment(source: DocumentSource, html: str, settings: Settings) -> list[CorpusSection]:
    soup = BeautifulSoup(html, "html.parser")
    _remove_chrome(soup)
    root = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = _extract_blocks(root)
    return _segment_blocks(source, blocks, settings.max_section_chars)


def _remove_chrome(soup: BeautifulSoup) -> None:
    for tag in list(soup.find_all(REMOVABLE_TAGS)):
        tag.decompose()

    for element in list(soup.find_all(True)):
        if element.name in {"html", "body", "main", "article", "section"}:
            continue
        style = element.get("style") or ""
        if "display:none" in style.replace(" ", "").lower() or "visibility:hidden" in style.replace(" ", "").lower():
            element.decompose()
            continue
        role = (element.get("role") or "").lower()
        attrs = " ".join(
            [
                " ".join(element.get("class", [])) if isinstance(element.get("class"), list) else str(element.get("class") or ""),
                str(element.get("id") or ""),
                str(element.get("aria-label") or ""),
                role,
            ]
        )
        if role in {"navigation", "banner", "contentinfo", "dialog"} or CHROME_TOKEN_RE.search(attrs):
            element.decompose()


def _extract_blocks(root) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    previous_text = ""
    for tag in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"], recursive=True):
        text = normalize_text(tag.get_text(" ", strip=True))
        kind = "heading" if tag.name and tag.name.lower().startswith("h") else "text"
        if kind == "heading":
            if len(text) < 3 or NOISE_RE.match(text):
                continue
        elif not _is_meaningful(text):
            continue
        if text == previous_text:
            continue
        previous_text = text
        blocks.append((kind, text))
    return blocks


def _is_meaningful(text: str) -> bool:
    if len(text) < 20:
        return False
    if NOISE_RE.match(text):
        return False
    lowered = text.lower()
    noise_hits = sum(token in lowered for token in ["cookie", "subscribe", "newsletter", "download app"])
    if noise_hits >= 2:
        return False
    return True


def _segment_blocks(
    source: DocumentSource,
    blocks: list[tuple[str, str]],
    max_section_chars: int,
) -> list[CorpusSection]:
    sections: list[CorpusSection] = []
    current_title = source.name
    paragraphs: list[str] = []

    def flush() -> None:
        nonlocal paragraphs
        if not paragraphs:
            return
        chunks = _split_paragraphs(paragraphs, max_section_chars)
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            title = current_title
            if total_chunks > 1:
                title = f"{current_title} (part {index})"
            text = normalize_text("\n\n".join(chunk))
            if not text:
                continue
            section_number = len(sections) + 1
            section_id = f"{source.document_id}-{section_number:03d}"
            sections.append(
                CorpusSection(
                    document_id=source.document_id,
                    document_name=source.name,
                    source_url=source.url,
                    section_id=section_id,
                    section_title=title,
                    text=text,
                    character_count=len(text),
                    content_hash=stable_hash(text),
                )
            )
        paragraphs = []

    for kind, text in blocks:
        if kind == "heading":
            flush()
            current_title = text
        else:
            paragraphs.append(text)
    flush()
    return sections


def _split_paragraphs(paragraphs: list[str], max_section_chars: int) -> list[list[str]]:
    if max_section_chars <= 0:
        return [paragraphs]
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if current and current_chars + paragraph_len > max_section_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(paragraph)
        current_chars += paragraph_len
    if current:
        chunks.append(current)
    return chunks


def _failure_section(source: DocumentSource, failure: FetchFailure) -> CorpusSection:
    text = normalize_text(
        "FETCH FAILURE: Live content could not be loaded for this configured source. "
        f"Source URL: {source.url}. Failure stage: {failure.stage}. Error: {failure.error}. "
        "This section exists to preserve an auditable document record; it is not source policy text."
    )
    return CorpusSection(
        document_id=source.document_id,
        document_name=source.name,
        source_url=source.url,
        section_id=f"{source.document_id}-001",
        section_title="Fetch failure",
        text=text,
        character_count=len(text),
        content_hash=stable_hash(text),
    )
