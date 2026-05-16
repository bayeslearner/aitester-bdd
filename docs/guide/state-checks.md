# State Checks

State checks are assertions about the current page state. Their behavior depends on **position** — before the first action they're guards (fast, skip on fail); after an action they're observations (wait, fail on timeout).

## URL checks

```robot
Given url contains "/dashboard"
Then url matches "^https://.*\\.example\\.com/app"
But url does not contain "/login"
```

URL checks poll every 100ms until timeout when used as observations.

## Element existence

```robot
Then selector exists "[data-testid='user-card']"
Then selector does not exist ".error-banner"
```

Uses Playwright's native element-state waiter (attached/detached). More reliable than polling `get_count`.

## Element count

```robot
Then count eq ".notification" "3"
Then count at least ".data-row" "10"
Then count at most ".warning" "2"
```

Counts are instant (no polling) — they report the current count. Use as observations when the count should have stabilized after an action.

## Text content

```robot
Then has text "h1" "Welcome back, Admin"
Then contains ".status-badge" "Active"
Then matches ".version" "v\\d+\\.\\d+\\.\\d+"
And not contains ".output" "Error"
```

- `has text` — exact match (trimmed)
- `contains` — substring match
- `matches` — regex match
- `not contains` — absence of substring

## Element state

```robot
Then visible ".modal"
Then hidden ".loading-spinner"
Then enabled "#submit-btn"
Then disabled "#locked-field"
Then checked "#remember-me"
```

## CSS class

```robot
Then has class "body" "dark-theme"
And not class ".nav-item:first-child" "disabled"
```

## Attributes

```robot
Then attr eq "[data-testid='status']" "data-value" "active"    attr=data-value
Then attr contains ".avatar" "src" "cloudinary"    attr=src
```

## Form values

```robot
Then input value "#email" "user@example.com"
Then select selected "#country" "US"
```

## Table headers

```robot
Then table headers "table.users" "Name|Email|Role|Status"
```

Pipe-delimited expected headers. Matches against `<thead> th` cells in order.

## Network (last response)

```robot
Then last status "200"
Then last body contains "success"
```

Checks the last HTTP response observed by the browser. Useful after form submissions.

## Shell (after `When I run shell`)

```robot
When I run shell "curl -s http://localhost:5175/api/health"
Then last shell exit "0"
And last shell stdout contains "ok"
And last shell stderr contains ""
```

## Semantic (AI-judged)

```robot
Then semantic "The page shows a successful login with a welcome message"
Then visual semantic "The chart shows an upward trend in the last 7 days"
```

Escape hatches that invoke the LLM at run time. `semantic` passes page text; `visual_semantic` passes a screenshot. Use sparingly — they cost tokens per assertion.

## LLM response (after `When I ask LLM`)

```robot
When I ask LLM "Summarize the visible data"
Then llm response contains "revenue"
Then llm response semantic "The response mentions positive growth"
```

## Position semantics summary

```robot
I define rule "example"
    # ─── GUARDS (before first action) ───
    Given url contains "/app"            # 200ms timeout, skip if fails
    Given selector exists "#app-root"    # 200ms timeout, skip if fails

    # ─── BODY (from first action onward) ───
    When I click locator "#refresh"      # action

    # ─── OBSERVATIONS (after action) ───
    Then count at least ".item" 5        # 30s timeout, FAIL if times out
    And contains ".status" "Ready"       # 30s timeout, FAIL if times out
```

The same `selector exists` keyword behaves completely differently based on where you place it. This is the core ergonomic win of position-determined semantics.
