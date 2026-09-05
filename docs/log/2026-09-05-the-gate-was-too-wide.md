# The reference-height gate was fifteen times too wide

2026-09-05

## What was wrong

`analyze` reports a static margin. When the CG sits at a different height from the
wing's own mean height, `-dCm/dCL` about that CG is not the classical static margin:
as alpha rises the resultant force tilts and its line of action moves relative to the
CG, adding a term that has nothing to do with pitch stiffness in the classical sense.
The code knows this and re-runs the analysis with the moment referenced to the wing's
mean height to separate the two.

It only did so when the offset exceeded **0.05 MAC**. Below that it declared the
number classical and reported it to four decimals.

That threshold was never measured. It was chosen to avoid the cost of a second pass.

## What it admits

One analysis per row on `examples/rc-glider.yaml` (MAC 0.190 m, reference height
0.0354 m), everything but the CG height held fixed:

| CG height offset (MAC) | reported static margin | error against the classical value |
|---|---|---|
| 0.000 | 0.0976 | — |
| 0.010 | 0.0961 | −0.0015 |
| 0.025 | 0.0938 | −0.0038 |
| 0.049 | 0.0902 | −0.0074 |
| −0.049 | 0.1051 | **+0.0075** |

Linear, at about **0.151 margin points per MAC of offset**.

The last row is the dangerous one. A CG *below* the wing's mean height — which is
where a pilot sits — makes the margin look **bigger** than it is. At the old gate
that was **+0.75 points of margin the aircraft does not have**.

`advisor/stability.py` calls any positive margin stable:

> the static margin is +0.2 % MAC and the preset for this class expects 5–15 %.
> **It is stable**, but with less margin than intended.

So an aircraft whose true classical margin was −0.005 could be reported at +0.0025
and described as stable. It diverges in pitch.

## Why the existing cross-check did not catch it

`summary.py` already compares the computed margin against the one flow5 prints in the
polar header. Its tolerance is `max(0.01, |margin| × 0.25)` — for a margin near 0.09
that is 0.0225, three times the error the gate admitted. It could not have fired.

The neutral point is untouched by the offset: 0.09 in every row above. `(XNP − XCG)/MAC`
is therefore identical across the whole table while the slope-derived margin moves by
1.5 points. Two independent routes to the same quantity disagreed, and nothing looked.

## The fix

The gate is now **0.003 MAC**, which holds the error below 0.0005 at the measured
sensitivity — under the last digit reported, so the approximation cannot change a
figure the reader sees. The constant lives in one place, `flow5.summary`, because it
was written out twice and one copy would eventually have been updated alone.

The sensitivity coefficient will differ between aircraft, so 0.003 is not a bound. It
is a threshold small enough that the term cannot change the answer at the precision
the answer is given in.

## How it was found

Codex, asked for an adversarial second opinion on the stability code, described the
path in the abstract: below the gate, `classical_margin` is set true, the force-tilt
value is passed to the advisor as the classical margin, and a positive-but-small
value is reported as stable. It did not have a number for how large the term is.

The measurement above is that number. It is the same shape of mistake as
[the wake](2026-09-04-the-wake-was-too-short.md): a threshold picked for cost,
never measured, and wrong in the direction that flatters the aircraft.
