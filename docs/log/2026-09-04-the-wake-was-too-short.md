# 2026-09-04 — the wake was too short, and it was our fault

**Question:** [the AVL comparison](2026-09-04-induced-drag-against-avl.md) concluded
that flow5's induced drag is systematically low, by an amount growing with aspect
ratio, and 0.1.0 shipped that claim in the README, both design guides and a runtime
warning. A reviewer asked one question the investigation had not: **how long is the
wake?**

**Answer:** 30 × MAC, flow5's default, because flow5ctl never wrote a `<Wake>`
element and so never set one. That is `30 / AR` **spans** — 3 spans at AR 10, 0.75 at
AR 40. The trailing vortices have not straightened out that close behind a slender
wing, the downwash is under-resolved, and the induced drag comes out low. **The claim
was wrong and the solver was right.**

## 1. Vary only the wake

Elliptic wing, AR 40, inviscid VLM2, α = 5°, 100 spanwise panels. The exact answer is
a span efficiency of **1.0**, and no planar wing can beat it.

| wake length | span efficiency |
|---|---|
| 30 × MAC — flow5's default | 1.2103 |
| 100 × MAC | 1.0305 |
| 300 × MAC | 1.0035 |
| 1000 × MAC | **1.0001** |

`CD_induced` at 1000 × MAC is 0.0021398 against AVL's 0.0021353 — **0.2 % apart**.

## 2. The aspect-ratio dependence disappears

Holding the wake at a fixed number of **spans** rather than chords:

| wake (spans) | AR 10 | AR 20 | AR 30 | AR 40 | AR 50 |
|---|---|---|---|---|---|
| 0.75 | 1.2238 | 1.2154 | 1.2126 | 1.2103 | 1.2095 |
| 3 | 1.0240 | 1.0238 | 1.0229 | 1.0217 | 1.0214 |
| 10 | 1.0039 | 1.0038 | 1.0030 | 1.0019 | 1.0016 |
| 30 | 1.0020 | 1.0019 | 1.0011 | 1.0000 | 0.9997 |

**Read across a row.** The error is the same at every aspect ratio for a given wake
in spans, and it is the row you are on that decides it. The published table was a
diagonal through this one: flow5's default put AR 10 at 3 spans and AR 40 at 0.75,
and the trend that produced was reported as a property of the solver.

## 3. The fix

`AnalysisSpec.wake_spans`, default **20**, written as
`LengthFactor = wake_spans × AR` because flow5's field is in MAC units
(`xflxmlwriter.cpp:349`). Measured after the change, on the same elliptic wings:

| AR | span efficiency | error |
|---|---|---|
| 10 | 1.0023 | 0.23 % |
| 20 | 1.0022 | 0.22 % |
| 30 | 1.0014 | 0.14 % |
| 40 | 1.0003 | 0.03 % |
| 50 | 1.0001 | 0.01 % |

Down from 2.4 %–28 %. The cost is a handful of wake panels; the mesh is untouched.

## 4. What it moves on real aircraft

| | before | after |
|---|---|---|
| `examples/hpa.yaml`, best L/D free air | 43.66 | **41.18** |
| `examples/hpa.yaml`, in ground effect at 2 m | 50.64 | 50.44 |
| ground-effect gain | +16.0 % | **+22.5 %** |
| `examples/rc-glider.yaml`, best L/D | 23.67 | **23.25** |
| PoC rectangular wing, CL_α | 0.08525 | 0.08516 |

Lift moves 0.1 %; induced drag moves by tens of percent on a slender wing. That split
is the signature of the whole thing, and it is why the earlier investigation's
observation that "lift is unaffected" pointed at the induced-drag calculation when it
should have pointed at the wake.

## 4a. Reproducing it

[`poc/case_k_wake.py`](../../poc/case_k_wake.py) builds the elliptic wing through the
frozen harness rather than through flow5ctl, so the finding does not rest on the
library it caused a change in:

```
cd poc && python3 case_k_wake.py
```

Its mesh is coarser than the runs above — 24 sections at 4 panels each rather than
100–120 spanwise — so the absolute values differ a little (1.2345 against 1.2103 at
30 × MAC). The structure is identical, which is the part that matters:

| wake (spans) | AR 10 | AR 20 | AR 30 | AR 40 | AR 50 |
|---|---|---|---|---|---|
| 0.75 | 1.2499 | 1.2396 | 1.2364 | 1.2345 | 1.2332 |
| 3 | 1.0279 | 1.0276 | 1.0267 | 1.0259 | 1.0252 |
| 10 | 1.0045 | 1.0044 | 1.0036 | 1.0029 | 1.0022 |
| 30 | 1.0023 | 1.0022 | 1.0014 | 1.0007 | 1.0000 |

Flat across each row, converging to 1.000 down the column.

## 4b. It also closes the rectangular-wing disagreement

The [mesh log](2026-09-04-induced-drag-and-the-mesh.md) left flow5 extrapolating to
a span efficiency of 0.984 on a rectangular AR 10 wing where AVL gave 0.9596 — 2.5 %
apart, and unexplained. Re-run at the 20-span wake:

| spanwise per semi-span | span efficiency |
|---|---|
| 10 | 1.0102 |
| 20 | 0.9854 |
| 40 | 0.9733 |
| 80 | 0.9674 |
| 120 | 0.9655 |
| ∞ (extrapolated) | **0.9617** |

Against AVL's **0.9596** — **0.2 % apart**. The two solvers agree on the rectangular
wing as well as the elliptic ones once they are asked the same question, and the
residual the mesh log could not account for was the same wake.

## 5. Why the earlier investigation missed it

The controls looked exhaustive — mesh density, spanwise distribution, chordwise
count, VLM1 against VLM2, two planforms, two solvers — and every one of them moved
the answer by less than half a percent. What none of them varied was the wake,
because flow5ctl did not expose it and the default was invisible: it appears in the
polar header as `Length = 30 x MAC` and was never read.

The aspect-ratio sweep also held the **span** fixed at 34 m and varied the chord.
That is the natural way to sweep AR, and it made the wake — measured in chords — the
one input that changed along with the aspect ratio. A sweep holding the chord fixed
instead would have shown a constant error and pointed straight at it.

**AVL being right made flow5 look wrong.** Two solvers disagreeing, with one of them
matching an exact answer, is strong evidence that the other is at fault — unless the
two are not being asked the same question. AVL's wake is a semi-infinite trailing
vortex; flow5's is a finite sheet whose length is a setting. That difference is the
whole result.
