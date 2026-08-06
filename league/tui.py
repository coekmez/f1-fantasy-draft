from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, OptionList, Select, Static
from textual.widgets.option_list import Option

from f1_fantasy.client import FantasyClient
from f1_fantasy.models import Market, Player

from . import draft, settlement
from .models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, League, Manager
from .store import save_league

NO_ITEM = "__none__"


class TradeScreen(ModalScreen[Optional[str]]):
    """Swap already-owned items and/or money between two managers, to unstick a manager
    who can no longer afford anything left in the pool."""

    CSS = """
    TradeScreen {
        align: center middle;
    }
    #dialog {
        width: 76;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #dialog Horizontal { height: auto; margin-bottom: 1; }
    #dialog Select { width: 1fr; margin-right: 1; }
    #error { color: $error; height: auto; margin-bottom: 1; }
    #buttons { align: right middle; height: auto; }
    """

    def __init__(self, league: League, market: Market):
        super().__init__()
        self.league = league
        self.market = market

    def compose(self) -> ComposeResult:
        manager_options = [(m.name, m.name) for m in self.league.managers]
        with Vertical(id="dialog"):
            yield Static("[b]Trade[/b] — swap owned drivers/constructors between two managers")
            yield Static("Budgets adjust automatically by the traded items' current price.")
            with Horizontal():
                yield Select(manager_options, id="manager_a", prompt="Manager A")
                yield Select(manager_options, id="manager_b", prompt="Manager B")
            with Horizontal():
                yield Select([("(nothing)", NO_ITEM)], id="give_a", prompt="A gives up")
                yield Select([("(nothing)", NO_ITEM)], id="give_b", prompt="B gives up")
            yield Static("", id="error")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", id="confirm", variant="success")

    def _manager(self, name) -> Optional[Manager]:
        return next((m for m in self.league.managers if m.name == name), None)

    def _item_options(self, manager: Optional[Manager]) -> list:
        options = [("(nothing)", NO_ITEM)]
        if manager:
            for pid in manager.roster.player_ids():
                player = self.market.by_id(pid)
                label = f'{player.name} ({player.price:g})' if player else pid
                options.append((label, pid))
        return options

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "manager_a":
            self.query_one("#give_a", Select).set_options(self._item_options(self._manager(event.value)))
        elif event.select.id == "manager_b":
            self.query_one("#give_b", Select).set_options(self._item_options(self._manager(event.value)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return

        error = self.query_one("#error", Static)
        name_a = self.query_one("#manager_a", Select).value
        name_b = self.query_one("#manager_b", Select).value
        give_a = self.query_one("#give_a", Select).value
        give_b = self.query_one("#give_b", Select).value

        if name_a in (None, Select.NULL) or name_b in (None, Select.NULL):
            error.update("Pick both managers.")
            return

        item_a = None if give_a in (None, Select.NULL, NO_ITEM) else give_a
        item_b = None if give_b in (None, Select.NULL, NO_ITEM) else give_b

        try:
            message = draft.trade(self.league, self.market, self._manager(name_a), self._manager(name_b), item_a, item_b)
        except ValueError as e:
            error.update(str(e))
            return

        self.dismiss(message)


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


class DraftApp(App):
    CSS = """
    #pool {
        width: 45%;
        border: round $accent;
    }
    #managers {
        width: 55%;
    }
    .manager-panel {
        border: round $panel;
        padding: 0 1;
        margin: 0 1 1 0;
        height: auto;
    }
    .manager-panel.current-turn {
        border: round $success;
        background: $success 10%;
    }
    """

    BINDINGS = [("q", "quit", "Quit"), ("t", "open_trade", "Trade"), ("s", "open_sell", "Sell all")]

    def __init__(self, league: League, path: Path, market: Market, client: FantasyClient):
        super().__init__()
        self.league = league
        self.path = path
        self.market = market
        self.client = client  # only used for the explicit, user-triggered sell action
        self.start_money = {m.name: m.money for m in league.managers}
        self.highlighted_item: Optional[Player] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield OptionList(id="pool")
            with VerticalScroll(id="managers"):
                for m in self.league.managers:
                    yield Static(id=f"manager-{self._widget_id(m)}", classes="manager-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_pool()
        self.refresh_managers()

    def _widget_id(self, manager: Manager) -> str:
        return f"m{self.league.managers.index(manager)}"

    def refresh_pool(self) -> None:
        pool = self.query_one("#pool", OptionList)
        highlighted = pool.highlighted
        pool.clear_options()

        owned = {pid for m in self.league.managers for pid in m.roster.player_ids()}

        for entries, label in ((self.market.drivers(), "DRIVERS"), (self.market.constructors(), "CONSTRUCTORS")):
            pool.add_option(Option(f"── {label} ──", disabled=True))
            items = sorted((p for p in entries if p.player_id not in owned), key=lambda p: -p.price)
            for item in items:
                text = f'{item.price:>5.1f}  {item.name}'
                pool.add_option(Option(text, id=item.player_id))

        if highlighted is not None and highlighted < pool.option_count:
            pool.highlighted = highlighted

        self._sync_highlighted_item()

    def _sync_highlighted_item(self) -> None:
        pool = self.query_one("#pool", OptionList)
        idx = pool.highlighted
        if idx is None:
            self.highlighted_item = None
            return
        option = pool.get_option_at_index(idx)
        self.highlighted_item = self.market.by_id(option.id) if option.id else None

    def refresh_managers(self) -> None:
        turn = draft.whose_turn(self.league)

        for m in self.league.managers:
            panel = self.query_one(f"#manager-{self._widget_id(m)}", Static)
            is_turn = turn is not None and turn.name == m.name

            lines = [f'[b]{m.name}[/b]' + (" [b green]◀ ON THE CLOCK[/b green]" if is_turn else "")]
            lines.append(f'Points: {m.points:g}')
            lines.append(f'Starting budget: {self.start_money[m.name]:g}')

            remaining_line = f'Remaining: [b]{m.money:g}[/b]'
            if is_turn and self.highlighted_item is not None:
                after = m.money - self.highlighted_item.price
                color = "green" if after >= 0 else "red"
                remaining_line += f'   if picked: [{color}]{after:g}[/{color}]'
            lines.append(remaining_line)

            lines.append("")
            lines.append(f'Drivers ({len(m.roster.drivers)}/{DRIVER_SLOTS}):')
            for pid in m.roster.drivers:
                lines.append(f'  • {self.market.name_of(pid)}')

            lines.append(f'Constructors ({len(m.roster.constructors)}/{CONSTRUCTOR_SLOTS}):')
            for pid in m.roster.constructors:
                lines.append(f'  • {self.market.name_of(pid)}')

            panel.update("\n".join(lines))
            panel.set_class(is_turn, "current-turn")

        round_note = f"Round {self.league.round} — " if self.league.round else ""
        self.sub_title = f"{round_note}{turn.name}'s turn" if turn else f"{round_note}Draft complete"

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "pool":
            return
        self._sync_highlighted_item()
        self.refresh_managers()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:  # section header
            return

        turn = draft.whose_turn(self.league)
        if turn is None:
            self.notify("Draft is already complete.", severity="warning")
            return

        item = self.market.by_id(event.option.id)
        try:
            message = draft.apply_pick(self.league, turn, item, self.market.gameday_id)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return

        save_league(self.league, self.path)
        self.notify(message)
        self.refresh_pool()
        self.refresh_managers()

        if draft.whose_turn(self.league) is None:
            self.notify("Draft complete — every roster is full!", severity="information", timeout=15)

    def action_open_trade(self) -> None:
        self.push_screen(TradeScreen(self.league, self.market), self._after_trade)

    def _after_trade(self, message: Optional[str]) -> None:
        if not message:
            return
        save_league(self.league, self.path)
        self.notify(message)
        self.refresh_managers()

    def action_open_sell(self) -> None:
        self.push_screen(ConfirmSellScreen(self.league.round), self._after_sell)

    def _after_sell(self, confirmed: bool) -> None:
        if not confirmed:
            return

        try:
            summaries = settlement.sell_all(self.league, self.client)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return

        save_league(self.league, self.path)
        for line in summaries:
            self.notify(line)

        self.start_money = {m.name: m.money for m in self.league.managers}
        self.refresh_pool()
        self.refresh_managers()
