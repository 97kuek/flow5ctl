# Tool surface

The same capabilities are exposed twice: as MCP tools (for Claude Desktop and other
MCP clients) and as CLI verbs (for Claude Code, Codex, humans, CI). This document
specifies them once.

## Principles

1. **Few tools, each a design action.** Not a CRUD API over XML. An agent should be
   able to hold the whole surface in mind.
2. **Every response is a summary plus a pointer.** Full data goes to a file; the
   response says where. See [ADR-0004](adr/0004-summarise-results-not-raw-data.md).
3. **Responses carry warnings.** Applied defaults, violated thresholds, and
   physically suspect results are named in the response, not buried in a log.
4. **The wrong thing is hard.** Asking for stability from a T1 polar is refused with
   the correct alternative, not silently obeyed.
5. **Prerequisites resolve themselves.** A viscous analysis with no 2D airfoil
   polars computes them and says so, rather than failing with a solver error.

## Where designs live

Claude Desktop has no filesystem access, so the server owns a workspace:

- default `~/flow5ctl/` — override with `FLOW5CTL_WORKSPACE`
- each design is a subdirectory (see [ARCHITECTURE.md](ARCHITECTURE.md))
- tools address designs by **name**, never by path
- the server refuses to read or write outside the workspace

For the CLI, the current working directory is the design if it contains
`design.yaml`; otherwise `--design <name>` resolves in the workspace.

---

## Tools

### `doctor`
Verify the environment. No arguments.

Returns: flow5 executable path, version, whether it is a **verified** version,
workspace path, writability, and the results of a 2-second self-test analysis.
Every other tool fails cheaply and clearly if `doctor` would fail.

> Agents should call this once at the start of a session. The MCP server also
> exposes the same content as the `flow5://status` resource so a client can read it
> without a tool call.

### `list_designs`
Returns each design's name, one-line description, preset, span, mass, and when it
was last analysed.

### `create_design`
`name`, `preset`, and either a `design` object or `from` (an existing design to copy).

Creates the project directory, writes `design.yaml`, computes geometry.
Returns the same payload as `get_design`.

### `get_design`
`name`. Returns the design, **all derived geometry**
([DOMAIN-MODEL.md](DOMAIN-MODEL.md#derived-geometry)), applied preset defaults, and
validation warnings.

```jsonc
{
  "name": "Albatross-2026",
  "preset": "hpa",
  "geometry": {
    "planform_area": 27.03, "projected_area": 27.01,
    "span": 34.0, "projected_span": 33.98,
    "mac": 0.826, "mac_y": 7.31, "aspect_ratio": 42.8, "taper_ratio": 0.45,
    "total_mass": 95.0, "cg": [0.351, 0.0, -0.221],
    "wing_loading": 3.51,
    "reynolds_at_mac": 4.4e5,
    "tail_volume_h": 0.52, "tail_volume_v": 0.021
  },
  "defaults_applied": [
    "wing.panels.span_distribution = COSINE (preset: hpa)",
    "atmosphere.density = 1.225 (standard sea level)"
  ],
  "warnings": [
    "Aspect ratio 42.8 is high even for an HPA; check that the structural mass budget is realistic.",
    "Vertical tail volume 0.021 is below the 0.03 typically used at this span."
  ]
}
```

### `update_design`
`name` plus a **partial** design object, deep-merged. Returns the new `get_design`
payload and a diff summary of what changed.

Partial updates matter: an agent adjusting washout should not have to restate the
whole aircraft, and a restated aircraft is a chance to lose a field.

### `add_airfoil`
`design`, `name`, `source` (`file:` / `naca:NNNN` / `url:` / inline coordinates),
optional `polars` specification.

Validates the coordinates (closed trailing edge, ordering, point count), stores the
`.dat`, and registers it. Does **not** compute polars — `analyze` does that on demand.

### `analyze`
The main tool.

```jsonc
{
  "design": "Albatross-2026",
  "type": "T1",                    // T1|T2|T3|T4|T5|T6|T7 — plain flow5 names
  "speed": 8.0,
  "alpha": [-2, 10, 0.5],
  "viscous": true,                 // default true
  "ground_effect": true,           // preset default for hpa
  "method": "VLM2",
  "cg_x": 0.351,                   // overrides the design CG for this run
  "mass": 95.0,
  "name": "cruise"                 // for later reference
}
```

Returns a summary, never the table:

```jsonc
{
  "status": "ok",
  "polar": "cruise",
  "points": 25,
  "runtime_s": 3.2,
  "summary": {
    "cl_alpha_per_deg": 0.0912,
    "alpha_zero_lift": -3.4,
    "best_LD": {"value": 38.2, "alpha": 3.5, "cl": 0.82, "cd": 0.0215},
    "min_sink": {"rate": 0.41, "alpha": 5.0, "speed": 7.4},
    "cm_alpha_per_deg": -0.0121,
    "neutral_point_x": 0.462,
    "static_margin": 0.134,
    "trim_alpha": 3.1
  },
  "warnings": [
    "Static margin 0.134 is inside the target band [0.05, 0.15].",
    "2D polars for DAE-31 were computed automatically (Re 3e5–1e6, 4 points, 11 s)."
  ],
  "data": "results/cruise.json",
  "flow5_project": "build/out/Albatross-2026.fl5"
}
```

A **T5** run returns a different summary, because α is held fixed and nothing
longitudinal means anything on a sideslip sweep:

```jsonc
{
  "summary": {
    "sideslip_sweep": true,
    "cn_beta_per_deg": 0.000991,    // > 0 is directionally stable
    "cl_beta_per_deg": -0.000788,   // < 0 is a stable dihedral effect
    "cy_beta_per_deg": -0.006333,
    "sign_convention": "textbook: Cn_beta > 0 stable, Cl_beta < 0 stable"
  }
}
```

`alpha` is the **sideslip** range on a T5 run. flow5 writes both lateral moment
coefficients with the opposite sign to the textbook convention; these are converted,
so the usual rule reads correctly. No `static_margin` or `neutral_point_x` is
returned — flow5's own header claimed 593 % for a 34 m HPA.
([FLOW5-INTERFACE.md §5.3a](FLOW5-INTERFACE.md))

Every analysis of an HPA or a glider also returns a **drag budget** — what the L/D
does *not* include, because a VLM run of a wing and a tail returns the drag of a
wing and a tail:

```jsonc
{
  "drag_budget": {
    "modelled_best_LD": 27.03,
    "missing_fraction": {"low": 0.20, "high": 0.40},
    "realistic_best_LD": {"low": 19.31, "high": 22.53},
    "items": [{"item": "rigging wires", "low": 0.10, "high": 0.30, "note": "..."}]
  },
  "structure": {
    "root_bending_moment_Nm": 2772.0,   // the aerodynamic load at this point
    "lift_at_point_N": 872.9,           // what the polar says the wing is carrying
    "load_factor": 1.0,                 // that lift over the aircraft's weight
    "elliptic_estimate_Nm": 2964.0,     // closed-form cross-check
    "estimate_from": "lift at this operating point",
    "ratio_to_estimate": 0.935
  }
}
```

`load_factor` is the check that matters before quoting the bending moment. A
fixed-speed (T1) polar holds the speed and sweeps alpha, so most of its points are
not level flight — on the shipped 3 m glider, best L/D sits at a load factor of
**4.45**, and its bending moment is the load *there*, not the load a spar is sized
from. When the factor is more than 15 % from 1 the report says so and points at
`trim` or a T2 polar. The elliptic cross-check is made against the lift at the point
rather than the weight, so it tests the strip table instead of measuring the load
factor a second time.

`compare_ground: true` runs the analysis free-air **and** in ground effect and
returns both with the change between them. For a Birdman Rally aircraft that
difference is a design driver rather than a correction — measured +9 % on best L/D
and −10 % on minimum sink at h = 2 m.

Guardrails enforced here:
- `type: "T1"` with a stability question → refused, pointing at `T7`
- a T5 polar reporting an unstable `Cn_beta` or `Cl_beta` → warned, with the fix
- `viscous: true` with no 2D polars → computes them, reports the cost
- panel count above the preset ceiling → refused with the count and a suggestion
- estimated runtime above the budget → asks for confirmation instead of hanging

### `trim`
Solve rather than sweep. `design`, plus a target:

| `target` | Solves for | Runs |
|---|---|---|
| `level` | α that holds level flight at a speed | 2 |
| `cl` | α that reaches a given CL | 2 |
| `speed` | the speed that holds level flight at a given α | 1 |
| `static_margin` | the CG x that achieves a target margin | 2 |
| `pitch` | the elevator incidence giving Cm = 0 | 3–5 |

Returns the solved quantity, the operating point at that condition, and — for the
iterative target — the history, so the convergence is inspectable rather than
asserted.

`level` and `cl` take two runs, not one: the first locates α on the sweep grid, and a
second run centred on that angle returns the drag and moment **at the condition
itself** rather than interpolated between grid points. Lift is linear enough to
interpolate; L/D is not.

`static_margin` is a closed-form solve because the neutral point does not move with
the CG — verified across three CG positions, with the static margin varying linearly
at exactly 1/MAC. The second run only confirms it, and warns if the moment slope
turned out to be non-linear enough to matter.

### `sweep`
Runs a [study](DOMAIN-MODEL.md#studies): `design`, `parameter`, `values`, `analysis`,
`metrics`. The parameter is either a dotted path into `design.yaml`
(`wing.planform.taper`) or one of the analysis overrides `cg_x`, `speed`, `mass`,
`ground_height`.

A design parameter is varied **in memory** — `design.yaml` is never written to, so an
interrupted sweep cannot leave the design in an intermediate state.

Returns a comparison table, the best row by the design's `objective`, and the path to
full results. Three things it does that a hand-rolled loop would not:

- **Names the metrics that are blind to the parameter.** Best L/D does not respond to
  CG at all; a CG study reported on it looks like it makes no difference when it makes
  a great deal. Compare on `ld_at_trim`.
- **Explains an empty cell.** A missing `trim_alpha` means the trimmed condition fell
  outside the α sweep, and it says so with the values affected.
- **Names the cost a potential-flow sweep cannot see.** A washout sweep will always
  "discover" that washout should be zero, because what washout buys — tip-stall
  margin, roll damping, an unloaded tip — is invisible to a solver with no separation
  model. The tool says so rather than letting the table speak for itself.
- **Collapses the repeats.** Every point runs a full analysis and warns about the
  same things, so a four-value sweep used to return the CG-height explanation four
  times with four different percentages. Warnings that differ only in their numbers
  are reported once, with a count.

#### `trimmed: true`

A fixed-speed sweep holds the speed and sweeps α, so at almost every point the lift
does not equal the weight and the pitching moment is not zero. Its best L/D is the
best point of a flight condition the aircraft never reaches.

With `trimmed`, each point runs as a **fixed-lift (T2) polar** — flow5 solves the
speed at every α so that lift equals weight — and the metrics are read at the α where
Cm crosses zero. That row is the aircraft actually flying: level, trimmed, at its own
weight. It overrides `type`, switches the default metrics to
`ld_at_trim, trim_alpha, cl_at_trim, min_sink, static_margin`, and needs an elevator
to trim against.

Measured on the HPA example, moving the CG aft:

| cg_x (m) | ld_at_trim | trim_alpha | static_margin |
|---|---|---|---|
| 0.360 | 41.45 | 1.77° | +16.1 % |
| 0.407 | 45.40 | 3.02° | +10.8 % |
| 0.453 | 48.81 | 4.71° | +5.5 % |
| 0.500 | 49.74 | 6.91° | +0.3 % |

That is the trade a CG study exists to show, and none of it is visible on best L/D,
which does not respond to CG at all.

### `plot`
`design`, `polar` (one or more), `kind` (`polar` | `cl_alpha` | `cm_alpha` |
`drag_breakdown` | `spanwise_lift`).

Returns a **PNG as MCP image content**. This exists for Claude Desktop, where the
user cannot open a file and where a curve communicates in one glance what twenty
numbers do not. The CLI writes the file instead.

`polar`, `cl_alpha` and `cm_alpha` take **several analyses at once** and draw them
against each other; the subtitle then shows any condition that differs as a range,
so a 12 m/s run plotted against an 8 m/s one is not captioned with one of them.
`drag_breakdown` and `spanwise_lift` take **one** and refuse more: a stack of two
aircraft's drag components cannot be read, and a spanwise chart is drawn from one
operating point's strip table against an elliptic reference computed for that
planform, so two would share neither.

### `export`
`design`, `format` (`fl5` | `stl` | `csv` | `xml`), optional `polar`.
Returns the path, and for `fl5` a reminder that `open_in_flow5` exists.

### `open_in_flow5`
Launches the flow5 GUI on the design's `.fl5` project. Available only to the CLI and
to MCP clients running on the user's own machine.

**This tool is important out of proportion to its size.** It is the handoff back to
the human — the point where a designer stops trusting the agent's summary and looks
at the aircraft with their own eyes, in the tool they already know. A design tool
that cannot be checked will not be adopted.

---

## Resources (MCP)

| URI | Content |
|---|---|
| `flow5://status` | Same as `doctor`, readable without a tool call |
| `flow5://guide/design` | [DESIGN-GUIDE.md](DESIGN-GUIDE.md) — the aerodynamic guardrails |
| `flow5://guide/design.ja` | [The same in Japanese](ja/DESIGN-GUIDE.md) |
| `flow5://schema/design` | The `design.yaml` schema, generated from the model |
| `flow5://presets/{name}` | Preset defaults and thresholds |
| `flow5://design/{name}` | The current `design.yaml` |
| `flow5://results/{design}/{polar}` | Full operating-point data |

The last three are URI templates, so they appear under `resources/templates/list`
rather than `resources/list`.

`flow5://guide/design` is deliberately a resource: a client that reads it before
designing makes far fewer physically wrong requests. **Both guides ship inside the
wheel**, because a client installed with `uvx` has no source tree and was being
served a 981-character summary of a 28,000-character document — and the Japanese
version exists precisely for readers who would not get the English one.

## Prompts (MCP)

| Prompt | Walks the user through |
|---|---|
| `new-aircraft` | Preset → requirements → first planform → first analysis |
| `improve-glide` | Diagnose the drag breakdown, propose and test changes |
| `check-stability` | T7 polar, modes, CG band, control authority |
| `compare-designs` | Two or more designs on the same metrics |

## CLI mapping

Implemented today:

```
flow5ctl doctor
flow5ctl presets
flow5ctl init <name> --file design.yaml [--preset hpa]
flow5ctl list
flow5ctl show [<name>]
flow5ctl set wing.planform.washout=-2.5 requirements.cruise_speed=11
flow5ctl expand                               # planform shorthand → explicit sections
flow5ctl airfoil add DAE-31 --file dae31.dat [--reynolds 3e5,5e5 --ncrit 11]
flow5ctl airfoil list
flow5ctl analyze --type T1 --speed 8 --alpha=-2,10,2 --name cruise
flow5ctl trim --target level|cl|speed|static-margin|pitch [--value V]
flow5ctl sweep --parameter cg_x --values 0.04:0.09:6 --metrics ld_at_trim,static_margin
flow5ctl sweep --study examples/cg-sweep.yaml
flow5ctl export --format fl5|stl|csv|xml
flow5ctl open                                 # hands the .fl5 to the flow5 GUI
```

Still to come: `plot` (Phase 4) and `flow5ctl mcp` (Phase 3).

Every command takes `--json`, before or after the verb, for machine-readable output
shaped as the MCP response will be — so an agent with a shell gets what an MCP client
will get.

An option value that starts with a minus works either way: `--alpha=-2,10,2` and
`--alpha -2,10,2` are both accepted, because an alpha sweep almost always starts
negative and argparse would otherwise read it as an option.
