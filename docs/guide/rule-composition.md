# Rule Composition

Rules are the building blocks of aitester-bdd tests. They compose into a directed acyclic graph (DAG) via parent declarations, enabling dependency ordering, scope inheritance, and structured failure cascading.

## Parent-child dependencies

```robot
I define rule "login"
    When I type "admin" into "#username"
    When I click locator "#submit"
    Then url contains "/dashboard"

I define rule "see_widgets"
    And I declare parents "login"
    Given url contains "/dashboard"    # guard — verifies parent's postcondition
    Then count at least ".widget" 3
```

If `login` fails, `see_widgets` is automatically skipped with `failure_step_kind="parent_failed"`. No explicit `Run Keyword If` needed.

## Multiple parents

```robot
I define rule "compose_email"
    And I declare parents "login, open_inbox"
    ...
```

All listed parents must pass before the child executes. Comma-separated.

## Guards vs observations

The **position** of a StateCheck determines its behavior:

```robot
I define rule "dashboard_widgets"
    Given url contains "/dashboard"        # GUARD — before first action
    Given selector exists ".widget-grid"   # GUARD — fast check, no waiting
    When I click locator ".refresh-btn"    # First action — splits guard/body
    Then count at least ".widget" 5        # OBSERVATION — waits up to 30s
    And contains ".widget:first-child" "Revenue"  # OBSERVATION
```

| Position | Timeout | On failure |
|----------|---------|-----------|
| Guard (before first action) | 200ms | Skip rule (or retry) |
| Observation (after an action) | 30,000ms | **Fail** the rule |

## Retry-with-redo

For timing-sensitive guards (AJAX content that hasn't loaded yet):

```robot
I define rule "data_loaded"
    And I set retry 3 delay 500
    Given count at least ".data-row" 10   # guard — might fail on first try
    When I click locator ".export-btn"
    Then selector exists ".download-link"
```

If the guard fails, the walker:
1. Waits 500ms
2. Replays the body (clicks the export button)
3. Re-checks the guard
4. Repeats up to 3 times

This handles the real-world pattern where actions trigger async updates.

## Scope inheritance

A parent rule can declare a CSS scope that all its children inherit:

```robot
I define rule "sidebar"
    When I click locator ".sidebar-toggle"
    Then selector exists ".sidebar-panel"
    And set child scope ".sidebar-panel"

I define rule "nav_links"
    And I declare parents "sidebar"
    # All selectors here are automatically prefixed with .sidebar-panel >>
    Then count at least "a.nav-link" 5
    And contains "a.nav-link:first-child" "Home"
```

Children don't need to repeat the parent's container selector. This keeps rules DRY and makes refactoring (if the container class changes) a one-line fix.

## Per-rule timeout

Override the default observation timeout (30s) for slow pages:

```robot
I define rule "heavy_report"
    And set rule timeout 60000    # 60 seconds
    When I click locator "#generate-report"
    Then selector exists ".report-table"   # waits up to 60s
```

Both guards and observations inherit the rule timeout.

## Interrupt scoping

By default, all rules inherit the verification's global dismiss selectors. Override per-rule:

```robot
# Pause all interrupt dismissal for this rule
I define rule "test_modal"
    And I pause interrupts
    When I click locator "#open-modal"
    Then selector exists ".modal-body"   # modal IS the thing we're testing

# Use a different dismiss list
I define rule "cookie_flow"
    And I scope interrupts ".other-popup"
    When I click locator ".cookie-settings"
    Then selector exists ".cookie-preferences"
```

## Guard policy

By default, a failed guard skips the rule. To abort the entire run instead:

```robot
I define rule "critical_precondition"
    And I set guard policy "abort"
    Given selector exists "#app-root"
```

If `#app-root` doesn't exist, the run stops immediately (the app isn't loaded).

## Explore rules (fluid)

```robot
I define rule "pinned_setup"
    When I type "admin" into "#user"
    When I click locator "#login"
    Then url contains "/dashboard"

When I explore "Navigate to settings and verify all toggles are functional"
```

Explore rules participate in the DAG — they auto-parent to the most recent rule. The walker hands its browser session to the LLM agent when it reaches the explore node.

## Execution order

Rules are topologically sorted: parents always execute before children. Among siblings (no dependency between them), execution follows declaration order in the `.robot` file.

```
login ──────────┐
                ├── dashboard_widgets
open_sidebar ───┘
                └── sidebar_links
```

Order: `login` → `open_sidebar` → `dashboard_widgets` → `sidebar_links`
