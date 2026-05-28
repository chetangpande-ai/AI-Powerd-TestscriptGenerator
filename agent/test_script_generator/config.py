from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AgentConfig:
    repo_root: Path
    mesh_api_key: str
    mesh_api_base_url: str
    mesh_model: str
    temperature: float = 0.1


def load_config(repo_root: Path) -> AgentConfig:
    package_agent_dir = Path(__file__).resolve().parents[1]
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(package_agent_dir / ".env")
    load_dotenv(repo_root / "agent" / ".env")

    return AgentConfig(
        repo_root=repo_root,
        mesh_api_key=os.getenv("MESH_API_KEY", ""),
        mesh_api_base_url=os.getenv("MESH_API_BASE_URL", ""),
        mesh_model=os.getenv("MESH_MODEL", ""),
        temperature=float(os.getenv("MESH_TEMPERATURE", "0.1")),
    )
