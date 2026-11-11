let STATE = null;
let currentBoard = "highest_score";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const medals = ["🥇", "🥈", "🥉"];

async function load() {
  const r = await fetch("/api/state");
  STATE = await r.json();
  renderBoards(); renderPlayers(); renderNameList();
}

/* ---------- boards ---------- */
const BOARD_VALUE = {
  highest_score:   s => [s.highest, `on ${s.highest_date}`],
  highest_average: s => [s.average, `${s.games} game${s.games === 1 ? "" : "s"} played`],
  lowest_score:    s => [s.lowest, `on ${s.lowest_date}`],
  most_krillions:  s => [s.krillion_count, "tap to see the questions"],
};

/* Daily Score: built from that day's results, so any date can be picked. */
function dailyRows(day) {
  const byId = Object.fromEntries(STATE.players.map(p => [p.id, p.name]));
  return STATE.results.filter(r => r.date === day)
    .sort((a, b) => b.score - a.score || String(byId[a.player_id]).localeCompare(String(byId[b.player_id])))
    .map(r => ({ player_id: r.player_id, name: byId[r.player_id], daily_score: r.score, krillions: r.krillions }));
}

function renderBoards() {
  const list = $("#board-list");
  const isDaily = currentBoard === "daily_score";
  $("#daily-picker").hidden = !isDaily;
  if (isDaily) {
    const day = $("#daily-date").value;
    const rows = dailyRows(day);
    if (!rows.length) {
      list.innerHTML = `<div class="empty">No dives yet on ${day}.<br>Be the first to submit for this day! 🌊</div>`;
      return;
    }
    list.innerHTML = rows.map((r, i) => `<div><div class="row">
      <div class="rank">${medals[i] || i + 1}</div>
      <div class="who"><div class="name">${esc(r.name)}</div><div class="meta">${esc(day)}</div></div>
      <div class="value">${esc(r.daily_score)}<span class="depth">${(r.daily_score * 10).toLocaleString()} m deep</span></div>
    </div></div>`).join("");
    return;
  }
  const rows = STATE.boards[currentBoard] || [];
  if (!rows.length) {
    list.innerHTML = `<div class="empty">No results yet.<br>Be the first to submit a dive! 🌊</div>`;
    return;
  }
  list.innerHTML = rows.map((s, i) => {
    const [val, meta] = BOARD_VALUE[currentBoard](s);
    let expansion = "";
    if (currentBoard === "most_krillions" && s.krillions.length) {
      expansion = `<div class="expand" id="exp-${s.player_id}" hidden>` +
        s.krillions.map(k => `<div>💎 <b>${esc(k.question || "(question not recorded)")}</b>` +
          (k.answer ? ` — “${esc(k.answer)}”` : "") + `<br><small>${esc(k.date)}</small></div>`).join("") +
        `</div>`;
    }
    const depth = currentBoard.includes("average") || currentBoard === "most_krillions" ? "" :
      `<span class="depth">${(val * 10).toLocaleString()} m deep</span>`;
    return `<div><div class="row" data-expand="${s.player_id}">
      <div class="rank">${medals[i] || i + 1}</div>
      <div class="who"><div class="name">${esc(s.name)}</div><div class="meta">${esc(meta)}</div></div>
      <div class="value">${esc(val)}${depth}</div>
    </div>${expansion}</div>`;
  }).join("");
  list.querySelectorAll("[data-expand]").forEach(el =>
    el.addEventListener("click", () => {
      const exp = document.getElementById("exp-" + el.dataset.expand);
      if (exp) exp.hidden = !exp.hidden;
    }));
}

$("#daily-date").value = new Date().toLocaleDateString("en-CA");
$("#board-select").addEventListener("change", e => {
  currentBoard = e.target.value; renderBoards();
});
$("#daily-date").addEventListener("change", () => { if (currentBoard === "daily_score") renderBoards(); });

/* ---------- players ---------- */
function renderPlayers() {
  const list = $("#player-list");
  if (!STATE.stats.length) {
    list.innerHTML = `<div class="empty">No players yet.<br>The first person to submit a result joins automatically.</div>`;
    return;
  }
  const byId = Object.fromEntries(STATE.results.map(r => [r.id, r]));
  list.innerHTML = STATE.stats.map(s => {
    const games = STATE.results.filter(r => r.player_id === s.player_id);
    const history = games.length ? `<div class="history" hidden id="hist-${s.player_id}">` +
      games.map(g => `<div>${esc(g.date)} — <b>${g.score}</b> pts (${(g.score * 10).toLocaleString()} m)` +
        (g.krillions.length ? "<br>" + g.krillions.map(k =>
          `💎 ${esc(k.question || "(question not recorded)")}` + (k.answer ? ` — “${esc(k.answer)}”` : "")).join("<br>") : "") +
        `<button class="delete" data-del="${g.id}">delete</button></div>`).join("") + `</div>` : "";
    return `<div class="card" data-player="${s.player_id}">
      <div class="name" style="font-weight:800;font-size:17px">${esc(s.name)}</div>
      <div class="grid">
        <div><b>${s.highest ?? "—"}</b><span>Highest</span></div>
        <div><b>${s.lowest ?? "—"}</b><span>Lowest</span></div>
        <div><b>${s.average ?? "—"}</b><span>Average</span></div>
        <div><b>${s.krillion_count}</b><span>💎 Krillions</span></div>
      </div>${history}</div>`;
  }).join("");
  list.querySelectorAll("[data-player]").forEach(card =>
    card.addEventListener("click", e => {
      if (e.target.closest("[data-del]")) return;
      const h = document.getElementById("hist-" + card.dataset.player);
      if (h) h.hidden = !h.hidden;
    }));
  list.querySelectorAll("[data-del]").forEach(btn =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this result?")) return;
      await fetch("/api/results/" + btn.dataset.del, { method: "DELETE" });
      load();
    }));
}

function renderNameList() {
  $("#player-names").innerHTML = STATE.players.map(p => `<option value="${esc(p.name)}">`).join("");
}

/* ---------- submit sound: rising bubble blips, made with WebAudio ---------- */
function playSubmitSound() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    if (ctx.resume) ctx.resume();
    [520, 680, 880, 1180].forEach((freq, i) => {
      const t = ctx.currentTime + i * 0.09;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, t);
      osc.frequency.exponentialRampToValueAtTime(freq * 1.6, t + 0.12);
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(t); osc.stop(t + 0.16);
    });
  } catch (_) { /* sound is a bonus — a failed sound must never block posting */ }
}

/* ---------- submit ---------- */
$("#f-date").value = new Date().toLocaleDateString("en-CA");
const savedName = localStorage.getItem("krillion_name");
if (savedName) $("#f-name").value = savedName;

let krCount = 0;
function renderKrFields() {
  $("#kr-count").textContent = krCount;
  $("#kr-fields").innerHTML = Array.from({ length: krCount }, (_, i) => `
    <div class="kr-field">
      <label>💎 One in a Krillion #${i + 1} — the question
        <input class="kr-q" placeholder="e.g. Name a type of cheese">
      </label>
      <label>Your answer (optional)
        <input class="kr-a" placeholder="e.g. Cabrales">
      </label>
    </div>`).join("");
}
$("#kr-plus").addEventListener("click", () => { if (krCount < 7) { krCount++; renderKrFields(); } });
$("#kr-minus").addEventListener("click", () => { if (krCount > 0) { krCount--; renderKrFields(); } });

$("#f-score").addEventListener("input", e => {
  const v = parseInt(e.target.value, 10);
  $("#depth-hint").textContent = Number.isFinite(v) && v >= 0 ? `= ${(v * 10).toLocaleString()} metres deep` : "";
});

$("#submit-form").addEventListener("submit", async e => {
  e.preventDefault();
  const msg = $("#submit-msg");
  const qs = [...document.querySelectorAll(".kr-q")];
  const as = [...document.querySelectorAll(".kr-a")];
  const payload = {
    player_name: $("#f-name").value.trim(),
    date: $("#f-date").value,
    score: parseInt($("#f-score").value, 10),
    krillions: qs.map((q, i) => ({ question: q.value.trim(), answer: as[i].value.trim() })),
  };
  const r = await fetch("/api/results", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json();
  if (!r.ok) { msg.textContent = "⚠️ " + (data.error || "Something went wrong"); msg.className = "msg err"; return; }
  playSubmitSound();
  localStorage.setItem("krillion_name", payload.player_name);
  msg.textContent = `✅ Posted! ${payload.player_name}: ${payload.score} pts on ${payload.date}. Check the boards!`;
  msg.className = "msg ok";
  krCount = 0; renderKrFields(); $("#f-score").value = ""; $("#depth-hint").textContent = "";
  await load();
});

/* ---------- nav ---------- */
document.querySelectorAll("nav button").forEach(b =>
  b.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
  }));

load().catch(() => { $("#board-list").innerHTML = `<div class="empty">Couldn't load — try refreshing.</div>`; });
