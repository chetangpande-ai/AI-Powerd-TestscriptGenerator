# Examples

Use these examples with the UI.

Repository:

```text
https://github.com/chetangpande-ai/Test-Automation-Project1.git
```

Branch:

```text
main
```

## Example 1: Existing Scenario

Scenario:

```text
User Management CRUD API: verify GET /users returns available users and includes user id 1.
```

Expected result:

```json
{
  "decision": "reuse_existing",
  "status": "reuse_existing"
}
```

Why:

The repository already contains:

```text
src/test/java/com/chetanpande/automation/tests/api/UserManagementCrudTest.java
```

The existing method covers the scenario:

```text
getUsersReturnsAvailableUsers
```

The approval button is disabled because there are no generated files to commit.

## Example 2: Brand-New Scenario

Scenario:

```text
Product Management CRUD API: create reusable route constants and TestNG API tests for /posts. Automate create product, get product by id, update product, patch product title, and delete product. Use existing framework standards, JSON test data, BaseApiTest, ApiClient, ConfigManager, reporting, and TestDataReader.
```

Expected result:

```json
{
  "decision": "generate",
  "status": "waiting_for_review"
}
```

Expected generated files:

```text
src/main/java/com/chetanpande/automation/api/ProductRoutes.java
src/test/resources/testdata/product-management-test-data.json
src/test/java/com/chetanpande/automation/tests/api/ProductManagementCrudTest.java
```

Why:

The framework already has reusable API foundations:

```text
BaseApiTest
ApiClient
ConfigManager
TestDataReader
Extent reporting
Log4j logging
```

But Product Management coverage does not exist, so the agent should generate only product-specific files.

## Example 3: Partially Automated Scenario

Scenario:

```text
User Management CRUD API: add validation for partially updating an existing user's phone number using PATCH /users/{id}. Reuse the existing UserManagementCrudTest, UserRoutes, ApiClient, BaseApiTest, and JSON test data. Add only the missing test data and test method needed.
```

Expected result:

```json
{
  "decision": "generate",
  "status": "waiting_for_review"
}
```

Expected behavior:

- reuse existing `UserManagementCrudTest`
- reuse existing `UserRoutes`
- reuse existing `ApiClient`
- reuse existing JSON test-data file
- add only the missing phone patch data and test method

This is the best scenario to validate partial automation behavior.

## Example 4: Needs Clarification

Scenario:

```text
Automate login validation.
```

Possible result:

```json
{
  "decision": "needs_clarification"
}
```

Why:

The scenario does not say:

- web or API
- application URL
- expected user role
- positive or negative path
- expected assertions

The agent should avoid guessing when the scenario is too vague.

## Example 5: Brand-New Web UI Scenario

Scenario:

```text
Web UI: automate Google search smoke test for https://www.google.com. Open the home page, search for Selenium WebDriver, submit the search, and verify the results page is shown. Reuse existing web framework code if present. If no matching test exists, crawl the page, create a raw UI action plan, then generate Selenium TestNG Page Object Model code.
```

Expected result:

```json
{
  "decision": "generate",
  "status": "waiting_for_review"
}
```

Expected behavior:

- the `Crawl web app` stage is completed
- raw action steps are shown in the UI
- page evidence shows detected inputs, buttons, links, or crawl errors
- generated code uses existing `BasePage`, `BaseWebTest`, driver utilities, config, and reporting when available
- if the repository has no web framework yet, only minimal Selenium/TestNG framework additions are proposed

After reviewer approval, the backend validates the Maven commands returned by the LLM, commits the approved files, pushes a generated branch, and raises a pull request.
