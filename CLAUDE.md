# CLAUDE.md

Project instructions for Claude Code. The full guidance for agents working on this
repository is in **[AGENTS.md](AGENTS.md)** — read it.

This file adds only what is specific to running Claude Code here.

## Status

Design phase. No source code yet. The repository holds the design record: README,
`docs/`, and ADRs. Do not scaffold an implementation unless asked.

## The two things most likely to trip you up

**1. The exit code carries almost no information.** flow5 exits `0` whether it
succeeded, rejected the script outright, or failed every operating point. But it
exits **139 (SIGSEGV)** when it crashes — which it does reproducibly if a script
contains both a `<foil_analysis>` and a `<Plane_analysis>` section. So check *both*
stdout and the exit code; neither alone is enough.

Verified markers are listed in [docs/FLOW5-INTERFACE.md §6](docs/FLOW5-INTERFACE.md),
and the crash in [§7](docs/FLOW5-INTERFACE.md).

**2. Output that looks fine is often wrong.** A polar `.csv` contains no commas; the
first data row is welded onto the header line; `Static margin` is a percentage;
op-point files are duplicated into every polar's directory carrying another polar's
contents. See [§5](docs/FLOW5-INTERFACE.md) before writing any parsing code, and reuse
[poc/lib/parse.py](poc/lib/parse.py) rather than starting over.

## Running flow5 locally

macOS:

```bash
/Applications/flow5.app/Contents/MacOS/flow5 -p -s script.xml
```

It runs headless and exits on its own. There is no `timeout` on stock macOS — wrap
long runs yourself rather than blocking.

A working end-to-end example — foil `.dat`, plane XML, analysis XML and script — is
reproduced in [docs/log/2026-09-03-feasibility-spike.md](docs/log/2026-09-03-feasibility-spike.md).
Start from it rather than writing XML from scratch.

## Checking a fact about flow5

The source is public and is the authority:

```bash
curl -s https://api.github.com/repos/techwinder/flow5/git/trees/main?recursive=1
curl -s https://raw.githubusercontent.com/techwinder/flow5/main/<path>
```

The files that matter are listed in
[docs/log/2026-09-03-feasibility-spike.md](docs/log/2026-09-03-feasibility-spike.md).
Cite the file you read when you record a fact.

## Scratch work

Keep experimental XML, trial runs and solver output out of the repository. Use a
scratch directory. Only promote something into `tests/fixtures/` when it is a
deliberate, documented fixture.

## Before you claim something works

Run it. This project's failure mode is confident wrong numbers, and the traps in
[the spike log](docs/log/2026-09-03-feasibility-spike.md) all produced output that
looked fine. If you did not execute it, say that you did not.
