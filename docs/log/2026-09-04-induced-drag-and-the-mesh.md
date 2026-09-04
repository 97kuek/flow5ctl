# 2026-09-04 — Span efficiency above 1 was the mesh, not the physics

**Question:** a rectangular wing came back with a span efficiency of 1.008–1.012.
For a planar wing 1.0 is the elliptic limit, so the number was impossible and
[DESIGN-GUIDE.md](../DESIGN-GUIDE.md) carried it as evidence that induced drag from
flow5 is only good to about ±5 %. Is that the right conclusion?

**Answer:** no. The impossible value is a **spanwise mesh artefact** and it goes
away with refinement. Chordwise resolution has nothing to do with it. Induced drag
is still uncertain at the few-percent level, but for a different and much more
useful reason, and the mesh part of it is now something a user can control.

Environment: macOS, flow5 7.57, inviscid VLM2 at α = 5°, span efficiency computed as
`e = CL² / (π · AR · CD_induced)` from the polar's own columns. The inviscid run was
checked first: `CD_viscous` is 0.0 and `CD` equals `CD_induced` exactly, so the
column means what it says.

## 1. Refining the span makes it possible again

Rectangular, AR 10 (S = 0.4 m², b = 2 m — the PoC case A wing), COSINE spanwise:

| spanwise panels per semi-span | e (UNIFORM) | e (COSINE) |
|---|---|---|
| 10 | **1.0354** | — |
| 20 | **1.0094** | **1.0135** |
| 40 | 0.9968 | 0.9989 |
| 80 | 0.9906 | 0.9917 |
| 120 | 0.9886 | 0.9892 |

Monotone, and linear in 1/N to three meshes: the differences give a slope of 0.497,
0.492 and 0.494, so extrapolating to an infinitely fine mesh gives **e → 0.984**
from all three of the 40, 80 and 120-panel results independently.

Repeated at human-powered-aircraft aspect ratio — rectangular, b = 34 m, c = 0.85 m,
AR 40 — the same thing happens:

| spanwise panels per semi-span | e |
|---|---|
| 20 | **1.0081** |
| 40 | 0.9906 |
| 80 | 0.9826 |
| 120 | 0.9801 |

Extrapolated: **e → 0.975**. So this is not a property of one test wing.

## 2. Chordwise panels do not matter at all

Same wing, 120 spanwise, varying only the chordwise count:

| chordwise panels | e |
|---|---|
| 7 | 0.98861 |
| 13 | 0.98856 |
| 21 | 0.98852 |

Four decimal places of agreement. Induced drag is set by the trailing vortex sheet,
which is a spanwise object; spending panels on the chord to improve it is wasted.

## 3. The method is not the cause

Same wing and mesh through flow5's own methods:

| method | 40 spanwise | 120 spanwise |
|---|---|---|
| VLM1 | 0.9987 | 0.9890 |
| VLM2 | 0.9989 | 0.9892 |
| LLT | flow5 reported errors on every point | — |

VLM1 and VLM2 agree to four decimals, so the horseshoe/ring distinction is not it.
flow5's own LLT would not run this case at all.

## 4. flow5 computes induced drag on the Trefftz plane [src]

`flow5-lib/analysis3d/planetask.cpp:1758` calls `m_pP4A->trefftzDrag(...)` per wing
(and `m_pP3A->trefftzDrag` for triangle methods). So this is a **far-field** value,
not the near-field pressure integration that is known to under-read in a VLM. The
usual explanation for a too-low VLM induced drag does not apply here.

## 5. Against classical lifting line

Prandtl lifting line solved by Glauert's series for the same planform, with the
section lift slope at 2π per radian, which is what a VLM's flat panels reproduce.
The solver was verified first: an elliptic planform returns **e = 1.000000** at
AR 6, 10 and 20, and a rectangular AR 6 wing returns 0.954, the textbook value.

| | flow5 (extrapolated) | lifting line |
|---|---|---|
| rectangular AR 10 | 0.984 | 0.921 |
| rectangular AR 40 | 0.975 | 0.791 |

They do not agree, and the disagreement grows with aspect ratio. Comparing the
normalised spanwise loading at AR 10 shows where it lives — flow5's loading is
closer to elliptic everywhere, and the gap is concentrated at the tip:

| η = y/(b/2) | flow5 | lifting line | elliptic |
|---|---|---|---|
| 0.10 | 1.1390 | 1.1104 | 1.2669 |
| 0.50 | 1.0870 | 1.0705 | 1.1027 |
| 0.85 | 0.8297 | 0.8741 | 0.6707 |
| 0.97 | 0.4475 | 0.5178 | 0.3095 |
| 0.995 | 0.2021 | 0.2351 | 0.1272 |

(each normalised to unit area over the semi-span; the flow5 curve integrates to
0.9973 against its own CL, which is a useful check on the strip table in itself.)

**This does not settle which is right, and it should not be reported as if it did.**
The lifting-line assumption is a single bound vortex line, which is least reliable
exactly at the tip, and it degrades as aspect ratio rises — its AR 40 answer of
0.791 is not a figure any human-powered aircraft team would recognise. flow5's
answer is the more believable one. But "the less believable model disagrees" is not
evidence of correctness, and an independent third method (AVL, or a panel code) is
what would close this.

## What changed as a result

- [DESIGN-GUIDE.md](../DESIGN-GUIDE.md) §1 no longer says the span efficiency is
  impossible. It says the mesh has to be refined before the number means anything,
  and gives the table.
- `analyze` warns when the main wing has fewer than 25 spanwise panels per
  semi-span, because that is where induced drag is optimistic by around 3 % and the
  reported span efficiency can exceed 1.
- Induced drag is still quoted as good to a few percent, not exactly — but now
  because two methods disagree at the tip, not because our own number was impossible.
