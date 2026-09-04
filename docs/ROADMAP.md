# Roadmap

Phases are ordered so that the riskiest assumptions are tested earliest and so that
something usable exists before anything ambitious is attempted.

The governing question at each gate is: **would a flow5 user who is not us get value
from this today?**

---

## Phase 0 — Design record and PoC verification ✅ done 2026-09-03

Establish that this is possible and write down what was learned.

- [x] Verify headless batch execution against flow5 7.70
- [x] Recover the script, plane and analysis XML schemas from source
- [x] Run a plane analysis end to end and check the physics
- [x] Record the traps ([log](log/2026-09-03-feasibility-spike.md))
- [x] Architecture, domain model, tool surface, ADRs
- [x] Verify every gap the spike left: 2D polar generation, viscous end to end,
      T2/T3/T5/T7, ground effect, fuselages, multi-plane runs, STL and Cp export,
      `load_project_file`, HPA-scale meshes, mesh convergence
      ([verification log](log/2026-09-03-poc-verification.md))
- [x] Meet the Phase 1 numerical exit criteria ahead of implementation:
      CL_α within **5.2 %** of theory, geometry confirmed via the strip table
- [x] Amend the design with what was found — [ADR-0009](adr/0009-two-pass-solver-invocation.md),
      [ADR-0010](adr/0010-treat-solver-output-as-hostile.md), [ADR-0007](adr/0007-flow5-version-compatibility.md)

---

## Phase 1 — Core, and proof the numbers are right ✅ done 2026-09-03

- [x] `design.yaml` model and validation (Pydantic) — [`model/design.py`](../src/flow5ctl/model/design.py)
- [x] `geometry/` — area, projected area, span, MAC, AR, CG, inertia, wing loading, Re, tail volumes
- [x] Planform shorthand → sections expansion, with proportional panel allocation
- [x] XML generation: plane, analysis, script — structurally unable to emit both script sections
- [x] Runner: subprocess, timeout, stdout state machine, crash detection, failure classification
- [x] Results: output → typed records; summary computation; stability modes from the eigenvalue block
- [x] `probe` — locate flow5, read the version from the program, compatibility matrix
- [x] Presets as data: `hpa`, `rc-glider`, `uav`, `custom`
- [x] Two-pass runner with 2D polar caching ([ADR-0009](adr/0009-two-pass-solver-invocation.md))
- [x] Self-validating result parser ([ADR-0010](adr/0010-treat-solver-output-as-hostile.md))
- [x] Guardrails that refuse rather than warn: stability from a non-T7 polar, T6 control
      polars, panel-count ceilings, fixed-lift sweeps through zero lift
- [x] A test suite that grew to 276 tests, 19 of which run a real flow5

**Exit criteria — all met:**

1. ✅ The spike reproduces through the library: `flow5ctl analyze` on the rectangular
   wing gives CL_α 0.08525 /deg, static margin −0.59 % MAC and 520 panels, matching
   the PoC exactly. Pinned in [`tests/test_end_to_end.py`](../tests/test_end_to_end.py).
2. ✅ Geometry confirmed against flow5's own output three ways: `panel_count` matches
   flow5's `Counted 520 elements`, `reynolds_at_mac` matches every strip's `Re`
   column, and the strip `y` column matches the panel distribution.
   **Still to do:** a direct comparison against a GUI-exported polar.
3. ✅ CL_α within 10 % of theory — measured **−5.2 %** against Helmbold.
4. ✅ Viscous analysis with a computed 2D polar mesh works end to end, on a single
   wing and a 3-surface aircraft, with the mesh cached between runs.
5. ✅ Parser row count matches flow5's declared `Nbr. of data points` for every
   fixture, including single-point polars and polars containing `inf`.

Beyond the criteria, the derived Reynolds envelope turned the PoC's worst failure —
a T2 polar returning 1 of 6 points — into 4 of 4 without the user specifying anything.

## Phase 2 — CLI, and the first real user ✅ done 2026-09-03 (macOS)

- [x] `doctor`, `init`, `list`, `show`, `presets`, `analyze`
- [x] `set` (field-level edit, refusing to create fields), `airfoil add`/`list`,
      `expand`, `export` (fl5/stl/csv/xml), `open` (hands the `.fl5` to the GUI)
- [x] `trim` — solves for α at a CL or for level flight, for the speed at an α, for
      the **CG that achieves a target static margin**, and for the elevator incidence
      that gives Cm = 0
- [x] `sweep` — varies one design or analysis parameter and returns a comparison table,
      with study files so a question is re-runnable after a design change
- [x] `--json` on every command, accepted before or after the verb
- [x] Automatic 2D polar computation when a viscous run needs one, with caching
- [x] Failure messages that distinguish our bugs from design problems
- [x] Worked examples in [`examples/`](../examples) for an RC glider, an HPA, and a study
- [x] `poc/verify_platform.py` — one command that checks every documented flow5
      behaviour and prints a pasteable report, so verifying a platform costs a
      contributor a minute rather than an afternoon
- [ ] **Linux verification; Windows verification** — *decided 2026-09-04: not a
      release blocker. flow5ctl is offered for macOS only until someone runs the
      script below on another platform.* Still the largest single unknown, and
      the largest remaining risk in the project. We do not own those machines; the
      script above and the platform-report template are how it gets closed.

Two things came out of building `trim` and `sweep` that changed the design:

- The neutral point does not move with the CG. Verified across three CG positions:
  X_np came out at 0.0941 m every time, with the static margin varying linearly at
  exactly 1/MAC. So a target static margin is a **closed-form solve** — two solver
  runs, one to measure and one to confirm — not a bisection.
- Best L/D does not respond to CG at all; only the trim point moves. A CG study
  reported on best L/D looks like it makes no difference when it makes a great deal,
  so `ld_at_trim` was added and `sweep` now warns when a requested metric is blind to
  the parameter being varied.

**Exit criterion:** design a complete RC glider and a complete HPA wing through
Claude Code, start to finish, without hand-editing XML — and have someone who did not
build the tool do it too.

## Phase 3 — MCP, and Claude Desktop ✅ done 2026-09-03

- [x] MCP server on stdio — 13 tools, 6 resources, 4 prompts
- [x] Workspace management for clients with no filesystem: designs are addressed by
      name, and a name containing a separator or a traversal is rejected rather than
      resolved
- [x] `plot` returning PNG image content — drag polar, lift curve, pitching moment
      with the trim point, drag breakdown, spanwise lift against elliptic; light and
      dark themes separately chosen, palette validated for colour-vision deficiency
- [x] `open_in_flow5` handoff
- [x] One-line Claude Desktop install with `uvx --from "flow5ctl[plot]" flow5ctl mcp`
      — see [MCP.md](MCP.md)
- [x] Blocking solver work runs off the event loop, so the server stays responsive
      through a twelve-second first analysis or a multi-minute sweep
- [x] `flow5://schema/design` generated from the model, so the advertised fields and
      the accepted fields cannot drift
- [x] Verified over real stdio, not just in process: handshake, tool calls, a PNG
      surviving base64 transport, and a rejected request coming back as an error
      result with the server still alive

**Exit criterion — not yet met:** a Birdman Rally team member with no terminal
experience designs a wing in Claude Desktop and opens the result in the flow5 GUI.
Everything needed for it is built and tested; what remains is putting it in front of
someone who did not build it.

Two things stood between the built software and that test, and both are now done:

- **A way to install it that does not require `git clone`.** Publishing is set up
  and documented ([RELEASING.md](RELEASING.md)); the tag is the owner's to push once
  the PyPI trusted publisher is registered.
- **A Japanese guide written for that reader.**
  [ja/QUICKSTART.md](ja/QUICKSTART.md) — preparation, the first analysis, what each
  number means, and what each warning is telling you to do. The English docs assume
  the reader already knows what a static margin is and reads English; the exit
  criterion's reader is neither.

## Phase 4 — The rest of the design questions

`trim`, `sweep`, T7 mode reporting, spanwise loading plots and multi-design comparison
were all pulled forward into Phases 1-3. What is left:

- [x] Ground-effect reporting in and out of ground effect in one call, for HPA —
      `analyze --compare-ground`. Running it by hand twice and changing one flag is
      easy to get silently wrong: two runs at the same height report no difference,
      which reads like "ground effect does not matter here"
- [x] A drag-budget view that names what is missing from the model — interference,
      surface finish, rigging, the pilot's body — rather than leaving the reader to
      remember that the total is optimistic. Every analysis of an HPA or a glider
      now says what its L/D excludes and what a realistic figure would be
- [ ] A `trim`-aware sweep: solve the trim at each point rather than reporting the
      untrimmed polar
- [x] Structural sanity from the strip table's bending-moment column — the wing
      root bending moment is reported with a closed-form cross-check beside it
      (elliptic loading puts the load centroid at 4s/3π). Measured on a 32 m
      aircraft: 2,772 N·m against an estimate of 2,964, which is the right side of
      elliptic for a constant-chord inner panel with washout
- [ ] **More than three lifting surfaces.** The schema is fixed at wing, elevator
      and fin. A real user's flow5 project kept as a reference (`26-el3.xfl`) has a
      `Second Wing` as well, so a tandem or biplane layout cannot be expressed today.
      flow5 itself has no cap — `xmlplanereader.cpp` calls `addWing()` once per
      `<wing>` element — and the twin-fin work already proved extra surfaces solve
      correctly, so this is a schema change rather than an adapter one

## Phase 5 — Community

- [ ] Fuselages (`<body>`, NURBS verified; flat-panel still to do)
- [ ] Bundled low-Re airfoil catalogue with checked provenance
- [ ] Contributed presets (F3B, F3F, F5J, DLG, HPA distance, HPA rally)
- [ ] Cross-check against AVL for validation
- [x] Japanese documentation for the Birdman Rally community — [ja/QUICKSTART.md](ja/QUICKSTART.md) and [ARCHITECTURE-ja.md](ARCHITECTURE-ja.md). Still to translate: the design guide, which is where the aerodynamic judgement lives

## Out of scope because flow5 cannot do it through this interface

- **Flaps and control surfaces; T6 control polars.** There are no flap or hinge
  elements anywhere in flow5's wing/plane XML — a flap is a property of flow5's Foil
  object, which a `.dat` file cannot carry. The only workaround would be a
  GUI-prepared `.fl5`, and planes loaded from a project file cannot be paired with new
  analyses. Verified twice; see findings 9 and 10 of the
  [verification log](log/2026-09-03-poc-verification.md). This is a real limitation
  for camber-changing RC gliders and must be stated up front rather than discovered.

## Deliberately out of scope for now

- **Structural analysis.** Aeroelasticity and spar sizing matter enormously for an
  HPA, and flow5 does not do them. We will not pretend otherwise; see
  [DESIGN-GUIDE.md §1](DESIGN-GUIDE.md).
- **Automatic optimisation.** Tempting, and premature. Get trustworthy single
  evaluations and honest comparisons first. An optimiser built on an unvalidated
  evaluation function optimises the error.
- **Sails / boats.** flow5 supports them; we do not, yet.
- **Replacing the flow5 GUI.** The handoff to the GUI is a feature.

## Known risks

| Risk | Mitigation |
|---|---|
| flow5 changes its XML format | Version detection, compatibility matrix, golden tests ([ADR-0007](adr/0007-flow5-version-compatibility.md)) |
| Our geometry disagrees with flow5's | Retired in Phase 0 via the strip-table cross-check; a direct GUI comparison remains |
| flow5 crashes on a script we generate | Known case fixed by [ADR-0009](adr/0009-two-pass-solver-invocation.md); the runner treats a non-zero exit as a crash and reports it as our bug |
| A parser change silently drops operating points | Row count is validated against flow5's own declared count ([ADR-0010](adr/0010-treat-solver-output-as-hostile.md)) |
| Agents report unstable/stalled results as valid | Guardrails in the tool plus [DESIGN-GUIDE.md](DESIGN-GUIDE.md); refuse the bad combinations outright |
| Someone builds a piloted aircraft on an unvalidated result | Stated limits in every report; cross-check guidance; the tool says so |
| Linux/Windows behave differently | Isolated in `probe/`; **decided 2026-09-04 to offer macOS only** rather than claim a platform nobody has run. `poc/verify_platform.py` closes it in one command when someone does |
| Induced drag is a few percent uncertain | **Bounded and partly closed.** The impossible span efficiency above 1 was a spanwise mesh artefact; the defaults were raised and the residual quantified ([log](log/2026-09-04-induced-drag-and-the-mesh.md)). What remains is a real disagreement with classical lifting line at the tip, which an independent third method would settle |
| Absolute drag disagrees with published aircraft | **Largely explained.** Two of the three reconstructions substitute the unmodified DAE sections because the teams' own modifications are not published, and they come out far too pessimistic. The one aircraft whose airfoil modification *is* published — FX76MP149, stated as a blend of FX76MP160 and FX76MP120 to 14.9 % thickness — reproduces exactly, and once the drag budget is applied its published figure lands inside the band. So the drag machinery is not systematically wrong; the airfoil work is worth about 40 % on L/D and cannot be guessed. n = 1 for the clean case, and it stays a risk until another team publishes theirs |
| Maintainer bandwidth | Presets and airfoils are data, not code, so the community can contribute without touching the solver layer |
