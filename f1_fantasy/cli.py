import argparse
import json

from .client import FantasyClient
from .scoring import CATEGORY_LABELS, find_constructor, find_driver, player_season


def print_players(players: list[dict], position: str) -> None:
    for p in players:
        if p["PositionName"] == position:
            print(f'{p["PlayerId"]:>6}  {p["FUllName"]}')


def print_breakdown(breakdowns: list) -> None:
    total = 0.0
    for race in breakdowns:
        total += race.points
        print(f'{race.weekend.name} — {race.points:g} pts')

        for session in race.sessions:
            print(f'    {session.session_type:<20} {session.points:>4} pts')

        for key, delta in race.categories.items():
            sign = "+" if delta > 0 else ""
            print(f'    {sign}{delta:g} pts  {CATEGORY_LABELS[key]}')

        print()

    print(f"Season total: {total:g} pts")


def print_scores(client: FantasyClient, weekends: list, current_players: list[dict], query: str, finder, as_json: bool) -> None:
    try:
        player = finder(current_players, query)
    except ValueError as e:
        raise SystemExit(str(e))

    if as_json:
        print(json.dumps(player, indent=2))
    else:
        print(f'{player["FUllName"]}\n')
        breakdowns = player_season(client, player["PlayerId"], weekends)
        print_breakdown(breakdowns)


def main():
    parser = argparse.ArgumentParser(description="F1 Fantasy points lookup")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("drivers", help="List all Fantasy drivers and their IDs")
    sub.add_parser("constructors", help="List all Fantasy constructors and their IDs")

    scores = sub.add_parser("scores", help="Get a driver's Fantasy points breakdown by race")
    scores.add_argument("driver", help="Driver name (partial match), e.g. 'Verstappen'")
    scores.add_argument("--json", action="store_true", help="Print raw JSON instead of a summary")

    cscores = sub.add_parser("constructor-scores", help="Get a constructor's Fantasy points breakdown by race")
    cscores.add_argument("constructor", help="Constructor name (partial match), e.g. 'Ferrari'")
    cscores.add_argument("--json", action="store_true", help="Print raw JSON instead of a summary")

    args = parser.parse_args()

    client = FantasyClient()
    weekends = client.fetch_schedule()
    latest = next(w for w in reversed(weekends) if w.status in (1, 4))
    current_players = client.fetch_gameday(latest.gameday_id)

    if args.command == "drivers":
        print_players(current_players, "DRIVER")
    elif args.command == "constructors":
        print_players(current_players, "CONSTRUCTOR")
    elif args.command == "scores":
        print_scores(client, weekends, current_players, args.driver, find_driver, args.json)
    elif args.command == "constructor-scores":
        print_scores(client, weekends, current_players, args.constructor, find_constructor, args.json)
