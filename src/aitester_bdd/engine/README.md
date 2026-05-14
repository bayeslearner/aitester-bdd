# engine — walker, browser adapter, verdict

## What's here

```
engine/
  walk.py     — rule DAG walker (ports WISE _walk_rule + friends)
  browser.py  — BrowserAdapter (ports WISE _PlaywrightAdapter gotcha-fixes)
  verdict.py  — RuleResult + Verdict (testing-specific evidence)
```

The walker is a *port* of the WISE RPA BDD execution engine, not a
clean-room reimplementation. The architecture is shaped to **test**
(RuleResult / Verdict failure model) rather than **scrape** (WISE's
extraction + checkpoint + emit pipeline), but the execution-time
behaviors that matter on real sites — dismiss-interrupts, guard
retry-redo, action retry-once, fallback selector resolution, `await=`
observation gates, navigation-aware JS, click_text fallback,
set_stepper JS-click — were ported with the WISE source as authority.

The vendored WISE source was used as the reference during the port and
removed once the relevant logic landed here. Don't restore it; if you
need to diff against upstream, fetch from the wise-rpa-bdd skill repo
rather than re-vendoring.

When porting another piece of upstream behavior, **read the upstream
method first and port the real logic, not a re-derivation from the
architecture diagram.** Clean-room rewrites of battle-tested code lose
every gotcha-fix that wasn't obvious from the high-level shape.

## What's ported

| WISE method                              | aitester-bdd location                     |
|------------------------------------------|-------------------------------------------|
| `_check_guards` (with retry-redo)        | `walk._check_guards` + `walk._walk_rule`  |
| `_execute_steps` (interrupts + retry)    | `walk._execute_body`                       |
| `_dismiss_interrupts_with`               | `walk._dismiss_interrupts`                 |
| `_get_interrupt_selectors` (per-rule)    | `walk._effective_interrupt_selectors`      |
| `_eval_state_check`                      | `walk._eval_state_check` (expanded kinds)  |
| `_resolve_fallback_selector`             | `BrowserAdapter.resolve_fallback_selector` |
| `click_text` with JS MouseEvent fallback | `BrowserAdapter.click_text`                |
| `evaluate_js` with navigation detection  | `BrowserAdapter.evaluate_js`               |
| `set_stepper` JS-click                   | `BrowserAdapter.set_stepper`               |
| `await=` observation gate                | `walk._await_after_action`                 |
| `_wait_page_ready`                       | `BrowserAdapter.wait_for_load_state`       |
| `_topo_sort` (Kahn's algorithm)          | `walk._topo_sort`                          |
| per-rule `timeout_ms`                    | `walk._walk_rule` `rule_deadline`          |
| global run timeout                       | `walk.walk_verification` `run_deadline`    |
| `on_enter`/`on_fail` screenshot          | `walk._walk_rule`                          |

## What's deliberately NOT ported (scraping-specific)

WISE is a scraper; aitester-bdd is a tester. These were dropped:

* `FieldSpec` / `TableSpec` / `_extract_*` — extraction is the wrong
  primitive for testing.
* `Expansion` / `_expand_*` (elements, pages_next, pages_numeric,
  combinations) — pagination is scraping. Tests iterate via parent-child
  rules.
* `ArtifactSchema` / `_emit_records` / `PersistentArtifactStore` /
  checkpoint — scraping output. Tests emit Verdicts, not artifacts.
* AI extraction.
* `_NodriverAdapter` + stealth bridge — for anti-bot SCRAPING. Internal
  app testing doesn't need stealth.
* `_resolve_entry_urls` template expansion — scraping artifact-driven
  URL templates.
* `_run_setup` — duplicates what is better expressed as a setup rule
  inside the test itself.

## What's testing-specific (NOT in WISE)

* **Post-action StateCheck failure FAILS the rule** with structured
  evidence (RuleResult). WISE only logs a warning ("Observation gate
  failed: ...") because for scraping, a missed observation isn't fatal.
  For testing it is.
* **Verdict aggregation** with screenshots, expected/observed,
  failure_step_repr — formatted for human + CI consumption.
* **`api_returns` StateCheck** — direct httpx call to verify backend state
  beyond what the UI shows. Scrapers don't do this.

## When to update this README

* When porting another WISE method into the engine.
* When the testing semantics diverge from WISE somewhere new.
* When upstream wise-rpa-bdd ships a new gotcha-fix worth porting.
