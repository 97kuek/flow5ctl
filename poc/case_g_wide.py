import sys, pathlib, shutil; sys.path.insert(0,'lib')
import f5, gen, parse
SRC = pathlib.Path("work/F").resolve()
ROOT = pathlib.Path("work/G").resolve(); f5.clean(str(ROOT))
for f in ("AG35ish.dat","NACA0009.dat"):
    shutil.copy(SRC/"foils"/f, ROOT/"foils"/f) if (ROOT/"foils").exists() or (ROOT/"foils").mkdir(parents=True) is None else None
p1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata>
    <make_project_file>true</make_project_file><project_file_name>foils</project_file_name>
    <MultiThreading><Allow_Multithreading>true</Allow_Multithreading><max_threads>8</max_threads></MultiThreading>
    <Directories>
      <output_dir>{ROOT}/pass1</output_dir><foil_files_dir>{ROOT}/foils</foil_files_dir>
    </Directories>
  </Metadata>
  <foil_analysis>
    <Foil_Files><Foil_File_Name>AG35ish.dat</Foil_File_Name><Foil_File_Name>NACA0009.dat</Foil_File_Name></Foil_Files>
    <Batch_Analysis_Data><Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range><Reynolds>20000, 30000, 50000, 75000, 100000, 150000, 200000, 300000, 400000</Reynolds></Batch_Range>
    </Batch_Analysis_Data>
    <OpPoint_Range><Alpha>-14.0, 16.0, 0.5</Alpha><Spec_Alpha>true</Spec_Alpha><From_Zero>true</From_Zero></OpPoint_Range>
    <Options><Repanel_Foils>true</Repanel_Foils><Foil_Panels>160</Foil_Panels></Options>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
</xflscript>
"""
pathlib.Path(f"{ROOT}/pass1.xml").write_text(p1)
el1,out1 = f5.run(f"{ROOT}/pass1.xml", timeout=1800)
files = sorted(pathlib.Path(f"{ROOT}/pass1").rglob("*.txt"))
xdir = ROOT/"xfoilpolars"; xdir.mkdir(exist_ok=True)
for p in files: shutil.copy(p, xdir/(p.parent.name+"_"+p.stem+".txt"))
print(f"PASS1 {el1:.1f}s -> {len(files)} polars")

shutil.copytree(SRC/"planes", ROOT/"planes")
S,B,MAC,M,CG = 0.5622, 3.0, 0.1935, 0.80, (0.075,0,0)
INERTIA = ("    <Inertia>\n      <Mass>0.80</Mass>\n      <CoG>0.075, 0.0, 0.0</CoG>\n"
           "      <CoG_Ixx>0.28</CoG_Ixx>\n      <CoG_Iyy>0.035</CoG_Iyy>\n"
           "      <CoG_Izz>0.31</CoG_Izz>\n      <CoG_Ixz>0.0</CoG_Ixz>\n    </Inertia>\n")
def mk(nm, ptype, extra="", **kw):
    gen.polar_xml(f"{ROOT}/analyses/{nm}.xml", nm, "Glider", ptype=ptype, area=S, span=B,
                  chord=MAC, mass=M, cog=CG, viscous=True, on_the_fly=False, extra_body=extra, **kw)
mk("t2_fixedlift","FIXEDLIFTPOLAR")
mk("t7_stab","STABILITYPOLAR", extra=INERTIA, velocity=12.0)
mk("t3_glide","GLIDEPOLAR", velocity=12.0)
gen.script_xml(f"{ROOT}/script2.xml", str(ROOT), project="G", foils=["AG35ish.dat","NACA0009.dat"],
    ranges={"T12_Range":"0.0, 8.0, 2.0","T3_Range":"0.0, 8.0, 2.0","T7_Range":"-2.0, 2.0, 2.0"},
    outputs={"make_polars_text_file":"true","Compute_derivatives":"true"})
el2,out2 = f5.run(f"{ROOT}/script2.xml", timeout=1800)
pathlib.Path(f"{ROOT}/pass2_stdout.txt").write_text(out2, encoding="utf-8")
print(f"PASS2 {el2:.1f}s")
for ln in out2.splitlines():
    if any(k in ln for k in ("Launching","completed","discard","Errors")):
        if ln.strip(): print("  ", ln.strip()[:110])
for nm in ("t2_fixedlift","t7_stab","t3_glide"):
    p=f"{ROOT}/out/G/Glider/{nm}.csv"
    if not pathlib.Path(p).exists(): print(f"{nm}: NO FILE"); continue
    hdr,cols,rows = parse.polar_table(p)
    print(f"\n=== {nm}: rows={len(rows)} ===")
    if rows:
        show=[l for l in ("α","V","CL","CD","CL/CD","Vz","Phugoid","Short","Dutch","Roll","Spiral") ]
        for lbl in show:
            try: print(f"   {lbl:9s}", [round(r[parse.col(cols,lbl)],4) for r in rows])
            except Exception: pass
