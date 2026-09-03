# 2026-09-03 — Feasibility spike

**Question:** Can an AI agent drive flow5 to design and analyse an aircraft, without
a human touching the GUI?

**Answer:** Yes. Verified end to end on this machine.

Environment: macOS 15 (Darwin 25.5.0), universal binary at
`/Applications/flow5.app/Contents/MacOS/flow5`, installed via Homebrew cask.

> **Two corrections, from the [verification round](2026-09-03-poc-verification.md):**
> 1. The version recorded here as 7.70 was read from the macOS bundle's
>    `Info.plist`. The program itself reports **7.57**, and so does Homebrew.
>    Everything in this log was produced by **flow5 7.57**.
> 2. "The exit code is always 0" (below) is wrong. It is 0 for every *handled*
>    condition, but a **crash gives exit 139**. Both the exit code and stdout must
>    be checked.

---

## What was done

### 1. Established what flow5 exposes

`flow5 --help` reports a `-s, --script <file>` option: "Runs the script file".
Bundle contents confirm the shape of the program — Qt 6, and
`libflow5-lib`, `libflow5-io-lib`, `libXFoil`, plus OpenCASCADE and gmsh for meshing
and CAD import.

Binary strings confirmed a batch pipeline built around XML: `XflScriptExec`,
`xflscript`, directory keys for plane/foil definitions and analyses, and output
switches for polars, operating points, Cp and STL.

### 2. Established that flow5 is open source

The application reports itself as GPL-3.0, and the source is public at
[techwinder/flow5](https://github.com/techwinder/flow5) — 221 stars, last pushed
2026-07-01. This changed the plan materially: **the XML schemas do not have to be
guessed.** They were read from:

- `flow5-app/modules/script/xflscriptreader.cpp` — the full script grammar
- `flow5-io-lib/xml/xplane/xmlplanewriter.cpp`, `xmlwingwriter.cpp`, `xflxmlwriter.cpp` — plane definition
- `flow5-io-lib/xml/xplane/xmlplanepolarreader.cpp`, `xmlplanepolarwriter.cpp` — analysis definition
- `flow5-io-lib/xml/xml_globals.cpp` — enum spellings

The repository also contains `API_examples/` — eight C++ programs using
`flow5-lib` directly. Noted as a future option; see
[ADR-0001](../adr/0001-drive-flow5-via-the-xml-script-interface.md).

### 3. Ran a real analysis

Built from scratch, with no GUI involvement:

- `foils/NACA2412.dat` — 161 points, generated from the NACA 4-digit equations
- `planes/testglider.xml` — tapered main wing (1.5 m span, 0.18 → 0.12 m chord,
  3° dihedral, −1.5° washout) plus an elevator, one 0.4 kg point mass
- `analyses/t1_vlm.xml` — T1 fixed-speed polar, VLM2, 10 m/s, inviscid
- `script.xml` — wiring the directories together, CSV output, oppoints and
  derivatives enabled

Then: `flow5 -p -s script.xml`

### 4. Result

```
Adding planes from the .xml files
   added the plane: TestGlider from file testglider.xml
   the analysis t1_vlm has been added for TestGlider
   Made 1 valid analysis pairs (plane, polar) to run
Launching plane analysis: TestGlider / t1_vlm
Panel analysis completed successfully
```

```
 α (°)   CL          CD_induced    Cm
 -1      0.043324    0.00016036    -0.060815
  0      0.13906     0.00083828    -0.053932
  3      0.42559     0.0067854     -0.035674
  8      0.89711     0.029335      -0.013633

XNP = 0.09 m   Static margin = -7.39598
```

**Runtime: 0.5 s** wall clock, including process startup, for 11 α points.

**The physics is right.** CL slope 0.0955 /deg = 5.47 /rad, which is what
lifting-line theory gives for AR ≈ 10. Cm rises with α — this aircraft is
longitudinally unstable, correctly reported, because the CG was placed at 0.10 m
behind a neutral point at 0.09 m. The tool caught a real design error on its first run.

Outputs produced: polar CSV, one CSV per operating point, a `.fl5` project openable
in the GUI, and a full log.

---

## What went wrong on the way (all now documented)

These are the failures that justify building a domain layer rather than a thin wrapper.

1. **Root element rejected.** `<xflscript>` without `version="1.0"` and a
   `<!DOCTYPE xflscript>` fails with "The file is not an xml readable script".

2. **`<T12_Range>` is a flat text element, not a container.** Writing
   `<T12_Range><Alpha>…</Alpha></T12_Range>` aborts the *entire* script with
   `Expected character data. line 33 column 15`. `Alpha` is a sibling, not a child.

3. **`Reference_Dimensions = PLANFORM` silently produces zeros.**

   ```
   error: reference chord length is 0m
   error: reference span length is 0m
   error: reference area is 0m²
   Panel analysis completed ... Errors encountered
   ```

   Cause, found by reading the source: the code that derives reference dimensions
   from geometry (`xflexecutor.cpp:278-424`) belongs to the *interactive* batch
   dialog and is never called from the script path. Fixed by computing area, span
   and MAC by hand and emitting `CUSTOM`. This became
   [ADR-0005](../adr/0005-compute-reference-dimensions-ourselves.md).

4. **The exit code is 0 for every handled condition**, including for a script that
   was rejected outright and ran nothing. Success has to be parsed from stdout
   markers. (A crash is the exception — see the correction above.)

5. **`Compute_derivatives` on a T1 polar returns nonsense.** The run reported lateral
   eigenvalues of `5.995e+51` and `2.836e+15`. Stability requires a T7 polar.
   An agent reading that output uncritically would report a fabricated result.

6. **Operating-point filenames are hostile.** `" 3_00°_10_00m_s.csv"` — leading
   space, degree sign, decimal points replaced by underscores. Not shell-globbable.

7. **Unknown elements are silently skipped.** A misspelled tag does not error; it
   does nothing. Validation has to be ours, before the file is written.

Each of these would have cost an unaided agent several failed runs, and #3 and #5
would have produced *plausible-looking wrong answers* rather than errors.

---

## Conclusions carried into the design

- The script interface is sufficient and fast. → [ADR-0001](../adr/0001-drive-flow5-via-the-xml-script-interface.md)
- The value is in the domain layer, not the invocation. → [ARCHITECTURE.md](../ARCHITECTURE.md)
- Reference dimensions must be ours. → [ADR-0005](../adr/0005-compute-reference-dimensions-ourselves.md)
- Physics guardrails are mandatory, not decorative. → [DESIGN-GUIDE.md](../DESIGN-GUIDE.md)
- Everything here is pinned to 7.70 and must be re-verified. → [ADR-0007](../adr/0007-flow5-version-compatibility.md)

## Not covered by this spike

Viscous analysis with a 2D polar mesh, fuselages, T7 stability output, control
surfaces, STL export, and any platform other than macOS. Listed as open items in
[FLOW5-INTERFACE.md §8](../FLOW5-INTERFACE.md).

## Artifacts

The working files live in the session scratchpad
(`…/scratchpad/spike/`) and should be promoted into `tests/fixtures/` during Phase 1
as the first golden-file test.
