import requests

from f1_fantasy.client import FantasyClient

from .models import League


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

    summaries = []
    for m in league.managers:
        player_ids = m.roster.player_ids()
        points_gained = sum(round_market.by_id(pid).gameday_points for pid in player_ids)
        money_gained = sum(price_market.by_id(pid).price for pid in player_ids)

        m.points += points_gained
        m.money += money_gained
        m.roster.drivers.clear()
        m.roster.constructors.clear()

        summaries.append(f'{m.name}: +{points_gained:g} pts, +{money_gained:g} money')

    league.round = None

    return summaries
