# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning will follow [Semantic Versioning](https://semver.org/) from 0.1.0 onward.

## [Unreleased]

The core library and CLI work. The MCP server is not built yet — see
[docs/ROADMAP.md](docs/ROADMAP.md).

### Added — CLI (Phase 2)

- `trim`: solves for the angle of attack at a target CL or for level flight, the speed
  at a given angle, the **CG that achieves a target static margin**, and the elevator
  incidence that gives Cm = 0. The static-margin solve is closed-form in two runs
  because the neutral point does not move with the CG — verified across three CG
  positions, with the margin varying linearly at exactly 1/MAC.
- `sweep`: varies one design or analysis parameter and returns a comparison table,
  with study files so a question is re-runnable after a design change. Design
  parameters are varied in memory, so `design.yaml` is never left half-edited.
- `ld_at_trim` and `cl_at_trim` metrics, plus warnings when a requested metric is
  blind to the parameter being varied (best L/D does not respond to CG) and when a
  sweep's apparent optimum ignores a cost a potential-flow solver cannot see (a
  washout sweep will always favour zero washout).
- `set`, `expand`, `airfoil add`/`list`, `export` (fl5/stl/csv/xml) and `open`, which
  hands the `.fl5` to the flow5 GUI so a human can check the aircraft themselves.
- Worked examples in `examples/` for an RC glider, an HPA and a study.

### Fixed

- Coincident surfaces — a fin root sitting on the elevator — are caught before the
  solver runs. flow5 answers that configuration with an effective angle of attack of
  −104° and a failed run, under the same heading it uses for an unrelated cause.
- A static margin that disagrees in sign between flow5's neutral point and its own
  moment slope is reported as ambiguous rather than resolved in favour of one.
- The `hpa` preset's vertical tail volume band was wrong: with a 34 m span in the
  denominator the coefficient is an order of magnitude below a conventional
  aircraft's, so the general-aviation band flagged every correctly sized HPA fin.

### Added — core (Phase 1)

- `design.yaml` schema and validation; presets shipped as data (`hpa`, `rc-glider`,
  `uav`, `custom`) so new aircraft classes need no code.
- Geometry: planform shorthand expansion, exact area/span/MAC integrals for wings with
  breaks, mass properties including inertia, Reynolds envelope over the flight range,
  and tail volume coefficients.
- Two-pass solver invocation with 2D airfoil polar caching — flow5 segfaults if one
  script asks for both 2D and 3D work.
- A self-validating output parser that checks its row count against flow5's own
  declared point count and refuses to report a partial polar.
- Guardrails that refuse rather than warn: stability from a non-T7 polar, T6 control
  polars, panel-count ceilings, and fixed-lift sweeps through zero lift.
- CLI: `doctor`, `init`, `list`, `show`, `presets`, `analyze`, all with `--json`.
- 210 tests, 17 of which run against a real flow5.

### Verified numerically

- The PoC reproduces through the library: CL_α 0.08525 /deg, static margin
  −0.59 % MAC, 520 panels — matching flow5's own element count.
- CL_α within 5.2 % of lifting-line theory for an AR 10 wing.
- The derived Reynolds envelope turns a fixed-lift polar that returned 1 of 6 points
  into 4 of 4, with no user input.

### Added — design record (Phase 0)

- Design record: architecture, domain model, tool surface, aerodynamic design guide.
- Ten architecture decision records covering the solver interface, the two front-ends,
  file-based state, result summarisation, reference dimensions, licensing, version
  compatibility, implementation language, two-pass invocation, and output parsing.
- `docs/FLOW5-INTERFACE.md`: a verified reference for flow5's undocumented batch and
  XML interface, every claim marked as executed or read-from-source.
- `poc/`: reproducible verification harness — eleven cases against flow5 7.57.
- Open-source scaffolding: Apache-2.0 licence, code of conduct, security policy,
  contribution guide, issue and PR templates, CI.

### Verified

- Headless batch analysis end to end, including viscous 2D → 3D, five polar types,
  ground effect, NURBS fuselages, multi-plane runs, STL and Cp export.
- Physics: CL_α within 5.2 % of lifting-line theory; ground effect +18 % L/D on a
  34 m span aircraft at 2 m height; mesh converged at 544 panels for a high-AR planform.
- A reproducible flow5 segfault when one script requests both 2D and 3D work.
- Seven ways flow5's output misleads a naive parser, each now handled.

### Known limitations

- Flaps and T6 control polars are unreachable through flow5's XML interface.
- Verified on macOS only; Linux and Windows untested.
- Dutch-roll and short-period outputs are unreliable in flow5 7.57 and are not reported.
