"""XML generators for PoC cases. Prototype of flow5ctl's xmlgen."""
import pathlib, math

def _sec(s):
    d = {"y_position":0.0,"Chord":0.1,"xOffset":0.0,"Dihedral":0.0,"Twist":0.0,
         "x_number_of_panels":13,"x_panel_distribution":"COSINE",
         "y_number_of_panels":10,"y_panel_distribution":"UNIFORM",
         "Left_Side_FoilName":None,"Right_Side_FoilName":None}
    d.update(s)
    out = ["        <Section>"]
    for k,v in d.items():
        if v is None: continue
        out.append(f"          <{k}>{v}</{k}>")
    out.append("        </Section>")
    return "\n".join(out)

def plane_xml(path, name, wings, point_masses=(), description="", body=None):
    W=[]
    for w in wings:
        secs = "\n".join(_sec(s) for s in w["sections"])
        extra = ""
        for k in ("Rx_angle","Ry_angle","Tip_Strips","Two_Sided","Closed_Inner_Side"):
            if k in w: extra += f"      <{k}>{w[k]}</{k}>\n"
        W.append(f"""    <wing>
      <Name>{w['name']}</Name>
      <Type>{w.get('type','MAINWING')}</Type>
      <Position>{w.get('position','0.0, 0.0, 0.0')}</Position>
      <Symmetric>{str(w.get('symmetric',True)).lower()}</Symmetric>
{extra}      <Sections>
{secs}
      </Sections>
    </wing>""")
    PM=""
    if point_masses:
        rows = "\n".join(
            f"""      <Point_Mass>
        <Tag>{t}</Tag>
        <Mass>{m}</Mass>
        <coordinates>{x}, {y}, {z}</coordinates>
      </Point_Mass>""" for t,m,x,y,z in point_masses)
        PM = f"    <Inertia>\n{rows}\n    </Inertia>\n"
    B = f"    {body}\n" if body else ""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE flow5>
<xflplane version="1.0">
  <Units>
    <meter_to_length_unit>1.0</meter_to_length_unit>
    <kg_to_mass_unit>1.0</kg_to_mass_unit>
  </Units>
  <Plane>
    <Name>{name}</Name>
    <Description>{description}</Description>
{PM}{B}{chr(10).join(W)}
  </Plane>
</xflplane>
"""
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(xml,encoding="utf-8")
    return xml

def polar_xml(path, polar_name, plane_name, ptype="FIXEDSPEEDPOLAR", method="VLM2",
              area=None, span=None, chord=None, viscous=False, on_the_fly=False,
              velocity=None, mass=None, cog=(0,0,0), ground=None, extra_body="",
              ncrit=9.0, ref_mode="CUSTOM", thin=True, from_cl=False):
    refs = f"      <Reference_Dimensions>{ref_mode}</Reference_Dimensions>\n"
    if ref_mode == "CUSTOM":
        refs += (f"      <Reference_Area>{area}</Reference_Area>\n"
                 f"      <Reference_Span_Length>{span}</Reference_Span_Length>\n"
                 f"      <Reference_Chord_Length>{chord}</Reference_Chord_Length>\n")
    G = ""
    if ground is not None:
        G = (f"    <Ground_Effect>true</Ground_Effect>\n"
             f"    <Ground_Height>{ground}</Ground_Height>\n")
    V = f"    <Fixed_Velocity>{velocity}</Fixed_Velocity>\n" if velocity is not None else ""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE flow5>
<xflPlanePolar version="1.0">
  <Units>
    <meter_to_length_unit>1.0</meter_to_length_unit>
    <kg_to_mass_unit>1.0</kg_to_mass_unit>
    <ms_to_speed_unit>1.0</ms_to_speed_unit>
  </Units>
  <Polar>
    <Polar_Name>{polar_name}</Polar_Name>
    <Plane_Name>{plane_name}</Plane_Name>
    <Type>{ptype}</Type>
    <Method>{method}</Method>
    <Thin_Surfaces>{str(thin).lower()}</Thin_Surfaces>
    <Reference_Dimensions>
{refs}    </Reference_Dimensions>
    <Viscous_Analysis>
      <Is_Viscous_Analysis>{str(viscous).lower()}</Is_Viscous_Analysis>
      <XFoil_OnTheFly>{str(on_the_fly).lower()}</XFoil_OnTheFly>
      <From_CL>{str(from_cl).lower()}</From_CL>
      <NCrit>{ncrit}</NCrit>
    </Viscous_Analysis>
{G}    <Use_plane_inertia>true</Use_plane_inertia>
{V}    <Inertia>
      <Mass>{mass}</Mass>
      <CoG>{cog[0]}, {cog[1]}, {cog[2]}</CoG>
    </Inertia>
{extra_body}  </Polar>
</xflPlanePolar>
"""
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(xml,encoding="utf-8")
    return xml

def script_xml(path, root, project="poc", foils=(), ranges=None, outputs=None,
               foil_section="", extra_meta="", dirs=None):
    ranges = ranges or {"T12_Range": "-2.0, 8.0, 1.0"}
    outputs = outputs or {"make_polars_text_file":"true","make_oppoints":"true",
                          "make_oppoints_text_file":"true"}
    d = {"output_dir":f"{root}/out","foil_files_dir":f"{root}/foils",
         "plane_definition_xml_dir":f"{root}/planes",
         "plane_analysis_xml_dir":f"{root}/analyses",
         "foil_analysis_xml_dir":f"{root}/foilanalyses",
         "foil_polars_dir":f"{root}/foilpolars",
         "xfoil_polars_dir":f"{root}/xfoilpolars"}
    if dirs: d.update(dirs)
    dirxml = "\n".join(f"      <{k}>{v}</{k}>" for k,v in d.items())
    fl = "\n".join(f"      <Foil_File_Name>{f}</Foil_File_Name>" for f in foils)
    outxml = "\n".join(f"      <{k}>{v}</{k}>" for k,v in outputs.items())
    rgxml = "\n".join(f"      <{k}>{v}</{k}>" for k,v in ranges.items())
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xflscript>
<xflscript version="1.0">
  <Metadata>
    <make_project_file>true</make_project_file>
    <project_file_name>{project}</project_file_name>
    <polar_text_output_format>csv</polar_text_output_format>
{extra_meta}    <Directories>
{dirxml}
    </Directories>
  </Metadata>
{foil_section}  <Plane_analysis>
    <Plane_Analysis_Output>
{outxml}
    </Plane_Analysis_Output>
    <Foil_Dat_Files>
{fl}
    </Foil_Dat_Files>
    <Plane_Definition_Files>
      <Process_All_Files>true</Process_All_Files>
    </Plane_Definition_Files>
    <Plane_Analysis_Files>
      <Process_All_Files>true</Process_All_Files>
    </Plane_Analysis_Files>
    <Plane_Analysis_Data>
{rgxml}
    </Plane_Analysis_Data>
  </Plane_analysis>
</xflscript>
"""
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(xml,encoding="utf-8")
    return xml
