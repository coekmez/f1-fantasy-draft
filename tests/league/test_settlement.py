import pytest

from league import settlement

from ..conftest import FakeClient, make_market, make_player


def manager(league, name):
    return next(m for m in league.managers if m.name == name)


@pytest.fixture
def round_market():
    return make_market([
        make_player("131", "Max Verstappen", 27.6, gameday_points=50.0),
        make_player("117", "Lando Norris", 26.1, gameday_points=21.0),
    ], gameday_id="1")


@pytest.fixture
def live_market():
    """The week about to be drafted — where the budget comes from.
    top-2 drivers (all that exist) sum to 53.5, no constructors -> ceil(53.5 / 4) = 14
    """
    return make_market([
        make_player("131", "Max Verstappen", 28.0, gameday_points=0.0),
        make_player("117", "Lando Norris", 25.5, gameday_points=0.0),
    ], gameday_id="2")


def settling_client(round_market, live_market):
    """A client mid-settlement: round 1 is the week just played, round 2 is live."""
    return FakeClient({"1": round_market, "2": live_market}, current_gameday_id="2")


class TestEqualBudget:
    def test_sums_only_the_top_x_drivers_and_y_constructors_then_splits_across_managers(self):
        # num_managers=1 -> X = DRIVER_SLOTS (5), Y = CONSTRUCTOR_SLOTS (2)
        drivers = [make_player(str(i), f"D{i}", price) for i, price in enumerate([50, 40, 30, 20, 10, 5, 1])]
        # top 5 by price: 50, 40, 30, 20, 10 -> sum 150; the 5 and 1 don't count
        constructors = [make_player(f"c{i}", f"C{i}", price, position="CONSTRUCTOR") for i, price in enumerate([100, 80, 10])]
        # top 2: 100, 80 -> sum 180; the 10 doesn't count
        market = make_market(drivers + constructors, gameday_id="2")

        assert settlement.equal_budget(market, num_managers=1) == pytest.approx(150 + 180)

    def test_same_total_sum_produces_a_smaller_budget_for_more_managers(self):
        # only 2 drivers exist, so top-X truncation never kicks in regardless of
        # manager count — but the same total pot gets split among more people
        market = make_market([make_player("1", "D1", 20.0), make_player("2", "D2", 10.0)], gameday_id="2")

        assert settlement.equal_budget(market, num_managers=1) == 30  # (20 + 10) / 1
        assert settlement.equal_budget(market, num_managers=2) == 15  # (20 + 10) / 2

    def test_rounds_up_to_the_next_whole_number(self):
        market = make_market([make_player("1", "D1", 27.6), make_player("2", "D2", 26.1)], gameday_id="2")

        assert settlement.equal_budget(market, num_managers=2) == 27  # ceil((27.6 + 26.1) / 2) = ceil(26.85)

    def test_sums_over_whatever_exists_when_fewer_than_x(self):
        market = make_market([make_player("1", "D1", 10.0)], gameday_id="2")

        assert settlement.equal_budget(market, num_managers=1) == 10  # a single driver -> that's the whole sum

    def test_empty_market_gives_zero(self):
        market = make_market([], gameday_id="2")

        assert settlement.equal_budget(market, num_managers=4) == 0


class TestSellAll:
    def test_no_round_in_progress_raises(self, four_managers, round_market):
        client = FakeClient({"1": round_market})
        with pytest.raises(ValueError, match="nothing to sell"):
            settlement.end_week(four_managers, client)

    def test_live_market_unavailable_raises_and_changes_nothing(self, four_managers, round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money, alice.points = 172.4, 40.0
        alice.roster.drivers.append("131")
        client = FakeClient({"1": round_market}, current_gameday_id="2")  # no "2" fixture

        with pytest.raises(ValueError, match="Could not fetch the current week"):
            settlement.end_week(four_managers, client)

        assert alice.money == 172.4
        assert alice.points == 40.0
        assert alice.roster.drivers == ["131"]
        assert four_managers.round == "1"

    def test_player_missing_from_round_data_raises_and_changes_nothing(self, four_managers, live_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.roster.drivers.append("131")
        empty_round_market = make_market([], gameday_id="1")
        client = FakeClient({"1": empty_round_market, "2": live_market}, current_gameday_id="2")

        with pytest.raises(ValueError, match="not found in round 1"):
            settlement.end_week(four_managers, client)

        assert alice.roster.drivers == ["131"]

    def test_a_held_item_absent_from_the_live_market_still_settles(self, four_managers, round_market):
        # nothing is sold at live prices any more — the budget is a flat figure off the
        # whole market — so a driver who scored last round but has since left the grid
        # must not block settlement.
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.roster.drivers.append("131")  # 50 pts in round 1, absent from the live market
        live = make_market([make_player("117", "Lando Norris", 25.5)], gameday_id="2")
        client = FakeClient({"1": round_market, "2": live}, current_gameday_id="2")

        settlement.end_week(four_managers, client)  # should not raise

        assert alice.points == 50.0
        assert alice.money == pytest.approx(7)  # ceil(25.5 / 4)

    def test_budget_comes_from_the_live_week_not_the_round_after_the_one_sold(self, four_managers, round_market):
        # the league skipped a few weeks: round 1 was drafted, but week 5 is what's live
        # now and what everyone is about to pick from, so that's what the budget must be
        # sized against — picking at week 5 prices on a week 2 budget wouldn't add up.
        four_managers.round = "1"
        week2 = make_market([make_player("131", "Max Verstappen", 8.0)], gameday_id="2")
        week5 = make_market([make_player("131", "Max Verstappen", 80.0)], gameday_id="5")
        client = FakeClient({"1": round_market, "2": week2, "5": week5}, current_gameday_id="5")

        settlement.end_week(four_managers, client)

        assert manager(four_managers, "Alice").money == pytest.approx(20)  # ceil(80 / 4), not ceil(8 / 4)

    def test_credits_points_and_resets_everyone_to_the_same_budget(self, four_managers, round_market, live_market):
        four_managers.round = "1"
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.money, alice.points = 172.4, 40.0
        bob.money = 5.0
        alice.roster.drivers.append("131")  # picked at round 1: 50 pts

        summaries = settlement.end_week(four_managers, settling_client(round_market, live_market))

        assert alice.points == 40.0 + 50.0
        assert alice.money == pytest.approx(14.0)  # the flat budget, not additive with the old 172.4
        assert bob.money == pytest.approx(14.0)  # same flat budget, despite an empty roster
        assert alice.roster.drivers == []
        assert four_managers.round is None
        assert any("Alice" in line and "+50" in line for line in summaries)

    def test_points_are_still_credited_individually(self, four_managers, round_market, live_market):
        four_managers.round = "1"
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.roster.drivers.append("131")  # 50 pts
        bob.roster.drivers.append("117")    # 21 pts
        client = settling_client(round_market, live_market)

        settlement.end_week(four_managers, client)

        assert alice.points == 50.0
        assert bob.points == 21.0

    def test_a_manager_above_the_new_budget_gets_a_negative_delta_formatted_cleanly(self, four_managers, round_market, live_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money = 1000.0  # far above the new budget (14) -> money should still drop to it
        client = settling_client(round_market, live_market)

        summaries = settlement.end_week(four_managers, client)

        assert alice.money == pytest.approx(14.0)
        assert any("Alice: +0 pts, -986 money" == line for line in summaries)


class TestPreviewSell:
    def test_returns_the_predicted_flat_budget_without_changing_anything(self, four_managers, round_market, live_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money = 172.4
        alice.roster.drivers.append("131")
        client = settling_client(round_market, live_market)

        budget = settlement.preview_end_week(four_managers, client)

        assert budget == pytest.approx(14.0)
        # nothing actually happened
        assert alice.money == 172.4
        assert alice.roster.drivers == ["131"]
        assert four_managers.round == "1"

    def test_matches_what_end_week_actually_does(self, four_managers, round_market, live_market):
        # the preview must never drift from reality — that's the whole point
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money = 172.4
        alice.roster.drivers.append("131")
        client = settling_client(round_market, live_market)

        preview = settlement.preview_end_week(four_managers, client)
        settlement.end_week(four_managers, client)

        assert alice.money == pytest.approx(preview)

    def test_no_round_in_progress_raises(self, four_managers, round_market):
        client = FakeClient({"1": round_market})
        with pytest.raises(ValueError, match="nothing to sell"):
            settlement.preview_end_week(four_managers, client)

    def test_live_market_unavailable_raises(self, four_managers, round_market):
        four_managers.round = "1"
        client = FakeClient({"1": round_market}, current_gameday_id="2")  # no "2" fixture
        with pytest.raises(ValueError, match="Could not fetch the current week"):
            settlement.preview_end_week(four_managers, client)


class TestResetAll:
    def test_no_round_in_progress_raises(self, four_managers, round_market):
        client = FakeClient({"1": round_market})
        with pytest.raises(ValueError, match="nothing to reset"):
            settlement.reset_all(four_managers, client)

    def test_player_missing_from_round_data_raises_and_changes_nothing(self, four_managers):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.roster.drivers.append("131")
        empty_round = make_market([], gameday_id="1")
        client = FakeClient({"1": empty_round})

        with pytest.raises(ValueError, match="not found in round 1"):
            settlement.reset_all(four_managers, client)

        assert alice.roster.drivers == ["131"]

    def test_refunds_exact_round_price_and_leaves_points_untouched(self, four_managers, round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money, alice.points = 172.4, 40.0
        alice.roster.drivers.append("131")  # round-1 price 27.6
        client = FakeClient({"1": round_market})

        summaries = settlement.reset_all(four_managers, client)

        assert alice.money == pytest.approx(172.4 + 27.6)
        assert alice.points == 40.0  # untouched
        assert alice.roster.drivers == []
        assert four_managers.round is None
        assert any("+0 pts" in line and "Alice" in line for line in summaries)

    def test_does_not_require_next_round_data(self, four_managers, round_market):
        # unlike end_week, reset only needs the round being reset — no "2" fixture here
        four_managers.round = "1"
        manager(four_managers, "Alice").roster.drivers.append("131")
        client = FakeClient({"1": round_market})

        settlement.reset_all(four_managers, client)  # should not raise

        assert four_managers.round is None
