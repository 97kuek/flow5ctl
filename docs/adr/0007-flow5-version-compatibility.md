# ADR-0007 — Version detection and a compatibility matrix

**Status:** Accepted · 2026-09-03

## Context

flow5's author states that the API and script XML format are still subject to
change, with stabilisation targeted for end of 2026. Our entire interface is
undocumented-by-upstream behaviour that we verified by experiment against **7.57**.

Meanwhile users install flow5 from Homebrew and elsewhere, and it auto-updates. A
silent flow5 upgrade could change our output without changing our code.

## Decision

1. **Detect the flow5 version at startup from `flow5 --version`** — or from the
   first line of a run log (`flow5 v7.57`) — and record it in `.flow5ctl/state.json`
   alongside every result.

   **Never read it from the application bundle.** On the verification machine the
   macOS `Info.plist` reported `CFBundleShortVersionString = 7.70` while the program
   and Homebrew both reported **7.57**. The bundle metadata is wrong, and trusting it
   put the wrong version in our own first log. Note also that `--version` prints the
   application name twice (`flow5 flow5 v7.57`) — parse the `v<major>.<minor>` token.
2. **Maintain a compatibility matrix** in the repository: `verified`, `expected to
   work`, `known incompatible`.
3. On an **unverified** version: run, but attach a warning to every result naming the
   version and pointing at the matrix.
4. On a **known incompatible** version: refuse, and say what to do.
5. **Keep a golden-file test suite**: fixed designs, fixed analyses, expected
   summaries within tolerance. Run it against each new flow5 release; a failure
   updates the matrix before it reaches users.
6. **Document how to pin.** For Homebrew users, how to stop the cask auto-updating.

## Consequences

- Users never silently get wrong answers from an untested solver version.
- We take on the ongoing job of testing new flow5 releases. This is real maintenance
  cost and it is the price of depending on an unstable interface.
- Results are traceable: every stored result names the flow5 version that produced it.
- The matrix is a public artifact the community can contribute to — reports from
  Linux and Windows users are how we find out what we cannot test ourselves.
