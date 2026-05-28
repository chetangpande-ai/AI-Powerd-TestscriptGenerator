# Test Script Generator Agent

This is a Python sidecar agent for the Java Maven TestNG automation framework.
It uses LangGraph for workflow control, LangChain for the Mesh API LLM call, and a deterministic repository scanner instead of RAG.

## Approach

The agent builds a compact context pack from the repository every run:

1. Scan Java classes, test classes, page objects, API helpers, config, and test data.
2. Match the incoming scenario against existing test names, JavaDocs, methods, packages, and resource paths.
3. If the same or very similar scenario already exists, return a reuse recommendation instead of generating a duplicate.
4. If generation is needed, send only the selected context pack and guidelines to the LLM.
5. Ask the LLM to return strict JSON with proposed full file contents and validation commands.
6. Write files only when `--write` is provided.

This is not vector RAG. The codebase context is selected by deterministic repository structure and lexical matching, which keeps behavior easier to audit.

## Setup

```powershell
cd C:\Users\Ishan Pande\Documents\HdfcBank_Test_Automation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r agent\requirements.txt
pip install -e agent
copy agent\.env.example agent\.env
```

Update `agent\.env` with your Mesh API details:

```text
MESH_API_KEY=...
MESH_API_BASE_URL=...
MESH_MODEL=...
GITHUB_TOKEN=...
GIT_AUTHOR_NAME=Test Script Generator Agent
GIT_AUTHOR_EMAIL=test-script-generator@example.com
```

The current implementation assumes the Mesh API exposes an OpenAI-compatible chat endpoint. If your Mesh API uses a different request schema, only `agent/test_script_generator/llm.py` needs to change.

## Usage

Preview what repository context would be sent to the LLM:

```powershell
python -m test_script_generator.cli --repo-root . --scenario "Valid Sauce Demo user should log in and see inventory" --dry-run-context
```

After `pip install -e agent`, you can also use the console command:

```powershell
test-script-generator --repo-root . --scenario "Valid Sauce Demo user should log in and see inventory" --dry-run-context
```

Generate a proposal without writing files:

```powershell
python -m test_script_generator.cli --repo-root . --scenario-file scenarios\login.txt --guidelines-file guidelines.md
```

Generate and write files:

```powershell
python -m test_script_generator.cli --repo-root . --scenario-file scenarios\login.txt --guidelines-file guidelines.md --write
```

Force generation even when a similar test already exists:

```powershell
python -m test_script_generator.cli --repo-root . --scenario "Locked out user sees login error" --force-generate
```

## React Review UI

The React UI wraps the generator in a GitHub workflow:

1. Enter GitHub repository URL, base branch, scenario, and guidelines.
2. Backend clones the requested branch into `agent/workspaces`.
3. Agent scans the repository and shows test script reusability analysis.
4. Generated file proposals are shown for human review.
5. On approval, backend writes the scripts, optionally runs Maven validation, commits to a generated branch, pushes it, and opens a pull request against the selected base branch.

Install and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r agent\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e agent
cd agent\ui
npm install
npm run dev
```

In another terminal from the repository root, start the backend:

```powershell
.\.venv\Scripts\uvicorn.exe test_script_generator.server:app --host 127.0.0.1 --port 8000
```

Open the UI at:

```text
http://127.0.0.1:5173
```

The approval step uses `GITHUB_TOKEN` only on the backend. The token is never sent to the browser.

## Recommended Guidelines Content

Keep guidelines explicit and project-specific:

```text
- Use TestNG.
- Web tests must extend BaseWebTest.
- API tests must extend BaseApiTest.
- Prefer existing page methods. Add page methods only when no reusable method exists.
- Do not create raw WebDriver locators in test classes.
- Add JavaDoc for public test methods and page methods.
- Use groups="web" or groups="api".
- Run mvn clean test after generation.
```
