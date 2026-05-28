# Agent Workflow

The UI is organized around workflow stages. Click any stage to see its details.

## Stages

1. **Request received**
   - Captures repository URL, branch, scenario, guidelines, and force-generation setting.

2. **Clone repository**
   - Clones the selected GitHub branch into a temporary local workspace.
   - Uses the GitHub token from `agent/.env`.
   - Temporary clone folders are ignored and cleaned after the run.

3. **Analyze reuse**
   - Scans Java source and test files.
   - Builds a catalog of classes, methods, annotations, JavaDoc, page objects, API helpers, config, and JSON test data.
   - Checks whether the scenario appears already automated.

4. **Crawl web app**
   - Runs only for web UI scenarios, detected from URLs or UI intent such as browser, page, form, click, field, button, or search.
   - Collects lightweight page evidence from the target URL, including title, forms, inputs, buttons, and links.
   - Builds a raw action plan from the scenario steps and crawl evidence.
   - Skips this stage for API or non-web scenarios.

5. **Generate proposal**
   - If existing coverage is found, generation is skipped.
   - If new web UI coverage is required, the crawl evidence and raw action plan are added to the context pack.
   - If new code is required, the agent sends a compact repository context pack to the LLM.
   - The LLM returns strict JSON with proposed files, file contents, rationale, and validation commands.

6. **Human review**
   - Generated files are displayed in the UI.
   - Reviewer can inspect proposed scripts before any repository changes are made.

7. **Approval**
   - Reviewer approves the proposal.
   - Approval is disabled when the decision is `reuse_existing` because there are no files to commit.

8. **Run validation**
   - Runs generated Maven validation commands, such as `mvn clean test`.
   - The backend currently allows Maven commands only.

9. **Commit changes**
   - Writes generated files into a fresh clone.
   - Creates a local Git commit.

10. **Push branch**
   - Pushes the generated branch to the same GitHub repository.
   - Branch name format:

```text
codex/test-script-generator-<run_id>
```

11. **Open pull request**
    - Creates a GitHub pull request from the generated branch into the selected base branch.

## Decision Types

```text
reuse_existing
```

The agent found matching existing coverage. No files are generated.

```text
generate
```

The agent generated a proposal and waits for human review.

```text
needs_clarification
```

The agent could not safely generate without more information.
