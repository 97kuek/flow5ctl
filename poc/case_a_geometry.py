import sys, pathlib, json; sys.path.insert(0,'lib')
import f5, gen
ROOT = str(pathlib.Path("work/A").resolve())
f5.clean(ROOT)
f5.write_foil(f"{ROOT}/foils/NACA0012.dat", "NACA0012", f5.naca4("0012"))

# Rectangular wing: full span 2.0, chord 0.2  -> S=0.4, AR=10, MAC=0.2
gen.plane_xml(f"{ROOT}/planes/rect.xml", "RectWing", [{
    "name":"Main Wing","type":"MAINWING","symmetric":True,
    "sections":[
        {"y_position":0.0,"Chord":0.2,"y_number_of_panels":20,
         "y_panel_distribution":"UNIFORM","x_number_of_panels":13,
         "Left_Side_FoilName":"NACA0012","Right_Side_FoilName":"NACA0012"},
        {"y_position":1.0,"Chord":0.2,"y_number_of_panels":1,
         "x_number_of_panels":13,
         "Left_Side_FoilName":"NACA0012","Right_Side_FoilName":"NACA0012"},
    ]}], point_masses=[("ballast",1.0,0.05,0,0)])

gen.polar_xml(f"{ROOT}/analyses/t1.xml", "t1", "RectWing",
              area=0.4, span=2.0, chord=0.2, velocity=15.0, mass=1.0, cog=(0.05,0,0))
gen.script_xml(f"{ROOT}/script.xml", ROOT, project="A",
               foils=["NACA0012.dat"], ranges={"T12_Range":"0.0, 8.0, 2.0"})
el, out = f5.run(f"{ROOT}/script.xml")
v, hits = f5.verdict(out)
print(f"verdict={v} {hits} elapsed={el:.2f}s")
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out, encoding="utf-8")
print("--- output tree ---")
for p in sorted(pathlib.Path(f"{ROOT}/out").rglob("*")):
    if p.is_file(): print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size} B)")
