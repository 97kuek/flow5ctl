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
- **Induced drag to better than a few percent.** A rectangular wing came back with a
  span efficiency of 1.008–1.012 — physically impossible for a planar wing, where 1.0
  is the elliptic limit. The error is small, but it means induced drag is good to
  roughly ±5 %, not exactly.
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

> This does not explain every discrepancy, and it is worth knowing why. Against
> three reconstructed aircraft the modelled L/D came out 16–28 % *below* what the
> published thrust implies, and adding the missing drag moves it further away, not
> closer. Something else is going on there — see the drag section of
> [ROADMAP.md](ROADMAP.md).

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
> whose dihedral lifts its mean height further, the offset reaches a full MAC and the
> term reaches **29 percentage points**.
>
> flow5ctl reports both. `static_margin` is the classical figure — the one the 5-15 %
> band below refers to, the one tail-sizing rules produce, and the one a published
> 「重心位置 % MAC」 is paired with. `pitch_stiffness_margin` is the whole −dCm/dCL
> about the real CG. **Compare only the first against any band or published value.**
> Measured on two reconstructed aircraft, confusing them put conventional designs 12
> and 29 points outside their own class's range.

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

**Viscous analysis is not optional here.** Measured on one wing at Re 2×10⁵: CD at
α=0° was 0.00095 inviscid versus 0.0133 viscous — the inviscid run omitted **93 %**
of the drag. flow5ctl defaults `viscous: true`; if you turn it off, say why, and
never quote an L/D from an inviscid run.

**Pick one viscous method and stay with it.** The interpolated method (a
pre-computed 2D polar mesh) and on-the-fly XFoil disagree by 10–25 % on viscous drag,
so mixing them inside a comparison invents a difference that is not in the aircraft.
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
- Measured on a 34 m HPA, 544 → 3172 panels: L/D at α=6° moved 45.6 → 45.4 (0.4 %)
  and static margin 5.09 → 5.07 %. **Converged at the coarsest mesh** — the preset
  default is already enough for a clean high-AR planform. The low-CL end is more
  sensitive: L/D at α=0° moved 27.7 → 29.4 (6 %), so refine before trusting the
  high-speed end of a polar.
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
  the point at which the aircraft trims moves. Measured on a 3 m glider, moving the CG
  from 40 to 90 mm left best L/D at 22.8 throughout while trimmed L/D went from 4.5 to
  17.3 and the static margin fell from 34 % to 8 %. Compare CG positions on
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

Measured magnitudes: a 3 m glider at h = 0.30 m gained CL +8 %, lost CD 9.6 %, and
went from L/D 24.4 to 29.2 (**+20 %**). A 34 m HPA at h = 2.0 m went from L/D 45.5 to
53.8 (**+18 %**), with static margin moving 5.08 → 7.08 %. For a Birdman Rally
aircraft this is a design driver, not a correction.

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
