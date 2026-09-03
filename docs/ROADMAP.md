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

## Phase 1 — Core, and proof the numbers are right

The numerical risk that dominated this phase has been retired early: the
[verification round](log/2026-09-03-poc-verification.md) established the physics and
geometry agreement, so Phase 1 is now engineering rather than discovery. What remains
is turning the verified harness in [`poc/`](../poc) into a maintained library.

- [ ] `design.yaml` model and validation (Pydantic)
- [ ] `geometry/` — area, projected area, span, MAC, AR, CG, wing loading, Re, tail volumes
- [ ] Planform shorthand → sections expansion
- [ ] XML generation: plane, analysis, script
- [ ] Runner: subprocess, timeout, stdout state machine, failure classification
- [ ] Results: CSV → typed records; summary computation
- [ ] `probe/` — locate flow5, detect version, compatibility matrix
- [ ] Presets: `hpa`, `rc-glider`

- [ ] Two-pass runner with polar caching ([ADR-0009](adr/0009-two-pass-solver-invocation.md))
- [ ] Self-validating result parser ([ADR-0010](adr/0010-treat-solver-output-as-hostile.md)),
      promoted from [`poc/lib/parse.py`](../poc/lib/parse.py)

**Exit criteria:**

1. ✅ *(met in Phase 0)* Golden-file test from the spike reproduces to within tolerance.
2. ✅ *(met in Phase 0, indirectly)* Geometry confirmed against flow5's own strip
   table — local chord recovered from the `Re` column, span and panel distribution
   from the `y` column. **Still to do:** a direct comparison against a
   GUI-exported polar, and the same check for multi-break planforms with dihedral.
3. ✅ *(met in Phase 0)* CL_α within 10 % of `2πAR/(2+AR)` — measured **−5.2 %**
   against Helmbold, −6.7 % against the classic form.
4. ✅ *(met in Phase 0)* Viscous analysis with a computed 2D polar mesh works end to
   end, on both a single wing and a 3-surface aircraft.
5. Parser row count matches flow5's declared `Nbr. of data points` across every
   polar type in the fixture set, including single-point polars and polars
   containing `inf`.

## Phase 2 — CLI, and the first real user

- [ ] `flow5ctl` CLI covering `doctor`, `init`, `show`, `set`, `airfoil`, `analyze`, `open`
- [ ] `--json` output identical to the MCP payloads
- [ ] Automatic 2D polar computation when a viscous run needs one
- [ ] Failure messages that distinguish our bugs from design problems
- [ ] Linux verification; Windows verification if a machine is available

**Exit criterion:** design a complete RC glider and a complete HPA wing through
Claude Code, start to finish, without hand-editing XML — and have someone who did not
build the tool do it too.

## Phase 3 — MCP, and Claude Desktop

- [ ] MCP server on stdio; tools, resources, prompts per [MCP-TOOLS.md](MCP-TOOLS.md)
- [ ] Workspace management for clients with no filesystem
- [ ] `plot` returning PNG image content
- [ ] `open_in_flow5` handoff
- [ ] One-line Claude Desktop install; `uvx flow5ctl mcp` with nothing pre-installed

**Exit criterion:** a Birdman Rally team member with no terminal experience designs a
wing in Claude Desktop and opens the result in the flow5 GUI.

## Phase 4 — The questions designers actually ask

- [ ] `trim` — solve for α, CG, or elevator incidence
- [ ] `sweep` / studies with comparison tables
- [ ] T7 stability polars: parse the eigenvalue block, report longitudinal modes,
      suppress Dutch roll and short-period until flow5 reports them reliably
      ([FLOW5-INTERFACE.md §9](FLOW5-INTERFACE.md))
- [ ] Spanwise loading plots and elliptic comparison
- [ ] Ground-effect reporting in and out, for HPA
- [ ] Multi-design comparison

## Phase 5 — Community

- [ ] Fuselages (`<body>`, NURBS verified; flat-panel still to do)
- [ ] Bundled low-Re airfoil catalogue with checked provenance
- [ ] Contributed presets (F3B, F3F, F5J, DLG, HPA distance, HPA rally)
- [ ] Cross-check against AVL for validation
- [ ] Japanese documentation for the Birdman Rally community

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
| Linux/Windows behave differently | Isolated in `probe/`; explicitly unverified until tested |
| Maintainer bandwidth | Presets and airfoils are data, not code, so the community can contribute without touching the solver layer |
