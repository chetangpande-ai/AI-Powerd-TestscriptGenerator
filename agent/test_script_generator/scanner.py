from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


JAVA_ROOTS = ("src/main/java", "src/test/java")
RESOURCE_ROOTS = ("src/test/resources/config", "src/test/resources/testdata")


@dataclass(frozen=True)
class JavaMethod:
    name: str
    signature: str
    annotations: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class JavaClass:
    name: str
    package: str
    path: Path
    extends: str | None = None
    methods: tuple[JavaMethod, ...] = ()
    annotations: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ContextFile:
    path: Path
    reason: str
    content: str


@dataclass
class RepoCatalog:
    repo_root: Path
    classes: list[JavaClass] = field(default_factory=list)
    resource_files: list[Path] = field(default_factory=list)

    @property
    def tests(self) -> list[JavaClass]:
        return [
            item
            for item in self.classes
            if "src/test/java" in item.path.as_posix()
            and any(
                annotation.startswith("Test")
                for method in item.methods
                for annotation in method.annotations
            )
        ]

    @property
    def pages(self) -> list[JavaClass]:
        return [
            item
            for item in self.classes
            if "src/main/java" in item.path.as_posix()
            and ".pages" in f"{item.package}."
        ]

    @property
    def api_helpers(self) -> list[JavaClass]:
        return [
            item
            for item in self.classes
            if "src/main/java" in item.path.as_posix()
            and ".api" in f"{item.package}."
        ]


def build_catalog(repo_root: Path) -> RepoCatalog:
    catalog = RepoCatalog(repo_root=repo_root)
    for root in JAVA_ROOTS:
        for path in sorted((repo_root / root).glob("**/*.java")):
            catalog.classes.append(parse_java_class(repo_root, path))
    for root in RESOURCE_ROOTS:
        base = repo_root / root
        if base.exists():
            catalog.resource_files.extend(sorted(base.glob("**/*")))
    return catalog


def parse_java_class(repo_root: Path, path: Path) -> JavaClass:
    text = path.read_text(encoding="utf-8")
    package = _first_match(r"package\s+([\w.]+);", text) or ""
    class_match = re.search(
        r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
        text,
    )
    name = class_match.group(1) if class_match else path.stem
    extends = class_match.group(2) if class_match and class_match.group(2) else None
    annotations = tuple(re.findall(r"^\s*@(\w+(?:\([^)]*\))?)", text, re.MULTILINE))
    methods = tuple(_parse_methods(text))
    description = _nearest_javadoc_before(text, class_match.start() if class_match else 0)
    return JavaClass(
        name=name,
        package=package,
        path=path.relative_to(repo_root),
        extends=extends,
        methods=methods,
        annotations=annotations,
        description=description,
    )


def select_context(catalog: RepoCatalog, scenario: str, max_files: int = 12) -> list[ContextFile]:
    scored: list[tuple[int, Path, str]] = []
    tokens = _tokens(scenario)
    scenario_kind = _scenario_kind(tokens)

    for klass in catalog.classes:
        haystack = " ".join(
            [
                klass.name,
                klass.package,
                klass.description,
                " ".join(method.name for method in klass.methods),
                " ".join(method.description for method in klass.methods),
            ]
        )
        score = _score(tokens, haystack)
        if _is_foundation_class(klass, scenario_kind):
            score += 4
        if score > 0:
            scored.append((score, klass.path, f"matched scenario score {score}"))

    for resource in catalog.resource_files:
        if resource.is_file():
            rel_path = resource.relative_to(catalog.repo_root)
            score = _score(tokens, rel_path.as_posix())
            if "config" in rel_path.as_posix():
                score += 2
            if score > 0:
                scored.append((score, rel_path, f"matched resource score {score}"))

    picked = _dedupe_ranked(scored, max_files)
    return [
        ContextFile(
            path=path,
            reason=reason,
            content=(catalog.repo_root / path).read_text(encoding="utf-8"),
        )
        for path, reason in picked
    ]


def find_existing_test_match(catalog: RepoCatalog, scenario: str) -> JavaClass | None:
    tokens = _tokens(scenario)
    strong_tokens = _strong_tokens(tokens)
    best: tuple[int, JavaClass] | None = None
    for klass in catalog.tests:
        method_text = " ".join(
            " ".join([method.name, method.signature, method.description])
            for method in klass.methods
        )
        score = _score(strong_tokens, f"{klass.name} {klass.description} {method_text}")
        if best is None or score > best[0]:
            best = (score, klass)
    if best and best[0] >= max(2, len(strong_tokens) // 2):
        return best[1]
    return None


def render_context_pack(catalog: RepoCatalog, scenario: str, files: list[ContextFile]) -> str:
    lines = [
        "Repository facts:",
        "- Framework: Java Maven TestNG automation.",
        "- Web tests extend BaseWebTest and use Page Object Model classes.",
        "- API tests extend BaseApiTest and use ApiClient/ApiRoutes.",
        "- Reuse existing pages, helpers, config, and test data before adding new code.",
        "",
        "Known page objects:",
    ]
    lines.extend(f"- {item.name}: {item.path.as_posix()}" for item in catalog.pages)
    lines.append("")
    lines.append("Known tests:")
    lines.extend(f"- {item.name}: {item.path.as_posix()}" for item in catalog.tests)
    lines.append("")
    lines.append("Selected source context:")
    for item in files:
        lines.append(f"\n--- {item.path.as_posix()} ({item.reason}) ---")
        lines.append(item.content)
    lines.append("\nScenario:")
    lines.append(scenario)
    return "\n".join(lines)


def _parse_methods(text: str) -> list[JavaMethod]:
    methods: list[JavaMethod] = []
    pattern = re.compile(
        r"(?P<ann>(?:^\s*@[\w.]+(?:\([^)]*\))?\s*$\n)*)"
        r"\s*(?:public|protected|private)\s+"
        r"(?:(?:static|final)\s+)*"
        r"[\w<>\[\], ?]+\s+"
        r"(?P<name>\w+)\s*"
        r"(?P<args>\([^;{}]*\))\s*"
        r"(?:throws\s+[\w, ]+\s*)?\{",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        signature = re.sub(r"\s+", " ", match.group(0).split("{", 1)[0]).strip()
        annotations = tuple(
            annotation.strip().lstrip("@")
            for annotation in match.group("ann").splitlines()
            if annotation.strip()
        )
        methods.append(
            JavaMethod(
                name=match.group("name"),
                signature=signature,
                annotations=annotations,
                description=_nearest_javadoc_before(text, match.start()),
            )
        )
    return methods


def _nearest_javadoc_before(text: str, offset: int) -> str:
    prefix = text[:offset]
    matches = list(re.finditer(r"/\*\*(.*?)\*/", prefix, re.DOTALL))
    if not matches:
        return ""
    raw = matches[-1].group(1)
    cleaned = [
        line.strip().lstrip("*").strip()
        for line in raw.splitlines()
        if line.strip().lstrip("*").strip() and not line.strip().startswith("@")
    ]
    return " ".join(cleaned)


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _tokens(value: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "as",
        "for",
        "get",
        "in",
        "is",
        "of",
        "on",
        "or",
        "should",
        "test",
        "the",
        "to",
        "user",
        "verify",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", value.lower())
        if token not in stop_words and len(token) > 2
    }


def _score(tokens: set[str], value: str) -> int:
    haystack = value.lower()
    return sum(1 for token in tokens if token in haystack)


def _strong_tokens(tokens: set[str]) -> set[str]:
    weak_tokens = {
        "api",
        "automation",
        "brand",
        "case",
        "cases",
        "create",
        "crud",
        "delete",
        "existing",
        "framework",
        "generate",
        "get",
        "management",
        "new",
        "patch",
        "record",
        "resource",
        "return",
        "returns",
        "route",
        "routes",
        "reusable",
        "test",
        "tests",
        "update",
    }
    return tokens - weak_tokens


def _scenario_kind(tokens: set[str]) -> str:
    api_tokens = {"api", "endpoint", "request", "response", "status", "payload", "post", "get", "put", "delete"}
    web_tokens = {"login", "page", "click", "browser", "field", "button", "inventory", "checkbox"}
    if tokens & api_tokens and not tokens & web_tokens:
        return "api"
    if tokens & web_tokens and not tokens & api_tokens:
        return "web"
    return "mixed"


def _is_foundation_class(klass: JavaClass, scenario_kind: str) -> bool:
    common = {"ConfigManager", "TestDataReader"}
    web = {"BasePage", "BaseWebTest"}
    api = {"BaseApiTest", "ApiClient", "ApiRoutes"}
    if klass.name in common:
        return True
    if scenario_kind == "web":
        return klass.name in web
    if scenario_kind == "api":
        return klass.name in api
    return klass.name in web | api


def _dedupe_ranked(scored: list[tuple[int, Path, str]], max_files: int) -> list[tuple[Path, str]]:
    seen: set[Path] = set()
    picked: list[tuple[Path, str]] = []
    for score, path, reason in sorted(scored, key=lambda item: (-item[0], item[1].as_posix())):
        if path in seen:
            continue
        seen.add(path)
        picked.append((path, reason))
        if len(picked) >= max_files:
            break
    return picked
