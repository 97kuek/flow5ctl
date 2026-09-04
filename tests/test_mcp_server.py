"""The MCP surface.

These run the server in-process — no flow5, no subprocess — so they check the
adapter's own contract: that it registers what it says it does, that it addresses
designs by name and never by path, that private fields never reach a client, and that
a bad request comes back as a message rather than a stack trace.

The end-to-end path over real stdio is exercised by `tests/test_mcp_stdio.py`.
"""
from __future__ import annotations

import json

import pytest

from flow5ctl.usecases import define

mcp = pytest.importorskip("flow5ctl.mcp_server", reason="the mcp package is not installed")
_exc = pytest.importorskip("mcp.server.mcpserver.exceptions")
ToolError = _exc.ToolError
#: What the SDK raises when a resource template's function fails, whatever the cause.
ResourceReadError = getattr(_exc, "ResourceError", Exception)


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path


@pytest.fixture
def design(rect_design):
    define.create("Rect", rect_design)
    return "Rect"


def payload(result):
    if result.structured_content is not None:
        return result.structured_content
    text = next(c.text for c in result.content if c.type == "text")
    return json.loads(text)


class TestSurface:
    async def test_every_documented_tool_is_registered(self):
        names = {t.name for t in await mcp.server.list_tools()}
        assert {
            "doctor", "list_workspace", "create_design", "get_design", "update_design",
            "add_airfoil", "expand_planform", "analyze", "trim", "sweep", "plot",
            "export", "open_in_flow5",
        } <= names

    async def test_every_tool_has_a_description(self):
        for tool in await mcp.server.list_tools():
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 40, f"{tool.name}'s description is too thin"

    async def test_resources_and_templates(self):
        uris = {str(r.uri) for r in await mcp.server.list_resources()}
        assert {"flow5://status", "flow5://guide/design", "flow5://schema/design"} <= uris
        templates = {t.uri_template for t in await mcp.server.list_resource_templates()}
        assert {"flow5://presets/{name}", "flow5://design/{name}",
                "flow5://results/{name}/{polar}"} <= templates

    async def test_prompts(self):
        names = {p.name for p in await mcp.server.list_prompts()}
        assert {"new_aircraft", "improve_glide", "check_stability",
                "compare_designs"} <= names

    def test_the_instructions_say_what_matters(self):
        text = mcp.INSTRUCTIONS
        assert "flow5://guide/design" in text
        assert "warnings" in text
        # the safety statement is not optional
        assert "carries a person" in text


class TestWorkspaceIsolation:
    """The server must never read or write outside its workspace.

    Called in process, a `ToolError` propagates as an exception; over the protocol the
    SDK turns the same error into a result with `is_error` set and the server stays
    alive. `tests/test_mcp_stdio.py` checks that half.
    """

    @pytest.mark.parametrize("name", [
        "../etc", "../../etc/passwd", "/etc/passwd", "a/b", "..", ".hidden",
        "with\x00null",
    ])
    async def test_a_path_is_not_a_name(self, name):
        with pytest.raises(ToolError, match="not a valid design name"):
            await mcp.server.call_tool("get_design", {"name": name})

    async def test_an_unknown_design_lists_what_exists(self, design):
        with pytest.raises(ToolError, match="Rect"):
            await mcp.server.call_tool("get_design", {"name": "Nope"})


class TestResponses:
    async def test_get_design_returns_derived_geometry(self, design):
        out = payload(await mcp.server.call_tool("get_design", {"name": design}))
        assert out["geometry"]["planform_area"] == pytest.approx(0.4)
        assert out["geometry"]["aspect_ratio"] == pytest.approx(10.0)
        assert "warnings" in out

    async def test_create_design_reports_the_defaults_it_applied(self, rect_design):
        raw = {**rect_design, "preset": "rc-glider"}
        raw.pop("requirements")
        out = payload(await mcp.server.call_tool(
            "create_design", {"name": "Glider", "design": raw}))
        assert any("objective" in d for d in out["defaults_applied"])

    async def test_update_design_takes_a_partial_patch(self, design):
        out = payload(await mcp.server.call_tool(
            "update_design", {"name": design, "patch": {"wing": {"planform": {"taper": 0.5}}}}))
        assert out["geometry"]["taper_ratio"] == pytest.approx(0.5)
        assert out["geometry"]["span"] == pytest.approx(2.0)   # untouched

    async def test_private_fields_are_stripped_from_analyze(self):
        """`_polar_rows` is for the solver iteration, not for a client (ADR-0004)."""
        stripped = mcp._trim({"polar": "x", "_polar_rows": [[1.0]], "_polar_columns": ["CL"]})
        assert stripped == {"polar": "x"}

    async def test_a_sweep_needs_at_least_two_values(self, design):
        with pytest.raises(ToolError, match="at least two"):
            await mcp.server.call_tool(
                "sweep", {"name": design, "parameter": "cg_x", "values": [0.05]})

    async def test_plot_without_an_analysis_says_so(self, design):
        with pytest.raises(ToolError, match="nothing has been analysed"):
            await mcp.server.call_tool("plot", {"name": design, "kind": "polar"})


class TestResources:
    async def test_the_design_guide_is_served(self):
        contents = list(await mcp.server.read_resource("flow5://guide/design"))
        text = contents[0].content
        assert "potential-flow" in text
        # the refusal that matters most must survive both the file and the fallback
        assert "T7" in text

    async def test_the_schema_is_the_real_model(self):
        contents = list(await mcp.server.read_resource("flow5://schema/design"))
        schema = json.loads(contents[0].content)
        assert "wing" in schema["properties"]
        assert "mass" in schema["properties"]

    async def test_a_preset_is_served_with_its_thresholds(self):
        contents = list(await mcp.server.read_resource("flow5://presets/hpa"))
        preset = json.loads(contents[0].content)
        assert preset["name"] == "hpa"
        assert preset["thresholds"]["aspect_ratio"]

    async def test_an_unknown_preset_answers_with_the_real_ones(self):
        """A listing beats a failure here: the protocol reduces a raised error from a
        resource template to "error creating resource", which tells a client nothing."""
        contents = list(await mcp.server.read_resource("flow5://presets/spaceship"))
        body = json.loads(contents[0].content)
        assert "hpa" in body["available"]
        assert "spaceship" in body["error"]

    async def test_an_unknown_design_resource_is_an_error(self):
        with pytest.raises(ResourceReadError):
            await mcp.server.read_resource("flow5://design/Nope")

    async def test_a_design_resource_path_cannot_escape_the_workspace(self):
        with pytest.raises(ResourceReadError):
            await mcp.server.read_resource("flow5://design/..")

    async def test_a_design_is_served_as_yaml(self, design):
        contents = list(await mcp.server.read_resource(f"flow5://design/{design}"))
        assert "schema: flow5ctl/design/1" in contents[0].content


class TestPrompts:
    @pytest.mark.parametrize("name,args", [
        ("new_aircraft", {"kind": "RC glider"}),
        ("improve_glide", {"name": "Rect"}),
        ("check_stability", {"name": "Rect"}),
        ("compare_designs", {"names": "A,B"}),
    ])
    async def test_each_prompt_renders(self, name, args):
        result = await mcp.server.get_prompt(name, args)
        assert result.messages
        assert len(result.messages[0].content.text) > 200

    async def test_the_stability_prompt_carries_the_dutch_roll_caution(self):
        result = await mcp.server.get_prompt("check_stability", {"name": "Rect"})
        text = result.messages[0].content.text
        assert "Dutch-roll" in text or "Dutch roll" in text
        assert "T7" in text

    async def test_the_glide_prompt_warns_about_invisible_costs(self):
        result = await mcp.server.get_prompt("improve_glide", {"name": "Rect"})
        assert "washout" in result.messages[0].content.text


class TestProgressIsBestEffort:
    async def test_no_context_is_not_an_error(self):
        await mcp._progress(None, 1, 2, "half way")

    async def test_a_failing_context_is_swallowed(self):
        class Broken:
            async def report_progress(self, *a, **k):
                raise RuntimeError("no progress token")
        await mcp._progress(Broken(), 1, 2, "half way")


class TestTheGuidesShipInTheWheel:
    """A client installed with `uvx` has no source tree.

    The design guide was read from `../../docs/`, so an installed client got a
    981-character summary of a 28,000-character document - and that document is
    where every measured limit lives, including that no aircraft carrying a person
    should be committed to build on a potential-flow analysis alone. It is the
    reader named by Phase 3's exit criterion who was getting the summary.
    """

    def test_the_english_guide_is_the_real_one(self):
        from flow5ctl.mcp_server import design_guide
        text = design_guide()
        assert len(text) > 15000
        assert "no separation model" in text
        assert "potential-flow analysis alone" in text

    def test_the_japanese_guide_is_the_real_one(self):
        from flow5ctl.mcp_server import design_guide_ja
        text = design_guide_ja()
        assert len(text) > 8000
        assert "設計ガイド" in text

    def test_both_are_force_included_into_the_wheel(self):
        """A build that drops them would fall back silently to the summary."""
        import pathlib
        import tomllib
        root = pathlib.Path(__file__).resolve().parent.parent
        cfg = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        inc = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        assert inc["docs/DESIGN-GUIDE.md"] == "flow5ctl/guides/DESIGN-GUIDE.md"
        assert inc["docs/ja/DESIGN-GUIDE.md"] == "flow5ctl/guides/DESIGN-GUIDE.ja.md"
