from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def enhance_web_result(repo_root: Path, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("decision") != "generate" or not _is_web_result(result):
        return result

    package_root = _package_root(result) or _existing_package_root(repo_root)
    if not package_root:
        return result

    _ensure_pom_dependencies(repo_root, result)
    _ensure_base_web_test(repo_root, result, package_root)
    result["validation_commands"] = ["mvn clean test -DskipTests"]
    return result


def _is_web_result(result: dict[str, Any]) -> bool:
    haystack = "\n".join(
        f"{item.get('path', '')}\n{item.get('content', '')}"
        for item in result.get("files", [])
    ).lower()
    return any(
        marker in haystack
        for marker in (
            "org.openqa.selenium",
            "basewebtest",
            "/tests/web/",
            "\\tests\\web\\",
            "/pages/",
            "\\pages\\",
        )
    )


def _package_root(result: dict[str, Any]) -> str:
    for item in result.get("files", []):
        content = item.get("content", "")
        package = _first_match(r"package\s+([\w.]+);", content)
        if not package:
            continue
        for suffix in (".pages", ".tests.web", ".tests"):
            if package.endswith(suffix):
                return package[: -len(suffix)]
    return ""


def _existing_package_root(repo_root: Path) -> str:
    for path in sorted((repo_root / "src/main/java").glob("**/*.java")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        package = _first_match(r"package\s+([\w.]+);", text)
        if package:
            return package.rsplit(".", 1)[0]
    return ""


def _ensure_pom_dependencies(repo_root: Path, result: dict[str, Any]) -> None:
    pom_item = _file_item(result, "pom.xml")
    pom_path = repo_root / "pom.xml"
    if pom_item:
        content = pom_item.get("content", "")
    elif pom_path.exists():
        content = pom_path.read_text(encoding="utf-8")
    else:
        return

    updated = _add_property(content, "selenium.version", "4.26.0")
    updated = _add_property(updated, "webdrivermanager.version", "5.9.2")
    updated = _add_dependency(
        updated,
        "org.seleniumhq.selenium",
        "selenium-java",
        "${selenium.version}",
    )
    updated = _add_dependency(
        updated,
        "io.github.bonigarcia",
        "webdrivermanager",
        "${webdrivermanager.version}",
    )

    if updated == content:
        return
    if pom_item:
        pom_item["content"] = updated
        pom_item["rationale"] = _append_rationale(pom_item.get("rationale", ""), "Add Selenium web automation dependencies.")
    else:
        result.setdefault("files", []).insert(
            0,
            {
                "path": "pom.xml",
                "content": updated,
                "rationale": "Add minimal Selenium and WebDriverManager dependencies for web UI tests.",
            },
        )


def _ensure_base_web_test(repo_root: Path, result: dict[str, Any], package_root: str) -> None:
    rel_path = Path("src/test/java") / Path(*package_root.split(".")) / "base" / "BaseWebTest.java"
    if (repo_root / rel_path).exists() or _file_item(result, rel_path.as_posix()):
        return
    result.setdefault("files", []).append(
        {
            "path": rel_path.as_posix(),
            "content": _base_web_test_content(package_root),
            "rationale": "Add minimal reusable Selenium TestNG base class because the repository has no web test foundation.",
        }
    )


def _base_web_test_content(package_root: str) -> str:
    return f"""package {package_root}.base;

import io.github.bonigarcia.wdm.WebDriverManager;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;

public abstract class BaseWebTest {{
    private final ThreadLocal<WebDriver> driver = new ThreadLocal<>();

    @BeforeMethod(alwaysRun = true)
    public void setUpWebDriver() {{
        WebDriverManager.chromedriver().setup();
        ChromeOptions options = new ChromeOptions();
        options.addArguments("--headless=new");
        options.addArguments("--disable-gpu");
        options.addArguments("--no-sandbox");
        options.addArguments("--window-size=1440,1000");
        driver.set(new ChromeDriver(options));
    }}

    @AfterMethod(alwaysRun = true)
    public void tearDownWebDriver() {{
        WebDriver currentDriver = driver.get();
        if (currentDriver != null) {{
            currentDriver.quit();
            driver.remove();
        }}
    }}

    protected WebDriver getDriver() {{
        return driver.get();
    }}
}}
"""


def _add_property(content: str, name: str, value: str) -> str:
    if f"<{name}>" in content:
        return content
    return content.replace(
        "    </properties>",
        f"        <{name}>{value}</{name}>\n    </properties>",
        1,
    )


def _add_dependency(content: str, group_id: str, artifact_id: str, version: str) -> str:
    if f"<artifactId>{artifact_id}</artifactId>" in content:
        return content
    dependency = f"""        <dependency>
            <groupId>{group_id}</groupId>
            <artifactId>{artifact_id}</artifactId>
            <version>{version}</version>
        </dependency>
"""
    return content.replace("    </dependencies>", f"{dependency}    </dependencies>", 1)


def _file_item(result: dict[str, Any], path: str) -> dict[str, Any] | None:
    normalized = path.replace("\\", "/")
    for item in result.get("files", []):
        if item.get("path", "").replace("\\", "/") == normalized:
            return item
    return None


def _append_rationale(current: str, addition: str) -> str:
    return f"{current.rstrip()} {addition}".strip()


def _first_match(pattern: str, value: str) -> str:
    match = re.search(pattern, value)
    return match.group(1) if match else ""
