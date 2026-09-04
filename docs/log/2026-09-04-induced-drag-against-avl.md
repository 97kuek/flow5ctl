# 2026-09-04 — flow5's induced drag against AVL, and against an exact answer

> ## ⚠ The conclusion below is WRONG, and it was released in 0.1.0
>
> This log concluded that flow5's induced drag is systematically low by an amount
> that grows with aspect ratio. **It is not.** A second reviewer pointed out the
> confound the same day: flow5's wake is **30 × MAC** by default, and every run here
> left it there. A wake measured in chords is `30 / AR` **spans**, so it shortens as
> the wing gets slender — 3 spans at AR 10, 0.75 at AR 40 — and that is what the
> "aspect ratio dependence" actually was.
>
> Varying only the wake length, on the same AR 40 elliptic wing:
>
> | wake | span efficiency (exact: 1.0) |
> |---|---|
> | 30 × MAC (flow5's default) | 1.2103 |
> | 100 × MAC | 1.0305 |
> | 300 × MAC | 1.0035 |
> | 1000 × MAC | **1.0001** |
>
> And holding the wake at a fixed number of **spans**, the aspect-ratio dependence
> disappears entirely:
>
> | wake (spans) | AR 10 | AR 20 | AR 30 | AR 40 | AR 50 |
> |---|---|---|---|---|---|
> | 0.75 | 1.2238 | 1.2154 | 1.2126 | 1.2103 | 1.2095 |
> | 3 | 1.0240 | 1.0238 | 1.0229 | 1.0217 | 1.0214 |
> | 10 | 1.0039 | 1.0038 | 1.0030 | 1.0019 | 1.0016 |
> | 30 | 1.0020 | 1.0019 | 1.0011 | 1.0000 | 0.9997 |
>
> **The error depends on the wake in spans and not on aspect ratio at all.** flow5's
> induced drag is right; the default wake is too short for a slender wing, and this
> tool was not setting it.
>
> Fixed in 0.1.1: flow5ctl now writes a `<Wake>` block with the length in **spans**
> (20 by default), which brings the elliptic wings to within **0.23 %** of the exact
> answer at every aspect ratio from 10 to 50. See
> [the wake log](2026-09-04-the-wake-was-too-short.md).
>
> **What went wrong in the reasoning.** The controls varied mesh, spanwise
> distribution, chordwise count and VLM1-against-VLM2, and all of them moved the
> answer by 0.4 %. That felt exhaustive and was not: the aspect-ratio sweep held the
> span at 34 m and varied the chord, so the wake — fixed in chords — was the one
> thing changing along with AR, and it was the only input never varied. AVL agreeing
> with the exact answer made flow5 look like the odd one out, when what differed was
> a solver setting this tool had left at its default.
>
> The measurements below are left as they were recorded.


**Question:** the [mesh investigation](2026-09-04-induced-drag-and-the-mesh.md) left a
residual. flow5's span efficiency for a rectangular AR 10 wing extrapolated to 0.984
where classical lifting line gives 0.921, and the disagreement was concentrated at the
tip. That log said an independent third method was what would settle it.

**Answer:** it is settled, and the answer is worse than the residual suggested.
flow5's induced drag is **systematically low, by an amount that grows with aspect
ratio** — about 2 % at AR 10 and **17 % at AR 40**. It is not the mesh, not the
panel distribution and not the method. At the aspect ratios this project's main users
fly, it is the largest known error in the tool.

Environment: macOS arm64, flow5 7.57, **AVL 3.40** (`avl3.40_execs/DARWINM1/avl` from
[web.mit.edu/drela/Public/web/avl](https://web.mit.edu/drela/Public/web/avl/)),
inviscid, α = 5°, `e = CL² / (π · AR · CD_induced)` from each solver's own columns.

## 1. The test that has an exact answer

An elliptic planform is the case where nobody has to arbitrate. Its span efficiency
is **1.0**, and for a planar wing 1.0 is a hard upper bound — no planar wing can
beat elliptic loading. A solver that returns more than 1.0 is under-predicting
induced drag, and by how much is readable directly.

The planform was built as 25 straight-edged sections following `c(η) = c₀√(1−η²)`.
That discretisation is very slightly *less* efficient than a true ellipse, so the
correct answer is a shade **below** 1.0 — which is what AVL returns.

| AR 10 elliptic | e | verdict |
|---|---|---|
| exact (planar limit) | 1.0000 | — |
| classical lifting line, true ellipse | 1.000000 | the method is exact here |
| **AVL** | **0.9969** | correct, 0.3 % below for the discretisation |
| **flow5, 120 spanwise** | **1.0233** | **2.3 % above the limit** |

| AR 40 elliptic | e | verdict |
|---|---|---|
| exact (planar limit) | 1.0000 | — |
| **AVL** | **0.9955** | correct |
| **flow5, 120 spanwise** | **1.2103** | **21 % above the limit** |

## 2. It is not the mesh, the distribution or the method

Everything varied on the AR 40 elliptic wing, one at a time:

| variation | e |
|---|---|
| COSINE, 120 spanwise, 9 chordwise | 1.2103 |
| UNIFORM, 120 spanwise | 1.2106 |
| SINE, 120 spanwise | 1.2098 |
| COSINE, 60 spanwise | 1.2135 |
| COSINE, 120 spanwise, **21** chordwise | 1.2103 |
| **VLM1** instead of VLM2 | 1.2099 |

Spread: 0.4 %. The mesh refinement documented in the previous log is real but small,
and it is not this.

**AVL is mesh-independent from 10 panels.** Its e was 0.9596 at 10, 20, 40, 80 and 120
spanwise on the rectangular AR 10 wing — five identical values to four figures — while
flow5's ran 1.035 → 0.989 over the same range.

## 2a. Switching methods does not fix it — it errs the other way

flow5's panel methods model thickness and solve a different problem, so they are the
obvious thing to try. Same elliptic AR 40 wing, every method flow5 offers:

| method | e (exact answer: 1.0000) | panels |
|---|---|---|
| VLM1 | 1.2104 | 1800 |
| VLM2 | 1.2108 | 1800 |
| LLT | flow5 reported errors on every point | — |
| **QUADS** | **0.7826** | 1800 |
| **TRIUNIFORM** | **0.7925** | 3600 |
| **TRILINEAR** | **0.7868** | 3600 |

The vortex-lattice methods are 21 % **above** the limit and the panel methods 21 %
**below** it. Both are mesh-converged: QUADS ran 0.7842 → 0.7826 → 0.7826 → 0.7817
from 1080 to 5040 panels.

At AR 10 the panel method is at least physically admissible where the VLM is not:

| AR 10 elliptic | e |
|---|---|
| AVL | 0.9969 |
| **flow5 QUADS** | **0.9800** — below the limit, 1.7 % pessimistic |
| flow5 VLM2 | 1.0233 — above the limit, impossible |

**So no flow5 method gives the induced drag correctly at high aspect ratio**, and
changing method is not a workaround. CL is unaffected throughout — QUADS gives
0.51561 at AR 40 against AVL's 0.51779, 0.4 % apart.

The two families happen to bracket the true answer in both cases measured, and their
midpoint lands within 0.1 % of it. **That is two data points and a coincidence, not
a method** — do not average them. What it is good for is a smell test: a large gap
between a VLM run and a QUADS run means the induced drag from either is not to be
trusted.

## 3. The error against aspect ratio

Elliptic wing, b = 34 m, 100 spanwise panels, inviscid VLM2. The exact answer is
1.0000 at every row:

| AR | flow5 e | error in e | **induced drag is** |
|---|---|---|---|
| 6 | 1.0089 | +0.9 % | 0.9 % low |
| 10 | 1.0241 | +2.4 % | 2.4 % low |
| 15 | 1.0486 | +4.9 % | 4.6 % low |
| 20 | 1.0771 | +7.7 % | 7.2 % low |
| 25 | 1.1089 | +10.9 % | 9.8 % low |
| 30 | 1.1420 | +14.2 % | **12.4 % low** |
| 40 | 1.2108 | +21.1 % | **17.4 % low** |
| 50 | 1.2801 | +28.0 % | **21.9 % low** |

Roughly **half a percent of induced drag per unit of aspect ratio** above about 5.

The rectangular wings agree: flow5/AVL on CDi is 1.025 at AR 10 and 1.170 at AR 40,
matching the elliptic figures. So it is not a property of one planform.

## 4. Lift is not affected

| case | flow5 CL | AVL CL | apart |
|---|---|---|---|
| rectangular AR 10, α 5° | 0.42264 | 0.42119 | 0.3 % |
| elliptic AR 40, α 5° | 0.52110 | 0.51779 | 0.6 % |

The two solvers agree on lift at both aspect ratios. Classical lifting line is the
outlier there instead — 0.44042 against flow5's 0.42264 at AR 10, 4 % high — which is
the expected weakness of a single-bound-vortex model and is why §5 of the previous
log could not settle anything on its own.

**So this is specific to the induced drag.** flow5 takes it on the Trefftz plane
(`planetask.cpp:1758`), which is the right place; something in that calculation
under-reads, and the under-read scales with span.

## 5. What it means for this project

Human-powered aircraft fly at **AR 30–45**, which is exactly where the error is
largest, and induced drag is the dominant term in their drag budget. A modelled L/D
for an HPA is optimistic by more than the "few percent" the design guide used to
claim.

It also puts a second term into the reconstruction conclusion recorded in
[DESIGN-GUIDE §1a](../DESIGN-GUIDE.md). That work found the modelled L/D was not
systematically wrong once the missing-drag budget was applied, on the strength of
one aircraft whose airfoil modification was published. This finding says one
component of the modelled drag *is* systematically low at that aspect ratio. Both
can be true — the budget band is wide — but the earlier conclusion should be read as
"the airfoil substitution explains the gap between those aircraft", not as "the
modelled drag is unbiased".

## What changed as a result

- `analyze` warns on any aircraft above AR 15, with the figure for its own aspect
  ratio, and says which direction it errs in.
- [DESIGN-GUIDE.md §1](../DESIGN-GUIDE.md) and its
  [Japanese translation](../ja/DESIGN-GUIDE.md) carry the table.
- §9 of the guide already said to cross-check against AVL before committing a design.
  It now says what that cross-check found.


## 6. A multi-surface aircraft, and a trap found on the way

The single-wing comparison says nothing about the interference between a wing and a
tail, which is most of what a real analysis is doing. The same three-surface aircraft
— AR 12 rectangular wing, a 0.9 × 0.15 m tail 1.2 m behind, a fin — was built in both.

**They agree.** flow5 gives CDi 0.00977 at CL 0.5926; AVL gives 0.01008 at 0.5884,
3 % apart, and the neutral point comes out at 0.184 m in flow5 against **0.1833 m**
in AVL. The pitching moments agree to 2 % once referenced to the same point. So the
interference is handled correctly, and the stability number — the one a design
decision rests on — is right.

**Except that the first attempt said the induced drag was 52 % low, and that was our
own test geometry's fault.** The tail had been put at `z = 0`, exactly the wing's own
height. The wing's trailing vortices leave at that height and run downstream, so the
tail's control points sat on the vortex sheet. flow5 does not complain; it returns a
number. Moving the tail by two centimetres:

| tail z | as a fraction of the 0.25 m chord | CD_induced | span efficiency |
|---|---|---|---|
| 0.000 | 0 | 0.004830 | **1.932 — impossible** |
| 0.001 | 0.4 % | 0.007337 | 1.271 — impossible |
| 0.005 | 2 % | 0.009352 | 0.996 |
| 0.010 | 4 % | 0.009642 | 0.966 |
| 0.015 | 6 % | 0.009736 | 0.957 |
| 0.020 | 8 % | 0.009772 | 0.953 |
| 0.400 | 160 % | 0.009746 | 0.963 |

Two centimetres **doubles** the induced drag, to the value that then matches AVL.

Real aircraft rarely sit exactly on that plane, but `position: [1.2, 0, 0]` in a
`design.yaml` does, and that is an easy thing to type. `analyze` now warns when a
surface behind the wing is within a tenth of the MAC of the wing's height. Both
shipped examples are clear of it.

**The claim this section nearly made was wrong**, and it is recorded because the
correction is the useful part: a solver that returns a confident number for a
singular configuration is exactly the failure mode this project is built around, and
the first reading of the evidence blamed the solver's physics for what was a
geometry anybody could type.
