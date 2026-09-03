# ADR-0009 — Two-pass solver invocation

**Status:** Accepted · 2026-09-03 · forced by a flow5 crash

## Context

The natural design is one flow5 invocation per analysis request: emit a script that
computes the 2D airfoil polars it needs and then runs the 3D analysis.

**That crashes.** A script containing both a `<foil_analysis>` and a
`<Plane_analysis>` section segfaults flow5 7.57 (exit 139, no stdout at all).
Bisected across seven configurations; either section alone is fine, both together
always crash, regardless of viscosity settings.
See [FLOW5-INTERFACE.md §7](../FLOW5-INTERFACE.md) and
[the verification log](../log/2026-09-03-poc-verification.md).

## Decision

**Always invoke flow5 twice, with disjoint script sections.**

1. **Pass 1 — 2D.** `<foil_analysis>` only, default (non-`csv`) text output. Produces
   genuine XFoil-format polars.
2. **Stage.** Copy those `.txt` files into the pass-2 `xfoil_polars_dir`.
3. **Pass 2 — 3D.** `<Plane_analysis>` only. flow5 reports
   `added the XFoil polar: <foil> / T1_Re…` per file.

A script generator must never emit both sections. Enforce it in the generator, not
by convention.

Corollaries:

- **2D polar meshes are cached** in the project's `airfoils/` and reused across
  analyses. Pass 1 costs ~15 s; pass 2 costs under 2 s
  ([FLOW5-INTERFACE.md §10](../FLOW5-INTERFACE.md)). Recompute only when the airfoil
  or the required Re range changes.
- **The mesh must bracket the whole flight envelope**, not just cruise. A mesh
  covering Re 50 k–250 k yielded 1 of 6 T2 points and 0 T7 points; 20 k–400 k gave
  5 of 5 and a working T7. Derive the range from the minimum flight speed and the
  tip chord, then widen it.
- **Prefer interpolation over on-the-fly XFoil** for anything with a tail.
  On-the-fly needs no pass 1 and is fine on a single wing, but on a 3-surface glider
  it failed to converge on the elevator and discarded every operating point.

## Consequences

- Every analysis is two processes plus a file copy. At these runtimes, irrelevant.
- The runner must check the **exit code** for a crash as well as parsing stdout,
  because a segfault produces no output to parse.
- If upstream fixes the crash, the two-pass structure still works and stays — it is
  also what makes polar caching natural.
- Worth reporting upstream; it is a genuine flow5 bug, not a usage error.
