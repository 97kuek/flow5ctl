"""The MCP server over real stdio, as Claude Desktop would talk to it.

This is the only test that exercises the whole path — process launch, JSON-RPC
handshake, tool call, image transport — and it is where the properties that only
appear over the wire are checked: that a rejected request comes back as an error
result rather than killing the server, and that a PNG survives base64 transport.

It launches `flow5ctl mcp` as a subprocess, so it needs the package installed.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

import pytest

pytest.importorskip("mcp", reason="the mcp package is not installed")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _command() -> list[str]:
    """Launch the flow5ctl under test, not whichever one is on PATH.

    `shutil.which("flow5ctl")` may well find a different installation — a uvx cache,
    a global install — and then the test measures that instead. The interpreter
    running pytest is by definition the environment under test.
    """
    return [sys.executable, "-m", "flow5ctl", "mcp"]


@asynccontextmanager
async def session(tmp_path):
    """An initialised client against a fresh server.

    Deliberately not a pytest fixture: the client holds anyio cancel scopes, and an
    async-generator fixture enters and exits them in different tasks, which anyio
    rejects. Opening it inside the test body keeps entry and exit together.
    """
    cmd = _command()
    params = StdioServerParameters(
        command=cmd[0], args=cmd[1:],
        env={**os.environ, "FLOW5CTL_WORKSPACE": str(tmp_path / "ws")},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()
        yield s


def _payload(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(next(c.text for c in result.content if c.type == "text"))


class TestHandshake:
    async def test_the_server_identifies_itself(self, tmp_path):
        async with session(tmp_path) as s:
            init = await s.initialize()
            assert init.server_info.name == "flow5ctl"
            # the instructions carry the guardrails; a client that reads nothing else
            # should still be told where the design guide is
            assert "flow5://guide/design" in (init.instructions or "")

    async def test_the_surface_is_advertised(self, tmp_path):
        async with session(tmp_path) as s:
            assert len((await s.list_tools()).tools) >= 13
            assert (await s.list_resources()).resources
            assert (await s.list_resource_templates()).resource_templates
            assert len((await s.list_prompts()).prompts) == 4


class TestOverTheWire:
    async def test_doctor_reports_the_environment(self, tmp_path):
        """Also the check that nothing but protocol reaches stdout: a stray print
        would corrupt the stream and this call would never come back."""
        async with session(tmp_path) as s:
            out = _payload(await s.call_tool("doctor", {}))
            assert "flow5ctl_version" in out
            assert "workspace" in out

    async def test_a_rejected_request_is_a_result_not_a_crash(self, tmp_path):
        """In process this raises; over the protocol it must come back as a result and
        leave the server usable."""
        async with session(tmp_path) as s:
            result = await s.call_tool("get_design", {"name": "../../etc/passwd"})
            assert result.is_error
            assert "not a valid design name" in result.content[0].text
            assert not (await s.call_tool("doctor", {})).is_error

    async def test_an_unknown_tool_is_an_error_not_a_crash(self, tmp_path):
        async with session(tmp_path) as s:
            assert (await s.call_tool("teleport", {})).is_error
            assert not (await s.call_tool("doctor", {})).is_error

    async def test_the_design_guide_is_readable(self, tmp_path):
        async with session(tmp_path) as s:
            contents = (await s.read_resource("flow5://guide/design")).contents
            assert contents[0].mime_type == "text/markdown"
            assert "potential-flow" in contents[0].text

    async def test_a_prompt_renders(self, tmp_path):
        async with session(tmp_path) as s:
            result = await s.get_prompt("check_stability", {"name": "X"})
            assert result.messages[0].content.text


@pytest.mark.needs_flow5
class TestFullFlowOverTheWire:
    @pytest.fixture(autouse=True)
    def _flow5(self):
        from flow5ctl.errors import SolverNotFound
        from flow5ctl.flow5 import probe as probe_mod
        try:
            probe_mod.probe()
        except SolverNotFound as exc:
            pytest.skip(str(exc))

    async def test_create_analyze_and_plot(self, tmp_path, rect_design):
        import base64
        async with session(tmp_path) as s:
            out = _payload(await s.call_tool(
                "create_design", {"name": "Wire", "design": rect_design}))
            assert out["geometry"]["planform_area"] == pytest.approx(0.4)

            out = _payload(await s.call_tool("analyze", {
                "name": "Wire", "polar": "cruise", "type": "T1", "speed": 15.0,
                "alpha": [0, 8, 2], "viscous": False}))
            assert out["points"] == 5
            assert out["summary"]["cl_alpha_per_deg"] == pytest.approx(0.08525, rel=1e-2)
            assert not any(k.startswith("_") for k in out), \
                "private fields reached a client"

            pytest.importorskip("matplotlib", reason="charts need the `plot` extra")
            result = await s.call_tool("plot", {"name": "Wire", "kind": "polar"})
            assert "image" in [c.type for c in result.content]
            image = next(c for c in result.content if c.type == "image")
            assert image.mime_type == "image/png"
            # a real PNG survived base64 transport
            assert base64.b64decode(image.data)[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_the_result_resource_carries_the_full_table(self, tmp_path,
                                                             rect_design):
        async with session(tmp_path) as s:
            await s.call_tool("create_design", {"name": "W2", "design": rect_design})
            await s.call_tool("analyze", {
                "name": "W2", "polar": "p", "type": "T1", "speed": 15.0,
                "alpha": [0, 6, 3], "viscous": False})
            contents = (await s.read_resource("flow5://results/W2/p")).contents
            data = json.loads(contents[0].text)
            assert len(data["columns"]) == 57
            assert len(data["rows"]) == 3
