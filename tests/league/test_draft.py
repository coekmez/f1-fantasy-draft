import pytest

from league import draft
from league.models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS

from ..conftest import FakeClient, make_market, make_player


def manager(league, name):
    return next(m for m in league.managers if m.name == name)


class TestComputeDraftOrder:
    def test_least_points_goes_first(self, four_managers):
        manager(four_managers, "Alice").points = 80
        manager(four_managers, "Bob").points = 60
        manager(four_managers, "Carol").points = 100
        manager(four_managers, "Dave").points = 40

        order = draft.compute_draft_order(four_managers)

        assert order == ["Dave", "Bob", "Alice", "Carol"]

    def test_ties_broken_by_name(self, four_managers):
        for m in four_managers.managers:
            m.points = 50

        order = draft.compute_draft_order(four_managers)

        assert order == ["Alice", "Bob", "Carol", "Dave"]


class TestWhoseTurn:
    def test_starts_at_draft_order_zero(self, four_managers):
        four_managers.draft_order = ["Dave", "Bob", "Alice", "Carol"]
        assert draft.whose_turn(four_managers).name == "Dave"

    def test_repeats_circularly_not_snake(self, four_managers):
        four_managers.draft_order = ["Dave", "Bob", "Alice", "Carol"]
        # one pick each for Dave, Bob, Alice, Carol -> should wrap back to Dave, not reverse
        for name in ["Dave", "Bob", "Alice", "Carol"]:
            manager(four_managers, name).roster.drivers.append(f"driver-{name}")

        assert draft.whose_turn(four_managers).name == "Dave"

    def test_returns_none_when_every_roster_is_full(self, four_managers):
        four_managers.draft_order = ["Alice", "Bob", "Carol", "Dave"]
        for m in four_managers.managers:
            m.roster.drivers = [f"d{i}" for i in range(DRIVER_SLOTS)]
            m.roster.constructors = [f"c{i}" for i in range(CONSTRUCTOR_SLOTS)]

        assert draft.whose_turn(four_managers) is None


class TestIsOwned:
    def test_true_when_any_manager_owns_it(self, four_managers):
        manager(four_managers, "Bob").roster.drivers.append("131")
        assert draft.is_owned(four_managers, "131") is True

    def test_false_when_nobody_owns_it(self, four_managers):
        assert draft.is_owned(four_managers, "131") is False


class TestFindItem:
    def test_matches_across_drivers_and_constructors(self, sample_market):
        assert draft.find_item(sample_market, "verstappen").player_id == "131"
        assert draft.find_item(sample_market, "mercedes").player_id == "28"

    def test_no_match_raises(self, sample_market):
        with pytest.raises(ValueError, match="No driver or constructor found"):
            draft.find_item(sample_market, "nonexistent")

    def test_ambiguous_match_raises(self):
        market = make_market([
            make_player("1", "Test One", 10.0),
            make_player("2", "Test Two", 10.0, position="CONSTRUCTOR"),
        ])
        with pytest.raises(ValueError, match="Multiple matches"):
            draft.find_item(market, "test")


class TestApplyPick:
    def _turn_manager(self, league):
        return draft.whose_turn(league)

    def test_deducts_price_and_adds_to_roster(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 200.0
        item = sample_market.by_id("131")

        message = draft.apply_pick(four_managers, picker, item, "12")

        assert picker.roster.drivers == ["131"]
        assert picker.money == pytest.approx(200.0 - 27.6)
        assert "picks Max Verstappen" in message

    def test_sets_round_on_first_pick_only(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 200.0

        draft.apply_pick(four_managers, picker, sample_market.by_id("131"), "12")
        assert four_managers.round == "12"

        next_picker = self._turn_manager(four_managers)
        next_picker.money = 200.0
        draft.apply_pick(four_managers, next_picker, sample_market.by_id("117"), "13")

        # round doesn't change even though a different "current_week" was passed
        assert four_managers.round == "12"

    def test_wrong_turn_without_force_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        turn = self._turn_manager(four_managers)
        not_turn = next(m for m in four_managers.managers if m.name != turn.name)
        not_turn.money = 200.0

        with pytest.raises(ValueError, match="turn"):
            draft.apply_pick(four_managers, not_turn, sample_market.by_id("131"), "12")

    def test_wrong_turn_with_force_succeeds(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        turn = self._turn_manager(four_managers)
        not_turn = next(m for m in four_managers.managers if m.name != turn.name)
        not_turn.money = 200.0

        draft.apply_pick(four_managers, not_turn, sample_market.by_id("131"), "12", force=True)

        assert not_turn.roster.drivers == ["131"]

    def test_already_owned_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 200.0
        other = next(m for m in four_managers.managers if m.name != picker.name)
        other.roster.drivers.append("131")

        with pytest.raises(ValueError, match="already been picked"):
            draft.apply_pick(four_managers, picker, sample_market.by_id("131"), "12", force=True)

    def test_driver_slot_full_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 200.0
        picker.roster.drivers = [f"d{i}" for i in range(DRIVER_SLOTS)]

        # filling slots as test setup shifts whose_turn() (it's derived from roster
        # sizes) — force past the turn check to isolate the slot-full validation
        with pytest.raises(ValueError, match="already full"):
            draft.apply_pick(four_managers, picker, sample_market.by_id("131"), "12", force=True)

    def test_constructor_slot_full_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 200.0
        picker.roster.constructors = [f"c{i}" for i in range(CONSTRUCTOR_SLOTS)]

        with pytest.raises(ValueError, match="already full"):
            draft.apply_pick(four_managers, picker, sample_market.by_id("29"), "12", force=True)

    def test_insufficient_funds_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = self._turn_manager(four_managers)
        picker.money = 5.0

        with pytest.raises(ValueError, match="cannot afford"):
            draft.apply_pick(four_managers, picker, sample_market.by_id("131"), "12")

    def test_draft_complete_raises(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        for m in four_managers.managers:
            m.roster.drivers = [f"d{i}" for i in range(DRIVER_SLOTS)]
            m.roster.constructors = [f"c{i}" for i in range(CONSTRUCTOR_SLOTS)]
        picker = four_managers.managers[0]
        picker.money = 200.0

        with pytest.raises(ValueError, match="complete"):
            draft.apply_pick(four_managers, picker, sample_market.by_id("131"), "12", force=True)


class TestMakePick:
    def test_delegates_to_apply_pick(self, four_managers, sample_market):
        four_managers.draft_order = draft.compute_draft_order(four_managers)
        picker = draft.whose_turn(four_managers)
        picker.money = 200.0
        client = FakeClient({"12": sample_market}, current_gameday_id="12")

        message = draft.make_pick(four_managers, client, picker.name, "verstappen")

        assert picker.roster.drivers == ["131"]
        assert "picks Max Verstappen" in message

    def test_unknown_manager_raises(self, four_managers, sample_market):
        client = FakeClient({"12": sample_market}, current_gameday_id="12")
        with pytest.raises(ValueError, match="No manager named"):
            draft.make_pick(four_managers, client, "Nobody", "verstappen")


class TestTrade:
    def test_cannot_trade_with_yourself(self, four_managers, sample_market):
        alice = manager(four_managers, "Alice")
        with pytest.raises(ValueError, match="yourself"):
            draft.trade(four_managers, sample_market, alice, alice, "131")

    def test_nothing_to_trade_raises(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        with pytest.raises(ValueError, match="Nothing to trade"):
            draft.trade(four_managers, sample_market, alice, bob)

    def test_driver_for_driver_swap_adjusts_money_by_value_difference(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.money = 200.0
        bob.money = 200.0
        alice.roster.drivers.append("131")  # Verstappen, 27.6
        bob.roster.drivers.append("117")    # Norris, 26.1

        draft.trade(four_managers, sample_market, alice, bob, "131", "117")

        assert alice.roster.drivers == ["117"]
        assert bob.roster.drivers == ["131"]
        assert alice.money == pytest.approx(200.0 + 27.6 - 26.1)
        assert bob.money == pytest.approx(200.0 + 26.1 - 27.6)

    def test_category_mismatch_rejected(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.roster.drivers.append("131")
        bob.roster.constructors.append("29")

        with pytest.raises(ValueError, match="driver for a driver"):
            draft.trade(four_managers, sample_market, alice, bob, "131", "29")

    def test_one_sided_gift_within_cap_succeeds(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.money = 200.0
        bob.money = 200.0
        alice.roster.drivers.append("131")

        draft.trade(four_managers, sample_market, alice, bob, give_a="131")

        assert alice.roster.drivers == []
        assert bob.roster.drivers == ["131"]
        assert alice.money == pytest.approx(200.0 + 27.6)
        assert bob.money == pytest.approx(200.0 - 27.6)

    def test_one_sided_gift_exceeding_cap_rejected(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.roster.drivers.append("131")
        bob.roster.drivers = [f"d{i}" for i in range(DRIVER_SLOTS)]
        bob.money = 200.0

        with pytest.raises(ValueError, match="slot limit"):
            draft.trade(four_managers, sample_market, alice, bob, give_a="131")

    def test_insufficient_funds_on_receiving_side_rejected(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.roster.drivers.append("131")  # 27.6
        bob.money = 5.0

        with pytest.raises(ValueError, match="does not have enough money"):
            draft.trade(four_managers, sample_market, alice, bob, give_a="131")

    def test_trading_unowned_item_raises(self, four_managers, sample_market):
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        with pytest.raises(ValueError, match="does not own"):
            draft.trade(four_managers, sample_market, alice, bob, give_a="131")

    def test_trade_does_not_touch_turn_order_or_round(self, four_managers, sample_market):
        four_managers.draft_order = ["Dave", "Bob", "Alice", "Carol"]
        four_managers.round = "12"
        alice, bob = manager(four_managers, "Alice"), manager(four_managers, "Bob")
        alice.money, bob.money = 200.0, 200.0
        alice.roster.drivers.append("131")

        draft.trade(four_managers, sample_market, alice, bob, give_a="131")

        assert four_managers.draft_order == ["Dave", "Bob", "Alice", "Carol"]
        assert four_managers.round == "12"
