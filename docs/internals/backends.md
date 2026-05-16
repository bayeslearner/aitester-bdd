# Browser Backends

The walker drives the browser through a `BrowserAdapter` — a common surface that all three backends implement. The walker is backend-agnostic; the same `.robot` suite runs on any backend.

## Backend selection

```python
def BrowserAdapter():
    choice = os.environ.get("AITESTER_BROWSER", "agent-browser")
    if choice == "nodriver":
        return NodriverBackend()
    if choice == "playwright":
        return _PlaywrightBackend()
    return AgentBrowserBackend()  # default
```

Set via environment variable or declared in the suite:

```robot
*** Variables ***
${ENGINE}    agent-browser
```

The `aitester run` CLI reads `${ENGINE}` from the suite and sets `AITESTER_BROWSER` accordingly.

## Common surface

All backends expose these methods (the walker calls only these):

| Category | Methods |
|----------|---------|
| Lifecycle | `new_session(headless=True)`, `close()`, `clear_state()` |
| Navigation | `open(url)`, `reload()`, `go_back()`, `url()` |
| Wait | `wait_for_load_state(state, timeout)`, `wait_for_elements_state(css, state, timeout_ms)`, `wait_for_idle()` |
| Query | `get_count(css)`, `get_text(css)`, `get_attribute(css, attr)`, `get_value(css)`, `get_class(css)`, `is_visible(css)`, `is_enabled(css)`, `is_checked(css)` |
| Action | `click(css)`, `click_text(text)`, `double_click(css)`, `type(css, value)`, `select(css, value)`, `check(css)`, `uncheck(css)`, `hover(css)`, `focus(css)`, `press(css, keys)`, `upload(css, path)`, `scroll()` |
| Special | `screenshot(path)`, `evaluate_js(script)`, `resolve_fallback_selector(css, scope)` |

## agent-browser (default)

Every method is a subprocess call to the `agent-browser` CLI:

```python
def click(self, css):
    self._run("click", css)

def _run(self, *args):
    cmd = ["agent-browser", "--session", self._session]
    if self._headed:
        cmd.append("--headed")
    cmd.extend(args)
    subprocess.run(cmd, ...)
```

**Advantages:**

- Zero install friction (CLI ships its own browser)
- Same driver for authoring and running — selector contracts identical
- Easy to debug (copy/paste the subprocess command)
- Session isolation via UUID

**Trade-offs:**

- Subprocess latency per action (~50-200ms overhead)
- State queries via JS eval (no first-class element-state API)

## Playwright (_PlaywrightBackend)

Wraps `robotframework-browser` (Playwright via Robot Framework):

```python
def click(self, css):
    self._rf_browser().click(css)
```

**Advantages:**

- In-process speed (no subprocess per action)
- Rich element-state API (Playwright's native waiters)
- Mature ecosystem (extensions, tracing, HAR recording)

**Trade-offs:**

- Requires `rfbrowser init` (~300MB browser download)
- Playwright fingerprint detectable by bot-detection services

## Nodriver (NodriverBackend)

Raw Chrome DevTools Protocol via `nodriver`:

```python
async def _click(self, css):
    el = await self._page.find(css)
    await el.click()
```

**Advantages:**

- No Playwright fingerprint — evades DataDome, Cloudflare BM, etc.
- No `rfbrowser init` — uses system Chrome/Edge
- Async CDP gives fine-grained control

**Trade-offs:**

- Requires Chrome or Edge installed on the system
- Less mature selector resolution than Playwright
- Async internals (wrapped in sync for the walker surface)

## Gotcha-fixes (ported from WISE)

All backends share battle-tested fixes for real-site quirks:

| Fix | What it handles |
|-----|----------------|
| `click_text` fallback | Playwright `text="X"` → substring → JS MouseEvent |
| `evaluate_js` navigation detection | JS that triggers navigation destroys context — caught and classified |
| `set_stepper` JS-click | Re-rendering elements trigger "element unstable" — use JS click |
| `resolve_fallback_selector` | `"a \| b \| c"` pipe syntax — pick first that resolves |

These fixes exist because production web apps have behaviors that break naive Playwright calls. The WISE engine discovered them across hundreds of real sites; aitester-bdd inherits them.

## Headed mode

All backends support headful execution for visual observation:

```bash
AITESTER_HEADED=1 aitester run suite.robot
# or
aitester run suite.robot --headed
```

The `WalkContext.headed` flag flows to `browser.new_session(headless=not ctx.headed)`. The agent-browser backend additionally passes `--headed` to every subprocess call.
