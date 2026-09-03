import sys, pathlib, shutil, subprocess; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = pathlib.Path("work/D").resolve(); f5.clean(str(ROOT))
f5.write_foil(f"{ROOT}/foils/AG35ish.dat", "AG35ish", f5.naca4("2409"))

# ---------- PASS 1: 2D polars only, default (non-csv) text format ----------
p1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata>
    <make_project_file>false</make_project_file>
    <Directories>
      <output_dir>{ROOT}/pass1</output_dir>
      <foil_files_dir>{ROOT}/foils</foil_files_dir>
    </Directories>
  </Metadata>
  <foil_analysis>
    <Foil_Files><Foil_File_Name>AG35ish.dat</Foil_File_Name></Foil_Files>
    <Batch_Analysis_Data>
      <Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range><Reynolds>100000, 150000, 200000, 300000, 400000</Reynolds></Batch_Range>
    </Batch_Analysis_Data>
    <OpPoint_Range>
      <Alpha>-6.0, 12.0, 0.5</Alpha><Spec_Alpha>true</Spec_Alpha><From_Zero>true</From_Zero>
    </OpPoint_Range>
    <Options><Repanel_Foils>true</Repanel_Foils><Foil_Panels>160</Foil_Panels></Options>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
</xflscript>
"""
pathlib.Path(f"{ROOT}/pass1.xml").write_text(p1)
el, out = f5.run(f"{ROOT}/pass1.xml")
print(f"PASS1 elapsed={el:.1f}s")
produced = sorted(pathlib.Path(f"{ROOT}/pass1").rglob("*.*"))
for p in produced: print("   ", p.relative_to(ROOT), p.stat().st_size, "B")

# stage them as .txt for the second pass
xdir = ROOT/"xfoilpolars"; xdir.mkdir(parents=True, exist_ok=True)
n=0
for p in produced:
    if p.suffix.lower() in (".txt",".csv"):
        shutil.copy(p, xdir/(p.stem+".txt")); n+=1
print(f"staged {n} polar files as .txt in {xdir.name}/")
print("--- sample of staged file ---")
if n: print("\n".join(sorted(xdir.glob("*.txt"))[0].read_text(errors='replace').splitlines()[:12]))

# ---------- PASS 2: plane analysis, viscous by interpolation ----------
gen.plane_xml(f"{ROOT}/planes/w.xml", "ViscWing", [{
    "name":"Main Wing","type":"MAINWING","symmetric":True,
    "sections":[
        {"y_position":0.0,"Chord":0.2,"y_number_of_panels":20,"x_number_of_panels":13,
         "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
        {"y_position":1.0,"Chord":0.2,"y_number_of_panels":1,"x_number_of_panels":13,
         "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"}]}],
    point_masses=[("ballast",1.0,0.05,0,0)])
gen.polar_xml(f"{ROOT}/analyses/visc.xml","visc","ViscWing",area=0.4,span=2.0,chord=0.2,
              velocity=15.0,mass=1.0,cog=(0.05,0,0),viscous=True,on_the_fly=False)
gen.script_xml(f"{ROOT}/script2.xml", str(ROOT), project="D", foils=["AG35ish.dat"],
               ranges={"T12_Range":"0.0, 8.0, 2.0"})
el2, out2 = f5.run(f"{ROOT}/script2.xml")
pathlib.Path(f"{ROOT}/pass2_stdout.txt").write_text(out2)
print(f"\nPASS2 elapsed={el2:.1f}s  verdict={f5.verdict(out2)[0]}")
for ln in out2.splitlines():
    if any(k in ln for k in ("XFoil polar","added the","discard","Errors","successfully","no foil")):
        if ln.strip(): print("   ", ln.strip()[:120])
