# ADR-0010 — Treat solver output as hostile input

**Status:** Accepted · 2026-09-03

## Context

Parsing flow5's output looked like a chore. It is a correctness risk. Every one of
these was hit while verifying a handful of runs
([FLOW5-INTERFACE.md §5](../FLOW5-INTERFACE.md)):

| Observed | Naive result |
|---|---|
| `polar_text_output_format=csv` emits **zero commas** for plane polars | CSV reader returns one column |
| First data row is **concatenated onto the header line** | one operating point silently lost |
| Labels are variable-width with internal spaces (`α (°)`, `Short Period Damping Ratio`) | columns misaligned; CL read from the β column |
| A single-point polar has **no standalone data line** | zero rows returned |
| Cells may be `inf` / `nan` | strict numeric filter drops whole rows |
| Op-point files are **duplicated into every polar's directory** with another polar's contents | results attributed to the wrong analysis |
| `Static margin` is a **percentage**, not a fraction | stable aircraft reported as wildly unstable |
| T7 header `XNP` and `Static margin` contradict the data columns | wrong stability conclusion |
| `Made 0 valid analysis pairs (boat, polar)` appears on **every** run | every success reported as failure |

None of these raise an error. All of them produce a plausible number.

## Decision

The results layer is written as if parsing untrusted input, and it **verifies itself
against the file**:

1. **Cross-check the row count** against the header's own `Nbr. of data points`.
   A mismatch is an error, not a warning — it means points were dropped.
2. **Take the column count from a data row**, never from the label text.
3. **Split labels on runs of 2+ spaces**, never on whitespace.
4. **Accept `inf`/`nan`, then report them.** A non-finite cell is surfaced as a
   warning naming the row and column; it is never presented as a result.
5. **Never infer attribution from a path.** The polar CSV is authoritative for which
   points exist; op-point files are matched on the polar name inside the file.
6. **Normalise units at the boundary.** Static margin becomes a fraction on the way
   in, once.
7. **Scope every stdout marker match** — `(plane, polar)`, not `analysis pairs`.
8. **Prefer computed quantities over reported ones** where they disagree: derive
   static margin from the `XNP` column and the CoG actually used, and read stability
   modes from the `___Longitudinal modes___` eigenvalue block rather than the summary
   columns.

Golden-file tests pin all of it. The reference implementation from the verification
round is [`poc/lib/parse.py`](../../poc/lib/parse.py), validated against 7 files
across 5 polar types.

## Consequences

- The parser is larger and stranger than it "should" be, and every oddity carries a
  comment pointing at the evidence. Do not "simplify" it without re-reading §5.
- Some of this will be fixed upstream. The self-checks stay regardless — they are
  what turn a silent wrong answer into a loud failure.
- This is the concrete reason flow5ctl is worth more than a shell command.
