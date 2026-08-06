from .client import FantasyClient
from .models import RaceBreakdown, RaceWeekend, SessionPoints

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


def find_player(players: list[dict], query: str, position: str) -> dict:
    query = query.lower()
    matches = [
        p for p in players
        if p.get("PositionName") == position and query in p.get("FUllName", "").lower()
    ]
    if not matches:
        raise ValueError(f"No {position.lower()} found matching {query!r}")
    if len(matches) > 1:
        names = ", ".join(p["FUllName"] for p in matches)
        raise ValueError(f"Multiple {position.lower()}s match {query!r}: {names}")
    return matches[0]


def find_driver(players: list[dict], query: str) -> dict:
    return find_player(players, query, "DRIVER")


def find_constructor(players: list[dict], query: str) -> dict:
    return find_player(players, query, "CONSTRUCTOR")


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

        drivers = client.fetch_gameday(weekend.gameday_id)
        driver = next((d for d in drivers if d["PlayerId"] == player_id), None)
        if not driver:
            continue

        sessions = [
            SessionPoints(session_type=s["sessiontype"], points=s["points"])
            for s in driver["SessionWisePoints"]
            if s["points"] is not None
        ]
        categories = category_deltas(prev_stats, driver["AdditionalStats"])

        breakdowns.append(RaceBreakdown(
            weekend=weekend,
            points=float(driver["GamedayPoints"]),
            sessions=sessions,
            categories=categories,
        ))
        prev_stats = driver["AdditionalStats"]

    return breakdowns
