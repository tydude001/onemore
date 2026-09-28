# Contributing to onemore

Issues and pull requests are welcome. onemore is maintained by one person in
their spare time, so a reply can take a while.

## Before you start

For anything bigger than a bug fix or a small catalog correction, open an
issue first. `PLAN.md` explains the architecture and the program model, and a
change that fights it will usually be turned down however good the code is.

## The rules a pull request is checked against

- **A rule that changes a plan emits an `Adjustment`.** Every adaptation rule
  writes its rule name and the evidence set ids behind a change; a rule that
  moves a number silently is a bug, not a feature.
- **Nothing depends on RPE.** Strong barely logs it — a percent-of-training-max
  prescription plus a last-set AMRAP is the substitute, and a rule that needs
  RPE to fire stays silent rather than guessing when none is logged.
- **No real training or health data in fixtures, issues, or pull requests.
  Ever.** Test fixtures under `tests/fixtures/` are synthetic. If you're
  filing a bug against your own export, describe the shape of the problem (a
  wrong rounding, a rule that fired when it shouldn't have, a missed import)
  rather than pasting rows, loads, or dates.
- **Don't edit an existing test to make it pass.** If your change and a test
  disagree, say so in the pull request — the test may be the one that's
  right.
- **Loads are stored in kg and rounded only at render time**, per exercise, to
  the catalog's `step_lb`. A catalog edit reaches old history only through
  `Store.remap_exercise_ids`, which every import already runs.
- **Equipment steps and ceilings are catalog data, not constants.** A change
  to what a lift can do belongs in `exercises.toml`, measured from an export,
  not hard-coded in a rule.

## Running the checks

```sh
uv sync
uv run ruff check .
uv run pytest
```

## Commits

Prefix commit messages with `feat:`, `fix:`, or `chore:`.

## How a pull request lands

GitHub is a read-only mirror of the maintainer's own git server, so a pull
request is never merged with GitHub's merge button. The maintainer fetches
your branch, merges it on their side, and the next mirror sync carries it up;
GitHub then marks the pull request merged on its own once your head commit
reaches `main`. If the merge has to be squashed or reworked, the SHAs change
and the pull request is closed by hand with a note naming the commit your
work landed in. Either way, nothing is lost and you'll be credited in the
commit.

By contributing, you agree your contribution is licensed under this
project's [MIT licence](LICENSE).
