# Keyword Library Reference

Complete reference for all Robot Framework keywords provided by `aitester_bdd.AITester`.

## Lifecycle

| Keyword | Purpose |
|---------|---------|
| `Given I start verification "${name}"` | Initialize a named verification (Suite Setup) |
| `Given I start scenario "${name}" at "${url}"` | Begin scenario with entry URL |
| `Given I start scenario "${name}"` | Begin scenario without entry URL |
| `Then I finalize verification` | Walk the rule DAG (Suite Teardown) |

## Rule definition

| Keyword | Purpose |
|---------|---------|
| `I define rule "${name}"` | Open a named rule block |
| `And I declare parents "${names}"` | Declare parent rules (comma-separated) |
| `And I set retry ${max} delay ${ms}` | Guard retry-redo configuration |
| `And set rule timeout ${ms}` | Per-rule deadline (ms) |
| `And set child scope "${css}"` | CSS prefix for child rules |
| `And I set guard policy "${policy}"` | `abort` or default (skip) |
| `And I pause interrupts` | Suppress interrupt dismissal |
| `And I scope interrupts "${selectors}"` | Override dismiss list |
| `And screenshot on enter` | Capture on rule start |
| `And screenshot on fail` | Capture on rule failure |

## State checks

All state check keywords work as **Given** (guard), **And** (continuation), or **Then** (observation).

### URL

| Keyword | Checks |
|---------|--------|
| `url contains "${pattern}"` | URL includes substring |
| `url matches "${regex}"` | URL matches regex |
| `url does not contain "${pattern}"` | URL excludes substring |

### Element existence

| Keyword | Checks |
|---------|--------|
| `selector exists "${css}"` | Element attached to DOM |
| `selector does not exist "${css}"` | Element absent |

### Count

| Keyword | Checks |
|---------|--------|
| `count eq "${css}" "${n}"` | Exactly N elements |
| `count at least "${css}" "${n}"` | At least N elements |
| `count at most "${css}" "${n}"` | At most N elements |

### Text

| Keyword | Checks |
|---------|--------|
| `has text "${css}" "${text}"` | Exact text (trimmed) |
| `contains "${css}" "${substring}"` | Text includes substring |
| `matches "${css}" "${regex}"` | Text matches regex |
| `not contains "${css}" "${text}"` | Text excludes substring |

### Table

| Keyword | Checks |
|---------|--------|
| `table headers "${css}" "${h1\|h2\|h3}"` | Pipe-delimited header match |

### Element state

| Keyword | Checks |
|---------|--------|
| `visible "${css}"` | Element is visible |
| `hidden "${css}"` | Element is hidden |
| `enabled "${css}"` | Form element enabled |
| `disabled "${css}"` | Form element disabled |
| `checked "${css}"` | Checkbox/radio checked |

### CSS class / Attribute

| Keyword | Checks |
|---------|--------|
| `has class "${css}" "${class}"` | Class present |
| `not class "${css}" "${class}"` | Class absent |
| `attr eq "${css}" "${expected}" attr=${name}` | Attribute equals |
| `attr contains "${css}" "${substring}" attr=${name}` | Attribute includes |

### Form

| Keyword | Checks |
|---------|--------|
| `input value "${css}" "${value}"` | Input field value |
| `select selected "${css}" "${value}"` | Selected option |

### Network

| Keyword | Checks |
|---------|--------|
| `last status "${code}"` | HTTP status code |
| `last body contains "${text}"` | Response body substring |

### Shell

| Keyword | Checks |
|---------|--------|
| `last shell exit "${code}"` | Exit code of last shell command |
| `last shell stdout contains "${text}"` | Stdout substring |
| `last shell stdout matches "${regex}"` | Stdout regex |
| `last shell stderr contains "${text}"` | Stderr substring |

### Semantic (LLM)

| Keyword | Checks |
|---------|--------|
| `semantic "${criterion}"` | AI judges page text against criterion |
| `visual semantic "${criterion}"` | AI judges screenshot against criterion |

### LLM response

| Keyword | Checks |
|---------|--------|
| `llm response contains "${text}"` | Last LLM response includes text |
| `llm response semantic "${criterion}"` | AI judges LLM response |

## Actions

| Keyword | Does |
|---------|------|
| `When I open "${url}"` | Navigate |
| `When I reload` | Reload page |
| `When I go back` | Browser back |
| `When I add url params "${params}"` | Append query params |
| `When I click locator "${css}"` | Click element |
| `When I click text "${text}"` | Click by visible text |
| `When I double click locator "${css}"` | Double-click |
| `When I type "${value}" into "${css}"` | Type text |
| `When I type "${value}" into "${css}" secret` | Type (masked in logs) |
| `When I fill locator "${css}" "${value}"` | Fill (alias for type) |
| `When I select "${value}" from "${css}"` | Select dropdown |
| `When I check "${css}"` | Check checkbox |
| `When I uncheck "${css}"` | Uncheck checkbox |
| `When I hover "${css}"` | Mouse hover |
| `When I focus "${css}"` | Focus element |
| `When I press keys "${css}" ${keys}` | Keyboard |
| `When I upload file "${path}" into "${css}"` | File upload |
| `When I scroll down` | Scroll page |
| `When I wait for idle` | Wait for network idle |
| `When I take screenshot` | Capture screenshot |
| `When I set stepper "${css}" "${n}"` | Click increment N times |
| `When I select date "${iso}"` | Date picker navigation |
| `When I evaluate js "${script}"` | Execute JavaScript |
| `When I run shell "${cmd}"` | Execute shell command |
| `When I ask LLM "${prompt}"` | Query LLM with page context |

## Explore

| Keyword | Does |
|---------|------|
| `When I explore "${story}"` | LLM-driven exploration rule |
| `When I explore and author "${story}" output=${path}` | Explore + write suite |

## Configuration

| Keyword | Does |
|---------|------|
| `And I configure interrupts dismiss=${css}` | Add dismiss selector |
| `And I configure state setup action=${type} ...` | Suite-level setup action |
| `And I register hook "${name}" at "${point}" ...` | Post-extract transform |

## Artifacts (capture pipeline)

| Keyword | Does |
|---------|------|
| `And I register artifact "${name}" ...` | Declare a capture artifact |
| `And I set artifact options "${name}" ...` | Configure artifact (dedupe, output) |
| `Then I extract fields ...` | Capture fields from current page |
| `Then I extract table ...` | Capture table rows |
| `Then I emit to artifact "${name}"` | Push record to artifact |
| `And I set quality gate for "${name}" ...` | Set min_records/filled_pct assertions |
