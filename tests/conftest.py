from typing import Optional

import pytest
import requests

from f1_fantasy.models import Market, Player
from league.models import League, new_league


def make_player(
    player_id: str,
    name: str,
    price: float,
    position: str = "DRIVER",
    gameday_points: float = 0.0,
    season_points: float = 0.0,
    sessions: Optional[list] = None,
    category_stats: Optional[dict] = None,
) -> Player:
    """Build a Player directly (bypassing Player.from_feed) for tests that just need
    domain objects, not feed-parsing behavior."""
    return Player(
        player_id=player_id,
        name=name,
        position=position,
        price=price,
        gameday_points=gameday_points,
        season_points=season_points,
        sessions=sessions or [],
        category_stats=category_stats or {},
        raw={"PlayerId": player_id, "FUllName": name, "PositionName": position, "Value": price},
    )


def make_market(players: list, gameday_id: str = "1") -> Market:
    return Market(players, gameday_id=gameday_id)


def make_feed_entry(
    player_id: str,
    name: str,
    price: float,
    position: str = "DRIVER",
    gameday_points: float = 0.0,
    season_points: float = 0.0,
    sessions: Optional[list] = None,
    category_stats: Optional[dict] = None,
) -> dict:
    """Build a raw feed-shaped dict (as F1's API actually returns it), for tests that
    exercise Player.from_feed()/FantasyClient parsing rather than constructing Player
    objects directly."""
    return {
        "PlayerId": player_id,
        "FUllName": name,
        "PositionName": position,
        "Value": price,
        "GamedayPoints": gameday_points,
        "OverallPpints": season_points,
        "SessionWisePoints": sessions if sessions is not None else [
            {"sessionnumber": 1, "sessiontype": "Qualifying", "points": 0, "nonegative_points": 0},
            {"sessionnumber": 2, "sessiontype": "Race", "points": gameday_points, "nonegative_points": gameday_points},
        ],
        "AdditionalStats": category_stats or {},
    }


class FakeClient:
    """A stand-in for FantasyClient in tests: gameday_id -> Market, no network involved."""

    def __init__(self, markets: dict, current_gameday_id: Optional[str] = None, weekends: Optional[list] = None):
        self.markets = markets
        self.current_gameday_id = current_gameday_id or next(iter(markets), None)
        self.weekends = weekends or []

    def fetch_gameday(self, gameday_id: str) -> Market:
        if gameday_id not in self.markets:
            raise requests.HTTPError(f"no fixture data for gameday {gameday_id!r}")
        return self.markets[gameday_id]

    def fetch_current_players(self) -> Market:
        return self.fetch_gameday(self.current_gameday_id)

    def fetch_schedule(self) -> list:
        return self.weekends


@pytest.fixture
def sample_drivers() -> list:
    return [
        make_player("131", "Max Verstappen", 27.6, gameday_points=50.0, season_points=271.0),
        make_player("117", "Lando Norris", 26.1, gameday_points=21.0, season_points=200.0),
        make_player("124", "George Russell", 27.9, gameday_points=25.0, season_points=210.0),
        make_player("13", "Valtteri Bottas", 3.0, gameday_points=0.0, season_points=10.0),
    ]


@pytest.fixture
def sample_constructors() -> list:
    return [
        make_player("29", "Red Bull Racing", 30.9, position="CONSTRUCTOR", gameday_points=45.0),
        make_player("28", "Mercedes", 32.6, position="CONSTRUCTOR", gameday_points=40.0),
    ]


@pytest.fixture
def sample_market(sample_drivers, sample_constructors) -> Market:
    return make_market(sample_drivers + sample_constructors, gameday_id="12")


@pytest.fixture
def four_managers() -> League:
    return new_league(["Alice", "Bob", "Carol", "Dave"])
