# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning will follow [Semantic Versioning](https://semver.org/) from 0.1.0 onward.

## [Unreleased]

The core library, the CLI and the MCP server all work — see
[docs/ROADMAP.md](docs/ROADMAP.md).

### Added — Phase 4

- **A drag budget on every analysis.** A VLM run of a wing and a tail returns the
  drag of a wing and a tail; the rigging, the fairing and the pilot are a fifth to
  two fifths of an HPA again and flow5 cannot model them here. Each report now names
  what its L/D excludes and gives a realistic band, so the modelled figure is not
  quoted as the aircraft's.
- **Ground effect in and out from one call** — `analyze --compare-ground`, and
  `compare_ground` over MCP. Doing it by hand means running twice and changing
  exactly one flag; two runs at the same height report no difference, which reads
  like "ground effect does not matter here" rather than like a mistake. Measured on
  a 32 m aircraft at 2 m: +9 % best L/D, −10 % minimum sink.
- **Wing root bending moment**, with a closed-form cross-check beside it. The strip
  table already carried the number a spar is sized from and it was being discarded.

- **More than three lifting surfaces** — `extra_surfaces` in `design.yaml`. A
  tandem, a biplane and a canard-plus-tail could not be expressed at all; the schema
  was fixed at wing, elevator and fin while flow5 itself has no cap. Verified end to
  end on a tandem. Tail volume and the bending moment's closed-form cross-check both
  stop applying on such a layout, and the report says so instead of quoting them.
- **`sweep --trimmed`** — solve the flight condition at every point instead of
  reporting a polar. A fixed-speed sweep holds the speed and sweeps alpha, so at
  almost every point the lift does not equal the weight and the moment is not zero;
  its best L/D belongs to a condition the aircraft never flies. Each point now runs
  as a fixed-lift polar and the metrics are read where Cm crosses zero. On the HPA
  example, moving the CG from 0.36 m to 0.50 m takes trimmed L/D from 41.4 to 49.7
  while the static margin falls from +16.1 % to +0.3 %.
- **A Japanese getting-started guide** — `docs/ja/QUICKSTART.md`. Written for the
  reader Phase 3's exit criterion names: a Birdman Rally team member who knows
  aerodynamics, has never used a terminal, and does not read English documentation.
  It covers preparation, the first analysis, what every reported number means, and
  what each warning is telling them to do about it.
- **Tag-triggered publishing to PyPI** through trusted publishing, with the release
  procedure in `docs/RELEASING.md`.

### Changed

- **The 2D polar Reynolds ladder is eight rungs per decade, not three.** Viscous
  drag is interpolated across it and at low Reynolds the section drag moves fast.
  Measured on a reconstructed aircraft, best L/D against rung count: 5 rungs 28.10,
  8 rungs 26.86, 12 rungs 27.05, 16 rungs 27.07, 24 rungs 27.03. It settles near
  27.0 and the old five-rung default was the outlier, 4 % optimistic.
- **macOS only.** Linux and Windows are unverified and no longer implied to work.
  Nothing in the package is platform-specific, but every measured claim about flow5
  was made on macOS, and claiming an untested platform is exactly this project's
  failure mode. `poc/verify_platform.py` closes it in one command.

### Fixed

- **Span efficiency above 1 was the mesh, not the physics.** A rectangular wing came
  back at 1.008–1.012, impossible for a planar wing, and the design guide carried
  that as evidence that induced drag was only good to ±5 %. Refining the spanwise
  panels makes it fall monotonically below 1 — measured at AR 10 and again at AR 40,
  extrapolating to 0.984 and 0.975 — while chordwise panels make no difference at
  all, agreeing to four decimal places across 7, 13 and 21. The default spanwise
  count is now **40 rather than 20**, where induced drag was about 3 % optimistic,
  and an analysis says so if a design goes below 25.
- **A negative static margin was reported in silence.** `requirements.static_margin`
  and the preset bands both existed and neither was ever compared against a result.
  The shipped HPA example analysed at **−10.1 % MAC** against its own declared
  requirement of 5–15 % — the CG behind the neutral point, so the aircraft diverges
  in pitch — printed beside a lift-to-drag figure of 50.6 that reads like success.
  Both examples were also corrected: the HPA's pilot sits far enough forward to give
  +8.7 %, and the glider's nose ballast is halved, from 21 % to +9.8 %.
- **The root bending moment was checked against the weight, not against the lift at
  the operating point.** A fixed-speed polar does not fly the aeroplane — it holds
  the speed and sweeps alpha — so most of its points are out of balance. On the 3 m
  glider example the check reported the strip table as 4.3x the estimate, which
  reads like a broken parser; against the lift the polar itself reports at that
  point it is 3 %. Nothing was wrong with the strips. The load factor is now
  reported on its own, and a point more than 15 % from level flight says that the
  bending moment there is not the load a spar is sized from.
- **`export` defaulted to one of our own by-products.** The reference-height pass
  (`__zref`, which holds the CG at wing height so the CG-height term can be
  separated) and a ground comparison's free-air copy (`__free`) both land in
  `build/out` and are usually the most recent thing there, so `export` handed back a
  different aircraft than the one asked about, under a name close enough to be
  missed. They are skipped by default, still usable by name, and labelled when used.
- **`set` now takes the design name positionally**, like every other verb. It did
  not, so `flow5ctl set Glider wing.planform.taper=0.6` read as three assignments
  and failed with "no design.yaml in the current directory" — an error about the
  wrong thing. An assignment without an `=` now says so.
- **The total mass carried binary noise.** 0.40 + 0.10 + 0.10 + 0.10 came back as
  0.7000000000000001 kg and `trim` printed it that way. A number that looks broken
  makes a careful reader doubt every other number beside it.
- A sweep repeated every per-point warning once per point. A four-value CG sweep
  returned the CG-height explanation four times with four different percentages, and
  exact-match de-duplication could not tell they were one finding. Warnings that
  differ only in their numbers are now collapsed, with a count.
- Twin fins (`tail.fin.count: 2`). flow5 has no twin-fin flag — a plane is a list of
  `<wing>` elements with no cap — so two fins are two entries at ±y.
- Airfoil files in Lednicer format, which is how the UIUC database serves every
  section. They could not be read at all.
- Sideslip (T5) polars reported longitudinal numbers, including a 593 % static
  margin, and none of the lateral derivatives the polar exists to measure. flow5
  signs both lateral moment coefficients opposite the textbook; they are converted.
- The spanwise strips were read at whichever operating-point file sorted to the
  middle of the directory — six degrees from the operating point on a real run.
- Rejected edits and invalid design files surfaced Pydantic tracebacks.
- The interpolation-failure message named the Reynolds range as the cause when it
  cannot know which axis failed.

### Added — MCP server (Phase 3)

- An MCP server on stdio (`flow5ctl mcp`), so Claude Desktop and any other MCP client
  can design an aircraft. 13 tools, 6 resources, 4 prompts. One-line install with
  `uvx --from "flow5ctl[plot]" flow5ctl mcp` — see `docs/MCP.md`.
- Charts as PNG image content: the drag polar with best L/D marked, the lift curve,
  the pitching moment with its trim point, the drag breakdown, and the spanwise lift
  distribution against elliptic. Light and dark themes are separately chosen rather
  than one inverted, and the palette is validated for colour-vision deficiency in
  both. `flow5ctl plot` writes the same images from the CLI.
- The spanwise strip table is now stored with each result, so a chart no longer
  depends on `build/` surviving the next analysis.
- Workspace isolation: designs are addressed by name, and a name containing a path
  separator, a traversal or a null byte is rejected rather than resolved. The server
  never reads or writes outside its workspace.
- `flow5://schema/design`, generated from the model, so the fields the server
  advertises and the fields it accepts cannot drift apart.
- Blocking solver work runs off the event loop, so the server stays responsive
  through a twelve-second first analysis or a multi-minute sweep.

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

- **Fins were built horizontally.** `Type=FIN` does not orient anything — flow5 lays a
  fin's sections along y like any other wing, and it becomes vertical only when rolled
  (`Rx_angle = -90`, as the upstream API example does explicitly). Every fin flow5ctl
  had generated was therefore a second horizontal tail: on a reconstructed 30 m
  aircraft the phantom surface moved the neutral point 35 % MAC aft, and every
  sideslip result was meaningless because flow5 never saw a vertical surface.
  `Closed_Inner_Side` is now set for a fin with no fuselage, as the same example
  requires. Found by checking against a real aircraft's published data; no synthetic
  test could catch it, because a horizontal "fin" is still symmetric in sideslip and
  a T5 polar looked perfectly reasonable.
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
- 276 tests, 19 of which run against a real flow5.

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
