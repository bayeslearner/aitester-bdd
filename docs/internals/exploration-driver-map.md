# Exploration driver map — CLI vs in-RF, and where the 30s stall lives

Written 2026-06-15 while diagnosing a 30s-per-probe stall in `aitester author`.
Captures a real inconsistency: **the same logical "explore" operation runs on
two different browser drivers depending on entry point.**

## Three exploration approaches, compared

Both Python entry points converge on the same agent functions in
`authoring/agent_loop.py` (`author_with_agent` / `explore_with_agent`), then
**diverge on the browser driver** via `_is_inside_rf()`. The TypeScript port
(`@picobay/engine`) is a separate implementation of the same idea. Full matrix:

| property | **Py · CLI** `aitester author` | **Py · in-RF** `I explore` (suite) | **TS port** `@picobay/engine` |
|---|---|---|---|
| Entry | `cli.py:75` → `author_with_agent` (`_is_inside_rf=False`) | `AITester.py:1890/1927` plan node → `engine/walk.py:897` → `explore_with_agent` (`_is_inside_rf=True`) | `ToolLoopAgent` → `exploreGoal`/`generateDeployment` (`inception-executor.ts`) |
| Browser driver | **agent-browser CLI** (3rd-party) | **Playwright** via `_PlaywrightBackend` → robotframework-browser (`engine/browser.py`) | **`BrowserDriver` interface** — CDP (`chrome.debugger`) in the extension, Playwright in CLI/eval |
| Transport | subprocess shell-out per command (daemon session) | in-process typed tool calls | in-process (CDP or Playwright) |
| Agent tool surface | **raw shell strings** — agent writes `agent-browser get text '…'` via `execute` | **typed** `browser_*` StructuredTools | **typed** inception tools over `BrowserDriverExplorer` |
| Probe wrapper | **none** — agent calls getters directly, eats the wait | backend `try/except → ""` (returns empty, but *after* the wait) | **explicit fail-fast** — `count()→0`, `text()→""`, `attr()→""` on any error, returns immediately (`agents/driver-explorer.ts:69-91`) |
| Content-getter on **missing** selector | **30s hang** (`get text/html/attr/value/box`), then `os error 35` | up to the **Browser-lib timeout** (~10s default, configurable) | **instant** (CDP `getText` is a direct DOM query; no auto-wait) |
| Fail-fast existence probe | `get count` / `is visible` / `eval` (0s) | `browser_get_count` / `browser_eval` (fast) | `count()` (0s) — and *all* probes are wrapped fail-fast |
| Timeout default / override | **30s, no CLI flag/env to change** | ~10s, `Set Browser Timeout` | configurable: `setBrowserTimeout()`, `waitForSelector(…, timeoutMs)` |
| Prompt | `_EXPLORE_SYSTEM_PROMPT` (agent-browser cheatsheet) | `PLAYWRIGHT_EXPLORE_PROMPT` | spec-11 explorer prompt |
| Driver swappable? | no (hardwired to agent-browser CLI) | no (hardwired to Playwright/RF) | **yes** — driver is an injected interface |
| Verified live (2026-06-15)? | yes (the 30s stall) | **no** (inferred from code) | n/a here |

Key takeaways:
- The **explore-and-author keyword IS equivalent to the CLI author** in *agent
  logic* (same `author_with_agent`, `mode="explore_and_author"`) — but they run
  on **different drivers**. That's the inconsistency.
- The **in-RF path does NOT use agent-browser** — it uses Playwright typed
  tools, exactly as expected since the runtime supports
  agent-browser | playwright | nodriver.
- **The TS port is the cleanest design:** a single `BrowserDriver` *interface*
  with an explicit **fail-fast probe wrapper** (`BrowserDriverExplorer`), so the
  30s-hang class of bug is structurally impossible regardless of the concrete
  driver. The Python side has no such wrapper — the CLI path inherits whatever
  the agent-browser CLI does (30s), the in-RF path inherits the RF Browser
  timeout. **This is the design lesson to port back to Python.**

## The agent-browser 30s quirk — rigorously confirmed (2026-06-15)

Direct timing of the third-party `agent-browser` binary, missing selector
(`.nope-xyz`) on a loaded page:

| command | time | result |
|---|---|---|
| `get text` / `get html` / `get attr` / `get value` / `get box` | **30.0s** | fail, `os error 35` |
| `get count` | 0.0s | `count: 0` |
| `is visible` | 0.0s | `visible: false` |

Clean split: **content getters** (which resolve a Playwright auto-waiting
locator) hang the full 30s default timeout; **count/predicate getters** (which
use non-waiting queries) are instant. The CLI exposes **no timeout flag or env
var** to shorten it.

**The agent-browser skill does NOT warn about this** (`~/.claude/skills/
agent-browser/`) — it documents `get count` and `wait` but never mentions that
content getters block 30s on a miss. So a prompt/skill note is both a valid
mitigation *and* fills a real gap:

> When exploring, NEVER call `get text/html/attr/value/box` on a selector you
> have not confirmed exists — each missing-selector call blocks ~30s. Probe
> existence first with `get count` or `is visible` (instant), then read content
> only on confirmed (`count > 0`) selectors.

This is cheap and effective, but prompt-reliability-dependent (a workaround, not
a fix). The structural fix is the TS port's pattern: a fail-fast probe wrapper.

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
