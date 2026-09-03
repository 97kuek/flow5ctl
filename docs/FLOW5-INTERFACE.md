# flow5 batch interface — verified reference

Everything here was verified against **flow5 7.57** on macOS 15 (Darwin 25.5),
either by executing it or by reading the GPL-3.0 sources at
[techwinder/flow5](https://github.com/techwinder/flow5).

- **[run]** — produced by running flow5. Reproduce with the harness in [`poc/`](../poc).
- **[src]** — read from the named upstream source file.

Anything not marked either way is not established.

> The flow5 author states the API and script XML format are **still subject to
> change** until roughly end of 2026. This document is pinned to 7.57 and must be
> re-verified on upgrade — [ADR-0007](adr/0007-flow5-version-compatibility.md).

---

## 0. Version detection — do not trust the app bundle

**[run]** On this machine the macOS bundle's `Info.plist` reports
`CFBundleShortVersionString = 7.70`, but the program itself reports **7.57**, and so
does Homebrew:

```
$ /Applications/flow5.app/Contents/MacOS/flow5 --version
flow5 flow5 v7.57
$ /usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" /Applications/flow5.app/Contents/Info.plist
7.70
$ brew list --cask --versions | grep flow5
flow5 7.57
```

**Detect the version from `flow5 --version` or from the first line of the run log
(`flow5 v7.57`), never from `Info.plist`.** Note the `--version` output repeats the
application name — parse the `v<major>.<minor>` token, not the whole string.

---

## 1. Command line

**[run]**

```
Usage: flow5 [options]
Options:
  -h, --help                     Displays help on commandline options.
  -v, --version                  Displays version information.
  -o, --opengl <OpenGL_version>  Launches with the specified OpenGL version.
  -p, --progress                 Show progress during script execution.
  -s, --script <file>            Runs the script file
  -t, --trace <file>             Runs the program in trace mode.
```

`flow5 -s script.xml` **[run]**:

- runs **without opening a GUI window** and exits on its own
- writes a structured progress log to **stdout**; `-p` adds per-analysis progress
- an incidental `QFile::copy: Empty or null file name` line may appear; it is benign

### Exit codes

| Exit | Meaning |
|---|---|
| `0` | Script ran to completion **or** was rejected outright **or** the solver failed. Not a success signal. |
| `139` / signal 11 | **SIGSEGV — flow5 crashed.** Observed reproducibly, see §7. |

**[run]** So: a non-zero exit means a crash, and `0` means nothing. Success must be
determined by parsing stdout (§6) *and* the exit code must still be checked for
crashes. Both are required.

macOS binary: `/Applications/flow5.app/Contents/MacOS/flow5`. On Linux/Windows the
executable is `flow5` on PATH. flow5 is a Qt GUI application run headless, not a
separate CLI binary; the bundled Qt ships only the `cocoa` platform plugin on macOS,
so `QT_QPA_PLATFORM=offscreen` is **not** available there.

---

## 2. The script file (`xflscript`)

**[src]** `flow5-app/modules/script/xflscriptreader.cpp:133`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0"> ... </xflscript>
```

The reader requires `version >= "1.0"` as a **string** comparison. Element names are
matched **case-insensitively**. Unknown elements are silently skipped
(`skipCurrentElement()`) — *a typo does not raise an error, it does nothing.*

### 2.1 Structure

```
xflscript
├── Metadata
│   ├── make_project_file          bool   — see §2.2, affects the OUTPUT PATH
│   ├── project_file_name          text
│   ├── load_project_file          text   — see §8
│   ├── polar_text_output_format   "csv"  — see §5, does NOT produce CSV for planes
│   ├── Double_Precision           bool
│   ├── MultiThreading { Allow_Multithreading, Thread_Priority, max_threads }
│   └── Directories
│       ├── output_dir
│       ├── foil_files_dir              — .dat airfoil coordinates
│       ├── foil_analysis_xml_dir
│       ├── foil_polars_dir             — .plr binary foil polars
│       ├── xfoil_polars_dir            — .txt XFoil polars (this is the useful one)
│       ├── plane_definition_xml_dir
│       ├── plane_analysis_xml_dir
│       ├── boat_definition_xml_dir / boat_analysis_xml_dir
│       └── recursive_scan         bool
├── foil_analysis                  — 2D / XFoil       ⚠ NEVER together with Plane_analysis, §7
├── Plane_analysis                 — 3D aircraft
└── Boat_analysis                  — sails (out of scope for flow5ctl)
```

`Thread_Priority` **[src]**: `Idle|Lowest|Low|Normal|High|Highest|TimeCritical`.

### 2.2 Output path depends on `make_project_file` — [run]

- `make_project_file = true` with `project_file_name = X` →
  output goes to `<output_dir>/X/`, deterministically.
- `make_project_file = false` → output goes to a **timestamped** directory
  `<output_dir>/script_<yyMMdd_hhmmss>/`.

**Always set `make_project_file` and `project_file_name`** so the output path is
predictable. Otherwise you must discover the directory after the fact.

### 2.3 `Plane_analysis`

```
Plane_analysis
├── Plane_Analysis_Output
│   ├── make_polars_text_file      bool
│   ├── make_oppoints              bool
│   ├── make_oppoints_text_file    bool
│   ├── export_oppoint_Cp          bool   — [run] verified; appends Cp to oppoint files
│   ├── export_stl_mesh            bool   — [run] verified; writes <output>/STL/<Plane>.stl
│   └── Compute_derivatives        bool   — see §9
├── Foil_Dat_Files / Foil_File_Name              (repeatable)
├── Foil_Polar_Files / Polar_File_Name           (repeatable)
├── Plane_Definition_Files { Process_All_Files, Plane_File_Name }
├── Plane_Analysis_Files   { Process_All_Files, Analysis_File_Name }
└── Plane_Analysis_Data
    ├── Alpha                      "min, max, inc"  — sets BOTH T12 and T3
    ├── Control                    "min, max, inc"  — sets BOTH T6 and T7
    ├── T12_Range / T3_Range / T5_Range / T6_Range / T7_Range / T8_Range
    └── Viscous_Loop { Enable, Relax_Factor, Init_Virtual_Twist, Alpha_Precision, Max_Iterations }
```

> **Trap — range elements are flat text, not containers.** **[run]**
> `<T12_Range>-2.0, 8.0, 1.0</T12_Range>` is correct.
> `<T12_Range><Alpha>…</Alpha></T12_Range>` aborts the whole script with
> `Expected character data.` `Alpha` is a *sibling* of `T12_Range`, not a child.
> **[src]** `xflscriptreader.cpp:544-640`.

### 2.4 `foil_analysis`

```
foil_analysis
├── Foil_Files / Foil_File_Name
├── Analysis_Files { Process_All_Files, Analysis_File_Name }
├── Batch_Analysis_Data
│   ├── Polar_Type
│   ├── Forced_Top_Transition / Forced_Bottom_Transition
│   └── Batch_Range
│       ├── Reynolds   "v1, v2, v3, …"   ← a LIST: one polar per value
│       ├── NCrit      "v1, v2, …"       ← padded to Reynolds' length with 9
│       └── Mach       "v1, v2, …"       ← padded with 0
├── OpPoint_Range        ← the points to COMPUTE
│   ├── Alpha          "min, max, inc"
│   ├── Cl / Reynolds / Control
│   ├── Spec_Alpha     bool
│   └── From_Zero      bool
├── Options { Max_XFoil_Iterations, Repanel_Foils, Foil_Panels }
└── Output { make_polars_bin_file, make_polars_text_file, make_oppoints }
```

> **Trap — `Batch_Range/Alpha` is parsed but never used.** **[run]** The α sweep must
> go in **`OpPoint_Range/Alpha`**. Put it in `Batch_Range` and the run "completes
> successfully" in 0.4 s having produced **empty polars** (267-byte header-only files)
> — a silent no-op, not an error. **[src]** the executor consumes `m_AlphaRange`
> (set by `OpPoint_Range`), not `m_Alpha` (set by `Batch_Range`):
> `xflscriptexec.cpp:188`.

> **`make_polars_bin_file = true` produced no `.plr` files** **[run]**. Use the text
> output and the `xfoil_polars_dir` route instead (§4).

---

## 3. Plane definition (`xflplane`)

**[src]** `flow5-io-lib/xml/xplane/xmlplanereader.cpp`, `xmlplanewriter.cpp`,
`flow5-io-lib/xml/xflxmlwriter.cpp`. Root name must be `xflplane` with **exactly**
`version="1.0"` (strict equality, unlike the script reader).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE flow5>
<xflplane version="1.0">
  <Units>
    <meter_to_length_unit>1.0</meter_to_length_unit>
    <kg_to_mass_unit>1.0</kg_to_mass_unit>
  </Units>
  <Plane>
    <Name>…</Name>
    <Description>…</Description>
    <Inertia>
      <Point_Mass>
        <Tag>pilot</Tag><Mass>68.0</Mass>
        <coordinates>0.35, 0.00, -0.30</coordinates>
      </Point_Mass>
    </Inertia>
    <body> … </body>              <!-- optional fuselage, §3.2 -->
    <wing>
      <Name>Main Wing</Name>
      <Type>MAINWING</Type>       <!-- MAINWING | ELEVATOR | FIN | OTHERWING -->
      <Position>0.0, 0.0, 0.0</Position>
      <Rx_angle>0.0</Rx_angle>
      <Ry_angle>0.0</Ry_angle>    <!-- incidence -->
      <Symmetric>true</Symmetric>
      <Two_Sided>false</Two_Sided>
      <Tip_Strips>0</Tip_Strips>
      <Sections>
        <Section>
          <y_position>0.000</y_position>
          <Chord>0.240</Chord>
          <xOffset>0.000</xOffset>
          <Dihedral>3.0</Dihedral>
          <Twist>0.0</Twist>
          <x_number_of_panels>13</x_number_of_panels>
          <x_panel_distribution>COSINE</x_panel_distribution>
          <y_number_of_panels>14</y_number_of_panels>
          <y_panel_distribution>COSINE</y_panel_distribution>
          <Left_Side_FoilName>AG35</Left_Side_FoilName>
          <Right_Side_FoilName>AG35</Right_Side_FoilName>
        </Section>
        <!-- … y_position strictly increasing; last section is the tip … -->
      </Sections>
    </wing>
  </Plane>
</xflplane>
```

`Dihedral`, `Twist` and `y_number_of_panels` on a section describe the panel
**outboard** of it, so the tip section's dihedral/twist are ignored and its
`y_number_of_panels` should be 1.

Enumerations **[src]** `xml_globals.cpp`, **[run]** binary strings:

| Field | Values |
|---|---|
| wing `Type` | `MAINWING`, `ELEVATOR`, `FIN`, `OTHERWING` |
| panel distribution | `UNIFORM`, `COSINE`, `SINE`, `INV_SINE`, `TANH`, `INV_EXP` |
| body `Type` | `NURBS`, `FLATPANELS` |

> **Trap — `Type=FIN` does not make a fin vertical.** **[src]** flow5 lays a fin's
> sections along `y` like any other wing; the type only affects bookkeeping. A fin
> becomes vertical when it is **rolled**, which the upstream API example does
> explicitly:
>
> ```cpp
> pPlaneXfl->setRxAngle(&fin, -90.0);
> fin.setClosedInnerSide(true);   // it is NOT connected to a fuselage
> ```
> (`API_examples/PlaneRun1/PlaneRun1.cpp:316`)
>
> So a fin written with `Rx_angle = 0` is built as a **second horizontal tail**.
> **[run]** Measured on a reconstructed 30 m aircraft: the phantom surface moved the
> neutral point **35 % MAC aft** (wing + elevator 55.1 % MAC; adding the "fin"
> 90.4 %), and every sideslip result was meaningless because flow5 never saw a
> vertical surface. With `Rx_angle = -90` the fin contributes nothing to pitch, as it
> should.
>
> Nothing in flow5's output hints at this. A horizontal surface is still symmetric in
> sideslip, so a T5 polar looks entirely reasonable — CL falls symmetrically with β —
> on an aircraft that has no vertical tail at all.
>
> Also write `Closed_Inner_Side = true` for a fin with no fuselage to close against.

### 3.1 Airfoil resolution

Airfoils are referenced **by name**, and the name must match a foil the script has
already loaded via `Foil_Dat_Files`. **The name of a foil loaded from a `.dat` file
is the string on its first line, not the filename.** A plane whose foils cannot be
resolved is silently discarded:
`foils not found ...discarding this plane`.
`Left_Side_Foil_File` / `Right_Side_Foil_File` reference `.dat` filenames instead.

### 3.2 Fuselage — [run] verified

A NURBS pod works end to end. **[src]** element names from `xflxmlreader.cpp`:

```xml
<body>
  <Name>Pod</Name>
  <Type>NURBS</Type>
  <Position>-0.15, 0.0, 0.0</Position>
  <x_panels>12</x_panels>
  <hoop_panels>10</hoop_panels>
  <Inertia><Volume_Mass>0.15</Volume_Mass></Inertia>
  <NURBS>
    <u_degree>3</u_degree>
    <v_degree>3</v_degree>
    <frame>
      <Angle>0</Angle>
      <x_panels>2</x_panels>
      <Position>0.0, 0.0, 0.0</Position>
      <point>0.0000, 0.0000, 0.0300</point>   <!-- top -->
      <point>0.0000, 0.0212, 0.0212</point>   <!-- y >= 0 half only -->
      <point>0.0000, 0.0300, 0.0000</point>
      <point>0.0000, 0.0212, -0.0212</point>
      <point>0.0000, 0.0000, -0.0300</point>  <!-- bottom -->
    </frame>
    <!-- more frames, increasing x -->
  </NURBS>
</body>
```

Frames define the **y ≥ 0 half** section, ordered top to bottom, and are mirrored.
Also accepted: `Panel_Stripes/stripe_N` (flat-panel bodies), `uAxis`, `vAxis`,
`uEdgeWeight`, `vEdgeWeight`, `Bunch_amplitude`, `Bunch_distribution`.

**[run]** Measured effect of adding the pod above to a 3 m glider, T1 viscous at
10 m/s: CL at α=6° fell 0.7229 → 0.6071 and L/D 24.50 → 22.65. The run log gains
`Calculating on-body pressure coefficients`.

### 3.3 Flaps and control surfaces are NOT reachable — [src]

There are **no flap or hinge elements in the wing/plane XML**: `xflxmlwriter.cpp`
`writeWing()` emits only the section fields listed above, and `xflxmlreader.cpp`
contains no `flap` handling. Flaps in flow5 are a property of the **Foil** object
(TE/LE hinge), which a `.dat` file cannot carry.

Consequence: **T6 control polars and flap deflections cannot be driven through the
XML script interface.** They would require a `.fl5` project prepared in the GUI —
and §8 shows that route cannot be paired with new analyses either. Out of reach for
flow5ctl v1.

---

## 4. Analysis definition (`xflPlanePolar`)

**[src]** `xmlplanepolarreader.cpp`, `xmlplanepolarwriter.cpp`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE flow5>
<xflPlanePolar version="1.0">
  <Units>
    <meter_to_length_unit>1.0</meter_to_length_unit>
    <kg_to_mass_unit>1.0</kg_to_mass_unit>
    <ms_to_speed_unit>1.0</ms_to_speed_unit>
  </Units>
  <Polar>
    <Polar_Name>cruise</Polar_Name>
    <Plane_Name>Glider</Plane_Name>      <!-- MUST equal the plane's <Name> -->
    <Type>FIXEDSPEEDPOLAR</Type>
    <Method>VLM2</Method>
    <Thin_Surfaces>true</Thin_Surfaces>
    <Reference_Dimensions>
      <Reference_Dimensions>CUSTOM</Reference_Dimensions>
      <Reference_Area>0.5622</Reference_Area>
      <Reference_Span_Length>3.0</Reference_Span_Length>
      <Reference_Chord_Length>0.1935</Reference_Chord_Length>
      <Include_Other_Wing_Area>false</Include_Other_Wing_Area>
    </Reference_Dimensions>
    <Viscous_Analysis>
      <Is_Viscous_Analysis>true</Is_Viscous_Analysis>
      <XFoil_OnTheFly>false</XFoil_OnTheFly>
      <From_CL>false</From_CL>
      <NCrit>9.0</NCrit>
      <XTrTop>1.0</XTrTop><XTrBot>1.0</XTrBot>
    </Viscous_Analysis>
    <Ground_Effect>false</Ground_Effect>
    <Ground_Height>0.0</Ground_Height>
    <Include_Fuse_Moments>false</Include_Fuse_Moments>
    <Fuselage_Drag>
      <Friction_Drag>false</Friction_Drag>
      <Friction_Drag_Method>Karman-Schoenherr</Friction_Drag_Method>
    </Fuselage_Drag>
    <Use_plane_inertia>true</Use_plane_inertia>   <!-- see §4.4 -->
    <Fixed_Velocity>12.0</Fixed_Velocity>         <!-- T1 -->
    <Fixed_AOA>2.0</Fixed_AOA>                    <!-- T4 -->
    <Inertia>
      <Mass>0.80</Mass>
      <CoG>0.075, 0.000, 0.000</CoG>
      <CoG_Ixx>0.28</CoG_Ixx><CoG_Iyy>0.035</CoG_Iyy>
      <CoG_Izz>0.31</CoG_Izz><CoG_Ixz>0.0</CoG_Ixz>
    </Inertia>
    <Wake>
      <FlatPanelWake>true</FlatPanelWake>
      <NX>5</NX><ProgressionFactor>1.0</ProgressionFactor><LengthFactor>1.0</LengthFactor>
    </Wake>
  </Polar>
</xflPlanePolar>
```

Also read **[src]**: `Flap_settings/Wing_N/flap_M` (a bare angle), and
`AVL_controls/Control/{Name,gains}` where `gains` is a **space-separated** vector.
Both are unusable in practice — see §3.3.

### 4.1 Polar types — all [run] verified except T4/T6/T8

| XML `Type` | flow5 | Verified |
|---|---|---|
| `FIXEDSPEEDPOLAR` | T1 | ✅ fixed speed, α swept |
| `FIXEDLIFTPOLAR` | T2 | ✅ speed solved per α — needs wide 2D Re coverage, §4.3 |
| `GLIDEPOLAR` | T3 | ✅ matched T2 to <0.3 % |
| `FIXEDAOAPOLAR` | T4 | not tested |
| `BETAPOLAR` | T5 | ✅ symmetric in β, as expected |
| `CONTROLPOLAR` | T6 | unreachable, §3.3 |
| `STABILITYPOLAR` | T7 | ✅ modes and eigenvalues; caveats in §9 |
| `T8POLAR` | T8 | not tested |

### 4.2 Methods and reference dimensions

Methods **[src]**: `LLT`, `VLM1`, `VLM2`, `QUADS`, `TRIUNIFORM`, `TRILINEAR`.
An unrecognised value **silently falls back to `VLM2`** — validate before writing.

Reference dimensions: `PLANFORM`, `PROJECTED`, `CUSTOM`, `AUTO` (sails).

> **Trap — `PLANFORM` and `PROJECTED` do not work in script mode.** **[run]**
> The code deriving reference area/span/MAC from geometry is in
> `xflexecutor.cpp:278-424`, which serves the *interactive* batch dialog; the script
> executor never calls it. The polar keeps zeros and the analysis fails:
>
> ```
> error: reference chord length is 0m
> error: reference span length is 0m
> error: reference area is 0m²
> Panel analysis completed ... Errors encountered
> ```
>
> **Always compute them and emit `CUSTOM`** —
> [ADR-0005](adr/0005-compute-reference-dimensions-ourselves.md).
>
> Note the polar's header block echoes back **the values you supplied**, so it is not
> an independent check of your geometry. Independent checks that do work: the strip
> table's `Re` column reveals flow5's local chord (`Re = c·V/ν`), and its `y` column
> reveals the span and panel distribution (§5.3).

### 4.3 Viscous analysis — two methods, and they disagree

**[run]** Same wing, same 15 m/s, three ways:

| α | inviscid CD | on-the-fly CD | interpolated CD |
|---|---|---|---|
| 0 | 0.000946 | 0.010587 | 0.013306 |
| 4 | 0.008361 | 0.017465 | 0.021943 |
| 8 | 0.022859 | 0.039416 | 0.040261 |

- **Inviscid understates drag by an order of magnitude** at low α. Never quote an
  L/D from it.
- **On-the-fly** (`XFoil_OnTheFly=true`) needs no 2D polars and works well on a
  single wing. **But it is fragile on small tail surfaces** — **[run]** on a
  3-surface glider it reported strip values like `Cl= 3.22986, Re= 97143` on the
  elevator, failed to converge, discarded every operating point, and never finished
  in over 2 minutes. Prefer it only for single-wing configurations.
- **Interpolation** (`XFoil_OnTheFly=false`) needs a pre-computed 2D polar mesh and
  is fast and robust on multi-surface aircraft: **[run]** 5 analyses on a 3-surface
  glider in **1.3 s**.
- The two methods differ by 10–25 % in viscous drag. **Never mix them in a
  comparison**, and always record which was used.

> **Trap — a fixed-lift polar diverges where the aircraft makes no lift.** **[run]**
> Asked for α = 0° on a symmetric section, a T2 polar has no finite solution: flow5
> solves an enormous speed instead of refusing, and the run then fails with
> `Viscous interpolation failures` at `Re = 59,043,819, Cl = 0.00`. The message points
> at the polar mesh, but the mesh is not the problem. A T2 or T3 sweep must start
> above the zero-lift angle.

**The 2D polar mesh must bracket the local Re over the whole flight envelope, not
just cruise.** **[run]** A mesh covering Re 50 k–250 k gave a T2 polar with **1 of 6
points** and a T7 polar with **0 points**; widening it to 20 k–400 k gave **5 of 5**
and a working T7. The cause: at high CL the T2 speed drops (α=8° → 4.69 m/s) and the
tip Re falls to ≈40 k, below the mesh. Failures surface as
`Viscous interpolation failures` / `Error generating the operating point... discarding`.

### 4.4 `Use_plane_inertia` overrides your `<Inertia>` block — [run]

| Setting | Ixx used | Roll damping | Spiral damping |
|---|---|---|---|
| `true`, centreline point masses only | **0** | 1.02e-23 | **inf** |
| `true`, masses distributed spanwise | 0.1126 | 0.00386 | 9.08 |
| `false`, explicit `CoG_Ixx=0.28` | **0.28** (honoured) | 0.0123 | 8.99 |

With `Use_plane_inertia=true` flow5 **ignores the explicit `<Inertia>` values** and
derives inertia from the plane's point masses and structure. Point masses all on the
centreline give `Ixx = 0`, and the lateral modes come back as `inf` — silently
garbage, not an error.

**flow5ctl must either set `Use_plane_inertia=false` with computed inertia, or
guarantee spanwise mass distribution.** The supplied CoG is likewise overridden:
a run requesting CoG x=0.075 reported `CoG = (0.051, 0.000, 0.000)`.

---

## 5. Output

### 5.1 File layout — [run]

```
<output_dir>/<project_name>/
├── <project_name>            # binary .fl5 project (no extension appended)
├── <project_name>.log        # full analysis log; first line is `flow5 v7.57`
├── Foil_polars/<Foil>/T1-Re0.200-N9.0.{csv|txt}
├── STL/<PlaneName>.stl       # when export_stl_mesh = true
└── <PlaneName>/
    ├── <polar>.csv           # the polar — authoritative
    └── <polar>/
        └── " 4_00°_12_00m_s.csv"      # operating points — see the trap below
```

> **Trap — operating-point filenames** contain a leading space, a degree sign, and
> decimal points replaced by underscores. Never glob them from a shell.

> **Trap — operating-point files are duplicated into every polar's directory, and
> their contents belong to a different polar.** **[run]** In a run with five polars,
> all five subdirectories contained the *same* 11 filenames, byte-identical
> (`md5` equal), and `t1_12ms/ 0_00°_ 4_00°_12_00m_s.csv` declares on its second
> line that it belongs to **`t5_beta`**.
>
> **The directory name does not identify the polar.** Read `<polar>.csv` for the
> authoritative point list; if you need op-point files, match on the polar name
> written inside the file (line 2), never on the directory.

### 5.2 The polar file is not CSV — [run]

`polar_text_output_format = csv` gives plane polars a `.csv` extension and
**zero commas**. It is whitespace-aligned fixed-width text.

*(Foil polars are different: with `csv` they really are comma-separated, and without
it they are genuine XFoil-format text — see §5.4.)*

Structure of a plane polar:

- a ~30-line prose header (`Type 1: Fixed speed`, `V∞ = 15m/s`, `Ref. dimensions =
  Custom`, `Area`/`Span`/`Chord`, `ρ`, `ν`, `Mass`, `CoG`, `Ixx`…`Ixz`,
  `XNP = d(XCp.Cl)/dCl`, `Static margin`, `Nbr. of data points`)
- then the table: **57 columns of exactly 13 characters** for T1/T3/T5/T7.

Four traps, all hit for real:

1. **The first data row is concatenated onto the header line with no newline.**
   A naive line reader silently drops one operating point. The header line measured
   1562 chars = 821 of labels + a 741-char data row.
2. **Column labels are variable-width with internal single spaces** — `α (°)`,
   `Lift (N)`, `Short Period Damping Ratio`. Labels are separated by runs of **2+
   spaces**; split on that, never on whitespace. Take the column *count* from a data
   row, never from the label text.
3. **A single-point polar has no standalone data line at all** — its only row is the
   one embedded in the header.
4. **Cells may be `inf` or `nan`.** **[run]** `Roll Damping` was `inf` in every row
   of a T7 polar. A strict numeric filter rejects the whole row and drops operating
   points without warning.

A parser handling all four, validated against 7 files across 5 polar types (row count
matching flow5's own `Nbr. of data points` every time), is
[`poc/lib/parse.py`](../poc/lib/parse.py).

Column list (T1): `Ctrl, α, β, φ, CL, CD, CD_viscous, CD_induced, CY, Cm,
Cm_viscous, Cm_pressure, Cl, Cn, Cn_viscous, Cn_pressure, CL/CD, CL^(3/2)/CD,
1/sqrt(CL), Lift (N), Drag (N), Fx_FF_wind … Fz_sum_wind, Extra drag, Fuse drag,
Cf_Fuse, Vx, Vz, V, Gamma, L, M, N, CPx, CPy, CPz, BM (N.m), m.g.Vz (W),
Drag x V (W), Efficiency, XCp.Cl, XNP (m), Phugoid Freq., Phugoid Damping,
Short Period Freq., Short Period Damping Ratio, Dutch Roll Freq., Dutch Roll Damping,
Roll Damping, Spiral Damping, Mass, CoG_x, CoG_z`.

`BM` (bending moment) is directly useful for HPA spar sizing.

### 5.3 Static margin is in **percent**, and the header XNP is unreliable

**[run]** For a rectangular wing with CoG at 0.050 m, reference chord 0.200 m:
`dCm/dCL = 0.005865` → static margin as a fraction is −0.00587, and flow5 reports
`Static margin = -0.590317`. **It is a percentage of the reference chord.** An agent
reading −0.59 as a fraction would call a marginally-unstable aircraft wildly unstable.

- The header `XNP = d(XCp.Cl)/dCl` is correct for **T1** (0.05 m, matching the
  implied neutral point 0.04883 m) but the per-row `XNP` column is **all zeros** for T1.
- For **T7** it is the other way round: header `XNP = 0.00 m` while the column reads
  `0.10883`, and the header `Static margin = -26.4858` contradicts the +29.8 %
  implied by the column and CoG — and contradicts the T1 run on the same aircraft
  (`+29.8478`). **Do not trust the T7 header static margin.** Compute it from the
  `XNP` column and the CoG actually used.

### 5.4 Spanwise strip table — the useful part of an operating-point file

**[run]** Each op-point file carries, per wing, a per-strip table:

```
y(m)  Re  Ai  Cd_i  Cd_v  Cl  CP.x(%)  Trans.top  Trans.bot  Cm_i  Cm_v
      Bending.mom  Vd.x Vd.y Vd.z  F.x F.y F.z  γ
```

This is the source for spanwise-loading plots, elliptic comparison, transition
location, and bending moment. It also cross-checks geometry: `Re = c·V/ν` recovers
flow5's local chord, and the `y` column recovers the span and panel distribution
(**[run]** strips at ±0.975, ±0.925, … 0.05 apart confirmed 20 uniform panels over a
1.0 m semi-span).

### 5.5 2D foil polars

**[run]** With the default (non-`csv`) format, foil polars are written in genuine
XFoil polar format and are **directly re-importable** as `.txt` via
`xfoil_polars_dir`:

```
 Calculated polar for: AG35ish
 xtrf =   0.000 (top)        0.000 (bottom)
 Mach =   0.000     Re =     0.100 e 6     Ncrit =   9.000
  alpha     CL        CD       CDp       Cm    Top Xtr Bot Xtr   Cpmin  Chinge  XCp
 ------- -------- --------- --------- -------- ------- ------- -------- ------- -------
```

Expect non-convergence to drop a few points (**[run]** 35 of 37 at Re 1e5).
Sanity check that came out right: CDmin fell and (L/D)max rose 40.7 → 72.8 as Re went
1e5 → 8e5.

### 5.6 Two more ways a run fails without an error — [run]

**Coincident surfaces.** A fin whose root sits exactly on the elevator (both at the
same `x` and `z`) makes flow5 compute an **effective angle of attack of −104°** at the
elevator centre, then fail the whole analysis:

```
...Viscous interpolation failures:
    Span position     -0.02 m,  Re =    398385,  AoA_effective = -103.90°
```

Note this is a *different shape* of the same failure block — the earlier one reports
`Cl = …`, this one reports `AoA_effective = …`. Both appear under the same
`Viscous interpolation failures` heading, and the same heading also covers a genuinely
narrow polar mesh, so the heading alone does not identify the cause. Offsetting the fin
root a few centimetres above the elevator fixes it.

**The two static-margin definitions can disagree in sign.** On a 34 m HPA with the CG
at 68 % MAC, flow5's neutral-point figure gave **−8.1 %** while the moment slope
`dCm/dCL` from its own columns gave **+6.0 %** — one says stable, the other unstable.
This is not a reporting quirk; the definitions genuinely diverge near neutral
stability. Neither number should be quoted alone: run a T7 polar and check whether the
modes are damped, and sweep the CG to find where the sign settles.

---

## 6. Determining success from stdout

| Marker | Meaning |
|---|---|
| `Error reading script...aborting` | script XML rejected — nothing ran |
| `The file is not an xml readable script` | root element/version wrong |
| `Expected character data.` | a flat range element was given children (§2.3) |
| `Script imported, no parsing error` | script accepted |
| `foils not found ...discarding this plane` | airfoil name mismatch (§3.1) |
| `Made 0 valid analysis pairs (plane, polar) to run` | plane/polar name mismatch |
| `error: reference … is 0m` | reference dimensions not supplied (§4.2) |
| `Error generating the operating point... discarding` | one point failed |
| `Viscous interpolation failures` | 2D polar mesh does not cover the local Re/Cl |
| `OTF failures:` | on-the-fly XFoil did not converge at a strip |
| `Panel analysis completed successfully` | success |
| `Panel analysis completed ... Errors encountered` | ran but failed |
| `LLT analysis completed successfully` / `... Errors encountered` | as above, LLT |
| `Counted N elements` | panel count — use it for the mesh budget |
| `----- Script completed -----` | end of run |

> **Trap — scope the "0 valid analysis pairs" match to `(plane, polar)`.** **[run]**
> flow5 *always* emits `Made 0 valid analysis pairs (boat, polar) to run` for the
> unused sail module, so an unscoped match reports failure on every successful run.

---

## 7. Reproducible crash: `foil_analysis` + `Plane_analysis` in one script

**[run]** **A script containing both sections segfaults.** Bisected over seven
configurations:

| Script contents | Exit |
|---|---|
| `Plane_analysis` only, inviscid | 0, OK |
| `Plane_analysis` only, viscous on-the-fly | 0, OK |
| `Plane_analysis` only, viscous interpolated, no polars | 0, graceful failure |
| `foil_analysis` only | 0, OK |
| **`foil_analysis` + `Plane_analysis` (inviscid)** | **139 SIGSEGV** |
| **`foil_analysis` + `Plane_analysis` (interpolated)** | **139 SIGSEGV** |
| **`foil_analysis` + `Plane_analysis` (on-the-fly)** | **139 SIGSEGV** |

No stdout is produced at all, so there is nothing to parse — this is precisely why
the exit code must still be checked (§1).

**flow5ctl must therefore run two separate flow5 invocations:** one for 2D polars,
one for the 3D analysis, staging the polars as `.txt` into `xfoil_polars_dir`
between them. Verified working — [ADR-0009](adr/0009-two-pass-solver-invocation.md).
Worth reporting upstream.

---

## 8. `load_project_file` — loads, but cannot be analysed further

**[run]** Given a `.fl5` written by an earlier run:

```
Pre-loaded the project file: …/loaded.fl5
   the analysis reloaded has been added for G_centre
   Made 0 valid analysis pairs (plane, polar) to run
```

The project loads — its existing polars are re-exported — and the new analysis is
registered against the right plane name, yet **no pair is made**. Planes read from a
project file are not offered to the pairing step; only planes read from
`plane_definition_xml_dir` are.

So `load_project_file` is useful for **re-exporting** existing results, not for
extending a project with new analyses. This also closes the only possible workaround
for flaps (§3.3).

---

## 9. Stability: T7 works, T1 does not — and T7 has caveats

**[run]** Same aircraft, `Compute_derivatives = true`:

- **T1** produced lateral eigenvalues of `5.995e+51` and `2.836e+15`, and all of its
  `CXu … Cnr` derivative columns are zero. **Meaningless.**
- **T7** produced longitudinal eigenvalues `-100.7`, `-25.78`,
  `-0.04435 ± 0.4199i`. The complex pair is the phugoid: 0.4199 rad/s = 0.0668 Hz,
  matching the reported `Phugoid Freq. = 0.067084 Hz`. **Correct.**

Remaining caveats in 7.57, all **[run]**:

- `Short Period Freq.` and `Short Period Damping Ratio` were reported as **0.0**
  where flow5 found two real roots instead of a complex pair. Reporting 0.0 for
  "overdamped" is misleading.
- `Dutch Roll Freq.` came back as **56.015 Hz** in one case and **0.0** in three
  others — never plausible for a 3 m glider. **Do not report it.**
- `Roll Damping` was `inf` whenever `Ixx = 0` (§4.4).
- The full eigenvalue matrices *are* printed to stdout under
  `___Longitudinal modes___` / `___Lateral modes___`. **Parse those rather than
  trusting the summary columns.**

---

## 10. Performance — measured

| Case | Panels | Analyses | Wall clock |
|---|---|---|---|
| Rectangular wing, T1 inviscid, 5 α | 520 | 1 | 0.5 s |
| 3 m glider, 5 polar types, viscous interpolated | 754 | 5 | 1.3 s |
| **34 m HPA, T1 viscous ×2 (free air + ground effect), 4 α** | **1204** | **2** | **0.5 s** |
| Same, refined mesh | 3172 | 2 | 1.5 s |
| 2D polar mesh: 2 foils × 6 Re × 49 α | — | 12 polars | 14.5 s |
| 2D polar mesh: 2 foils × 9 Re × 61 α | — | 18 polars | 15.4 s |

**The 3D solver is not the cost; XFoil is.** Process-per-analysis is comfortably
viable ([ADR-0001](adr/0001-drive-flow5-via-the-xml-script-interface.md)), and 2D
polar meshes should be computed once and cached.

**Mesh convergence [run]**, 34 m HPA from 544 to 3172 panels: L/D at α=6° moved
45.6 → 45.4 (0.4 %) and static margin 5.091 → 5.073 (0.35 %) — converged at the
coarsest mesh. The low-CL end is more sensitive: L/D at α=0° moved 27.7 → 29.4 (6 %).

---

## 11. Still not verified

- [ ] **Linux and Windows** — no machine available. Paths, display requirements and
      exit semantics are all unconfirmed off macOS.
- [ ] `.plr` binary foil polars — `make_polars_bin_file` produced none (§2.4). The
      `.txt` route works, so this is not blocking.
- [ ] T4 (`FIXEDAOAPOLAR`) and T8 (`T8POLAR`) polar types.
- [ ] `FLATPANELS` bodies, and fuselage import from STL/STEP.
- [ ] `Viscous_Loop` (the non-linear lift iteration).
- [ ] Boats/sails — out of scope for flow5ctl.
- [ ] Whether the §7 segfault and the §5.1 op-point duplication persist in newer
      flow5 releases.

---

## 12. Where this is implemented

| Behaviour | Code |
|---|---|
| Version detection (§0) | [`flow5/probe.py`](../src/flow5ctl/flow5/probe.py) |
| Exit code + stdout markers (§1, §6) | [`flow5/markers.py`](../src/flow5ctl/flow5/markers.py) |
| Two-pass invocation (§7) | [`flow5/runner.py`](../src/flow5ctl/flow5/runner.py), [`usecases/analyze.py`](../src/flow5ctl/usecases/analyze.py) |
| XML generation (§2-4) | [`flow5/xmlgen.py`](../src/flow5ctl/flow5/xmlgen.py) |
| Reference dimensions (§4.2) | [`geometry/derived.py`](../src/flow5ctl/geometry/derived.py) |
| Reynolds envelope (§4.3) | [`geometry/derived.py`](../src/flow5ctl/geometry/derived.py) |
| Explicit inertia (§4.4) | [`geometry/massprops.py`](../src/flow5ctl/geometry/massprops.py) |
| Fin orientation (§3) | [`flow5/xmlgen.py`](../src/flow5ctl/flow5/xmlgen.py) — `FIN_ROLL_ANGLE` |
| Output parsing (§5) | [`flow5/results.py`](../src/flow5ctl/flow5/results.py) |
| Static margin units (§5.3) | [`units.py`](../src/flow5ctl/units.py) |
| Stability modes (§9) | [`flow5/summary.py`](../src/flow5ctl/flow5/summary.py) |

Each trap is pinned by a test in
[`tests/test_results_parser.py`](../tests/test_results_parser.py) and
[`tests/test_xmlgen.py`](../tests/test_xmlgen.py) against the real output in
[`tests/fixtures/`](../tests/fixtures).
