---
spec_id: 03-product-consolidation
status: DRAFT
closed_as: null
since: 2026-09-27
until: null
epic: public-product-review
features: [lineage, product-boundary, backend-reduction, package-review, public-site]
supersedes: []
superseded_by: null
depends_on: []
anchors:
  - README.md
  - src/aitester_bdd/engine/README.md
  - docs/internals/architecture.md
  - docs/internals/exploration-driver-map.md
---

# aitester-bdd product consolidation

## Intent

Review `aitester-bdd` as the public testing product descended from WISE RPA BDD,
reduce overlapping execution paths, and make its already-published website and
package accurately demonstrate what is proven.

`aitester-bdd` is not superseded by `wise-rpa-bdd`. The direction is the reverse:
this repo was initialized on 2026-05-14 with WISE source as reference, then ported
the WISE walker and browser gotcha fixes while changing the domain from scraping
records to test verdicts. The earlier `TBD/bayeslearner-aitester` prototype explored
pytest fixtures, repository discovery, multi-agent execution/judgment, and direct
Playwright-test codification. Those ideas are prior art to assess, not a second
package to revive by default.

## Product boundary

The product promise remains: describe a web-app behavior in English, let an agent
ground selectors by using the live app, and receive a readable `.robot` test whose
pinned steps run deterministically. Fluid LLM-backed steps are explicit exceptions.

Unlike WISE Scraper and WISE RPA BDD, the primary output is a pass/fail regression
test with evidence, not a collected dataset. Unlike the older prototype, broad
autonomous repo discovery is not part of the promise unless a new evaluation proves
it improves authored tests.

## Current risks to review

- three runtime backends plus different standalone and in-Robot exploration paths;
- about 9,300 Python source lines across 21 files and overlapping LLM libraries;
- implemented specs still marked DRAFT, so lifecycle records do not match reality;
- website/configuration text has previously disagreed about the default backend;
- local uncommitted source changes predate this spec and must remain isolated;
- public claims about timing, provider support, and live verification can drift.

This package should remain modular. The single-file constraint applies to the WISE
skill runners, not this installable library; merging a 9,000-line package would make
its public API and tests harder to understand.

## Work plan

### P0 — Reconstruct and verify

- [ ] Snapshot the published version, current worktree, PyPI artifact, documentation
      site, and clean-install behavior without disturbing pre-existing edits.
- [ ] Trace authoring, pinned execution, fluid execution, diagnosis, and browser
      session ownership file by file.
- [ ] Reconcile specs 01–02 with landed commits and close or rewrite their statuses.
- [ ] Compare the abandoned `bayeslearner-aitester` prototype feature by feature;
      retain only ideas supported by present user value and tests.

### P1 — Simplify execution

- [ ] Measure the standalone authoring path and in-Robot fluid path on the same
      corpus.
- [ ] Select one primary browser implementation and one session model.
- [ ] Remove `agent-browser` and/or nodriver unless a named supported scenario and
      regression suite justify the maintenance cost.
- [ ] Reduce LLM/provider dependencies and make offline pinned execution genuinely
      independent of authoring extras.
- [ ] Define the ownership/porting relationship for WISE-derived fixes.

### P2 — Public package quality

- [ ] Review public types, CLI errors, configuration precedence, environment
      handling, logs, artifacts, and failure honesty.
- [ ] Add architecture contract tests around plan-then-execute, selector grounding,
      test isolation, and pinned/fluid session sharing.
- [ ] Establish supported Python, Robot Framework, browser, and provider versions.
- [ ] Audit package contents, license/provenance, security guidance, CI, PyPI release,
      and reproducible browser setup.

### P3 — Website and evidence

- [ ] Redesign the existing docs homepage around one runnable story and the
      author-once/run-many distinction.
- [ ] Show the generated `.robot`, execution report, and a real failure diagnosis.
- [ ] Publish a precise comparison with Playwright codegen, ordinary Robot Framework,
      WISE RPA BDD, and fully fluid browser agents.
- [ ] Replace stale performance claims with versioned, reproducible measurements.
- [ ] Clearly label alpha limitations, LLM costs, privacy boundaries, and which paths
      were verified live.

### P4 — Retire the prototype deliberately

- [ ] Preserve a final architecture/lessons record for `bayeslearner-aitester`.
- [ ] Decide whether any pytest fixture or deterministic Playwright writer is worth
      porting through a new spec and evaluation.
- [ ] Archive or mark the old repo superseded only after confirming no active
      consumer imports it.

## Acceptance criteria

- One documented primary browser/session path covers authoring, pinned execution,
  and fluid execution; exceptions have measured value.
- The public package installs from scratch and runs a pinned example without LLM
  credentials after authoring.
- The website's claims, defaults, commands, and supported versions match the release.
- The relationship to both WISE RPA BDD and the old pytest prototype is explicit.
- Pre-existing worktree changes are reconciled separately rather than silently
  absorbed into this sprint.

## Non-goals

- Rewriting the package into one file.
- Restoring multi-agent complexity solely because it existed in the prototype.
- Supporting every LLM provider and browser backend.
- Claiming that fluid checks are deterministic.

