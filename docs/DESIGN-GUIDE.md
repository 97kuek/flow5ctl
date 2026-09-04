# Design guide — aerodynamic guardrails for agents

Read this before designing an aircraft with flow5ctl. It is exposed to MCP clients
as `flow5://guide/design`.

flow5 is a **potential-flow** solver with 2D viscous data layered on top. It is fast
and, inside its domain, accurate. Outside that domain it does not warn you — it
returns confident numbers that are wrong. Most of this document is about the edge.

## 1. What the solver can and cannot tell you

**Trustworthy:**

- Lift-curve slope, spanwise lift distribution, induced drag — these are what
  potential flow is *for*, and at these aspect ratios they are good.
- Pitching moment, neutral point, static margin.
- Relative comparisons: design A versus design B under identical settings. This is
  the single most reliable use of the tool.
- Viscous drag, *interpolated from real 2D airfoil data*, in attached flow.
- Bending moment per strip, which is directly useful for spar sizing.

**Not trustworthy:**

- **Anything at or past stall.** There is no separation model. CL keeps rising
  linearly past the real CL_max. If your α sweep goes to 15°, the top of it is fiction.
  Keep sweeps inside roughly ±10° and check the 2D polar for where the airfoil
  actually stalls.
- **Post-stall, spin, deep sideslip.**
- **Thick or bluff bodies.** Fuselage pressure drag is not modelled; only friction
  drag, and only if you enable it.
- **Absolute drag counts.** Not because they are optimistic — because they are
  uncertain by tens of percent, **in either direction**, and which direction depends
  on the aircraft.

  Two effects pull opposite ways. The model omits real drag: interference, surface
  finish, rigging wires, control gaps, and the pilot's body on an HPA. But the profile
  drag it does compute rests on XFoil's transition prediction and on airfoil
  coordinates that may not be the ones actually built.

  Measured on two reconstructed human-powered aircraft, against each team's own
  published design thrust: on one, absolute L/D came out **0.6 % high**; on the other,
  **17 % low**, even though the model included less drag than the real aircraft had.
  In the second case profile drag was 75 % of the computed total, and closing the gap
  would need the mean section drag to be 29 % lower.

  So: **do not quote an absolute L/D as a prediction.** Quote it as one number from
  one model, say what is missing from the model, and put a comparison beside it. A
  comparison between two designs run identically — same airfoil, same ncrit, same
  method — cancels most of this and is what the tool is actually good at.
- **Induced drag to better than a few percent** — and **not at all on a coarse
  span**. A rectangular wing came back with a span efficiency of 1.008–1.012, which
  is impossible for a planar wing. That turned out to be the mesh, not the physics:
  refine the spanwise panels and it falls monotonically below 1. Measured at AR 10
  and again at AR 40, varying only the panel count
  ([log](log/2026-09-04-induced-drag-and-the-mesh.md)):

  | spanwise panels per semi-span | span efficiency, AR 10 | how optimistic |
  |---|---|---|
  | 10 | 1.035 | ~5 % |
  | 20 | 1.009 | ~3 % |
  | 40 | 0.999 | ~1.5 % |
  | 80 | 0.991 | ~0.7 % |
  | ∞ (extrapolated) | 0.984 | — |

  **Chordwise panels do not affect this at all** — 7, 13 and 21 chordwise agree to
  four decimal places — so always spend the panels on the span. The defaults are now
  40 spanwise, and an analysis says so if a design goes below 25.

- **Induced drag at high aspect ratio — the largest known error in this tool.**
  Refining the mesh is necessary but not sufficient. Checked against AVL 3.40 and
  against the one case with an exact answer — an elliptic planar wing has a span
  efficiency of **1.0 and cannot exceed it** — flow5 comes back *above* the limit,
  by more and more as the span grows
  ([log](log/2026-09-04-induced-drag-against-avl.md)):

  | AR | flow5 e (exact answer: 1.000) | **induced drag is** |
  |---|---|---|
  | 6 | 1.009 | 0.9 % low |
  | 10 | 1.024 | 2.4 % low |
  | 15 | 1.049 | 4.6 % low |
  | 20 | 1.077 | 7.2 % low |
  | 25 | 1.109 | 9.8 % low |
  | 30 | 1.142 | **12.4 % low** |
  | 40 | 1.211 | **17.4 % low** |
  | 50 | 1.280 | **21.9 % low** |

  AVL returns 0.997 at AR 10 and 0.996 at AR 40 on the same planforms, and is
  mesh-independent from 10 panels. Varying flow5's mesh, spanwise distribution,
  chordwise count and VLM1-against-VLM2 moves its figure by 0.4 %, so it is none of
  those. **Lift is unaffected** — the two solvers agree within 0.6 % on CL at both
  aspect ratios — so this is specific to the induced drag.

  **Changing method is not a workaround.** On the same AR 40 wing, flow5's panel
  methods land 21 % on the *other* side of the limit — QUADS 0.783, TRIUNIFORM
  0.793, TRILINEAR 0.787, all mesh-converged, against the vortex lattice's 1.211.
  At AR 10 the panel method is at least admissible (QUADS 0.980, below the limit)
  where the VLM is not (1.023). A large gap between a VLM run and a QUADS run is a
  useful smell test; averaging them is not a method.

  **Human-powered aircraft fly at AR 30–45, where induced drag is most of the drag
  budget.** That is the worst place for this error to be, and it is optimistic: the
  aircraft has more drag than the model says, on top of everything §1a lists as
  missing. flow5ctl warns above AR 15 with the figure for your own aspect ratio. It
  does **not** correct the number — a fudge factor applied to a solver would hide
  the problem and would be wrong for any case not measured — so treat a high-AR L/D
  as an upper bound and cross-check against AVL (§9) before committing.
- **Structural deflection.** A 34 m HPA wing bends several percent of span in flight.
  flow5 analyses the rigid shape you gave it.

State these limits when reporting results. An agent that says "L/D is 38" without
saying "rigid, no interference drag, attached flow only" is misleading its user.

## 1a. What the L/D does not include

A VLM run of a wing and a tail returns the drag of a wing and a tail. On a
human-powered aircraft that is most of the lift and a good deal less than all of
the drag: the rigging wires, the fairing, the pilot's body, the wheel and every
joint are not in the model, and flow5 cannot put them there through this interface.

| Missing from the model | Share of the modelled drag | What moves it |
|---|---|---|
| rigging wires | 10–30 % | bare wire runs near Cd 1.0; fairing halves it |
| pilot and fairing | 8–20 % | a bad fairing separates and is worse than none |
| interference at joints | 3–8 % | wing root, tail boom, every strut end |
| surface finish, rib stitching | 2–6 % | film over ribs is not the 2D aerofoil |
| undercarriage | 1–4 % | small if dropped, not small if left hanging |

**The total is not the sum of those highs** — no aircraft is at every worst case at
once. Published whole-aircraft budgets put everything outside the lifting surfaces
at **20–40 %** of the modelled drag for an HPA, and 8–20 % for an RC glider or UAV,
where there is no rigging and the fuselage dominates.

flow5ctl reports this on every analysis, so a modelled L/D of 27 is shown alongside
a realistic 19–23. **Compare a published aircraft's figure against that band**, not
against the modelled number.

> **Use this band, not the raw number, when comparing against a published aircraft.**
> Three reconstructions make the point. Two of them substitute the unmodified DAE
> sections, because the teams' own modifications to them are not published, and both
> come out far below what their published thrust implies. The third uses FX76MP149,
> which its team *did* publish as a blend of FX76MP160 and FX76MP120 to 14.9 %
> thickness — reproducible exactly — and its published figure of 31.9 falls inside
> the band this gives (27.7–32.4) from a modelled 38.8.
>
> Two things follow. The modelled drag is not systematically wrong. And a team's own
> airfoil work is worth roughly 40 % on lift-to-drag, so **substituting the parent
> section for a modified one is not a small approximation** — say so when you do it.

## 2. Choosing the analysis type

| The question | Polar type | Notes |
|---|---|---|
| How does it perform at cruise speed? | **T1** fixed speed | The default. |
| What is the speed range / glide polar? | **T2** fixed lift | Speed solves per α at fixed weight. Right for gliders. |
| Best glide angle and speed? | **T3** glide polar | |
| How does drag vary with speed at fixed attitude? | **T4** fixed α | |
| Sideslip / fin sizing | **T5** beta | Sweeps β through the `--alpha` range. Reports `Cn_beta`, `Cl_beta`, `CY_beta` and nothing longitudinal. |
| Flap or control-surface effectiveness | **T6** control | Needs control definitions. |
| **Is it stable? What are the modes?** | **T7** stability | The *only* correct source of eigenvalues and dynamic modes. |

> **A T5 polar answers only lateral questions, and flow5's signs are inverted.**
> flow5 7.57 writes `Cn` and `Cl` with the opposite sign to the textbook convention.
> flow5ctl converts them, so the usual rule reads correctly: **`Cn_beta > 0` is
> directionally stable, `Cl_beta < 0` is a stable dihedral effect.** If you read the
> flow5 CSV yourself, the signs are the other way round.
>
> Nothing longitudinal is reported from a T5 run, because nothing longitudinal means
> anything on it: α is held fixed, so flow5's own header claimed a **593 %** static
> margin for a 34 m HPA. Use T1/T2/T7 for pitch.
> ([FLOW5-INTERFACE.md §5.3a](FLOW5-INTERFACE.md))

> **Never take stability results from a T1 polar.** Measured on the same aircraft:
> a T1 run with `Compute_derivatives` returned lateral eigenvalues of `5.995e+51`
> with every derivative column zero, while the T7 run returned
> `-0.04435 ± 0.4199i` — a phugoid at 0.0668 Hz, matching its own reported value.
> flow5ctl refuses the combination; do not work around it.
> ([FLOW5-INTERFACE.md §9](FLOW5-INTERFACE.md))

> **And do not report Dutch roll at all.** In flow5 7.57 the `Dutch Roll Freq.`
> column came back as 56 Hz in one case and 0.0 in three others — never plausible for
> a 3 m glider. `Short Period Freq.` reads 0.0 whenever the mode is overdamped, and
> `Roll Damping` is `inf` whenever Ixx is zero. Read the `___Longitudinal modes___`
> eigenvalue block from the log instead of the summary columns.

> **A CG below the wing inflates pitch stiffness, and it is not static margin.**
> As α rises the force vector tilts, and about a CG hung below the wing its line of
> action moves — adding a term to −dCm/dCL that the classical static margin does not
> contain. On a human-powered aircraft, where the pilot sits half a metre under a wing
> whose dihedral lifts its mean height further, the offset reaches most of a MAC and
> the term is worth tens of percent.
>
> Measured on [`examples/hpa.yaml`](../examples/hpa.yaml), which anyone can re-run:
> the CG sits **0.74 MAC** below the wing's mean height, the classical static margin
> is **+8.7 %** and the pitch stiffness **+22.2 %** — the CG-height term is
> **+13.5 percentage points**, more than the margin itself. On a reconstructed 34 m
> aircraft with the pilot a full MAC below it reached 29 points; that aircraft is not
> in this repository, so treat 13.5 as the figure you can check and 29 as the top of
> the range seen.
>
> flow5ctl reports both. `static_margin` is the classical figure — the one the 5-15 %
> band below refers to, the one tail-sizing rules produce, and the one a published
> 「重心位置 % MAC」 is paired with. `pitch_stiffness_margin` is the whole −dCm/dCL
> about the real CG. **Compare only the first against any band or published value.**
> Confusing them puts a conventional design tens of points outside its own class's
> range and makes an unflyable one look stable.

> **Lateral stability needs real inertia.** With `Use_plane_inertia=true` flow5
> ignores any explicit inertia you supply and derives it from the plane's masses. If
> those all sit on the centreline, `Ixx = 0` and every lateral result is meaningless.
> Distribute mass spanwise, or supply inertia explicitly with
> `Use_plane_inertia=false`. ([FLOW5-INTERFACE.md §4.4](FLOW5-INTERFACE.md))

Static margin and neutral point *are* reported by a T1 polar and are usable — it is
the dynamic modes that require T7.

## 3. Reynolds number decides everything at this scale

Compute Re at the MAC at cruise before choosing an airfoil. flow5ctl reports it in
`get_design`.

| Re at MAC | Regime |
|---|---|
| < 5×10⁴ | Very low Re. Laminar separation bubbles dominate. 2D data is unreliable and sensitive to `ncrit`; treat results as indicative. DLG tips live here. |
| 5×10⁴ – 2×10⁵ | Low Re. Typical RC glider. Airfoil choice dominates performance. Bubble drag is real; use airfoils designed for the regime (AG, SD, MH, RG15). |
| 2×10⁵ – 1×10⁶ | HPA and large models. Better behaved. DAE, FX, SG series. |
| > 1×10⁶ | Above this community's normal range. |

**Viscous analysis is not optional here.** Measured on the shipped 3 m glider
(Re 1.5×10⁵ at the MAC) at α = 0°: CD was **0.000332 inviscid against 0.017991
viscous** — the inviscid run left out **98 %** of the drag. Re-run it with
`analyze --inviscid` and without. flow5ctl defaults `viscous: true`; if you turn it off, say why, and
never quote an L/D from an inviscid run.

**Pick one viscous method and stay with it.** The interpolated method (a
pre-computed 2D polar mesh) and on-the-fly XFoil disagree substantially, and
**on-the-fly is consistently the lower of the two**. Measured on
[`examples/rc-glider.yaml`](../examples/rc-glider.yaml), the same run with and
without `--on-the-fly`:

| α | viscous CD, interpolated | on-the-fly | on-the-fly is |
|---|---|---|---|
| 0° | 0.017659 | 0.014258 | 19 % lower |
| 2° | 0.017238 | 0.013800 | 20 % lower |
| 4° | 0.018450 | 0.013461 | 27 % lower |
| 6° | 0.020263 | 0.014584 | 28 % lower |

Total CD is 19 % lower throughout. **Which one is right is not known here** — the
interpolated mesh smooths across the gaps where XFoil did not converge, and
on-the-fly computes at the exact condition but fails more often. What is certain is
that mixing them inside a comparison invents a fifth of the drag that is not in the
aircraft.

Interpolation is the default: on-the-fly failed to converge on the elevator of a
3-surface glider and discarded every operating point, while interpolation ran five
polar types on the same aircraft in 1.3 s.

`ncrit` encodes freestream turbulence: 9 is standard, 11–12 for very clean air,
4–6 for turbulent conditions. It should change low-Re drag substantially. Pick one,
state it, and keep it fixed across comparisons.

> **`ncrit` stops doing anything once transition reaches the leading edge**, which on
> a cambered section happens well below stall. Measured on a 13.6 %-thick, 6.7 %-camber
> section at Re 4.5×10⁵ in flow5 7.57, with the transition column read alongside the
> drag:
>
> | Cl | Cd @ n9 | Xtr | Cd @ n11 | Xtr | Cd @ n13 | Xtr |
> |---|---|---|---|---|---|---|
> | 0.79 | 0.01050 | 0.715 | 0.01150 | 0.729 | 0.01265 | 0.741 |
> | 0.90 | 0.01513 | **0.000** | 0.01513 | **0.000** | 0.01513 | **0.000** |
> | 1.10 | 0.02013 | **0.000** | 0.02013 | **0.000** | 0.02013 | **0.000** |
>
> Above Cl 0.9 the upper surface is turbulent from the leading edge, so there is no
> laminar run left for ncrit to act on and the drag is bit-identical by construction.
> Below it ncrit works normally — transition moves aft monotonically. That minimum
> drag *rises* with ncrit is also real: pushing transition aft lengthens the laminar
> separation bubble, and on this section the bubble costs more than the skin friction
> it saves. Both effects are physics.
>
> An earlier version of this guide called the identical drag a flow5 defect. It is
> not; the transition column settles it. What is worth checking is where your own
> section's transition reaches the leading edge, because ncrit is only a design knob
> below that point.

Make sure the 2D polar mesh **brackets** the Re the wing actually sees, root to tip
**and across the whole speed range** — not just at cruise. A 34 m tapered wing at
8 m/s spans a factor of ~2 in local Re, and the tip is the low-Re end where the
airfoil is worst behaved.

This is not a refinement. Measured: a mesh covering Re 50 k–250 k produced a T2 polar
with **1 of 6** points and a T7 polar with **none**; widening it to 20 k–400 k gave
5 of 5 and a working T7. The cause is that a fixed-lift polar solves a *lower* speed
at high CL — α=8° came out at 4.69 m/s, putting the tip at Re ≈ 40 k, below the mesh.
Derive the range from the **minimum** flight speed and the **tip** chord, then widen it.

## 4. Panels and convergence

Results depend on the mesh. Before believing a number, know that it has converged.

- Start at the preset defaults (13 chordwise × 20–40 per semi-span).
- Chordwise panels drive pitching moment accuracy more than lift.
- Use `COSINE` chordwise, and `COSINE` spanwise on a wing with strong taper or a
  tip that matters.
- **Refine once and check.** If doubling the panel count moves CL by more than ~1 %
  or Cm by more than ~2 %, the coarse mesh was not enough.
- Measured on [`examples/hpa.yaml`](../examples/hpa.yaml), viscous, varying only the
  wing mesh:

  | wing panels | total | L/D at α = 6° | L/D at α = 0° |
  |---|---|---|---|
  | 9 × 20 | 612 | 50.03 | 24.93 |
  | 13 × 40 (the preset) | 1292 | 50.22 | 26.05 |
  | 17 × 60 | 2292 | 50.18 | 26.66 |
  | 21 × 90 | 4032 | 50.17 | **27.03** |

  **Near best L/D the coarsest mesh is already converged** — 0.3 % across a
  six-fold refinement. **The low-CL end is not**: α = 0° moves 8.4 % over the same
  range and is still climbing at 4032 panels. So the preset default is enough for
  the part of the polar you design at, and the high-speed end needs refining before
  it is trusted.
- Panel count is not a time problem at this scale: 3172 panels, viscous, two polars,
  4 α points ran in 1.5 s. Refine when in doubt.

`VLM2` is the sensible default. `LLT` is faster and fine for a straight, unswept,
moderate-dihedral single wing but cannot handle sweep, multiple surfaces, or
interference. Panel methods (`QUADS`, `TRIUNIFORM`, `TRILINEAR`) model thickness and
are needed for fuselages.

## 5. Longitudinal stability

- **Static margin** = (X_NP − X_CG) / MAC. Positive means statically stable.
- Target bands by class: HPA 5–15 %, RC glider 5–12 % (F3F racers fly lower;
  thermal duration ships higher), UAV 10–20 %.
- Below ~3 % the aircraft is twitchy and sensitive to build tolerance; negative is
  unstable and, for a human-powered aircraft flown by a tired pilot a few metres
  above water, unacceptable.
- **Tail volume coefficients** are the sanity check flow5 will not do:
  horizontal V_h = (S_h · l_h) / (S_w · MAC), typically 0.4–0.7;
  vertical V_v = (S_v · l_v) / (S_w · b), typically 0.02–0.05.
  A design that only reaches its static margin through an implausibly small tail is
  wrong somewhere else.
- Changing CG changes trim, which changes trimmed L/D. Report performance **at trim**,
  not at a fixed α, when comparing CG positions. Use `trim`.
- **Best L/D does not respond to the CG at all.** The drag polar is unchanged; only
  the point at which the aircraft trims moves. Measured on
  [`examples/rc-glider.yaml`](../examples/rc-glider.yaml) —
  `sweep --parameter cg_x --values 0.040,0.055,0.070,0.090`:

  | cg_x (m) | best L/D | **L/D at trim** | static margin | trim α |
  |---|---|---|---|---|
  | 0.040 | 23.668 | 7.72 | +24.7 % | 0.25° |
  | 0.055 | 23.668 | 11.22 | +16.9 % | 0.87° |
  | 0.070 | 23.668 | 17.78 | +9.0 % | 2.41° |
  | 0.090 | 23.668 | — | **−1.4 %** | — |

  Best L/D is the **same number to five figures** at every CG, while the L/D the
  aircraft actually flies at more than doubles. At 90 mm it is unstable and there is
  no trim point at all, which is why the last row is empty. Compare CG positions on
  `ld_at_trim`; comparing on best L/D will tell you the CG does not matter.
- **The neutral point does not move with the CG**, so a target static margin is a
  solve, not a search: X_cg = X_np − SM·MAC. `flow5ctl trim --target static-margin`
  does it in two runs.

## 6. Ground effect — read this for HPA

Birdman Rally aircraft fly a few metres above water. Ground effect is not a detail
there; it can cut induced drag by 20–40 % at a height of half a span or less, and
induced drag is most of the drag budget on a high-AR aircraft.

- Enable it: `ground_effect: true`, `ground_height` = height of the **CG above the
  water**, positive.
- The `hpa` preset enables it by default.
- Report *both* in and out of ground effect. Take-off, cruise near the water, and
  any climb are different problems.
- flow5 models the ground with an image plane. That is the right first-order model
  and it is not exact near the surface.

Measured on the two shipped examples with the current defaults, so any reader can
reproduce them with `analyze --compare-ground`:

| example | height | best L/D | minimum sink |
|---|---|---|---|
| [`examples/hpa.yaml`](../examples/hpa.yaml), 34 m | 2.0 m | 43.66 → 50.64 (**+16.0 %**) | 0.1599 → 0.1330 (−16.8 %) |
| [`examples/rc-glider.yaml`](../examples/rc-glider.yaml), 3 m | 0.30 m | 23.67 → 27.27 (**+15.2 %**) | 0.1991 → 0.1646 (−17.3 %) |

Earlier versions of this guide quoted +18 to +20 %, measured before the Reynolds
ladder was widened to eight rungs per decade and the spanwise panel default raised
to 40. Both changed the drag, so those figures no longer describe what this tool
does — which is the reason for preferring numbers a reader can re-run.

For a Birdman Rally aircraft this is a design driver, not a correction.

Negative `ground_height` models a hydrofoil under a free surface — a different
feature, not a mistake to make by accident.

## 7. Spanwise loading

For minimum induced drag on a planar wing the loading is elliptic. In practice:

- Check the spanwise lift distribution (`plot --kind spanwise_lift`), not just the
  total.
- Washout trades a little induced drag for tip-stall margin and roll damping. On an
  HPA it also unloads the tip where the structure is lightest. −2° to −4° is common.
- A perfectly elliptic planform is neither buildable nor optimal once structural
  mass is priced in. Slight taper toward the tip with a bit of washout is the usual
  compromise, and for a span-loaded aircraft the *structurally* optimal loading is
  deliberately non-elliptic.
- Taper ratios below ~0.4 push the tip into a lower Re than the airfoil data covers.

## 8. Reporting honestly

When you report a result, include:

1. The analysis conditions — type, speed, mass, CG, viscous **method**, ncrit,
   ground effect.
2. Whether the mesh was checked for convergence.
3. Which numbers are comparative and which are absolute.
4. The limits from §1 that apply.

One unit trap worth naming because it inverts a conclusion: flow5 reports
**static margin as a percentage** of the reference chord. A reported `-0.59` means
−0.59 % — marginally unstable — not −59 %. flow5ctl normalises this at the boundary
and reports a fraction, but if you read a raw flow5 file, remember it.

A comparison table between two designs run identically is worth more than a single
absolute figure, and it is what this tool is good at. Prefer it.

## 9. Cross-check before you commit

flow5 is one solver. Before a design decision that costs money or carries a pilot:

- Sanity-check lift-curve slope against lifting-line theory: CL_α ≈ 2π·AR / (2 + AR)
  per radian for a straight wing. Agreement within ~10 % is expected; a large
  discrepancy means the model is wrong, not that the theory is.
- Compare against a second tool (AVL, XFLR5) for anything structural or life-critical.
- Compare against measured data from a previous aircraft in the same class if you
  have it. Teams that have flown before should calibrate against their own results.

**No aircraft that carries a person should be committed to build on the basis of a
potential-flow analysis alone, and an agent should say so.**
