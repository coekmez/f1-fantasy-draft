from dataclasses import dataclass, field

DRIVER_SLOTS = 5
CONSTRUCTOR_SLOTS = 2


@dataclass
class Roster:
    drivers: list[str] = field(default_factory=list)  # F1 PlayerIds
    constructors: list[str] = field(default_factory=list)  # F1 PlayerIds

    @property
    def is_full(self) -> bool:
        return len(self.drivers) >= DRIVER_SLOTS and len(self.constructors) >= CONSTRUCTOR_SLOTS


@dataclass
class Manager:
    name: str
    points: float
    money: float
    roster: Roster = field(default_factory=Roster)


@dataclass
class League:
    managers: list[Manager] = field(default_factory=list)
    draft_order: list[str] = field(default_factory=list)  # manager names, fixed at draft start


def new_league(manager_names: list[str]) -> League:
    return League(managers=[Manager(name=n, points=0.0, money=0.0, roster=Roster()) for n in manager_names])
