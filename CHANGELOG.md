# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning will follow [Semantic Versioning](https://semver.org/) from 0.1.0 onward.

## [Unreleased]

The core library and CLI work. The MCP server is not built yet — see
[docs/ROADMAP.md](docs/ROADMAP.md).

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
- 131 tests, 8 of which run against a real flow5.

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
