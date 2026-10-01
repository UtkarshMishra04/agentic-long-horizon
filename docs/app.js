/* Interactive page for the RoboEnvs agent runs. No dependencies; works from file:// (data is loaded as scripts). */
(function () {
  "use strict";
  const GITHUB_URL = "https://github.com/OWNER/roboenvs-agents";  // TODO: set to the public repository
  const S = window.SUMMARY, CAT = window.CATALOG, RUNS = window.RUNS, DIFFS = window.DIFFS;
  const AG = { codex: { name: "Codex", color: "var(--codex)", hex: "#2a78d6" }, claude: { name: "Claude", color: "var(--claude)", hex: "#eb6834" } };
  const OBJ_COLOR = { red_box: "#e34948", blue_box: "#2a78d6", yellow_box: "#eda100", cyan_box: "#1baf7a", lstick: "#4a3aa7", rack: "#898781" };
  const BOX_SIZE = { red_box: 0.05, blue_box: 0.07, yellow_box: 0.07, cyan_box: 0.07 };
  const GOALS = {
    "LiftRedBox-v0": ["the red box is held by the gripper or raised above the table", 1500],
    "RedBoxOnRack-v0": ["the red box rests upright on the rack", 1800],
    "RedBoxUnderRack-v0": ["the red box is under the rack, resting on the table", 1300],
    "RedBoxUnderRack-v1": ["same goal, different scene distribution", 2500],
    "RedBoxToBlueSpot-v0": ["the red box is at the blue box's starting position; the stick back at its own start; blue box and stick on the table inside the workspace; nothing stacked", 1000],
    "RedBoxToBlueSpot-v1": ["the red box is at the blue box's starting position; blue box and stick on the table inside the workspace; nothing stacked", 2400],
    "PackRack-v0": ["yellow, red and cyan boxes upright on the rack", 1000],
    "PackRack-v1": ["yellow, cyan and blue boxes upright on the rack", 1600],
    "PackRack-v2": ["red, yellow, cyan and blue boxes upright on the rack", 2000],
  };
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  const tip = $("#tooltip");
  function showTip(html, ev) { tip.innerHTML = html; tip.style.display = "block"; moveTip(ev); }
  function moveTip(ev) {
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
    if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => (tip.style.display = "none");
  const pct = (a) => (a[1] ? (100 * a[0]) / a[1] : 0);
  function md(text) {  // minimal markdown: tables, bullets, headings, bold, code
    const lines = String(text).split("\n"), out = [];
    let i = 0;
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
    while (i < lines.length) {
      const l = lines[i];
      if (/^\|/.test(l)) {
        const rows = [];
        while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
        const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        const body = rows.filter((r) => !/^\|[\s|:-]+\|$/.test(r));
        out.push("<table><thead><tr>" + cells(body[0]).map((c) => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>" +
          body.slice(1).map((r) => "<tr>" + cells(r).map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
        continue;
      }
      if (/^\s*[-*] /.test(l)) {
        const items = [];
        while (i < lines.length && /^\s*[-*] /.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*] /, ""));
        out.push("<ul>" + items.map((x) => "<li>" + inline(x) + "</li>").join("") + "</ul>");
        continue;
      }
      if (/^#+ /.test(l)) { out.push("<h4>" + inline(l.replace(/^#+ /, "")) + "</h4>"); i++; continue; }
      if (l.trim()) {  // join hard-wrapped lines into one paragraph
        const para = [];
        while (i < lines.length && lines[i].trim() && !/^\||^\s*[-*] |^#+ /.test(lines[i])) para.push(lines[i++].trim());
        out.push("<p>" + inline(para.join(" ")) + "</p>");
        continue;
      }
      i++;
    }
    return out.join("");
  }

  // ------------------------------------------------------------------ header, benchmark, prompts
  function tiles() {
    const tot = (a) => S.envs.reduce((acc, e) => [acc[0] + S.results[e][a][0], acc[1] + S.results[e][a][1]], [0, 0]);
    const c = tot("codex"), a = tot("claude");
    const t = [
      ["Claude Code · Opus 5.5", `${a[0]}/${a[1]}`, `${pct(a).toFixed(1)}% of episodes · 60 scenes per task`, "claude"],
      ["Codex · GPT-6-Astra", `${c[0]}/${c[1]}`, `${pct(c).toFixed(1)}% of episodes · 20 seeds per task`, "codex"],
      ["Wall-clock time", `${Math.round(S.agents.claude.minutes / 60 * 10) / 10} h vs ${Math.round(S.agents.codex.minutes / 60 * 10) / 10} h`, "Claude vs Codex, start to final report", null],
      ["Evaluation runs", `${RUNS.claude.iterations.length} vs ${RUNS.codex.iterations.length}`, `${S.agents.claude.tool_calls} vs ${S.agents.codex.tool_calls} tool calls`, null],
    ];
    $("#tiles").innerHTML = t.map(([l, v, s, ag]) => `<div class="tile"><div class="label">${ag ? `<span class="tag ${ag}"><span>${l}</span></span>` : l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join("");
  }
  const TASKINFO = {
    "LiftRedBox-v0": { objects: "rack, L-stick, red box", start: "The red box starts beyond reach (≥ 0.85 m); the stick and the rack are within reach.", hard: "The arm cannot get to the box directly. The box has to come closer before it can be grasped and lifted." },
    "RedBoxOnRack-v0": { objects: "rack, L-stick, red box", start: "Same scene distribution as LiftRedBox: the red box starts out of reach.", hard: "Bring the box within reach, grasp it, and set it down upright on the 22 × 32 cm rack top without knocking the rack." },
    "RedBoxUnderRack-v0": { objects: "rack, L-stick, red box", start: "The rack starts beyond reach; the red box is within reach.", hard: "At least half of the box must end under a rack the arm cannot reach, while staying on the table. Placing from above is impossible under a 16 cm-tall rack top." },
    "RedBoxUnderRack-v1": { objects: "rack, L-stick, red box", start: "Both the rack and the red box start beyond reach.", hard: "Everything of the v0 task, plus the box itself starts out of reach. The light rack is easy to drag or tip." },
    "RedBoxToBlueSpot-v0": { objects: "L-stick, red box, blue box", start: "All three objects start within reach; the target is wherever the blue box starts.", hard: "The target spot is occupied by the blue box, which must be moved somewhere clear first. The stick must end within 1 cm of its starting pose, and nothing may rest on anything." },
    "RedBoxToBlueSpot-v1": { objects: "L-stick, red box, blue box", start: "The red box starts beyond reach; the blue box and the stick are within reach.", hard: "Combines the occupied target spot with an out-of-reach red box; every object must end on the table inside the workspace." },
    "PackRack-v0": { objects: "rack, yellow, red and cyan boxes", start: "All boxes start within reach; one (cyan) can already be on the rack.", hard: "Three boxes must fit upright on a 22 × 32 cm rack without touching or knocking each other off." },
    "PackRack-v1": { objects: "rack, yellow, cyan and blue boxes", start: "All boxes start within reach, mostly on the table.", hard: "Three 7 cm boxes on the small rack: little room for the fingers between them." },
    "PackRack-v2": { objects: "rack, red, yellow, cyan and blue boxes", start: "All four boxes start within reach.", hard: "Four boxes on one small rack: the tightest packing, with the most chances to clip an already placed box." },
  };
  function taskTable() {
    $("#taskcards").innerHTML = S.envs.map((e, i) => {
      const r = S.results[e], info = TASKINFO[e];
      const score = (a, k) => `<span class="tag ${a}"><span>${AG[a].name} ${r[k][0]}/${r[k][1]}</span></span>`;
      return `<div class="taskcard card">
        <div class="tc-head"><span class="tc-num">${i + 1}</span><code>${e}</code></div>
        <div class="tc-imgs"><figure><img src="media/tasks/${e}_initial.png" alt="${e} initial state" loading="lazy"><figcaption>start</figcaption></figure>
          <figure><img src="media/tasks/${e}_goal.png" alt="${e} goal state" loading="lazy"><figcaption>a goal state</figcaption></figure></div>
        <p class="small"><strong>Goal:</strong> ${esc(GOALS[e][0])}.</p>
        <p class="small"><strong>Objects:</strong> ${info.objects}. <strong>Time limit:</strong> ${GOALS[e][1]} steps (${GOALS[e][1] / 20} s).</p>
        <p class="small"><strong>Start:</strong> ${info.start}</p>
        <p class="small"><strong>Why it is hard:</strong> ${info.hard}</p>
        <div class="tc-foot">${score("codex", "codex")} ${score("claude", "claude")}
          <button class="btn" data-watch="${e}" style="margin-left:auto">watch ▶</button></div>
      </div>`;
    }).join("");
    $$("[data-watch]").forEach((b) => (b.onclick = () => { const t = $$("#taskbtns .btn").find((x) => x.dataset.env === b.dataset.watch); if (t) t.click(); $("#videos").scrollIntoView({ behavior: "smooth" }); }));
    const lb = $("#lightbox");
    $("#openfig").onclick = (ev) => { ev.preventDefault(); lb.classList.add("open"); };
    lb.onclick = () => lb.classList.remove("open");
    $("#prompt-merged").textContent = window.PROMPTS.merged;
  }

  // ------------------------------------------------------------------ results chart
  function resultsTable() {
    const cell = (a) => `<td class="num ${a[0] === a[1] ? "ok" : "bad"}">${a[0]}/${a[1]} <span class="muted small">(${pct(a).toFixed(0)}%)</span></td>`;
    const tot = (k) => S.envs.reduce((acc, e) => [acc[0] + S.results[e][k][0], acc[1] + S.results[e][k][1]], [0, 0]);
    $("#restable").innerHTML = `<table><thead><tr><th>task</th><th>goal</th><th class="num">time limit</th>` +
      `<th class="num"><span class="tag codex"><span>Codex</span></span><br><span class="muted small">20 seeds</span></th>` +
      `<th class="num"><span class="tag claude"><span>Claude</span></span><br><span class="muted small">60 scenes</span></th></tr></thead><tbody>` +
      S.envs.map((e) => `<tr><td><code>${e}</code></td><td class="small">${esc(GOALS[e][0])}</td><td class="num">${GOALS[e][1]}</td>${cell(S.results[e].codex)}${cell(S.results[e].claude)}</tr>`).join("") +
      `<tr><td colspan="3"><strong>all tasks</strong></td>${cell(tot("codex"))}${cell(tot("claude"))}</tr></tbody></table>`;
  }
  const fmtMin = (m) => (m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min` : `${m} min`);

  // ------------------------------------------------------------------ iteration explorer
  let iterAgent = "claude";
  function openIteration(agent, index) {
    iterAgent = agent;
    $$("[data-iteragent]").forEach((b) => b.classList.toggle("active", b.dataset.iteragent === agent));
    const sl = $("#iterslider"); sl.max = RUNS[agent].iterations.length - 1; sl.value = index;
    renderIteration();
    $("#iterations").scrollIntoView({ behavior: "smooth" });
  }
  function renderIteration() {
    const its = RUNS[iterAgent].iterations, sl = $("#iterslider");
    sl.max = its.length - 1;
    const i = +sl.value, it = its[i];
    const prev = {};  // most recent earlier result per environment
    for (let k = 0; k < i; k++) for (const e in its[k].results) prev[e] = its[k].results[e];
    const rows = S.envs.map((e) => {
      const r = it.results[e];
      if (!r) return `<tr class="muted"><td>${e}</td><td colspan="3" class="small">not evaluated in this run</td></tr>`;
      const p = prev[e], d = p ? pct(r) - pct(p) : null;
      const delta = d === null ? '<span class="pill">first run</span>' : Math.abs(d) < 0.5 ? '<span class="muted small">no change</span>' : `<span class="${d > 0 ? "ok" : "bad"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(0)} pts</span>`;
      return `<tr><td>${e}</td><td class="num">${r[0]}/${r[1]}</td><td style="width:40%"><div style="background:#e1e0d9;border-radius:3px;height:8px"><div style="width:${pct(r)}%;height:8px;border-radius:3px;background:${AG[iterAgent].hex}"></div></div></td><td>${delta}</td></tr>`;
    }).join("");
    const tot = Object.values(it.results).reduce((acc, v) => [acc[0] + v[0], acc[1] + v[1]], [0, 0]);
    const diff = it.diff_index !== null && it.diff_index !== undefined ? DIFFS[iterAgent][it.diff_index] : null;
    const obs = it.observed.length ? "<ol>" + it.observed.map((t) => `<li>${md(t)}</li>`).join("") + "</ol>" : '<p class="muted small">No narration between the previous run and this one.</p>';
    $("#iterdetail").innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-top:12px">
        <h3 style="margin:0"><span class="tag ${iterAgent}"><span>${esc(it.label)}</span></span> <span class="muted small">· run ${i + 1} of ${its.length} · finished ${fmtMin(it.minutes)} after start · ${esc(it.seeds)}</span></h3>
        <div><strong>${tot[0]}/${tot[1]}</strong> <span class="muted small">(${pct(tot).toFixed(1)}%)</span></div>
      </div>
      <div class="grid2" style="margin-top:8px">
        <div><h4>Results in this run</h4><table>${rows}</table></div>
        <div><h4>What changed</h4><div class="small">${md(it.changed || "")}</div>
          <h4>What the agent observed on the way here</h4><div class="small" style="max-height:260px;overflow:auto">${obs}</div></div>
      </div>
      <div style="margin-top:10px">${diff ? `<details><summary>Code diff vs the previous snapshot: +${it.lines_added} / −${it.lines_removed} lines in ${diff.length} file(s)</summary>${diff.map((f) => `<h4 style="margin:10px 0 4px"><code>${esc(f.path)}</code></h4><pre class="diff">${renderDiff(f.diff)}</pre>`).join("")}</details>` : `<p class="muted small">${it.snapshot ? "First saved snapshot (no earlier one to diff against)." : "No code snapshot was saved for this run."}</p>`}</div>`;
  }
  function renderDiff(text) {
    return text.split("\n").map((l) => {
      const c = l.startsWith("+++") || l.startsWith("---") ? "#52514e" : l.startsWith("+") ? "#006300" : l.startsWith("-") ? "#b02a2a" : l.startsWith("@@") ? "#2a78d6" : "#52514e";
      const bg = l.startsWith("+") && !l.startsWith("+++") ? "#eaf6ea" : l.startsWith("-") && !l.startsWith("---") ? "#fbecec" : "transparent";
      return `<span style="display:block;color:${c};background:${bg}">${esc(l) || " "}</span>`;
    }).join("");
  }
  function iterations() {
    $$("[data-iteragent]").forEach((b) => (b.onclick = () => { iterAgent = b.dataset.iteragent; $$("[data-iteragent]").forEach((x) => x.classList.toggle("active", x === b)); $("#iterslider").value = RUNS[iterAgent].iterations.length - 1; renderIteration(); }));
    $("#iterslider").oninput = renderIteration;
    $("#iterprev").onclick = () => { const s = $("#iterslider"); s.value = Math.max(0, +s.value - 1); renderIteration(); };
    $("#iternext").onclick = () => { const s = $("#iterslider"); s.value = Math.min(+s.max, +s.value + 1); renderIteration(); };
    $("#iterslider").max = RUNS.claude.iterations.length - 1; $("#iterslider").value = 0;
    renderIteration();
    const lastAgentText = (a) => { const l = RUNS[a].log.filter((e) => e.who === "agent"); return l[l.length - 1].text; };
    $("#claude-report").innerHTML = md(window.CLAUDE_REPORT || lastAgentText("claude"));
    $("#codex-report").innerHTML = md(lastAgentText("codex"));
  }

  // ------------------------------------------------------------------ logs
  let logAgent = "claude";
  function renderLog() {
    const kinds = new Set($$("[data-logkind]").filter((c) => c.checked).map((c) => c.dataset.logkind));
    const q = $("#logsearch").value.trim().toLowerCase();
    const log = RUNS[logAgent].log, t0 = Date.parse(log[0].t);
    const rows = log.filter((e) => kinds.has(e.who) && (!q || e.text.toLowerCase().includes(q)));
    $("#logcount").textContent = `${rows.length} of ${log.length} entries`;
    const badge = { user: ["prompt", "#0b0b0b"], agent: [AG[logAgent].name, AG[logAgent].hex], tool: ["command", "#898781"] };
    const hl = (s) => (q ? esc(s).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`) : esc(s));
    $("#logtable tbody").innerHTML = rows.map((e) => {
      const m = Math.round((Date.parse(e.t) - t0) / 60000);
      const body = e.who === "tool" ? `<code style="white-space:pre-wrap">${hl(e.text.length > 600 ? e.text.slice(0, 600) + " …" : e.text)}</code>` : e.who === "agent" && !q ? md(e.text) : `<div style="white-space:pre-wrap">${hl(e.text)}</div>`;
      return `<tr><td class="num small muted" style="width:70px">+${m} min</td><td style="width:90px"><span class="pill" style="color:${badge[e.who][1]}">${badge[e.who][0]}</span></td><td class="small">${body}</td></tr>`;
    }).join("");
  }
  function logs() {
    $$("[data-logagent]").forEach((b) => (b.onclick = () => { logAgent = b.dataset.logagent; $$("[data-logagent]").forEach((x) => x.classList.toggle("active", x === b)); renderLog(); }));
    $$("[data-logkind]").forEach((c) => (c.onchange = renderLog));
    $("#logsearch").oninput = renderLog;
    renderLog();
  }

  // ------------------------------------------------------------------ code browser
  let codeAgent = "claude";
  const KW = /\b(def|class|return|if|elif|else|for|while|in|not|and|or|import|from|as|with|try|except|finally|raise|lambda|yield|None|True|False|pass|break|continue|global|is)\b/g;
  function highlight(src) {
    const re = /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(\b\d+(?:\.\d+)?(?:e-?\d+)?\b)|([^#"'\d]+|.)/g;
    let out = "", m;
    while ((m = re.exec(src))) {
      if (m[1]) out += `<span style="color:#898781">${esc(m[1])}</span>`;
      else if (m[2]) out += `<span style="color:#006300">${esc(m[2])}</span>`;
      else if (m[3]) out += `<span style="color:#b25a00">${esc(m[3])}</span>`;
      else out += esc(m[4]).replace(KW, '<span style="color:#4a3aa7;font-weight:600">$1</span>');
    }
    return out;
  }
  function showFile(path) {
    const text = RUNS[codeAgent].code[path];
    $$("#filelist li").forEach((li) => li.classList.toggle("now", li.dataset.path === path));
    const lines = highlight(text).split("\n");
    $("#codeview").innerHTML = lines.map((l, i) => `<span style="display:inline-block;width:42px;color:#c3c2b7;user-select:none;text-align:right;margin-right:12px">${i + 1}</span>${l}`).join("\n");
  }
  function codeBrowser() {
    const render = () => {
      const code = RUNS[codeAgent].code, files = Object.keys(code).filter((f) => f.startsWith("solutions/")).sort();
      const loc = files.reduce((n, f) => n + code[f].split("\n").length, 0);
      $("#codestats").textContent = `${files.length} files · ${loc.toLocaleString()} lines`;
      $("#filelist").innerHTML = files.map((f) => `<li data-path="${esc(f)}"><span>${esc(f)}</span><span class="muted small" style="margin-left:auto">${code[f].split("\n").length}</span></li>`).join("");
      $$("#filelist li").forEach((li) => (li.onclick = () => showFile(li.dataset.path)));
      const main = files.find((f) => /(^|\/)common\.py$/.test(f)) || files[0];
      showFile(main);
    };
    $$("[data-codeagent]").forEach((b) => (b.onclick = () => { codeAgent = b.dataset.codeagent; $$("[data-codeagent]").forEach((x) => x.classList.toggle("active", x === b)); render(); }));
    render();
  }

  // ------------------------------------------------------------------ video explorer
  const EP = {}, EPWAIT = {};
  window.__episode = (d) => { EP[d.id] = d; (EPWAIT[d.id] || []).forEach((f) => f(d)); delete EPWAIT[d.id]; };
  function loadEpisode(id) {
    if (EP[id]) return Promise.resolve(EP[id]);
    return new Promise((res) => {
      (EPWAIT[id] = EPWAIT[id] || []).push(res);
      if (EPWAIT[id].length === 1) { const sc = document.createElement("script"); sc.src = `data/episodes/${id}.js`; document.body.appendChild(sc); }
    });
  }
  const EV_COLOR = { close: "#0b0b0b", open: "#898781", lift: "#2a78d6", slide: "#4a3aa7", goal: "#0ca30c" };
  const EV_LABEL = { close: "grasp", open: "release", lift: "lift", slide: "slides", goal: "goal" };
  let task = "RedBoxUnderRack-v1";
  const mode = "both";
  const seedIdx = { codex: 0, claude: 0 };
  let players = [];

  function idxOf(ep, step) {  // index into the downsampled arrays for a control step
    const t = ep.t; let lo = 0, hi = t.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (t[mid] <= step) lo = mid; else hi = mid - 1; }
    return lo;
  }

  class Player {
    constructor(agent, host) {
      this.agent = agent; this.host = host; this.speed = 1; this.loop = false; this.step = 0;
      this.build(); this.select(seedIdx[agent]);
    }
    episodes() { return CAT.filter((c) => c.agent === this.agent && c.env === task).sort((a, b) => a.seed - b.seed); }
    build() {
      const a = this.agent, el = document.createElement("div");
      el.className = "player";
      el.innerHTML = `
        <div class="head"><span class="tag ${a}"><span>${AG[a].name}</span></span>
          <span class="status"></span></div>
        <div class="row">
          <div>
            <div class="vidbox"><video muted playsinline preload="auto"></video></div>
            <div class="transport">
              <button class="btn" data-act="restart" title="Back to the start">⏮</button>
              <button class="btn" data-act="prevev" title="Previous event ( [ )">◀◀</button>
              <button class="btn" data-act="back" title="One frame back (←)">◀</button>
              <button class="btn" data-act="play" title="Play / pause (space)" style="min-width:44px">▶</button>
              <button class="btn" data-act="fwd" title="One frame forward (→)">▶</button>
              <button class="btn" data-act="nextev" title="Next event ( ] )">▶▶</button>
              <span class="readout"></span>
            </div>
            <div class="scrub"><div class="ticks"></div><input type="range" min="0" value="0"></div>
            <div class="timelimit" title="Episode length against the task's time limit"><div class="used"></div><div class="cursor"></div></div>
            <div class="btnrow" style="margin-top:8px"><span class="lbl">Speed</span>
              ${[0.25, 0.5, 1, 2, 4, 8].map((v) => `<button class="btn" data-speed="${v}">${v}×</button>`).join("")}
              <label class="small" style="margin-left:6px"><input type="checkbox" data-act="loop"> loop</label>
              <label class="small"><input type="checkbox" data-act="trails" checked> trails</label>
            </div>
            <p class="small muted" style="margin:6px 0 0">Speeds are relative to real time (20 control steps per second).</p>
          </div>
          <div class="panel"><h4><span>Top-down view</span><span class="muted small">x forward from the robot base, metres</span></h4><div class="map"></div><div class="maplegend small"></div></div>
        </div>
        <div class="panel" style="margin-top:10px"><h4><span>Events</span><span class="muted small">auto-detected · click to jump</span></h4><ul class="events"></ul></div>`;
      this.host.appendChild(el); this.el = el;
      this.video = $("video", el); this.range = $(".scrub input", el);
      $$("[data-act]", el).forEach((b) => {
        const act = b.dataset.act;
        if (act === "loop") b.onchange = () => (this.loop = b.checked);
        else if (act === "trails") b.onchange = () => { this.trails = b.checked; this.draw(); };
        else b.onclick = () => this.action(act);
      });
      this.trails = true;
      $$("[data-speed]", el).forEach((b) => (b.onclick = () => this.setSpeed(+b.dataset.speed)));
      this.range.oninput = () => { this.pause(); this.seekStep(+this.range.value); };
      this.video.onended = () => { if (this.loop) { this.video.currentTime = 0; this.video.play(); } else this.updatePlayBtn(); };
      this.video.onplay = this.video.onpause = () => this.updatePlayBtn();
      el.addEventListener("click", () => (Player.focused = this));
    }
    async select(i) {
      const eps = this.episodes();
      this.meta = eps.find((c) => c.success) || eps[0];  // one episode per agent and task
      const c = this.meta;
      $(".status", this.el).innerHTML = c.success ? `<span class="ok">✓ goal at step ${c.success_step}</span> <span class="muted">(${(c.success_step / 20).toFixed(1)} s)</span>` : `<span class="bad">✗ not solved in ${c.steps} steps</span>`;
      this.video.src = c.video; this.video.load();
      this.ep = await loadEpisode(c.id);
      this.range.max = this.ep.steps;
      this.setSpeed(this.speed);
      this.playhead = []; this.buildMap(); this.buildEvents();
      const lim = GOALS[task][1];
      $(".timelimit .used", this.el).style.width = Math.min(100, 100 * this.ep.steps / lim) + "%";
      this.seekStep(0);
      this.tick();
    }
    get stepsPerFrame() { return this.meta.steps_per_frame; }
    timeForStep(s) { return Math.min(Math.ceil(s / this.stepsPerFrame) / this.meta.fps + 0.001, (this.video.duration || 1e9) - 0.001); }
    stepForTime(t) { return Math.min(Math.floor(t * this.meta.fps + 1e-6) * this.stepsPerFrame, this.ep.steps); }
    setSpeed(v) {
      this.speed = v;
      const videoSpeedup = this.stepsPerFrame * this.meta.fps / 20;  // video seconds -> real seconds
      this.video.playbackRate = Math.max(0.0625, Math.min(16, v / videoSpeedup));
      $$("[data-speed]", this.el).forEach((b) => b.classList.toggle("active", +b.dataset.speed === v));
    }
    action(a) {
      const evs = this.ep ? this.ep.events : [];
      if (a === "play") return this.video.paused ? this.play() : this.pause();
      if (a === "restart") { this.pause(); return this.seekStep(0); }
      if (a === "back") { this.pause(); return this.seekStep(Math.max(0, this.step - this.stepsPerFrame)); }
      if (a === "fwd") { this.pause(); return this.seekStep(Math.min(this.ep.steps, this.step + this.stepsPerFrame)); }
      if (a === "nextev") { const e = evs.find((e) => e.step > this.step + 1); if (e) { this.pause(); this.seekStep(e.step); } return; }
      if (a === "prevev") { const e = [...evs].reverse().find((e) => e.step < this.step - 1); this.pause(); this.seekStep(e ? e.step : 0); }
    }
    play() { if (this.step >= this.ep.steps - 1) this.seekStep(0); this.video.play(); }
    pause() { this.video.pause(); }
    updatePlayBtn() { $('[data-act="play"]', this.el).textContent = this.video.paused ? "▶" : "⏸"; }
    seekStep(s) { this.video.currentTime = this.timeForStep(s); this.setStep(s); }
    tick() {
      if (!this.el.isConnected) return;
      if (this.ep && !this.video.paused) this.setStep(this.stepForTime(this.video.currentTime));
      requestAnimationFrame(() => this.tick());
    }
    setStep(s) {
      this.step = s; this.range.value = s; this.draw();
      const c = this.meta;
      $(".readout", this.el).textContent = `step ${s} / ${this.ep.steps} · ${(s / 20).toFixed(1)} s` + (c.success && s >= c.success_step ? " · ✓ goal" : "");
      $(".timelimit .cursor", this.el).style.left = Math.min(100, 100 * s / GOALS[task][1]) + "%";
    }
    // ---- map
    buildMap() {
      const box = $(".map", this.el); box.innerHTML = "";
      const W = Math.max(240, box.clientWidth || 320), H = W * 1.0;
      const xr = [-0.08, 1.05], yr = [-0.55, 0.55], sc = Math.min((H - 20) / (xr[1] - xr[0]), (W - 10) / (yr[1] - yr[0]));
      const P = (x, y) => [W / 2 - y * sc, H - 14 - (x - xr[0]) * sc];
      this.P = P; this.sc = sc;
      const s = svg("svg", { width: W, height: H, role: "img", "aria-label": "Top-down view of the scene" }, box);
      for (let g = 0.1; g <= 1.0001; g += 0.1) {
        const [ax, ay] = P(g, yr[0]), [bx] = P(g, yr[1]);
        svg("line", { x1: ax, x2: bx, y1: ay, y2: ay, stroke: "#eeede8" }, s);
        if (Math.abs(g * 10 % 2) < 0.01) svg("text", { x: 4, y: ay + 3, "font-size": 9, fill: "#b5b3ab" }, s).textContent = g.toFixed(1);
      }
      const base = P(0, 0);
      [[0.75, "inside reach < 0.75 m", "4 3"], [0.85, "beyond ≥ 0.85 m", "1 3"]].forEach(([rad, lab, dash]) => {
        const a1 = P(rad * Math.cos(1.2), rad * Math.sin(1.2)), a2 = P(rad * Math.cos(-1.2), rad * Math.sin(-1.2));
        svg("path", { d: `M${a1[0]},${a1[1]} A${rad * sc},${rad * sc} 0 0 1 ${a2[0]},${a2[1]}`, fill: "none", stroke: "#c3c2b7", "stroke-dasharray": dash }, s);
        const lp = P(rad + 0.02, -0.5 * rad); svg("text", { x: lp[0], y: lp[1], "font-size": 9, fill: "#898781" }, s).textContent = lab;
      });
      svg("rect", { x: base[0] - 9, y: base[1] - 6, width: 18, height: 12, rx: 3, fill: "#52514e" }, s);
      svg("text", { x: base[0] + 13, y: base[1] + 4, "font-size": 9, fill: "#52514e" }, s).textContent = "robot base";
      // goal targets
      for (const c of this.ep.goal.conditions || []) {
        if (c.target_xy) {
          const [gx, gy] = P(c.target_xy[0], c.target_xy[1]);
          svg("circle", { cx: gx, cy: gy, r: c.tolerance * sc, fill: "rgba(12,163,12,0.07)", stroke: "#0ca30c", "stroke-dasharray": "3 2" }, s);
          svg("text", { x: gx + c.tolerance * sc + 3, y: gy + 3, "font-size": 9, fill: "#006300" }, s).textContent = "goal: " + c.objects[0];
        }
      }
      this.layer = svg("g", {}, s);
      this.objEls = {};
      const names = Object.keys(this.ep.objects).sort((a, b) => (a === "rack" ? -1 : b === "rack" ? 1 : 0));
      for (const n of names) {
        const col = OBJ_COLOR[n] || "#52514e", g = svg("g", { style: "cursor:default" }, this.layer);
        const trail = svg("path", { fill: "none", stroke: col, "stroke-width": 1.5, "stroke-opacity": 0.45 }, g);
        let shape;
        if (n === "rack") shape = svg("rect", { x: -0.11 * sc, y: -0.16 * sc, width: 0.22 * sc, height: 0.32 * sc, fill: "rgba(137,135,129,0.18)", stroke: col, "stroke-width": 1.5 }, g);
        else if (n === "lstick") shape = svg("path", { fill: "none", stroke: col, "stroke-width": Math.max(3, 0.03 * sc), "stroke-linecap": "round", "stroke-linejoin": "round" }, g);
        else { const w = (BOX_SIZE[n] || 0.06) * sc; shape = svg("rect", { x: -w / 2, y: -w / 2, width: w, height: w, rx: 2, fill: col, stroke: "#fcfcfb", "stroke-width": 1.5 }, g); }
        const label = svg("text", { "font-size": 10, fill: "#0b0b0b", "font-weight": 600 }, g); label.textContent = n.replace("_", " ");
        g.addEventListener("mousemove", (ev) => { const o = this.ep.objects[n], i = idxOf(this.ep, this.step); showTip(`<b>${n}</b> at step ${this.step}<br>x ${o.x[i].toFixed(3)} · y ${o.y[i].toFixed(3)} · z ${o.z[i].toFixed(3)} m<br>distance from base ${Math.hypot(o.x[i], o.y[i]).toFixed(3)} m · tilt ${o.tilt[i]}°`, ev); });
        g.addEventListener("mouseleave", hideTip);
        this.objEls[n] = { g, trail, shape, label };
      }
      this.eeTrail = svg("path", { fill: "none", stroke: "#0b0b0b", "stroke-width": 1, "stroke-opacity": 0.35, "stroke-dasharray": "2 2" }, this.layer);
      this.ee = svg("g", {}, this.layer);
      this.eeRing = svg("circle", { r: 6, fill: "#fcfcfb", stroke: "#0b0b0b", "stroke-width": 2 }, this.ee);
      this.eeDot = svg("circle", { r: 2.5, fill: "#0b0b0b" }, this.ee);
      this.eeText = svg("text", { "font-size": 9, fill: "#0b0b0b", x: 9, y: -7 }, this.ee);
      $(".maplegend", this.el).innerHTML = names.map((n) => `<span style="margin-right:10px"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${OBJ_COLOR[n] || "#52514e"}"></span> ${n.replace("_", " ")}</span>`).join("") +
        `<span><span style="display:inline-block;width:9px;height:9px;border-radius:50%;border:2px solid #0b0b0b"></span> gripper (filled = closed)</span>`;
    }
    draw() {
      if (!this.ep || !this.P) return;
      const ep = this.ep, i = idxOf(ep, this.step), P = this.P, sc = this.sc;
      for (const n in this.objEls) {
        const o = ep.objects[n], e = this.objEls[n], [px, py] = P(o.x[i], o.y[i]);
        const deg = -o.yaw[i] * 180 / Math.PI;  // map is rotated: screen up = +x
        if (n === "lstick") {
          const flip = o.tilt[i] > 90 ? -1 : 1;
          const pts = [[-0.2, -0.09 * flip], [0.18, -0.09 * flip], [0.18, 0.11 * flip]];
          e.shape.setAttribute("d", pts.map(([x, y], k) => (k ? "L" : "M") + (-y * sc) + "," + (-x * sc)).join(" "));
        }
        e.shape.setAttribute("transform", `translate(${px},${py}) rotate(${deg})`);
        e.label.setAttribute("x", px + 8); e.label.setAttribute("y", py - 8 - (o.z[i] > 0.1 ? 0 : 0));
        e.trail.setAttribute("d", this.trails ? pathUpTo(o.x, o.y, i, P) : "");
        e.g.setAttribute("opacity", o.z[i] < -0.05 ? 0.35 : 1);
      }
      const [ex, ey] = P(ep.ee.x[i], ep.ee.y[i]);
      this.ee.setAttribute("transform", `translate(${ex},${ey})`);
      const [lo, hi] = ep.grip_range, closed = hi - lo > 0.05 && ep.grip[i] > (lo + hi) / 2;
      this.eeRing.setAttribute("fill", closed ? "#0b0b0b" : "#fcfcfb");
      this.eeText.textContent = `z ${ep.ee.z[i].toFixed(2)}`;
      this.eeTrail.setAttribute("d", this.trails ? pathUpTo(ep.ee.x, ep.ee.y, i, P) : "");
      if (this.playhead) for (const ph of this.playhead) { const x = ph.x(this.step); ph.line.setAttribute("x1", x); ph.line.setAttribute("x2", x); }
      $$(".events li", this.el).forEach((li) => { const st = +li.dataset.step; li.className = st < this.step - 2 ? "past" : Math.abs(st - this.step) <= 2 ? "now" : "future"; });
    }
    buildEvents() {
      const ep = this.ep;
      $(".events", this.el).innerHTML = ep.events.length ? ep.events.map((e) => `<li data-step="${e.step}"><span class="st">step ${e.step}</span><span><span style="color:${EV_COLOR[e.kind]}">●</span> ${esc(e.text)}</span></li>`).join("") : '<li class="muted">no events detected</li>';
      $$(".events li[data-step]", this.el).forEach((li) => (li.onclick = () => { this.pause(); this.seekStep(+li.dataset.step); }));
      $(".ticks", this.el).innerHTML = ep.events.map((e) => `<span class="tick" title="step ${e.step}: ${esc(e.text)}" data-step="${e.step}" style="left:${(100 * e.step / ep.steps).toFixed(2)}%;background:${EV_COLOR[e.kind]}"></span>`).join("");
      $$(".ticks .tick", this.el).forEach((t) => (t.onclick = () => { this.pause(); this.seekStep(+t.dataset.step); }));
    }
  }
  function pathUpTo(xs, ys, i, P) {
    let d = "";
    for (let k = 0; k <= i; k++) { const [px, py] = P(xs[k], ys[k]); d += (k ? "L" : "M") + px.toFixed(1) + "," + py.toFixed(1); }
    return d;
  }

  function renderPlayers() {
    const host = $("#players"); host.innerHTML = ""; host.className = "players" + (mode === "both" ? " split" : "");
    players = (mode === "both" ? ["codex", "claude"] : [mode]).map((a) => new Player(a, host));
    Player.focused = players[0];
    $("#goalbox").innerHTML = `<strong>${task}</strong> · goal: ${esc(GOALS[task][0])} · time limit ${GOALS[task][1]} steps (${GOALS[task][1] / 20} s)` +
      (mode === "both" ? ` · <button class="btn" id="playboth" style="padding:2px 9px;font-size:0.8rem">▶ play both from the start</button>` : "");
    const pb = $("#playboth");  // eslint-disable-line
    if (pb) pb.onclick = () => players.forEach((p) => { p.seekStep(0); p.video.play(); });
  }
  function videoExplorer() {
    const tb = $("#taskbtns");
    S.envs.forEach((e) => {
      const b = document.createElement("button");
      b.className = "btn" + (e === task ? " active" : ""); b.textContent = e.replace("-v", " v"); b.dataset.env = e;
      const r = S.results[e];
      b.title = `Codex ${r.codex[0]}/${r.codex[1]} · Claude ${r.claude[0]}/${r.claude[1]}`;
      b.onclick = () => { task = e; $$("#taskbtns .btn").forEach((x) => x.classList.toggle("active", x === b)); renderPlayers(); };
      tb.appendChild(b);
    });
    renderPlayers();
    document.addEventListener("keydown", (ev) => {
      if (/input|textarea/i.test(ev.target.tagName) && ev.target.type !== "range") return;
      const p = Player.focused; if (!p || !p.ep) return;
      const r = $("#videos").getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight) return;
      const map = { " ": "play", ArrowLeft: "back", ArrowRight: "fwd", "[": "prevev", "]": "nextev" };
      if (map[ev.key]) { ev.preventDefault(); (mode === "both" && ev.key === " " ? players : [p]).forEach((q) => q.action(map[ev.key])); }
    });
  }

  // ------------------------------------------------------------------ wire up
  tiles(); taskTable(); resultsTable();
  $("#envcode").href = GITHUB_URL + "/tree/main/RoboEnvs";
  videoExplorer(); iterations(); if ($("#logs")) logs(); codeBrowser();
  let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { players.forEach((p) => { if (p.ep) { p.buildMap(); p.draw(); } }); }, 200); });
})();
