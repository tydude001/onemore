"""Resolve a Week against lift state into concrete, plate-rounded prescriptions."""

from __future__ import annotations

from dataclasses import dataclass

from .. import estimate
from ..units import from_kg, round_load, to_kg
from .spec import Abs, Bodyweight, Pct, Rpe, Sets, Week


@dataclass(frozen=True, slots=True)
class Prescribed:
    lift: str
    sets: int
    reps: int | tuple[int, int]
    load_kg: float | None  # None: no state to resolve against, or bodyweight
    amrap: bool
    rpe_target: float | None
    how: str  # human explanation of where the number came from
    rest_s: int | None = None


@dataclass(slots=True)
class RenderedSlot:
    lift: str
    name: str
    prescribed: list[Prescribed]
    note: str = ""
    warmup: list[tuple[float, int]] | None = None  # (kg, reps) ramp to the first set


@dataclass(slots=True)
class RenderedDay:
    name: str
    slots: list[RenderedSlot]


@dataclass(slots=True)
class RenderedWeek:
    number: int
    kind: str
    label: str
    days: list[RenderedDay]
    unit: str
    steps: dict[str, float]  # lift id -> smallest load jump, in `unit`
    fallback_step: float  # for a lift the catalog has no step for, also in `unit`

    def step(self, lift: str) -> float:
        return self.steps.get(lift, self.fallback_step)


def bump_reps(reps: int | tuple[int, int], delta: int) -> int | tuple[int, int]:
    """Shift a prescribed rep target or range up by `delta`. This is how the reps half of
    `dumbbell_ceiling` reaches the plan: without it the rule's state would be written and
    never read, which is a plan changed silently."""
    if not delta:
        return reps
    if isinstance(reps, int):
        return reps + delta
    return (reps[0] + delta, reps[1] + delta)


def resolve_sets(lift: str, s: Sets, state: dict[str, float | None], sets_delta: int,
                 reps_delta: int = 0, provisional_tm: float | None = None) -> Prescribed:
    n = max(1, s.n + sets_delta)
    reps = bump_reps(s.reps, reps_delta)
    load = s.load
    tm = state.get("tm_kg")
    e1 = state.get("e1rm_kg")
    if isinstance(load, Pct):
        base = tm if load.of == "tm" else e1
        if base is None and load.of == "tm" and provisional_tm is not None:
            # engine.provisional_tms: what calibrate_new_lift will set, shown meanwhile.
            return Prescribed(lift, n, reps, provisional_tm * load.value, s.amrap, None,
                              f"{load.value:.0%} of provisional tm {provisional_tm:.1f} kg",
                              s.rest_s)
        if base is None:
            return Prescribed(lift, n, reps, None, s.amrap, None,
                              f"{load.value:.0%} of {load.of}, but no {load.of} yet", s.rest_s)
        return Prescribed(lift, n, reps, base * load.value, s.amrap, None,
                          f"{load.value:.0%} of {load.of} {base:.1f} kg", s.rest_s)
    if isinstance(load, Rpe):
        if e1 is None:
            return Prescribed(lift, n, reps, None, s.amrap, load.value,
                              f"work up to RPE {load.value:g}; no estimate yet", s.rest_s)
        low = reps if isinstance(reps, int) else reps[0]
        try:
            kg = estimate.load_for(load.value, low, e1)
        except ValueError:
            return Prescribed(lift, n, reps, None, s.amrap, load.value,
                              f"RPE {load.value:g}; reps outside the RPE table", s.rest_s)
        return Prescribed(lift, n, reps, kg, s.amrap, load.value,
                          f"RPE {load.value:g} x{low} from e1RM {e1:.1f} kg", s.rest_s)
    if isinstance(load, Abs):
        return Prescribed(lift, n, reps, load.kg, s.amrap, None, "fixed load", s.rest_s)
    if isinstance(load, Bodyweight):
        return Prescribed(lift, n, reps, load.added_kg or None, s.amrap, None,
                          "bodyweight" + (f" +{load.added_kg:.1f} kg" if load.added_kg else ""),
                          s.rest_s)
    raise TypeError(load)


def render_week(week: Week, states: dict[str, dict[str, float | None]], catalog, unit="lb",
                fallback_step_lb: float = 5.0,
                provisional: dict[str, float] | None = None) -> RenderedWeek:
    """Resolve a week's prescriptions. Rounding is per exercise, from the catalog.

    `catalog` supplies both the display name and the load step, because both are facts
    about the exercise. A single global rounding constant cannot be right at a gym where
    the leg press moves in 5 lb, the machine curl in 2.5 and the pulldown in 10.

    `provisional` is {lift: TM kg} for main lifts with no TM yet (engine.provisional_tms);
    it is used only where the lift's state has no `tm_kg`.
    """
    days = []
    steps: dict[str, float] = {}
    for d in week.days:
        slots = []
        for slot in d.slots:
            st = states.get(slot.lift, {})
            delta = int(st.get("sets_delta") or 0)
            rdelta = int(st.get("reps_delta") or 0)
            ptm = (provisional or {}).get(slot.lift)
            pres = [resolve_sets(slot.lift, s, st, delta, rdelta, ptm) for s in slot.sets]
            warm = None
            if slot.warmup and pres and pres[0].load_kg:
                warm = [(pres[0].load_kg * frac, reps) for frac, reps in slot.warmup.steps]
            slots.append(RenderedSlot(slot.lift, catalog.name(slot.lift), pres, slot.note, warm))
            steps[slot.lift] = from_kg(catalog.step_kg(slot.lift, fallback_step_lb), unit)
        days.append(RenderedDay(d.name, slots))
    fallback = from_kg(to_kg(fallback_step_lb, "lb"), unit)
    return RenderedWeek(week.number, str(week.kind), week.label, days, unit, steps, fallback)


def fmt_reps(reps: int | tuple[int, int]) -> str:
    return str(reps) if isinstance(reps, int) else f"{reps[0]}-{reps[1]}"


def fmt_rest(rest_s: int | None) -> str:
    if not rest_s:
        return ""
    return f"rest {rest_s // 60}:{rest_s % 60:02d}" if rest_s >= 60 else f"rest {rest_s}s"


def warmup_steps(warm: list[tuple[float, int]] | None, top_kg: float | None, unit: str,
                 step: float) -> list[tuple[float, int]]:
    """The ramp as (load in `unit`, reps), rounded on the lift's step. A rung that rounds
    to nothing, repeats the previous one, or reaches the working load is dropped."""
    if not warm:
        return []
    out: list[tuple[float, int]] = []
    prev = None
    top = round_load(top_kg, unit, step) if top_kg else None
    for kg, reps in warm:
        v = round_load(kg, unit, step)
        if v <= 0 or v == prev or (top is not None and v >= top):
            continue
        out.append((v, reps))
        prev = v
    return out


def fmt_warmup(warm: list[tuple[float, int]] | None, top_kg: float | None, unit: str,
               step: float) -> str:
    """`75x8, 115x5, 150x3` — see warmup_steps for what is dropped."""
    return ", ".join(f"{v:g}x{reps}" for v, reps in warmup_steps(warm, top_kg, unit, step))


def fmt_load(p: Prescribed, unit: str, step: float) -> str:
    """`step` is this exercise's own load jump, in `unit` — see RenderedWeek.step()."""
    if p.load_kg is None:
        # Bodyweight, or a percentage with nothing to resolve against yet: `how` says
        # which, and "60% of tm, but no tm yet" must not print as "bodyweight".
        return f"@RPE {p.rpe_target:g}" if p.rpe_target else p.how
    v = round_load(p.load_kg, unit, step)
    s = f"{v:g} {unit}"
    if p.rpe_target:
        s += f" (~RPE {p.rpe_target:g})"
    return s


def to_text(rw: RenderedWeek, previous: dict[str, str] | None = None,
            notes: dict[str, list[str]] | None = None, header: str = "") -> str:
    out = [f"Week {rw.number} — {rw.kind}" + (f" ({rw.label})" if rw.label else "")]
    if header:
        out.append(header)
    for d in rw.days:
        out.append(f"\n{d.name}")
        for s in d.slots:
            parts = []
            for p in s.prescribed:
                scheme = f"{p.sets}x{fmt_reps(p.reps)}" + ("+" if p.amrap else "")
                rest = fmt_rest(p.rest_s)
                parts.append(f"{scheme} {fmt_load(p, rw.unit, rw.step(s.lift))}"
                             + (f" ({rest})" if rest else ""))
            line = f"  {s.name}: " + ", ".join(parts)
            if s.note:
                line += f"  [{s.note}]"
            out.append(line)
            warm = fmt_warmup(s.warmup, s.prescribed[0].load_kg if s.prescribed else None,
                              rw.unit, rw.step(s.lift))
            if warm:
                out.append(f"      warm-up: {warm}")
            if previous and s.lift in previous:
                out.append(f"      last: {previous[s.lift]}")
            for n in (notes or {}).get(s.lift, []):
                out.append(f"      why: {n}")
    return "\n".join(out)


def to_html(rw: RenderedWeek, previous: dict[str, str] | None = None,
            notes: dict[str, list[str]] | None = None, header: str = "") -> str:
    import html

    h = [
        (
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,"
            "initial-scale=1'><title>onemore</title><style>body{font:17px/1.4 -apple-system,system-ui,"
            "sans-serif;margin:1rem;max-width:40rem;color:#111;background:#fafafa}h2{margin:1.2rem 0 "
            ".3rem}.s{padding:.4rem 0;border-top:1px solid #ddd}.n{font-weight:600}.l{color:#333}.p,"
            ".w{font-size:.85em;color:#666}@media(prefers-color-scheme:dark){body{background:#111;"
            "color:#eee}.l{color:#ddd}.s{border-color:#333}.p,.w{color:#999}}</style>"
        ),
        f"<h1>Week {rw.number} <small>{html.escape(rw.kind)}"
        + (f" · {html.escape(rw.label)}" if rw.label else "") + "</small></h1>",
    ]
    if header:
        h.append(f"<div class=p>{html.escape(header)}</div>")
    for d in rw.days:
        h.append(f"<h2>{html.escape(d.name)}</h2>")
        for s in d.slots:
            parts = []
            for p in s.prescribed:
                scheme = f"{p.sets}×{fmt_reps(p.reps)}" + ("+" if p.amrap else "")
                rest = fmt_rest(p.rest_s)
                parts.append(f"{scheme} {html.escape(fmt_load(p, rw.unit, rw.step(s.lift)))}"
                             + (f" <span class=p>{rest}</span>" if rest else ""))
            h.append(f"<div class=s><div class=n>{html.escape(s.name)}</div>"
                     f"<div class=l>{' · '.join(parts)}</div>")
            warm = fmt_warmup(s.warmup, s.prescribed[0].load_kg if s.prescribed else None,
                              rw.unit, rw.step(s.lift))
            if warm:
                h.append(f"<div class=p>warm-up: {html.escape(warm)}</div>")
            if s.note:
                h.append(f"<div class=p>{html.escape(s.note)}</div>")
            if previous and s.lift in previous:
                h.append(f"<div class=p>last: {html.escape(previous[s.lift])}</div>")
            for n in (notes or {}).get(s.lift, []):
                h.append(f"<div class=w>why: {html.escape(n)}</div>")
            h.append("</div>")
    return "".join(h)
