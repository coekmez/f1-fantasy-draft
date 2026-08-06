from f1_fantasy.client import FantasyClient

from .models import CONSTRUCTOR_SLOTS, DRIVER_SLOTS, League, Manager


def compute_draft_order(league: League) -> list[str]:
    """Least points first; that order then repeats every round (circular, not snake)."""
    ordered = sorted(league.managers, key=lambda m: (m.points, m.name))
    return [m.name for m in ordered]


def whose_turn(league: League) -> Manager:
    """The fixed draft_order repeats until every manager's roster is full."""
    total_picks = sum(len(m.roster.drivers) + len(m.roster.constructors) for m in league.managers)
    max_picks = len(league.managers) * (DRIVER_SLOTS + CONSTRUCTOR_SLOTS)
    if total_picks >= max_picks:
        return None
    name = league.draft_order[total_picks % len(league.draft_order)]
    return next(m for m in league.managers if m.name == name)


def is_owned(league: League, player_id: str) -> bool:
    return any(
        player_id in m.roster.drivers or player_id in m.roster.constructors
        for m in league.managers
    )


def find_item(market: list[dict], query: str) -> dict:
    query = query.lower()
    matches = [p for p in market if query in p.get("FUllName", "").lower()]
    if not matches:
        raise ValueError(f"No driver or constructor found matching {query!r}")
    if len(matches) > 1:
        names = ", ".join(f'{p["FUllName"]} ({p["PositionName"].title()})' for p in matches)
        raise ValueError(f"Multiple matches for {query!r}: {names}")
    return matches[0]


def make_pick(league: League, client: FantasyClient, manager_name: str, query: str, force: bool = False) -> str:
    """Validate and apply one draft pick at the current fixed price. Mutates league in place."""
    picker = next((m for m in league.managers if m.name == manager_name), None)
    if picker is None:
        raise ValueError(f"No manager named {manager_name!r} in this league")

    turn = whose_turn(league)
    if turn is None:
        raise ValueError("Draft is complete — every roster is full")
    if not force and turn.name != manager_name:
        raise ValueError(f"It's {turn.name}'s turn, not {manager_name}'s (use --force to override)")

    item = find_item(client.fetch_current_players(), query)

    if is_owned(league, item["PlayerId"]):
        raise ValueError(f'{item["FUllName"]} has already been picked')

    if item["PositionName"] == "DRIVER":
        roster_list, slot_limit, slot_name = picker.roster.drivers, DRIVER_SLOTS, "drivers"
    else:
        roster_list, slot_limit, slot_name = picker.roster.constructors, CONSTRUCTOR_SLOTS, "constructors"

    if len(roster_list) >= slot_limit:
        raise ValueError(f"{manager_name}'s {slot_name} roster is already full")

    price = float(item["Value"])
    if price > picker.money:
        raise ValueError(f'{manager_name} cannot afford {item["FUllName"]} (costs {price:g}, has {picker.money:g})')

    roster_list.append(item["PlayerId"])
    picker.money -= price

    return f'{manager_name} picks {item["FUllName"]} for {price:g}'
