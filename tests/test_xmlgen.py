"""What flow5ctl writes for flow5.

The tests that matter here are the ones enforcing behaviour that flow5 punishes
silently: reference dimensions, a method it recognises, inertia it will not discard,
and above all never putting both script sections in one file.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import pytest

from flow5ctl.errors import InternalError
from flow5ctl.flow5 import xmlgen
from flow5ctl.geometry import derived as geometry
from flow5ctl.model.design import Design


@pytest.fixture
def solved(rect_design):
    d = Design.model_validate(rect_design)
    return d, geometry.solve(d)


class TestPlaneXml:
    def test_is_well_formed_with_the_root_flow5_requires(self, solved):
        design, derived = solved
        root = ET.fromstring(xmlgen.plane_xml(design, derived))
        assert root.tag == "xflplane"
        # the reader demands exactly "1.0", not >= 1.0
        assert root.attrib["version"] == "1.0"

    def test_carries_the_doctype_and_utf8_declaration(self, solved):
        xml = xmlgen.plane_xml(*solved)
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "<!DOCTYPE flow5>" in xml

    def test_tip_section_gets_one_spanwise_panel(self, solved):
        root = ET.fromstring(xmlgen.plane_xml(*solved))
        sections = root.findall(".//Section")
        assert sections[-1].findtext("y_number_of_panels") == "1"

    def test_every_section_names_both_side_airfoils(self, solved):
        """flow5 silently discards a plane whose foils cannot be resolved."""
        root = ET.fromstring(xmlgen.plane_xml(*solved))
        for sec in root.findall(".//Section"):
            assert sec.findtext("Left_Side_FoilName")
            assert sec.findtext("Right_Side_FoilName")

    def test_point_masses_are_written_in_si(self, solved):
        root = ET.fromstring(xmlgen.plane_xml(*solved))
        pm = root.find(".//Point_Mass")
        assert pm is not None
        assert pm.findtext("Tag") == "ballast"
        assert float(pm.findtext("Mass")) == pytest.approx(1.0)

    def test_special_characters_in_a_name_are_escaped(self, rect_design):
        raw = {**rect_design, "name": "Wing & <Test>"}
        design = Design.model_validate(raw)
        xml = xmlgen.plane_xml(design, geometry.solve(design))
        root = ET.fromstring(xml)          # would raise if unescaped
        assert root.findtext("./Plane/Name") == "Wing & <Test>"


class TestPolarXml:
    def spec(self, **kw):
        return xmlgen.AnalysisSpec(name="t1", speed=15.0, **kw)

    def test_reference_dimensions_are_always_custom_with_values(self, solved):
        """PLANFORM and PROJECTED silently produce zeros in script mode (ADR-0005)."""
        design, derived = solved
        root = ET.fromstring(xmlgen.polar_xml(self.spec(), design.name, derived))
        refs = root.find(".//Reference_Dimensions")
        assert refs.findtext("Reference_Dimensions") == "CUSTOM"
        assert float(refs.findtext("Reference_Area")) == pytest.approx(0.4)
        assert float(refs.findtext("Reference_Span_Length")) == pytest.approx(2.0)
        assert float(refs.findtext("Reference_Chord_Length")) == pytest.approx(0.2)

    def test_never_emits_planform_or_projected(self, solved):
        design, derived = solved
        xml = xmlgen.polar_xml(self.spec(), design.name, derived)
        assert "PLANFORM" not in xml
        assert "PROJECTED" not in xml

    def test_plane_name_must_match_exactly(self, solved):
        design, derived = solved
        root = ET.fromstring(xmlgen.polar_xml(self.spec(), design.name, derived))
        assert root.findtext(".//Plane_Name") == design.name

    def test_inertia_is_explicit_so_flow5_cannot_discard_it(self, solved):
        """With Use_plane_inertia=true flow5 overrides these values (section 4.4)."""
        design, derived = solved
        root = ET.fromstring(xmlgen.polar_xml(self.spec(), design.name, derived))
        assert root.findtext(".//Use_plane_inertia") == "false"
        inertia = root.find("./Polar/Inertia")
        for tag in ("CoG_Ixx", "CoG_Iyy", "CoG_Izz", "CoG_Ixz"):
            assert inertia.findtext(tag) is not None

    def test_unknown_method_is_refused_not_silently_downgraded(self, solved):
        design, derived = solved
        with pytest.raises(InternalError, match="VLM2"):
            xmlgen.polar_xml(self.spec(method="NOPE"), design.name, derived)

    @pytest.mark.parametrize("short,expected", [
        ("T1", "FIXEDSPEEDPOLAR"), ("T2", "FIXEDLIFTPOLAR"), ("T3", "GLIDEPOLAR"),
        ("T5", "BETAPOLAR"), ("T7", "STABILITYPOLAR"),
    ])
    def test_polar_type_names(self, solved, short, expected):
        design, derived = solved
        root = ET.fromstring(xmlgen.polar_xml(self.spec(polar_type=short),
                                              design.name, derived))
        assert root.findtext(".//Type") == expected

    def test_ground_effect_is_only_written_when_asked(self, solved):
        design, derived = solved
        without = xmlgen.polar_xml(self.spec(), design.name, derived)
        assert "Ground_Effect" not in without
        with_ge = xmlgen.polar_xml(self.spec(ground_height=0.5), design.name, derived)
        root = ET.fromstring(with_ge)
        assert root.findtext(".//Ground_Effect") == "true"
        assert float(root.findtext(".//Ground_Height")) == pytest.approx(0.5)


class TestScripts:
    def dirs(self, tmp_path):
        return xmlgen.Dirs(output=tmp_path / "out", foils=tmp_path / "foils")

    def test_a_foil_script_never_contains_a_plane_analysis(self, tmp_path):
        """Both sections in one script segfaults flow5 (ADR-0009)."""
        xml = xmlgen.foil_script("p", self.dirs(tmp_path), ["a.dat"],
                                 [1e5, 2e5], (-8.0, 12.0, 0.5))
        assert "<foil_analysis>" in xml
        assert "Plane_analysis" not in xml

    def test_a_plane_script_never_contains_a_foil_analysis(self, tmp_path):
        xml = xmlgen.plane_script("p", self.dirs(tmp_path), ["a.dat"],
                                  xmlgen.PlaneRanges(t12=(-2.0, 8.0, 1.0)))
        assert "<Plane_analysis>" in xml
        assert "foil_analysis" not in xml

    def test_the_alpha_sweep_goes_in_oppoint_range_not_batch_range(self, tmp_path):
        """flow5 parses Batch_Range/Alpha and then ignores it, producing empty polars."""
        xml = xmlgen.foil_script("p", self.dirs(tmp_path), ["a.dat"],
                                 [1e5], (-6.0, 12.0, 0.5))
        root = ET.fromstring(xml)
        assert root.find(".//Batch_Range/Alpha") is None
        assert root.findtext(".//OpPoint_Range/Alpha") == "-6, 12, 0.5"

    def test_range_elements_are_flat_text(self, tmp_path):
        """Children inside a range element abort the entire script."""
        xml = xmlgen.plane_script("p", self.dirs(tmp_path), ["a.dat"],
                                  xmlgen.PlaneRanges(t12=(-2.0, 8.0, 1.0)))
        root = ET.fromstring(xml)
        node = root.find(".//T12_Range")
        assert list(node) == []
        assert node.text == "-2, 8, 1"

    def test_output_path_is_deterministic(self, tmp_path):
        """Without make_project_file flow5 writes to a timestamped directory."""
        xml = xmlgen.plane_script("myproj", self.dirs(tmp_path), ["a.dat"],
                                  xmlgen.PlaneRanges(t12=(0.0, 4.0, 2.0)))
        root = ET.fromstring(xml)
        assert root.findtext(".//make_project_file") == "true"
        assert root.findtext(".//project_file_name") == "myproj"

    def test_a_script_with_no_range_is_refused(self, tmp_path):
        with pytest.raises(InternalError, match="range"):
            xmlgen.plane_script("p", self.dirs(tmp_path), ["a.dat"], xmlgen.PlaneRanges())

    def test_foil_script_requires_reynolds_numbers(self, tmp_path):
        with pytest.raises(InternalError, match="Reynolds"):
            xmlgen.foil_script("p", self.dirs(tmp_path), ["a.dat"], [], (-6.0, 12.0, 0.5))

    def test_scripts_are_well_formed(self, tmp_path):
        for xml in (
            xmlgen.foil_script("p", self.dirs(tmp_path), ["a.dat"], [1e5], (-6.0, 12.0, 0.5)),
            xmlgen.plane_script("p", self.dirs(tmp_path), ["a.dat"],
                                xmlgen.PlaneRanges(t12=(-2.0, 8.0, 1.0))),
        ):
            root = ET.fromstring(xml)
            assert root.tag == "xflscript"
            assert re.match(r"^\d+\.\d+$", root.attrib["version"])
