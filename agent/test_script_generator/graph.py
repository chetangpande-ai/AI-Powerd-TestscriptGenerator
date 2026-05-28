from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from test_script_generator.config import AgentConfig
from test_script_generator.llm import create_llm
from test_script_generator.prompts import SYSTEM_PROMPT, user_prompt
from test_script_generator.scanner import (
    build_catalog,
    find_existing_test_match,
    render_context_pack,
    select_context,
)
from test_script_generator.web_discovery import discover_web_context, render_web_context
from test_script_generator.web_framework import enhance_web_result


class GeneratorState(TypedDict, total=False):
    scenario: str
    guidelines: str
    force_generate: bool
    dry_run_context: bool
    catalog_summary: dict[str, Any]
    existing_match: str | None
    context_pack: str
    web_discovery: dict[str, Any]
    result: dict[str, Any]


def build_graph(config: AgentConfig):
    def inventory_repo(state: GeneratorState) -> GeneratorState:
        catalog = build_catalog(config.repo_root)
        files = select_context(catalog, state["scenario"])
        match = find_existing_test_match(catalog, state["scenario"])
        if match and not state.get("force_generate", False):
            web_discovery = {
                "enabled": False,
                "summary": "Web crawl skipped because matching automation already exists.",
                "urls": [],
                "pages": [],
                "raw_script": [],
            }
        else:
            web_discovery = discover_web_context(
                config.repo_root,
                state["scenario"],
                state.get("guidelines", ""),
            )
        context_pack = render_context_pack(catalog, state["scenario"], files)
        if web_discovery.get("enabled"):
            context_pack = f"{context_pack}\n\n{render_web_context(web_discovery)}"
        return {
            **state,
            "catalog_summary": {
                "classes": len(catalog.classes),
                "tests": [item.path.as_posix() for item in catalog.tests],
                "pages": [item.path.as_posix() for item in catalog.pages],
            },
            "existing_match": match.path.as_posix() if match else None,
            "web_discovery": web_discovery,
            "context_pack": context_pack,
        }

    def decide_or_generate(state: GeneratorState) -> GeneratorState:
        if state.get("dry_run_context"):
            return {
                **state,
                "result": {
                    "decision": "context_only",
                    "summary": "Generated deterministic repository context pack.",
                    "context_pack": state["context_pack"],
                },
            }

        if state.get("existing_match") and not state.get("force_generate", False):
            return {
                **state,
                "result": {
                    "decision": "reuse_existing",
                    "summary": f"Existing test coverage appears relevant: {state['existing_match']}",
                    "files": [],
                    "validation_commands": ["mvn clean test"],
                    "questions": [],
                },
            }

        llm = create_llm(config)
        response = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt(state["context_pack"], state.get("guidelines", ""))),
            ]
        )
        result = enhance_web_result(config.repo_root, _parse_json_response(response.content))
        return {**state, "result": result}

    graph = StateGraph(GeneratorState)
    graph.add_node("inventory_repo", inventory_repo)
    graph.add_node("decide_or_generate", decide_or_generate)
    graph.add_edge(START, "inventory_repo")
    graph.add_edge("inventory_repo", "decide_or_generate")
    graph.add_edge("decide_or_generate", END)
    return graph.compile()


def apply_generated_files(repo_root: Path, result: dict[str, Any]) -> list[Path]:
    written: list[Path] = []
    for file_item in result.get("files", []):
        rel_path = Path(file_item["path"])
        target = (repo_root / rel_path).resolve()
        if not target.is_relative_to(repo_root.resolve()):
            raise ValueError(f"Refusing to write outside repository: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file_item["content"], encoding="utf-8")
        written.append(target)
    return written


def _parse_json_response(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start == -1:
            raise
        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(cleaned[start:])
        return parsed
