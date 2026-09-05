# Review backlog

What is still worth an adversarial second opinion, why, and what to ask.

This exists because the two most serious defects found in this project were both
found by a reviewer asking a question nobody here had asked, and both were the same
shape: **a number chosen for convenience, never measured, wrong in the direction that
flatters the aircraft.**

- [The wake was too short](log/2026-09-04-the-wake-was-too-short.md). A published
  claim — "flow5's induced drag is systematically low, worsening with aspect ratio" —
  shipped in the README, both design guides, the roadmap risk table and a runtime
  warning. Six controls had been run. The reviewer asked about the one input none of
  them held fixed. The claim was retracted.
- [The gate was too wide](log/2026-09-05-the-gate-was-too-wide.md). The threshold
  deciding when a reported static margin is the classical one was fifteen times too
  wide, admitting +0.75 points of margin an aircraft does not have — in the direction
  a pilot's seating position produces. The advisor calls any positive margin stable.

Neither was found by testing. Both were found by someone asking why a number was what
it was. That is what this list is for.

## How to run one

Measured over fifteen reviews: **single-topic requests with two questions succeeded
eleven times out of eleven; ten-item requests failed twice.** Four concurrent reviews
at `effort=high` on a ChatGPT Plus plan exhausted the usage limit and lost one.

So: one topic, two questions, name the files, say what a failure would cost, and ask
the reviewer to be adversarial. Run them one or two at a time. `effort=medium` was
enough for every finding on this page — the three reviews that produced the drag,
stability and store findings were not limited by reasoning effort but by whether the
question was specific.

State the aircraft's purpose in the prompt. "This tool designs aircraft that carry a
person" changed the character of the stability review completely.

### Coverage figures on this page

Measured 2026-09-05 with `pytest-cov`. Two numbers exist for anything that touches the
solver: CI runs `-m "not needs_flow5"`, which is what protects a pull request, while
the full suite adds 31 solver tests on a developer machine. Where they differ
materially both are given. Overall: **84 % with flow5, 4,001 statements.**

Coverage is named here only to say what has never been executed. It is not a target —
the tautological tests found in `test_project.py` on 2026-09-05 were counted as
coverage while proving nothing.

## Tier 1 — safety, and unreviewed

### 1. Ground effect

`usecases/ground.py`, the ground parts of `flow5/xmlgen.py`.

**The highest-value item on this page.** A Birdman Rally aircraft flies its entire
flight in ground effect a few metres above water. The tool currently reports a
**+22.5 % L/D gain** for `examples/hpa.yaml`, and that number, more than any other,
is what a team would design against.

Two reviews have now been lost to usage limits here. The second got one finding out
before dying — that flow5 mirrors across `z = -Ground_Height` in model coordinates and
infers nothing about the CG or the wing, which turned out to mean the guide's
description of the input was wrong ([log](log/2026-09-05-the-ground-height-was-not-the-cg.md)).

**Question 2 below is still unanswered and is the more important half.** Whether the
magnitude is right has been checked by nobody.

Worse: `ground.compare` — the whole body of the comparison, lines 48–63 — is **never
executed by any test**, including the ones that run a real flow5. `ground.py` sits at
71 % with the solver tests deselected and at 71 % with them included: the solver tests
do not reach it at all. Only `resolve_height` and `replace_ground` are covered. The
+22.5 % figure comes out of code no test has ever run.

Ask:
1. Is the ground actually modelled — how does flow5 represent it (image plane,
   mirrored panels, a ground panel), does our XML request that correctly, and is the
   height reference physically the right one? We pass a chord-weighted `mac_z` and
   document a residual of 0.8 points against a load-weighted height.
2. Is +22.5 % defensible against Wieselsberger, Hoerner and modern panel data, or is
   it out by enough that a team would build to it? Use **h/b = 0.066** for the HPA,
   not the 0.059 the declared height suggests — the wing sits above the datum. Note
   that an L/D gain is not an induced-drag reduction: profile drag does not change, so
   the gain has to be consistent with the induced-drag fraction of this aircraft's
   drag at the best-L/D point. Confusing those two is the most likely way this number
   is wrong.

### 2. Structural root load

`advisor/structure.py` (171 lines, 96 % covered but with no dedicated test file).

This estimates the bending moment at the wing root. For a human-powered aircraft that
is the number between the pilot and the water. The module states its own central
assumption — "the closed form assumes the wing carries all the lift" — which is
exactly the kind of self-declared approximation whose *size* has never been measured.
The reference-height approximation was documented the same way and turned out to
matter.

Ask:
1. Is the closed form right, and how large is the error from the single-lifting-wing
   assumption on a design where the tail carries real load? Does `shared_lift` fix it
   or merely re-scale it?
2. Do `load_factor` and the elliptic-centroid shortcut hold for a wing with taper and
   washout, and does `cross_check` actually detect a strip table that disagrees, or
   only one that disagrees a lot? (`_DISAGREEMENT = 0.35` is asserted, not measured.)

### 3. The unmeasured thresholds

Numeric constants that shape a user-facing verdict. **Two of eleven are measured.**

| constant | file | basis |
|---|---|---|
| `spanwise = 40` | `model/design.py` | measured, AR 10 and 40, logged |
| `wake_spans = 20.0` | `flow5/xmlgen.py` | measured |
| `REFERENCE_PASS_ABOVE = 0.003` | `flow5/summary.py` | measured 2026-09-05, after being wrong by 15× |
| `chordwise = 13` | `model/design.py` | none given |
| `_DIFFERS = 0.005` | `advisor/stability.py` | asserted: "below this the two margins are the same number" |
| `_DISAGREEMENT = 0.35` | `advisor/structure.py` | asserted |
| `_LEVEL = 0.15` | `advisor/structure.py` | asserted |
| `MAX_ITERATIONS = 8` | `usecases/trim.py` | none given |
| `WAKE_PLANE_MAC = 0.10` | `advisor/guardrails.py` | labelled a heuristic |
| `tol = 0.02` | `advisor/guardrails.py` | none given |
| `_SWEPT_DEG = 0.5` | `flow5/summary.py` | none given |

Ask, for a named few at a time:
1. Which of these can change a verdict a user acts on, and for each, what measurement
   would establish the right value?
2. Which are wrong in the direction that flatters the aircraft?

Note that `chordwise = 13` sits beside `spanwise = 40`, which carries a measurement
table. The neighbour was measured and it was not.

### 4. The preset bands

`presets/*.yaml` — e.g. `static_margin: [0.05, 0.15]`, `cl_max_estimate: 1.4`.

**Every stability verdict the tool gives is a comparison against these**, and they
have never been reviewed. `advisor/stability.py` phrases its output as "the preset for
this class expects 5–15 %" — the band *is* the advice.

Ask:
1. Are the static-margin bands right for each class, and is a single band per class
   even the right shape given that an HPA's margin requirement depends on pilot mass
   fraction and control authority?
2. Is `cl_max_estimate` used anywhere it can silently truncate a Reynolds ladder or a
   polar range?

## Tier 2 — correctness

### 5. What we actually send flow5

`flow5/xmlgen.py` (463 lines) against the flow5 source.

The wake finding came from reading `xflxmlwriter.cpp`. Twelve flow5 source files are
cited across `docs/`; the XML we emit has never been reviewed against them as a whole.

Ask:
1. Does every element we write mean what we think, and are there elements flow5
   honours that we leave at defaults that do not suit these aircraft?
2. Is `Use_plane_inertia=false` doing what we assume, i.e. is flow5 using our inertia
   tensor rather than recomputing one?

### 6. Mass properties into the dynamic modes

`geometry/massprops.py` (87 lines) → `xmlgen` inertia → `summary.parse_modes`.

An unreviewed path end to end. If the inertia tensor is wrong the phugoid period and
short-period damping are wrong, and **the output looks entirely normal** — this
project's stated failure mode.

Ask:
1. Is the inertia tensor computed correctly from point masses, including `Ixz` and the
   axis convention flow5 expects?
2. Do the parsed modes correspond to the modes they are labelled as, and would a sign
   or axis error be visible in the output at all?

### 7. Airfoil polars and their gaps

`flow5/airfoils.py` (87 %), `flow5/foilpolar.py` (67 %).

Ask:
1. When XFoil fails to converge at a Reynolds/alpha combination, what does the 3D pass
   do with the hole — interpolate across it, extrapolate off the end, or refuse?
2. Is the gap warning raised for every case that matters, or only when the manifest
   notices?

### 8. Sweep and its trimmed metrics

`usecases/sweep.py` (397 lines; 59 % without flow5, 90 % with it).

`_apply_trimmed` forces T2 and swaps the metric set. Ask whether the swapped metrics
mean the same thing across the sweep, and whether the three qualifications in its note
cover the cases where they do not.

## Tier 3 — interface and robustness

### 9. The CLI

`cli.py` — **881 lines, the largest module, 46 % covered, no dedicated test file.**
It is the least-covered module in the package and the one every human interaction
passes through.

Everything a person types goes through it. Ask about argument parsing that can
silently mean something other than what was typed, and about the paths that write to
a design.

### 10. The MCP contract

`mcp_server.py` (649 lines, 68 % covered).

One finding is already known and unfixed: **`status` is `"ok"` in all six use cases**,
so it carries no information, and an MCP client reading only structured output cannot
distinguish success from a failed solve. `trim` now reports `converged` separately;
the general question is untouched because changing `status` everywhere alters the
published contract.

Ask:
1. Should `status` mean something, and what breaks if it does?
2. Are there tools whose structured output omits a fact the prose warning carries —
   i.e. where an agent client is told less than a human reader?

### 11. Subprocess handling

`flow5/runner.py` (47 % covered), `flow5/probe.py` (70 %).

Ask about timeout handling, orphaned processes, and whether a partially-written output
directory can be read as a complete run.

### 12. Documentation against code

`docs/` is 2,900 lines and carries the measured claims. The induced-drag retraction
had to be propagated to five places by hand.

Ask for a sweep of every quantitative claim in `docs/` against the code and logs that
produced it, naming any that no longer hold.

## Not on this list

- **Anything requiring someone who did not build the tool.** The Phase 3 exit
  criterion needs a Birdman Rally team member to design an aircraft with it. No
  review substitutes for that.
- **`open_in_flow5`.** Deliberately never exercised; it opens a GUI window on the
  user's desktop. Only its refusal path is tested.
