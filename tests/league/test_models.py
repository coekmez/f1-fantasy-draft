from league.models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, League, Manager, Roster, new_league


class TestRoster:
    def test_empty_roster_is_not_full(self):
        assert Roster().is_full is False

    def test_full_when_both_slot_types_are_at_capacity(self):
        roster = Roster(drivers=[str(i) for i in range(DRIVER_SLOTS)], constructors=[str(i) for i in range(CONSTRUCTOR_SLOTS)])
        assert roster.is_full is True

    def test_not_full_if_only_drivers_are_at_capacity(self):
        roster = Roster(drivers=[str(i) for i in range(DRIVER_SLOTS)], constructors=[])
        assert roster.is_full is False

    def test_player_ids_combines_both_slot_types(self):
        roster = Roster(drivers=["131", "117"], constructors=["29"])
        assert roster.player_ids() == ["131", "117", "29"]

    def test_player_ids_empty_when_roster_empty(self):
        assert Roster().player_ids() == []


class TestNewLeague:
    def test_creates_one_manager_per_name(self):
        league = new_league(["Alice", "Bob", "Carol", "Dave"])
        assert [m.name for m in league.managers] == ["Alice", "Bob", "Carol", "Dave"]

    def test_managers_start_at_zero_points_and_money_with_empty_rosters(self):
        league = new_league(["Alice"])
        manager = league.managers[0]
        assert manager.points == 0.0
        assert manager.money == 0.0
        assert manager.roster.drivers == []
        assert manager.roster.constructors == []

    def test_draft_order_and_round_start_unset(self):
        league = new_league(["Alice", "Bob"])
        assert league.draft_order == []
        assert league.round is None
