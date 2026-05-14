# engine — walker, browser adapter, verdict

## What's here

```
engine/
  walk.py            — rule DAG walker (ports WISE _walk_rule + friends)
  browser.py         — BrowserAdapter (ports WISE _PlaywrightAdapter gotcha-fixes)
  verdict.py         — RuleResult + Verdict (testing-specific evidence)
  _wise_source.py    — vendored WISE engine, kept for reference
```

`_wise_source.py` is a verbatim copy of the WISE RPA BDD engine. It is
the source of truth for every gotcha-fix the walker has ported. If a
test fails or a real-site regression appears, **diff walk.py against
_wise_source.py before "fixing" by deleting code** — the deletion is
almost certainly removing a battle-tested gotcha-fix.

The walker is a *port*, not a clean-room reimplementation. The
architecture is shaped to test (RuleResult/Verdict failure model) rather
than scrape (WISE's extraction + checkpoint + emit pipeline), but the
execution-time behaviors that matter on real sites — dismiss-interrupts,
guard retry-redo, action retry-once, fallback selector resolution,
`await=` observation gates, navigation-aware JS, click_text fallback,
set_stepper JS-click — are all ported with the WISE source as authority.

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
* When `_wise_source.py` is updated (sync from upstream wise-rpa-bdd).
