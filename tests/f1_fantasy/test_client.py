from unittest.mock import MagicMock

import pytest
import requests

from f1_fantasy.client import FantasyClient
from f1_fantasy.models import Market

from ..conftest import make_feed_entry


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def make_session(responses_by_url_substring: dict) -> MagicMock:
    """A fake requests.Session whose .get() is routed by URL substring, so tests don't
    touch the network."""
    session = MagicMock()

    def fake_get(url, timeout=None):
        for substring, response in responses_by_url_substring.items():
            if substring in url:
                return response
        raise AssertionError(f"Unexpected URL requested: {url}")

    session.get.side_effect = fake_get
    return session


class TestFetchSchedule:
    def test_dedupes_sessions_sharing_a_gameday_id(self):
        payload = {"Data": {"fixtures": [
            {"GamedayId": "1", "MeetingName": "Australian Grand Prix", "GDStatus": 4},
            {"GamedayId": "1", "MeetingName": "Australian Grand Prix", "GDStatus": 4},
            {"GamedayId": "2", "MeetingName": "Chinese Grand Prix", "GDStatus": 1},
        ]}}
        session = make_session({"schedule/raceday_en.json": FakeResponse(payload)})
        client = FantasyClient(session=session)

        weekends = client.fetch_schedule()

        assert [w.gameday_id for w in weekends] == ["1", "2"]
        assert weekends[0].name == "Australian Grand Prix"
        assert weekends[0].status == 4
        assert weekends[1].status == 1

    def test_sorts_numerically_not_lexicographically(self):
        payload = {"Data": {"fixtures": [
            {"GamedayId": "10", "MeetingName": "X", "GDStatus": 0},
            {"GamedayId": "2", "MeetingName": "Y", "GDStatus": 0},
        ]}}
        session = make_session({"schedule/raceday_en.json": FakeResponse(payload)})
        client = FantasyClient(session=session)

        weekends = client.fetch_schedule()

        # lexicographic sort would put "10" before "2" — confirm it doesn't
        assert [w.gameday_id for w in weekends] == ["2", "10"]

    def test_coerces_a_numeric_gameday_id_to_a_string(self):
        # regression: the real feed's JSON can carry GamedayId as a number, not a
        # string, despite RaceWeekend.gameday_id being typed str — a consumer that
        # actually enforces that type (e.g. a Textual Input widget) crashes outright
        # on a raw int, so this must be coerced right where it's parsed
        payload = {"Data": {"fixtures": [{"GamedayId": 12, "MeetingName": "X", "GDStatus": 0}]}}
        session = make_session({"schedule/raceday_en.json": FakeResponse(payload)})
        client = FantasyClient(session=session)

        weekends = client.fetch_schedule()

        assert weekends[0].gameday_id == "12"
        assert isinstance(weekends[0].gameday_id, str)


class TestFetchGameday:
    def test_parses_players_into_a_market(self):
        payload = {"Data": {"Value": [
            make_feed_entry("131", "Max Verstappen", 27.6),
            make_feed_entry("29", "Red Bull Racing", 30.9, position="CONSTRUCTOR"),
        ]}}
        session = make_session({"drivers/12_en.json": FakeResponse(payload)})
        client = FantasyClient(session=session)

        market = client.fetch_gameday("12")

        assert isinstance(market, Market)
        assert market.gameday_id == "12"
        assert market.by_id("131").name == "Max Verstappen"
        assert len(market) == 2

    def test_raises_on_http_error(self):
        session = make_session({"drivers/13_en.json": FakeResponse({}, status_code=403)})
        client = FantasyClient(session=session)

        with pytest.raises(requests.HTTPError):
            client.fetch_gameday("13")

    def test_coerces_an_integer_gameday_id_argument_to_a_string(self):
        # a RaceWeekend.gameday_id could reach here as a real int (see
        # TestFetchSchedule.test_coerces_a_numeric_gameday_id_to_a_string) before that
        # fix, or from any other caller passing one directly
        payload = {"Data": {"Value": [make_feed_entry("131", "Max Verstappen", 27.6)]}}
        session = make_session({"drivers/12_en.json": FakeResponse(payload)})
        client = FantasyClient(session=session)

        market = client.fetch_gameday(12)

        assert market.gameday_id == "12"
        assert isinstance(market.gameday_id, str)


class TestFetchCurrentPlayers:
    def test_uses_latest_in_progress_weekend_over_a_later_upcoming_one(self):
        schedule = {"Data": {"fixtures": [
            {"GamedayId": "1", "MeetingName": "R1", "GDStatus": 4},
            {"GamedayId": "2", "MeetingName": "R2", "GDStatus": 1},
            {"GamedayId": "3", "MeetingName": "R3", "GDStatus": 0},
        ]}}
        gameday_2 = {"Data": {"Value": [make_feed_entry("131", "Max Verstappen", 27.6)]}}
        session = make_session({
            "schedule/raceday_en.json": FakeResponse(schedule),
            "drivers/2_en.json": FakeResponse(gameday_2),
        })
        client = FantasyClient(session=session)

        market = client.fetch_current_players()

        assert market.gameday_id == "2"

    def test_falls_back_to_latest_completed_when_none_in_progress(self):
        schedule = {"Data": {"fixtures": [
            {"GamedayId": "1", "MeetingName": "R1", "GDStatus": 4},
            {"GamedayId": "2", "MeetingName": "R2", "GDStatus": 4},
            {"GamedayId": "3", "MeetingName": "R3", "GDStatus": 0},
        ]}}
        gameday_2 = {"Data": {"Value": []}}
        session = make_session({
            "schedule/raceday_en.json": FakeResponse(schedule),
            "drivers/2_en.json": FakeResponse(gameday_2),
        })
        client = FantasyClient(session=session)

        market = client.fetch_current_players()

        assert market.gameday_id == "2"
