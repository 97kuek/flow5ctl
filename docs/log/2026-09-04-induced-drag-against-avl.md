# 2026-09-04 — flow5's induced drag against AVL, and against an exact answer

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
