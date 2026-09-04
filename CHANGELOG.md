# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning will follow [Semantic Versioning](https://semver.org/) from 0.1.0 onward.

## [Unreleased]

### Fixed

- **The elliptic reference on the spanwise chart went to zero before the tip.** It
  used the outermost strip's centroid as the ellipse's half-span, and a strip's `y`
  is where its load acts, so the last one sits inboard of the tip. On the 34 m
  example that is 0.28 % of semi-span — which is −0.1 % on the curve at mid-span
  and **−15 % at 99 % of span**, where the tip loading is read and the chart exists
  to be read. It uses the geometry's own semi-span now, and both integrals close at
  zero load on the physical tip rather than stopping at the last centroid.
- The chord-from-Reynolds inference behind that reference is now **measured** rather
  than argued: the root-to-tip Re ratio is 2.212 on T1, T2 and T5 alike on the 34 m
  example, with ground effect on — a fixed-lift polar solves a lower speed but the
  ratio does not move, and only the ratio is used.


## [0.1.11] — 2026-09-04

### Fixed

- **The wake-plane check accused surfaces that were nowhere near the wake, and its
  threshold claimed more than it had earned.** Both from a second reviewer. It
  collapsed each surface to a mean height with no look at spanwise reach, so a tail
  lying wholly beyond the upstream wing's tip was warned whenever its mean height
  matched. Spanwise overlap is now a gate. And the tenth-of-MAC figure is relabelled
  as what it is — a clearance margin, not a boundary: the real displacement scales
  with downstream distance times the wake angle, which depends on the downwash and
  the angle of attack, none of which the check sees. The warning now says so, and
  the residual it still cannot catch (an outboard surface in a dihedral panel's
  *local* wake) is written down rather than left implied.
- **The wake-plane check never asked the reciprocal question.** It looked for
  surfaces behind the main wing and skipped anything ahead of it — so on a canard
  layout, where the main wing is the surface sitting in the canard's wake, it looked
  at the one pair that could not be a problem and passed. It now checks every
  ordered pair by streamwise position and names whichever surface is downstream.
- **`open` refused by naming `export`.** It reuses the export path and inherited its
  wording, so running `open` before any analysis said "there is nothing to export" —
  an operation the user had not asked for. It says what it needs and what produces
  it: flow5 writes the `.fl5` as a side effect of an analysis.


## [0.1.10] — 2026-09-04

### Changed

- **The bending cross-check now says the wing does not carry quite all the lift.** A
  reviewer objected that the estimate uses the aircraft's *total* lift for what is
  presented as a main-wing check. Measured by integrating each surface's own strips
  on the shipped examples: the elevator carries **3.5 %** on the 3 m glider at α 6°
  and **3.2 %** on the 34 m HPA at α 7°, so the estimate is high by about that. It
  is stated rather than corrected — splitting the total by the strips' own shares
  would check the strip table against itself, and the whole value of the comparison
  is that its two sides come from different places.


## [0.1.9] — 2026-09-04

### Fixed

- **Over MCP, a rejected edit said only "Error executing tool update_design".**
  `define.update` and `define.create` called `Design.model_validate` bare, and a
  pydantic error is not a `Flow5ctlError`, so the MCP layer's translation did not
  catch it and the client got the tool's name and nothing else. It now names the
  field or the limit, the way the CLI's `set` already did — and the Claude Desktop
  path is the one where the caller has nothing else to go on.


## [0.1.8] — 2026-09-04

### Fixed

- **The panel count disagreed with flow5's whenever there was a fin.** ADR-0010 and
  the Phase 0 log record that `panel_count` matches flow5's own
  `Counted N elements` — established on a rectangular wing, where it does. flow5
  doubles **every** surface, a fin included, and ours doubled only the mirrored
  ones. Measured on a 34 m aircraft varying only the fin's spanwise count, our total
  was short by exactly the fin's panels every time (56, 112, 168). It matters twice:
  the documented cross-check was false for any aircraft with a fin, and the
  `max_panels` budget under-reported the matrix flow5 actually builds.


## [0.1.7] — 2026-09-04

### Fixed

- **The "wing only" note said stability could not be assessed, and then the tool
  assessed it.** For a wing alone the neutral point *is* its aerodynamic centre and
  comes out right — measured on the shipped glider with the tail removed,
  x_np = 0.04747 m against a quarter chord of 0.04763, so
  `trim --target static-margin` answers correctly. What a wing alone cannot do is
  reach Cm = 0, because a cambered section's pitching moment has no surface to
  balance it. The note now says that instead, and the quarter-chord result is pinned
  as a physics check.
- **A spanwise loading chart silently dropped every polar but the first.** The strip
  table is read from one result, so asking for two produced one aircraft's loading
  under a subtitle naming both runs' conditions. It refuses now, like
  `drag_breakdown` already did, and says to plot them separately. `MCP-TOOLS.md`
  records which kinds take several analyses and which take one.


## [0.1.6] — 2026-09-04

### Fixed

- **The wake-plane warning still quoted the pre-fix numbers.** It said the span
  efficiency read 1.93 and that offsetting the tail brought it within 3 % of AVL;
  re-measured under the wake this release ships, those are 1.81 and 0.05 %. An
  earlier attempt to update them had not applied.
- **A comparison chart captioned every curve with the first one's conditions.** A
  12 m/s polar plotted against an 8 m/s one was labelled "12 m/s", so the second
  curve was silently attributed a speed it was not run at — on the chart whose whole
  purpose is comparison. Conditions that differ are now shown as a range, and a
  mixture of viscous methods is named rather than hidden, because mixing those
  invents a fifth of the drag.


## [0.1.5] — 2026-09-04

### Fixed

- **34 broken links on the PyPI project page.** PyPI renders `README.md` and does
  not rewrite relative links, so every `docs/…` and `examples/` reference on the page
  a new user lands on pointed at nowhere — including the design guide and the
  quickstart. They are absolute now, and `tools/check_docs.py` maps URLs back into
  this repository so they are still validated rather than silently exempted.
- **Messages that told the user to read a file they do not have.** Three refusals
  and warnings cited `docs/FLOW5-INTERFACE.md` and `docs/adr/0010-…`, which is a dead
  end for anyone who ran `pip install` rather than cloning. They carry URLs now.
  Docstrings keep the repo-relative paths, because those are read in the source tree.


## [0.1.4] — 2026-09-04

### Added

- **The examples ship in the wheel, and `init --example rc-glider` reads them.** The
  README opened with `init --file examples/rc-glider.yaml` — a path that exists only
  in a checkout, so the documentation's first command failed for everyone who ran
  `pip install flow5ctl`. `sweep --study cg-sweep` resolves the same way. A test
  validates every shipped example against the model, because a broken example is
  documentation that fails on first contact.


## [0.1.3] — 2026-09-04

### Added

- **Both design guides ship inside the wheel**, and the Japanese one is served as
  `flow5://guide/design.ja`. A client installed with `uvx` has no source tree, so it
  was being handed a **981-character summary of a 28,000-character document** — the
  document where every measured limit lives, and where it says no aircraft carrying a
  person should be committed to build on a potential-flow analysis alone. The reader
  getting the summary was exactly the one Phase 3's exit criterion names.

### Fixed

- The documented MCP resource list was wrong in two ways: it advertised
  `flow5://airfoils`, which does not exist, and omitted `flow5://schema/design`,
  which does. Seven resources, three of them URI templates.


### Fixed

- **The drag reconstruction's conclusion changed with the wake.** DESIGN-GUIDE §1a
  said the one aircraft whose airfoil modification is published "falls inside the
  band". Re-run: modelled L/D 38.8 → **36.66**, band 27.7–32.4 → **26.2–30.6**, and
  the published 31.9 now sits **4 % above** it rather than inside. The airfoil
  finding is unaffected and stronger for being stated plainly — reproducing the
  section closes **94 %** of the gap, from 72 % above the band to 4 % — but "the
  modelled drag is not systematically wrong" is no longer supported, and it was
  agreement measured with a wake that flattered the model by about 6 %.
- **Every measurement taken under the old wake, re-taken under the new one.** The
  wake-plane check and the spanwise-mesh study were both run with flow5's 30-chord
  default, which this release replaced — a change that invalidated the conditions
  its own earlier measurements were made under. Both hold up, and both improved:

  | | before | after |
  |---|---|---|
  | tail level with the wing | e 1.932, matching AVL to 3 % once offset | e **1.809**, matching AVL to **0.05 %** |
  | rectangular AR 10, converged | e 0.984, 2.5 % from AVL | e **0.962**, **0.2 %** from AVL |

  The rectangular-wing disagreement the mesh log could not account for was the same
  wake. flow5 and AVL now agree on both planforms.


## [0.1.2] — 2026-09-04

### Fixed — from a second reviewer

- **A stability verdict was given on a number that was not the static margin.** When
  the reference-height pass produces no polar, `static_margin` still holds the pitch
  stiffness — the code said so in a warning and then judged it against the band
  anyway. On an aircraft whose CG hangs below the wing that term is worth tens of
  points, so the failure direction was **reading an unstable aircraft as stable**,
  inside the guardrail added in 0.1.0 to stop exactly that silence. No verdict is
  given now, and the warning says why.
- **The wake-plane check compared surface origins**, ignoring the height dihedral
  gives the wing. It now uses the chord-weighted mean height (`mac_z`), which is what
  the CG-height separation already used.
- **`structure.py` contradicted its own disclaimer** — it opened by saying spar
  sizing needs a section, a material and a safety factor, then called the 1 g
  level-flight load "the load a spar is sized from". It is not; the wording says so.
- **The release workflow never installed what it built.** `RELEASING.md` says that is
  the check that catches a packaged `.yaml` failing to ship, and it was a manual step
  for the first release only. It now installs the wheel, runs it, loads the presets
  and asserts the reported version matches `pyproject.toml`.
- **Every GitHub action is pinned by commit SHA**, including the one that receives
  PyPI's publishing authority.
- The GitHub release notes linked to `CHANGELOG.md` on `main`, so an old release
  would eventually point at a different file. They link to the tag.
- `RELEASING.md` said `git push --tags`, which pushes every unpushed local `v*` tag.
- `DOMAIN-MODEL.md` still listed 20 spanwise panels for the rc-glider and uav
  presets after the default moved to 40.
- **Every quoted figure re-measured after the wake fix.** The wake change moved the
  drag, so the numbers re-measured earlier in this release were wrong again by the
  end of it — ground effect on the HPA example is **+22.5 %** (was +16.0 % pre-wake,
  +18–20 % before that), the glider **+17.2 %**, its best L/D **23.25**, the inviscid
  omission 0.000345 against 0.018006. Three revisions of the same numbers inside one
  release is the argument for measuring them on files in this repository: each change
  invalidated the last set, and each set could be re-run.
- **`poc/case_k_wake.py`** reproduces the wake finding through the frozen harness
  rather than through flow5ctl, because `poc/README.md` promises every measured claim
  in `docs/` can be re-run and the wake tables could not be. Coarser mesh, so the
  absolute values differ a little; the structure is identical — flat across each row,
  converging to 1.000 down the column.


## [0.1.1] — 2026-09-04

### Fixed

- **Retracted: "flow5's induced drag is low, and the shortfall grows with aspect
  ratio."** 0.1.0 shipped that in the README, both design guides, the roadmap's risk
  table and a runtime warning above AR 15. **It was wrong.** flow5 carries its wake a
  fixed number of *chords* downstream — 30 × MAC by default — which is `30 / AR`
  **spans**, and this tool never wrote a `<Wake>` element, so every measurement left
  it there. A sweep that held the span at 34 m and varied the chord therefore varied
  the wake along with the aspect ratio, and the trend that produced was reported as a
  property of the solver.

  Varying only the wake on the same AR 40 elliptic wing, where the exact span
  efficiency is 1.0: **1.2103** at 30 × MAC, 1.0305 at 100, 1.0035 at 300,
  **1.0001** at 1000. Holding the wake at a fixed number of *spans*, the
  aspect-ratio dependence disappears completely — 0.75 spans gives 1.21 at every AR
  from 10 to 50, and 30 spans gives 1.000.

  **flow5's induced drag is sound.** The default wake is too short for a slender
  wing and we were not setting it.
- **The wake is now written in spans, not chords** — `AnalysisSpec.wake_spans`,
  default 20, emitted as `LengthFactor = spans × AR`. Elliptic wings come out within
  **0.23 %** of exact at every aspect ratio from 10 to 50, against 2.4–28 % before,
  and within 0.2 % of AVL. It costs a handful of wake panels and touches no mesh.

  What it moves: `examples/hpa.yaml` best L/D free-air **43.66 → 41.18**, in ground
  effect 50.64 → 50.44, so the ground-effect gain goes +16.0 % → **+22.5 %**;
  `examples/rc-glider.yaml` 23.67 → **23.25**; the PoC rectangular wing's CL_α
  0.08525 → 0.08516. Lift moves 0.1 % while induced drag moves by tens of percent,
  which is the signature of the whole thing.
- The AR-keyed induced-drag warning and the "two optimistic errors stack" sentence in
  the drag budget are removed, along with their tests.


## [0.1.0] — 2026-09-04

First release. The core library, the CLI and the MCP server all work — see
[docs/ROADMAP.md](docs/ROADMAP.md). **macOS only**: nothing in the package is
platform-specific, but every measured claim about flow5 was made on macOS, and
claiming an untested platform is exactly this project's failure mode.

Read [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) — or
[its Japanese translation](docs/ja/DESIGN-GUIDE.md) — before trusting a number from
this. The largest known error is that flow5's induced drag is low by about 12–19 %
at the aspect ratios human-powered aircraft fly, which the tool warns about but does
not correct.

### Added — Phase 4

- **A drag budget on every analysis.** A VLM run of a wing and a tail returns the
  drag of a wing and a tail; the rigging, the fairing and the pilot are a fifth to
  two fifths of an HPA again and flow5 cannot model them here. Each report now names
  what its L/D excludes and gives a realistic band, so the modelled figure is not
  quoted as the aircraft's.
- **Ground effect in and out from one call** — `analyze --compare-ground`, and
  `compare_ground` over MCP. Doing it by hand means running twice and changing
  exactly one flag; two runs at the same height report no difference, which reads
  like "ground effect does not matter here" rather than like a mistake. Measured on
  a 32 m aircraft at 2 m: +9 % best L/D, −10 % minimum sink.
- **Wing root bending moment**, with a closed-form cross-check beside it. The strip
  table already carried the number a spar is sized from and it was being discarded.

- **More than three lifting surfaces** — `extra_surfaces` in `design.yaml`. A
  tandem, a biplane and a canard-plus-tail could not be expressed at all; the schema
  was fixed at wing, elevator and fin while flow5 itself has no cap. Verified end to
  end on a tandem. Tail volume and the bending moment's closed-form cross-check both
  stop applying on such a layout, and the report says so instead of quoting them.
- **`sweep --trimmed`** — solve the flight condition at every point instead of
  reporting a polar. A fixed-speed sweep holds the speed and sweeps alpha, so at
  almost every point the lift does not equal the weight and the moment is not zero;
  its best L/D belongs to a condition the aircraft never flies. Each point now runs
  as a fixed-lift polar and the metrics are read where Cm crosses zero. On the HPA
  example, moving the CG from 0.36 m to 0.50 m takes trimmed L/D from 41.4 to 49.7
  while the static margin falls from +16.1 % to +0.3 %.
- **The design guide in Japanese** — `docs/ja/DESIGN-GUIDE.md`, a full translation
  rather than a summary. It is where every measured limit lives: what the solver can
  and cannot tell you, why absolute drag misses in either direction, that static
  margin and pitch stiffness are different quantities, and that no aircraft carrying
  a person should be committed to build on a potential-flow analysis alone. Leaving
  that in English for a largely Japanese-speaking community left the safety-relevant
  half of the documentation unread.
- **A Japanese getting-started guide** — `docs/ja/QUICKSTART.md`. Written for the
  reader Phase 3's exit criterion names: a Birdman Rally team member who knows
  aerodynamics, has never used a terminal, and does not read English documentation.
  It covers preparation, the first analysis, what every reported number means, and
  what each warning is telling them to do about it.
- **Tag-triggered publishing to PyPI** through trusted publishing, with the release
  procedure in `docs/RELEASING.md`.

### Changed

- **The 2D polar Reynolds ladder is eight rungs per decade, not three.** Viscous
  drag is interpolated across it and at low Reynolds the section drag moves fast.
  Measured on a reconstructed aircraft, best L/D against rung count: 5 rungs 28.10,
  8 rungs 26.86, 12 rungs 27.05, 16 rungs 27.07, 24 rungs 27.03. It settles near
  27.0 and the old five-rung default was the outlier, 4 % optimistic.
- **macOS only.** Linux and Windows are unverified and no longer implied to work.
  Nothing in the package is platform-specific, but every measured claim about flow5
  was made on macOS, and claiming an untested platform is exactly this project's
  failure mode. `poc/verify_platform.py` closes it in one command.

### Fixed

- **The drag budget's band now says it does not include the induced-drag bias.**
  The band comes from published whole-aircraft budgets measured against a modelled
  drag that was taken as sound; at high aspect ratio the modelled drag is itself
  optimistic. Two errors in the same direction have to be said to stack, or the
  reader subtracts one and believes they are done. The band is not quietly moved —
  folding a second correction into it would invent a number.
- **A tail level with the wing halves the induced drag, silently.** The wing's
  trailing vortices leave at its own height and run downstream, so a horizontal
  surface at exactly that height has its control points on the vortex sheet. flow5
  returns a number rather than complaining: measured on an AR 12 wing with a tail
  1.2 m behind, CD_induced was 0.00483 at zero offset — a span efficiency of 1.93,
  which is impossible — against 0.00977 two centimetres away, which matches AVL
  within 3 %. `analyze` now warns when a surface behind the wing is within a tenth
  of the MAC of the wing's height. Both shipped examples are clear of it.
- **flow5's induced drag is low, and the shortfall grows with aspect ratio.** Found
  by cross-checking against AVL 3.40 and against the one case with an exact answer:
  an elliptic planar wing has a span efficiency of 1.0 and cannot exceed it. flow5
  returns **1.024 at AR 10 and 1.210 at AR 40** — 21 % past a hard physical limit —
  where AVL returns 0.997 and 0.996 on the same planforms and is mesh-independent
  from 10 panels. Varying flow5's mesh, spanwise distribution, chordwise count and
  VLM1-against-VLM2 moves it by 0.4 %, so it is none of those; lift is unaffected,
  the two solvers agreeing within 0.6 % on CL. Human-powered aircraft fly at AR
  30–45, where **12–19 % of the induced drag is missing** and induced drag is most
  of the budget. Changing method is not a workaround: flow5's panel methods land
  21 % on the *other* side of the same limit (QUADS 0.783 at AR 40), all
  mesh-converged. `analyze` now warns above AR 15 with the figure for that aircraft.
  It is reported, not corrected: a fudge factor on a solver's output would hide the
  problem and would be wrong wherever it was not measured.
- **Span efficiency above 1 was the mesh, not the physics.** A rectangular wing came
  back at 1.008–1.012, impossible for a planar wing, and the design guide carried
  that as evidence that induced drag was only good to ±5 %. Refining the spanwise
  panels makes it fall monotonically below 1 — measured at AR 10 and again at AR 40,
  extrapolating to 0.984 and 0.975 — while chordwise panels make no difference at
  all, agreeing to four decimal places across 7, 13 and 21. The default spanwise
  count is now **40 rather than 20**, where induced drag was about 3 % optimistic,
  and an analysis says so if a design goes below 25.
- **A negative static margin was reported in silence.** `requirements.static_margin`
  and the preset bands both existed and neither was ever compared against a result.
  The shipped HPA example analysed at **−10.1 % MAC** against its own declared
  requirement of 5–15 % — the CG behind the neutral point, so the aircraft diverges
  in pitch — printed beside a lift-to-drag figure of 50.6 that reads like success.
  Both examples were also corrected: the HPA's pilot sits far enough forward to give
  +8.7 %, and the glider's nose ballast is halved, from 21 % to +9.8 %.
- **The root bending moment was checked against the weight, not against the lift at
  the operating point.** A fixed-speed polar does not fly the aeroplane — it holds
  the speed and sweeps alpha — so most of its points are out of balance. On the 3 m
  glider example the check reported the strip table as 4.3x the estimate, which
  reads like a broken parser; against the lift the polar itself reports at that
  point it is 3 %. Nothing was wrong with the strips. The load factor is now
  reported on its own, and a point more than 15 % from level flight says that the
  bending moment there is not the load a spar is sized from.
- **The spanwise chart compared the local Cl against an elliptic Cl.** Elliptic
  means the *loading* is elliptic, and loading is Cl × chord, so on a tapered wing
  the local Cl that produces an elliptic load rises towards the tip rather than
  falling like √(1−η²). Drawing √(1−η²) against local Cl compares two different
  quantities, and on the 34 m example at taper 0.45 it made a wing whose loading is
  close to elliptic look far below it. The scale was also fitted on the sum of Cl,
  which is the total lift only when the chord and the strip widths are constant.
  flow5's strip table has no chord column, but Re is exactly proportional to it
  within one operating point — measured 2.21 against a taper ratio of 2.22 — so the
  reference is now built from that. A rectangular wing's chart is unchanged.
- **`--compare-ground` did not work on a human-powered aircraft**, which is the
  only class it was built for. It looked for the ground height in the preset's
  `analysis` block, and no preset has ever put one there — they set it in
  `defaults.requirements`, from which it lands on the design as
  `requirements.ground_effect_height`, where every other code path reads it. So the
  feature refused to run and told the user to "use a preset that sets one (hpa
  does)" about a design that was already using that preset. Measured after the fix
  on the HPA example at h = 2.0 m: **+16.0 % best L/D, −16.8 % minimum sink.**
- **A sideslip polar reported a root bending moment.** Alpha is held and beta swept,
  so there is no longitudinal operating point and nothing to read a wing loading at;
  the strips were being taken at whichever beta sorted to the middle, giving
  1,186 N·m against a 3,680 N·m estimate on an HPA. That reads as a structural
  finding and is not one. The summary already refused to report anything else
  longitudinal from a T5 run; this now joins it, with a note saying which polar
  types to use instead.
- **Best L/D did not report the speed it happens at.** `min_sink` carried it and
  `best_LD` did not, so on a fixed-lift or glide polar — where flow5 solves the
  speed at every alpha — the **best glide speed** was computed and thrown away. It
  is also what tells the structural cross-check how much lift the wing was carrying:
  without it a T2 run compared its bending moment against the weight "assuming level
  flight" when the polar had already guaranteed exactly that. With it, the HPA
  example's T2 run reports a load factor of **1.00** — 1020.2 N of lift against
  1020.2 N of weight — which checks the polar's speed column, CL, the reference area
  and the density all at once.
- **`export` could not find an analysis that plainly existed.** `build/` holds the
  last solver invocation only, so a `trim` or a `sweep` afterwards leaves an earlier
  analysis' artifacts gone while its results JSON stays. Exporting it then failed
  with "no analysis called 'cruise'. Available: cg_x_02" — naming a sweep point the
  user never asked for, and implying their own analysis had never happened. It now
  prefers a run they named, says when what it exported is just the last thing the
  solver ran, and explains the overwrite instead of denying the analysis.
- **`export` defaulted to one of our own by-products.** The reference-height pass
  (`__zref`, which holds the CG at wing height so the CG-height term can be
  separated) and a ground comparison's free-air copy (`__free`) both land in
  `build/out` and are usually the most recent thing there, so `export` handed back a
  different aircraft than the one asked about, under a name close enough to be
  missed. They are skipped by default, still usable by name, and labelled when used.
- **Measured claims re-measured against the shipped examples.** Several figures
  quoted in warnings and in the guides came from aircraft the reader does not have,
  and some predated this release's own changes to the Reynolds ladder and the
  spanwise panel default — both of which move the drag. Every replacement is
  something a reader can re-run from this repository, which is the point.

  | claim | was | re-measured |
  |---|---|---|
  | ground effect, best L/D | +18 to +20 % | **+16.0 %** (`hpa.yaml`, h = 2.0 m), **+15.2 %** (`rc-glider.yaml`, h = 0.30 m) |
  | inviscid drag omitted | 93 % "at Re 2e5" | **98 %** (glider at α = 0: CD 0.000332 against 0.017991) |
  | mesh convergence at best L/D | 0.4 % over 544→3172 panels | **0.3 %** over 612→4032 |
  | mesh convergence at α = 0 | 6 % | **8.4 %**, and still climbing at 4032 panels |
  | best L/D against CG | "22.8 throughout" | **23.668 to five figures at every CG**, while trimmed L/D goes 7.72 → 17.78 |
  | interpolated vs on-the-fly XFoil | 10–25 % | **19–28 %**, and on-the-fly is consistently the lower of the two |
  | the CG-height term | "29 points" on a reconstruction | **+13.5 points** on `hpa.yaml` (margin +8.7 %, stiffness +22.2 %); 29 kept as the top of the range seen, marked as not reproducible from this repo |
  | a too-narrow Reynolds mesh | "1 of 6 points" | still the cause, but **the run is now refused** with the range that was reached; derived it gives 6 of 6 |
  | on-the-fly XFoil on a multi-surface aircraft | "unreliable … discarded every operating point" | **it can fail that way and does not always** — the shipped 3-surface glider runs all five points, 8× slower (6.5 s against 0.8 s) |
- **The version was declared in two places and they drifted.** `pyproject.toml` was
  bumped to 0.1.0 while `__init__.py` still said `0.1.0.dev0`, so the wheel was built
  correctly and `flow5ctl --version`, `doctor` and the `flow5://status` resource all
  reported a pre-release to anyone who installed it. It is now read back from the
  installed distribution — one source of truth — and a test fails if a literal ever
  reappears.
- **T4 and T8 polars are refused instead of offered.** Both were listed as known
  types and both were marked untested; running them settled it. T8 returns
  *nonsense* rather than an error — asked for α 2→8 in steps of 2 it gave one point,
  at a speed of 2.0 m/s that nothing in the request mentioned, reporting L/D 68.6
  for a 3 m glider. T4 holds α and sweeps the speed, which this interface has no way
  to express, and flow5 rejects the analysis outright — which was being reported to
  the user as "a bug in flow5ctl, please report it". The refusal for T4 points at
  `sweep` on `speed` with a T1 polar, which asks the same question and works.
- **`airfoil add` now takes the design name positionally too.** `airfoil list`
  does, and so does every other verb, so `flow5ctl airfoil add MyGlider AG35
  naca:2409` read the design name as the airfoil name, and
  `airfoil add MyGlider AG35 --naca 2409` — the natural way to type it — failed with
  "no design.yaml in the current directory", an error about something else. What the
  positionals mean now follows from whether a source flag is present, which settles
  it without guessing: three positionals are `(design, name, source)`, and two with
  `--naca`/`--file`/`--url` are `(design, name)` because a positional source would
  clash. Giving the design twice is refused rather than resolved.
- **`set` now takes the design name positionally**, like every other verb. It did
  not, so `flow5ctl set Glider wing.planform.taper=0.6` read as three assignments
  and failed with "no design.yaml in the current directory" — an error about the
  wrong thing. An assignment without an `=` now says so.
- **The total mass carried binary noise.** 0.40 + 0.10 + 0.10 + 0.10 came back as
  0.7000000000000001 kg and `trim` printed it that way. A number that looks broken
  makes a careful reader doubt every other number beside it.
- A sweep repeated every per-point warning once per point. A four-value CG sweep
  returned the CG-height explanation four times with four different percentages, and
  exact-match de-duplication could not tell they were one finding. Warnings that
  differ only in their numbers are now collapsed, with a count.
- Twin fins (`tail.fin.count: 2`). flow5 has no twin-fin flag — a plane is a list of
  `<wing>` elements with no cap — so two fins are two entries at ±y.
- Airfoil files in Lednicer format, which is how the UIUC database serves every
  section. They could not be read at all.
- Sideslip (T5) polars reported longitudinal numbers, including a 593 % static
  margin, and none of the lateral derivatives the polar exists to measure. flow5
  signs both lateral moment coefficients opposite the textbook; they are converted.
- The spanwise strips were read at whichever operating-point file sorted to the
  middle of the directory — six degrees from the operating point on a real run.
- Rejected edits and invalid design files surfaced Pydantic tracebacks.
- The interpolation-failure message named the Reynolds range as the cause when it
  cannot know which axis failed.

### Added — MCP server (Phase 3)

- An MCP server on stdio (`flow5ctl mcp`), so Claude Desktop and any other MCP client
  can design an aircraft. 13 tools, 6 resources, 4 prompts. One-line install with
  `uvx --from "flow5ctl[plot]" flow5ctl mcp` — see `docs/MCP.md`.
- Charts as PNG image content: the drag polar with best L/D marked, the lift curve,
  the pitching moment with its trim point, the drag breakdown, and the spanwise lift
  distribution against elliptic. Light and dark themes are separately chosen rather
  than one inverted, and the palette is validated for colour-vision deficiency in
  both. `flow5ctl plot` writes the same images from the CLI.
- The spanwise strip table is now stored with each result, so a chart no longer
  depends on `build/` surviving the next analysis.
- Workspace isolation: designs are addressed by name, and a name containing a path
  separator, a traversal or a null byte is rejected rather than resolved. The server
  never reads or writes outside its workspace.
- `flow5://schema/design`, generated from the model, so the fields the server
  advertises and the fields it accepts cannot drift apart.
- Blocking solver work runs off the event loop, so the server stays responsive
  through a twelve-second first analysis or a multi-minute sweep.

### Added — CLI (Phase 2)

- `trim`: solves for the angle of attack at a target CL or for level flight, the speed
  at a given angle, the **CG that achieves a target static margin**, and the elevator
  incidence that gives Cm = 0. The static-margin solve is closed-form in two runs
  because the neutral point does not move with the CG — verified across three CG
  positions, with the margin varying linearly at exactly 1/MAC.
- `sweep`: varies one design or analysis parameter and returns a comparison table,
  with study files so a question is re-runnable after a design change. Design
  parameters are varied in memory, so `design.yaml` is never left half-edited.
- `ld_at_trim` and `cl_at_trim` metrics, plus warnings when a requested metric is
  blind to the parameter being varied (best L/D does not respond to CG) and when a
  sweep's apparent optimum ignores a cost a potential-flow solver cannot see (a
  washout sweep will always favour zero washout).
- `set`, `expand`, `airfoil add`/`list`, `export` (fl5/stl/csv/xml) and `open`, which
  hands the `.fl5` to the flow5 GUI so a human can check the aircraft themselves.
- Worked examples in `examples/` for an RC glider, an HPA and a study.

### Fixed

- **Fins were built horizontally.** `Type=FIN` does not orient anything — flow5 lays a
  fin's sections along y like any other wing, and it becomes vertical only when rolled
  (`Rx_angle = -90`, as the upstream API example does explicitly). Every fin flow5ctl
  had generated was therefore a second horizontal tail: on a reconstructed 30 m
  aircraft the phantom surface moved the neutral point 35 % MAC aft, and every
  sideslip result was meaningless because flow5 never saw a vertical surface.
  `Closed_Inner_Side` is now set for a fin with no fuselage, as the same example
  requires. Found by checking against a real aircraft's published data; no synthetic
  test could catch it, because a horizontal "fin" is still symmetric in sideslip and
  a T5 polar looked perfectly reasonable.
- Coincident surfaces — a fin root sitting on the elevator — are caught before the
  solver runs. flow5 answers that configuration with an effective angle of attack of
  −104° and a failed run, under the same heading it uses for an unrelated cause.
- A static margin that disagrees in sign between flow5's neutral point and its own
  moment slope is reported as ambiguous rather than resolved in favour of one.
- The `hpa` preset's vertical tail volume band was wrong: with a 34 m span in the
  denominator the coefficient is an order of magnitude below a conventional
  aircraft's, so the general-aviation band flagged every correctly sized HPA fin.

### Added — core (Phase 1)

- `design.yaml` schema and validation; presets shipped as data (`hpa`, `rc-glider`,
  `uav`, `custom`) so new aircraft classes need no code.
- Geometry: planform shorthand expansion, exact area/span/MAC integrals for wings with
  breaks, mass properties including inertia, Reynolds envelope over the flight range,
  and tail volume coefficients.
- Two-pass solver invocation with 2D airfoil polar caching — flow5 segfaults if one
  script asks for both 2D and 3D work.
- A self-validating output parser that checks its row count against flow5's own
  declared point count and refuses to report a partial polar.
- Guardrails that refuse rather than warn: stability from a non-T7 polar, T6 control
  polars, panel-count ceilings, and fixed-lift sweeps through zero lift.
- CLI: `doctor`, `init`, `list`, `show`, `presets`, `analyze`, all with `--json`.
- 276 tests, 19 of which run against a real flow5.

### Verified numerically

- The PoC reproduces through the library: CL_α 0.08525 /deg, static margin
  −0.59 % MAC, 520 panels — matching flow5's own element count.
- CL_α within 5.2 % of lifting-line theory for an AR 10 wing.
- The derived Reynolds envelope turns a fixed-lift polar that returned 1 of 6 points
  into 4 of 4, with no user input.

### Added — design record (Phase 0)

- Design record: architecture, domain model, tool surface, aerodynamic design guide.
- Ten architecture decision records covering the solver interface, the two front-ends,
  file-based state, result summarisation, reference dimensions, licensing, version
  compatibility, implementation language, two-pass invocation, and output parsing.
- `docs/FLOW5-INTERFACE.md`: a verified reference for flow5's undocumented batch and
  XML interface, every claim marked as executed or read-from-source.
- `poc/`: reproducible verification harness — eleven cases against flow5 7.57.
- Open-source scaffolding: Apache-2.0 licence, code of conduct, security policy,
  contribution guide, issue and PR templates, CI.

### Verified

- Headless batch analysis end to end, including viscous 2D → 3D, five polar types,
  ground effect, NURBS fuselages, multi-plane runs, STL and Cp export.
- Physics: CL_α within 5.2 % of lifting-line theory; ground effect +18 % L/D on a
  34 m span aircraft at 2 m height; mesh converged at 544 panels for a high-AR planform.
- A reproducible flow5 segfault when one script requests both 2D and 3D work.
- Seven ways flow5's output misleads a naive parser, each now handled.

### Known limitations

- Flaps and T6 control polars are unreachable through flow5's XML interface.
- Verified on macOS only; Linux and Windows untested.
- Dutch-roll and short-period outputs are unreliable in flow5 7.57 and are not reported.
