# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning will follow [Semantic Versioning](https://semver.org/) from 0.1.0 onward.

## [Unreleased]

Design phase — no library code yet. See [docs/ROADMAP.md](docs/ROADMAP.md).

### Added

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
