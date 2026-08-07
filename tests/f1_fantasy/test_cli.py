import argparse
import json

from f1_fantasy import cli as f1_cli
from f1_fantasy.models import RaceWeekend

from ..conftest import FakeClient


def make_args(**kwargs):
    return argparse.Namespace(**kwargs)


class TestCurrentWeek:
    def test_prints_gameday_name_and_status_label(self, monkeypatch, capsys):
        weekends = [
            RaceWeekend(gameday_id="1", name="Australian Grand Prix", status=4),
            RaceWeekend(gameday_id="2", name="Chinese Grand Prix", status=1),
        ]
        client = FakeClient({}, weekends=weekends)
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: client)

        f1_cli._current_week(make_args())

        out = capsys.readouterr().out
        assert "Week 2" in out
        assert "Chinese Grand Prix" in out
        assert "in progress" in out


class TestDriversAndConstructors:
    def test_drivers_lists_only_drivers(self, monkeypatch, capsys, sample_market):
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        f1_cli._drivers(make_args())

        out = capsys.readouterr().out
        assert "Max Verstappen" in out
        assert "Mercedes" not in out

    def test_constructors_lists_only_constructors(self, monkeypatch, capsys, sample_market):
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        f1_cli._constructors(make_args())

        out = capsys.readouterr().out
        assert "Mercedes" in out
        assert "Max Verstappen" not in out


class TestPrices:
    def test_prints_both_groups_sorted_by_price_descending(self, monkeypatch, capsys, sample_market):
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: FakeClient({"12": sample_market}, current_gameday_id="12"))

        f1_cli._prices(make_args())

        out = capsys.readouterr().out
        # George Russell (27.9) is the priciest driver — should appear before Verstappen (27.6)
        assert out.index("George Russell") < out.index("Max Verstappen")
        assert "Drivers:" in out
        assert "Constructors:" in out


class TestScores:
    def test_json_flag_dumps_raw_feed_data(self, monkeypatch, capsys, sample_market):
        weekends = [RaceWeekend(gameday_id="12", name="Dutch Grand Prix", status=1)]
        client = FakeClient({"12": sample_market}, current_gameday_id="12", weekends=weekends)
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: client)

        f1_cli._scores(make_args(driver="verstappen", json=True))

        data = json.loads(capsys.readouterr().out)
        assert data["PlayerId"] == "131"
        assert data["FUllName"] == "Max Verstappen"

    def test_summary_mode_shows_season_total(self, monkeypatch, capsys, sample_market):
        weekends = [RaceWeekend(gameday_id="1", name="Australian Grand Prix", status=4)]
        client = FakeClient({"1": sample_market, "12": sample_market}, current_gameday_id="12", weekends=weekends)
        monkeypatch.setattr(f1_cli, "FantasyClient", lambda: client)

        f1_cli._scores(make_args(driver="verstappen", json=False))

        out = capsys.readouterr().out
        assert "Max Verstappen" in out
        assert "Season total" in out
