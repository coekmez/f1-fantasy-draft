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
def next_round_market():
    return make_market([
        make_player("131", "Max Verstappen", 28.0, gameday_points=0.0),
        make_player("117", "Lando Norris", 25.5, gameday_points=0.0),
    ], gameday_id="2")


class TestSellAll:
    def test_no_round_in_progress_raises(self, four_managers, round_market):
        client = FakeClient({"1": round_market})
        with pytest.raises(ValueError, match="nothing to sell"):
            settlement.sell_all(four_managers, client)

    def test_next_round_unavailable_raises_and_changes_nothing(self, four_managers, round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money, alice.points = 172.4, 40.0
        alice.roster.drivers.append("131")
        client = FakeClient({"1": round_market})  # no "2" fixture

        with pytest.raises(ValueError, match="Could not fetch round 2"):
            settlement.sell_all(four_managers, client)

        assert alice.money == 172.4
        assert alice.points == 40.0
        assert alice.roster.drivers == ["131"]
        assert four_managers.round == "1"

    def test_player_missing_from_round_data_raises_and_changes_nothing(self, four_managers, next_round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.roster.drivers.append("131")
        empty_round_market = make_market([], gameday_id="1")
        client = FakeClient({"1": empty_round_market, "2": next_round_market})

        with pytest.raises(ValueError, match="not found in round 1"):
            settlement.sell_all(four_managers, client)

        assert alice.roster.drivers == ["131"]

    def test_player_missing_from_next_round_data_raises_and_changes_nothing(self, four_managers, round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.roster.drivers.append("131")
        empty_next_round = make_market([], gameday_id="2")
        client = FakeClient({"1": round_market, "2": empty_next_round})

        with pytest.raises(ValueError, match="not found in round 2"):
            settlement.sell_all(four_managers, client)

        assert alice.roster.drivers == ["131"]

    def test_credits_points_from_round_and_price_from_next_round(self, four_managers, round_market, next_round_market):
        four_managers.round = "1"
        alice = manager(four_managers, "Alice")
        alice.money, alice.points = 172.4, 40.0
        alice.roster.drivers.append("131")  # picked at round 1: 50 pts, round-2 price 28.0
        client = FakeClient({"1": round_market, "2": next_round_market})

        summaries = settlement.sell_all(four_managers, client)

        assert alice.points == 40.0 + 50.0
        assert alice.money == pytest.approx(172.4 + 28.0)
        assert alice.roster.drivers == []
        assert four_managers.round is None
        assert any("Alice" in line and "+50" in line for line in summaries)

    def test_settles_every_manager_independently(self, four_managers, round_market, next_round_market):
        four_managers.round = "1"
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.roster.drivers.append("131")
        bob.roster.drivers.append("117")
        client = FakeClient({"1": round_market, "2": next_round_market})

        settlement.sell_all(four_managers, client)

        assert alice.points == 50.0
        assert bob.points == 21.0
        assert alice.money == pytest.approx(28.0)
        assert bob.money == pytest.approx(25.5)

    def test_manager_with_empty_roster_gets_zero_deltas(self, four_managers, round_market, next_round_market):
        four_managers.round = "1"
        client = FakeClient({"1": round_market, "2": next_round_market})

        settlement.sell_all(four_managers, client)

        for m in four_managers.managers:
            assert m.points == 0.0
            assert m.money == 0.0


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
        # unlike sell_all, reset only needs the round being reset — no "2" fixture here
        four_managers.round = "1"
        manager(four_managers, "Alice").roster.drivers.append("131")
        client = FakeClient({"1": round_market})

        settlement.reset_all(four_managers, client)  # should not raise

        assert four_managers.round is None
