# Login Flow Example

Demonstrates: parent-child rules, guards, retry-redo, interrupt dismissal, and scope inheritance.

## The suite

`login_flow.robot` tests a typical SPA login + dashboard verification:

1. **Rule `login`** — fills credentials, submits, asserts URL change
2. **Rule `dashboard`** — depends on `login`, checks widget count with retry
3. **Rule `sidebar`** — depends on `login`, opens sidebar, sets child scope
4. **Rule `sidebar_links`** — depends on `sidebar`, checks links within scoped container

## Key patterns shown

### Parent-child dependency
```robot
I define rule "dashboard"
    And I declare parents "login"
```

### Guard with retry-redo
```robot
I define rule "dashboard"
    And I set retry 2 delay 1000
    Given count at least ".widget" 3    # guard — retries if AJAX slow
```

### Interrupt dismissal
```robot
And I configure interrupts    dismiss=.cookie-banner
And I configure interrupts    dismiss=[aria-label="Close chat"]
```

### Scope inheritance
```robot
I define rule "sidebar"
    And set child scope ".sidebar-panel"

I define rule "sidebar_links"
    And I declare parents "sidebar"
    # All selectors automatically scoped under .sidebar-panel
    Then count at least "a.nav-link" 5
```

## Running

```bash
# Requires a running app at localhost:5173 with login/dashboard/sidebar
aitester run login_flow.robot

# Watch it
aitester run login_flow.robot --headed --step-delay 300
```
