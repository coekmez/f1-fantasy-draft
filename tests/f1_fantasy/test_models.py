from f1_fantasy.models import Market, Player

from ..conftest import make_feed_entry, make_market, make_player


class TestPlayerFromFeed:
    def test_parses_core_fields(self):
        entry = make_feed_entry("131", "Max Verstappen", 27.6, gameday_points=50.0, season_points=271.0)
        player = Player.from_feed(entry)

        assert player.player_id == "131"
        assert player.name == "Max Verstappen"
        assert player.position == "DRIVER"
        assert player.price == 27.6
        assert player.gameday_points == 50.0
        assert player.season_points == 271.0

    def test_is_driver_and_is_constructor(self):
        driver = Player.from_feed(make_feed_entry("131", "Max Verstappen", 27.6))
        constructor = Player.from_feed(make_feed_entry("29", "Red Bull Racing", 30.9, position="CONSTRUCTOR"))

        assert driver.is_driver is True
        assert driver.is_constructor is False
        assert constructor.is_driver is False
        assert constructor.is_constructor is True

    def test_sessions_with_null_points_are_dropped(self):
        # A non-sprint weekend has no "Sprint Qualifying" session — F1's feed represents
        # that as points=None, not 0. from_feed should drop those, not keep them as 0.
        entry = make_feed_entry(
            "131", "Max Verstappen", 27.6,
            sessions=[
                {"sessionnumber": 1, "sessiontype": "Sprint Qualifying", "points": None, "nonegative_points": None},
                {"sessionnumber": 2, "sessiontype": "Qualifying", "points": 4, "nonegative_points": 4},
                {"sessionnumber": 3, "sessiontype": "Race", "points": 25, "nonegative_points": 25},
            ],
        )
        player = Player.from_feed(entry)

        session_types = [s.session_type for s in player.sessions]
        assert "Sprint Qualifying" not in session_types
        assert session_types == ["Qualifying", "Race"]

    def test_sessions_with_zero_points_are_kept(self):
        entry = make_feed_entry(
            "131", "Max Verstappen", 27.6,
            sessions=[{"sessionnumber": 1, "sessiontype": "Qualifying", "points": 0, "nonegative_points": 0}],
        )
        player = Player.from_feed(entry)

        assert len(player.sessions) == 1
        assert player.sessions[0].points == 0

    def test_raw_dict_is_preserved_for_json_passthrough(self):
        entry = make_feed_entry("131", "Max Verstappen", 27.6)
        entry["SomeUnmodeledField"] = "keep me"
        player = Player.from_feed(entry)

        assert player.raw is entry
        assert player.raw["SomeUnmodeledField"] == "keep me"

    def test_price_and_points_are_coerced_to_float(self):
        entry = make_feed_entry("131", "Max Verstappen", "27.6", gameday_points="50", season_points="271.00")
        player = Player.from_feed(entry)

        assert player.price == 27.6
        assert player.gameday_points == 50.0
        assert player.season_points == 271.0

    def test_player_id_is_coerced_to_a_string(self):
        # regression: the real feed's JSON can carry PlayerId as a number, not a
        # string, despite Player.player_id being typed str — a consumer that actually
        # enforces that type (e.g. a Textual widget id) crashes outright on a raw int
        entry = make_feed_entry(131, "Max Verstappen", 27.6)
        player = Player.from_feed(entry)

        assert player.player_id == "131"
        assert isinstance(player.player_id, str)


class TestMarket:
    def test_by_id_found_and_missing(self, sample_market):
        assert sample_market.by_id("131").name == "Max Verstappen"
        assert sample_market.by_id("nonexistent") is None

    def test_name_of_falls_back_to_id_when_missing(self, sample_market):
        assert sample_market.name_of("131") == "Max Verstappen"
        assert sample_market.name_of("nonexistent") == "nonexistent"

    def test_drivers_and_constructors_are_partitioned_by_position(self, sample_market, sample_drivers, sample_constructors):
        assert {p.player_id for p in sample_market.drivers()} == {p.player_id for p in sample_drivers}
        assert {p.player_id for p in sample_market.constructors()} == {p.player_id for p in sample_constructors}

    def test_iteration_and_len(self, sample_market, sample_drivers, sample_constructors):
        assert len(sample_market) == len(sample_drivers) + len(sample_constructors)
        assert {p.player_id for p in sample_market} == {p.player_id for p in sample_drivers + sample_constructors}

    def test_gameday_id_is_recorded(self):
        market = make_market([make_player("131", "Max Verstappen", 27.6)], gameday_id="7")
        assert market.gameday_id == "7"

    def test_gameday_id_is_coerced_to_a_string(self):
        market = Market([make_player("131", "Max Verstappen", 27.6)], gameday_id=7)
        assert market.gameday_id == "7"
        assert isinstance(market.gameday_id, str)
