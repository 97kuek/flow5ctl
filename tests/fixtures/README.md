# Test fixtures

Real flow5 7.57 output, kept small and committed on purpose: these files are the
only way to pin the parser against the traps documented in
[FLOW5-INTERFACE.md §5](../../docs/FLOW5-INTERFACE.md).

| File | The trap it pins |
|---|---|
| `polar_t1_rectwing.csv` | 57 fixed-width columns, no commas, first data row welded onto the header line |
| `polar_t2_single_point.csv` | a polar whose only row is the one embedded in the header — no standalone data line exists |
| `polar_t7_inf.csv` | `inf` in the `Roll Damping` column, which a strict numeric filter drops silently |
| `polar_t5_beta.csv` | a sideslip sweep; α constant, β varying |
| `polar_t5_finaft.csv` | one HPA, fin 6.0 m behind the CG — laterally stable |
| `polar_t5_finfwd.csv` | the same fin 1.5 m *ahead* of the CG — yaw-unstable |
| `polar_t5_anhedral.csv` | the same HPA with −6° anhedral and no fin — roll-unstable |

The last three are one control experiment. Moving the fin from behind the CG to in
front leaves `dCY/dβ` almost unchanged and flips `dCn/dβ`, which is how flow5's
lateral sign convention was established: only a moment-arm sign change can do that,
so the aft-fin case — stable by construction — is the negative one. flow5 writes
both lateral moment coefficients opposite the textbook convention.
| `oppoint_strips.csv` | the spanwise strip table, and line 2 naming the polar an op-point file really belongs to |
| `foilpolar_csv.csv` | a foil polar that IS comma-separated |
| `foilpolar_xfoil.txt` | the same data in XFoil text format, the shape that can be re-imported |

Regenerate with the cases in [`poc/`](../../poc) if flow5's output ever changes;
`docs/FLOW5-INTERFACE.md` says which case produced which file.
