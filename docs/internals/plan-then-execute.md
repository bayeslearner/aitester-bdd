# The Plan-Then-Execute Model

This is the core architectural insight of aitester-bdd: **keywords don't execute — they build a plan. Execution happens once, all at once, in a controlled walk.**

## Why deferred execution?

In a naive approach, each Robot Framework keyword would immediately drive the browser:

```robot
# NAIVE (not how aitester-bdd works)
When I click ".login-btn"     ← immediately clicks
Then selector exists ".dashboard"  ← immediately checks
```

This seems simpler but causes problems:

1. **No rule ordering** — you can't express "rule B depends on rule A passing"
2. **No retry-redo** — if a guard fails, you can't replay the body and re-check
3. **No aspects** — there's no transition point to hook timing, logging, or diagnosis into
4. **No scope inheritance** — child rules can't inherit a parent's DOM scope
5. **No topo-sort** — execution order is file order, not dependency order

## How it actually works

### Phase A: Plan (keyword execution)

Every keyword appends to an in-memory `Verification` model:

```python
# What happens when RF calls "When I click locator '.btn'"
def when_click_locator(self, css):
    self._current_rule().items.append(Action("click", target=css))
```

Nothing touches the browser. The keyword just records *what to do later*.

After all keywords run, the model looks like:

```
Verification "login flow"
  └── Scenario "happy path" (entry_url="http://localhost:5173")
      ├── Rule "login"
      │   ├── [Guard] selector_exists ".login-form"
      │   ├── [Action] type "admin" into "#username"
      │   ├── [Action] type "secret" into "#password"
      │   ├── [Action] click "#submit"
      │   └── [Observation] url_contains "/dashboard"
      └── Rule "see_widgets" (parents: ["login"])
          ├── [Guard] url_contains "/dashboard"
          └── [Observation] count_at_least ".widget" 3
```

### Phase B: Execute (walker)

`Then I finalize verification` calls `walk_verification(verification)`:

1. **Build WalkContext** — resolve headed mode, step delay, timeouts from env
2. **Wire aspects** — trajectory recording, instrumentation, diagnosis, step delay
3. **Open browser** — single session for all scenarios
4. **For each scenario:**
    - Navigate to `entry_url`
    - Topo-sort rules by parent dependencies
    - Walk each rule in order:
        - Check guards (fast timeout, no waiting)
        - If guards pass → execute body (actions + observations)
        - If guards fail + retry configured → replay body, re-check
        - Fire aspects at every transition
5. **Collect Verdict** — pass/fail per rule with structured evidence

### The split point

Every item in a rule's `items` list gets split at the first Action:

```
[StateCheck, StateCheck, Action, StateCheck, Action, StateCheck]
 ├── guards ──────────┤├── body ─────────────────────────────┤
```

- **Guards** (before first Action): checked with a short timeout (200ms). They ask "is the world already in the right state?" If not, the rule is skipped (or retried).
- **Body** (from first Action onward): Actions execute against the browser. Inline StateChecks after actions are **observations** — they wait with a long timeout (30s) and **fail the rule** if they don't pass.

This position-determined semantics means the same `StateCheck` type behaves differently based on where the author placed it. No explicit "assert" vs "wait" keywords needed.

## The Verification model

```python
@dataclass
class Verification:
    name: str
    scenarios: list[Scenario]
    interrupts: InterruptConfig      # global dismiss selectors
    state_setup: StateSetup          # suite-level auth/consent

@dataclass
class Scenario:
    name: str
    entry_url: str
    rules: dict[str, Rule]           # ordered dict

@dataclass
class Rule:
    name: str
    items: list[Action | StateCheck | Emit]
    parents: list[str]               # dependency names
    retry_max: int                   # guard retry count
    rule_type: str                   # "pinned" or "explore"
    # ... options, scope, interrupt overrides
```

## Why this matters for testing

The deferred model gives aitester-bdd properties that immediate-execution frameworks lack:

| Property | How |
|----------|-----|
| Dependency ordering | Topo-sort places parents before children |
| Guard-based skipping | If parent failed, child is auto-skipped |
| Retry-with-redo | Replay body → re-check guards (handles AJAX timing) |
| Scope inheritance | Child rules inherit parent's CSS scope prefix |
| Cross-cutting aspects | Every transition fires hooks without touching rule logic |
| Structured failure evidence | Walker knows exactly which step failed, with expected/observed |
| AI diagnosis | Full trajectory is available for the LLM to reason about |
