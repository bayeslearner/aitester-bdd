# aitester-bdd

**A general end-to-end testing framework for any web app — where you describe the test in English and an agent writes a real, runnable test file by actually using your app.**

Not bolted onto a specific product, framework, or stack. Point it at example.com, your own SaaS, an internal SPA, a customer site — same library, same workflow.

## The pitch

You built a web app. Every time you change something you click through the same flows in a browser to check it still works. You know automating this is called end-to-end testing, but every time you've looked into it you've found yourself wiring up Playwright, learning a test framework, and writing a hundred lines of code to check what your eyes could check in ten seconds.

`aitester-bdd` is the missing middle: describe what should happen in English, get back a real `.robot` test file. Run it as many times as you want for free.

```bash
pip install aitester-bdd
aitester init-browser

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

But some parts of an app are too volatile to pin (AI chat replies, dynamic dashboards, search results). For those, drop in a **fluid** line:

```robot
When I explore "ask the chat 'what does the pro plan cost' and check the answer mentions a dollar amount"
```

At runtime, that one line spins up a small LLM agent that uses the same browser — same tab, same cookies, same login session — does the semantic check, and returns pass/fail. The rest of your suite stays cheap. You choose per line whether you want strictness or flexibility.

## Promotion path

A third keyword does both at once — runs the story as a fluid test, and if it succeeds, writes a pinned `.robot` from the experience:

```robot
When I explore and author "log in, navigate to settings, change the theme to dark, verify it stuck" output=settings.robot
```

Prototype with `I explore`, promote to pinned when the flow settles.

## How it works (high level)

- **Authoring** (one-time, ~30s–2min): an agent (DeepAgents + LangGraph + Claude, by default) opens your app in a real browser, snapshots structured DOM, picks elements, acts on them, snapshots again, loops. Every selector in the output `.robot` is grounded in something the agent actually touched — never guessed from the story.
- **Running** (every time, ~seconds): plain Robot Framework executing the suite. Run it 1,000 times in CI; only fluid `I explore` lines pay for LLM calls.
- **Failures get diagnosed**: each failure ships with an LLM-written natural-language explanation classifying *test bug vs app bug*.

For the deeper picture, see [Architecture Overview](internals/architecture.md) and [How It Works → Authoring Agent](internals/authoring.md).

## Next steps

- [Quick Start](getting-started/quickstart.md) — install and run your first test in 5 minutes
- [Writing Suites](guide/writing-suites.md) — keyword vocabulary and rule composition
- [Running Tests](guide/running-tests.md) — backends, CI, environment
- [How It Works](internals/architecture.md) — implementation details
