import sys, pathlib, shutil; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = pathlib.Path("work/F").resolve(); f5.clean(str(ROOT))
f5.write_foil(f"{ROOT}/foils/AG35ish.dat","AG35ish",f5.naca4("2409"))
f5.write_foil(f"{ROOT}/foils/NACA0009.dat","NACA0009",f5.naca4("0009"))

# ---- PASS 1: 2D polar mesh covering wing (104k-192k) and tail (72k-104k) Re
p1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata>
    <make_project_file>true</make_project_file>
    <project_file_name>foils</project_file_name>
    <MultiThreading><Allow_Multithreading>true</Allow_Multithreading><max_threads>8</max_threads></MultiThreading>
    <Directories>
      <output_dir>{ROOT}/pass1</output_dir>
      <foil_files_dir>{ROOT}/foils</foil_files_dir>
    </Directories>
  </Metadata>
  <foil_analysis>
    <Foil_Files>
      <Foil_File_Name>AG35ish.dat</Foil_File_Name>
      <Foil_File_Name>NACA0009.dat</Foil_File_Name>
    </Foil_Files>
    <Batch_Analysis_Data>
      <Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range><Reynolds>50000, 75000, 100000, 150000, 200000, 250000</Reynolds></Batch_Range>
    </Batch_Analysis_Data>
    <OpPoint_Range>
      <Alpha>-10.0, 14.0, 0.5</Alpha><Spec_Alpha>true</Spec_Alpha><From_Zero>true</From_Zero>
    </OpPoint_Range>
    <Options><Repanel_Foils>true</Repanel_Foils><Foil_Panels>160</Foil_Panels></Options>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
</xflscript>
"""
pathlib.Path(f"{ROOT}/pass1.xml").write_text(p1)
el1, out1 = f5.run(f"{ROOT}/pass1.xml", timeout=1200)
files = sorted(pathlib.Path(f"{ROOT}/pass1").rglob("*.txt"))
xdir = ROOT/"xfoilpolars"; xdir.mkdir(exist_ok=True)
for p in files: shutil.copy(p, xdir/(p.parent.name+"_"+p.stem+".txt"))
print(f"PASS1 {el1:.1f}s -> {len(files)} polars staged")
pathlib.Path(f"{ROOT}/pass1_stdout.txt").write_text(out1, encoding="utf-8")

# ---- PASS 2: the glider, several polar types, viscous by interpolation
WING = {"name":"Main Wing","type":"MAINWING","symmetric":True,"sections":[
    {"y_position":0.0,"Chord":0.24,"y_number_of_panels":14,"y_panel_distribution":"COSINE",
     "x_number_of_panels":13,"Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
    {"y_position":1.05,"Chord":0.20,"xOffset":0.02,"Dihedral":3.0,
     "y_number_of_panels":8,"y_panel_distribution":"COSINE","x_number_of_panels":13,
     "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
    {"y_position":1.50,"Chord":0.13,"xOffset":0.06,"Dihedral":3.0,"Twist":-1.5,
     "y_number_of_panels":1,"x_number_of_panels":13,
     "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"}]}
ELEV = {"name":"Elevator","type":"ELEVATOR","symmetric":True,"position":"0.85, 0.0, 0.03",
    "Ry_angle":-1.5,"sections":[
    {"y_position":0.0,"Chord":0.13,"y_number_of_panels":7,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"},
    {"y_position":0.24,"Chord":0.09,"xOffset":0.02,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"}]}
FIN  = {"name":"Fin","type":"FIN","symmetric":False,"position":"0.85, 0.0, 0.05","sections":[
    {"y_position":0.0,"Chord":0.14,"y_number_of_panels":6,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"},
    {"y_position":0.20,"Chord":0.09,"xOffset":0.05,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"}]}
gen.plane_xml(f"{ROOT}/planes/glider.xml","Glider",[WING,ELEV,FIN],
              point_masses=[("fuselage",0.55,0.12,0,0),("nose_ballast",0.25,-0.10,0,0)])

S,B,MAC,M,CG = 0.5622, 3.0, 0.1935, 0.80, (0.075,0,0)
INERTIA = ("    <Inertia>\n      <Mass>0.80</Mass>\n      <CoG>0.075, 0.0, 0.0</CoG>\n"
           "      <CoG_Ixx>0.28</CoG_Ixx>\n      <CoG_Iyy>0.035</CoG_Iyy>\n"
           "      <CoG_Izz>0.31</CoG_Izz>\n      <CoG_Ixz>0.0</CoG_Ixz>\n    </Inertia>\n")
def mk(nm, ptype, extra="", **kw):
    gen.polar_xml(f"{ROOT}/analyses/{nm}.xml", nm, "Glider", ptype=ptype, area=S, span=B,
                  chord=MAC, mass=M, cog=CG, viscous=True, on_the_fly=False,
                  extra_body=extra, **kw)
mk("t1_12ms","FIXEDSPEEDPOLAR", velocity=12.0)
mk("t2_fixedlift","FIXEDLIFTPOLAR")
mk("t5_beta","BETAPOLAR", velocity=12.0)
mk("t1_ground_0p30","FIXEDSPEEDPOLAR", velocity=12.0, ground=0.30)
mk("t7_stab","STABILITYPOLAR", extra=INERTIA, velocity=12.0)

gen.script_xml(f"{ROOT}/script2.xml", str(ROOT), project="F",
    foils=["AG35ish.dat","NACA0009.dat"],
    ranges={"T12_Range":"-2.0, 8.0, 2.0","T5_Range":"-8.0, 8.0, 4.0","T7_Range":"-2.0, 4.0, 2.0"},
    outputs={"make_polars_text_file":"true","make_oppoints":"true",
             "make_oppoints_text_file":"true","export_stl_mesh":"true",
             "Compute_derivatives":"true"})
el2, out2 = f5.run(f"{ROOT}/script2.xml", timeout=1200)
pathlib.Path(f"{ROOT}/pass2_stdout.txt").write_text(out2, encoding="utf-8")
print(f"PASS2 {el2:.1f}s verdict={f5.verdict(out2)[0]}")
for ln in out2.splitlines():
    if any(k in ln for k in ("XFoil polar:","added analysis","Launching","completed","Errors","discard","error:")):
        if ln.strip(): print("  ", ln.strip()[:120])
print("--- outputs ---")
for p in sorted(pathlib.Path(f"{ROOT}/out").rglob("*")):
    if p.is_file(): print(f"   {p.relative_to(ROOT)}  ({p.stat().st_size} B)")
