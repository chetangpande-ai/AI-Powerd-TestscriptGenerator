# How It Works

The system has three main parts.

## 1. React UI

Location:

```text
agent/ui
```

The UI lets the user:

- enter GitHub repository URL and branch
- enter a test scenario
- add project-specific guidelines
- view workflow stages
- inspect stage-specific details
- inspect web crawl evidence and raw UI action plans
- review generated files
- approve generated scripts
- open the final pull request

The UI does not receive or store GitHub tokens. Secrets stay in the backend.

## 2. FastAPI Backend

Location:

```text
agent/test_script_generator/server.py
```

Responsibilities:

- clone the GitHub repository
- invoke the LangGraph agent
- crawl web pages for UI evidence when a web scenario needs new automation
- store workflow run state under `agent/runs`
- expose run results to the UI
- apply approved generated files
- run validation commands
- commit and push generated code
- create GitHub pull requests

Secrets are read from:

```text
agent/.env
```

Supported GitHub token keys:

```text
GITHUB_TOKEN
GITHUB_PERSONAL_ACCESS_TOKEN
```

## 3. LangGraph Agent

Location:

```text
agent/test_script_generator/graph.py
```

The graph has two core nodes:

```text
inventory_repo -> decide_or_generate
```

`inventory_repo`:

- scans the cloned repository
- builds a code catalog
- finds matching existing tests
- selects relevant files as context
- detects web UI scenarios and crawls configured or user-provided target URLs
- adds the web raw action plan and page evidence to the context pack
- renders a context pack

`decide_or_generate`:

- returns `reuse_existing` if a strong existing test match is found
- otherwise calls the Mesh API LLM through LangChain
- parses the LLM JSON proposal

## Web Automation Flow

Location:

```text
agent/test_script_generator/web_discovery.py
```

For web UI scenarios, the agent first tries to reuse existing tests and page objects. If the script does not already exist, it:

- detects URLs from the scenario, guidelines, or `src/test/resources/config/**/*.properties`
- fetches up to three target pages
- extracts forms, inputs, buttons, links, and page titles
- turns the scenario steps and page evidence into a raw action plan
- sends that evidence to the LLM with the repository context
- asks the LLM to generate framework-style Selenium/TestNG Page Object Model code

If the target repository does not already have web test foundations, the prompt allows the smallest required additions, such as Selenium/WebDriverManager dependencies, `DriverFactory`, `BasePage`, `BaseWebTest`, config keys, and TestNG suite updates.

## LLM Layer

Location:

```text
agent/test_script_generator/llm.py
```

The agent uses LangChain `ChatOpenAI` with Mesh API settings:

```text
MESH_API_KEY
MESH_API_BASE_URL
MESH_MODEL
```

The Mesh API is expected to expose an OpenAI-compatible chat endpoint.

## Prompt Rules

Location:

```text
agent/test_script_generator/prompts.py
```

Important prompt rules:

- reuse existing test classes, page objects, helpers, config, API clients, routes, and test data
- do not duplicate existing coverage
- keep generated files minimal
- use Page Object Model for UI tests
- use `ApiClient`, routes, and `TestDataReader` for API tests
- return strict JSON
- preserve existing file content when modifying existing files
