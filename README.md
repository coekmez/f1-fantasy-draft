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

**Run the draft in a TUI** — a fixed-size frame centered in the terminal
(sized to exactly fit the content, so it doesn't stretch — and leave empty
space in the panes — just because your terminal is bigger), split left and
right:

- Left: Drivers and Constructors, each their own single-column pane with
  current prices sorted highest to lowest, sized to fit every item at once —
  nobody needs to scroll to see the full list. Picking an item doesn't
  remove it from the list; it stays put, struck through, so the list's
  positions and your sense of "where things are" never shift mid-draft.
- Right: every manager in a 2-column grid (rows added as needed for more
  managers), height-matched with the pool panes on the left so both sides
  line up exactly. Each panel always shows all 5 driver slots and 2
  constructor slots — empty ones as `—` placeholders — so every panel is the
  same shape regardless of how full a roster is. The manager on the clock is
  marked by a green border only (no fill), and none of the panes have a
  background fill either — just borders, so nothing bleeds past the rounded
  corners. Slots aren't normally interactive; `t` (see trade mode below)
  turns them into a selectable grid for the duration of the trade.
- Bottom: a persistent, scrollable event log — every pick, trade, sell,
  reset, undo, and redo (plus any errors) prints there and stays, instead of
  popping up as a toast notification that disappears and piles up on top of
  the screen if several things happen in quick succession.
- Top: the header shows two different weeks, since they're not always the
  same — the title is the current live week (whatever the market was
  fetched for), and the subtitle is which week the current picks belong to
  (`league.round`), whose turn it is, and what everyone's budget will reset
  to on the next sell (see "Budgets are always equal" below) for the
  market currently being shown. If the league hasn't drafted since the
  live week moved on, this is the at-a-glance way to notice. The live week
  only ever changes right after a sell (see below) — nothing else moves it.

```
uv run main.py league draft
```

- `↑`/`↓` move within a pane, automatically skipping over already-picked
  (struck-through) items; `←`/`→` jump between the Drivers and Constructors
  panes. `Enter` picks the highlighted item for whoever's turn it is.
- The on-the-clock manager's budget line shows their current money and —
  live, as you move the highlight — what it would drop to if they picked the
  currently-highlighted item (shown in red if it'd go negative).
- `t` opens **trade mode** — no dialog, it's done in place on the right
  side. Only *filled* driver/constructor slots become selectable — empty
  slots stay struck out of the interaction entirely, since there's nothing
  to trade there. `←`/`→` move between managers' rosters, `↑`/`↓` move
  within one, `Enter` picks a slot. Pick a first slot, then a second one of
  the same type (driver-for-driver or constructor-for-constructor) — once
  picked, only matching-category filled slots stay selectable for the second
  pick, so an invalid pairing can't be made in the first place. As you move
  the highlight over a candidate second slot, both managers' budget lines
  live-preview what their money would become if that trade went through
  (red if it'd go negative) — nothing is committed until you actually press
  `Enter` on it, which fires the trade immediately and logs the result.
  Picking the same slot twice, or `Esc` at any point, cancels instead.
  Meant for the deadlock case — a manager can't afford anything left in the
  pool — so someone can hand them a cheaper driver to unstick the draft.
  Budgets adjust automatically by the traded items' current price (give up
  something pricier than you receive and your remaining budget goes up, and
  vice versa); there's no manual cash side-payment, so a trade only ever
  balances against real item value, never moves money for its own sake. An
  invalid trade (unaffordable, over a roster's slot cap) is logged as an
  error and leaves the first selection active so you can try a different
  second slot instead of starting over.
- `s` opens a confirmation dialog for **sell all** — the same end-of-week
  settlement as `league sell` (see below), without leaving the TUI. It
  shows the flat budget everyone will land on ahead of time (see "Budgets
  are always equal" below), computed the same way it'll actually be
  applied, so there's nothing to double-check after confirming. Selling
  isn't just a sell, though — it's what actually turns the crank to the
  next week: once confirmed, the pool refetches and moves on to whatever
  week is now live. This is the only thing that ever advances the live
  week shown in the header.
- `r` opens a confirmation dialog to **reset the round** — the same undo as
  `league reset` (see below), without leaving the TUI.
- `u` **undoes** the most recent pick (refunds its price, removes it from the
  roster it was picked into); `U` (shift+u) **redoes** it. This is separate
  from `r`/reset above — undo/redo works pick-by-pick and is scoped to this
  TUI session (it doesn't survive quitting), while reset wipes the whole
  round at once. Redo is blocked with a clear message if the item's since
  been picked by someone else or its manager can no longer afford it; undo
  is blocked the same way if the item's been traded away since — either way
  the action stays queued so you can try again once the conflict clears.
- `q` (or Ctrl-C) quits; progress is saved after every pick, trade, sell,
  reset, undo, and redo, so re-running `league draft` resumes exactly where
  you left off.

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
settle the week and everyone's budget resets for the next one.

```
uv run main.py league sell
uv run main.py league sell --yes   # skip the confirmation prompt
```

This is global — it settles every manager's entire roster in one go using
the league's current round, then clears all rosters (and the round) so the
next week's picks start from scratch. Each manager is credited with the
points their drivers/constructors earned in that round (not their
whole-season total).

### Budgets are always equal

Money resets to the same flat number for every manager, computed from the
live market — the very same prices next week's picks will be made at:

```
budget = ceil((sum(top X driver prices) + sum(top Y constructor prices)) / num_managers)
```

where `X`/`Y` are drivers-per-manager/constructors-per-manager times the
number of managers — i.e., exactly how many drivers/constructors will
actually end up drafted league-wide. Summing only the top `X`/`Y` (rather
than the whole market) means the glut of cheap items nobody will ever draft
doesn't drag the figure down; dividing that total by the number of managers
is what makes it a fair per-manager share of the whole pool that's actually
in play, rather than the total pool's value itself. There's no "dynamic"
mode where individual performance compounds a manager's budget over
time — everyone always resets to the same number, so nobody's spending
power can diverge from the rest of the league regardless of how their own
picks did.

Pricing off the live week is what makes the figure mean anything: the budget
is sized so everyone can afford a full roster at the prices they're about to
face, and that only holds if it's computed from the week actually being
drafted. If the league skips a few weeks, the budget follows the market to
wherever it's got to, rather than being anchored to a week nobody will pick
in.

Every successful sell also archives a snapshot of the settled state to
`past_weeks/round_<round>.json`, next to the main league file (gitignored,
same as `league.json` — it's local, personal data). This is the only
history the tool keeps — `league.json` itself only ever holds the current
state, so without these snapshots a past week's standings would be gone
the moment the next sell overwrites it. `sell` refuses to run (and touches
nothing) if no round is in progress, if the live week's data can't be
fetched, or if any owned item can't be found in the sold round's data.

**Changed your mind about a round?**

```
uv run main.py league reset
```

Undoes the current round instead of settling it: refunds each manager
exactly the round's price for everything they picked (what they were
actually charged — picks are always made at the current round's price, so
this is a precise undo, not an estimate), clears every roster, and resets
the round. Points are left untouched, since nothing was actually settled.
Unlike `sell`, this doesn't need the live week's data — it only reads the
round being reset.

## Layout

```
f1_fantasy/   # read-only Fantasy data: HTTP client, scoring/domain logic, CLI
league/       # draft league: models, JSON storage, draft domain logic, CLI, TUI (tui.py)
main.py       # composes both packages' subcommands
tests/        # mirrors the above 1:1 — see Testing below
```

## Testing

```
uv run pytest
```

`tests/` mirrors the source layout file-for-file (`f1_fantasy/client.py` ↔
`tests/f1_fantasy/test_client.py`, `league/draft.py` ↔
`tests/league/test_draft.py`, etc.) — when a module changes, its test file
lives at the matching path. Nothing hits the live network: `f1_fantasy`'s
HTTP layer is tested against a mocked `requests.Session`, and everything
above it (`league/draft.py`, `settlement.py`, `store.py`, `cli.py`) runs
against a `FakeClient` fixture (`tests/conftest.py`) that serves canned
`Market`/`Player` data instead. `tests/league/test_tui.py` drives the actual
`DraftApp` through Textual's headless test pilot (`App.run_test()`) —
keypresses, resizes, and widget-tree assertions against the real app, not
mocks of it.

## Building a standalone executable

For sharing with league managers who don't have Python installed. Bundles
the app and its dependencies into a single binary with
[PyInstaller](https://pyinstaller.org/) (already in the `dev` dependency
group):

```
uv run pyinstaller f1-fantasy-draft.spec
```

The binary lands at `dist/f1-fantasy-draft` (`dist\f1-fantasy-draft.exe` on
Windows). Send that one file — nothing else from the repo is needed, and the
recipient doesn't need Python, `uv`, or any dependencies installed. It's
still a terminal app, though: they run it from Terminal/PowerShell/cmd, e.g.
`./f1-fantasy-draft league draft` (or double-click `f1-fantasy-draft.exe` on
Windows, which opens its own console window). `league.json` is created in
whatever directory they run it from.

A couple of things worth knowing:

- **PyInstaller doesn't cross-compile** — a binary built on macOS only runs
  on macOS (and only on that same CPU architecture, e.g. an Apple Silicon
  build won't run on an Intel Mac), same for Windows and Linux. Building for
  a manager on a different OS means building on (or in a VM/CI matching)
  that OS.
- **Unsigned binary warnings**: since this isn't code-signed, macOS
  Gatekeeper and Windows SmartScreen will warn on first launch. On macOS,
  right-click the binary and choose "Open" (instead of double-clicking) to
  get a one-time bypass prompt instead of an outright block. On Windows,
  it's "More info" → "Run anyway" on the SmartScreen dialog.
- `f1-fantasy-draft.spec` is the PyInstaller build recipe (checked in, so
  the build is reproducible); `build/` and `dist/` are the generated output
  and are gitignored.
