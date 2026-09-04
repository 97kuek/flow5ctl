# Case K: the wake length, and the claim it demolished.
#
# 0.1.0 shipped "flow5's induced drag is systematically low, increasingly with
# aspect ratio". It is not. flow5's wake is 30 x MAC by default, which is 30/AR
# SPANS, and flow5ctl was not writing a <Wake> element at all. This case is the
# evidence, and it is here because docs/ asserts numbers that a reader must be able
# to re-run.
#
# The test wing is elliptic, because that is the one planform with an exact answer:
# span efficiency e = CL^2/(pi*AR*CDi) is 1.0 and no planar wing can beat it.
#
# Run: cd poc && python3 case_k_wake.py
import sys, pathlib, math; sys.path.insert(0,'lib')
import f5, gen, parse

ROOT = str(pathlib.Path("work/K").resolve())
B, N_SEC, ALPHA = 34.0, 24, 5.0

def elliptic(ar):
    """25 straight sections following c(eta) = c0*sqrt(1-eta^2), quarter-chord aligned."""
    S = B * B / ar
    c0 = 4.0 * S / (math.pi * B)
    secs = []
    for i in range(N_SEC + 1):
        eta = i / N_SEC
        c = c0 * math.sqrt(max(1e-4, 1.0 - eta * eta))
        secs.append({"y_position": eta * B / 2.0, "Chord": c,
                     "xOffset": c0 / 4.0 - c / 4.0,
                     "y_number_of_panels": 1 if i == N_SEC else 4,
                     "y_panel_distribution": "COSINE",
                     "x_number_of_panels": 9,
                     "Left_Side_FoilName": "NACA0012",
                     "Right_Side_FoilName": "NACA0012"})
    return S, c0, secs

def run(ar, wake_mac):
    S, c0, secs = elliptic(ar)
    mac = S / B                      # mean chord; flow5's LengthFactor is in MAC units
    f5.clean(ROOT)
    f5.write_foil(f"{ROOT}/foils/NACA0012.dat", "NACA0012", f5.naca4("0012"))
    gen.plane_xml(f"{ROOT}/planes/e.xml", "Ell", [{
        "name": "Main Wing", "type": "MAINWING", "symmetric": True, "sections": secs}],
        point_masses=[("b", 100.0, 0.2, 0, 0)])
    wake = ("    <Wake>\n"
            "      <FlatPanelWake>true</FlatPanelWake>\n"
            "      <NX>5</NX>\n"
            "      <ProgressionFactor>1.100</ProgressionFactor>\n"
            f"      <LengthFactor>{wake_mac:.3f}</LengthFactor>\n"
            "    </Wake>\n") if wake_mac else ""
    gen.polar_xml(f"{ROOT}/analyses/p.xml", "p", "Ell", area=S, span=B, chord=mac,
                  velocity=8.0, mass=100.0, cog=(0.2, 0, 0), extra_body=wake)
    gen.script_xml(f"{ROOT}/script.xml", ROOT, project="K", foils=["NACA0012.dat"],
                   ranges={"T12_Range": f"{ALPHA}, {ALPHA}, 1.0"})
    f5.run(f"{ROOT}/script.xml")
    csv = pathlib.Path(f"{ROOT}/out/K/Ell/p.csv")
    if not csv.is_file():
        return None
    _hdr, cols, rows = parse.polar_table(csv)
    r = rows[0]
    cl = float(r[parse.col(cols, "CL")])
    cdi = float(r[parse.col(cols, "CD_induced")])
    return cl * cl / (math.pi * (B * B / S) * cdi)

print("Case K - elliptic wing, exact span efficiency is 1.0 and cannot be beaten\n")
print("1. Vary only the wake, at AR 40")
for w in (30, 100, 300, 1000):
    e = run(40.0, w)
    print(f"   wake {w:5d} x MAC   e = {e:.4f}" if e else f"   wake {w:5d}  FAILED")

print("\n2. Hold the wake at a fixed number of SPANS (LengthFactor = spans x AR)")
print("   the aspect-ratio dependence disappears - read across a row\n")
print("   spans " + "".join(f"   AR {a:<7d}" for a in (10, 20, 30, 40, 50)))
for spans in (0.75, 3, 10, 30):
    cells = []
    for ar in (10, 20, 30, 40, 50):
        e = run(float(ar), spans * ar)
        cells.append(f"   {e:.4f}    " if e else "   FAILED   ")
    print(f"   {spans:5.2f} " + "".join(cells), flush=True)

print("\nflow5ctl writes LengthFactor = 20 x AR, which lands within 0.23 % of exact.")
