# aitester-bdd

📖 **Docs:** [kundeng.github.io/aitester-bdd](https://kundeng.github.io/aitester-bdd/) · 📦 **PyPI:** [aitester-bdd](https://pypi.org/project/aitester-bdd/)

**A general end-to-end testing framework for any web app — where you describe the test in English and an agent writes a real, runnable test file by actually using your app.**

Not bolted onto a specific product, framework, or stack. Point it at example.com, your own SaaS, an internal SPA, a customer site — same library, same workflow.

## The pitch

You built a web app. Every time you change something you click through the same flows in a browser to check it still works. You know automating this is called end-to-end testing, but every time you've looked into it you've found yourself wiring up Playwright, learning a test framework, and writing a hundred lines of code to check what your eyes could check in ten seconds.

`aitester-bdd` is the missing middle: describe what should happen in English, get back a real `.robot` test file. Run it as many times as you want for free.

```bash
pip install aitester-bdd
aitester init-browser   # one-time Playwright setup

aitester author \
  --story "Open the homepage, search for 'BDD', confirm the article heading appears and a paragraph mentions BDD." \
  --base-url https://en.wikipedia.org \
  --out wiki_test.robot

aitester run wiki_test.robot
```

About a minute later you have `wiki_test.robot` — checked-in, human-readable, runs in ~3 seconds with no LLM in the loop.

## Two kinds of test line, one file

Most lines in an authored suite are **pinned** — strict, deterministic, no LLM at runtime:

```robot
Given I am on "/"
When I fill "input[name='search']" with "BDD"
And I click "button.cdx-search-input__end-button"
Then I see "Behavior-driven development"
```

But some parts of an app are too volatile to pin (AI chat replies, dynamic dashboards, search results). For those, you drop in a **fluid** line:

```robot
When I explore "ask the chat 'what does the pro plan cost' and check the answer mentions a dollar amount"
```

At runtime that one line spins up a small LLM agent that uses the same browser (same tab, same cookies, same login session), does the semantic check, and returns pass/fail. Use it sparingly — the rest of your suite stays cheap.

You choose per line whether you want strictness or flexibility.

## Promotion path: explore now, pin later

A third keyword does both at once — runs the story as a fluid test, and if it succeeds, writes a pinned `.robot` from the experience:

```robot
When I explore and author "log in, navigate to settings, change the theme to dark, verify it stuck" output=settings.robot
```

Use it when you're not sure a flow is stable enough to commit to a pinned test yet. Prototype with `I explore`, promote to pinned when the flow settles.

## How it works

**Authoring (one-time, ~30s–2min, uses an LLM).**

A DeepAgents + LangGraph agent (Claude by default, any OpenAI-compatible model works) reads your story, opens your app in a real browser, takes structured snapshots of every interactive element on the page, picks one, acts on it, snapshots the new state, and loops. Every selector it writes is one it touched during exploration — never guessed from the story. If the app is too broken to test (login dead, page won't load), it writes a markdown bug report to `triage/` instead of inventing a fake test.

**Running (every time, ~seconds, no LLM for pinned lines).**

`aitester run` is just [Robot Framework](https://robotframework.org/) executing the suite. Run it 1,000 times in CI, costs nothing for the pinned portion. Fluid `I explore` lines pay for an LLM call at runtime — that's the explicit trade you opted into when you wrote them.

**Failures get a diagnosis.**

When a rule fails, an aspect hands the trajectory (what was clicked, page state before and after) to an LLM and asks "is this a test bug or an app bug?" You get a short natural-language explanation attached to the failure — not a raw stack trace.

## Quick speed reference

Authoring is **headless DeepAgents on Claude Opus 4.7**. Typical wall-time:

| Story | Steps | Wall time |
|---|---:|---:|
| example.com smoke (heading + link) | 9 | ~27s |
| en.wikipedia.org search + article check (5 assertions) | 27 | ~70s |
| Real SPA login + chat + multi-rule verification | 50–80 | 2–3 min |

The agent batches multiple browser ops per LLM round-trip, so most remaining wall-time is **SUT-bound** — waiting for the app's own LLM to stream a response — not authoring overhead.

## Backends

`AITESTER_BROWSER=` picks the driver at runtime:

| Backend | Default? | Setup | Best for |
|---------|----------|-------|----------|
| `playwright` | ✓ | `aitester init-browser` once | consistent engine for pinned + fluid, reliable text reads, native Playwright waits, in-process speed |
| `agent-browser` | | `npm i -g agent-browser` | zero install friction, same CLI used during authoring |
| `nodriver` | | `pip install aitester-bdd[stealth]` + Edge/Chrome | bot-detected sites (DataDome / Cloudflare BM) |

Same `.robot` runs on any of the three because everything is CSS selectors. With the default `playwright` backend, pinned and fluid lines share one in-process browser session.

## Status

**Alpha.** Verified end-to-end on public sites (example.com, en.wikipedia.org, the-internet.herokuapp.com) and on a real internal SPA (login + chat + tool-rendering verification).

## Architecture, one paragraph

The LLM is the author, not the runtime — except where you explicitly ask for it. Authoring drives the live target via Playwright, snapshots real DOM, and emits a `.robot` file. Runtime is Robot Framework executing pinned rules deterministically; fluid `I explore` rules invoke an LLM at runtime against the *same* browser session as the pinned rules. Failures fire an AOP `diagnose` aspect that produces a natural-language explanation. Backends are pluggable; the walker is engine-agnostic.

## License

MIT
