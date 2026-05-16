# Writing Suites

A `.robot` suite for aitester-bdd follows a specific structure. Whether you author by hand or let the LLM generate it, understanding the grammar is essential.

## Minimal suite

```robot
*** Settings ***
Library    aitester_bdd.AITester

*** Variables ***
${ENGINE}    agent-browser

*** Test Cases ***
Homepage Smoke
    [Setup]    Given I start scenario "homepage" at "http://localhost:5173"
    I define rule "main_content"
        Then selector exists "h1"
        And contains "h1" "Welcome"
    [Teardown]    Then I finalize verification
```

Every suite has:

1. **Settings** — imports the keyword library
2. **Variables** — declares the runtime backend
3. **Test Cases** — one or more test cases, each with Setup/Teardown

## The lifecycle

```
[Setup] Given I start scenario "name" at "url"   ← creates a Scenario
    I define rule "rule_name"                      ← opens a Rule
        Given/When/Then ...                        ← adds items to the Rule
    I define rule "another_rule"                   ← opens another Rule
        And I declare parents "rule_name"          ← declares dependency
        ...
[Teardown] Then I finalize verification           ← walks the DAG
```

## Keywords by category

### Scenario lifecycle

| Keyword | Purpose |
|---------|---------|
| `Given I start scenario "${name}" at "${url}"` | Begin scenario with entry URL |
| `Given I start scenario "${name}"` | Begin scenario (no initial navigation) |
| `Then I finalize verification` | Execute the rule DAG |

### Rule definition

| Keyword | Purpose |
|---------|---------|
| `I define rule "${name}"` | Open a named rule block |
| `And I declare parents "${names}"` | Declare parent dependencies (comma-separated) |
| `And I set retry ${max} delay ${ms}` | Configure guard retry-redo |
| `And set rule timeout ${ms}` | Per-rule deadline for all checks |
| `And set child scope "${css}"` | CSS prefix inherited by child rules |

### State checks (Given/Then)

State checks can appear as **guards** (before first action) or **observations** (after an action):

```robot
# As a guard (fast check, skip rule if fails):
I define rule "dashboard"
    Given url contains "/dashboard"    ← guard
    When I click locator ".widget"
    Then count at least ".items" 3     ← observation (waits + fails)
```

| Keyword | Checks |
|---------|--------|
| `url contains "${pattern}"` | URL includes substring |
| `url matches "${regex}"` | URL matches regex |
| `selector exists "${css}"` | Element is in the DOM |
| `selector does not exist "${css}"` | Element is absent |
| `count eq "${css}" "${n}"` | Exact element count |
| `count at least "${css}" "${n}"` | Minimum count |
| `has text "${css}" "${text}"` | Exact text match |
| `contains "${css}" "${substring}"` | Text includes substring |
| `matches "${css}" "${regex}"` | Text matches regex |
| `visible "${css}"` | Element is visible |
| `hidden "${css}"` | Element is hidden |
| `enabled "${css}"` / `disabled "${css}"` | Form element state |
| `checked "${css}"` | Checkbox/radio state |
| `has class "${css}" "${class}"` | CSS class present |
| `input value "${css}" "${value}"` | Form input value |

### Actions (When)

| Keyword | Does |
|---------|------|
| `When I open "${url}"` | Navigate to URL |
| `When I click locator "${css}"` | Click element |
| `When I click text "${text}"` | Click by visible text |
| `When I type "${value}" into "${css}"` | Type into input |
| `When I select "${value}" from "${css}"` | Select dropdown option |
| `When I press keys "${css}" ${keys}` | Keyboard input |
| `When I hover "${css}"` | Mouse hover |
| `When I scroll down` | Scroll the page |
| `When I take screenshot` | Capture current state |

### Interrupts

```robot
*** Test Cases ***
My Test
    [Setup]    Given I start scenario "test" at "http://example.com"
    And I configure interrupts    dismiss=.cookie-banner
    And I configure interrupts    dismiss=.chat-widget
    ...
```

The walker dismisses these selectors before every action.

## Multiple scenarios in one test case

```robot
*** Test Cases ***
Full Flow
    [Setup]    Given I start verification "full"
    Given I start scenario "login" at "http://localhost:5173/login"
    I define rule "authenticate"
        When I type "admin" into "#user"
        When I click locator "#submit"
        Then url contains "/dashboard"

    Given I start scenario "settings" at "http://localhost:5173/settings"
    I define rule "toggle_theme"
        When I click locator "#dark-mode-toggle"
        Then has class "body" "dark"

    [Teardown]    Then I finalize verification
```

Each scenario gets its own entry URL and rules. The walker clears cookies/storage between scenarios for isolation.
