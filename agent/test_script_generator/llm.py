from __future__ import annotations

from langchain_openai import ChatOpenAI

from test_script_generator.config import AgentConfig


def create_llm(config: AgentConfig) -> ChatOpenAI:
    missing = [
        name
        for name, value in {
            "MESH_API_KEY": config.mesh_api_key,
            "MESH_API_BASE_URL": config.mesh_api_base_url,
            "MESH_MODEL": config.mesh_model,
        }.items()
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing Mesh API configuration: {joined}")

    return ChatOpenAI(
        model=config.mesh_model,
        api_key=config.mesh_api_key,
        base_url=config.mesh_api_base_url,
        temperature=config.temperature,
    )
