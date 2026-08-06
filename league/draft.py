from typing import Optional

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


def apply_pick(league: League, picker: Manager, item: dict, force: bool = False) -> str:
    """Validate and apply one draft pick at the current fixed price. Mutates league in place."""
    turn = whose_turn(league)
    if turn is None:
        raise ValueError("Draft is complete — every roster is full")
    if not force and turn.name != picker.name:
        raise ValueError(f"It's {turn.name}'s turn, not {picker.name}'s (use --force to override)")

    if is_owned(league, item["PlayerId"]):
        raise ValueError(f'{item["FUllName"]} has already been picked')

    if item["PositionName"] == "DRIVER":
        roster_list, slot_limit, slot_name = picker.roster.drivers, DRIVER_SLOTS, "drivers"
    else:
        roster_list, slot_limit, slot_name = picker.roster.constructors, CONSTRUCTOR_SLOTS, "constructors"

    if len(roster_list) >= slot_limit:
        raise ValueError(f"{picker.name}'s {slot_name} roster is already full")

    price = float(item["Value"])
    if price > picker.money:
        raise ValueError(f'{picker.name} cannot afford {item["FUllName"]} (costs {price:g}, has {picker.money:g})')

    roster_list.append(item["PlayerId"])
    picker.money -= price

    return f'{picker.name} picks {item["FUllName"]} for {price:g}'


def make_pick(league: League, client: FantasyClient, manager_name: str, query: str, force: bool = False) -> str:
    """Look up a manager and item by name, then apply the pick. Used by the manual, string-based CLI."""
    picker = next((m for m in league.managers if m.name == manager_name), None)
    if picker is None:
        raise ValueError(f"No manager named {manager_name!r} in this league")

    item = find_item(client.fetch_current_players(), query)
    return apply_pick(league, picker, item, force=force)


def _locate(manager: Manager, player_id: str) -> str:
    if player_id in manager.roster.drivers:
        return "drivers"
    if player_id in manager.roster.constructors:
        return "constructors"
    raise ValueError(f"{manager.name} does not own that item")


def _price(market: list[dict], player_id: Optional[str]) -> float:
    if player_id is None:
        return 0.0
    return float(next(p for p in market if p["PlayerId"] == player_id)["Value"])


def trade(
    league: League,
    market: list[dict],
    manager_a: Manager,
    manager_b: Manager,
    give_a: Optional[str] = None,
    give_b: Optional[str] = None,
) -> str:
    """Swap already-owned items between two managers.

    give_a/give_b are the PlayerIds each manager gives up (None to skip that side). A
    manager's money reflects starting budget minus the value of what they currently
    own, so it's adjusted automatically by the traded items' current Fantasy prices:
    giving up an item frees its price back into your budget, receiving one spends it.
    This only balances budgets against traded item value — there's no manual cash
    side-payment, so a trade can't be used to move money for its own sake.

    A same-category swap (driver<->driver or constructor<->constructor) leaves roster
    sizes unchanged; a one-sided gift is also allowed as long as it doesn't push the
    receiving manager over their slot cap. Doesn't touch turn order — trades can
    happen any time, between any two managers, to unstick one who can't afford
    anything left in the pool.
    """
    if manager_a.name == manager_b.name:
        raise ValueError("Cannot trade with yourself")
    if give_a is None and give_b is None:
        raise ValueError("Nothing to trade")

    slot_a = _locate(manager_a, give_a) if give_a else None
    slot_b = _locate(manager_b, give_b) if give_b else None

    if give_a and give_b and slot_a != slot_b:
        raise ValueError("Can only trade a driver for a driver, or a constructor for a constructor")

    limits = {"drivers": DRIVER_SLOTS, "constructors": CONSTRUCTOR_SLOTS}
    if give_a and not give_b and len(getattr(manager_b.roster, slot_a)) + 1 > limits[slot_a]:
        raise ValueError(f"{manager_b.name}'s {slot_a} roster would exceed the {limits[slot_a]}-slot limit")
    if give_b and not give_a and len(getattr(manager_a.roster, slot_b)) + 1 > limits[slot_b]:
        raise ValueError(f"{manager_a.name}'s {slot_b} roster would exceed the {limits[slot_b]}-slot limit")

    value_a, value_b = _price(market, give_a), _price(market, give_b)
    new_money_a = manager_a.money + value_a - value_b
    new_money_b = manager_b.money + value_b - value_a

    if new_money_a < 0:
        raise ValueError(f"{manager_a.name} does not have enough money for this trade")
    if new_money_b < 0:
        raise ValueError(f"{manager_b.name} does not have enough money for this trade")

    if give_a:
        getattr(manager_a.roster, slot_a).remove(give_a)
        getattr(manager_b.roster, slot_a).append(give_a)
    if give_b:
        getattr(manager_b.roster, slot_b).remove(give_b)
        getattr(manager_a.roster, slot_b).append(give_b)

    manager_a.money = new_money_a
    manager_b.money = new_money_b

    return f"Trade complete between {manager_a.name} and {manager_b.name}"
