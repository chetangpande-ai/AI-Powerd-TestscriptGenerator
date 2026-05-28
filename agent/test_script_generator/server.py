from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from test_script_generator.config import load_config
from test_script_generator.graph import apply_generated_files, build_graph


AGENT_DIR = Path(__file__).resolve().parents[1]
RUNS_DIR = AGENT_DIR / "runs"
WORKSPACES_DIR = AGENT_DIR / "workspaces"

load_dotenv(AGENT_DIR / ".env")

app = FastAPI(title="Test Script Generator Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    repository_url: str = Field(..., min_length=5)
    branch: str = Field(..., min_length=1)
    scenario: str = Field(..., min_length=5)
    guidelines: str = ""
    force_generate: bool = False


class ApproveRequest(BaseModel):
    reviewer_note: str = ""
    run_validation: bool = True


class Stage(BaseModel):
    id: str
    label: str
    status: str
    detail: str = ""


STAGE_LABELS = {
    "request": "Request received",
    "clone": "Clone repository",
    "analyze": "Analyze reuse",
    "generate": "Generate proposal",
    "review": "Human review",
    "approve": "Approval",
    "validate": "Run validation",
    "commit": "Commit changes",
    "push": "Push branch",
    "pr": "Open pull request",
}


def main() -> None:
    uvicorn.run("test_script_generator.server:app", host="127.0.0.1", port=8000, reload=True)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs")
def create_run(request: GenerateRequest) -> dict[str, Any]:
    token = _github_token()
    run_id = uuid.uuid4().hex[:10]
    run_dir = RUNS_DIR / run_id
    repo_dir = WORKSPACES_DIR / run_id / "repo"
    generated_branch = f"codex/test-script-generator-{run_id}"
    _ensure_dirs(run_dir, repo_dir.parent)

    stages = _initial_stages()
    _mark(stages, "request", "complete", "Scenario and repository details captured.")

    try:
        _mark(stages, "clone", "running", f"Cloning {request.branch}.")
        _clone_repository(request.repository_url, request.branch, repo_dir, token)
        _git(repo_dir, ["checkout", "-b", generated_branch], token=None)
        _mark(stages, "clone", "complete", f"Working branch: {generated_branch}.")

        _mark(stages, "analyze", "running", "Building deterministic repository context.")
        config = load_config(repo_dir)
        graph = build_graph(config)
        state = graph.invoke(
            {
                "scenario": request.scenario,
                "guidelines": _combined_guidelines(request.guidelines),
                "force_generate": request.force_generate,
            }
        )
        result = state["result"]
        reusability = _reusability_analysis(state, result)
        _mark(stages, "analyze", "complete", reusability["summary"])

        if result.get("decision") == "generate":
            _mark(stages, "generate", "complete", f"{len(result.get('files', []))} file proposal(s) generated.")
            _mark(stages, "review", "waiting", "Review generated scripts before approval.")
        elif result.get("decision") == "reuse_existing":
            _mark(stages, "generate", "skipped", "Existing coverage found; no new scripts proposed.")
            _mark(stages, "review", "complete", "Review not required.")
        else:
            _mark(stages, "generate", "waiting", "Clarification is required before generation.")

        run_state = {
            "id": run_id,
            "created_at": _now(),
            "repository_url": request.repository_url,
            "base_branch": request.branch,
            "working_branch": generated_branch,
            "repo_path": str(repo_dir),
            "scenario": request.scenario,
            "guidelines": request.guidelines,
            "result": result,
            "reusability_analysis": reusability,
            "stages": stages,
            "status": _status_from_result(result),
        }
        _save_run(run_dir, run_state)
        _cleanup_workspace(repo_dir)
        return _public_run(run_state)
    except Exception as exception:
        _mark(stages, "clone" if not repo_dir.exists() else "generate", "failed", str(exception))
        run_state = {
            "id": run_id,
            "created_at": _now(),
            "repository_url": request.repository_url,
            "base_branch": request.branch,
            "working_branch": generated_branch,
            "repo_path": str(repo_dir),
            "scenario": request.scenario,
            "guidelines": request.guidelines,
            "result": {"decision": "failed", "summary": str(exception), "files": []},
            "reusability_analysis": {"summary": "Workflow failed before analysis.", "existing_match": None, "reused_files": []},
            "stages": stages,
            "status": "failed",
        }
        _save_run(run_dir, run_state)
        _cleanup_workspace(repo_dir)
        raise HTTPException(status_code=500, detail=_public_run(run_state))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _public_run(_load_run(run_id))


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, request: ApproveRequest) -> dict[str, Any]:
    token = _github_token()
    run_state = _load_run(run_id)
    result = run_state["result"]
    if result.get("decision") != "generate":
        raise HTTPException(status_code=400, detail="Only generated proposals can be approved.")

    repo_dir = Path(run_state["repo_path"])
    stages = run_state["stages"]
    try:
        _mark(stages, "clone", "running", "Preparing a fresh repository workspace for approval.")
        _ensure_dirs(repo_dir.parent)
        _clone_repository(run_state["repository_url"], run_state["base_branch"], repo_dir, token)
        _git(repo_dir, ["checkout", "-b", run_state["working_branch"]], token=None)
        _mark(stages, "clone", "complete", f"Working branch: {run_state['working_branch']}.")

        _mark(stages, "approve", "complete", "Reviewer approved generated test scripts.")
        written = apply_generated_files(repo_dir, result)
        result["written_files"] = [str(path.relative_to(repo_dir)) for path in written]

        if request.run_validation:
            _mark(stages, "validate", "running", "Running generated validation commands.")
            validation_output = _run_validation(repo_dir, result.get("validation_commands", []))
            run_state["validation_output"] = validation_output
            _mark(stages, "validate", "complete", "Validation passed.")
        else:
            _mark(stages, "validate", "skipped", "Reviewer skipped validation.")

        _mark(stages, "commit", "running", "Creating local commit.")
        _commit_changes(repo_dir, request.reviewer_note)
        _mark(stages, "commit", "complete", f"Committed to {run_state['working_branch']}.")

        _mark(stages, "push", "running", "Pushing working branch to origin.")
        _git(repo_dir, ["push", "-u", "origin", run_state["working_branch"]], token=token)
        _mark(stages, "push", "complete", "Branch pushed.")

        _mark(stages, "pr", "running", "Creating GitHub pull request.")
        pr = _create_pull_request(run_state, token)
        run_state["pull_request"] = pr
        _mark(stages, "pr", "complete", pr["html_url"])
        _mark(stages, "review", "complete", "Human review completed.")
        run_state["status"] = "pull_request_created"
        _save_run(RUNS_DIR / run_id, run_state)
        _cleanup_workspace(repo_dir)
        return _public_run(run_state)
    except subprocess.CalledProcessError as exception:
        detail = _command_failure_message(exception)
        _mark(stages, "validate", "failed", detail)
        run_state["status"] = "failed"
        _save_run(RUNS_DIR / run_id, run_state)
        _cleanup_workspace(repo_dir)
        raise HTTPException(status_code=500, detail=_public_run(run_state))
    except Exception as exception:
        _mark(stages, "pr", "failed", str(exception))
        run_state["status"] = "failed"
        _save_run(RUNS_DIR / run_id, run_state)
        _cleanup_workspace(repo_dir)
        raise HTTPException(status_code=500, detail=_public_run(run_state))


def _initial_stages() -> list[dict[str, str]]:
    return [
        {"id": stage_id, "label": label, "status": "pending", "detail": ""}
        for stage_id, label in STAGE_LABELS.items()
    ]


def _mark(stages: list[dict[str, str]], stage_id: str, status: str, detail: str = "") -> None:
    for stage in stages:
        if stage["id"] == stage_id:
            stage["status"] = status
            stage["detail"] = detail
            return


def _clone_repository(repository_url: str, branch: str, repo_dir: Path, token: str) -> None:
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    _git(
        None,
        ["clone", "--branch", branch, "--single-branch", repository_url, str(repo_dir)],
        token=token,
    )


def _git(cwd: Path | None, args: list[str], token: str | None) -> subprocess.CompletedProcess[str]:
    command = ["git"]
    if token:
        basic_token = _git_basic_token(token)
        command.extend(["-c", f"http.extraHeader=Authorization: Basic {basic_token}"])
    command.extend(args)
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def _run_validation(repo_dir: Path, commands: list[str]) -> str:
    if not commands:
        commands = ["mvn test"]
    outputs: list[str] = []
    for command in commands:
        if not _is_allowed_validation_command(command):
            raise ValueError(f"Refusing unsupported validation command: {command}")
        completed = subprocess.run(
            command,
            cwd=repo_dir,
            shell=True,
            text=True,
            capture_output=True,
            check=True,
        )
        outputs.append(completed.stdout[-4000:])
    return "\n".join(outputs)


def _is_allowed_validation_command(command: str) -> bool:
    normalized = command.strip().lower()
    return normalized.startswith("mvn ")


def _commit_changes(repo_dir: Path, reviewer_note: str) -> None:
    _git(repo_dir, ["config", "user.name", os.getenv("GIT_AUTHOR_NAME", "Test Script Generator Agent")], token=None)
    _git(
        repo_dir,
        ["config", "user.email", os.getenv("GIT_AUTHOR_EMAIL", "test-script-generator@example.com")],
        token=None,
    )
    _git(repo_dir, ["add", "."], token=None)
    status = _git(repo_dir, ["status", "--porcelain"], token=None).stdout.strip()
    if not status:
        raise ValueError("No generated changes to commit.")
    message = "Add generated automation test scripts"
    if reviewer_note.strip():
        message = f"{message}\n\nReviewer note: {reviewer_note.strip()}"
    _git(repo_dir, ["commit", "-m", message], token=None)


def _create_pull_request(run_state: dict[str, Any], token: str) -> dict[str, Any]:
    owner, repo = _parse_github_repo(run_state["repository_url"])
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    body = {
        "title": "Add generated automation test scripts",
        "head": run_state["working_branch"],
        "base": run_state["base_branch"],
        "body": _pull_request_body(run_state),
    }
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return {"html_url": payload["html_url"], "number": payload["number"]}


def _parse_github_repo(repository_url: str) -> tuple[str, str]:
    patterns = [
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, repository_url)
        if match:
            return match.group("owner"), match.group("repo")
    raise ValueError("Repository URL must point to a GitHub repository.")


def _pull_request_body(run_state: dict[str, Any]) -> str:
    result = run_state["result"]
    files = "\n".join(f"- `{item['path']}`" for item in result.get("files", []))
    commands = "\n".join(f"- `{command}`" for command in result.get("validation_commands", []))
    return (
        "Generated by the Test Script Generator Agent.\n\n"
        f"Scenario:\n{run_state['scenario']}\n\n"
        f"Summary:\n{result.get('summary', '')}\n\n"
        f"Files:\n{files or '- No files'}\n\n"
        f"Validation:\n{commands or '- Not provided'}\n"
    )


def _combined_guidelines(guidelines: str) -> str:
    defaults = """
- Reuse existing automation framework code before creating new classes.
- If a scenario already exists, return reuse_existing and do not generate duplicate tests.
- For new UI pages, create page objects under src/main/java/.../pages and tests under src/test/java/.../tests/web.
- Keep generated changes minimal and compatible with TestNG groups.
"""
    return f"{defaults}\n{guidelines}".strip()


def _reusability_analysis(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    context_pack = state.get("context_pack", "")
    reused_files = re.findall(r"--- ([^\n]+?) \(", context_pack)
    existing_match = state.get("existing_match")
    if result.get("decision") == "reuse_existing":
        summary = f"Existing coverage found in {existing_match}."
    elif reused_files:
        summary = f"Generated using {len(reused_files)} selected repository file(s) as reusable context."
    else:
        summary = "No reusable files were selected."
    return {
        "summary": summary,
        "existing_match": existing_match,
        "reused_files": reused_files,
        "catalog": state.get("catalog_summary", {}),
    }


def _status_from_result(result: dict[str, Any]) -> str:
    decision = result.get("decision")
    if decision == "generate":
        return "waiting_for_review"
    if decision == "reuse_existing":
        return "reuse_existing"
    return "needs_clarification"


def _save_run(run_dir: Path, run_state: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(run_state, indent=2), encoding="utf-8")


def _load_run(run_id: str) -> dict[str, Any]:
    path = RUNS_DIR / run_id / "state.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def _public_run(run_state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in run_state.items()
        if key not in {"repo_path"}
    }


def _ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_workspace(repo_dir: Path) -> None:
    workspace_root = WORKSPACES_DIR.resolve()
    target = repo_dir.parent.resolve()
    if target.exists() and target.is_relative_to(workspace_root):
        try:
            shutil.rmtree(target)
        except OSError:
            # Windows can briefly hold Git pack files after clone operations.
            # Cleanup is best-effort and must not fail the user workflow.
            pass


def _github_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="Missing GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN in agent/.env.")
    return token


def _git_basic_token(token: str) -> str:
    import base64

    credentials = f"x-access-token:{token}".encode("ascii")
    return base64.b64encode(credentials).decode("ascii")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _command_failure_message(exception: subprocess.CalledProcessError) -> str:
    output = f"{exception.stdout}\n{exception.stderr}".strip()
    return output[-2000:] if output else str(exception)


if __name__ == "__main__":
    main()
