from __future__ import annotations

import argparse
import json
from pathlib import Path

from test_script_generator.config import load_config
from test_script_generator.graph import apply_generated_files, build_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TestNG scripts from scenarios.")
    parser.add_argument("--repo-root", default=".", help="Path to the automation repository.")
    parser.add_argument("--scenario", help="Scenario text.")
    parser.add_argument("--scenario-file", help="Path to a file containing scenario text.")
    parser.add_argument("--guidelines-file", help="Optional project guidelines file.")
    parser.add_argument("--force-generate", action="store_true", help="Generate even when a close test already exists.")
    parser.add_argument("--dry-run-context", action="store_true", help="Print deterministic context pack without calling LLM.")
    parser.add_argument("--write", action="store_true", help="Write generated files to the repository.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    scenario = _read_scenario(args)
    guidelines = Path(args.guidelines_file).read_text(encoding="utf-8") if args.guidelines_file else ""

    config = load_config(repo_root)
    graph = build_graph(config)
    state = graph.invoke(
        {
            "scenario": scenario,
            "guidelines": guidelines,
            "force_generate": args.force_generate,
            "dry_run_context": args.dry_run_context,
        }
    )
    result = state["result"]

    if args.write and result.get("decision") == "generate":
        written = apply_generated_files(repo_root, result)
        result["written_files"] = [str(path) for path in written]

    print(json.dumps(result, indent=2))
    return 0


def _read_scenario(args: argparse.Namespace) -> str:
    if args.scenario:
        return args.scenario
    if args.scenario_file:
        return Path(args.scenario_file).read_text(encoding="utf-8")
    raise SystemExit("Provide --scenario or --scenario-file.")


if __name__ == "__main__":
    raise SystemExit(main())
