"""What flow5ctl writes for flow5.

The tests that matter here are the ones enforcing behaviour that flow5 punishes
silently: reference dimensions, a method it recognises, inertia it will not discard,
and above all never putting both script sections in one file.
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError

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


class TestFinOrientation:
    """A fin must be rolled upright, or flow5 builds it as a horizontal tail.

    `Type=FIN` does not orient anything: flow5 lays a fin's sections along y like any
    other wing. The upstream API example rolls it explicitly
    (`setRxAngle(&fin, -90.0)`, API_examples/PlaneRun1/PlaneRun1.cpp:316).

    Found by reconstructing a real aircraft from its published three-view: the phantom
    horizontal surface moved the neutral point 35 % MAC aft, and every sideslip result
    was meaningless because flow5 never saw a vertical surface. Synthetic tests could
    not catch it — a horizontal "fin" is still symmetric in beta, so a T5 polar looked
    perfectly reasonable.
    """

    @pytest.fixture
    def with_tail(self, rect_design):
        raw = {**rect_design}
        raw["tail"] = {
            "type": "conventional",
            "elevator": {"position": [1.0, 0.0, 0.05], "airfoil": "NACA0012",
                         "planform": {"span": 0.5, "root_chord": 0.12},
                         "panels": {"chordwise": 7, "spanwise": 6}},
            "fin": {"position": [1.0, 0.0, 0.10], "airfoil": "NACA0012",
                    "planform": {"span": 0.25, "root_chord": 0.14},
                    "panels": {"chordwise": 7, "spanwise": 5}},
        }
        design = Design.model_validate(raw)
        return design, geometry.solve(design)

    def _wing(self, xml: str, name: str):
        for w in ET.fromstring(xml).findall(".//wing"):
            if w.findtext("Type") == name:
                return w
        raise AssertionError(f"no {name} in the plane XML")

    def test_a_fin_is_rolled_upright(self, with_tail):
        fin = self._wing(xmlgen.plane_xml(*with_tail), "FIN")
        assert float(fin.findtext("Rx_angle")) == pytest.approx(-90.0)

    def test_the_main_wing_and_elevator_are_not_rolled(self, with_tail):
        xml = xmlgen.plane_xml(*with_tail)
        for name in ("MAINWING", "ELEVATOR"):
            assert float(self._wing(xml, name).findtext("Rx_angle")) == pytest.approx(0.0)

    def test_a_fin_is_not_mirrored(self, with_tail):
        assert self._wing(xmlgen.plane_xml(*with_tail), "FIN").findtext("symmetric") == "false"

    def test_a_fin_with_no_fuselage_closes_its_own_root(self, with_tail):
        """Otherwise the root panels leak — the upstream example calls this out."""
        fin = self._wing(xmlgen.plane_xml(*with_tail), "FIN")
        assert fin.findtext("Closed_Inner_Side") == "true"

    def test_a_fin_on_a_fuselage_does_not(self, with_tail):
        design, derived = with_tail
        design.fuselage.type = "pod"
        fin = self._wing(xmlgen.plane_xml(design, derived), "FIN")
        assert fin.findtext("Closed_Inner_Side") is None

    def test_incidence_still_goes_to_ry_not_rx(self, rect_design):
        """A fin's roll must not swallow an elevator's incidence."""
        raw = {**rect_design}
        raw["tail"] = {"type": "conventional",
                       "elevator": {"position": [1.0, 0.0, 0.05], "incidence": -2.5,
                                    "airfoil": "NACA0012",
                                    "planform": {"span": 0.5, "root_chord": 0.12}}}
        design = Design.model_validate(raw)
        elev = self._wing(xmlgen.plane_xml(design, geometry.solve(design)), "ELEVATOR")
        assert float(elev.findtext("Ry_angle")) == pytest.approx(-2.5)
        assert float(elev.findtext("Rx_angle")) == pytest.approx(0.0)


class TestTwinFin:
    """flow5 has no twin-fin flag; a plane is just a list of `<wing>` elements.

    Verified against the source: `xmlplanereader.cpp` calls `addWing()` once per
    `<wing>` element with no cap, and the only wing tags its reader accepts are Name,
    Type, Position, Rx_angle, Ry_angle, symmetric and Closed_Inner_Side
    (`flow5-io-lib/xml/xflxmlreader.cpp`). Writing `isDoubleFin` or `isSymFin` into
    the file changes nothing - measured, the polar came back bit-identical.

    So two fins are two entries at ±y. Measured on one HPA, two fins of exactly
    double the area gave 1.92x the side force and 1.96x the yaw moment of one.
    """

    def _design(self, count: int, y: float) -> Design:
        d = Design.model_validate({
            "name": "TwinFinTest",
            "mass": {"components": [{"tag": "all", "mass": 100.0, "at": [0.3, 0, 0]}]},
            "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
            "wing": {"airfoil": "NACA0012",
                     "planform": {"span": 10.0, "root_chord": 1.0}},
            "tail": {"fin": {"airfoil": "NACA0012", "count": count,
                             "position": [5.0, y, 0.0],
                             "planform": {"span": 1.0, "root_chord": 0.5}}},
        })
        return d

    def test_one_fin_emits_one_wing(self):
        d = self._design(1, 0.0)
        assert xmlgen.plane_xml(d, geometry.solve(d)).count("<wing>") == 2

    def test_two_fins_emit_two_wings_mirrored_in_y(self):
        d = self._design(2, 1.6)
        xml = xmlgen.plane_xml(d, geometry.solve(d))
        assert xml.count("<wing>") == 3
        assert "<Position>5, 1.6, 0</Position>" in xml
        assert "<Position>5, -1.6, 0</Position>" in xml

    def test_both_fins_are_stood_up_vertically(self):
        """Rx_angle is the only thing that orients a surface, so both need it."""
        xml = xmlgen.plane_xml(self._design(2, 1.6), geometry.solve(self._design(2, 1.6)))
        assert xml.count(f"<Rx_angle>{xmlgen.FIN_ROLL_ANGLE:.6g}</Rx_angle>") == 2

    def test_the_two_fins_are_named_apart(self):
        xml = xmlgen.plane_xml(self._design(2, 1.6), geometry.solve(self._design(2, 1.6)))
        assert "<Name>Fin L</Name>" in xml and "<Name>Fin R</Name>" in xml

    def test_no_twin_fin_flag_is_written(self):
        """flow5's reader has no such tag; writing one would be cargo cult."""
        xml = xmlgen.plane_xml(self._design(2, 1.6), geometry.solve(self._design(2, 1.6)))
        assert "isDoubleFin" not in xml and "isSymFin" not in xml

    def test_both_fins_count_towards_the_tail_volume(self):
        one, two = geometry.solve(self._design(1, 0.0)), geometry.solve(self._design(2, 1.6))
        assert two.tail_volume_v == pytest.approx(2 * one.tail_volume_v, rel=1e-6)

    def test_both_fins_count_towards_the_panel_budget(self):
        one, two = geometry.solve(self._design(1, 0.0)), geometry.solve(self._design(2, 1.6))
        fin_panels = next(s.geom.panel_count for s in one.surfaces
                          if s.wing.role == "fin")
        assert two.panel_count == one.panel_count + fin_panels

    def test_two_fins_on_the_centreline_are_refused(self):
        """They would be coincident, which flow5 solves into a narrow mesh."""
        with pytest.raises(ValidationError, match="half-spacing"):
            self._design(2, 0.0)

    def test_only_a_fin_may_be_doubled(self):
        with pytest.raises(ValidationError, match="only a fin may have count"):
            Design.model_validate({
                "name": "X",
                "mass": {"components": [{"tag": "a", "mass": 1.0, "at": [0, 0, 0]}]},
                "airfoils": [{"name": "NACA0012", "source": "naca:0012"}],
                "wing": {"airfoil": "NACA0012",
                         "planform": {"span": 10.0, "root_chord": 1.0}},
                "tail": {"elevator": {"airfoil": "NACA0012", "count": 2,
                                      "position": [5.0, 0, 0],
                                      "planform": {"span": 2.0, "root_chord": 0.4}}},
            })
