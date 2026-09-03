import sys, pathlib; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = str(pathlib.Path("work/E").resolve()); f5.clean(ROOT)
f5.write_foil(f"{ROOT}/foils/AG35ish.dat","AG35ish",f5.naca4("2409"))
f5.write_foil(f"{ROOT}/foils/NACA0009.dat","NACA0009",f5.naca4("0009"))

# 3 m RC glider: wing + elevator + fin
WING = {"name":"Main Wing","type":"MAINWING","symmetric":True,"sections":[
    {"y_position":0.0,"Chord":0.24,"y_number_of_panels":14,"y_panel_distribution":"COSINE",
     "x_number_of_panels":13,"Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
    {"y_position":1.05,"Chord":0.20,"xOffset":0.02,"Dihedral":3.0,"Twist":0.0,
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
FIN  = {"name":"Fin","type":"FIN","symmetric":False,"position":"0.85, 0.0, 0.03","sections":[
    {"y_position":0.0,"Chord":0.14,"y_number_of_panels":6,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"},
    {"y_position":0.20,"Chord":0.09,"xOffset":0.05,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"}]}
gen.plane_xml(f"{ROOT}/planes/glider.xml","Glider",[WING,ELEV,FIN],
              point_masses=[("fuselage",0.55,0.12,0,0),("nose_ballast",0.25,-0.10,0,0)])

S, B, MAC, M, CG = 0.5622, 3.0, 0.1935, 0.80, (0.075,0,0)
INERTIA = ("    <Inertia>\n      <Mass>0.80</Mass>\n      <CoG>0.075, 0.0, 0.0</CoG>\n"
           "      <CoG_Ixx>0.28</CoG_Ixx>\n      <CoG_Iyy>0.035</CoG_Iyy>\n"
           "      <CoG_Izz>0.31</CoG_Izz>\n      <CoG_Ixz>0.0</CoG_Ixz>\n    </Inertia>\n")
def mk(nm, ptype, **kw):
    gen.polar_xml(f"{ROOT}/analyses/{nm}.xml", nm, "Glider", ptype=ptype,
                  area=S, span=B, chord=MAC, mass=M, cog=CG, viscous=True,
                  on_the_fly=True, **kw)
mk("t1_12ms","FIXEDSPEEDPOLAR", velocity=12.0)
mk("t2_fixedlift","FIXEDLIFTPOLAR")
mk("t5_beta","BETAPOLAR", velocity=12.0)
mk("t1_ground","FIXEDSPEEDPOLAR", velocity=12.0, ground=0.30)
gen.polar_xml(f"{ROOT}/analyses/t7_stab.xml","t7_stab","Glider",ptype="STABILITYPOLAR",
              area=S,span=B,chord=MAC,mass=M,cog=CG,viscous=True,on_the_fly=True,
              velocity=12.0, extra_body=INERTIA)

gen.script_xml(f"{ROOT}/script.xml", ROOT, project="E", foils=["AG35ish.dat","NACA0009.dat"],
    ranges={"T12_Range":"-2.0, 8.0, 2.0","T5_Range":"-8.0, 8.0, 4.0","T7_Range":"-2.0, 4.0, 2.0"},
    outputs={"make_polars_text_file":"true","make_oppoints":"true",
             "make_oppoints_text_file":"true","export_stl_mesh":"true",
             "Compute_derivatives":"true"})
el,out = f5.run(f"{ROOT}/script.xml", timeout=900)
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out,encoding="utf-8")
print(f"elapsed={el:.1f}s  exit-verdict={f5.verdict(out)[0]}")
for ln in out.splitlines():
    if any(k in ln for k in ("added analysis","Launching","completed","Errors","discard","error:")):
        if ln.strip(): print("  ", ln.strip()[:120])
print("--- outputs ---")
for p in sorted(pathlib.Path(f"{ROOT}/out").rglob("*")):
    if p.is_file(): print(f"   {p.relative_to(ROOT)}  ({p.stat().st_size} B)")
