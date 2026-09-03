"""Verify load_project_file round-trip: can a previous run's .fl5 be reloaded
   and analysed further, without re-supplying plane/foil XML?"""
import sys, pathlib, shutil; sys.path.insert(0,'lib')
import f5, gen, parse
SRC = pathlib.Path("work/I").resolve()
ROOT = pathlib.Path("work/J").resolve(); f5.clean(str(ROOT))
proj = SRC/"out"/"I"/"I"
print("source project:", proj, proj.stat().st_size, "B")
shutil.copy(proj, ROOT/"loaded.fl5")

# New analysis only — no plane xml dir, no foil dat files supplied.
gen.polar_xml(f"{ROOT}/analyses/reloaded.xml","reloaded","G_centre",
              ptype="FIXEDSPEEDPOLAR", area=0.5622, span=3.0, chord=0.1935,
              velocity=9.0, mass=0.80, cog=(0.075,0,0), viscous=True)
script = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata>
    <make_project_file>true</make_project_file>
    <project_file_name>J</project_file_name>
    <load_project_file>{ROOT}/loaded.fl5</load_project_file>
    <polar_text_output_format>csv</polar_text_output_format>
    <Directories>
      <output_dir>{ROOT}/out</output_dir>
      <plane_analysis_xml_dir>{ROOT}/analyses</plane_analysis_xml_dir>
    </Directories>
  </Metadata>
  <Plane_analysis>
    <Plane_Analysis_Output><make_polars_text_file>true</make_polars_text_file></Plane_Analysis_Output>
    <Plane_Definition_Files><Process_All_Files>true</Process_All_Files></Plane_Definition_Files>
    <Plane_Analysis_Files><Process_All_Files>true</Process_All_Files></Plane_Analysis_Files>
    <Plane_Analysis_Data><T12_Range>0.0, 6.0, 3.0</T12_Range></Plane_Analysis_Data>
  </Plane_analysis>
</xflscript>
"""
pathlib.Path(f"{ROOT}/script.xml").write_text(script)
el,out = f5.run(f"{ROOT}/script.xml", timeout=600)
pathlib.Path(f"{ROOT}/stdout.txt").write_text(out, encoding="utf-8")
print(f"elapsed={el:.1f}s verdict={f5.verdict(out)[0]}")
for ln in out.splitlines():
    if any(k in ln for k in ("Pre-loaded","Could not","Error reading the project","added","Launching","completed","Made","Available")):
        if ln.strip(): print("  ", ln.strip()[:115])
print("--- outputs ---")
for p in sorted(pathlib.Path(f"{ROOT}/out").rglob("*")):
    if p.is_file(): print("   ", p.relative_to(ROOT), p.stat().st_size, "B")
for p in pathlib.Path(f"{ROOT}/out").rglob("reloaded.csv"):
    hdr,cols,rows = parse.polar_table(p)
    ia,icl,ild = (parse.col(cols,x) for x in ("α","CL","CL/CD"))
    print("   reloaded polar:", [(r[ia], round(r[icl],4), round(r[ild],2)) for r in rows])
