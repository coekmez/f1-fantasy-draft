import pytest
from textual.containers import Grid
from textual.widgets import OptionList, RichLog, Static

from league.store import load_league, save_league
from league.tui import ConfirmResetScreen, ConfirmSellScreen, DraftApp

from ..conftest import FakeClient, make_market, make_player


def log_text(app) -> str:
    return "".join(strip.text for strip in app.query_one("#event-log", RichLog).lines)


@pytest.fixture
def league_path(tmp_path, four_managers):
    path = tmp_path / "league.json"
    for m in four_managers.managers:
        m.money = 200.0
    four_managers.draft_order = ["Dave", "Bob", "Alice", "Carol"]  # Dave (managers[3]) picks first
    save_league(four_managers, path)
    return path


@pytest.fixture
def market():
    return make_market([
        make_player("131", "Max Verstappen", 27.6, gameday_points=50.0),
        make_player("117", "Lando Norris", 26.1, gameday_points=21.0),
        make_player("124", "George Russell", 27.9, gameday_points=25.0),
        make_player("29", "Red Bull Racing", 30.9, position="CONSTRUCTOR", gameday_points=45.0),
        make_player("28", "Mercedes", 32.6, position="CONSTRUCTOR", gameday_points=40.0),
    ], gameday_id="12")


def make_app(league_path, market, client=None):
    league = load_league(league_path)
    return DraftApp(league, league_path, market, client or FakeClient({"12": market}, current_gameday_id="12"))


class TestPoolAndPicking:
    async def test_pool_lists_populate_sorted_by_price_descending(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            drivers = app.query_one("#pool-drivers", OptionList)
            constructors = app.query_one("#pool-constructors", OptionList)

            assert drivers.option_count == 3
            assert drivers.get_option_at_index(0).prompt.strip().endswith("George Russell")  # 27.9, highest
            assert constructors.option_count == 2
            assert constructors.get_option_at_index(0).prompt.strip().endswith("Mercedes")  # 32.6, highest

    async def test_picking_deducts_price_updates_roster_and_sets_round(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")  # least points -> first turn
            assert dave.roster.drivers == ["124"]  # George Russell, top of the list
            assert dave.money == pytest.approx(200.0 - 27.9)
            assert app.league.round == "12"

    async def test_focus_stays_in_the_pane_the_pick_was_made_from(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert app.focused is drivers
            # picking index 0 must not leave the highlight sitting on that now-disabled
            # row — no visible cursor there looks exactly like focus left the pane
            assert drivers.highlighted is not None
            assert drivers.get_option_at_index(drivers.highlighted).disabled is False

    async def test_highlight_never_lands_on_a_disabled_option_after_refresh(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()

            # pick all three drivers in sequence, from index 0 each time (turn moves
            # to a different manager each time, but the highlight target stays put)
            for _ in range(3):
                await pilot.press("enter")
                await pilot.pause()
                if drivers.highlighted is not None:
                    assert drivers.get_option_at_index(drivers.highlighted).disabled is False

    async def test_picked_item_stays_listed_struck_through_and_disabled(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")  # picks George Russell (124), top of the list
            await pilot.pause()

            assert drivers.option_count == 3  # still listed, not removed
            picked = drivers.get_option_at_index(0)
            assert picked.id == "124"
            assert picked.disabled is True
            assert "[strike]" in picked.prompt

    async def test_picking_auto_advances_highlight_past_the_disabled_row(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()

            await pilot.press("enter")  # Dave picks index 0 (George Russell)
            await pilot.pause()

            # landing the highlight on the just-picked (disabled) row would show no
            # visible cursor at all, which looks exactly like focus left the pane
            assert drivers.highlighted == 1
            assert drivers.get_option_at_index(1).id != "124"

    async def test_arrow_navigation_skips_over_a_disabled_row(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()

            # sorted by price desc: index0=Russell(124), index1=Verstappen(131), index2=Norris(117)
            drivers.highlighted = 1  # Verstappen, the middle item
            await pilot.pause()
            await pilot.press("enter")  # Dave picks Verstappen -> index 1 becomes disabled
            await pilot.pause()

            # move back to the row just before the disabled one, then navigate down —
            # OptionList's own cursor movement should skip straight over index 1
            drivers.highlighted = 0
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()

            assert drivers.highlighted == 2
            assert drivers.get_option_at_index(2).id == "117"  # Norris — index 1 (Verstappen) was skipped

    async def test_enter_on_a_picked_item_does_nothing(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")  # Dave picks George Russell
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            bob = next(m for m in app.league.managers if m.name == "Bob")
            drivers.highlighted = 0  # force the highlight back onto the disabled row
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # nothing changed — it's Bob's turn now, and the picked item is untouched
            assert dave.roster.drivers == ["124"]
            assert bob.roster.drivers == []

    async def test_owned_item_does_not_drive_the_budget_preview(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # force the highlight back onto the now-disabled, just-picked item, then
            # refresh — this is what OptionHighlighted's handler does on a real
            # keypress; calling it directly keeps the test deterministic rather than
            # depending on message-loop timing in the headless harness
            drivers.highlighted = 0
            app.refresh_managers()

            assert app.highlighted_item is None
            header = str(app.query_one("#manager-header-m1", Static).render())  # Bob, on the clock now
            assert "▶" not in header

    async def test_budget_preview_updates_as_highlight_moves(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("down")  # move off the first (already-default-highlighted) item
            await pilot.pause()

            assert app.highlighted_item is not None
            header = str(app.query_one("#manager-header-m3", Static).render())  # Dave is managers[3], first turn
            assert f'▶ {200.0 - app.highlighted_item.price:g}' in header

    async def test_empty_roster_shows_placeholder_dashes(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            header = str(app.query_one("#manager-header-m0", Static).render())  # Alice, untouched
            assert "Starting budget" not in header

            roster = app.query_one("#manager-roster-m0", OptionList)
            dashes = sum(
                1 for i in range(roster.option_count)
                if roster.get_option_at_index(i).prompt.strip() == "—"
            )
            assert dashes == 7  # 5 driver slots + 2 constructor slots


class TestTrade:
    async def test_pressing_t_enables_and_focuses_manager_rosters(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            alice = next(m for m in app.league.managers if m.name == "Alice")
            alice.roster.drivers.append("131")
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            assert app.trade_mode is True
            alice_roster = app.query_one("#manager-roster-m0", OptionList)
            assert app.focused is alice_roster
            assert alice_roster.get_option_at_index(1).disabled is False  # filled slot -> interactive now
            assert "select the first slot" in log_text(app)

    async def test_empty_slots_stay_disabled_even_in_trade_mode(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()

            # Alice's roster is untouched — every slot is empty, so none of them
            # should become selectable just because trade mode turned on
            alice_roster = app.query_one("#manager-roster-m0", OptionList)
            for i in range(1, 6):
                assert alice_roster.get_option_at_index(i).disabled is True

            alice_roster.highlighted = 1
            await pilot.pause()
            await pilot.press("enter")  # should do nothing — the option is disabled
            await pilot.pause()

            assert app.trade_first is None
            assert app.trade_mode is True  # nothing happened, still waiting for a real first pick

    async def test_escape_cancels_before_any_slot_is_chosen(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            dave.roster.drivers.append("131")
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()
            assert app.query_one("#manager-roster-m3", OptionList).get_option_at_index(1).disabled is False

            await pilot.press("escape")
            await pilot.pause()

            assert app.trade_mode is False
            assert "Trade cancelled" in log_text(app)
            # slots go back to being inert/non-interactive once trade mode ends
            assert app.query_one("#manager-roster-m3", OptionList).get_option_at_index(1).disabled is True

    async def test_selecting_the_same_slot_twice_cancels(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            dave.roster.drivers.append("131")
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            dave_roster = app.query_one("#manager-roster-m3", OptionList)
            dave_roster.focus()
            dave_roster.highlighted = 1  # Dave's first driver slot
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")  # the same slot again
            await pilot.pause()

            assert app.trade_mode is False
            assert app.trade_first is None
            assert dave.roster.drivers == ["131"]  # untouched
            assert "Trade cancelled" in log_text(app)

    async def test_swap_between_two_managers_adjusts_money_by_value_difference(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            bob = next(m for m in app.league.managers if m.name == "Bob")
            dave.roster.drivers.append("131")  # Verstappen 27.6
            bob.roster.drivers.append("117")   # Norris 26.1
            dave.money = 172.4
            bob.money = 173.9
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            dave_roster = app.query_one("#manager-roster-m3", OptionList)
            dave_roster.focus()
            dave_roster.highlighted = 1  # Dave's first (only) driver slot: Verstappen
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            bob_roster = app.query_one("#manager-roster-m1", OptionList)
            bob_roster.focus()
            bob_roster.highlighted = 1  # Bob's first (only) driver slot: Norris
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert dave.roster.drivers == ["117"]
            assert bob.roster.drivers == ["131"]
            assert dave.money == pytest.approx(172.4 + 27.6 - 26.1)
            assert bob.money == pytest.approx(173.9 + 26.1 - 27.6)
            assert app.trade_mode is False
            assert "Trade complete between Dave and Bob" in log_text(app)

    async def test_empty_slot_is_not_selectable_as_the_second_pick(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            bob = next(m for m in app.league.managers if m.name == "Bob")
            dave.roster.drivers.append("131")  # Verstappen 27.6
            dave.money = 172.4
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            dave_roster = app.query_one("#manager-roster-m3", OptionList)
            dave_roster.focus()
            dave_roster.highlighted = 1
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            bob_roster = app.query_one("#manager-roster-m1", OptionList)
            assert bob_roster.get_option_at_index(1).disabled is True  # Bob's driver slot is empty

            bob_roster.focus()
            bob_roster.highlighted = 1
            await pilot.pause()
            await pilot.press("enter")  # should do nothing — the option is disabled
            await pilot.pause()

            assert dave.roster.drivers == ["131"]  # nothing moved
            assert bob.roster.drivers == []
            assert app.trade_first is not None  # first pick is still waiting on a valid second slot

    async def test_mismatched_category_slots_are_not_selectable_for_the_second_pick(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            bob = next(m for m in app.league.managers if m.name == "Bob")
            dave.roster.drivers.append("131")
            bob.roster.constructors.append("29")
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            dave_roster = app.query_one("#manager-roster-m3", OptionList)
            dave_roster.focus()
            dave_roster.highlighted = 1  # Dave's driver slot
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            bob_roster = app.query_one("#manager-roster-m1", OptionList)
            assert bob_roster.get_option_at_index(7).disabled is True  # constructor, doesn't match "drivers"

            bob_roster.focus()
            bob_roster.highlighted = 7
            await pilot.pause()
            await pilot.press("enter")  # should do nothing — the option is disabled
            await pilot.pause()

            assert app.trade_mode is True  # still active — free to pick a different second slot
            assert app.trade_first is not None
            assert dave.roster.drivers == ["131"]  # nothing actually moved
            assert bob.roster.constructors == ["29"]

    async def test_hovering_the_second_choice_previews_both_managers_budget_change(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            bob = next(m for m in app.league.managers if m.name == "Bob")
            dave.roster.drivers.append("131")  # Verstappen 27.6
            bob.roster.drivers.append("117")   # Norris 26.1
            dave.money = 172.4
            bob.money = 173.9
            app.refresh_managers()

            await pilot.press("t")
            await pilot.pause()

            dave_roster = app.query_one("#manager-roster-m3", OptionList)
            dave_roster.focus()
            dave_roster.highlighted = 1
            await pilot.pause()
            await pilot.press("enter")  # Dave's Verstappen becomes the first pick

            dave_header_before = str(app.query_one("#manager-header-m3", Static).render())
            bob_header_before = str(app.query_one("#manager-header-m1", Static).render())
            assert "▶" not in dave_header_before  # nothing hovered as a second slot yet
            assert "▶" not in bob_header_before

            bob_roster = app.query_one("#manager-roster-m1", OptionList)
            bob_roster.focus()
            await pilot.pause()  # .focused isn't updated synchronously right after .focus()
            bob_roster.highlighted = 1  # hover over Bob's Norris — don't select yet
            app.refresh_managers()

            dave_header = str(app.query_one("#manager-header-m3", Static).render())
            bob_header = str(app.query_one("#manager-header-m1", Static).render())
            assert f'▶ {172.4 + 27.6 - 26.1:g}' in dave_header
            assert f'▶ {173.9 + 26.1 - 27.6:g}' in bob_header

            # nothing has actually traded yet — this is only a preview
            assert dave.roster.drivers == ["131"]
            assert bob.roster.drivers == ["117"]

    async def test_pool_pick_is_blocked_while_trade_mode_is_active(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()

            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()  # simulates a direct click into the pool while mid-trade
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            assert dave.roster.drivers == []  # the pick never went through
            assert "Finish or cancel the trade first" in log_text(app)


class TestSell:
    async def test_cancel_is_a_no_op(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmSellScreen)
            await pilot.click("#cancel")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            assert dave.roster.drivers == ["124"]
            assert app.league.round == "12"

    async def test_confirm_credits_points_and_price_then_clears_round(self, league_path, market):
        next_round_market = make_market([
            make_player("124", "George Russell", 29.0, gameday_points=0.0),
        ], gameday_id="13")
        client = FakeClient({"12": market, "13": next_round_market}, current_gameday_id="12")
        app = make_app(league_path, market, client=client)

        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")  # Dave picks George Russell (124), 25 pts at round 12
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            points_before = dave.points

            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#confirm")
            await pilot.pause()

            assert dave.points == points_before + 25.0
            assert dave.money == pytest.approx(200.0 - 27.9 + 29.0)
            assert dave.roster.drivers == []
            assert app.league.round is None


class TestReset:
    async def test_confirm_refunds_exact_price_and_leaves_points_untouched(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            points_before = dave.points

            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmResetScreen)
            await pilot.click("#confirm")
            await pilot.pause()

            assert dave.money == pytest.approx(200.0)
            assert dave.points == points_before
            assert dave.roster.drivers == []
            assert app.league.round is None


class TestUndoRedo:
    async def test_undo_refunds_and_removes_pick(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            assert dave.roster.drivers == ["124"]

            await pilot.press("u")
            await pilot.pause()

            assert dave.roster.drivers == []
            assert dave.money == pytest.approx(200.0)
            assert app.league.round is None  # last pick undone -> round clears too

    async def test_redo_reapplies_the_undone_pick(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()

            await pilot.press("U")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            assert dave.roster.drivers == ["124"]
            assert dave.money == pytest.approx(200.0 - 27.9)
            assert app.league.round == "12"

    async def test_blocked_redo_keeps_action_queued_instead_of_discarding_it(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()

            # someone else grabs the same item before the redo happens
            bob = next(m for m in app.league.managers if m.name == "Bob")
            bob.roster.drivers.append("124")

            await pilot.press("U")
            await pilot.pause()

            dave = next(m for m in app.league.managers if m.name == "Dave")
            assert dave.roster.drivers == []  # redo was correctly blocked
            assert len(app.redo_stack) == 1   # and the action wasn't silently discarded

    async def test_sell_clears_undo_and_redo_stacks(self, league_path, market):
        next_round_market = make_market([make_player("124", "George Russell", 29.0)], gameday_id="13")
        client = FakeClient({"12": market, "13": next_round_market}, current_gameday_id="12")
        app = make_app(league_path, market, client=client)

        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.undo_stack) == 1

            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#confirm")
            await pilot.pause()

            assert app.undo_stack == []
            assert app.redo_stack == []


class TestFixedLayout:
    async def test_body_stays_fixed_size_across_resizes(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test(size=(220, 90)) as pilot:
            body = app.query_one("#body")
            initial_size = body.size

            await pilot.resize_terminal(300, 120)
            await pilot.pause()
            assert body.size == initial_size

            await pilot.resize_terminal(100, 40)
            await pilot.pause()
            assert body.size == initial_size

    async def test_body_is_centered_when_terminal_has_room(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test(size=(220, 90)):
            body = app.query_one("#body")
            assert body.region.x > 0

    async def test_pool_panes_are_tall_enough_to_show_every_item_without_scrolling(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test(size=(220, 90)):
            drivers = app.query_one("#pool-drivers", OptionList)
            constructors = app.query_one("#pool-constructors", OptionList)

            # virtual_size is the full scrollable content size; if it's no taller than
            # the visible size, there's nothing to scroll to
            assert drivers.virtual_size.height <= drivers.size.height
            assert constructors.virtual_size.height <= constructors.size.height

    async def test_pool_panes_scale_with_the_number_of_items(self, league_path):
        big_market = make_market(
            [make_player(str(i), f"Driver {i}", 10.0) for i in range(30)]
            + [make_player(f"c{i}", f"Constructor {i}", 10.0, position="CONSTRUCTOR") for i in range(15)],
            gameday_id="12",
        )
        app = make_app(league_path, big_market)
        async with app.run_test(size=(220, 90)):
            drivers = app.query_one("#pool-drivers", OptionList)
            constructors = app.query_one("#pool-constructors", OptionList)
            assert drivers.virtual_size.height <= drivers.size.height
            assert constructors.virtual_size.height <= constructors.size.height

    async def test_active_manager_has_no_background_fill(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            panel = app.query_one("#manager-panel-m3")  # Dave, first in draft_order
            assert "current-turn" in panel.classes
            assert panel.styles.background.a == 0

    async def test_managers_grid_is_a_2_column_layout(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            grid = app.query_one("#managers", Grid)
            assert grid.styles.grid_size_columns == 2
            assert grid.styles.grid_size_rows == 2

    async def test_pool_panes_have_no_background_fill(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            assert app.query_one("#pool-drivers").styles.background.a == 0
            assert app.query_one("#pool-constructors").styles.background.a == 0


class TestEventLog:
    async def test_log_pane_exists_and_is_a_scrollable_richlog(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            log = app.query_one("#event-log", RichLog)
            assert log.border_title == "Log"

    async def test_log_pane_has_no_background_fill(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test():
            assert app.query_one("#event-log").styles.background.a == 0

    async def test_pick_message_is_logged_and_persists(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert "Dave picks George Russell" in log_text(app)

    async def test_events_accumulate_rather_than_replace(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()

            await pilot.press("enter")  # Dave picks index 0
            await pilot.pause()
            await pilot.press("enter")  # Bob picks the now-first enabled item
            await pilot.pause()

            text = log_text(app)
            assert "Dave picks" in text
            assert "Bob picks" in text

    async def test_errors_are_logged_instead_of_raised_as_toasts(self, league_path, market):
        app = make_app(league_path, market)
        async with app.run_test() as pilot:
            dave = next(m for m in app.league.managers if m.name == "Dave")
            dave.money = 1.0  # cheapest item still costs more than this

            drivers = app.query_one("#pool-drivers", OptionList)
            drivers.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert "cannot afford" in log_text(app)
            assert dave.roster.drivers == []  # the pick was correctly rejected
            assert len(app.screen_stack) == 1  # and nothing popped up over the screen
