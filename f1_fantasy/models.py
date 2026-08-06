from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RaceWeekend:
    gameday_id: str
    name: str
    status: int  # 0 = upcoming, 1 = in progress, 4 = completed

    @property
    def is_completed(self) -> bool:
        return self.status == 4


@dataclass
class SessionPoints:
    session_type: str  # e.g. "Qualifying", "Sprint Qualifying", "Race"
    points: int


@dataclass
class RaceBreakdown:
    weekend: RaceWeekend
    points: float
    sessions: list[SessionPoints]
    categories: dict[str, float]  # category label -> points delta for this race


@dataclass(frozen=True)
class Player:
    """A driver or constructor's state as of one race weekend's snapshot from F1's feed."""

    player_id: str
    name: str
    position: str  # "DRIVER" or "CONSTRUCTOR"
    price: float
    gameday_points: float
    season_points: float
    sessions: list[SessionPoints]
    category_stats: dict[str, float]  # cumulative season-to-date as of this weekend
    raw: dict = field(repr=False)  # the original feed entry, for lossless --json passthrough

    @property
    def is_driver(self) -> bool:
        return self.position == "DRIVER"

    @property
    def is_constructor(self) -> bool:
        return self.position == "CONSTRUCTOR"

    @classmethod
    def from_feed(cls, data: dict) -> "Player":
        sessions = [
            SessionPoints(session_type=s["sessiontype"], points=s["points"])
            for s in data["SessionWisePoints"]
            if s["points"] is not None
        ]
        return cls(
            player_id=data["PlayerId"],
            name=data["FUllName"],
            position=data["PositionName"],
            price=float(data["Value"]),
            gameday_points=float(data["GamedayPoints"]),
            season_points=float(data["OverallPpints"]),
            sessions=sessions,
            category_stats=data["AdditionalStats"],
            raw=data,
        )


class Market:
    """All drivers/constructors as of one race weekend snapshot, indexed for lookup."""

    def __init__(self, players: list[Player], gameday_id: str):
        self.players = players
        self.gameday_id = gameday_id
        self._by_id = {p.player_id: p for p in players}

    def by_id(self, player_id: str) -> Optional[Player]:
        return self._by_id.get(player_id)

    def name_of(self, player_id: str) -> str:
        player = self.by_id(player_id)
        return player.name if player else player_id

    def drivers(self) -> list[Player]:
        return [p for p in self.players if p.is_driver]

    def constructors(self) -> list[Player]:
        return [p for p in self.players if p.is_constructor]

    def __iter__(self):
        return iter(self.players)

    def __len__(self):
        return len(self.players)
