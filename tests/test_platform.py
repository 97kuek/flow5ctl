"""Guards for the platforms we cannot test.

flow5ctl is verified on macOS only. These keep the platform-dependent seams honest
without a Linux or Windows machine: every platform must offer candidate paths, the
environment override must win, and a missing flow5 must say where it looked.
"""
from __future__ import annotations

import pytest


class TestPlatformIndependence:
    """Guards for the platforms we cannot test. Not marked needs_flow5 on purpose."""

    def test_candidate_paths_are_offered_for_every_platform(self, monkeypatch):
        from flow5ctl.flow5 import probe as p
        for platform in ("darwin", "linux", "win32"):
            monkeypatch.setattr(p.sys, "platform", platform)
            assert p._candidates(), f"no candidate paths for {platform}"

    def test_a_missing_flow5_names_where_it_looked(self, monkeypatch, tmp_path):
        from flow5ctl.errors import SolverNotFound
        from flow5ctl.flow5 import probe as p
        monkeypatch.delenv("FLOW5CTL_FLOW5", raising=False)
        monkeypatch.setattr(p.shutil, "which", lambda _: None)
        monkeypatch.setattr(p, "_candidates", lambda: (str(tmp_path / "nope"),))
        with pytest.raises(SolverNotFound, match="FLOW5CTL_FLOW5"):
            p.find_executable()

    def test_the_env_override_wins(self, monkeypatch, tmp_path):
        from flow5ctl.flow5 import probe as p
        fake = tmp_path / "flow5"
        fake.write_text("#!/bin/sh\n", encoding="utf-8")
        fake.chmod(0o755)
        monkeypatch.setenv("FLOW5CTL_FLOW5", str(fake))
        assert p.find_executable() == fake

    def test_the_version_parser_accepts_the_doubled_name(self):
        """flow5 prints `flow5 flow5 v7.57`."""
        from flow5ctl.flow5.probe import _VERSION_RE
        m = _VERSION_RE.search("flow5 flow5 v7.57")
        assert m and f"{m.group(1)}.{m.group(2)}" == "7.57"
