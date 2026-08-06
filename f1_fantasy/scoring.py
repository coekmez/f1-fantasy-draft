from .client import FantasyClient
from .models import Market, Player, RaceBreakdown, RaceWeekend

CATEGORY_LABELS = {
    "fastest_lap_pts": "Fastest lap",
    "dotd_pts": "Driver of the Day",
    "overtaking_pts": "Overtakes",
    "q3_finishes_pts": "Q3 finish",
    "top10_race_position_pts": "Race position (top 10)",
    "top8_sprint_position_pts": "Sprint position (top 8)",
    "total_position_pts": "Position points",
    "total_position_gained_lost": "Positions gained/lost",
    "total_dnf_dq_pts": "DNF / DSQ",
}


def find_player(market: Market, query: str, position: str) -> Player:
    query = query.lower()
    entries = market.drivers() if position == "DRIVER" else market.constructors()
    matches = [p for p in entries if query in p.name.lower()]
    if not matches:
        raise ValueError(f"No {position.lower()} found matching {query!r}")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ValueError(f"Multiple {position.lower()}s match {query!r}: {names}")
    return matches[0]


def find_driver(market: Market, query: str) -> Player:
    return find_player(market, query, "DRIVER")


def find_constructor(market: Market, query: str) -> Player:
    return find_player(market, query, "CONSTRUCTOR")


def category_deltas(prev_stats: dict, curr_stats: dict) -> dict[str, float]:
    """F1's AdditionalStats are cumulative season-to-date; diff two weekends to isolate one race."""
    deltas = {}
    for key in CATEGORY_LABELS:
        delta = curr_stats.get(key, 0.0) - (prev_stats.get(key, 0.0) if prev_stats else 0.0)
        if delta:
            deltas[key] = delta
    return deltas


def player_season(client: FantasyClient, player_id: str, weekends: list[RaceWeekend]) -> list[RaceBreakdown]:
    """Per-race Fantasy points for one driver or constructor across all completed weekends."""
    breakdowns = []
    prev_stats = None

    for weekend in weekends:
        if not weekend.is_completed:
            continue

        market = client.fetch_gameday(weekend.gameday_id)
        player = market.by_id(player_id)
        if not player:
            continue

        categories = category_deltas(prev_stats, player.category_stats)

        breakdowns.append(RaceBreakdown(
            weekend=weekend,
            points=player.gameday_points,
            sessions=player.sessions,
            categories=categories,
        ))
        prev_stats = player.category_stats

    return breakdowns
