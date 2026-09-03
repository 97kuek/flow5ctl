# poc/ — verification harness

Every measured claim in [`docs/`](../docs) was produced here, and can be reproduced.
This is **not** library code — it is a deliberately small, ugly harness whose only
job is to establish facts about flow5. The library will be written properly in
Phase 1; the parser here is the one part intended for promotion.

## Requirements

- flow5 installed. On macOS the harness expects
  `/Applications/flow5.app/Contents/MacOS/flow5` (edit `lib/f5.py` otherwise).
- Python 3.11+. No third-party packages.

## Verify a platform

If you are on Linux or Windows, this is the most useful thing you can run:

```bash
python3 poc/verify_platform.py
```

It checks each behaviour `docs/FLOW5-INTERFACE.md` claims — headless execution, where
the polar lands, the whitespace-not-CSV output, the row welded onto the header line,
the declared point count, and the combined-script crash — and prints a report to paste
into a [platform report](https://github.com/97kuek/flow5ctl/issues/new?template=platform_report.yml).
Standard library only, and it writes nothing outside a temporary directory.

## Run a case

```bash
cd poc
python3 case_a_geometry.py          # geometry + physics cross-check
python3 case_c_bisect.py            # reproduces the flow5 segfault
python3 case_h_hpa.py               # 34 m HPA: mesh convergence + ground effect
```

Each case writes to `work/<case>/` — gitignored, and safe to delete.

## What each case establishes

| Case | Establishes |
|---|---|
| `case_a_geometry.py` | Rectangular wing baseline; CL_α within 5.2 % of theory; strip table recovers the supplied geometry |
| `case_b_foil.py` | 2D polar generation; that `Batch_Range/Alpha` is ignored and `OpPoint_Range/Alpha` is required |
| `case_c_viscous.py` | The naive single-script approach — **crashes** |
| `case_c_bisect.py` | Isolates the crash to `foil_analysis` + `Plane_analysis` in one script, over 7 configurations |
| `case_d_twopass.py` | The two-pass workflow that replaces it |
| `case_e_polartypes.py` | On-the-fly XFoil failing on a 3-surface aircraft (expected to be abandoned, not to pass) |
| `case_f_glider2pass.py` | Five polar types on a 3 m glider in 1.3 s; op-point directory duplication |
| `case_g_wide.py` | That T2/T3/T7 need a wider 2D Re mesh, and succeed with one |
| `case_h_hpa.py` | 34 m HPA: mesh convergence, ground effect, timing |
| `case_i_inertia_body_multi.py` | `Use_plane_inertia` semantics, NURBS fuselage, multi-plane runs |
| `case_j_project.py` | `load_project_file` loads but cannot be extended |
| `verify_platform.py` | Whether all of the above still holds on *your* platform |

`case_e` is kept because the failure is the finding.

## The library

| File | Purpose |
|---|---|
| `lib/f5.py` | Run flow5, classify stdout, generate NACA coordinates |
| `lib/gen.py` | Emit `xflplane` / `xflPlanePolar` / `xflscript` XML — prototype of `xmlgen` |
| `lib/parse.py` | **Parse flow5 output safely.** Handles all seven traps in [FLOW5-INTERFACE.md §5](../docs/FLOW5-INTERFACE.md) and validates its own row count against the file's declared point count. Intended for promotion into the library — read [ADR-0010](../docs/adr/0010-treat-solver-output-as-hostile.md) before changing it. |

## Not committed

`work/` (solver output) and `ref/` (upstream flow5 source fetched for reference) are
gitignored. flow5 is GPL-3.0 and its source must never be committed here — see
[ADR-0006](../docs/adr/0006-licensing-and-the-gpl-boundary.md).
