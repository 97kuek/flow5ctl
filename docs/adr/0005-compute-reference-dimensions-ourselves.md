# ADR-0005 — Always compute reference dimensions and emit CUSTOM

**Status:** Accepted · 2026-09-03

## Context

A flow5 plane polar needs a reference area, span and chord to non-dimensionalise
its results. The XML offers `PLANFORM`, `PROJECTED`, `CUSTOM` and `AUTO`.

`PLANFORM` and `PROJECTED` are supposed to derive the values from the plane geometry.
**In script mode they do not.** The derivation code lives in
`flow5-app/modules/script/xflexecutor.cpp:278-424`, which serves the interactive
batch dialog; the script executor path never calls it. The polar keeps zeros and the
analysis fails:

```
Checking plane and polar data
   error: reference chord length is 0m
   error: reference span length is 0m
   error: reference area is 0m²
Panel analysis completed ... Errors encountered
```

This was hit on the first real run during the feasibility spike, and it is not
documented anywhere upstream.

## Decision

flow5ctl **always** computes planform area, projected area, span, projected span and
mean aerodynamic chord from the design, and **always** writes
`Reference_Dimensions = CUSTOM` with explicit values.

`PLANFORM` and `PROJECTED` are never emitted. If a user's imported XML contains
them, we replace them and say so.

MAC is computed by integrating chord² over the span across all sections, not from
the two-parameter taper formula, so that wings with breaks are correct.

## Consequences

- Correct results instead of a cryptic failure. This single behaviour is a large part
  of the tool's justification.
- The geometry module becomes load-bearing and needs real tests: known planforms
  (rectangular, simple taper, multi-break, with dihedral) against hand-computed values.
- Our numbers must match what flow5's GUI would compute, or users comparing against
  their own GUI sessions will see different coefficients for the same aircraft.
  Validate against a GUI-exported polar during Phase 1.
- If upstream fixes the script path, nothing breaks — `CUSTOM` stays correct.
