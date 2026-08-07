import requests

from f1_fantasy.client import FantasyClient

from .models import League


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
        summaries.append(f'{m.name}: +{points_delta:g} pts, +{money_delta:g} money')

    league.round = None
    return summaries


def sell_all(league: League, client: FantasyClient) -> list[str]:
    """End-of-week settlement: 'make picks -> race happens -> sell drivers' is one
    week of the draft. This is the sell step, applied to every manager at once.

    Every manager's roster is credited with the points their drivers/constructors
    earned in league.round (the week everyone drafted in this cycle), plus each
    item's price in the *following* round — not whatever the market shows today.
    The league doesn't always convene every week, so "today" could be several
    rounds after the pick; pricing off the round right after the pick means a
    manager banks the value change from their own pick's result, not whatever
    drift happened in the extra weeks before the league got around to selling.
    Every roster is then cleared and league.round reset so next week's picks
    start fresh. Mutates league in place; raises without changing anything if
    it can't be settled.
    """
    if league.round is None:
        raise ValueError("No round is currently in progress — nothing to sell")

    round_market = client.fetch_gameday(league.round)

    next_round = str(int(league.round) + 1)
    try:
        price_market = client.fetch_gameday(next_round)
    except requests.RequestException as e:
        raise ValueError(f"Could not fetch round {next_round}'s price data (the round after {league.round}): {e}") from e

    # Validate everything before mutating anything.
    for m in league.managers:
        for player_id in m.roster.player_ids():
            if round_market.by_id(player_id) is None:
                raise ValueError(f"{player_id} not found in round {league.round}'s data")
            if price_market.by_id(player_id) is None:
                raise ValueError(f"{player_id} not found in round {next_round}'s data")

    deltas = {}
    for m in league.managers:
        player_ids = m.roster.player_ids()
        points_gained = sum(round_market.by_id(pid).gameday_points for pid in player_ids)
        money_gained = sum(price_market.by_id(pid).price for pid in player_ids)
        deltas[m.name] = (points_gained, money_gained)

    return _apply_and_clear(league, deltas)


def reset_all(league: League, client: FantasyClient) -> list[str]:
    """Undo the current round's picks: refund each manager exactly what they paid
    (league.round's price for every item they hold — the price they were actually
    charged at pick time, since picks are always made at the current round's price)
    and clear every roster. Unlike sell_all, no points are credited — this is a
    do-over, not a settlement. Mutates league in place; raises without changing
    anything if it can't be reset.
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
