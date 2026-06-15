# Exploration driver map — CLI vs in-RF, and where the 30s stall lives

Written 2026-06-15 while diagnosing a 30s-per-probe stall in `aitester author`.
Captures a real inconsistency: **the same logical "explore" operation runs on
two different browser drivers depending on entry point.**

## Two entry points, one agent function, two drivers

Both entry points converge on the same agent functions in
`authoring/agent_loop.py` (`author_with_agent` / `explore_with_agent`), then
**diverge on the browser driver** via `_is_inside_rf()`:

| | CLI `aitester author` | in-RF `I explore` / `I explore and author` |
|---|---|---|
| Entry | `cli.py:75` → `author_with_agent` | `AITester.py:1890/1927` records a plan node → walk time `engine/walk.py:897` → `explore_with_agent` |
| `_is_inside_rf()` | **False** | **True** |
| Tools given to the deep agent | terminal tools only + `LocalShellBackend` `execute` | typed `browser_*` tools (`build_playwright_browser_tools`) |
| Browser driver | **agent-browser CLI** (third-party tool), driven by the agent **writing shell commands** (`agent-browser get text '…'`) through `execute` | **Playwright** via `_PlaywrightBackend` → the shared **robotframework-browser** `Browser` session (`engine/browser.py`) |
| Prompt | `_EXPLORE_SYSTEM_PROMPT` (agent-browser cheatsheet) | `PLAYWRIGHT_EXPLORE_PROMPT` (browser_* tool cheatsheet) |

So:
- The **explore-and-author keyword IS equivalent to the CLI author** in *agent
  logic* (same `author_with_agent`, `mode="explore_and_author"`) — but they run
  on **different drivers**. That's the inconsistency.
- The **in-RF path does NOT use agent-browser.** It uses Playwright typed tools
  — exactly as expected, because the suite runtime supports
  agent-browser | playwright | nodriver, so the embedded explorer goes through
  tool-calling against the (here) Playwright backend. The deep agent calls
  `browser_get_text` / `browser_get_count` / `browser_eval`, not `agent-browser`.

## Runtime (exploitation) backends — separate from the above

The authored suite's *deterministic walk* (Phase B, `Then I finalize
verification`) uses one of three engine backends selected by `${ENGINE}`:
`engine/agent_browser_backend.py` (wraps the agent-browser CLI),
`engine/browser.py` (Playwright/robotframework-browser),
`engine/nodriver_backend.py`. Each implements `get_text` / `get_count` /
`evaluate_js`. These are the *exploitation* drivers; the auto-wait there is
desirable (selectors are known-good).

## Where the 30s stall lives — and where it does NOT

Localized to the **agent-browser CLI path only** (CLI `aitester author`
exploration). Direct timing of the third-party `agent-browser` binary on
`quotes.toscrape.com/js/`:

| command | result | time |
|---|---|---|
| `get count '.quote'` | 10 | 0.02s (fail-fast) |
| `eval '…querySelectorAll…'` | n | ~0s (fail-fast) |
| `get html '.quote'` (matches) | strict-mode error | 0.02s |
| `get text '.nonexistent'` (0 matches) | **30s** then `os error 35` | **30.0s** |

`get text/html/attr` sit on the underlying Playwright locator's **default 30s
timeout** when the selector matches 0 elements (surfaced confusingly as a socket
"Resource temporarily unavailable" because the CLI client's read gives up).
During *exploration* the agent probes selectors that momentarily match 0 → 30s
per miss. `get count` and `eval` do **not** auto-wait, so they're the correct
exploration primitives; the agent just isn't constrained to them.

The in-RF Playwright path's `_get_text` (`playwright_tools.py:147`) wraps
`_PlaywrightBackend.get_text` → robotframework-browser `Get Text`, which uses
the **Browser library's configurable timeout** (default 10s, settable), and the
backend swallows the exception to `""`. So the in-RF explorer has a *different,
shorter, configurable* wait — not the agent-browser 30s pathology.

## Implications

1. **The planning A/B was run via the CLI path** (`aitester author`) — i.e. on
   the agent-browser driver with the 30s-per-miss tax. Its wall-clock was
   dominated by probe-miss roulette, NOT planning. The inception feature people
   actually use (`I explore` in a `.robot`) runs on Playwright and would not
   show the same stalls. **The CLI path is not representative of the in-RF
   feature.**
2. **The inconsistency to resolve:** one logical "explore" op, two drivers
   selected by `_is_inside_rf()`, with different probing semantics and different
   prompts. They should converge — at minimum the CLI path's selector probing
   should be made fail-fast (steer the agent to `get count`/`eval`, or set a
   short agent-browser `get` timeout if/when the third-party CLI exposes one) so
   it behaves like the Playwright path.

## Corrections to earlier claims (mine)

- agent-browser is a **third-party** CLI, not "kundeng's package" — I wrongly
  inferred ownership from the `@bayeslearner/...` install string. The fix is on
  the *usage* side (probe fail-fast), not "edit your package".
- The 30s is **not** an inherent "agent-browser is the wrong driver"
  verdict — it's a too-long default `get` timeout on the *missing-selector*
  case, and the driver already ships fail-fast primitives (`count`, `eval`).

## Open questions

- Should the CLI path use Playwright too (true driver convergence), or should
  the agent-browser exploration prompt forbid `get text/html` on unverified
  selectors (probe via `count`/`eval` first)?
- Does the in-RF Playwright explorer actually avoid the stall in practice?
  (Untested live here — it uses a 10s Browser-lib timeout, so a miss still costs
  up to 10s; worth measuring before assuming it's clean.)
