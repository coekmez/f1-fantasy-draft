import json
from pathlib import Path

from .models import League, Manager, Roster

DEFAULT_LEAGUE_PATH = Path("league.json")


def load_league(path: Path = DEFAULT_LEAGUE_PATH) -> League:
    data = json.loads(path.read_text())
    managers = [
        Manager(
            name=m["name"],
            points=m["points"],
            money=m["money"],
            roster=Roster(drivers=m["roster"]["drivers"], constructors=m["roster"]["constructors"]),
        )
        for m in data["managers"]
    ]
    return League(managers=managers, draft_order=data.get("draft_order", []))


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
    }
    path.write_text(json.dumps(data, indent=2))
