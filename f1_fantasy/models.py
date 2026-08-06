from dataclasses import dataclass


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
