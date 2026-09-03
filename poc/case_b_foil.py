import sys, pathlib; sys.path.insert(0,'lib')
import f5, gen
ROOT = str(pathlib.Path("work/B").resolve())
f5.clean(ROOT)
f5.write_foil(f"{ROOT}/foils/AG35ish.dat", "AG35ish", f5.naca4("2409"))
f5.write_foil(f"{ROOT}/foils/NACA0009.dat", "NACA0009", f5.naca4("0009"))

foil_sec = """  <foil_analysis>
    <Foil_Files>
      <Foil_File_Name>AG35ish.dat</Foil_File_Name>
      <Foil_File_Name>NACA0009.dat</Foil_File_Name>
    </Foil_Files>
    <Batch_Analysis_Data>
      <Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range>
        <Reynolds>100000, 200000, 400000, 800000</Reynolds>
        <NCrit>9, 9, 9, 9</NCrit>
        <Mach>0, 0, 0, 0</Mach>
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
      <make_polars_bin_file>true</make_polars_bin_file>
      <make_polars_text_file>true</make_polars_text_file>
      <make_oppoints>false</make_oppoints>
    </Output>
  </foil_analysis>
"""
# no plane section needed, but script_xml always emits one; give it no planes
gen.script_xml(f"{ROOT}/script.xml", ROOT, project="B", foils=[],
               foil_section=foil_sec,
               extra_meta="    <MultiThreading>\n      <Allow_Multithreading>true</Allow_Multithreading>\n      <max_threads>8</max_threads>\n    </MultiThreading>\n")
el, out = f5.run(f"{ROOT}/script.xml", timeout=900)
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out, encoding="utf-8")
print(f"elapsed={el:.1f}s")
import re
for ln in out.splitlines():
    if any(k in ln for k in ("foil","Foil","Running with","Found","pairs","completed","cancel","error","Error")):
        print("  ", ln.strip()[:120])
print("--- outputs ---")
for p in sorted(pathlib.Path(f"{ROOT}/out").rglob("*")):
    if p.is_file(): print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size} B)")
