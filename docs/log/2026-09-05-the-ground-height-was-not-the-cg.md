# The ground height was not the CG's, and not the wing's either

2026-09-05

## What the guide said

> `ground_height` = height of the **CG above the water**, positive.

## What flow5 does

flow5 mirrors the influence points across a plane at **`z = -Ground_Height`, in the
model's own coordinates**. It does not infer the CG, and it does not infer the mean
height of the wing. flow5ctl writes the user's number into `<Ground_Height>`
unchanged, so what the number actually sets is the height of the design's **z = 0
datum**.

For an aeroplane whose datum happens to sit at the wing, the distinction is academic.
For a human-powered aircraft it is not, because the pilot hangs well below the wing
and the CG follows.

## How far apart they are

`examples/hpa.yaml`, 34 m span, with `ground_effect_height: 2.0`:

| | height above the ground plane | h/b |
|---|---|---|
| the z = 0 datum — what the number sets | 2.000 m | 0.0588 |
| the wing's chord-weighted mean height (`mac_z` = +0.2593) | **2.259 m** | **0.0664** |
| the CG (`cg_z` = −0.3913) | 1.609 m | 0.0473 |

The CG is **19.6 % lower** than the declared height and the wing **13 % higher**. They
are 0.65 m apart — a third of the declared 2.0 m. Ground effect is strongly non-linear
in h/b at these heights, so which one a reader has in mind changes what they expect.

The guide's sentence was wrong twice over: it is not what flow5 does, and the CG is
not the physically relevant height anyway. Ground effect depends on how high the
*lifting surface* is.

## What this does and does not change

**It does not change the measured percentages.** The +22.5 % gain on the HPA is
correct for the geometry that was analysed — a wing whose mean height is 2.26 m. The
solver was given a consistent problem and solved it. What was wrong was the label on
the input, and therefore what a reader would think the output applied to.

That is worth stating plainly because the instinct on finding this is to assume every
ground-effect number in the repository is wrong. They are not. A reader who wanted the
*wing* at 2.0 m should have written 1.74, and would have got a different (smaller)
gain; a reader who wrote 2.0 meaning "the aircraft is about two metres up" got an
answer for 2.26 m at the wing.

## The fix

The guides say what the number is, in both languages, with the table above.
`analyze --compare-ground` now reports all three heights and both h/b values, so the
gain can be read against the height it belongs to rather than against the one that was
typed. The semantics of `ground_height` are unchanged: redefining it would silently
move every number anyone has already published from this tool, which is a worse
failure than a wrong label.

## How it was found

A Codex review of the ground-effect modelling. It got as far as

> flow5 reflects influence points across a plane at `z = -Ground_Height`; it does not
> infer CG or mean-wing height. The reviewed code forwards the user number unchanged

before the account hit its usage limit. The measurements above are this project's,
prompted by that sentence.

The second question put to that review — whether +22.5 % at h/b ≈ 0.06 is a defensible
magnitude against Wieselsberger and Hoerner — was never answered. It is still open, and
it is the more important half. See [REVIEW-BACKLOG.md](../REVIEW-BACKLOG.md).
