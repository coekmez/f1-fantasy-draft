from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from f1_fantasy.client import FantasyClient
from f1_fantasy.models import Market, Player

from . import draft, settlement
from .models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, League, Manager
from .store import save_league


class ConfirmSellScreen(ModalScreen[bool]):
    """One week of the draft is pick -> race -> sell. This confirms the sell step,
    which settles every manager's roster at once and can't be undone in the UI."""

    CSS = """
    ConfirmSellScreen {
        align: center middle;
    }
    #dialog {
        width: 66;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #buttons { align: right middle; height: auto; margin-top: 1; }
    """

    def __init__(self, round_number: Optional[str]):
        super().__init__()
        self.round_number = round_number

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[b]Sell every manager's roster?[/b]")
            yield Static(
                f"Credits each manager with the points their drivers/constructors "
                f"earned in round {self.round_number}, plus their current price, "
                f"then clears every roster for next week's picks."
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Sell", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class ConfirmResetScreen(ModalScreen[bool]):
    """Undoes the current round's picks — a do-over, not a settlement: refunds what
    was spent, clears every roster, and does not touch anyone's points."""

    CSS = """
    ConfirmResetScreen {
        align: center middle;
    }
    #dialog {
        width: 66;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #buttons { align: right middle; height: auto; margin-top: 1; }
    """

    def __init__(self, round_number: Optional[str]):
        super().__init__()
        self.round_number = round_number

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[b]Reset every manager's roster?[/b]")
            yield Static(
                f"Refunds each manager the round {self.round_number} price of every "
                f"driver/constructor they picked, then clears every roster. Points "
                f"are not affected — this undoes the picks, it doesn't settle them."
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Reset", id="confirm", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


POOL_COLUMN_IDS = ("pool-drivers", "pool-constructors")


@dataclass
class PickAction:
    """A pick, recorded so it can be undone/redone. Session-only — not persisted."""

    manager_name: str
    player_id: str
    price: float
    slot: str  # "drivers" or "constructors"


@dataclass
class SlotRef:
    """One roster slot (a manager's Nth driver or constructor, filled or empty),
    as selected during in-place trade mode. Session-only."""

    manager_name: str
    slot_type: str  # "drivers" or "constructors"
    slot_index: int

    def player_id(self, league: League) -> Optional[str]:
        manager = next(m for m in league.managers if m.name == self.manager_name)
        items = getattr(manager.roster, self.slot_type)
        return items[self.slot_index] if self.slot_index < len(items) else None


MANAGER_PANEL_CONTENT_LINES = 13  # name, points, budget, blank, "Drivers(n/5):", 5 slots, "Constructors(n/2):", 2 slots
MANAGER_PANEL_HEIGHT = MANAGER_PANEL_CONTENT_LINES + 2  # + top/bottom border
LOG_HEIGHT = 8


class DraftApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    #frame {
        width: 130;
    }
    #pool-column {
        width: 40%;
        height: 100%;
    }
    #pool-drivers {
        border: round $accent;
        background: transparent;
    }
    #pool-constructors {
        border: round $accent;
        background: transparent;
    }
    #managers-scroll {
        width: 60%;
        height: 100%;
    }
    #managers {
        grid-gutter: 1;
        height: 100%;
    }
    .manager-panel {
        border: round $panel;
        padding: 0 1;
        height: 100%;
        width: 100%;
    }
    .manager-panel.current-turn {
        border: round $success;
    }
    .manager-header {
        height: 4;
    }
    .manager-roster {
        height: 1fr;
        background: transparent;
    }
    /* Slots are disabled except during an active trade — that's what makes them
       inert/unselectable the rest of the time, not a visual "greyed out" state. */
    .manager-roster > .option-list--option-disabled {
        color: $foreground;
    }
    #event-log {
        border: round $accent;
        margin-top: 1;
        background: transparent;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "open_trade", "Trade"),
        ("escape", "cancel_trade", "Cancel trade"),
        ("s", "open_sell", "Sell all"),
        ("r", "open_reset", "Reset round"),
        ("u", "undo", "Undo"),
        ("U", "redo", "Redo"),
        ("left", "focus_prev_column", "◀ column"),
        ("right", "focus_next_column", "column ▶"),
    ]

    def __init__(self, league: League, path: Path, market: Market, client: FantasyClient):
        super().__init__()
        self.league = league
        self.path = path
        self.market = market
        self.client = client  # only used for the explicit, user-triggered sell action
        self.highlighted_item: Optional[Player] = None
        self.undo_stack: list[PickAction] = []
        self.redo_stack: list[PickAction] = []
        self.trade_mode: bool = False
        self.trade_first: Optional[SlotRef] = None
        self.trade_hover: Optional[SlotRef] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="frame"):
            with Horizontal(id="body"):
                with Vertical(id="pool-column"):
                    yield OptionList(id="pool-drivers")
                    yield OptionList(id="pool-constructors")
                with VerticalScroll(id="managers-scroll"):
                    with Grid(id="managers"):
                        for m in self.league.managers:
                            wid = self._widget_id(m)
                            with Vertical(id=f"manager-panel-{wid}", classes="manager-panel"):
                                yield Static(id=f"manager-header-{wid}", classes="manager-header")
                                yield OptionList(id=f"manager-roster-{wid}", classes="manager-roster")
            yield RichLog(id="event-log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pool-drivers", OptionList).border_title = "Drivers"
        self.query_one("#pool-constructors", OptionList).border_title = "Constructors"
        self.query_one("#event-log", RichLog).border_title = "Log"

        # Every driver/constructor always stays in its list (picked ones are struck
        # through, not removed), so each pane can be sized to its exact full content —
        # nobody ever needs to scroll to see the whole list.
        drivers_height = len(self.market.drivers()) + 2  # + top/bottom border
        constructors_height = len(self.market.constructors()) + 2
        self.query_one("#pool-drivers").styles.height = drivers_height
        self.query_one("#pool-constructors").styles.height = constructors_height

        body_height = max(drivers_height + constructors_height, self._managers_height())
        self.query_one("#body").styles.height = body_height
        self.query_one("#event-log").styles.height = LOG_HEIGHT
        self.query_one("#frame").styles.height = body_height + 1 + LOG_HEIGHT  # +1 for the log's margin-top gap

        self._relayout_managers()
        self.refresh_pool()
        self.refresh_managers()

    def _managers_height(self) -> int:
        n = len(self.league.managers)
        columns = min(2, n) if n else 1
        rows = -(-n // columns) if columns else 1
        return rows * MANAGER_PANEL_HEIGHT + (rows - 1)  # + gutter between manager rows

    def _widget_id(self, manager: Manager) -> str:
        return f"m{self.league.managers.index(manager)}"

    def _manager_roster_ids(self) -> list:
        return [f"manager-roster-{self._widget_id(m)}" for m in self.league.managers]

    def _log_event(self, message: str, severity: str = "information") -> None:
        # A persistent, scrollable log instead of toast notifications — those piled up
        # and covered the screen when several events landed in quick succession.
        color = {"error": "red", "warning": "yellow"}.get(severity)
        self.query_one("#event-log", RichLog).write(f'[{color}]{message}[/{color}]' if color else message)

    def _relayout_managers(self) -> None:
        grid = self.query_one("#managers", Grid)
        n = len(self.league.managers)
        columns = min(2, n) if n else 1
        rows = -(-n // columns) if columns else 0  # ceil
        grid.styles.grid_size_columns = columns
        grid.styles.grid_size_rows = rows

    def refresh_pool(self) -> None:
        owned = {pid for m in self.league.managers for pid in m.roster.player_ids()}

        drivers = sorted(self.market.drivers(), key=lambda p: -p.price)
        constructors = sorted(self.market.constructors(), key=lambda p: -p.price)

        for widget_id, items in (("pool-drivers", drivers), ("pool-constructors", constructors)):
            option_list = self.query_one(f"#{widget_id}", OptionList)
            highlighted = option_list.highlighted
            option_list.clear_options()
            for item in items:
                text = f'{item.price:>5.1f}  {item.name}'
                is_picked = item.player_id in owned
                if is_picked:
                    text = f'[strike]{text}[/strike]'
                # disabled options are automatically skipped by OptionList's own
                # up/down cursor movement, so picked items never receive the highlight
                option_list.add_option(Option(text, id=item.player_id, disabled=is_picked))

            target = highlighted if highlighted is not None and highlighted < option_list.option_count else 0
            resolved = self._nearest_enabled_index(option_list, target)
            if resolved is not None:
                option_list.highlighted = resolved

        self._sync_highlighted_item()

    def _nearest_enabled_index(self, option_list: OptionList, start: int) -> Optional[int]:
        # Landing the highlight directly on a disabled option leaves no visible cursor
        # in the pane — it looks like focus left, even though the widget itself is
        # still focused. Search forward (wrapping) for something selectable.
        count = option_list.option_count
        if count == 0:
            return None
        for offset in range(count):
            idx = (start + offset) % count
            if not option_list.get_option_at_index(idx).disabled:
                return idx
        return None  # every option is disabled

    def _sync_highlighted_item(self) -> None:
        active = self.focused
        if active is None or active.id not in POOL_COLUMN_IDS:
            self.highlighted_item = None
            return
        idx = active.highlighted
        if idx is None:
            self.highlighted_item = None
            return
        option = active.get_option_at_index(idx)
        # a disabled option is a picked (struck-through) item — not something you can
        # actually pick right now, so it shouldn't drive the "if picked" budget preview
        self.highlighted_item = self.market.by_id(option.id) if option.id and not option.disabled else None

    def _sync_trade_hover(self) -> None:
        self.trade_hover = None
        if not self.trade_mode or self.trade_first is None:
            return
        active = self.focused
        if active is None or active.id not in self._manager_roster_ids():
            return
        idx = active.highlighted
        if idx is None:
            return
        option = active.get_option_at_index(idx)
        if option.id is None or option.disabled:
            return
        manager = self.league.managers[self._manager_roster_ids().index(active.id)]
        slot_type, index_str = option.id.split(":")
        self.trade_hover = SlotRef(manager.name, slot_type, int(index_str))

    def refresh_managers(self) -> None:
        """Full refresh: header text plus a rebuild of every manager's roster
        OptionList. Only call this after something that actually changed roster
        contents (pick, trade, undo/redo, sell/reset, entering/exiting trade mode) —
        rebuilding an OptionList reassigns `.highlighted`, which re-fires
        OptionHighlighted, so calling this FROM that event's own handler would loop
        forever. Live hover/preview updates must go through `_refresh_manager_headers`
        instead, which never touches an OptionList.
        """
        self._refresh_manager_headers()
        for m in self.league.managers:
            roster = self.query_one(f"#manager-roster-{self._widget_id(m)}", OptionList)
            self._refresh_manager_roster(roster, m)

    def _refresh_manager_headers(self) -> None:
        # Recompute rather than trust the cached value — a direct `.highlighted =`
        # assignment elsewhere doesn't reliably fire OptionHighlighted in time for
        # self.highlighted_item to already be fresh when this runs.
        self._sync_highlighted_item()
        self._sync_trade_hover()

        turn = draft.whose_turn(self.league)

        trade_preview = None
        if self.trade_first is not None and self.trade_hover is not None and self.trade_first.manager_name != self.trade_hover.manager_name:
            value_first = self.market.by_id(self.trade_first.player_id(self.league)).price
            value_second = self.market.by_id(self.trade_hover.player_id(self.league)).price
            trade_preview = {
                self.trade_first.manager_name: value_first - value_second,
                self.trade_hover.manager_name: value_second - value_first,
            }

        for m in self.league.managers:
            wid = self._widget_id(m)
            panel = self.query_one(f"#manager-panel-{wid}")
            header = self.query_one(f"#manager-header-{wid}", Static)
            is_turn = turn is not None and turn.name == m.name

            lines = [f'[b]{m.name}[/b]']
            lines.append(f'Points: {m.points:g}')

            budget_line = f'Budget: [b]{m.money:g}[/b]'
            if is_turn and self.highlighted_item is not None:
                after = m.money - self.highlighted_item.price
                color = "green" if after >= 0 else "red"
                budget_line += f'[{color}] ▶ {after:g}[/{color}]'
            elif trade_preview is not None and m.name in trade_preview:
                after = m.money + trade_preview[m.name]
                color = "green" if after >= 0 else "red"
                budget_line += f'[{color}] ▶ {after:g}[/{color}]'
            lines.append(budget_line)
            lines.append("")
            header.update("\n".join(lines))
            panel.set_class(is_turn, "current-turn")

        round_note = f"Round {self.league.round} — " if self.league.round else ""
        mode_note = " (select a trade slot)" if self.trade_mode else ""
        self.sub_title = (f"{round_note}{turn.name}'s turn" if turn else f"{round_note}Draft complete") + mode_note

    def _refresh_manager_roster(self, roster: OptionList, manager: Manager) -> None:
        highlighted = roster.highlighted
        roster.clear_options()

        roster.add_option(Option(f'Drivers ({len(manager.roster.drivers)}/{DRIVER_SLOTS}):', disabled=True))
        for i in range(DRIVER_SLOTS):
            roster.add_option(self._slot_option(manager, "drivers", i))

        roster.add_option(Option(f'Constructors ({len(manager.roster.constructors)}/{CONSTRUCTOR_SLOTS}):', disabled=True))
        for i in range(CONSTRUCTOR_SLOTS):
            roster.add_option(self._slot_option(manager, "constructors", i))

        if not self.trade_mode:
            return  # not interactive right now — leave it with no highlighted cursor

        target = highlighted if highlighted is not None and highlighted < roster.option_count else 0
        resolved = self._nearest_enabled_index(roster, target)
        if resolved is not None:
            roster.highlighted = resolved

    def _slot_option(self, manager: Manager, slot_type: str, index: int) -> Option:
        items = getattr(manager.roster, slot_type)
        is_filled = index < len(items)
        label = self.market.name_of(items[index]) if is_filled else "—"

        if SlotRef(manager.name, slot_type, index) == self.trade_first:
            label = f'[reverse] {label} [/reverse]'

        # Only a filled slot can take part in a trade — an empty slot has nothing to
        # give — and once a first slot is picked, only its own category (driver for
        # driver, constructor for constructor) is a legal second choice.
        disabled = not self.trade_mode or not is_filled
        if self.trade_first is not None and slot_type != self.trade_first.slot_type:
            disabled = True

        return Option(f'  {label}', id=f'{slot_type}:{index}', disabled=disabled)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        # Header-only refresh — never rebuilds an OptionList in response to one of
        # its own highlight-change events (see refresh_managers's docstring).
        if event.option_list.id in POOL_COLUMN_IDS or event.option_list.id in self._manager_roster_ids():
            self._refresh_manager_headers()

    def action_focus_prev_column(self) -> None:
        self._cycle_focus(-1)

    def action_focus_next_column(self) -> None:
        self._cycle_focus(1)

    def _cycle_focus(self, direction: int) -> None:
        ids = self._manager_roster_ids() if self.trade_mode else list(POOL_COLUMN_IDS)
        columns = [self.query_one(f"#{wid}", OptionList) for wid in ids]
        if not columns:
            return
        current = self.focused
        idx = columns.index(current) if current in columns else 0
        columns[(idx + direction) % len(columns)].focus()

        self.call_after_refresh(self.refresh_managers)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id in POOL_COLUMN_IDS:
            self._handle_pick(event)
        elif self.trade_mode and event.option_list.id in self._manager_roster_ids():
            self._handle_trade_slot_selected(event)

    def _handle_pick(self, event: OptionList.OptionSelected) -> None:
        if self.trade_mode:
            self._log_event("Finish or cancel the trade first (Esc).", severity="warning")
            return

        turn = draft.whose_turn(self.league)
        if turn is None:
            self._log_event("Draft is already complete.", severity="warning")
            return

        item = self.market.by_id(event.option.id)
        try:
            message = draft.apply_pick(self.league, turn, item, self.market.gameday_id)
        except ValueError as e:
            self._log_event(str(e), severity="error")
            return

        self.undo_stack.append(PickAction(turn.name, item.player_id, item.price, "drivers" if item.is_driver else "constructors"))
        self.redo_stack.clear()

        save_league(self.league, self.path)
        self._log_event(message)
        self.refresh_pool()
        self.refresh_managers()

        if draft.whose_turn(self.league) is None:
            self._log_event("Draft complete — every roster is full!")

    def action_undo(self) -> None:
        if not self.undo_stack:
            self._log_event("Nothing to undo.", severity="warning")
            return

        action = self.undo_stack[-1]  # peek: only pop once we know it can actually be undone
        manager = next(m for m in self.league.managers if m.name == action.manager_name)
        roster_list = getattr(manager.roster, action.slot)
        if action.player_id not in roster_list:
            self._log_event(f"Can't undo — {self.market.name_of(action.player_id)} is no longer where it was picked (traded since?).", severity="error")
            return

        self.undo_stack.pop()
        roster_list.remove(action.player_id)
        manager.money += action.price
        if not any(m.roster.player_ids() for m in self.league.managers):
            self.league.round = None

        self.redo_stack.append(action)
        save_league(self.league, self.path)
        self._log_event(f'Undid: {action.manager_name} — {self.market.name_of(action.player_id)}')
        self.refresh_pool()
        self.refresh_managers()

    def action_redo(self) -> None:
        if not self.redo_stack:
            self._log_event("Nothing to redo.", severity="warning")
            return

        action = self.redo_stack[-1]  # peek: only pop once we know it can actually be redone
        manager = next(m for m in self.league.managers if m.name == action.manager_name)

        if draft.is_owned(self.league, action.player_id):
            self._log_event(f"Can't redo — {self.market.name_of(action.player_id)} has since been picked by someone else.", severity="error")
            return
        if action.price > manager.money:
            self._log_event(f"Can't redo — {action.manager_name} can no longer afford {self.market.name_of(action.player_id)}.", severity="error")
            return

        self.redo_stack.pop()

        if self.league.round is None:
            self.league.round = self.market.gameday_id
        getattr(manager.roster, action.slot).append(action.player_id)
        manager.money -= action.price

        self.undo_stack.append(action)
        save_league(self.league, self.path)
        self._log_event(f'Redid: {action.manager_name} — {self.market.name_of(action.player_id)}')
        self.refresh_pool()
        self.refresh_managers()

    def action_open_trade(self) -> None:
        self.trade_mode = True
        self.trade_first = None
        self._log_event("Trade: select the first slot (Esc to cancel).")
        self.refresh_managers()  # enables + highlights every manager roster

        roster_ids = self._manager_roster_ids()
        if roster_ids:
            self.query_one(f"#{roster_ids[0]}", OptionList).focus()

    def action_cancel_trade(self) -> None:
        if not self.trade_mode:
            return
        self.trade_first = None
        self.trade_hover = None
        self._log_event("Trade cancelled.")
        self._exit_trade_mode()

    def _exit_trade_mode(self) -> None:
        self.trade_mode = False
        self.refresh_managers()  # disables + clears the highlight on every manager roster
        self.query_one("#pool-drivers", OptionList).focus()

    def _handle_trade_slot_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:  # a "Drivers (n/5):" / "Constructors (n/2):" header row
            return

        manager = self.league.managers[self._manager_roster_ids().index(event.option_list.id)]
        slot_type, index_str = event.option.id.split(":")
        ref = SlotRef(manager.name, slot_type, int(index_str))

        if self.trade_first is None:
            self.trade_first = ref
            label = self.market.name_of(ref.player_id(self.league))  # slot is always filled — empty slots are disabled
            self._log_event(f"Trade: {manager.name}'s {label} selected — now choose the second slot (Esc to cancel).")
            self.refresh_managers()
            return

        if ref == self.trade_first:
            self.trade_first = None
            self.trade_hover = None
            self._log_event("Trade cancelled.")
            self._exit_trade_mode()
            return

        self._complete_trade(self.trade_first, ref)

    def _complete_trade(self, first: SlotRef, second: SlotRef) -> None:
        manager_a = next(m for m in self.league.managers if m.name == first.manager_name)
        manager_b = next(m for m in self.league.managers if m.name == second.manager_name)
        give_a = first.player_id(self.league)
        give_b = second.player_id(self.league)

        try:
            message = draft.trade(self.league, self.market, manager_a, manager_b, give_a, give_b)
        except ValueError as e:
            # keep the first selection active so they can try a different second slot
            self._log_event(str(e), severity="error")
            return

        save_league(self.league, self.path)
        self._log_event(message)
        self.trade_first = None
        self.trade_hover = None
        self._exit_trade_mode()
        self.refresh_pool()
        self.refresh_managers()

    def action_open_sell(self) -> None:
        self.push_screen(ConfirmSellScreen(self.league.round), self._after_sell)

    def _after_sell(self, confirmed: bool) -> None:
        if not confirmed:
            return

        try:
            summaries = settlement.sell_all(self.league, self.client)
        except ValueError as e:
            self._log_event(str(e), severity="error")
            return

        self.undo_stack.clear()
        self.redo_stack.clear()
        self.trade_mode = False
        self.trade_first = None

        save_league(self.league, self.path)
        for line in summaries:
            self._log_event(line)

        self.refresh_pool()
        self.refresh_managers()

    def action_open_reset(self) -> None:
        self.push_screen(ConfirmResetScreen(self.league.round), self._after_reset)

    def _after_reset(self, confirmed: bool) -> None:
        if not confirmed:
            return

        try:
            summaries = settlement.reset_all(self.league, self.client)
        except ValueError as e:
            self._log_event(str(e), severity="error")
            return

        self.undo_stack.clear()
        self.redo_stack.clear()
        self.trade_mode = False
        self.trade_first = None

        save_league(self.league, self.path)
        for line in summaries:
            self._log_event(line)

        self.refresh_pool()
        self.refresh_managers()
