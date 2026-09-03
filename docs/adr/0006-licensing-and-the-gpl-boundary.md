# ADR-0006 — Licensing and the GPL boundary

**Status:** Proposed · 2026-09-03

## Context

flow5 is GPL-3.0 ([techwinder/flow5](https://github.com/techwinder/flow5)). We want
flow5ctl to be adopted as widely as possible, including by people who want to embed
it in other tooling.

Two questions: what licence for flow5ctl, and does using flow5 constrain it.

## Decision

1. **flow5ctl is licensed Apache-2.0.**
2. **flow5ctl invokes the flow5 executable as a subprocess.** It does not link
   `libflow5-lib`, does not include flow5 source, and does not redistribute flow5
   binaries. Users install flow5 themselves.
3. **We read flow5's GPL source to learn its file formats, and we do not copy it.**
   Interface facts — element names, enum spellings, output markers — are recorded in
   our own words in [FLOW5-INTERFACE.md](../FLOW5-INTERFACE.md), with citations to the
   files they came from. No flow5 code is copied into this repository.
4. **Attribution is explicit.** README and docs credit flow5 and André Deperrois and
   link upstream, and state that flow5ctl is not affiliated with or endorsed by flow5.

## Rationale

Running a GPL program as a separate process, exchanging data through files and
stdout, is the arms-length relationship the GPL's own FAQ treats as separate works.
Apache-2.0 adds an explicit patent grant over MIT at no practical cost to adopters.

## Consequences

- If [ADR-0001](0001-drive-flow5-via-the-xml-script-interface.md) is ever revisited
  and we link `flow5-lib`, **this ADR must be revisited first** — linking would make
  the result a derivative work and require GPL-3.0. That is a licence change, not an
  implementation detail, and it is a real cost to weigh against the API's benefits.
- Bundled airfoil coordinates must have their own provenance and licensing checked
  before inclusion; several public airfoil databases have restrictive terms.
- Contributors must not paste flow5 source into this repository. Stated in
  [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Open

- Confirm the choice with a reading of the flow5 licence text as shipped, and
  consider notifying upstream as a courtesy before the first public release.
