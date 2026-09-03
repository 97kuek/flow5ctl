import sys, pathlib, subprocess, shutil, os; sys.path.insert(0,'lib')
import f5, gen
BASE = pathlib.Path("work/C").resolve()

FOIL_SEC = """  <foil_analysis>
    <Foil_Files>
      <Foil_File_Name>AG35ish.dat</Foil_File_Name>
    </Foil_Files>
    <Batch_Analysis_Data>
      <Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range>
        <Reynolds>100000, 150000, 200000, 300000, 400000</Reynolds>
      </Batch_Range>
    </Batch_Analysis_Data>
    <OpPoint_Range>
      <Alpha>-6.0, 12.0, 0.5</Alpha>
      <Spec_Alpha>true</Spec_Alpha>
      <From_Zero>true</From_Zero>
    </OpPoint_Range>
    <Options><Repanel_Foils>true</Repanel_Foils><Foil_Panels>160</Foil_Panels></Options>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
"""

def build(tag, analyses, foil_sec):
    root = str(BASE.parent / f"C_{tag}")
    f5.clean(root)
    f5.write_foil(f"{root}/foils/AG35ish.dat", "AG35ish", f5.naca4("2409"))
    gen.plane_xml(f"{root}/planes/rect.xml", "ViscWing", [{
        "name":"Main Wing","type":"MAINWING","symmetric":True,
        "sections":[
            {"y_position":0.0,"Chord":0.2,"y_number_of_panels":20,"x_number_of_panels":13,
             "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
            {"y_position":1.0,"Chord":0.2,"y_number_of_panels":1,"x_number_of_panels":13,
             "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"}]}],
        point_masses=[("ballast",1.0,0.05,0,0)])
    for nm, visc, otf in analyses:
        gen.polar_xml(f"{root}/analyses/{nm}.xml", nm, "ViscWing", area=0.4, span=2.0,
                      chord=0.2, velocity=15.0, mass=1.0, cog=(0.05,0,0),
                      viscous=visc, on_the_fly=otf)
    gen.script_xml(f"{root}/script.xml", root, project=tag, foils=["AG35ish.dat"],
                   foil_section=foil_sec, ranges={"T12_Range":"0.0, 8.0, 2.0"})
    return root

CASES = [
  ("inv_nofoil",  [("inviscid", False, False)],   ""),
  ("inv_foil",    [("inviscid", False, False)],   FOIL_SEC),
  ("visc_foil",   [("visc", True, False)],        FOIL_SEC),
  ("visc_nofoil", [("visc", True, False)],        ""),
  ("otf_nofoil",  [("otf", True, True)],          ""),
  ("otf_foil",    [("otf", True, True)],          FOIL_SEC),
  ("all3_foil",   [("inviscid",False,False),("visc",True,False),("otf",True,True)], FOIL_SEC),
]
print(f"{'case':<14}{'exit':>6}{'time':>8}  verdict")
for tag, an, fs in CASES:
    root = build(tag, an, fs)
    p = subprocess.run(["/Applications/flow5.app/Contents/MacOS/flow5","-p","-s",f"{root}/script.xml"],
                       capture_output=True, text=True, timeout=900)
    import time
    v = f5.verdict(p.stdout)[0] if p.stdout else "NO_OUTPUT"
    sig = "SIGSEGV" if p.returncode==139 else ("SIGABRT" if p.returncode==134 else "")
    print(f"{tag:<14}{p.returncode:>6}{'':>8}  {v} {sig}")
    pathlib.Path(f"{root}/stdout.txt").write_text(p.stdout+p.stderr, encoding="utf-8")
