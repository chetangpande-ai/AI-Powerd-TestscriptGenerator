# AI-Powerd-TestscriptGenerator

Repository-aware test script generator agent.

The local project contains only the agent implementation:

- Python/LangGraph generator backend
- FastAPI workflow API
- React human-in-the-loop review UI
- deterministic repository scanner for code reuse analysis

Generated automation projects are created in the target GitHub repository, reviewed in the UI, and committed through pull requests. Temporary local clones under `agent/workspaces` are ignored and cleaned after runs.

## Documentation

See [docs/README.md](docs/README.md) for:

- agent workflow
- how the system works
- code analysis approach
- example scenarios and expected outcomes

## Run

Start the backend:

```powershell
.\.venv\Scripts\uvicorn.exe test_script_generator.server:app --host 127.0.0.1 --port 8000
```

Start the UI:

```powershell
cd agent\ui
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```
