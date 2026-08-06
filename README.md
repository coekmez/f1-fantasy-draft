# f1-fantasy-draft

Tools for a 4-manager F1 Fantasy draft league:

- Pull driver/constructor **Fantasy** points (not real-world championship
  standings) from F1's public JSON feeds — no login required.
- Track a locally-run, fixed-price draft: 4 managers, 5 drivers + 2
  constructors each, turn order fixed by standings and repeating circularly
  (not snake). Each pick costs whatever that driver/constructor's current
  official Fantasy price is.

## Setup

```
uv sync
```

## Fantasy points

```
uv run main.py drivers                        # list drivers + IDs
uv run main.py constructors                    # list constructors + IDs
uv run main.py scores "Verstappen"              # per-race points breakdown
uv run main.py constructor-scores "Ferrari"
uv run main.py scores "Verstappen" --json       # raw data instead of a summary
uv run main.py prices                           # every driver/constructor's current price, for reference
```

Data comes from `fantasy.formula1.com/feeds/...`. It's unofficial and
undocumented (no SLA, can change without notice), but requires no
authentication. The category breakdown (Overtakes, DOTD, DNF/DSQ, etc.) is
derived by diffing F1's cumulative season stats between race weekends, so it
covers the biggest scoring buckets but isn't always a byte-perfect itemized
ledger of every point.

## Draft league

State (managers, points, money, rosters) lives in `league.json` (gitignored —
it's local, personal data).

**Set up or import the league's current hand-tracked state:**

```
uv run main.py league init
```

Prompts for the 4 manager names, then each manager's current points and
money. Draft order is fixed at this point: least points goes first, then that
same order repeats every round.

**Check standings, rosters, and whose turn is next:**

```
uv run main.py league status
```

**Run the draft in a TUI** — a full-screen terminal interface: available
drivers/constructors with prices on the left (navigate with the arrow keys),
all 4 managers' points, budget, and rosters on the right, with the manager on
the clock highlighted:

```
uv run main.py league draft
```

- `Enter` picks the highlighted item for whoever's turn it is.
- The on-the-clock manager's budget shows three lines: starting budget for
  this session, current remaining, and — live, as you move the highlight —
  what would remain if they picked the currently-highlighted item (shown in
  red if it'd go negative).
- `t` opens **trade mode**: a dialog to swap already-drafted items
  (driver-for-driver or constructor-for-constructor) between any two
  managers. Meant for the deadlock case — a manager can't afford anything
  left in the pool — so someone can hand them a cheaper driver to unstick the
  draft. Budgets adjust automatically by the traded items' current price
  (give up something pricier than you receive and your remaining budget goes
  up, and vice versa); there's no manual cash side-payment, so a trade only
  ever balances against real item value, never moves money for its own sake.
- `s` opens a confirmation dialog for **sell all** — the same end-of-week
  settlement as `league sell` (see below), without leaving the TUI. On
  confirm it also resets the "starting budget" baseline shown in each panel
  to the new post-sell money, since that's the start of the next week.
- `q` (or Ctrl-C) quits; progress is saved after every pick, trade, and sell,
  so re-running `league draft` resumes exactly where you left off.

**Or record a single pick manually** — useful for fixing a mistake without
going through the whole interactive flow:

```
uv run main.py league pick Dave Verstappen
uv run main.py league pick Alice "Red Bull" --force   # bypass the turn check
```

Both paths validate the same rules: turn order (manual picks can bypass this
with `--force`), one owner per driver/constructor league-wide,
5-driver/2-constructor roster caps, and enough money to afford the price.

The league also tracks one **round** — the race weekend everyone's currently
drafting for. It's `None` until the first pick of a fresh cycle, which sets
it (visible in `league status` and the TUI header); every pick and trade
after that shares the same round, since a league picks together in one
sitting. `league sell` (below) clears it again once the week is settled.

**One week of the draft is: pick -> race happens -> sell.** After the race,
settle the week — this is how a manager's budget grows, exactly like real F1
Fantasy: a driver who performed well is now worth more, and you realize that
gain by selling.

```
uv run main.py league sell
```

This is global — it settles every manager's entire roster in one go using
the league's current round, then clears all rosters (and the round) so the
next week's picks start from scratch. Each manager is credited with the
points their drivers/constructors earned in that round (not their
whole-season total), and each item's price *in the round right after the
pick* — not whatever the market shows today. The league doesn't always
convene every week, so pricing off "today" would mean a manager's payout
depends on drift from extra weeks they didn't control, instead of the value
change their own pick's result actually caused. It refuses to run (and
touches nothing) if no round is in progress, if that following round's data
isn't published yet, or if any owned item
can't be found in that round's data.

## Layout

```
f1_fantasy/   # read-only Fantasy data: HTTP client, scoring/domain logic, CLI
league/       # draft league: models, JSON storage, draft domain logic, CLI, TUI (tui.py)
main.py       # composes both packages' subcommands
```
