# The Walker (MDP Engine)

The walker is the heart of aitester-bdd's runtime. It interprets the rule DAG as a Markov Decision Process: each rule is a sequence of `(state, action, observation)` tuples executed against a live browser.

## Entry point

```python
def walk_verification(verification, ctx=None):
    if ctx is None:
        ctx = WalkContext.from_env()
    # ... build registry, open browser, walk scenarios
```

Called from `Then I finalize verification`. Everything before this keyword was plan-building.

## Walk algorithm

```
for each scenario:
    navigate to entry_url
    order = topo_sort(scenario.rules)    # Kahn's algorithm
    already_passed = set()

    for rule_name in order:
        rule = rules[rule_name]

        # 1. Parent gating
        if any parent not in already_passed:
            result = FAIL("parent_failed")
            continue

        # 2. Guard check
        guards, body = split_at_first_action(rule.items)
        ok = check_guards(guards)       # short timeout, no waiting

        # 3. Retry-redo (if configured)
        if not ok and rule.retry_max > 0:
            for attempt in range(retry_max):
                execute_body(body)       # replay actions
                ok = check_guards(guards)  # re-check
                if ok: break

        # 4. Body execution
        if ok:
            result = execute_body(body)  # actions + observations

        # 5. Record result
        if result.passed:
            already_passed.add(rule_name)
        verdict.results.append(result)
```

## Topo-sort

Rules declare parents: `And I declare parents "login"`. The walker sorts them parents-before-children using Kahn's algorithm. If a parent fails, all its children are auto-skipped with `failure_step_kind="parent_failed"`.

Cycles raise `ValueError` at sort time (not at execution time).

## Guard semantics

Guards are StateChecks positioned **before** the first Action in a rule. They answer: "is the world already in the expected state?"

- **Timeout:** 200ms (configurable via `set rule timeout`)
- **On failure:** rule is skipped (not failed), unless `guard_policy="abort"`
- **Retry-redo:** if `set retry N delay M` is declared, the walker replays the body N times between guard re-checks

This handles the real-world pattern where AJAX updates haven't landed yet — replay the actions that trigger the update, then re-check.

## Body execution

The body is everything from the first Action onward. For each item:

**Action items:**

1. Dismiss interrupts (cookie banners, modals)
2. Fire `before_action` aspects
3. Execute the action against the browser
4. If it raises → dismiss interrupts + retry once
5. Fire `after_action` aspects
6. Honor `await=<selector>` option (wait for element before continuing)

**StateCheck items (observations):**

1. Wait with full timeout (30s default, or rule's `timeout_ms`)
2. If it passes → fire `after_state_check`, continue
3. If it fails → **fail the rule** with structured evidence

**Emit items:**

1. Capture page state into emit.jsonl
2. Never fail the rule (observation only)

## Interrupt dismissal

Ported from WISE. Before every action, the walker clicks any visible elements matching the verification's `dismiss_selectors`. This handles:

- Cookie consent banners
- Newsletter popups
- Chat widgets
- Any overlay that would block the click target

Per-rule scoping:

- `interrupt_paused` — suppress all dismissals for this rule
- `interrupt_override` — replace the global list with a custom one

## Scope inheritance (TIER 2.5)

A rule can declare `set child scope ".container"`. All its children automatically prefix their selectors with `.container >> `. This enables:

```robot
I define rule "sidebar"
    ...set child scope ".sidebar-panel"

I define rule "sidebar_link"
    And I declare parents "sidebar"
    # All selectors here are automatically scoped under .sidebar-panel
    Then selector exists "a.nav-link"  # resolves to .sidebar-panel >> a.nav-link
```

## Per-rule timeout

`set rule timeout 5000` gives the rule a 5-second deadline. Both guards and observations inherit this timeout. The global run timeout (default 300s, via `AITESTER_RUN_TIMEOUT`) caps the entire verification.

## RuleResult

Every rule produces a `RuleResult`:

```python
@dataclass
class RuleResult:
    rule_name: str
    scenario_name: str
    passed: bool
    failure_step_kind: str      # "guard", "action", "observation_or_assertion", "parent_failed", "run_timeout"
    failure_step_repr: str      # human-readable step that failed
    failure_message: str
    expected: str               # what we wanted
    observed: str               # what we got
    screenshot: str | None      # path to failure screenshot
    ai_diagnosis: str           # LLM explanation (if diagnose aspect is wired)
    duration_ms: float
```

The `Verdict` aggregates all RuleResults and formats a human-readable failure report.
