"use strict";

const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};
const KEY = new URLSearchParams(location.search).get("k") || store.get("k");
if (KEY) store.set("k", KEY);

const ORDER = { waiting: 0, working: 1, done: 2, idle: 3 };
const LABEL = { waiting: "Needs you", working: "Working", done: "Done", idle: "Idle" };
const AGENT_COLORS = { "claude code": "#e08a62", cursor: "#d4d8df", opencode: "#4fd1e0", codex: "#74d39a", gemini: "#7aa7ff" };
const agentColor = (name) => AGENT_COLORS[String(name).toLowerCase()] || "#a78bfa";

const ICON = {
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>',
  coin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.4 0-2.5-.5-3-1.5M12 6v2M12 16v2"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  tool: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/></svg>',
  branch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9c0 5-6 4-11 8"/></svg>',
  chip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5v.01"/></svg>',
  soundOn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  soundOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="m17 9 5 6M22 9l-5 6"/></svg>',
};

// ---------- formatting ----------
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
const num = (n) => (n >= 1e9 ? (n / 1e9).toFixed(1) + "B" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(Math.round(n || 0)));
const bytes = (b) => {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return (b >= 100 || i === 0 ? Math.round(b) : b.toFixed(1)) + " " + u[i];
};
const usd = (c, est) => (c == null ? "—" : (est ? "≈" : "") + "$" + (c >= 100 ? Math.round(c) : c >= 10 ? c.toFixed(1) : c.toFixed(2)));
const ago = (s) => {
  s = Math.max(0, s | 0);
  if (s < 60) return s + "s";
  if (s < 3600) return ((s / 60) | 0) + "m";
  if (s < 86400) return ((s / 3600) | 0) + "h " + (((s % 3600) / 60) | 0) + "m";
  return ((s / 86400) | 0) + "d " + (((s % 86400) / 3600) | 0) + "h";
};
const shortModel = (m) => String(m || "").replace(/^claude-/, "").replace(/\[.*\]$/, "");
const tempClass = (t) => (t >= 85 ? "temp hot" : t >= 70 ? "temp warm" : "temp");
const temp = (t) => (t == null ? "" : `<span class="${tempClass(t)}">${Math.round(t)}°C</span>`);

// ---------- tiny charts ----------
function gauge(pct, color) {
  const r = 31, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  return `<div class="gauge" style="--g:${color}"><svg viewBox="0 0 74 74">
    <circle cx="37" cy="37" r="${r}" fill="none" stroke-width="7" class="track"/>
    <circle cx="37" cy="37" r="${r}" fill="none" stroke-width="7" stroke-linecap="round" class="val"
      stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - p / 100)).toFixed(1)}"/></svg>
    <span>${Math.round(p)}<small>%</small></span></div>`;
}

function spark(series, max) {
  // series: [[values, color], ...] drawn on a shared scale
  const w = 200, h = 34, all = series.flatMap(([v]) => v);
  if (all.length < 2) return '<svg class="spark"></svg>';
  max = max || Math.max(...all, 1);
  const paths = series.map(([vals, color]) => {
    if (vals.length < 2) return "";
    const pts = vals.map((v, i) => [(i / (vals.length - 1)) * w, h - 1 - (Math.min(v, max) / max) * (h - 3)]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
    return `<g style="--g:${color}"><path class="area" d="${line}L${w} ${h}L0 ${h}Z"/><path class="line" d="${line}"/></g>`;
  });
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${paths.join("")}</svg>`;
}

const bar = (pct, color) => `<div class="bar" style="--b:${color}"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></div>`;
const setHTML = (el, html) => { if (el._h !== html) { el.innerHTML = html; el._h = html; } };

// ---------- sound ----------
let audio = null;
let soundOn = store.get("sound") === "1";
function chime(kind) {
  if (!soundOn || !audio) return;
  const notes = kind === "waiting" ? [880, 660, 880] : [523, 784];
  notes.forEach((f, i) => {
    const t = audio.currentTime + i * 0.16, o = audio.createOscillator(), g = audio.createGain();
    o.type = "sine"; o.frequency.value = f;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.22, t + 0.02); g.gain.exponentialRampToValueAtTime(0.001, t + 0.5);
    o.connect(g).connect(audio.destination); o.start(t); o.stop(t + 0.55);
  });
}
function paintSound() { const b = $("sound"); b.innerHTML = soundOn ? ICON.soundOn : ICON.soundOff; b.classList.toggle("on", soundOn); }
$("sound").addEventListener("click", () => {
  audio = audio || new (window.AudioContext || window.webkitAudioContext)();  // iOS needs a tap to unlock audio
  audio.resume();
  soundOn = !soundOn;
  store.set("sound", soundOn ? "1" : "0");
  paintSound();
  if (soundOn) chime("done");
});
paintSound();
if (soundOn) document.addEventListener("click", () => { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); }, { once: true });

// ---------- screen: keep awake + full screen ----------
// Wake Lock only exists in secure contexts (HTTPS or localhost); over plain LAN http the button stays hidden.
let wakeLock = null, wantWake = store.get("wake") === "1";
async function applyWake() {
  try {
    if (wantWake && !wakeLock) { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.addEventListener("release", () => { wakeLock = null; }); }
    if (!wantWake && wakeLock) { await wakeLock.release(); wakeLock = null; }
  } catch (e) { wakeLock = null; }
  $("wake").classList.toggle("on", wantWake);
}
if ("wakeLock" in navigator) {
  $("wake").hidden = false;
  $("wake").innerHTML = ICON.sun;
  $("wake").addEventListener("click", () => { wantWake = !wantWake; store.set("wake", wantWake ? "1" : "0"); applyWake(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") applyWake(); });  // locks drop when hidden
  applyWake();
}
const root = document.documentElement;
const canFull = (document.fullscreenEnabled || document.webkitFullscreenEnabled) && !matchMedia("(display-mode: standalone)").matches;
if (canFull) {
  $("full").hidden = false;
  $("full").innerHTML = ICON.expand;
  $("full").addEventListener("click", () => {
    const fs = document.fullscreenElement || document.webkitFullscreenElement;
    if (fs) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    else (root.requestFullscreen || root.webkitRequestFullscreen).call(root);
  });
}

// ---------- clock ----------
function clock() {
  const d = new Date();
  $("time").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("date").textContent = d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
}
clock();
setInterval(clock, 1000);

// ---------- agents ----------
const cardEls = new Map();
const sent = new Set(), askErr = new Map();  // Allow/Deny taps, keyed by the prompt's one-time ask token
const prevState = new Map();
let lastOrder = "", firstRender = true;

function cardHTML(a, now) {
  const stats = [`<span>${ICON.clock}<b>${ago(now - a.since)}</b></span>`];
  if (a.tps) stats.push(`<span>${ICON.bolt}<b>${Math.round(a.tps)}</b> tok/s</span>`);
  if (a.cost != null) stats.push(`<span>${ICON.coin}<b>${usd(a.cost, a.estimated)}</b></span>`);
  if (a.prompts) stats.push(`<span>${ICON.chat}<b>${a.prompts}</b></span>`);
  if (a.tools) stats.push(`<span>${ICON.tool}<b>${a.tools}</b></span>`);

  let ctx = "";
  if (a.ctx != null) {
    const p = a.ctx * 100;
    ctx = `<div class="ctx">${bar(p, p > 80 ? "var(--red)" : p > 60 ? "var(--amber)" : "var(--blue)")}<span>${Math.round(p)}% context · ${num(a.ctx_tokens)}</span></div>`;
  } else if (a.ctx_tokens) {
    ctx = `<div class="ctx"><span>${num(a.ctx_tokens)} tokens in context</span></div>`;
  }

  const g = a.git, lines = a.lines && (a.lines[0] || a.lines[1]) ? a.lines : g && [g.add, g.rem];
  const left = g && g.branch
    ? `<span class="branch">${ICON.branch}${esc(g.branch)}${lines && (lines[0] || lines[1]) ? ` <span class="add">+${num(lines[0])}</span> <span class="rem">−${num(lines[1])}</span>` : ""}${g.files ? ` · ${g.files} files` : ""}</span>`
    : "<span></span>";
  const right = a.cpu != null ? `<span>${ICON.chip}${Math.round(a.cpu)}% · ${bytes(a.rss)}</span>` : "";
  const foot = g && g.branch || right ? `<div class="c-foot">${left}${right}</div>` : "";

  return `<div class="c-top"><span class="c-name">${esc(a.name)}</span><span class="chip">${LABEL[a.state]}</span></div>
    <div class="c-sub"><span class="tag" style="--a:${agentColor(a.kind)}">${esc(a.kind)}</span>${a.model ? `<span class="model">${esc(shortModel(a.model))}</span>` : ""}</div>
    <div class="c-detail">${esc(a.detail) || "&nbsp;"}</div>${ctx}
    <div class="c-stats">${stats.join("")}</div>${foot}`;
}

// Kept out of cardHTML: the card body re-renders every tick, and replacing a button mid-tap loses the tap.
function actHTML(a) {
  if (!a.ask) return "";
  const err = askErr.get(a.ask);
  return `<div class="c-ask">${esc(a.ask_text)}</div><div class="c-act">${sent.has(a.ask)
    ? '<span class="muted">Sending…</span>'
    : `<button data-d="allow" data-ask="${esc(a.ask)}">Allow</button><button data-d="deny" data-ask="${esc(a.ask)}">Deny</button>`}
    <span class="left">${err ? esc(err) : "No tap in time: it asks in the terminal"}</span></div>`;
}

function renderAgents(d) {
  const list = d.agents.slice().sort((x, y) => ORDER[x.state] - ORDER[y.state] || y.since - x.since);
  const seen = new Set(), box = $("cards");
  for (const a of list) {
    let el = cardEls.get(a.id);
    if (!el) {
      el = document.createElement("article");
      el.innerHTML = '<div class="shine"></div><div class="body"></div><div class="act"></div>';
      el.dataset.id = a.id;
      cardEls.set(a.id, el);
    }
    const cls = `card s-${a.state}${a.guessed ? " guessed" : ""}`;
    if (el.className !== cls) el.className = cls;
    setHTML(el.children[1], cardHTML(a, d.now));
    setHTML(el.lastChild, actHTML(a));
    const before = prevState.get(a.id);
    if (!firstRender && before !== a.state && (a.state === "waiting" || (a.state === "done" && before === "working"))) chime(a.state);
    prevState.set(a.id, a.state);
    seen.add(a.id);
  }
  for (const [id, el] of cardEls) if (!seen.has(id)) { el.remove(); cardEls.delete(id); prevState.delete(id); }
  const order = list.map((a) => a.id).join("|");
  if (order !== lastOrder) { list.forEach((a) => box.appendChild(cardEls.get(a.id))); lastOrder = order; }
  $("empty").hidden = list.length > 0;
  $("agent-count").textContent = list.length ? `${list.length} session${list.length > 1 ? "s" : ""}` : "";
  firstRender = false;

  const n = (s) => list.filter((a) => a.state === s).length;
  const pills = [["waiting", "var(--amber)", "need you"], ["working", "var(--blue)", "working"], ["done", "var(--green)", "done"]]
    .filter(([s]) => n(s)).map(([s, c, t]) => `<span class="pill" style="--c:${c}"><i></i><b>${n(s)}</b> ${t}</span>`);
  if (d.today.cost) pills.push(`<span class="pill" style="--c:var(--violet)"><i></i><b>${usd(d.today.cost, true)}</b> today</span>`);
  setHTML($("pills"), pills.join("") || '<span class="pill" style="--c:var(--faint)"><i></i>All quiet</span>');

  const waiting = list.filter((a) => a.state === "waiting");
  $("alert").hidden = !waiting.length;
  if (waiting.length) {
    const w = waiting[0];
    setHTML($("alert"), `${ICON.alert}<span><b>${esc(w.name)}</b> needs you — ${esc(w.detail || w.kind)}</span>${waiting.length > 1 ? `<span class="more">+${waiting.length - 1} more</span>` : ""}`);
  }
  document.title = waiting.length ? `(${waiting.length}) Agent Status` : "Agent Status";
}

// Allow/Deny on a waiting card: the agent's hook is polling for this answer.
$("cards").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-d]");
  if (!b || sent.has(b.dataset.ask)) return;
  const ask = b.dataset.ask, card = b.closest("article");
  sent.add(ask); askErr.delete(ask);
  card.querySelectorAll(".c-act button").forEach((x) => { x.disabled = true; });  // repainted as "Sending…" next tick
  try {
    const r = await fetch("decide?k=" + encodeURIComponent(KEY), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: card.dataset.id, ask, decision: b.dataset.d }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "HTTP " + r.status);
  } catch (err) {
    sent.delete(ask); askErr.set(ask, "Not sent: " + err.message);
    card.querySelectorAll(".c-act button").forEach((x) => { x.disabled = false; });
  }
});

// ---------- usage ----------
function renderToday(d) {
  const t = d.today;
  setHTML($("today-cost"), t.cost ? `<small>≈</small>$${t.cost.toFixed(2)}` : "$0");
  setHTML($("today-sub"), `<span><b>${num(t.tokens)}</b> tokens</span><span><b>${num(t.output)}</b> output</span>${t.burn ? `<span><b>${usd(t.burn)}</b>/hour</span>` : ""}`);
  const hourNow = new Date().getHours(), max = Math.max(...t.hours.map((h) => h[0]), 1);
  setHTML($("hours"), t.hours.map((h, i) =>
    `<i class="${i === hourNow ? "now" : i > hourNow ? "future" : ""}" style="height:${i > hourNow ? 4 : Math.max(3, (h[0] / max) * 100)}%"></i>`).join(""));

  setHTML($("models"), t.models.slice(0, 5).map((r) => `<tr>
      <td><span class="m">${esc(shortModel(r.model))}</span><small style="--a:${agentColor(r.agent)}">${esc(r.agent)}</small></td>
      <td>${num(r.output)}</td><td>${r.total ? num(r.total) : "—"}</td>
      <td class="c">${usd(r.cost, r.estimated)}</td><td>${r.tps ? Math.round(r.tps) : "—"}</td></tr>`).join("")
    || '<tr><td colspan="5" class="muted">Nothing yet today</td></tr>');
}

function renderLimits(d) {
  $("limits-panel").hidden = !d.limits.length;
  setHTML($("limits"), d.limits.map((p) => `<div class="limit"><div class="limit-h">${esc(p.name)}<span>${esc(p.tier)}</span></div>
    ${p.limits.map((l) => {
      const pct = Math.min(100, l.pct * 100), left = l.resets ? Date.parse(l.resets) / 1000 - d.now : 0;
      const c = pct >= 95 ? "var(--red)" : pct >= 80 ? "var(--amber)" : "var(--blue)";
      return `<div class="lrow"><span>${esc(l.label)}</span>${bar(pct, c)}<b>${Math.round(pct)}%</b><span class="reset">${left > 0 ? ago(left) : ""}</span></div>`;
    }).join("")}</div>`).join(""));
}

function renderWeek(d) {
  $("week-panel").hidden = !d.week.length;
  if (!d.week.length) return;
  const agents = [...new Set(d.week.flatMap((w) => Object.keys(w.agents)))];
  const max = Math.max(...d.week.map((w) => Object.values(w.agents).reduce((a, b) => a + b, 0)), 1);
  const today = new Date().toISOString().slice(0, 10);
  setHTML($("week"), d.week.map((w) => {
    const total = Object.values(w.agents).reduce((a, b) => a + b, 0);
    const day = new Date(w.date + "T12:00:00").toLocaleDateString([], { weekday: "short" });
    return `<div class="day${w.date === today ? " today" : ""}"><div class="stack" style="height:${Math.max(2, (total / max) * 100)}%">
      ${agents.map((a) => w.agents[a] ? `<i style="--a:${agentColor(a)};height:${(w.agents[a] / total) * 100}%"></i>` : "").join("")}
      </div><span>${day}</span></div>`;
  }).join(""));
  setHTML($("legend"), agents.map((a) => `<span><i style="--a:${agentColor(a)}"></i>${esc(a)}</span>`).join(""));
}

// ---------- system ----------
function renderSystem(d) {
  const s = d.system, h = s.hist, tiles = [];
  const coreMax = Math.max(...s.cpu.cores, 1) > 0 ? 100 : 1;
  tiles.push(`<div class="tile"><div class="tile-h"><h2>CPU</h2>${temp(s.cpu.temp)}</div>${gauge(s.cpu.pct, "var(--blue)")}
    <div class="cores">${s.cpu.cores.map((c) => `<i style="height:${Math.max(6, (c / coreMax) * 100)}%;opacity:${0.35 + c / 160}"></i>`).join("")}</div>
    <div class="kv"><span>load</span><b>${s.cpu.load.map((l) => l.toFixed(1)).join(" ")}</b></div>${spark([[h.cpu, "var(--blue)"]], 100)}</div>`);

  s.gpus.slice(0, 1).forEach((g) => tiles.push(`<div class="tile"><div class="tile-h"><h2>${esc(g.name)}</h2>${temp(g.temp)}</div>${gauge(g.util, "var(--green)")}
    <div class="kv"><span>VRAM</span><b>${bytes(g.mem_used)} / ${bytes(g.mem_total)}</b></div>
    ${g.power != null ? `<div class="kv"><span>power</span><b>${Math.round(g.power)} W${g.power_limit ? " / " + Math.round(g.power_limit) : ""}</b></div>` : ""}
    ${s.gpus.slice(1).map((o) => `<div class="kv"><span>${esc(o.name)}</span><b>${Math.round(o.util || 0)}%</b></div>`).join("")}
    ${spark([[h.gpu, "var(--green)"]], 100)}</div>`));

  const m = s.mem;
  tiles.push(`<div class="tile"><div class="tile-h"><h2>Memory</h2></div>${gauge(m.pct, "var(--violet)")}
    <div class="kv"><span>used</span><b>${bytes(m.used)} / ${bytes(m.total)}</b></div>
    ${m.swap_total ? `<div class="kv"><span>swap</span><b>${bytes(m.swap_used)}</b></div>` : ""}${spark([[h.mem, "var(--violet)"]], 100)}</div>`);

  tiles.push(`<div class="tile"><div class="tile-h"><h2>Network</h2></div>
    <div class="rate" style="--g:var(--cyan)"><em>↓</em>${bytes(s.net.rx)}<small>/s</small></div>
    <div class="rate" style="--g:var(--amber)"><em>↑</em>${bytes(s.net.tx)}<small>/s</small></div>
    ${spark([[h.rx, "var(--cyan)"], [h.tx, "var(--amber)"]])}</div>`);

  const disks = s.disks.map((k) => `<div class="kv"><span>${esc(k.mount === "/" ? "disk" : k.mount)}</span><b>${bytes(k.used)} / ${bytes(k.total)}</b></div>${bar((k.used / k.total) * 100, "var(--cyan)")}`).join("");
  const devices = s.devices.map((v) => `<div class="dev"><span>${esc(v.name)}</span>${bar(v.pct, v.pct <= 20 ? "var(--red)" : "var(--green)")}<b>${Math.round(v.pct)}%</b></div>`).join("");
  tiles.push(`<div class="tile"><div class="tile-h"><h2>Storage</h2>${temp(s.nvme_temp)}</div>${disks}
    ${devices ? `<h2 style="margin-top:4px">Devices</h2>${devices}` : ""}</div>`);

  setHTML($("system"), tiles.join(""));
  $("uptime").textContent = s.uptime ? "up " + ago(s.uptime) : "";
  $("host").textContent = s.host;
}

// ---------- loop ----------
let failures = 0;
async function tick() {
  if (!KEY) {
    $("offline").hidden = false;
    $("offline").textContent = "Missing access key: open the link printed by `agent-status url`";
    return;
  }
  try {
    const r = await fetch("status?k=" + encodeURIComponent(KEY), { cache: "no-store" });
    if (r.status === 403) throw new Error("bad key");
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    renderAgents(d); renderToday(d); renderLimits(d); renderWeek(d); renderSystem(d);
    failures = 0;
    $("offline").hidden = true;
    $("live").className = "live ok";
  } catch (e) {
    if (++failures > 1) {
      $("offline").hidden = false;
      $("offline").textContent = String(e.message) === "bad key" ? "Access key rejected: open the link printed by `agent-status url`" : "Can't reach the computer — retrying…";
      $("live").className = "live bad";
    }
  }
}
tick();
setInterval(tick, 2000);
