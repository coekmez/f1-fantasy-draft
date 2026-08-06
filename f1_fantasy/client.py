import requests

from .models import RaceWeekend

FEEDS_URL = "https://fantasy.formula1.com/feeds"


class FantasyClient:
    """Thin wrapper around F1 Fantasy's public JSON feeds. No authentication required."""

    def __init__(self, session: requests.Session = None, timeout: int = 30):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_schedule(self) -> list[RaceWeekend]:
        """One entry per race weekend. Sessions sharing a GamedayId belong to the same weekend."""
        resp = self.session.get(f"{FEEDS_URL}/v2/schedule/raceday_en.json", timeout=self.timeout)
        resp.raise_for_status()
        fixtures = resp.json()["Data"]["fixtures"]

        weekends: dict[str, RaceWeekend] = {}
        for f in fixtures:
            gid = f["GamedayId"]
            weekends[gid] = RaceWeekend(gameday_id=gid, name=f["MeetingName"], status=f["GDStatus"])
        return sorted(weekends.values(), key=lambda w: int(w.gameday_id))

    def fetch_gameday(self, gameday_id: str) -> list[dict]:
        """Every driver/constructor with cumulative season stats as of this race weekend."""
        resp = self.session.get(f"{FEEDS_URL}/drivers/{gameday_id}_en.json", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["Data"]["Value"]
