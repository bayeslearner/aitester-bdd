# Actions

Actions drive the browser — clicking, typing, navigating. They always appear in the rule body (after any guards) and fire `before_action`/`after_action` aspect hooks.

## Navigation

```robot
When I open "http://localhost:5173/settings"
When I reload
When I go back
When I add url params "?debug=true&tab=2"
```

## Click

```robot
When I click locator "#submit-btn"
When I click locator "[data-testid='save']"    await=.toast-success
When I click text "Sign In"
When I double click locator ".editable-cell"
```

The `await=<selector>` option waits for the specified element to appear after the click (synchronization gate for async actions).

## Type / Fill

```robot
When I type "admin@example.com" into "#email"
When I type "hunter2" into "#password"    secret
When I fill locator "#search" "query text"
```

`secret` flag masks the value in logs. `fill` is an alias for `type`.

## Select / Check

```robot
When I select "United States" from "#country"
When I check "#terms-checkbox"
When I uncheck "#newsletter"
```

## Keyboard

```robot
When I press keys "#search" Enter
When I press keys "body" Control+a
When I press keys "#editor" Shift+Tab
```

Multiple keys separated by spaces. Modifier+key combos with `+`.

## Mouse

```robot
When I hover ".tooltip-trigger"
When I focus "#input-field"
When I scroll down
```

## File upload

```robot
When I upload file "/path/to/document.pdf" into "#file-input"
```

## Screenshot

```robot
When I take screenshot
When I take screenshot    filename=after_login.png
```

## JavaScript

```robot
When I evaluate js "document.querySelector('#hidden-btn').click()"
When I evaluate js "window.scrollTo(0, document.body.scrollHeight)"
```

Escape hatch for actions that can't be expressed via the standard keyword vocabulary.

## Shell

```robot
When I run shell "curl -X POST http://localhost:5175/api/reset"
When I run shell "sleep 2 && curl http://localhost:5175/api/status"    timeout_ms=10000
```

Runs a shell command during the walk. Results are queryable via `last shell exit/stdout/stderr` state checks.

## Stepper

```robot
When I set stepper ".quantity-input" "5"
```

For increment/decrement buttons: clicks the button N times with JS-click (handles re-rendering between clicks).

## Date picker

```robot
When I select date "2026-03-15"
When I select date "2026-03-15"    forward=.next-month    heading=.calendar-title
```

Navigates a date picker by clicking forward/backward until the target month is visible, then clicks the day.

## Browser step (passthrough)

```robot
And I browser step "fill_form"    field1=value1    field2=value2
And I call keyword "Custom Setup Keyword"    arg1    arg2
```

Passthrough to backend-specific methods or other Robot Framework keywords.

## LLM interaction

```robot
When I ask LLM "Based on the current page, what is the user's account status?"
```

Captures the current page text, sends it to the LLM with the prompt, stores the response for subsequent `llm response contains/semantic` checks.

## Interrupt dismissal

Before **every** action, the walker automatically dismisses any visible elements matching the configured interrupt selectors:

```robot
And I configure interrupts    dismiss=.cookie-banner
And I configure interrupts    dismiss=[aria-label="Close"]
```

If an action raises (element obscured), the walker dismisses interrupts and retries the action once. This handles modals that appear between the dismiss check and the action.

## The `await=` option

Any click or type action can include `await=<selector>`:

```robot
When I click locator "#submit"    await=.success-toast
```

After the action completes, the walker waits for `<selector>` to appear (30s timeout) before advancing to the next item. This is the MDP synchronization gate — it tells the walker "the action isn't done until this element appears."
