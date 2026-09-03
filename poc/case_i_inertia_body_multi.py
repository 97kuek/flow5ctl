"""Verify: explicit inertia vs plane inertia; fuselage <body>; multi-plane;
   load_project_file round-trip."""
import sys, pathlib, shutil, math; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = pathlib.Path("work/I").resolve(); f5.clean(str(ROOT))
shutil.copytree("work/G/foils", ROOT/"foils")
shutil.copytree("work/G/xfoilpolars", ROOT/"xfoilpolars")

WING = {"name":"Main Wing","type":"MAINWING","symmetric":True,"sections":[
    {"y_position":0.0,"Chord":0.24,"y_number_of_panels":12,"y_panel_distribution":"COSINE",
     "x_number_of_panels":11,"Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
    {"y_position":1.50,"Chord":0.13,"xOffset":0.06,"Dihedral":3.0,"Twist":-1.5,
     "y_number_of_panels":1,"x_number_of_panels":11,
     "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"}]}
ELEV = {"name":"Elevator","type":"ELEVATOR","symmetric":True,"position":"0.85, 0.0, 0.03",
    "Ry_angle":-1.5,"sections":[
    {"y_position":0.0,"Chord":0.13,"y_number_of_panels":6,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"},
    {"y_position":0.24,"Chord":0.09,"xOffset":0.02,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"}]}
FIN  = {"name":"Fin","type":"FIN","symmetric":False,"position":"0.85, 0.0, 0.05","sections":[
    {"y_position":0.0,"Chord":0.14,"y_number_of_panels":5,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"},
    {"y_position":0.20,"Chord":0.09,"xOffset":0.05,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0009","Right_Side_FoilName":"NACA0009"}]}

# centreline masses only -> Ixx should be ~0
CENTRE = [("fuselage",0.55,0.12,0,0),("nose",0.25,-0.10,0,0)]
# same total, distributed spanwise -> Ixx should be finite
SPANW  = [("fuselage",0.40,0.12,0,0),("nose",0.20,-0.10,0,0),
          ("wingL",0.10,0.05,-0.75,0.02),("wingR",0.10,0.05,0.75,0.02)]

gen.plane_xml(f"{ROOT}/planes/g_centre.xml","G_centre",[WING,ELEV,FIN],point_masses=CENTRE)
gen.plane_xml(f"{ROOT}/planes/g_spanwise.xml","G_span",[WING,ELEV,FIN],point_masses=SPANW)
# a fuselage-equipped variant (NURBS body)
def nurbs_body():
    frames=[]
    prof=[(0.00,0.000),(0.10,0.030),(0.35,0.055),(0.70,0.045),(1.00,0.000)]
    xs=[0.00,0.08,0.25,0.55,0.95]
    for x,(_,r) in zip(xs,prof):
        pts=[]
        n=5
        for k in range(n):
            th=math.pi*k/(n-1)          # top -> bottom, y>=0
            pts.append((x, r*math.sin(th), r*math.cos(th)))
        pstr="\n".join(f"        <point>{px:.4f}, {py:.4f}, {pz:.4f}</point>" for px,py,pz in pts)
        frames.append(f"""      <frame>
        <Angle>0</Angle>
        <x_panels>2</x_panels>
        <Position>{x:.4f}, 0.0000, 0.0000</Position>
{pstr}
      </frame>""")
    return f"""<body>
      <Name>Pod</Name>
      <Type>NURBS</Type>
      <Position>-0.15, 0.0, 0.0</Position>
      <x_panels>12</x_panels>
      <hoop_panels>10</hoop_panels>
      <Inertia><Volume_Mass>0.15</Volume_Mass></Inertia>
      <NURBS>
        <u_degree>3</u_degree>
        <v_degree>3</v_degree>
{chr(10).join(frames)}
      </NURBS>
    </body>"""
gen.plane_xml(f"{ROOT}/planes/g_body.xml","G_body",[WING,ELEV,FIN],
              point_masses=CENTRE, body=nurbs_body())

S,B,MAC,M,CG = 0.5622,3.0,0.1935,0.80,(0.075,0,0)
EXPL = ("    <Inertia>\n      <Mass>0.80</Mass>\n      <CoG>0.075, 0.0, 0.0</CoG>\n"
        "      <CoG_Ixx>0.28</CoG_Ixx>\n      <CoG_Iyy>0.035</CoG_Iyy>\n"
        "      <CoG_Izz>0.31</CoG_Izz>\n      <CoG_Ixz>0.0</CoG_Ixz>\n    </Inertia>\n")
def mk(nm, plane, ptype="STABILITYPOLAR", auto=True, extra="", **kw):
    xml = gen.polar_xml(f"{ROOT}/analyses/{nm}.xml", nm, plane, ptype=ptype, area=S, span=B,
                        chord=MAC, mass=M, cog=CG, viscous=True, extra_body=extra,
                        velocity=12.0, **kw)
    if not auto:
        p=pathlib.Path(f"{ROOT}/analyses/{nm}.xml")
        p.write_text(p.read_text().replace("<Use_plane_inertia>true</Use_plane_inertia>",
                                           "<Use_plane_inertia>false</Use_plane_inertia>"))
mk("s_centre_auto",  "G_centre", auto=True,  extra=EXPL)
mk("s_centre_expl",  "G_centre", auto=False, extra=EXPL)
mk("s_spanwise_auto","G_span",   auto=True,  extra=EXPL)
mk("t1_body",        "G_body",   ptype="FIXEDSPEEDPOLAR", auto=True, extra=EXPL)
mk("t1_centre",      "G_centre", ptype="FIXEDSPEEDPOLAR", auto=True, extra=EXPL)

gen.script_xml(f"{ROOT}/script.xml", str(ROOT), project="I",
    foils=["AG35ish.dat","NACA0009.dat"],
    ranges={"T12_Range":"0.0, 6.0, 2.0","T7_Range":"0.0, 1.0, 1.0"},
    outputs={"make_polars_text_file":"true","Compute_derivatives":"true"})
el,out = f5.run(f"{ROOT}/script.xml", timeout=1800)
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out, encoding="utf-8")
print(f"MULTI-PLANE RUN {el:.1f}s")
for ln in out.splitlines():
    if any(k in ln for k in ("added the plane","added analysis","Launching","completed","Errors","discard","no body","body")):
        if ln.strip(): print("  ", ln.strip()[:115])
print("\n=== inertia actually used (from polar headers) ===")
for nm in ("s_centre_auto","s_centre_expl","s_spanwise_auto"):
    for plane in ("G_centre","G_span"):
        p=f"{ROOT}/out/I/{plane}/{nm}.csv"
        if pathlib.Path(p).exists():
            hdr,cols,rows=parse.polar_table(p)
            print(f"  {nm:17s} rows={len(rows)} Ixx={hdr.get('Ixx')} Iyy={hdr.get('Iyy')} Izz={hdr.get('Izz')} CoG={hdr.get('CoG')}")
            if rows:
                for lbl in ("Dutch Roll Freq.","Roll Damping","Spiral Damping","Phugoid Freq."):
                    try: print(f"        {lbl:18s}", [r[parse.col(cols,lbl)] for r in rows])
                    except Exception: pass
print("\n=== fuselage effect (T1) ===")
for plane,nm in (("G_body","t1_body"),("G_centre","t1_centre")):
    p=f"{ROOT}/out/I/{plane}/{nm}.csv"
    if not pathlib.Path(p).exists(): print(f"  {plane}: NO FILE"); continue
    hdr,cols,rows=parse.polar_table(p)
    ia,icl,icd,ild=(parse.col(cols,x) for x in ("α","CL","CD","CL/CD"))
    print(f"  {plane:9s} rows={len(rows)}  " + "  ".join(f"a={r[ia]:.0f}:CL={r[icl]:.4f},CD={r[icd]:.5f},L/D={r[ild]:.2f}" for r in rows))
