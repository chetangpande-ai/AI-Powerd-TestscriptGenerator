# Code Analysis Approach

The agent does **not** use vector RAG for repository code.

Instead, it uses deterministic code scanning and lexical matching. This makes behavior easier to audit and debug.

## Scanner

Location:

```text
agent/test_script_generator/scanner.py
```

The scanner reads these repository roots:

```text
src/main/java
src/test/java
src/test/resources/config
src/test/resources/testdata
```

## Cataloged Items

For Java files, the scanner extracts:

- package name
- class name
- parent class from `extends`
- class-level annotations
- public/protected/private method names
- method signatures
- method annotations such as `@Test`
- nearby JavaDoc descriptions
- repo-relative file paths

For resources, it records:

- config files
- JSON test data files

## Test Detection

A Java class is treated as an existing test class when:

- it is under `src/test/java`
- at least one method has an annotation beginning with `Test`

Example:

```java
@Test(groups = {"api", "crud"})
public void getUsersReturnsAvailableUsers() {
    ...
}
```

## Existing Scenario Match

The agent checks whether the scenario is already automated using:

- scenario tokens
- class names
- method names
- method signatures
- JavaDoc descriptions

It removes weak/generic tokens such as:

```text
api, automation, crud, create, delete, framework, generate, management, new, patch, test, update
```

This prevents generic overlap from causing false reuse.

For example:

```text
User Management CRUD API: verify GET /users returns available users.
```

can match:

```text
UserManagementCrudTest#getUsersReturnsAvailableUsers
```

But:

```text
Product Management CRUD API: automate /posts CRUD operations.
```

should not be treated as covered by `UserManagementCrudTest`, because the strong domain token `product` is not present in the existing user test.

## Context Selection

If generation is needed, the scanner selects a compact set of files for the LLM.

Files are scored by lexical overlap with the scenario. Foundation classes get a small score boost:

Common:

```text
ConfigManager
TestDataReader
```

Web:

```text
BasePage
BaseWebTest
```

API:

```text
BaseApiTest
ApiClient
ApiRoutes
```

The selected files are rendered into a context pack.

## Context Pack

The context pack includes:

- framework facts
- known page objects
- known tests
- selected source files
- selected config/test data
- web crawl evidence for UI scenarios
- raw UI action plan for brand-new web scenarios
- the user scenario

The LLM receives this compact pack, not the whole repository.

## Web Crawl Evidence

Web crawl is not vector retrieval. It is a deterministic evidence-gathering step used only when the scenario looks like a web UI test.

The crawler:

- reads explicit URLs from the scenario or guidelines
- reads fallback URLs from `src/test/resources/config/**/*.properties`
- fetches a small number of target pages
- extracts page titles, forms, inputs, buttons, and links with an HTML parser
- builds a raw action plan from the user steps and discovered page controls

The LLM then converts that raw action plan into the target framework style. Existing page objects, base classes, config readers, and test data still take priority over creating new code.

## Why This Is Not RAG

No embeddings are created.

No vector database is used.

No semantic retrieval system is involved.

The process is:

```text
scan files -> extract symbols -> score text deterministically -> build context pack -> ask LLM
```

## Strengths

- easier to audit
- deterministic
- no separate indexing service
- no stale vector index
- works well for structured automation repositories

## Limitations

- lexical matching can miss scenarios phrased very differently
- Java parsing is regex-based, not a full compiler AST
- the web crawler reads server-rendered HTML and does not execute JavaScript-heavy flows
- the scanner currently targets Java Maven/TestNG repository structure
- generated code still requires human review before commit
