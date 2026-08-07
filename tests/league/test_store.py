import json

from league.models import League, Manager, Roster
from league.store import load_league, save_league


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
