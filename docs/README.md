# Documentation

This folder explains how the AI-powered test script generator works, how the workflow moves through the UI, and how code reuse is detected without vector RAG.

## Contents

- [Agent Workflow](agent-workflow.md)
- [How It Works](how-it-works.md)
- [Code Analysis Approach](code-analysis.md)
- [Examples](examples.md)

## Short Summary

The agent takes a GitHub repository, branch, scenario, and optional guidelines. It clones the repository into a temporary local workspace, analyzes the existing automation framework, checks whether the scenario is already covered, and either:

- returns `reuse_existing`, or
- generates a minimal file proposal for human review.

Only after human approval does the backend write files, run validation, commit, push a branch, and raise a pull request.
