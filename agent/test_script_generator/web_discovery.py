from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


WEB_HINTS = {
    "browser",
    "button",
    "checkbox",
    "click",
    "field",
    "form",
    "home",
    "login",
    "page",
    "search",
    "submit",
    "ui",
    "url",
    "web",
}


@dataclass
class PageEvidence:
    url: str
    final_url: str = ""
    title: str = ""
    inputs: list[dict[str, str]] = field(default_factory=list)
    buttons: list[dict[str, str]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    forms: list[dict[str, str]] = field(default_factory=list)
    error: str = ""


class EvidenceParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self.inputs: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self._capture_title = False
        self._capture_button = False
        self._capture_link: dict[str, str] | None = None
        self._button_attrs: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self._capture_title = True
        elif tag == "input":
            self.inputs.append(_compact_attrs(attrs_map, ["id", "name", "type", "placeholder", "value", "aria-label"]))
        elif tag == "textarea":
            item = _compact_attrs(attrs_map, ["id", "name", "placeholder", "aria-label"])
            item["type"] = "textarea"
            self.inputs.append(item)
        elif tag == "select":
            item = _compact_attrs(attrs_map, ["id", "name", "aria-label"])
            item["type"] = "select"
            self.inputs.append(item)
        elif tag == "button":
            self._capture_button = True
            self._button_attrs = _compact_attrs(attrs_map, ["id", "name", "type", "aria-label"])
        elif tag == "a":
            href = attrs_map.get("href", "")
            self._capture_link = {
                "href": urljoin(self.base_url, href) if href else "",
                "text": "",
            }
        elif tag == "form":
            form = _compact_attrs(attrs_map, ["id", "name", "method", "action", "aria-label"])
            if form.get("action"):
                form["action"] = urljoin(self.base_url, form["action"])
            self.forms.append(form)

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._capture_title:
            self.title = (self.title + " " + text).strip()
        if self._capture_button and self._button_attrs is not None:
            existing = self._button_attrs.get("text", "")
            self._button_attrs["text"] = f"{existing} {text}".strip()
        if self._capture_link is not None:
            existing = self._capture_link.get("text", "")
            self._capture_link["text"] = f"{existing} {text}".strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._capture_title = False
        elif tag == "button" and self._button_attrs is not None:
            self.buttons.append(self._button_attrs)
            self._capture_button = False
            self._button_attrs = None
        elif tag == "a" and self._capture_link is not None:
            if self._capture_link.get("href") and self._capture_link.get("text"):
                self.links.append(self._capture_link)
            self._capture_link = None


def discover_web_context(repo_root: Path, scenario: str, guidelines: str = "") -> dict[str, Any]:
    text = f"{scenario}\n{guidelines}"
    explicit_urls = _extract_urls(text)
    config_urls = _config_urls(repo_root)
    is_web = bool(explicit_urls) or _looks_like_web_scenario(text)
    urls = _rank_urls(explicit_urls, config_urls, text)

    if not is_web:
        return {
            "enabled": False,
            "summary": "Scenario does not look like a web UI scenario.",
            "urls": [],
            "pages": [],
            "raw_script": [],
        }

    pages = [_fetch_page(url) for url in urls[:3]]
    raw_script = _raw_script(text, pages)
    return {
        "enabled": True,
        "summary": _summary(pages, urls),
        "urls": urls,
        "pages": [_page_to_dict(page) for page in pages],
        "raw_script": raw_script,
    }


def render_web_context(web_context: dict[str, Any]) -> str:
    if not web_context.get("enabled"):
        return "Web discovery: skipped. Scenario did not look like a web UI scenario."

    lines = ["Web discovery:", f"- Summary: {web_context.get('summary', '')}"]
    lines.append("- Raw script intent:")
    for step in web_context.get("raw_script", []):
        lines.append(f"  - {step}")
    for page in web_context.get("pages", []):
        lines.append(f"\nPage: {page.get('final_url') or page.get('url')}")
        if page.get("error"):
            lines.append(f"- Crawl error: {page['error']}")
            continue
        lines.append(f"- Title: {page.get('title', '')}")
        _append_items(lines, "Forms", page.get("forms", []))
        _append_items(lines, "Inputs", page.get("inputs", []))
        _append_items(lines, "Buttons", page.get("buttons", []))
        _append_items(lines, "Links", page.get("links", [])[:12])
    return "\n".join(lines)


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)>\]\"']+", text)
    return _dedupe(url.rstrip(".,;") for url in urls)


def _config_urls(repo_root: Path) -> list[str]:
    urls: list[str] = []
    for path in (repo_root / "src/test/resources/config").glob("**/*.properties"):
        content = path.read_text(encoding="utf-8")
        urls.extend(_extract_urls(content))
    return _dedupe(urls)


def _looks_like_web_scenario(text: str) -> bool:
    tokens = {token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text)}
    return bool(tokens & WEB_HINTS)


def _rank_urls(explicit_urls: list[str], config_urls: list[str], text: str) -> list[str]:
    if explicit_urls:
        return explicit_urls
    tokens = {token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text)}
    scored: list[tuple[int, str]] = []
    for url in config_urls:
        parsed = urlparse(url)
        haystack = f"{parsed.netloc} {parsed.path}".lower()
        score = sum(1 for token in tokens if token in haystack)
        scored.append((score, url))
    return [url for _, url in sorted(scored, key=lambda item: (-item[0], item[1]))]


def _fetch_page(url: str) -> PageEvidence:
    evidence = PageEvidence(url=url)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 test-script-generator-agent"},
        ) as client:
            response = client.get(url)
            evidence.final_url = str(response.url)
            response.raise_for_status()
            parser = EvidenceParser(evidence.final_url)
            parser.feed(response.text[:500_000])
            evidence.title = parser.title
            evidence.inputs = parser.inputs[:40]
            evidence.buttons = parser.buttons[:30]
            evidence.links = parser.links[:40]
            evidence.forms = parser.forms[:20]
    except Exception as exception:
        evidence.error = str(exception)
    return evidence


def _raw_script(text: str, pages: list[PageEvidence]) -> list[str]:
    steps = _scenario_steps(text)
    if steps:
        return steps
    if not pages:
        return ["Open the target web application.", "Perform the requested UI action.", "Assert the expected result."]
    first_page = pages[0]
    target = first_page.final_url or first_page.url
    result = [f"Open {target}."]
    if first_page.inputs:
        result.append("Interact with discovered input fields using stable id/name/placeholder locators.")
    if first_page.buttons:
        result.append("Click the relevant discovered button.")
    result.append("Assert the expected UI outcome from the scenario.")
    return result


def _scenario_steps(text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    numbered = [line for line in lines if re.match(r"^\d+[\.)]\s+", line)]
    if numbered:
        return [re.sub(r"^\d+[\.)]\s+", "", line) for line in numbered]
    url_map = {f"__URL_{index}__": url for index, url in enumerate(_extract_urls(text))}
    protected_text = text
    for placeholder, url in url_map.items():
        protected_text = protected_text.replace(url, placeholder)
    separators = re.split(r"\b(?:and then|then|after that)\b|[.;]", protected_text, flags=re.IGNORECASE)
    steps = []
    for step in separators:
        restored = step.strip()
        for placeholder, url in url_map.items():
            restored = restored.replace(placeholder, url)
        if len(restored) > 12:
            steps.append(restored)
    return steps[:8]


def _summary(pages: list[PageEvidence], urls: list[str]) -> str:
    successful = [page for page in pages if not page.error]
    if successful:
        controls = sum(len(page.inputs) + len(page.buttons) for page in successful)
        return f"Crawled {len(successful)} page(s) and found {controls} candidate control(s)."
    if urls:
        return "Web scenario detected, but page crawl did not return usable page evidence."
    return "Web scenario detected, but no URL was found in scenario or config."


def _compact_attrs(attrs: dict[str, str], keys: list[str]) -> dict[str, str]:
    return {key: attrs[key] for key in keys if attrs.get(key)}


def _page_to_dict(page: PageEvidence) -> dict[str, Any]:
    return {
        "url": page.url,
        "final_url": page.final_url,
        "title": page.title,
        "inputs": page.inputs,
        "buttons": page.buttons,
        "links": page.links,
        "forms": page.forms,
        "error": page.error,
    }


def _append_items(lines: list[str], label: str, items: list[dict[str, str]]) -> None:
    if not items:
        return
    lines.append(f"- {label}:")
    for item in items:
        rendered = ", ".join(f"{key}={value}" for key, value in item.items() if value)
        lines.append(f"  - {rendered}")


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
