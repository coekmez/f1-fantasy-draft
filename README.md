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
- `q` (or Ctrl-C) quits; progress is saved after every pick and trade, so
  re-running `league draft` resumes exactly where you left off.

**Or record a single pick manually** — useful for fixing a mistake without
going through the whole interactive flow:

```
uv run main.py league pick Dave Verstappen
uv run main.py league pick Alice "Red Bull" --force   # bypass the turn check
```

Both paths validate the same rules: turn order (manual picks can bypass this
with `--force`), one owner per driver/constructor league-wide,
5-driver/2-constructor roster caps, and enough money to afford the price.

## Layout

```
f1_fantasy/   # read-only Fantasy data: HTTP client, scoring/domain logic, CLI
league/       # draft league: models, JSON storage, draft domain logic, CLI, TUI (tui.py)
main.py       # composes both packages' subcommands
```
