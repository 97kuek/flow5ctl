"""HPA-scale: 34 m span, AR~40, ground effect, panel-count/timing sweep."""
import sys, pathlib, shutil, math, time; sys.path.insert(0,'lib')
import f5, gen, parse
ROOT = pathlib.Path("work/H").resolve(); f5.clean(str(ROOT))
f5.write_foil(f"{ROOT}/foils/DAEish.dat","DAEish",f5.naca4("4412"))
f5.write_foil(f"{ROOT}/foils/NACA0010.dat","NACA0010",f5.naca4("0010"))

# planform: 34 m span, root 1.15, two breaks, taper to 0.52 tip
BREAKS = [(0.0,1.15,0.0,0.0),(6.5,1.05,0.05,-0.5),(12.0,0.80,0.20,-1.2),(17.0,0.52,0.42,-2.0)]
def area_span_mac(br):
    S=0.0; num=0.0
    for (y0,c0,_,_),(y1,c1,_,_) in zip(br,br[1:]):
        dy=y1-y0; S+=(c0+c1)/2*dy; num+=dy*(c0*c0+c0*c1+c1*c1)/3
    return 2*S, 2*br[-1][0], num/S
S,B,MAC = area_span_mac(BREAKS)
print(f"HPA wing: S={S:.3f} m^2  b={B:.1f} m  MAC={MAC:.4f} m  AR={B*B/S:.2f}")

def wing(npx, npy_each):
    secs=[]
    for i,(y,c,off,tw) in enumerate(BREAKS):
        last = (i==len(BREAKS)-1)
        secs.append({"y_position":y,"Chord":c,"xOffset":off,"Dihedral":2.0,"Twist":tw,
                     "x_number_of_panels":npx,"x_panel_distribution":"COSINE",
                     "y_number_of_panels":1 if last else npy_each,
                     "y_panel_distribution":"COSINE",
                     "Left_Side_FoilName":"DAEish","Right_Side_FoilName":"DAEish"})
    return {"name":"Main Wing","type":"MAINWING","symmetric":True,"sections":secs}
ELEV = {"name":"Elevator","type":"ELEVATOR","symmetric":True,"position":"6.0, 0.0, 0.5",
    "Ry_angle":-2.0,"sections":[
    {"y_position":0.0,"Chord":0.75,"y_number_of_panels":8,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0010","Right_Side_FoilName":"NACA0010"},
    {"y_position":1.70,"Chord":0.50,"xOffset":0.10,"y_number_of_panels":1,"x_number_of_panels":7,
     "Left_Side_FoilName":"NACA0010","Right_Side_FoilName":"NACA0010"}]}
MASSES=[("pilot",68.0,0.55,0,-0.55),("structure",22.0,0.60,0,0.0),("drive",6.0,0.20,0,-0.70)]
MTOT=sum(m for _,m,_,_,_ in MASSES)
CGX=sum(m*x for _,m,x,_,_ in MASSES)/MTOT
CGZ=sum(m*z for _,m,_,_,z in MASSES)/MTOT
print(f"mass={MTOT:.1f} kg  CG=({CGX:.4f}, 0, {CGZ:.4f})  wing loading={MTOT/S:.3f} kg/m2")
V=8.0
print(f"Re at MAC @ {V} m/s = {MAC*V/1.5e-5:.0f}")

# 2D polars covering root..tip Re at 8 m/s: 0.52*8/1.5e-5=277k .. 1.15*8/1.5e-5=613k
p1=f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata><make_project_file>true</make_project_file><project_file_name>foils</project_file_name>
    <MultiThreading><Allow_Multithreading>true</Allow_Multithreading><max_threads>8</max_threads></MultiThreading>
    <Directories><output_dir>{ROOT}/pass1</output_dir><foil_files_dir>{ROOT}/foils</foil_files_dir></Directories>
  </Metadata>
  <foil_analysis>
    <Foil_Files><Foil_File_Name>DAEish.dat</Foil_File_Name><Foil_File_Name>NACA0010.dat</Foil_File_Name></Foil_Files>
    <Batch_Analysis_Data><Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range><Reynolds>100000, 200000, 300000, 400000, 500000, 600000, 800000</Reynolds></Batch_Range></Batch_Analysis_Data>
    <OpPoint_Range><Alpha>-8.0, 14.0, 0.5</Alpha><Spec_Alpha>true</Spec_Alpha><From_Zero>true</From_Zero></OpPoint_Range>
    <Options><Repanel_Foils>true</Repanel_Foils><Foil_Panels>160</Foil_Panels></Options>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
</xflscript>
"""
pathlib.Path(f"{ROOT}/pass1.xml").write_text(p1)
el1,_=f5.run(f"{ROOT}/pass1.xml", timeout=1800)
xdir=ROOT/"xfoilpolars"; xdir.mkdir(exist_ok=True)
files=sorted(pathlib.Path(f"{ROOT}/pass1").rglob("*.txt"))
for p in files: shutil.copy(p, xdir/(p.parent.name+"_"+p.stem+".txt"))
print(f"PASS1 {el1:.1f}s -> {len(files)} polars")

print(f"\n{'npx':>4}{'npy':>5}{'panels':>8}{'time_s':>9}  result")
results={}
for npx, npy in ((9,8),(13,14),(13,24),(17,30)):
    tag=f"m{npx}x{npy}"
    root=str(ROOT/tag); f5.clean(root)
    shutil.copytree(ROOT/"foils", f"{root}/foils")
    shutil.copytree(xdir, f"{root}/xfoilpolars")
    gen.plane_xml(f"{root}/planes/hpa.xml","HPA",[wing(npx,npy),ELEV],point_masses=MASSES)
    gen.polar_xml(f"{root}/analyses/cruise.xml","cruise","HPA",area=S,span=B,chord=MAC,
                  velocity=V,mass=MTOT,cog=(round(CGX,4),0,round(CGZ,4)),viscous=True)
    gen.polar_xml(f"{root}/analyses/cruise_ige.xml","cruise_ige","HPA",area=S,span=B,chord=MAC,
                  velocity=V,mass=MTOT,cog=(round(CGX,4),0,round(CGZ,4)),viscous=True,ground=2.0)
    gen.script_xml(f"{root}/script.xml", root, project=tag, foils=["DAEish.dat","NACA0010.dat"],
                   ranges={"T12_Range":"0.0, 6.0, 2.0"},
                   outputs={"make_polars_text_file":"true"})
    el,out=f5.run(f"{root}/script.xml", timeout=1800)
    npan = next((l.split()[1] for l in out.splitlines() if l.strip().startswith("Counted")), "?")
    v=f5.verdict(out)[0]
    print(f"{npx:>4}{npy:>5}{npan:>8}{el:>9.1f}  {v}")
    for nm in ("cruise","cruise_ige"):
        p=f"{root}/out/{tag}/HPA/{nm}.csv"
        if pathlib.Path(p).exists():
            hdr,cols,rows=parse.polar_table(p)
            if rows:
                ia,icl,icd,ild=(parse.col(cols,x) for x in ("α","CL","CD","CL/CD"))
                results[(npx,npy,nm)]={r[ia]:(r[icl],r[icd],r[ild]) for r in rows}
                print(f"        {nm:11s} SM={hdr.get('Static margin')}  " +
                      " ".join(f"a={a}:L/D={results[(npx,npy,nm)][a][2]:.1f}" for a in sorted(results[(npx,npy,nm)])))
pathlib.Path(f"{ROOT}/summary.txt").write_text(repr(results))
