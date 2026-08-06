import json

from .client import FantasyClient
from .scoring import CATEGORY_LABELS, find_constructor, find_driver, player_season


def print_players(players: list[dict], position: str) -> None:
    for p in players:
        if p["PositionName"] == position:
            print(f'{p["PlayerId"]:>6}  {p["FUllName"]}')


def print_prices(players: list[dict]) -> None:
    for position, label in (("DRIVER", "Drivers"), ("CONSTRUCTOR", "Constructors")):
        print(f'{label}:')
        entries = sorted(
            (p for p in players if p["PositionName"] == position),
            key=lambda p: float(p["Value"]),
            reverse=True,
        )
        for p in entries:
            print(f'    {float(p["Value"]):>6.1f}  {p["FUllName"]}')
        print()


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


def _drivers(args):
    client = FantasyClient()
    print_players(client.fetch_current_players(), "DRIVER")


def _constructors(args):
    client = FantasyClient()
    print_players(client.fetch_current_players(), "CONSTRUCTOR")


def _prices(args):
    client = FantasyClient()
    print_prices(client.fetch_current_players())


def _scores(args):
    client = FantasyClient()
    weekends = client.fetch_schedule()
    current_players = client.fetch_current_players()
    print_scores(client, weekends, current_players, args.driver, find_driver, args.json)


def _constructor_scores(args):
    client = FantasyClient()
    weekends = client.fetch_schedule()
    current_players = client.fetch_current_players()
    print_scores(client, weekends, current_players, args.constructor, find_constructor, args.json)


def add_subcommands(subparsers) -> None:
    subparsers.add_parser("drivers", help="List all Fantasy drivers and their IDs").set_defaults(func=_drivers)
    subparsers.add_parser("constructors", help="List all Fantasy constructors and their IDs").set_defaults(func=_constructors)
    subparsers.add_parser("prices", help="List all drivers and constructors with their current Fantasy price").set_defaults(func=_prices)

    scores = subparsers.add_parser("scores", help="Get a driver's Fantasy points breakdown by race")
    scores.add_argument("driver", help="Driver name (partial match), e.g. 'Verstappen'")
    scores.add_argument("--json", action="store_true", help="Print raw JSON instead of a summary")
    scores.set_defaults(func=_scores)

    cscores = subparsers.add_parser("constructor-scores", help="Get a constructor's Fantasy points breakdown by race")
    cscores.add_argument("constructor", help="Constructor name (partial match), e.g. 'Ferrari'")
    cscores.add_argument("--json", action="store_true", help="Print raw JSON instead of a summary")
    cscores.set_defaults(func=_constructor_scores)
