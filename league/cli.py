from pathlib import Path

from f1_fantasy.client import FantasyClient

from . import draft, settlement
from .models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, new_league
from .store import DEFAULT_LEAGUE_PATH, load_league, save_league, save_round_snapshot


def _init(args):
    path = Path(args.path)
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists. Use --force to overwrite.")

    print("Enter the 4 managers in this league.")
    names = [input(f"Manager {i + 1} name: ").strip() for i in range(4)]

    league = new_league(names)
    print("\nNow the current state for each manager (as tracked by hand so far).")
    for manager in league.managers:
        manager.points = float(input(f"{manager.name} — current points: ") or 0)
        manager.money = float(input(f"{manager.name} — current money: ") or 0)

    league.draft_order = draft.compute_draft_order(league)
    save_league(league, path)

    print(f"\nSaved to {path}.")
    print(f"Draft order (least points first, repeats every round): {', '.join(league.draft_order)}")


def _status(args):
    league = load_league(Path(args.path))
    market = FantasyClient().fetch_current_players()

    for m in league.managers:
        roster_note = f'{len(m.roster.drivers)}/{DRIVER_SLOTS} drivers, {len(m.roster.constructors)}/{CONSTRUCTOR_SLOTS} constructors'
        print(f'{m.name:<15} {m.points:>7g} pts   {m.money:>7g} money   {roster_note}')
        for pid in m.roster.drivers + m.roster.constructors:
            print(f'    {market.name_of(pid)}')

    turn = draft.whose_turn(league)
    print(f"\nRound: {league.round if league.round else '(none in progress)'}")
    print(f"Draft order: {', '.join(league.draft_order)}")
    print(f"Next to pick: {turn.name if turn else '(draft complete)'}")


def _pick(args):
    path = Path(args.path)
    league = load_league(path)
    client = FantasyClient()
    try:
        message = draft.make_pick(league, client, args.manager, args.item, force=args.force)
    except ValueError as e:
        raise SystemExit(str(e))
    save_league(league, path)
    print(message)


def _sell(args):
    path = Path(args.path)
    league = load_league(path)
    client = FantasyClient()

    if not args.yes:
        confirm = input("Sell every manager's roster and settle the week? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    round_sold = league.round
    try:
        summaries = settlement.end_week(league, client)
    except ValueError as e:
        raise SystemExit(str(e))

    save_league(league, path)
    save_round_snapshot(league, path, round_sold)
    for line in summaries:
        print(line)


def _reset(args):
    path = Path(args.path)
    league = load_league(path)
    client = FantasyClient()

    if not args.yes:
        confirm = input("Reset every manager's roster for this round (refunds money, does not touch points)? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    try:
        summaries = settlement.reset_all(league, client)
    except ValueError as e:
        raise SystemExit(str(e))

    save_league(league, path)
    for line in summaries:
        print(line)


def _draft(args):
    from .tui import DraftApp

    path = Path(args.path)
    league = load_league(path)
    client = FantasyClient()
    market = client.fetch_current_players()

    DraftApp(league, path, market, client).run()


def add_subcommands(subparsers) -> None:
    league_parser = subparsers.add_parser("league", help="Manage the draft league (managers, rosters, budgets)")
    league_sub = league_parser.add_subparsers(dest="league_command", required=True)

    init = league_sub.add_parser("init", help="Set up a new league or import the current hand-tracked state")
    init.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    init.add_argument("--force", action="store_true", help="Overwrite an existing league file")
    init.set_defaults(func=_init)

    status = league_sub.add_parser("status", help="Show standings, money, rosters, and whose turn is next")
    status.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    status.set_defaults(func=_status)

    pick = league_sub.add_parser("pick", help="Record a draft pick for a manager at its current Fantasy price")
    pick.add_argument("manager", help="Manager name as entered during 'league init'")
    pick.add_argument("item", help="Driver or constructor name (partial match)")
    pick.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    pick.add_argument("--force", action="store_true", help="Bypass the turn-order check")
    pick.set_defaults(func=_pick)

    draft_cmd = league_sub.add_parser("draft", help="Run the draft in an interactive TUI")
    draft_cmd.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    draft_cmd.set_defaults(func=_draft)

    sell = league_sub.add_parser("sell", help="End-of-week settlement: sell every manager's roster and clear it for next week")
    sell.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    sell.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    sell.set_defaults(func=_sell)

    reset = league_sub.add_parser("reset", help="Undo this round's picks: refund the money spent, leave points untouched")
    reset.add_argument("--path", default=str(DEFAULT_LEAGUE_PATH))
    reset.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    reset.set_defaults(func=_reset)
