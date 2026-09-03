# ADR-0004 — Return summaries, not raw data

**Status:** Accepted · 2026-09-03

## Context

flow5 writes a polar as a wide CSV: ~25 lines of prose header followed by a
16-column table, with Unicode column names (`α`, `β`, `φ`, `∞`, `ρ`, `m²`), plus one
CSV per operating point in a subdirectory whose filenames contain leading spaces and
degree signs.

A 25-point sweep is a few thousand tokens of numbers. A parameter study is tens of
thousands. And a designer's actual question was never "what are the 400 numbers" —
it was "is it stable", "what is the best L/D and where", "did that change help".

## Decision

Tool responses carry a **computed summary** and a **path to the full data**. They
never inline the table.

The summary is fixed and always includes, where meaningful: lift-curve slope,
zero-lift α, best L/D with the α and CL where it occurs, minimum sink, Cm_α, neutral
point, static margin, trim α — plus warnings.

Full operating-point data is normalised to JSON in `results/<polar>.json`. An agent
that genuinely needs a specific number reads that file (Claude Code) or the
`flow5://results/…` resource (MCP).

## Consequences

- Responses stay small and comparable across analyses.
- The agent reasons about aerodynamic quantities rather than re-deriving them from
  columns, so it makes fewer arithmetic mistakes.
- We must decide once, well, what belongs in the summary — and extend it when a
  question turns out to be unanswerable from it. This is a feature: it forces the
  summary to track what designers actually ask.
- Parsing must be robust to the Unicode headers and to the header block's variable
  length. Never assume the table starts on a fixed line.
- `plot` returns a PNG for the same reason: for Claude Desktop users a curve is the
  summary.
