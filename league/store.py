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
    return League(
        managers=managers,
        draft_order=data.get("draft_order", []),
        round=data.get("round"),
    )


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


def save_round_snapshot(league: League, path: Path, round_number: str) -> None:
    """Archive the settled state of a just-sold round to past_weeks/, next to the
    live league file, so history survives being overwritten by future sells. Safe
    to call more than once for the same round — it just overwrites that round's
    snapshot rather than piling up duplicates."""
    snapshot_dir = path.parent / "past_weeks"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    save_league(league, snapshot_dir / f"round_{round_number}.json")
