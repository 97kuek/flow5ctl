# 2026-09-03 — PoC verification round

**Question:** are the gaps left by the [feasibility spike](2026-09-03-feasibility-spike.md)
real blockers, and does the design in `docs/` survive contact with the solver?

**Answer:** the design survives, with four amendments. Eleven verification cases were
run; every case is reproducible from [`poc/`](../../poc).

Environment: macOS 15 (Darwin 25.5), **flow5 7.57** — note the earlier spike log
recorded 7.70, which was wrong; see finding 1.

| Case | What it checked | Result |
|---|---|---|
| A | Rectangular wing; geometry and physics cross-check | ✅ CL_α within 5.2 % of theory |
| B | 2D polar generation via `foil_analysis` | ✅ after finding 3 |
| C | Viscous 3D, three ways | ⚠ crash found (finding 4) |
| C-bisect | Isolating the crash across 7 configurations | ✅ cause identified |
| D | Two-pass 2D → 3D workflow | ✅ works |
| E | 5 polar types with on-the-fly XFoil | ❌ abandoned (finding 6) |
| F | Same, with interpolation | ✅ 5 analyses in 1.3 s |
| G | Wide 2D Re mesh; T2 / T3 / T7 | ✅ all three succeed |
| H | 34 m HPA: mesh convergence, ground effect, timing | ✅ converged, +18 % L/D IGE |
| I | Inertia semantics, fuselage, multi-plane | ✅ all three, with finding 8 |
| J | `load_project_file` round-trip | ⚠ limited (finding 9) |
| K | `export_oppoint_Cp`, STL export | ✅ both work |

---

## Phase 1 exit criteria

| Criterion | Status |
|---|---|
| 1. Spike reproduces | ✅ Case A reproduces the baseline |
| 2. Geometry matches flow5's | ✅ by an indirect route — see below |
| 3. CL_α within 10 % of `2πAR/(2+AR)` | ✅ **−5.2 %** vs Helmbold, −6.7 % vs classic |
| 4. Viscous end to end | ✅ Cases D, F, G, H |

On criterion 2: the polar header's `Area`/`Span`/`Chord` merely **echo back the
values we supplied**, so they are not an independent check. Two routes that do work
were found and used instead — the strip table's `Re` column recovers flow5's local
chord (`Re = c·V/ν`) and its `y` column recovers the span and panel distribution.
**[run]** For the 2.0 m × 0.2 m test wing, strips appeared at ±0.975, ±0.925 …
0.05 m apart, and every strip reported `Re = 200000` = 0.2 × 15 / 1.5e-5. Exactly the
supplied geometry.

A direct comparison against a GUI-exported polar is still worth doing before v1.

---

## Findings

### 1. The installed flow5 is 7.57, not 7.70

The macOS bundle's `Info.plist` says `7.70`; `flow5 --version` and Homebrew both say
**7.57**. The spike log's "7.70" was taken from the plist and was wrong.
[ADR-0007](../adr/0007-flow5-version-compatibility.md) now specifies detection from
`flow5 --version` or the log's first line. Every document has been corrected.

### 2. flow5 *can* exit non-zero

The spike concluded "always exits 0". Wrong: a **SIGSEGV gives exit 139**. The rule
is that `0` carries no information and non-zero means a crash — so the runner must
check both the exit code and stdout. Neither alone is sufficient.

### 3. `Batch_Range/Alpha` is parsed and then ignored

The α sweep for a 2D polar must go in `OpPoint_Range/Alpha`. Put it in `Batch_Range`
and the run reports success in 0.4 s having written **empty 267-byte polars**.
A silent no-op — the worst possible failure mode, and one an agent would not notice.

### 4. `foil_analysis` + `Plane_analysis` in one script segfaults

Reproducible, bisected over seven configurations, and independent of viscosity
settings. No stdout is produced at all. This forced
[ADR-0009](../adr/0009-two-pass-solver-invocation.md): flow5ctl always runs flow5
twice. Worth reporting upstream.

### 5. The 2D polar mesh must cover the whole envelope, not cruise

A mesh covering Re 50 k–250 k gave a T2 polar with **1 of 6** points and a T7 polar
with **0**. Widening to 20 k–400 k gave **5 of 5** and a working T7. Cause: at
α = 8° the T2 speed solves to 4.69 m/s, putting the tip at Re ≈ 40 k, below the mesh.
The Re range must be derived from the *minimum* flight speed and the *tip* chord.

### 6. On-the-fly XFoil is unusable on multi-surface aircraft

On a single wing it works well and needs no 2D polars. On a 3-surface glider it
reported strip values like `Cl = 3.23, Re = 97143` on the elevator, failed to
converge, discarded **every** operating point, and had not finished after 2 minutes
of 200 % CPU. Interpolation ran the same aircraft — five polar types — in **1.3 s**.

The two methods also **disagree by 10–25 %** on viscous drag, so they must never be
mixed within a comparison.

### 7. Output parsing is a correctness risk, not a chore

Seven distinct traps, each producing a plausible wrong number rather than an error:
the `.csv` extension with zero commas; the first data row welded onto the header
line; variable-width labels with internal spaces; single-point polars with no data
line; `inf` cells silently dropping rows; op-point files duplicated into every
polar's directory carrying **another polar's** contents; and `Static margin` being a
**percentage** while looking like a fraction.

Also: `Made 0 valid analysis pairs (boat, polar) to run` is printed on **every** run,
so an unscoped marker match reports failure on every success. This one bit during the
verification itself.

This produced [ADR-0010](../adr/0010-treat-solver-output-as-hostile.md) and a parser
that validates its own row count against flow5's declared point count — now green
across 7 files and 5 polar types.

### 8. `Use_plane_inertia=true` silently discards your inertia and CoG

| Setting | Ixx used | Roll damping | Spiral damping |
|---|---|---|---|
| `true`, centreline masses | **0** | 1.02e-23 | **inf** |
| `true`, spanwise masses | 0.1126 | 0.00386 | 9.08 |
| `false`, explicit Ixx = 0.28 | 0.28 ✅ | 0.0123 | 8.99 |

A run requesting CoG x = 0.075 reported `CoG = (0.051, 0, 0)`. Lateral-directional
results are garbage unless inertia is either given explicitly with
`Use_plane_inertia=false` or made real by distributing mass spanwise.

### 9. `load_project_file` loads but cannot be extended

The project loads and its existing polars are re-exported, the new analysis is
registered against the correct plane name — and then
`Made 0 valid analysis pairs (plane, polar) to run`. Planes from a project file are
not offered to the pairing step; only planes from `plane_definition_xml_dir` are.

Useful for re-exporting, not for adding analyses.

### 10. Flaps and control surfaces are out of reach

There are no flap or hinge elements anywhere in the wing/plane XML — flaps are a
property of flow5's **Foil** object, which a `.dat` file cannot carry. Combined with
finding 9, which closes the GUI-project workaround, **T6 control polars are not
achievable through the script interface.** Removed from the v1 scope.

### 11. T7 gives valid eigenvalues; T1 does not — confirmed

- **T1**: lateral eigenvalues of `5.995e+51`, all derivative columns zero. Meaningless.
- **T7**: longitudinal eigenvalues `-100.7`, `-25.78`, `-0.04435 ± 0.4199i`. The
  complex pair is the phugoid — 0.4199 rad/s = 0.0668 Hz, matching the reported
  0.067084 Hz.

The [design guide](../DESIGN-GUIDE.md)'s refusal to take stability from T1 is now
empirically justified. But T7 has its own defects: `Short Period Freq.` reported as
0.0 where two real roots were found, `Dutch Roll Freq.` returning 56 Hz once and 0.0
three times, `Roll Damping` = `inf` whenever Ixx = 0, and the header static margin
contradicting the columns. **Parse the eigenvalue block, not the summary columns, and
do not report Dutch roll at all.**

### 12. Performance is a non-problem; XFoil is the only cost

| Case | Panels | Wall clock |
|---|---|---|
| 34 m HPA, T1 viscous ×2, 4 α | 1204 | **0.5 s** |
| Same, refined | 3172 | 1.5 s |
| 3 m glider, 5 polar types | 754 | 1.3 s |
| 2D mesh, 2 foils × 9 Re × 61 α | — | 15.4 s |

Mesh convergence on the HPA from 544 → 3172 panels: L/D at α=6° moved 45.6 → 45.4
(0.4 %), static margin 5.091 → 5.073. **Converged at the coarsest mesh** — the
preset default is already enough. The low-CL end is more sensitive (L/D at α=0°
moved 6 %).

### 13. Ground effect is large and behaves correctly

3 m glider at h = 0.30 m: CL +8 %, CD −9.6 %, L/D 24.4 → 29.2 (+20 %).
34 m HPA at h = 2.0 m: L/D 45.5 → 53.8 (+18 %).

Both match the magnitude the design guide claims. For a Birdman Rally aircraft this
is not a correction, it is a design driver.

### 14. Fuselages work

A NURBS pod on the 3 m glider: CL at α=6° 0.7229 → 0.6071, L/D 24.50 → 22.65.
Frames define the y ≥ 0 half section, top to bottom, and are mirrored.
Multi-plane runs (3 planes, 5 analyses) work in one script, as do
`export_oppoint_Cp` and `export_stl_mesh`.

---

## Amendments to the design

1. **[ADR-0009](../adr/0009-two-pass-solver-invocation.md)** — two-pass invocation is
   mandatory, not an optimisation.
2. **[ADR-0010](../adr/0010-treat-solver-output-as-hostile.md)** — the results layer
   validates itself against the file.
3. **[ADR-0007](../adr/0007-flow5-version-compatibility.md)** — version detection
   from `--version`, never the app bundle.
4. **Scope reduction** — T6 control polars and flap deflections are out for v1
   (findings 9, 10). This should be stated in the README rather than discovered by a
   user with flaps.

## Still not verified

- **Linux and Windows** — no machine available. The largest remaining gap.
- T4 and T8 polar types; `FLATPANELS` bodies; STL/STEP fuselage import;
  `Viscous_Loop`; `.plr` binary polars.
- A direct geometry comparison against a GUI-exported polar.
