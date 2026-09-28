"""Derive per-exercise load steps and observed ceilings from the imported history.

Not part of the package and not imported by it: an analysis whose reviewed output becomes
the `step_lb` catalog data in exercises.toml. The review record is
docs/research/equipment-increments.md, which explains why the step is the *modal*
difference between consecutive distinct loads rather than their GCD or their minimum.

Grouped by canonical exercise id, because that is the unit `step_lb` applies to. An id
covering several Strong names also prints those names, so a bad catalog merge shows up as
one id whose names disagree about their step.

    uv run python scripts/derive_increments.py [path/to/onemore.db]
"""
import sqlite3
import sys
from collections import Counter
from itertools import pairwise

KG_PER_LB = 0.45359237
db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "data/onemore.db")

rows = db.execute(
    "SELECT e.exercise_id, e.source_name, s.weight_kg FROM sets s"
    " JOIN entries e ON s.entry_id = e.id"
    " WHERE s.weight_kg IS NOT NULL AND s.weight_kg > 0"
).fetchall()

by_ex = {}
names = {}
for eid, raw, kg in rows:
    by_ex.setdefault(eid, []).append(kg / KG_PER_LB)
    names.setdefault(eid, set()).add(raw)

out = []
for eid, lbs in by_ex.items():
    # Loads are stored in kg after a lb->kg import, so they come back with float dust.
    distinct = sorted({round(x, 1) for x in lbs})
    diffs = [round(b - a, 1) for a, b in pairwise(distinct)]
    modal = Counter(diffs).most_common(1)[0] if diffs else (None, 0)
    out.append({
        "id": eid, "raw": sorted(names[eid]), "n_sets": len(lbs), "n_distinct": len(distinct),
        "min": distinct[0], "max": distinct[-1],
        "step": modal[0], "step_support": modal[1], "n_diffs": len(diffs),
        "distinct": distinct,
        "odd": [d for d in sorted(set(diffs)) if modal[0] and d % modal[0] != 0],
    })

out.sort(key=lambda r: -r["n_sets"])
print(f"{'exercise_id':34} {'sets':>4} {'dist':>4} {'min':>6} {'max':>6} {'step':>5} {'conf':>7}  odd diffs")
for r in out:
    conf = f"{r['step_support']}/{r['n_diffs']}" if r["n_diffs"] else "-"
    print(f"{r['id']:34} {r['n_sets']:4} {r['n_distinct']:4} {r['min']:6.1f} {r['max']:6.1f} "
          f"{r['step']!s:>5} {conf:>7}  {r['odd'] if r['odd'] else ''}")
    if len(r["raw"]) > 1:
        print(f"{'':34} from {', '.join(repr(x) for x in r['raw'])}")
