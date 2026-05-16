# CLI Reference

The `aitester` command is the primary interface for authoring and running suites.

## `aitester author`

Author a `.robot` suite from a story and a live target.

```bash
aitester author --story "..." --base-url URL --out FILE [OPTIONS]
```

### Required arguments

| Argument | Description |
|----------|-------------|
| `--story TEXT` | Plain-English intention to verify |
| `--base-url URL` | Target application URL |
| `--out FILE` | Output `.robot` file path |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--debug` | off | Stream agent steps to stderr |
| `--max-attempts N` | 2 | Retry authoring on crash/recursion-limit |
| `--mode MODE` | `author` | `author` or `explore_and_author` |
| `--pinning LEVEL` | `auto` | Selector pinning: `auto`, `aggressive`, `conservative`, `none` |

### Example

```bash
aitester author \
  --story "Login with admin/admin, verify the dashboard shows at least 3 widgets" \
  --base-url http://localhost:5173 \
  --out login_dashboard.robot \
  --debug
```

## `aitester run`

Run an authored `.robot` suite via Robot Framework.

```bash
aitester run SUITE [OPTIONS]
```

### Required arguments

| Argument | Description |
|----------|-------------|
| `SUITE` | Path to the `.robot` file |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--headed` | off | Visible browser window |
| `--step-delay N` | 0 | Pause N ms after each action |
| `--base-url URL` | (from suite) | Override `${BASE_URL}` variable |
| `--output-dir DIR` | current dir | Where RF writes output files |
| `--engine ENGINE` | (from suite) | Override `${ENGINE}` variable |

### Example

```bash
# Standard run
aitester run login_dashboard.robot

# Watch it run slowly
aitester run login_dashboard.robot --headed --step-delay 500

# Override base URL for staging
aitester run login_dashboard.robot --base-url https://staging.example.com
```

## `aitester init-browser`

Initialize the Playwright browser binaries (only needed for the `playwright` backend).

```bash
aitester init-browser
```

Equivalent to `rfbrowser init`. Downloads ~300MB of Chromium/Firefox/WebKit binaries.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed |
| 2 | CLI argument error |
| 3 | Environment error (missing dependency, unreachable LLM) |
