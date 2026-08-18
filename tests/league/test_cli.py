import argparse

import pytest

from league import cli as league_cli
from league.models import new_league
from league.store import load_league, save_league

from ..conftest import FakeClient


def make_args(**kwargs):
    return argparse.Namespace(**kwargs)


def league_with_money(names=("Alice", "Bob", "Carol", "Dave"), money=200.0):
    league = new_league(list(names))
    for m in league.managers:
        m.money = money
    league.draft_order = list(names)
    return league


class TestPick:
    def test_success_prints_message_and_persists(self, tmp_path, monkeypatch, capsys, sample_market):
        path = tmp_path / "league.json"
        save_league(league_with_money(), path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        league_cli._pick(make_args(path=str(path), manager="Alice", item="verstappen", force=False))

        assert "Alice picks Max Verstappen" in capsys.readouterr().out
        assert load_league(path).managers[0].roster.drivers == ["131"]

    def test_wrong_turn_exits_without_saving(self, tmp_path, monkeypatch, sample_market):
        path = tmp_path / "league.json"
        league = league_with_money(names=("Bob", "Alice", "Carol", "Dave"))
        save_league(league, path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        with pytest.raises(SystemExit, match="turn"):
            league_cli._pick(make_args(path=str(path), manager="Alice", item="verstappen", force=False))

        assert load_league(path).managers[1].roster.drivers == []

    def test_force_bypasses_turn_check(self, tmp_path, monkeypatch, sample_market):
        path = tmp_path / "league.json"
        league = league_with_money(names=("Bob", "Alice", "Carol", "Dave"))
        save_league(league, path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        league_cli._pick(make_args(path=str(path), manager="Alice", item="verstappen", force=True))

        assert load_league(path).managers[1].roster.drivers == ["131"]


class TestStatus:
    def test_prints_standings_round_and_next_picker(self, tmp_path, monkeypatch, capsys, sample_market):
        path = tmp_path / "league.json"
        league = league_with_money()
        league.round = "12"
        league.managers[0].roster.drivers.append("131")
        save_league(league, path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        league_cli._status(make_args(path=str(path)))

        out = capsys.readouterr().out
        assert "Alice" in out
        assert "Max Verstappen" in out  # resolved from the roster's player_id via the market
        assert "Round: 12" in out
        assert "Next to pick: Bob" in out


class TestSell:
    def test_prompt_declined_cancels_without_mutating(self, tmp_path, monkeypatch, capsys):
        path = tmp_path / "league.json"
        league = league_with_money()
        league.round = "1"
        save_league(league, path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({}))
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")

        league_cli._sell(make_args(path=str(path), yes=False))

        assert "Cancelled" in capsys.readouterr().out
        assert load_league(path).round == "1"

    def test_yes_flag_skips_the_prompt(self, tmp_path, monkeypatch, sample_market):
        path = tmp_path / "league.json"
        league = league_with_money()
        league.round = "12"
        save_league(league, path)

        def fail_if_called(prompt=""):
            raise AssertionError("input() should not be called when --yes is set")

        monkeypatch.setattr("builtins.input", fail_if_called)
        # the live week has no data -> settlement.end_week raises ValueError; the point
        # of this test is just that we got past the prompt without input()
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="999"))

        with pytest.raises(SystemExit):
            league_cli._sell(make_args(path=str(path), yes=True))

    def test_successful_sell_writes_a_past_weeks_snapshot(self, tmp_path, monkeypatch, capsys, sample_market):
        next_round_market = FakeClient({"12": sample_market}, current_gameday_id="12").markets["12"]
        path = tmp_path / "league.json"
        league = league_with_money()
        league.round = "12"
        save_league(league, path)
        monkeypatch.setattr(
            league_cli, "FantasyClient",
            lambda: FakeClient({"12": sample_market, "13": next_round_market}, current_gameday_id="12"),
        )

        league_cli._sell(make_args(path=str(path), yes=True))

        snapshot_path = tmp_path / "past_weeks" / "round_12.json"
        assert snapshot_path.exists()
        assert load_league(snapshot_path).round is None  # captures the post-sell, settled state


class TestReset:
    def test_success_refunds_and_prints_summary(self, tmp_path, monkeypatch, capsys, sample_market):
        path = tmp_path / "league.json"
        league = league_with_money(money=172.4)
        league.round = "12"
        league.managers[0].roster.drivers.append("131")
        save_league(league, path)
        monkeypatch.setattr(league_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        league_cli._reset(make_args(path=str(path), yes=True))

        out = capsys.readouterr().out
        assert "Alice" in out
        reloaded = load_league(path)
        assert reloaded.managers[0].roster.drivers == []
        assert reloaded.managers[0].money == pytest.approx(172.4 + 27.6)
        assert reloaded.round is None
