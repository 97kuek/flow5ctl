import sys, pathlib; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = str(pathlib.Path("work/C").resolve())
f5.clean(ROOT)
f5.write_foil(f"{ROOT}/foils/AG35ish.dat", "AG35ish", f5.naca4("2409"))

gen.plane_xml(f"{ROOT}/planes/rect.xml", "ViscWing", [{
    "name":"Main Wing","type":"MAINWING","symmetric":True,
    "sections":[
        {"y_position":0.0,"Chord":0.2,"y_number_of_panels":20,"x_number_of_panels":13,
         "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
        {"y_position":1.0,"Chord":0.2,"y_number_of_panels":1,"x_number_of_panels":13,
         "Left_Side_FoilName":"AG35ish","Right_Side_FoilName":"AG35ish"},
    ]}], point_masses=[("ballast",1.0,0.05,0,0)])

for nm, visc, otf in (("inviscid", False, False), ("visc_interp", True, False), ("visc_otf", True, True)):
    gen.polar_xml(f"{ROOT}/analyses/{nm}.xml", nm, "ViscWing", area=0.4, span=2.0,
                  chord=0.2, velocity=15.0, mass=1.0, cog=(0.05,0,0),
                  viscous=visc, on_the_fly=otf)

foil_sec = """  <foil_analysis>
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
    <Options>
      <Max_XFoil_Iterations>120</Max_XFoil_Iterations>
      <Repanel_Foils>true</Repanel_Foils>
      <Foil_Panels>160</Foil_Panels>
    </Options>
    <Output>
      <make_polars_text_file>true</make_polars_text_file>
    </Output>
  </foil_analysis>
"""
gen.script_xml(f"{ROOT}/script.xml", ROOT, project="C", foils=["AG35ish.dat"],
               foil_section=foil_sec, ranges={"T12_Range":"0.0, 8.0, 2.0"})
el, out = f5.run(f"{ROOT}/script.xml", timeout=900)
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out, encoding="utf-8")
print(f"elapsed={el:.1f}s  verdict={f5.verdict(out)[0]}")
for ln in out.splitlines():
    if any(k in ln for k in ("analysis","Analysis","error","Error","pairs","completed","interpol","viscous","Viscous")):
        t=ln.strip()
        if t: print("  ", t[:130])
