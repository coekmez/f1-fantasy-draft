import json
from pathlib import Path

from .models import League, Manager, Roster

DEFAULT_LEAGUE_PATH = Path("league.json")


def _player_id(raw) -> str:
    # Older league.json files stored roster entries as {"player_id": ..., "picked_week": ...}
    # dicts; normalize either shape down to a plain PlayerId string.
    return raw if isinstance(raw, str) else raw["player_id"]


def load_league(path: Path = DEFAULT_LEAGUE_PATH) -> League:
    data = json.loads(path.read_text())
    managers = [
        Manager(
            name=m["name"],
            points=m["points"],
            money=m["money"],
            roster=Roster(
                drivers=[_player_id(e) for e in m["roster"]["drivers"]],
                constructors=[_player_id(e) for e in m["roster"]["constructors"]],
            ),
        )
        for m in data["managers"]
    ]
    return League(managers=managers, draft_order=data.get("draft_order", []), round=data.get("round"))


def save_league(league: League, path: Path = DEFAULT_LEAGUE_PATH) -> None:
    data = {
        "managers": [
            {
                "name": m.name,
                "points": m.points,
                "money": m.money,
                "roster": {"drivers": m.roster.drivers, "constructors": m.roster.constructors},
            }
            for m in league.managers
        ],
        "draft_order": league.draft_order,
        "round": league.round,
    }
    path.write_text(json.dumps(data, indent=2))
