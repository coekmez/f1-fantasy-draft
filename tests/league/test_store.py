import json

from league.models import League, Manager, Roster
from league.store import load_league, save_league, save_round_snapshot


class TestSaveLoadRoundTrip:
    def test_round_trips_all_fields(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(
            managers=[
                Manager(name="Alice", points=80.0, money=172.4, roster=Roster(drivers=["131"], constructors=["29"])),
                Manager(name="Bob", points=60.0, money=200.0, roster=Roster()),
            ],
            draft_order=["Bob", "Alice"],
            round="12",
        )

        save_league(league, path)
        loaded = load_league(path)

        assert [m.name for m in loaded.managers] == ["Alice", "Bob"]
        assert loaded.managers[0].points == 80.0
        assert loaded.managers[0].money == 172.4
        assert loaded.managers[0].roster.drivers == ["131"]
        assert loaded.managers[0].roster.constructors == ["29"]
        assert loaded.draft_order == ["Bob", "Alice"]
        assert loaded.round == "12"

    def test_round_trips_none_round(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=0.0, money=200.0, roster=Roster())])

        save_league(league, path)
        loaded = load_league(path)

        assert loaded.round is None

    def test_saved_file_is_readable_json(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=0.0, money=200.0, roster=Roster())])

        save_league(league, path)

        data = json.loads(path.read_text())
        assert data["managers"][0]["name"] == "Alice"


class TestBackwardCompatLoading:
    def test_loads_legacy_plain_string_roster(self, tmp_path):
        path = tmp_path / "league.json"
        path.write_text(json.dumps({
            "managers": [{
                "name": "Alice",
                "points": 80.0,
                "money": 172.4,
                "roster": {"drivers": ["131"], "constructors": []},
            }],
            "draft_order": ["Alice"],
        }))

        league = load_league(path)

        assert league.managers[0].roster.drivers == ["131"]
        assert league.round is None  # field didn't exist in this old format

    def test_loads_legacy_picked_week_dict_roster(self, tmp_path):
        path = tmp_path / "league.json"
        path.write_text(json.dumps({
            "managers": [{
                "name": "Alice",
                "points": 80.0,
                "money": 172.4,
                "roster": {
                    "drivers": [{"player_id": "131", "picked_week": "1"}],
                    "constructors": [],
                },
            }],
            "draft_order": ["Alice"],
        }))

        league = load_league(path)

        # picked_week metadata is intentionally dropped — only the plain id survives
        assert league.managers[0].roster.drivers == ["131"]

    def test_loads_file_missing_draft_order_and_round_keys(self, tmp_path):
        path = tmp_path / "league.json"
        path.write_text(json.dumps({
            "managers": [{
                "name": "Alice",
                "points": 0.0,
                "money": 200.0,
                "roster": {"drivers": [], "constructors": []},
            }],
        }))

        league = load_league(path)

        assert league.draft_order == []
        assert league.round is None

    def test_mixed_legacy_and_current_entries_in_same_roster(self, tmp_path):
        # Hand-editing or a partial migration could plausibly mix shapes within one roster.
        path = tmp_path / "league.json"
        path.write_text(json.dumps({
            "managers": [{
                "name": "Alice",
                "points": 0.0,
                "money": 200.0,
                "roster": {
                    "drivers": ["131", {"player_id": "117", "picked_week": "2"}],
                    "constructors": [],
                },
            }],
        }))

        league = load_league(path)

        assert league.managers[0].roster.drivers == ["131", "117"]

    def test_ignores_now_obsolete_base_budget_and_budget_delta_keys(self, tmp_path):
        # Briefly-lived fields from an earlier iteration of budget mode — files written
        # during that window still have them; loading should just ignore them.
        path = tmp_path / "league.json"
        path.write_text(json.dumps({
            "managers": [{
                "name": "Alice",
                "points": 0.0,
                "money": 200.0,
                "roster": {"drivers": [], "constructors": []},
                "budget_delta": 22.6,
            }],
            "base_budget": 149.8,
        }))

        league = load_league(path)  # should not raise

        assert league.managers[0].money == 200.0


class TestSaveRoundSnapshot:
    def test_writes_a_snapshot_file_named_for_the_round(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=80.0, money=172.4, roster=Roster())])

        save_round_snapshot(league, path, "12")

        snapshot_path = tmp_path / "past_weeks" / "round_12.json"
        assert snapshot_path.exists()
        loaded = load_league(snapshot_path)
        assert loaded.managers[0].points == 80.0
        assert loaded.managers[0].money == 172.4

    def test_does_not_touch_the_live_league_file(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=0.0, money=200.0, roster=Roster())])
        save_league(league, path)

        save_round_snapshot(league, path, "12")

        assert not (tmp_path / "past_weeks" / "league.json").exists()
        assert load_league(path).managers[0].points == 0.0  # untouched

    def test_a_second_snapshot_for_the_same_round_overwrites_rather_than_duplicates(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=0.0, money=200.0, roster=Roster())])

        save_round_snapshot(league, path, "12")
        league.managers[0].points = 50.0
        save_round_snapshot(league, path, "12")

        snapshot_dir = tmp_path / "past_weeks"
        assert list(snapshot_dir.glob("round_12*.json")) == [snapshot_dir / "round_12.json"]
        assert load_league(snapshot_dir / "round_12.json").managers[0].points == 50.0

    def test_different_rounds_get_separate_snapshot_files(self, tmp_path):
        path = tmp_path / "league.json"
        league = League(managers=[Manager(name="Alice", points=0.0, money=200.0, roster=Roster())])

        save_round_snapshot(league, path, "12")
        save_round_snapshot(league, path, "13")

        snapshot_dir = tmp_path / "past_weeks"
        assert (snapshot_dir / "round_12.json").exists()
        assert (snapshot_dir / "round_13.json").exists()
