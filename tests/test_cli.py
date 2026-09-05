"""The command line, which had no test file of its own.

`cli.py` is the largest module in the package and the least covered, and everything
a person types passes through it. It does not need restructuring — the size is
argparse declarations and a pretty-printer, both inherently long, and the command
functions are small. What it needed was tests for the places where what the user
typed can quietly become something else.
"""
from __future__ import annotations

import pytest

from flow5ctl import cli


class TestNegativeValuesReachTheParser:
    """`--alpha -2,8,2` is rewritten to `--alpha=-2,8,2` before argparse sees it.

    argparse treats any token starting with `-` as an option unless it looks like a
    plain number, and `-2,8,2` does not, so an alpha sweep — which almost always
    starts negative — would fail on nearly every call. The rewrite is the right fix
    and it works; it is pinned here because it edits the user's argv, which is
    exactly the kind of code that can start meaning something else without anyone
    noticing.
    """

    def test_a_negative_range_is_glued_to_its_option(self):
        assert cli._glue_negative_values(["--alpha", "-2,8,2"]) == ["--alpha=-2,8,2"]

    def test_a_bare_negative_number_is_glued(self):
        assert cli._glue_negative_values(["--speed", "-3.5"]) == ["--speed=-3.5"]

    def test_a_following_flag_is_left_alone(self):
        """The dangerous case: gluing here would eat a real option."""
        assert cli._glue_negative_values(["--alpha", "--json"]) == ["--alpha", "--json"]
        assert cli._glue_negative_values(["--alpha", "-v"]) == ["--alpha", "-v"]

    def test_a_trailing_option_with_no_value_is_left_for_argparse_to_reject(self):
        assert cli._glue_negative_values(["--alpha"]) == ["--alpha"]

    def test_an_option_that_takes_no_value_is_never_touched(self):
        assert cli._glue_negative_values(["--viscous", "-2"]) == ["--viscous", "-2"]

    def test_repeated_options_are_each_handled(self):
        assert cli._glue_negative_values(
            ["--alpha", "-2,8,2", "--speed", "-1"]
        ) == ["--alpha=-2,8,2", "--speed=-1"]

    def test_a_positional_carrying_a_negative_is_untouched(self):
        argv = ["set", "Rect", "wing.planform.washout=-2.5"]
        assert cli._glue_negative_values(argv) == argv


class TestTheParserItself:
    def test_json_before_or_after_the_subcommand_both_work(self, tmp_path, monkeypatch):
        """`--json` is declared twice and resolved into one boolean."""
        monkeypatch.setenv("FLOW5CTL_WORKSPACE", str(tmp_path / "ws"))
        ap = cli.build_parser()
        assert ap.parse_args(["--json", "list"]).func is not None
        assert ap.parse_args(["list", "--json"]).json is True

    def test_every_subcommand_has_a_handler(self):
        """A subcommand with no `func` raises AttributeError at run time, not parse."""
        ap = cli.build_parser()
        actions = [a for a in ap._actions if hasattr(a, "choices") and a.choices]
        subparsers = next((a for a in actions if isinstance(a.choices, dict)), None)
        assert subparsers is not None
        for name, sub in subparsers.choices.items():
            assert sub.get_default("func") is not None, f"{name} has no handler"

    def test_an_unknown_example_says_what_exists(self):
        with pytest.raises(Exception) as exc:
            cli.example_path("no-such-example")
        assert "rc-glider" in str(exc.value)
