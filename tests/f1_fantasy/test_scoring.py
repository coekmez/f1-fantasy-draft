import pytest

from f1_fantasy.models import RaceWeekend
from f1_fantasy.scoring import category_deltas, find_driver, find_constructor, player_season

from ..conftest import FakeClient, make_market, make_player


class TestFindPlayer:
    def test_finds_case_insensitive_partial_match(self, sample_market):
        found = find_driver(sample_market, "verstappen")
        assert found.player_id == "131"

    def test_no_match_raises(self, sample_market):
        with pytest.raises(ValueError, match="No driver found"):
            find_driver(sample_market, "nonexistent")

    def test_ambiguous_match_raises_and_lists_both_names(self):
        market = make_market([
            make_player("1", "Test Driver One", 20.0),
            make_player("2", "Test Driver Two", 15.0),
        ])
        with pytest.raises(ValueError, match="Multiple drivers match"):
            find_driver(market, "test driver")

    def test_only_searches_within_the_given_position(self, sample_market):
        with pytest.raises(ValueError, match="No driver found"):
            find_driver(sample_market, "mercedes")

    def test_find_constructor_only_searches_constructors(self, sample_market):
        found = find_constructor(sample_market, "mercedes")
        assert found.player_id == "28"
        with pytest.raises(ValueError, match="No constructor found"):
            find_constructor(sample_market, "verstappen")


class TestCategoryDeltas:
    def test_first_weekend_diffs_against_zero(self):
        deltas = category_deltas(None, {"fastest_lap_pts": 10.0, "overtaking_pts": 5.0})
        assert deltas == {"fastest_lap_pts": 10.0, "overtaking_pts": 5.0}

    def test_diffs_cumulative_stats_between_weekends(self):
        prev = {"fastest_lap_pts": 10.0, "overtaking_pts": 20.0}
        curr = {"fastest_lap_pts": 10.0, "overtaking_pts": 26.0}

        deltas = category_deltas(prev, curr)

        # fastest_lap_pts delta is 0, so it's excluded entirely
        assert deltas == {"overtaking_pts": 6.0}

    def test_missing_keys_default_to_zero(self):
        assert category_deltas({}, {"dotd_pts": 10.0}) == {"dotd_pts": 10.0}

    def test_unknown_stat_keys_are_ignored(self):
        assert category_deltas(None, {"some_unmodeled_stat": 999.0}) == {}


class TestPlayerSeason:
    def test_skips_incomplete_weekends(self):
        weekends = [
            RaceWeekend(gameday_id="1", name="R1", status=4),
            RaceWeekend(gameday_id="2", name="R2", status=1),  # in progress
            RaceWeekend(gameday_id="3", name="R3", status=0),  # upcoming
        ]
        market1 = make_market([make_player("131", "Max Verstappen", 27.6, gameday_points=25.0)])
        client = FakeClient({"1": market1})

        breakdowns = player_season(client, "131", weekends)

        assert len(breakdowns) == 1
        assert breakdowns[0].weekend.gameday_id == "1"
        assert breakdowns[0].points == 25.0

    def test_skips_weekends_where_the_player_is_absent(self):
        weekends = [
            RaceWeekend(gameday_id="1", name="R1", status=4),
            RaceWeekend(gameday_id="2", name="R2", status=4),
        ]
        market1 = make_market([make_player("131", "Max Verstappen", 27.6, gameday_points=25.0)])
        market2 = make_market([])
        client = FakeClient({"1": market1, "2": market2})

        breakdowns = player_season(client, "131", weekends)

        assert len(breakdowns) == 1

    def test_diffs_categories_across_completed_weekends(self):
        weekends = [
            RaceWeekend(gameday_id="1", name="R1", status=4),
            RaceWeekend(gameday_id="2", name="R2", status=4),
        ]
        market1 = make_market([
            make_player("131", "Max Verstappen", 27.6, gameday_points=25.0, category_stats={"overtaking_pts": 6.0})
        ])
        market2 = make_market([
            make_player("131", "Max Verstappen", 27.9, gameday_points=14.0, category_stats={"overtaking_pts": 38.0})
        ])
        client = FakeClient({"1": market1, "2": market2})

        breakdowns = player_season(client, "131", weekends)

        assert len(breakdowns) == 2
        assert breakdowns[0].categories == {"overtaking_pts": 6.0}
        assert breakdowns[1].categories == {"overtaking_pts": 32.0}
        assert breakdowns[1].points == 14.0
