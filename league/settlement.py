import math

import requests

from f1_fantasy.client import FantasyClient
from f1_fantasy.models import Market, Player

from .models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, League


def _fmt_delta(x: float) -> str:
    return f'+{x:g}' if x >= 0 else f'{x:g}'


def _apply_and_clear(league: League, deltas: dict) -> list[str]:
    """deltas: manager name -> (points_delta, money_delta). Applies them, clears every
    roster, and resets league.round so next week's picks start fresh."""
    summaries = []
    for m in league.managers:
        points_delta, money_delta = deltas[m.name]
        m.points += points_delta
        m.money += money_delta
        m.roster.drivers.clear()
        m.roster.constructors.clear()
        summaries.append(f'{m.name}: {_fmt_delta(points_delta)} pts, {_fmt_delta(money_delta)} money')

    league.round = None
    return summaries


def _sum_top_price(players: list[Player], n: int) -> float:
    return sum(p.price for p in sorted(players, key=lambda p: -p.price)[:n])


def equal_budget(market: Market, num_managers: int) -> float:
    """Everyone's budget, always the same for every manager: the total cost of the
    top X drivers (X = DRIVER_SLOTS * num_managers — exactly how many drivers will
    actually end up drafted league-wide) plus the total cost of the top Y
    constructors (Y = CONSTRUCTOR_SLOTS * num_managers), split evenly across all
    managers and rounded up to the next whole number. Restricting to the top X/Y
    (rather than the whole market) means cheap items nobody will ever draft don't
    drag the figure down.
    """
    driver_total = _sum_top_price(market.drivers(), DRIVER_SLOTS * num_managers)
    constructor_total = _sum_top_price(market.constructors(), CONSTRUCTOR_SLOTS * num_managers)
    return math.ceil((driver_total + constructor_total) / num_managers)


def _fetch_and_validate_end_week_markets(league: League, client: FantasyClient) -> tuple[Market, Market]:
    """Fetch league.round's market (for points, so every held item has to be found
    in it) and the live market (for the budget) — the shared groundwork for both
    end_week (which then mutates) and preview_end_week (which doesn't)."""
    if league.round is None:
        raise ValueError("No round is currently in progress — nothing to sell")

    round_market = client.fetch_gameday(league.round)

    try:
        budget_market = client.fetch_current_players()
    except requests.RequestException as e:
        raise ValueError(f"Could not fetch the current week's price data: {e}") from e

    for m in league.managers:
        for player_id in m.roster.player_ids():
            if round_market.by_id(player_id) is None:
                raise ValueError(f"{player_id} not found in round {league.round}'s data")

    return round_market, budget_market


def preview_end_week(league: League, client: FantasyClient) -> float:
    """The flat budget everyone would get if end_week ran right now, without
    changing anything — lets a caller show "what would our budget become" before
    actually ending the week. Raises the same ValueErrors end_week would if
    there's nothing to sell or the data isn't available yet.
    """
    _, budget_market = _fetch_and_validate_end_week_markets(league, client)
    return equal_budget(budget_market, len(league.managers))


def end_week(league: League, client: FantasyClient) -> list[str]:
    """End-of-week settlement: 'make picks -> race happens -> sell drivers' is one
    week of the draft, and this is what actually turns the crank from one week to
    the next — selling every manager's roster at once is only half of what it
    does; the other half is retiring league.round so the *next* week's picks start
    from a clean slate. The week counter (whatever picking week comes next) only
    ever moves forward here — nowhere else changes it.

    Every manager's roster is credited with the points their drivers/constructors
    earned in league.round (the week everyone drafted in this cycle). Money is
    reset to the same flat equal_budget for everyone, computed from the live
    market — the very same prices next week's picks will be made at. That pairing
    is the whole point of the budget: it's sized so everyone can afford a full
    roster at current prices, which only holds if it's computed from the week
    being drafted. Budgets are always equal, so nobody's can pull ahead of
    anyone else's regardless of how their own picks did.

    Every roster is then cleared and league.round reset so next week's picks start
    fresh. Mutates league in place; raises without changing anything if it can't be
    settled.
    """
    round_market, budget_market = _fetch_and_validate_end_week_markets(league, client)
    budget = equal_budget(budget_market, len(league.managers))

    deltas = {}
    for m in league.managers:
        points_gained = sum(round_market.by_id(pid).gameday_points for pid in m.roster.player_ids())
        money_delta = budget - m.money
        deltas[m.name] = (points_gained, money_delta)

    return _apply_and_clear(league, deltas)


def reset_all(league: League, client: FantasyClient) -> list[str]:
    """Undo the current round's picks: refund each manager exactly what they paid
    (league.round's price for every item they hold — the price they were actually
    charged at pick time, since picks are always made at the current round's price)
    and clear every roster. Unlike end_week, no points are credited and the week
    counter doesn't move — this is a do-over, not a settlement. Mutates league in
    place; raises without changing anything if it can't be reset.
    """
    if league.round is None:
        raise ValueError("No round is currently in progress — nothing to reset")

    round_market = client.fetch_gameday(league.round)

    for m in league.managers:
        for player_id in m.roster.player_ids():
            if round_market.by_id(player_id) is None:
                raise ValueError(f"{player_id} not found in round {league.round}'s data")

    deltas = {
        m.name: (0.0, sum(round_market.by_id(pid).price for pid in m.roster.player_ids()))
        for m in league.managers
    }

    return _apply_and_clear(league, deltas)
