/* onemore — the app. Vanilla JS over /api/*, no build step, no CDN. */
(() => {
  "use strict";

  // ---------------------------------------------------------------- utilities
  const $ = (sel, el = document) => el.querySelector(sel);
  const main = $("#main");

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const svgNS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(svgNS, tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
    for (const kid of kids.flat(Infinity)) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return el;
  }
  const link = (href, attrs, ...kids) => h("a", { href, "data-link": true, ...attrs }, ...kids);

  const ls = {
    get(k, d = null) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fmt = {
    n(v, nd = 0) { return v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: nd, minimumFractionDigits: 0 }); },
    load(v) { if (v == null) return "—"; const r = Math.round(v * 10) / 10; return Number.isInteger(r) ? String(r) : r.toFixed(1); },
    date(iso, year = true) { if (!iso) return "—"; const d = new Date(iso.slice(0, 10) + "T12:00:00"); return `${MONTHS[d.getMonth()]} ${d.getDate()}${year ? ", " + d.getFullYear() : ""}`; },
    ago(iso) {
      if (!iso) return "";
      const days = Math.round((Date.now() - new Date(iso.slice(0, 10) + "T12:00:00")) / 864e5);
      if (days <= 0) return "today"; if (days === 1) return "yesterday"; if (days < 14) return `${days} d ago`;
      if (days < 60) return `${Math.round(days / 7)} wk ago`; if (days < 365) return `${Math.round(days / 30)} mo ago`;
      const y = Math.floor(days / 365), m = Math.round((days % 365) / 30); return `${y} y${m ? " " + m + " mo" : ""} ago`;
    },
    rest(sec) { if (!sec) return ""; return sec >= 60 ? `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}` : `${sec}s`; },
    dur(sec) { if (!sec) return ""; const hh = Math.floor(sec / 3600), mm = Math.round((sec % 3600) / 60); return hh ? `${hh}h ${mm}m` : `${mm}m`; },
    set(st) { const w = st.w == null ? "bw" : fmt.load(st.w); return `${w}×${st.r ?? "?"}${st.rpe ? "@" + st.rpe : ""}`; },
  };

  let toastTimer;
  function toast(msg, err = false) {
    const t = $("#toast"); t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, err ? 6000 : 2800);
  }

  const cache = new Map();
  async function get(path, fresh = false) {
    if (!fresh && cache.has(path)) return cache.get(path);
    const r = await fetch(path, { headers: { Accept: "application/json" } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(body.error || r.statusText), { status: r.status, body });
    cache.set(path, body);
    return body;
  }
  async function post(path, body, raw = false) {
    const token = ls.get("token", "");
    const r = await fetch(path, {
      method: "POST",
      headers: raw ? { "X-Token": token } : { "X-Token": token, "Content-Type": "application/json" },
      body: raw ? body : JSON.stringify(body || {}),
    });
    const out = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok) throw Object.assign(new Error(out.error || r.statusText), { status: r.status });
    cache.clear();
    return out;
  }

  // ------------------------------------------------------------------ theme
  const themeBtn = $("#theme-toggle");
  const SUN = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  const themeParam = new URLSearchParams(location.search).get("theme");
  if (themeParam === "light" || themeParam === "dark") ls.set("theme", themeParam);
  function applyTheme() {
    const t = ls.get("theme");
    if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
    const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    // pale.css scopes its dark tokens to :root.dark, so carry the resolved
    // choice onto the class as well as the data attribute.
    document.documentElement.classList.toggle("dark", dark);
    themeBtn.innerHTML = dark ? SUN : MOON;
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!ls.get("theme")) applyTheme();
  });
  themeBtn.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    ls.set("theme", dark ? "light" : "dark"); applyTheme();
  });
  applyTheme();

  // ----------------------------------------------------------------- charts
  function niceTicks(lo, hi, n = 4) {
    if (!(hi > lo)) { hi = lo + 1; lo = lo - 1; }
    const span = hi - lo, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(st => span / st <= n + 1) || mag * 10;
    const start = Math.floor(lo / step) * step, out = [];
    for (let v = start; v <= hi + step * 0.5; v += step) out.push(Math.round(v * 1e6) / 1e6);
    return out;
  }
  function xTicks(t0, t1) {
    const days = (t1 - t0) / 864e5, out = [];
    const d0 = new Date(t0), d1 = new Date(t1);
    if (days > 800) { for (let y = d0.getFullYear() + 1; y <= d1.getFullYear(); y++) out.push([new Date(y, 0, 1).getTime(), String(y)]); }
    else if (days > 120) {
      const stepM = days > 400 ? 3 : 1; let d = new Date(d0.getFullYear(), d0.getMonth() + 1, 1);
      while (d <= d1) { if (d.getMonth() % stepM === 0) out.push([d.getTime(), d.getMonth() === 0 ? String(d.getFullYear()) : MONTHS[d.getMonth()]]); d = new Date(d.getFullYear(), d.getMonth() + 1, 1); }
    } else {
      const stepD = days > 45 ? 14 : days > 14 ? 7 : 1; let d = new Date(d0); d.setHours(12, 0, 0, 0);
      let i = 0; while (d <= d1) { if (i % stepD === 0) out.push([d.getTime(), `${MONTHS[d.getMonth()]} ${d.getDate()}`]); d = new Date(d.getTime() + 864e5); i++; }
    }
    return out;
  }

  /** Line chart. points: [{t: ms, y: number, ...extra}] sorted by t. opts: {unit, ref:{y,label}, fmtY, tip(p)} */
  function lineChart(points, opts = {}) {
    const wrap = h("div", { class: "chart" });
    if (points.length === 0) { wrap.append(h("div", { class: "muted small", style: "padding:1rem 0" }, "No readings in this range.")); return wrap; }
    let drawnW = 0;
    const draw = () => {
      const W = Math.max(280, Math.round(wrap.clientWidth || (main.clientWidth - 64)));
      if (Math.abs(W - drawnW) < 16) return;
      drawnW = W;
      wrap.replaceChildren(...lineChartSvg(points, opts, W));
    };
    draw();
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(draw).observe(wrap);
    return wrap;
  }
  function lineChartSvg(points, opts, W) {
    const H = opts.height || 220, P = { l: 40, r: 14, t: 14, b: 26 };
    const ys = points.map(p => p.y); let lo = Math.min(...ys), hi = Math.max(...ys);
    if (opts.ref) { lo = Math.min(lo, opts.ref.y); hi = Math.max(hi, opts.ref.y); }
    const pad = (hi - lo) * 0.12 || Math.abs(hi) * 0.05 || 1; lo -= pad; hi += pad;
    if (opts.zero) lo = 0;
    const ticks = niceTicks(lo, hi, 5).filter(v => v >= lo && v <= hi);
    let t0 = points[0].t, t1 = points[points.length - 1].t; if (t1 === t0) { t0 -= 864e5 * 3; t1 += 864e5 * 3; }
    const x = t => P.l + (t - t0) / (t1 - t0) * (W - P.l - P.r);
    const y = v => P.t + (hi - v) / (hi - lo) * (H - P.t - P.b);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
    const grid = s("g", { class: "grid" }), axis = s("g", { class: "axis" });
    for (const v of ticks) {
      if (v < lo || v > hi) continue;
      grid.append(s("line", { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
      svg.append(s("text", { x: P.l - 6, y: y(v) + 4, "text-anchor": "end" }, (opts.fmtY || fmt.n)(v)));
    }
    axis.append(s("line", { x1: P.l, x2: W - P.r, y1: H - P.b, y2: H - P.b }));
    for (const [t, lbl] of xTicks(t0, t1)) if (t >= t0 && t <= t1) svg.append(s("text", { x: x(t), y: H - 8, "text-anchor": "middle" }, lbl));
    svg.append(grid, axis);
    const pathOf = pts => pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.y).toFixed(1)}`).join("");
    let line = points;
    if (opts.smooth && points.length > opts.smooth) {
      const win = opts.smooth * 864e5;
      line = points.map((p, i) => { let sum = 0, n = 0; for (let j = i; j >= 0 && p.t - points[j].t < win; j--) { sum += points[j].y; n++; } return { t: p.t, y: sum / n }; });
      svg.append(s("path", { class: "line raw", d: pathOf(points) }));
    }
    if (points.length > 1) {
      const d = pathOf(line);
      svg.append(s("path", { class: "area", d: `${d}L${x(t1).toFixed(1)},${y(lo)}L${x(t0).toFixed(1)},${y(lo)}Z` }));
      svg.append(s("path", { class: "line", d }));
    }
    if (opts.ref && opts.ref.y != null) {
      svg.append(s("line", { class: "ref", x1: P.l, x2: W - P.r, y1: y(opts.ref.y), y2: y(opts.ref.y) }));
      svg.append(s("text", { class: "ref-lbl", x: W - P.r, y: y(opts.ref.y) - 5, "text-anchor": "end" }, opts.ref.label));
    }
    const showDots = points.length <= 80 && !(opts.smooth && points.length > opts.smooth);
    if (showDots) for (const p of points) svg.append(s("circle", { class: "dot", cx: x(p.t), cy: y(p.y), r: points.length > 40 ? 3 : 4 }));
    const last = points[points.length - 1];
    if (!showDots) svg.append(s("circle", { class: "dot", cx: x(last.t), cy: y(last.y), r: 4 }));
    svg.append(s("text", { class: "end-lbl", x: Math.min(x(last.t) + 6, W - 2), y: y(last.y) - 8, "text-anchor": x(last.t) > W - 60 ? "end" : "start" }, (opts.fmtY || fmt.load)(last.y)));
    // hover layer
    const cross = s("line", { class: "cross", y1: P.t, y2: H - P.b, visibility: "hidden" });
    const hdot = s("circle", { class: "hover-dot", r: 5, visibility: "hidden" });
    const hit = s("rect", { class: "hit", x: P.l, y: 0, width: W - P.l - P.r, height: H });
    svg.append(cross, hdot, hit);
    const tip = h("div", { class: "tooltip", hidden: true });
    const move = ev => {
      const box = svg.getBoundingClientRect();
      const cx = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - box.left) / box.width * W;
      const t = t0 + (cx - P.l) / (W - P.l - P.r) * (t1 - t0);
      let best = points[0], bd = Infinity;
      for (const p of points) { const dd = Math.abs(p.t - t); if (dd < bd) { bd = dd; best = p; } }
      cross.setAttribute("x1", x(best.t)); cross.setAttribute("x2", x(best.t)); cross.setAttribute("visibility", "visible");
      hdot.setAttribute("cx", x(best.t)); hdot.setAttribute("cy", y(best.y)); hdot.setAttribute("visibility", "visible");
      tip.innerHTML = opts.tip ? opts.tip(best) : `<b>${(opts.fmtY || fmt.load)(best.y)}${opts.unit ? " " + opts.unit : ""}</b> · ${fmt.date(new Date(best.t).toISOString())}`;
      tip.hidden = false;
      tip.style.left = `${x(best.t) / W * box.width}px`; tip.style.top = `${y(best.y) / H * box.height}px`;
    };
    const leave = () => { cross.setAttribute("visibility", "hidden"); hdot.setAttribute("visibility", "hidden"); tip.hidden = true; };
    hit.addEventListener("mousemove", move); hit.addEventListener("mouseleave", leave);
    hit.addEventListener("touchstart", move, { passive: true }); hit.addEventListener("touchmove", move, { passive: true }); hit.addEventListener("touchend", leave);
    return [svg, tip];
  }

  function sparkline(vals) {
    const v = vals.filter(x => x != null);
    const svg = s("svg", { class: "spark", viewBox: "0 0 88 30", "aria-hidden": "true" });
    if (v.length < 2) { if (v.length === 1) svg.append(s("circle", { cx: 84, cy: 15, r: 3 })); return svg; }
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const pts = v.map((y, i) => [4 + i / (v.length - 1) * 80, 26 - (y - lo) / span * 22]);
    svg.append(s("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("") }));
    const l = pts[pts.length - 1]; svg.append(s("circle", { cx: l[0], cy: l[1], r: 3 }));
    return svg;
  }

  const toT = iso => new Date(iso.slice(0, 10) + "T12:00:00").getTime();

  // ------------------------------------------------------------- components
  const kindBadge = kind => h("span", { class: `badge kind-${kind}` }, kind);
  function tile(label, value, unit, sub, cls) {
    return h("div", { class: "tile " + (cls || "") }, h("div", { class: "lbl" }, label),
      h("div", { class: "val" }, value, unit ? h("small", null, unit) : null), sub ? h("div", { class: "sub" }, sub) : null);
  }
  function section(title, right) { return h("div", { class: "section" }, h("h2", null, title), right || null); }
  function emptyState(title, body, action) { return h("div", { class: "card empty" }, h("h2", null, title), h("p", null, body), action || null); }
  function skeleton(n = 3) { const f = document.createDocumentFragment(); for (let i = 0; i < n; i++) f.append(h("div", { class: "skeleton", style: "margin-bottom:.8rem" })); return f; }

  function setChips(sets, topRef) {
    return h("div", { class: "chips" }, sets.map(st => h("span", {
      class: "chip" + (st.type === "warmup" ? " warm" : "") + (topRef && st.ref === topRef ? " top" : ""),
      title: st.type === "warmup" ? "warm-up" : st.type,
    }, fmt.set(st))));
  }

  function planChip(status) {
    const el = $("#plan-chip"); el.replaceChildren();
    if (!status) return;
    if (!status.plan) { el.append(h("span", { class: "muted" }, `${status.sessions} sessions · no plan started`)); return; }
    const p = status.plan;
    el.append(link(`/week/${p.current_week}`, {}, h("span", { class: "badge accent" }, `wk ${p.current_week}`)),
      h("span", null, `${p.program} · ${p.days}/wk`));
    if (p.deload_next) el.append(h("span", { class: "badge kind-deload" }, "deload next"));
  }

  // ------------------------------------------------------------------ views
  const views = {};

  // -- Week -----------------------------------------------------------------
  views.week = async ({ n }) => {
    let wk;
    try { wk = await get(n ? `/api/week/${n}` : "/api/week"); }
    catch (e) {
      if (e.status !== 404) throw e;
      const st = await get("/api/status");
      return noPlan(st);
    }
    const unit = wk.unit;
    const doneKey = `done:${wk.plan.started_on}:${wk.number}`;
    const done = new Set(ls.get(doneKey, []));
    const frag = document.createDocumentFragment();
    const cur = wk.plan.current_week;

    const strip = h("div", { class: "week-strip" });
    const shown = Math.max(wk.defined_weeks, cur, wk.number);
    for (let i = 1; i <= shown; i++) {
      const meta = wk.weeks[i - 1] || wk.weeks[(i - 2) % (wk.weeks.length - 1) + 1];
      strip.append(link(`/week/${i}`, { class: `${meta.kind}${i === cur ? " cur" : ""}${i === wk.number ? " sel" : ""}`, title: meta.label }, i));
    }
    frag.append(h("div", { class: "week-head" },
      h("div", { class: "row between" },
        h("div", { class: "week-title" }, h("h1", null, `Week ${wk.number}`), kindBadge(wk.kind),
          wk.is_current ? h("span", { class: "badge accent" }, "current") : null),
        h("div", { class: "week-nav" },
          wk.number > 1 ? link(`/week/${wk.number - 1}`, { class: "btn sm", "aria-label": "Previous week" }, "‹") : null,
          wk.number !== cur ? link(`/week/${cur}`, { class: "btn sm" }, "today") : null,
          link(`/week/${wk.number + 1}`, { class: "btn sm", "aria-label": "Next week" }, "›"))),
      h("div", { class: "ink2 small" }, wk.label ? wk.label + " · " : "", `${fmt.date(wk.window[0])} – ${fmt.date(wk.window[1])}`,
        wk.plan.deload_next && wk.is_current ? " · deload next" : ""),
      strip,
      wk.vitals.length ? vitalsStrip(wk.vitals) : null,
    ));
    if (wk.missing.length) frag.append(h("div", { class: "banner warn", style: "margin-bottom:.8rem" },
      h("b", null, `${wk.missing.length} lifts need equipment this gym does not have: `), wk.missing.join(", "), ". The loads for those are arithmetic, not a workout."));
    if (wk.kind === "calibration") frag.append(h("div", { class: "banner info", style: "margin-bottom:.8rem" },
      "Seeded week. Loads come from a decayed historical e1RM; the 5+ top set is what sets each training max. Push it, log it, then advance."));

    wk.days.forEach((day, di) => {
      const card = h("div", { class: "card day" });
      const prog = h("span", { class: "prog" });
      // A slot the Strong import confirmed is done for good; a hand tick covers the gap until the export lands.
      const isDone = (slot, si) => slot.logged || done.has(`${di}:${si}`);
      const updateProg = () => { const dn = day.slots.filter(isDone).length; prog.textContent = `${dn}/${day.slots.length}`; };
      card.append(h("div", { class: "day-h" }, h("div", { class: "row" }, h("h2", null, day.name),
        day.logged ? h("span", { class: "badge good", title: `from the Strong import: ${day.logged.title}` }, `logged ${fmt.date(day.logged.date)}`) : null), prog));
      day.slots.forEach((slot, si) => {
        const key = `${di}:${si}`;
        const el = h("div", { class: "slot" + (isDone(slot, si) ? " done" : "") });
        const check = h("button", { class: "check" + (isDone(slot, si) ? " on" : ""), "aria-label": slot.logged ? "Logged in Strong" : "Mark done", disabled: slot.logged ? true : null, onclick: () => {
          if (done.has(key)) done.delete(key); else done.add(key);
          ls.set(doneKey, [...done]); el.classList.toggle("done", done.has(key)); check.classList.toggle("on", done.has(key)); updateProg();
        } }, s("svg", { viewBox: "0 0 24 24" }, s("path", { d: "M5 13l4 4L19 7" })));
        const isMain = slot.main;
        const meta = [];
        if (slot.tm != null) meta.push(`TM ${fmt.load(slot.tm)}`);
        else if (slot.e1rm != null) meta.push(`e1RM ${fmt.load(slot.e1rm)}`);
        if (slot.reps_delta) meta.push(`+${slot.reps_delta} reps (ceiling)`);
        if (slot.sets_delta) meta.push(`${slot.sets_delta > 0 ? "+" : ""}${slot.sets_delta} set`);
        el.append(h("div", { class: "slot-name" }, link(`/lift/${slot.lift}`, {}, slot.name),
          slot.equipment ? h("span", { class: "badge" }, slot.equipment) : null,
          isMain ? h("span", { class: "badge lift-main" }, "main") : null,
          !slot.available ? h("span", { class: "badge warn" }, "not at this gym") : null),
          check,
          h("div", { class: "slot-meta" }, meta.join(" · ")));
        const pres = h("div", { class: "pres" });
        for (const p of slot.prescribed) {
          pres.append(h("span", { class: "scheme" }, h("b", null, p.sets), " × ", h("b", null, p.reps), p.amrap ? h("span", { class: "amrap", title: "last set as many reps as possible" }, "+") : null),
            p.load != null ? h("span", { class: "load" }, fmt.load(p.load), h("small", null, unit))
              : h("span", { class: "load text" }, p.rpe ? `@RPE ${p.rpe}` : p.how),
            h("span", { class: "rest" }, p.rest_s ? "rest " + fmt.rest(p.rest_s) : ""));
        }
        el.append(pres);
        const aux = h("div", { class: "aux" });
        if (slot.warmup.length) aux.append(h("span", { class: "k" }, "warm-up"), h("span", null, slot.warmup.map(w => `${fmt.load(w.load)}×${w.reps}`).join(" · ")));
        if (slot.last) aux.append(h("span", { class: "k" }, "last"), h("span", null, `${fmt.date(slot.last.date)} · `, slot.last.sets.map(fmt.set).join("  ")));
        for (const why of slot.why) { const [rule, ...rest] = why.split(": "); aux.append(h("span", { class: "k" }, "why"), h("span", { class: "why" }, h("b", null, rule), ": ", rest.join(": "))); }
        if (slot.note) aux.append(h("span", { class: "k" }, "note"), h("span", null, slot.note));
        if (aux.children.length) el.append(aux);
        card.append(el);
      });
      updateProg();
      frag.append(card);
    });
    frag.append(h("div", { class: "row", style: "margin-top:1rem;justify-content:center" },
      h("button", { class: "btn sm", onclick: () => copyWeek(wk) }, "Copy week as text"),
      link("/program", { class: "btn sm" }, "Program map"),
      link("/rules", { class: "btn sm" }, "Why these numbers")));
    return frag;
  };

  function vitalsStrip(vitals) {
    const pick = l => vitals.find(v => v.label === l);
    const bw = pick("bodyweight"), hr = pick("resting HR"), sl = pick("sleep h"), hrv = pick("HRV");
    const strip = h("div", { class: "vitals-strip" });
    if (bw) strip.append(h("span", { class: "chip", title: `latest ${bw.latest} on ${bw.on}` }, "bw ", h("b", null, fmt.n(bw.mean_7d ?? bw.latest, 1)), ` ${bw.unit}`, bw.mean_28d != null ? h("span", { class: "muted" }, ` · 28d ${fmt.n(bw.mean_28d, 1)}`) : h("span", { class: "muted" }, ` · ${fmt.ago(bw.on)}`)));
    if (hr) strip.append(h("span", { class: "chip" }, "rHR ", h("b", null, fmt.n(hr.mean_7d ?? hr.latest)), hr.mean_28d != null ? h("span", { class: "muted" }, ` · 28d ${fmt.n(hr.mean_28d)}`) : null));
    if (hrv) strip.append(h("span", { class: "chip" }, "HRV ", h("b", null, fmt.n(hrv.mean_7d ?? hrv.latest)), hrv.mean_28d != null ? h("span", { class: "muted" }, ` · 28d ${fmt.n(hrv.mean_28d)}`) : null));
    if (sl && sl.mean_7d != null) strip.append(h("span", { class: "chip" }, "sleep ", h("b", null, fmt.n(sl.mean_7d, 1)), " h"));
    strip.append(link("/vitals", { class: "chip linkish" }, "all vitals ›"));
    return strip;
  }

  function copyWeek(wk) {
    const lines = [`Week ${wk.number} — ${wk.kind}${wk.label ? " (" + wk.label + ")" : ""}`];
    for (const d of wk.days) {
      lines.push("", d.name);
      for (const sl of d.slots) {
        const parts = sl.prescribed.map(p => `${p.sets}x${p.reps}${p.amrap ? "+" : ""} ${p.load != null ? fmt.load(p.load) + " " + wk.unit : p.how}${p.rest_s ? " (rest " + fmt.rest(p.rest_s) + ")" : ""}`);
        lines.push(`  ${sl.name}: ${parts.join(", ")}`);
        if (sl.warmup.length) lines.push(`      warm-up: ${sl.warmup.map(w => `${fmt.load(w.load)}x${w.reps}`).join(", ")}`);
      }
    }
    navigator.clipboard?.writeText(lines.join("\n")).then(() => toast("Copied"), () => toast("Clipboard unavailable", true));
  }

  function noPlan(st) {
    const frag = document.createDocumentFragment();
    frag.append(emptyState("No plan started",
      `${st.sessions} sessions imported, ${fmt.date(st.first)} to ${fmt.date(st.last)}. Starting ${st.program} seeds every lift from its best historical e1RM, decayed ×0.8 past 180 days, and prescribes week 1 off that.`,
      link("/settings", { class: "btn primary" }, "Start a program")));
    frag.append(section("What start would seed"));
    frag.append(liftTable(st.lifts, st.unit));
    return frag;
  }

  function liftTable(lifts, unit) {
    return h("div", { class: "card tscroll", style: "padding:0" }, h("table", { class: "table" },
      h("thead", null, h("tr", null, h("th", null, "Lift"), h("th", { class: "r" }, `best e1RM (${unit})`), h("th", { class: "r" }, "when"), h("th", { class: "r" }, "21d"), h("th", { class: "r" }, "TM"))),
      h("tbody", null, lifts.map(l => h("tr", null,
        h("td", null, link(`/lift/${l.id}`, {}, l.name), l.main ? h("span", { class: "badge lift-main", style: "margin-left:.4rem" }, "main") : null),
        h("td", { class: "r num" }, fmt.load(l.best_e1rm)), h("td", { class: "r num muted" }, l.best_on ? fmt.date(l.best_on) : "—"),
        h("td", { class: "r num" }, fmt.load(l.rolling_e1rm)), h("td", { class: "r num" }, fmt.load(l.tm)))))));
  }

  // -- Lifts ----------------------------------------------------------------
  views.lifts = async () => {
    const data = await get("/api/lifts");
    const frag = document.createDocumentFragment();
    frag.append(h("h1", { class: "page-h1" }, "Lifts"));
    const inProg = data.lifts.filter(l => l.in_program), rest = data.lifts.filter(l => !l.in_program && l.sessions > 0);
    const sortOrder = (a, b) => (b.main - a.main) || ((b.best_e1rm || 0) - (a.best_e1rm || 0));
    frag.append(section("Program lifts", h("span", { class: "muted small" }, `e1RM in ${data.unit}`)));
    frag.append(h("div", { class: "lift-grid" }, inProg.sort(sortOrder).map(l => liftCard(l, data.unit))));
    if (rest.length) {
      frag.append(section("Everything else logged", h("span", { class: "muted small" }, `${rest.length} movements`)));
      frag.append(h("div", { class: "lift-grid" }, rest.sort((a, b) => b.sessions - a.sessions).map(l => liftCard(l, data.unit))));
    }
    return frag;
  };
  function liftCard(l, unit) {
    return h("div", { class: "card lift-card", onclick: () => navigate(`/lift/${l.id}`), role: "link", tabindex: 0,
      onkeydown: e => { if (e.key === "Enter") navigate(`/lift/${l.id}`); } },
      h("div", { class: "nm" }, l.name, l.main ? h("span", { class: "badge lift-main" }, "main") : null, l.available ? null : h("span", { class: "badge warn" }, "n/a")),
      h("div", null, h("div", { class: "big" }, fmt.load(l.best_e1rm), h("small", null, unit)), h("div", { class: "tiny muted" }, l.best_on ? `best · ${fmt.ago(l.best_on)}` : "no loaded sets")),
      sparkline(l.spark),
      h("div", { class: "foot" }, `${l.sessions} sessions`, l.equipment ? ` · ${l.equipment}` : "", ` · step ${fmt.load(l.step)}`, l.tm != null ? ` · TM ${fmt.load(l.tm)}` : ""));
  }

  // -- Lift detail ----------------------------------------------------------
  views.lift = async ({ id }) => {
    const l = await get(`/api/lift/${encodeURIComponent(id)}`);
    const unit = "lb";
    const frag = document.createDocumentFragment();
    frag.append(h("div", { class: "stack", style: "margin-bottom:1rem" },
      h("div", { class: "row" }, link("/lifts", { class: "btn sm" }, "‹ Lifts")),
      h("div", { class: "row" }, h("h1", null, l.name), l.main ? h("span", { class: "badge lift-main" }, "main") : l.in_program ? h("span", { class: "badge" }, "accessory") : null,
        l.available ? null : h("span", { class: "badge warn" }, "not at this gym")),
      h("div", { class: "ink2 small" }, [l.equipment, l.pattern, `step ${fmt.load(l.step)} ${unit}`, l.ceiling != null ? `ceiling ${fmt.load(l.ceiling)} ${unit}` : null].filter(Boolean).join(" · "),
        l.aliases.length ? h("span", { class: "muted" }, ` · Strong: ${l.aliases.join(", ")}`) : null)));
    frag.append(h("div", { class: "tiles" },
      tile("Best e1RM", fmt.load(l.best_e1rm), unit, l.best_on ? `${fmt.date(l.best_on)} · ${fmt.ago(l.best_on)}` : "no loaded sets"),
      tile("Training max", fmt.load(l.tm), l.tm != null ? unit : "", l.tm != null ? "0.9 × e1RM, progressed by rules" : "set by calibrate_tm after week 1"),
      tile("Seeded e1RM", fmt.load(l.e1rm), l.e1rm != null ? unit : "", l.e1rm != null ? "current state" : "seeded at start"),
      tile("Sessions", String(l.sessions), "", l.last_on ? `last ${fmt.date(l.last_on)}` : "")));

    if (l.series.length) {
      const modes = [["e1rm", "e1RM", p => p.e1rm], ["top_w", "Top load", p => p.top_w], ["volume", "Volume", p => p.volume]];
      let mode = "e1rm", range = "all";
      const chartHost = h("div");
      const draw = () => {
        const [, label, pick] = modes.find(m => m[0] === mode);
        const cut = range === "all" ? 0 : Date.now() - (range === "1y" ? 365 : 90) * 864e5;
        const pts = l.series.filter(p => pick(p) != null && toT(p.date) >= cut).map(p => ({ t: toT(p.date), y: pick(p), p }));
        chartHost.replaceChildren(...[
          h("div", { class: "chart-h" }, h("span", { class: "t" }, `${label} per session`), h("span", { class: "s" }, `${pts.length} sessions`)),
          lineChart(pts, {
            unit, ref: mode === "e1rm" && l.tm != null ? { y: l.tm, label: `TM ${fmt.load(l.tm)}` } : null,
            fmtY: mode === "volume" ? v => fmt.n(v) : fmt.load,
            tip: ({ p, y }) => mode === "e1rm" ? `<b>${fmt.load(y)} ${unit}</b> e1RM · ${fmt.load(p.best_w)}×${p.best_r}<br>${fmt.date(p.date)} · ${p.sets} sets`
              : mode === "top_w" ? `<b>${fmt.load(y)} ${unit}</b> × ${p.top_r}<br>${fmt.date(p.date)} · ${p.sets} sets`
              : `<b>${fmt.n(y)} ${unit}</b> volume<br>${fmt.date(p.date)} · ${p.sets} sets`,
          }),
          mode === "e1rm" && l.tm != null ? h("div", { class: "legend" }, h("span", null, h("i", { class: "sw", style: "background:var(--series-1)" }), "e1RM"), h("span", null, h("i", { class: "sw", style: "background:var(--series-2)" }), "training max")) : null,
        ].filter(Boolean));
      };
      const seg = (items, cur, set) => h("div", { class: "seg" }, items.map(([k, lbl]) => h("button", { class: k === cur() ? "on" : "", onclick: () => { set(k); draw(); redrawSeg(); } }, lbl)));
      const segHost = h("div", { class: "row between", style: "margin-bottom:.5rem" });
      const redrawSeg = () => segHost.replaceChildren(seg(modes.map(m => [m[0], m[1]]), () => mode, k => { mode = k; }), seg([["90d", "90d"], ["1y", "1y"], ["all", "All"]], () => range, k => { range = k; }));
      redrawSeg(); draw();
      frag.append(h("div", { class: "card", style: "margin-top:.8rem" }, segHost, chartHost));
    }
    if (l.adjustments.length) {
      frag.append(section("Rule log"));
      frag.append(h("div", { class: "card" }, l.adjustments.slice().reverse().map(a => adjRow(a, unit, false))));
    }
    if (l.recent.length) {
      frag.append(section("Sessions", h("span", { class: "muted small" }, `latest ${l.recent.length}`)));
      frag.append(h("div", { class: "card", style: "padding:.3rem 1rem" }, l.recent.map(r => h("div", { class: "entry" },
        h("span", { class: "en num" }, fmt.date(r.date)), setChips(r.sets)))));
    }
    return frag;
  };

  // -- Log ------------------------------------------------------------------
  views.log = async () => {
    const frag = document.createDocumentFragment();
    frag.append(h("h1", { class: "page-h1" }, "Log"));
    const list = h("div");
    const filter = h("input", { type: "text", placeholder: "Filter by workout or exercise…", "aria-label": "Filter sessions" });
    const count = h("span", { class: "muted small" });
    frag.append(h("div", { class: "row", style: "margin-bottom:.8rem" }, h("div", { class: "grow" }, filter), count), list);
    let sessions = [], more = false, oldest = null, loading = false;
    const moreBtn = h("button", { class: "btn", style: "margin:1rem auto;display:block", onclick: () => load() }, "Load older");
    const render = () => {
      const q = filter.value.trim().toLowerCase();
      const rows = q ? sessions.filter(sx => sx.title.toLowerCase().includes(q) || sx.entries.some(e => e.name.toLowerCase().includes(q))) : sessions;
      count.textContent = `${rows.length}${more ? "+" : ""} sessions`;
      list.replaceChildren();
      let month = "";
      for (const sx of rows) {
        const m = sx.date.slice(0, 7);
        if (m !== month) { month = m; list.append(h("div", { class: "month" }, `${MONTHS[+m.slice(5) - 1]} ${m.slice(0, 4)}`)); }
        list.append(sessionCard(sx, q));
      }
      if (more) list.append(moreBtn);
    };
    const load = async () => {
      if (loading) return; loading = true; moreBtn.disabled = true;
      try {
        const d = await get(`/api/sessions?limit=60${oldest ? "&before=" + oldest : ""}`);
        sessions = sessions.concat(d.sessions); more = d.more;
        if (d.sessions.length) oldest = d.sessions[d.sessions.length - 1].date;
        render();
      } finally { loading = false; moreBtn.disabled = false; }
    };
    filter.addEventListener("input", render);
    list.append(skeleton(4));
    load().catch(e => toast(e.message, true));
    return frag;
  };
  function sessionCard(sx, q) {
    const d = new Date(sx.date + "T12:00:00");
    const det = h("details", { class: "card sess fold", open: q && sx.entries.some(e => e.name.toLowerCase().includes(q)) ? true : null });
    det.append(h("summary", null,
      h("div", { class: "d" }, h("b", null, d.getDate()), h("span", null, ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()])),
      h("div", null, h("div", { class: "t" }, sx.title || "Workout"), h("div", { class: "m" }, [sx.time, fmt.dur(sx.duration_s), `${sx.exercises} exercises`, `${sx.sets} sets`].filter(Boolean).join(" · "))),
      h("div", { class: "v" }, h("b", null, fmt.n(sx.volume)), "volume")));
    const body = h("div", { class: "body" });
    for (const e of sx.entries) body.append(h("div", { class: "entry" }, h("span", { class: "en" }, link(`/lift/${e.lift}`, {}, e.name), e.notes ? h("div", { class: "tiny muted" }, e.notes) : null), setChips(e.sets)));
    if (sx.notes) body.append(h("p", { class: "small ink2" }, sx.notes));
    det.append(body);
    return det;
  }

  // -- Rules ----------------------------------------------------------------
  views.rules = async () => {
    const [adj, prog] = await Promise.all([get("/api/adjustments"), get("/api/program")]);
    const frag = document.createDocumentFragment();
    frag.append(h("h1", { class: "page-h1" }, "Rules"));
    const rules = [...new Set(adj.adjustments.map(a => a.rule))];
    let sel = null;
    const host = h("div");
    const draw = () => {
      host.replaceChildren();
      const rows = sel ? adj.adjustments.filter(a => a.rule === sel) : adj.adjustments;
      if (!rows.length) { host.append(emptyState("Nothing has fired yet", "Rules run when a week closes. Advance the plan after the week's export lands and every adjustment shows up here with the sets it read.")); return; }
      const byWeek = new Map();
      for (const a of rows) { const k = a.week ?? "?"; if (!byWeek.has(k)) byWeek.set(k, []); byWeek.get(k).push(a); }
      for (const [w, list] of [...byWeek.entries()].sort((a, b) => (b[0] === "?" ? -1 : b[0]) - (a[0] === "?" ? -1 : a[0]))) {
        host.append(section(w === 0 ? "Before week 1 (seeding)" : `Week ${w}`, w > 0 ? link(`/week/${w}`, { class: "small linkish" }, "view week ›") : null));
        host.append(h("div", { class: "card" }, list.map(a => adjRow(a, adj.unit, true))));
      }
    };
    if (rules.length) frag.append(h("div", { class: "chips", style: "margin-bottom:.6rem" },
      h("button", { class: "btn sm" + (sel ? "" : " primary"), onclick: () => { sel = null; draw(); redraw(); } }, "all"),
      rules.map(r => h("button", { class: "btn sm" + (sel === r ? " primary" : ""), onclick: () => { sel = r; draw(); redraw(); } }, r))));
    const redraw = () => { const chips = frag.firstChild; if (chips && chips.classList.contains("chips")) [...chips.children].forEach((b, i) => b.classList.toggle("primary", i === 0 ? !sel : rules[i - 1] === sel)); };
    draw();
    frag.append(host);
    frag.append(section("The rule set", h("span", { class: "muted small" }, "in firing order")));
    frag.append(h("div", { class: "card" }, prog.rules.map(r => h("details", { class: "rule-doc fold" },
      h("summary", null, h("span", { class: "n" }, r.name), h("span", { class: "sm" }, r.summary)),
      h("div", { class: "prose", style: "margin-top:.5rem" }, r.doc)))));
    return frag;
  };
  function adjRow(a, unit, showLift) {
    const show = v => a.kg ? fmt.load(v) : String(v);
    const chg = a.new == null ? (a.old == null ? "" : `${show(a.old)} → —`) : `${a.old == null ? "" : show(a.old) + " → "}${show(a.new)}${a.kg ? " " + unit : ""}`;
    return h("div", { class: "adj" },
      h("span", { class: "rule" }, a.rule),
      h("span", null, showLift && a.lift !== "*" ? link(`/lift/${a.lift}`, { class: "lift" }, a.lift.replace(/_/g, " ")) : showLift ? h("span", { class: "lift" }, "plan") : null,
        showLift ? " · " : "", h("span", { class: "chg" }, a.field.replace(/_kg$/, ""), chg ? [" ", h("b", null, chg)] : null)),
      h("span", { class: "why" }, a.reason),
      a.evidence.length ? h("span", { class: "ev", title: a.evidence.join("\n") }, `${a.evidence.length} set${a.evidence.length > 1 ? "s" : ""} of evidence`) : null);
  }

  // -- Vitals ---------------------------------------------------------------
  views.vitals = async () => {
    let range = ls.get("vitals.range", "365");
    const frag = document.createDocumentFragment();
    const host = h("div");
    const segHost = h("div", { class: "row between", style: "margin-bottom:.8rem" });
    const redrawSeg = () => segHost.replaceChildren(h("h1", null, "Vitals"), h("div", { class: "seg" }, [["90", "90d"], ["365", "1y"], ["all", "All"]].map(([k, l]) => h("button", { class: k === range ? "on" : "", onclick: () => { range = k; ls.set("vitals.range", k); redrawSeg(); draw(); } }, l))));
    const draw = async () => {
      host.replaceChildren(skeleton(3));
      const v = await get(`/api/vitals?days=${range}`);
      host.replaceChildren();
      if (!v.tiles.length) { host.append(emptyState("No Health data yet", "Import the Health app's export zip, or point Health Auto Export at /import/health.")); return; }
      const UP_IS_GOOD = { "resting HR": false, HRV: true, "sleep h": true, steps: true, "VO2 max": true };
      host.append(h("div", { class: "tiles" }, v.tiles.map(t => {
        const trend = t.mean_7d != null && t.mean_28d != null ? t.mean_7d - t.mean_28d : null;
        const good = UP_IS_GOOD[t.label];
        const cls = good == null ? "" : (trend > 0) === good ? " up" : " down";
        const sub = t.mean_7d != null ? h("span", null, `7d ${fmt.n(t.mean_7d, t.decimals)} · 28d ${fmt.n(t.mean_28d, t.decimals)}`) : h("span", { class: "muted" }, `${fmt.date(t.on)} · ${fmt.ago(t.on)}`);
        return tile(t.label === "sleep h" ? "sleep" : t.label, fmt.n(t.latest, t.decimals), t.unit, [sub, trend != null && Math.abs(trend) >= 0.5 * 10 ** -t.decimals ? h("span", { class: "delta" + cls, style: "margin-left:.4rem", title: "7-day mean against 28-day mean" }, `${trend > 0 ? "▲" : "▼"} ${fmt.n(Math.abs(trend), t.decimals)}`) : null]);
      })));
      const order = ["bodyweight", "resting HR", "HRV", "sleep h", "steps", "body fat %"];
      for (const label of order) {
        const sdata = v.series[label]; if (!sdata) continue;
        const pts = sdata.points.map(([d, y]) => ({ t: toT(d), y }));
        const nd = label === "bodyweight" || label === "sleep h" || label === "body fat %" ? 1 : 0;
        const dense = pts.length > 60;
        host.append(h("div", { class: "card", style: "margin-top:.8rem" },
          h("div", { class: "chart-h" }, h("span", { class: "t" }, label === "sleep h" ? "sleep" : label), h("span", { class: "s" }, `${pts.length} days · ${sdata.unit}`)),
          lineChart(pts, { unit: sdata.unit, height: 170, fmtY: x => fmt.n(x, nd), zero: label === "steps", smooth: dense ? 7 : 0, tip: p => `<b>${fmt.n(p.y, nd)} ${sdata.unit}</b> · ${fmt.date(new Date(p.t).toISOString())}` }),
          dense ? h("div", { class: "legend" }, h("span", null, h("i", { class: "sw", style: "background:var(--muted-foreground);opacity:.55" }), "daily"), h("span", null, h("i", { class: "sw", style: "background:var(--series-1)" }), "7-day mean")) : null));
      }
      if (v.workouts.length) {
        host.append(section("Workouts the Watch recorded", h("span", { class: "muted small" }, "latest 40")));
        host.append(h("div", { class: "card tscroll", style: "padding:0" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, h("th", null, "When"), h("th", { class: "r" }, "avg HR"), h("th", { class: "r" }, "max HR"), h("th", { class: "r" }, "kcal"), h("th", { class: "r" }, "min"))),
          h("tbody", null, v.workouts.map(w => h("tr", null, h("td", { class: "num" }, fmt.date(w.at), h("span", { class: "muted" }, ` ${w.at.slice(11, 16)}`)),
            h("td", { class: "r num" }, fmt.n(w.hr_avg)), h("td", { class: "r num" }, fmt.n(w.hr_max)), h("td", { class: "r num" }, fmt.n(w.kcal)), h("td", { class: "r num" }, fmt.n(w.minutes))))))));
      }
    };
    redrawSeg(); frag.append(segHost, host);
    draw().catch(e => toast(e.message, true));
    return frag;
  };

  // -- Program --------------------------------------------------------------
  views.program = async ({ days }) => {
    const st = await get("/api/status");
    const p = await get(`/api/program${days ? "?days=" + days : ""}`);
    const cur = st.plan ? st.plan.current_week : null;
    const frag = document.createDocumentFragment();
    frag.append(h("div", { class: "row between", style: "margin-bottom:.6rem" },
      h("div", null, h("h1", null, p.name), h("div", { class: "ink2 small" }, `${p.weeks.length} weeks · ${p.days} days/week`, st.plan ? ` · running since ${fmt.date(st.plan.started_on)}` : " · not started")),
      h("div", { class: "seg" }, [3, 4].map(d => h("button", { class: d === p.days ? "on" : "", onclick: () => navigate(`/program?days=${d}`) }, `${d} days`)))));
    frag.append(h("div", { class: "chips", style: "margin-bottom:.8rem" }, p.lifts.map(l => link(`/lift/${l.id}`, { class: "chip" + (l.main ? " top" : "") }, l.name))));
    if (p.missing.length) frag.append(h("div", { class: "banner warn", style: "margin-bottom:.8rem" }, `Not at this gym: ${p.missing.join(", ")}`));
    const map = h("div", { class: "pmap" });
    for (const w of p.weeks) {
      const det = h("details", { class: "fold", open: cur === w.number ? true : null });
      det.append(h("summary", { class: "pweek" },
        h("span", { class: "n" + (cur === w.number ? " cur" : "") }, w.number, h("i", { class: w.kind })),
        h("span", { class: "lab" }, kindBadge(w.kind), " ", w.label, st.plan ? [" · ", link(`/week/${w.number}`, { class: "linkish small" }, "loads ›")] : null)));
      det.append(h("div", { class: "pdays", style: "margin-left:3.2rem" }, w.days.map(d => h("div", { class: "pday" }, h("div", { class: "dn" }, d.name),
        d.slots.map(sl => h("div", { class: "ps" + (sl.main ? " main" : "") }, h("span", { class: "sn" }, sl.name, sl.equipment ? h("span", { class: "equip" }, ` · ${sl.equipment}`) : null),
          h("span", { class: "sc" }, sl.scheme.map(sc => `${sc.sets}×${sc.reps}${sc.amrap ? "+" : ""} ${sc.how}`).join(" · "))))))));
      map.append(det);
    }
    frag.append(map);
    frag.append(section("Design note"));
    frag.append(h("div", { class: "card" }, h("div", { class: "prose", html: mdLite(p.doc) })));
    frag.append(section("Rules", link("/rules", { class: "small linkish" }, "what has fired ›")));
    frag.append(h("div", { class: "card" }, p.rules.map(r => h("div", { class: "rule-doc" }, h("span", { class: "n" }, r.name), " ", h("span", { class: "sm" }, r.summary)))));
    return frag;
  };
  function mdLite(text) {
    const esc = text.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    return esc.trim().replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n(?!\n)/g, " ");
  }

  // -- Settings -------------------------------------------------------------
  views.settings = async () => {
    const st = await get("/api/status", true);
    const frag = document.createDocumentFragment();
    frag.append(h("h1", { class: "page-h1" }, "Settings"));

    // token
    const tok = h("input", { type: "password", value: ls.get("token", ""), placeholder: "ONEMORE_TOKEN", autocomplete: "off" });
    frag.append(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h2", null, "Write access"),
      h("span", { class: "badge " + (st.writable ? "kind-deload" : "warn") }, st.writable ? "server accepts writes" : "ONEMORE_TOKEN unset on server")),
      h("p", { class: "small ink2" }, "Reads need nothing. Imports, starting and advancing the plan send this token as X-Token; it stays in this browser."),
      h("div", { class: "row" }, h("div", { class: "grow" }, tok), h("button", { class: "btn", onclick: () => { ls.set("token", tok.value.trim()); toast("Token saved"); } }, "Save"))));

    // plan
    const plan = st.plan;
    // No plan yet? take the server's default from st.program, never a literal here: the
    // API and the CLI were single-sourced onto DEFAULT_PROGRAM and this select was missed,
    // so the one control that actually starts a plan still pre-selected the superseded
    // `rebuild` — a wrong program is one unread tap away, and it looks deliberate.
    const progSel = h("select", null, st.programs.map(p => h("option", { value: p, selected: p === (plan ? plan.program : st.program) ? true : null }, p)));
    const daysSel = h("select", null, [3, 4].map(d => h("option", { value: d, selected: d === (plan ? plan.days : 4) ? true : null }, `${d} days / week`)));
    const onInp = h("input", { type: "date", value: st.today });
    const force = h("input", { type: "checkbox" });
    const startRes = h("div", { class: "result" });
    const startBtn = h("button", { class: "btn primary", onclick: async () => {
      if (plan && !force.checked) return toast("A plan is running: tick restart to replace it", true);
      startBtn.disabled = true;
      try {
        const r = await post("/api/start", { program: progSel.value, days: +daysSel.value, on: onInp.value, force: force.checked });
        startRes.replaceChildren(h("div", null, h("b", null, `Started ${r.plan.program}`), ` · week 1 begins ${fmt.date(r.plan.started_on)} · ${r.seeded.length} lifts seeded`),
          h("pre", null, r.seeded.map(a => `${a.lift}: ${a.reason}`).join("\n")));
        toast("Plan started"); planChip(await get("/api/status", true));
      } catch (e) { toast(e.message, true); } finally { startBtn.disabled = false; }
    } }, plan ? "Restart at week 1" : "Start");
    frag.append(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h2", null, "Plan"),
      plan ? h("span", { class: "small ink2" }, `${plan.program} · week ${plan.current_week} · ${fmt.date(plan.window[0])} – ${fmt.date(plan.window[1])}`) : h("span", { class: "badge warn" }, "none")),
      h("div", { class: "grid2" }, h("label", { class: "field" }, "Program", progSel), h("label", { class: "field" }, "Days", daysSel), h("label", { class: "field" }, "Week 1 starts", onInp),
        plan ? h("label", { class: "field row", style: "align-self:end" }, force, " restart, discarding the current position") : null),
      h("div", { class: "row", style: "margin-top:.7rem" }, startBtn), startRes));

    // advance
    if (plan) {
      const aforce = h("input", { type: "checkbox" }); const asof = h("input", { type: "date" });
      const advRes = h("div", { class: "result" });
      const advBtn = h("button", { class: "btn primary", onclick: async () => {
        advBtn.disabled = true;
        try {
          const r = await post("/api/advance", { force: aforce.checked, asof: asof.value || null });
          advRes.replaceChildren(h("div", null, h("b", null, r.fired.length ? `${r.fired.length} rules fired` : "No rule fired"), ` · now week ${r.plan.current_week}${r.plan.deload_next ? " (deload next)" : ""}`),
            h("div", { class: "card", style: "margin-top:.4rem" }, r.fired.length ? r.fired.map(a => adjRow(a, st.unit, true)) : h("span", { class: "muted small" }, "nothing to show")));
          toast(`Now week ${r.plan.current_week}`); planChip(await get("/api/status", true));
        } catch (e) { toast(e.message, true); } finally { advBtn.disabled = false; }
      } }, "Advance");
      frag.append(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h2", null, "Close the week"), h("span", { class: "small ink2" }, `week ${plan.current_week} ends ${fmt.date(plan.window[1])}`)),
        h("p", { class: "small ink2" }, "Runs every rule over the week's logged sets, records what fired, and moves the plan on. Refuses until the window has ended unless forced."),
        h("div", { class: "grid2" }, h("label", { class: "field row" }, aforce, " force (close early)"), h("label", { class: "field" }, "Pretend today is", asof)),
        h("div", { class: "row", style: "margin-top:.7rem" }, advBtn), advRes));
    }

    // imports
    const impRes = h("div", { class: "result" });
    const upload = async (file, kind) => {
      impRes.replaceChildren(h("span", { class: "muted" }, `Uploading ${file.name}…`));
      try {
        // The file itself, not file.text() — the Health app's export is a zip, and
        // decoding it as text corrupts it before it is ever sent.
        const r = await post(kind === "health" ? "/import/health" : "/import/strong", file, true);
        if (r.queued) {  // a Health export: parsed on the server, minutes after this answers
          impRes.replaceChildren(h("div", null, h("b", null, "Parsing " + r.queued), " · it lands in the imports list below when it finishes"));
          toast("Queued"); return;
        }
        impRes.replaceChildren(h("div", null, h("b", null, kind === "health" ? `${r.readings} readings, ${r.new} new` : `${r.sessions} sessions, ${r.new} new`), ` · saved as ${r.saved}`, r.remapped ? ` · ${r.remapped} names re-resolved` : ""));
        toast("Imported"); planChip(await get("/api/status", true));
      } catch (e) { impRes.replaceChildren(h("span", { style: "color:var(--bad-ink)" }, e.message)); }
    };
    const pick = kind => { const i = h("input", { type: "file", accept: kind === "health" ? ".zip,.json,.xml" : ".csv,text/csv", hidden: true, onchange: () => i.files[0] && upload(i.files[0], kind) }); document.body.append(i); i.click(); setTimeout(() => i.remove(), 60000); };
    const healthy = name => /\.(zip|json|xml)$/i.test(name);
    const drop = h("div", { class: "drop", onclick: () => pick("strong"),
      ondragover: e => { e.preventDefault(); drop.classList.add("over"); }, ondragleave: () => drop.classList.remove("over"),
      ondrop: e => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) upload(f, healthy(f.name) ? "health" : "strong"); } },
      h("b", null, "Drop a Strong CSV or an Apple Health export"), h("div", { class: "tiny" }, "or tap to choose a CSV"));
    frag.append(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h2", null, "Import"),
      h("span", { class: "small ink2" }, `${st.sessions} sessions · ${fmt.n(st.sets)} sets · ${st.first ? fmt.date(st.first) + " – " + fmt.date(st.last) : ""}`)),
      drop, h("div", { class: "row", style: "margin-top:.6rem" }, h("button", { class: "btn sm", onclick: () => pick("strong") }, "Strong CSV…"), h("button", { class: "btn sm", onclick: () => pick("health") }, "Health export…"),
        h("span", { class: "tiny muted" }, "The Health app's zip parses on the server: this answers at once and the readings land a few minutes later.")),
      impRes,
      st.imports.length ? h("details", { class: "fold", style: "margin-top:.6rem" }, h("summary", { class: "small linkish" }, `${st.imports.length} imports so far`),
        h("div", { class: "tscroll" }, h("table", { class: "table" }, h("tbody", null, st.imports.slice().reverse().map(i => h("tr", null, h("td", { class: "num tiny" }, i.at.replace("T", " ")), h("td", { class: "tiny" }, i.source), h("td", { class: "tiny" }, i.file.split("/").pop()), h("td", { class: "r num tiny" }, `${i.new} / ${i.seen}`))))))) : null));
    if (st.unmapped.length) frag.append(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h2", null, "Not in the catalog"), h("span", { class: "badge warn" }, st.unmapped.length)),
      h("p", { class: "small ink2" }, "Strong names that resolved to a slug. Add an alias in exercises.toml; the next import re-resolves them."),
      h("table", { class: "table" }, h("tbody", null, st.unmapped.map(u => h("tr", null, h("td", null, u.name), h("td", { class: "mono tiny muted" }, u.id), h("td", { class: "r num" }, u.entries)))))));
    return frag;
  };

  // ----------------------------------------------------------------- router
  function parse(pathname, search) {
    const q = new URLSearchParams(search);
    const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean);
    const [root, arg] = parts;
    if (!root || root === "week") return { view: "week", n: arg ? +arg : null, key: "week" };
    if (root === "lifts") return { view: "lifts", key: "lifts" };
    if (root === "lift" && arg) return { view: "lift", id: decodeURIComponent(arg), key: "lifts" };
    if (root === "log") return { view: "log", key: "log" };
    if (root === "rules" || root === "explain") return { view: "rules", key: "rules" };
    if (root === "vitals") return { view: "vitals", key: "vitals" };
    if (root === "program") return { view: "program", days: q.get("days"), key: "program" };
    if (root === "settings") return { view: "settings", key: "settings" };
    return { view: "week", n: null, key: "week" };
  }
  let renderId = 0;
  async function render() {
    const r = parse(location.pathname, location.search);
    const id = ++renderId;
    document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.dataset.route === r.key));
    main.replaceChildren(skeleton(3));
    try {
      const out = await views[r.view](r);
      if (id !== renderId) return;
      main.replaceChildren(out);
      window.scrollTo(0, 0);
      const sel = main.querySelector(".week-strip .sel");
      if (sel) sel.scrollIntoView({ inline: "center", block: "nearest" });
    } catch (e) {
      if (id !== renderId) return;
      main.replaceChildren(emptyState("Could not load", e.message, h("button", { class: "btn", onclick: () => { cache.clear(); render(); } }, "Retry")));
    }
  }
  function navigate(href) { history.pushState(null, "", href); render(); }
  document.addEventListener("click", e => {
    const a = e.target.closest("a[data-link]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault(); navigate(a.getAttribute("href"));
  });
  window.addEventListener("popstate", render);
  document.addEventListener("keydown", e => {
    if (e.target.matches("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    const r = parse(location.pathname, location.search);
    if (r.view === "week" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      const cur = $(".week-strip a.sel"); const n = cur ? +cur.textContent : 1;
      if (e.key === "ArrowLeft" && n > 1) navigate(`/week/${n - 1}`); if (e.key === "ArrowRight") navigate(`/week/${n + 1}`);
    }
  });

  get("/api/status").then(planChip).catch(() => {});
  render();
})();
