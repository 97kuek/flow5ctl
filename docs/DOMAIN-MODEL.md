# Domain model

This document fixes the vocabulary and the shape of `design.yaml`. It is the
contract between the agent, the human, and the flow5 adapter.

## Vocabulary

We use flow5/XFLR5 terms wherever they exist, and avoid inventing synonyms.

| Term | Meaning here |
|---|---|
| **Design** | The whole aircraft description — the contents of `design.yaml`. |
| **Wing** | One lifting surface: main wing, elevator, fin. flow5 models all three with the same object; so do we. |
| **Section** | A spanwise station on a wing: `y`, chord, offset, dihedral, twist, airfoil. Everything between two sections is linear. |
| **Planform (shorthand)** | A compact description — span, root chord, taper, sweep — that flow5ctl *expands* into sections. Convenience only; sections are the truth. |
| **Airfoil** | A 2D profile with a name and coordinates. Referenced by name from sections. |
| **Foil polar** | 2D lift/drag data for one airfoil over Re and α. Needed for viscous 3D analysis. |
| **Polar** | A 3D analysis result: a family of operating points for one aircraft under one set of conditions. flow5 calls the *request* a polar too; we call the request an **Analysis**. |
| **Analysis** | The request: polar type, method, viscosity, speed/mass/CG, α range. |
| **Operating point (op point)** | One converged solution: a row in the polar. |
| **Study** | A named, re-runnable question spanning several analyses — a CG sweep, a taper comparison. |
| **Derived geometry** | Everything flow5ctl computes from the design: area, span, MAC, AR, Re, CG, wing loading. Never authored by hand. |
| **Preset** | A named bundle of defaults for a class of aircraft (`hpa`, `rc-glider`, `uav`). |

Two terms we deliberately do **not** use, because flow5 users mean something else by
them: *model* (means the 3D mesh) and *project* (means a `.fl5` file).
A flow5ctl **project directory** is always written in full.

## `design.yaml`

Designed so an LLM can fill it in from a sentence, and a human can read it in a
diff. Flat where possible, no deep nesting, explicit units, no magic numbers.

```yaml
schema: flow5ctl/design/1
name: Albatross-2026
description: HPA for the 2026 Birdman Rally, distance category
preset: hpa

units:                      # optional; these are the defaults
  length: m
  mass: kg
  speed: m/s
  angle: deg

atmosphere:
  density: 1.225            # kg/m^3
  kinematic_viscosity: 1.5e-5

# ── Design intent ────────────────────────────────────────────────
# Not sent to flow5. Used by the advisor to choose analyses,
# to sanity-check results, and to tell the agent when it is done.
requirements:
  cruise_speed: 8.0
  total_mass: 95.0
  static_margin: [0.05, 0.15]     # fraction of MAC, acceptable band
  ground_effect_height: 1.5       # m above water; null to ignore
  objective: max_range            # max_range | min_sink | max_speed | custom

# ── Mass ─────────────────────────────────────────────────────────
# Give components and let CG be derived, or give `total` and `cg` directly.
mass:
  components:
    - {tag: pilot,     mass: 68.0, at: [0.35, 0.0, -0.30]}
    - {tag: structure, mass: 22.0, at: [0.45, 0.0,  0.00]}
    - {tag: drive,     mass:  5.0, at: [0.10, 0.0, -0.40]}

# ── Airfoils ─────────────────────────────────────────────────────
airfoils:
  - name: DAE-31              # the name sections refer to
    source: file:airfoils/dae31.dat
    polars:                   # 2D polar mesh for viscous 3D analysis
      reynolds: [300e3, 500e3, 700e3, 1.0e6]
      ncrit: 9
      alpha: [-4, 14, 0.5]
  - name: DAE-21
    source: naca:2412         # or  naca:2412  |  url:https://…

# ── Geometry ─────────────────────────────────────────────────────
wing:
  position: [0.0, 0.0, 0.0]
  airfoil: DAE-31             # default for all sections
  planform:                   # shorthand — expanded into sections
    span: 34.0                # full span, tip to tip
    root_chord: 1.15
    taper: 0.45               # tip chord / root chord
    sweep_le: 0.0             # deg, leading-edge
    dihedral: 2.0             # deg
    washout: -2.0             # deg of twist at the tip, linear from root
    breaks: [0.45, 0.80]      # fractions of semi-span where sections are added
  panels:
    chordwise: 13
    spanwise: 40              # distributed across the semi-span
    chord_distribution: COSINE
    span_distribution: COSINE

tail:
  type: conventional          # conventional | t-tail | v-tail | canard | none
  elevator:
    position: [7.5, 0.0, 0.3]
    airfoil: DAE-21
    planform: {span: 3.4, root_chord: 0.60, taper: 0.8, dihedral: 0.0}
    panels: {chordwise: 7, spanwise: 10}
    incidence: -1.5           # deg, applied as Ry_angle
  fin:
    position: [7.5, 0.0, 0.3]
    airfoil: DAE-21
    planform: {span: 1.2, root_chord: 0.70, taper: 0.6}
    panels: {chordwise: 7, spanwise: 8}
    count: 1                  # 2 for a twin fin; y above is then the half-spacing

extra_surfaces:               # optional; a tandem, biplane or canard-plus-tail
  - name: Second Wing         # required, and unique across every surface
    position: [4.2, 0.0, 0.4]
    airfoil: DAE-31
    planform: {span: 24.0, root_chord: 0.85, taper: 0.6}
    panels: {chordwise: 11, spanwise: 30}

fuselage:
  type: none                  # none | pod | frames   (Phase 3)
```

### Rules

- **`planform` and `sections` are mutually exclusive** per wing. A wing may declare
  either; `flow5ctl expand` rewrites `planform` into explicit `sections` in place
  when the designer wants to hand-tune. That expansion is the *only* way sections
  appear, so shorthand never silently diverges from truth.
- **`airfoil` cascades**: wing-level default, overridden per section, overridden per
  section side (`airfoil_left` / `airfoil_right`) for a transition.
- **`fin` is not mirrored.** It becomes a flow5 `FIN` wing with `Symmetric=false`.
- **`fin.count: 2` builds a twin fin**, at `+y` and `−y` from the fin's `position`.
  flow5 has no twin-fin flag — a plane is a list of `<wing>` elements with no cap, so
  two fins are two entries, each stood up by its own `Rx_angle`. Both count towards
  the vertical tail volume and the panel budget. Only a fin may be doubled, and two
  fins on the centreline are refused because they would be coincident.
  ([FLOW5-INTERFACE.md §3.0a](FLOW5-INTERFACE.md))
- **`extra_surfaces` carries any lifting surface beyond the three named ones.** A
  tandem, a biplane and a canard-plus-tail all need a fourth, and until it existed
  they could not be expressed at all. flow5 has no cap — its plane reader calls
  `addWing()` once per `<wing>` element and dispatches on nothing else
  (`xmlplanereader.cpp:127`) — so this was a schema limit, not a solver one. Each
  needs a **unique `name`**, because results are keyed by surface name and two
  unnamed surfaces would overwrite each other in the strip table with no error.
  Coefficients stay referenced to the main wing's area, span and MAC, which is
  flow5's own convention. Two consequences the tool reports rather than hides:
  **tail volume stops being the right measure** (both coefficients assume one wing
  and one tail, and every published band was fitted to that), and **the root
  bending moment loses its closed-form cross-check**, because the estimate assumes
  the wing carries all the lift and on a tandem it carries an unknown share.
- **Everything not given takes a preset default**, and every applied default is
  reported back to the agent in the `define_plane` response. Silent defaults are
  how designs go wrong.

## Derived geometry

Computed by `geometry/`, never authored, always returned to the agent:

| Quantity | Notes |
|---|---|
| Planform area, projected area | Projected accounts for dihedral. |
| Span, projected span | |
| Mean aerodynamic chord (MAC) and its `y` | Integrated over sections, not the taper formula, so breaks are handled. |
| Aspect ratio | Based on planform area. |
| Taper ratio | |
| Total mass, CG | Summed from `mass.components`. |
| Wing loading | |
| Reynolds number at MAC | At `requirements.cruise_speed`. **Drives airfoil polar range selection.** |
| Tail volume coefficients | Horizontal and vertical. A classic sanity check flow5 will not do for you. |

The first three feed flow5's `CUSTOM` reference dimensions, which is mandatory —
see [ADR-0005](adr/0005-compute-reference-dimensions-ourselves.md).

## Presets

A preset supplies defaults, sane panel counts, an analysis policy, and the
sanity thresholds the advisor uses.

| | `hpa` | `rc-glider` | `uav` |
|---|---|---|---|
| Typical span | 25–35 m | 1.5–4 m | 1–3 m |
| Typical Re at MAC | 5×10⁵ – 1×10⁶ | 5×10⁴ – 3×10⁵ | 1×10⁵ – 5×10⁵ |
| Default polar type | T1 at cruise; T2 for the speed range | T1 at several speeds | T1 |
| Viscous | required | required, `ncrit` 9 → 11 for clean air | required |
| Ground effect | **on by default** (`ground_effect_height`) | off | off |
| Default method | VLM2 | VLM2 | VLM2 |
| Static margin band | 5–15 % MAC | 5–12 % MAC | 10–20 % MAC |
| Panels (chord × semi-span) | 13 × 40 | 13 × 20 | 13 × 20 |
| Extra checks | tail volume, spanwise loading vs elliptic, structural span-mass | ballast range, flap effectiveness | — |

Presets are data (`presets/*.yaml`), not code, so the community can contribute more
without touching the solver layer.

## Studies

A study is a named question, stored so it can be re-run after a design change:

```yaml
schema: flow5ctl/study/1
name: cg-sweep
question: How does static margin trade against trimmed L/D?
vary:
  parameter: mass.cg.x
  values: [0.30, 0.32, 0.34, 0.36, 0.38]     # or {from: .., to: .., steps: ..}
analysis:
  type: T1
  speed: 8.0
  alpha: [-2, 10, 0.5]
  viscous: true
report:
  metrics: [static_margin, trimmed_alpha, L_over_D_at_trim, sink_rate]
```

Results land in `results/cg-sweep.json` and are summarised as a comparison table.
This is the unit of work most designers actually want, and the reason `sweep` is a
first-class tool rather than something the agent loops by hand.
