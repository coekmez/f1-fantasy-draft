# f1-fantasy-draft

CLI for pulling driver **Fantasy** points from F1's unofficial fantasy API
(fantasy-api.formula1.com) — not real-world championship standings.

## Setup

```
uv sync
uv run playwright install chromium
```

## Usage

List all drivers and their IDs (no login needed):

```
uv run main.py drivers
```

Get a driver's points broken down by race and category:

```
uv run main.py scores "Verstappen"
uv run main.py scores "Verstappen" --json   # raw data instead of the summary
```

The first `scores` call needs to authenticate. It opens a headless browser to
pass F1's Akamai bot check, then logs in with your F1 account credentials —
read from the `F1_EMAIL` / `F1_PASSWORD` environment variables, or typed in
interactively if unset. The resulting session is cached in `.f1_session.json`
so you don't have to log in again on every run; use `--relogin` to force a
fresh login.

## If the automated login gets blocked

Akamai (F1's bot protection) may 403 the login request depending on the
network you're running from, even with a legitimate cookie. If that happens,
grab the auth header manually instead of logging in through the script:

1. Log into <https://fantasy.formula1.com> in your normal browser.
2. Open DevTools → Network, find any request to `fantasy-api.formula1.com`.
3. Copy the value of the `X-F1-Cookie-Data` request header.
4. Set it as an environment variable before running the script:

   ```
   export F1_COOKIE_DATA="<paste the header value here>"
   uv run main.py scores "Verstappen"
   ```

This skips the login flow entirely. It'll expire after a while (F1 doesn't
publish how long) — if requests start failing, just repeat the steps above.

## Notes

- This is an unofficial, undocumented API — no SLA, no public contract, and
  it can change or break without notice.
- `game_periods_scores` returns Fantasy scoring events (qualifying position,
  race position, overtakes, Driver of the Day, penalties, etc.), not the real
  F1 Drivers' Championship. For real standings, use a source like
  [OpenF1](https://openf1.org/) instead.
