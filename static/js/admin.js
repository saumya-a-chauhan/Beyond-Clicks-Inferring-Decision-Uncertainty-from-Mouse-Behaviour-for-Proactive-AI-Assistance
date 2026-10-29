/* Researcher dashboard. */
const view = document.getElementById("view");
let charts = [];
const pct = v => v == null ? "–" : `${(100 * v).toFixed(0)}%`;
const num = (v, d = 2) => v == null ? "–" : Number(v).toFixed(d);
const COND_NAMES = { C1: "No AI", C2: "Ask AI", C3: "Smart pop-up", C4: "Random pop-up" };

function clearCharts() { charts.forEach(c => c.destroy()); charts = []; }
function chart(canvas, cfg) { const c = new Chart(canvas, cfg); charts.push(c); return c; }
function box(title, inner, note) {
  return `<div class="chart-box"><h3>${esc(title)}</h3>${note ? `<p class="small muted">${note}</p>` : ""}${inner}</div>`;
}
function table(cols, rows, rowClass) {
  return `<div style="overflow:auto"><table class="data"><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr>
    ${rows.map(r => `<tr class="${rowClass ? rowClass(r) : ""}">${cols.map(c => `<td>${c[1](r)}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

async function downloadFile(url, fallbackName, btn, out) {
  const label = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Preparing…"; }
  if (out) out.innerHTML = "";
  try {
    const r = await fetch(url, { credentials: "same-origin" });
    if (r.status === 401) throw new Error("Your login has expired. Reload the page and log in again.");
    if (!r.ok) {
      let msg = `Download failed (${r.status})`;
      try { const d = await r.json(); if (d.detail) msg = d.detail; } catch (e) { /* not JSON */ }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const cd = r.headers.get("content-disposition") || "";
    const m = cd.match(/filename="?([^";]+)"?/);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = m ? m[1] : fallbackName;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
    if (out) out.innerHTML = `<p class="small muted">Saved <b>${esc(a.download)}</b> to your Downloads folder.</p>`;
  } catch (e) {
    if (out) out.innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; else alert(e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

async function boot() {
  try { await API.get("/api/admin/overview"); showDash(); }
  catch (e) { document.getElementById("login").classList.remove("hidden"); }
}
document.getElementById("dologin").onclick = async () => {
  try {
    await API.post("/api/admin/login", { password: document.getElementById("pw").value });
    document.getElementById("login").classList.add("hidden");
    showDash();
  } catch (e) { document.getElementById("loginerr").textContent = e.message; }
};
document.getElementById("pw").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("dologin").click(); });
document.getElementById("logout").onclick = async () => { await API.post("/api/admin/logout"); location.reload(); };

function showDash() {
  document.getElementById("dash").classList.remove("hidden");
  document.getElementById("logout").classList.remove("hidden");
  document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("active", x === b));
    TABS[b.dataset.tab]();
  });
  TABS.overview();
}

const TABS = {
  async overview() {
    clearCharts();
    const o = await API.get("/api/admin/overview");
    const fz = o.frozen || {};
    const kp = Object.entries(o.counts).map(([k, v]) => `<div class="kpi"><div class="n">${v.completed}</div><div class="l">${esc(k)} completed<br>${v.started} in progress, ${v.declined} declined, ${v.excluded} excluded</div></div>`).join("");
    view.innerHTML = `
      <div class="panel">
        <h2>Study status</h2>
        <div class="kpis">${kp || '<div class="kpi"><div class="n">0</div><div class="l">participants yet</div></div>'}</div>
        ${fz.frozen
          ? `<div class="notice good"><b>Settings frozen</b> on ${esc(fz.frozen_at)} with threshold <b>${fz.threshold}</b>. The main study is open.${fz.include_simulated ? " <b>Warning: the analysis behind this freeze included simulated data.</b>" : ""}</div>`
          : `<div class="notice">Settings are <b>not frozen</b>. The main study is locked. Finish the pilot, then use <b>Pilot analysis &amp; freeze</b>.</div>`}
        <p class="small muted" style="margin-top:12px">Laptop: <b>${esc(o.site_name)}</b> · Data file: <code>${esc(o.db_file || o.database)}</code> · Latest backup: ${o.backups && o.backups.length ? esc(o.backups[0].time.replace("T", " ")) : "none yet"}<br>Database: ${esc(o.database)} · Gemini key: ${o.llm.gemini_key ? "set" : "missing"} (${esc(o.llm.gemini_model)}) · Groq key: ${o.llm.groq_key ? "set" : "missing"} (${esc(o.llm.groq_model)}) · Next pilot participant gets AI check: <b>${o.pilot_ai_check_next ? "yes" : "no"}</b></p>
      </div>
      <div class="panel"><h3>Audit log (latest 50)</h3>
        ${table([["Time", a => esc(a.ts.slice(0, 19))], ["Action", a => esc(a.action)], ["Detail", a => `<code class="small">${esc(JSON.stringify(a.detail).slice(0, 220))}</code>`]], o.audit)}
      </div>`;
  },

  async participants() {
    clearCharts();
    const ps = await API.get("/api/admin/participants");
    view.innerHTML = `<div class="panel"><h2>Participants (${ps.length})</h2>
      ${table([
        ["Code", p => `<b>${esc(p.code)}</b>${p.simulated ? ' <span class="pill warn">sim</span>' : ""}${p.excluded ? ' <span class="pill bad">excluded</span>' : ""}`],
        ["Study", p => esc(p.study) + (p.pilot_ai_check ? " + AI check" : "")],
        ["Age / gender", p => p.age == null ? '<span class="muted">–</span>' : `${esc(p.age)} / ${esc(p.gender || "–")}`],
        ["Status", p => esc(p.status)],
        ["Step", p => `${esc(p.step)}<br><span class="small muted">${esc(p.current)}</span>`],
        ["Order", p => p.study === "main" ? esc((p.condition_order || []).map(c => COND_NAMES[c]).join(" → ")) + `<br><span class="small muted">${esc((p.set_order || []).join(" "))}</span>` : `<span class="small muted">${esc((p.set_order || []).join(" "))}</span>`],
        ["Tasks", p => p.tasks.filter(t => /^t\d|ai/.test(t.key)).map(t => `${t.key}:${t.correct == null ? "…" : t.correct ? "✓" : "✗"} ${t.time_s ? t.time_s.toFixed(0) + "s" : ""}`).join("<br>")],
        ["Labels", p => p.study === "pilot" ? p.labels : ""],
        ["Device", p => p.device ? `<span class="small">${p.device.viewport_w}×${p.device.viewport_h}, dpr ${p.device.dpr}</span>` : ""],
        ["Created", p => `<span class="small">${esc(p.created_at.slice(0, 16))}</span>`],
        ["", p => `<button class="small" data-ex="${p.id}" data-v="${p.excluded ? 0 : 1}">${p.excluded ? "Include" : "Exclude"}</button>
                   <button class="small danger" data-del="${p.id}" data-code="${esc(p.code)}">Delete</button>`],
      ], ps)}</div>`;
    view.querySelectorAll("[data-ex]").forEach(b => b.onclick = async () => {
      const note = b.dataset.v === "1" ? prompt("Reason for excluding (kept in the audit log):") : "";
      if (b.dataset.v === "1" && !note) return;
      await API.post(`/api/admin/participants/${b.dataset.ex}/exclude`, { excluded: b.dataset.v === "1", note });
      TABS.participants();
    });
    view.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
      if (prompt(`Type ${b.dataset.code} to permanently delete this participant's data:`) !== b.dataset.code) return;
      await API.del(`/api/admin/participants/${b.dataset.del}`);
      TABS.participants();
    });
  },

  async pilot() {
    clearCharts();
    const o = await API.get("/api/admin/overview");
    view.innerHTML = `<div class="panel">
      <h2>Pilot analysis</h2>
      <p>Computes each pilot person's baseline, simulates the live trigger rules on every pilot shopping task, compares the pop-ups with the replay labels, and picks the threshold with the pre-registered rule: <b>highest recall among thresholds with precision ≥ 70% and ≤ 1 false alarm per task</b> (ties: higher threshold).</p>
      <label class="check"><input type="checkbox" id="sim"> Include simulated participants (for testing only)</label>
      <div class="actions" style="justify-content:flex-start"><button class="primary" id="run">Run pilot analysis</button></div>
      </div><div id="pres"></div>`;
    view.querySelector("#run").onclick = async () => {
      const out = view.querySelector("#pres");
      out.innerHTML = `<div class="panel"><p>Running<span class="dots"></span> (this can take a minute)</p></div>`;
      try { renderPilot(await API.post("/api/admin/pilot-analysis", { include_simulated: view.querySelector("#sim").checked }), o, out); }
      catch (e) { out.innerHTML = `<div class="panel notice">${esc(e.message)}</div>`; }
    };
    if (o.frozen && o.frozen.frozen) {
      view.querySelector("#pres").innerHTML = `<div class="panel"><div class="notice good">Frozen on ${esc(o.frozen.frozen_at)}: threshold ${o.frozen.threshold}.</div>${unfreezeForm()}</div>`;
      bindUnfreeze();
    }
  },

  async main() {
    clearCharts();
    view.innerHTML = `<div class="panel"><h2>Main study results</h2>
      <p class="muted">Descriptive results and the key comparisons. Mixed-effects models and the full set of figures come from <code>analysis/make_figures.py</code> (see docs).</p>
      <label class="check"><input type="checkbox" id="sim"> Include simulated participants (for testing only)</label>
      <div class="actions" style="justify-content:flex-start"><button class="primary" id="run">Compute results</button></div></div><div id="mres"></div>`;
    view.querySelector("#run").onclick = async () => {
      const out = view.querySelector("#mres");
      out.innerHTML = `<div class="panel"><p>Computing<span class="dots"></span></p></div>`;
      try { renderMain(await API.post("/api/admin/main-results", { include_simulated: view.querySelector("#sim").checked }), out); }
      catch (e) { out.innerHTML = `<div class="panel notice">${esc(e.message)}</div>`; }
    };
  },

  async data() {
    clearCharts();
    view.innerHTML = `
      <div class="panel"><h2>Results (Excel)</h2>
        <p>One row per participant and shopping round: a <b>Pilot</b> sheet, a <b>Main</b> sheet, and an <b>About</b> sheet explaining every column.
        Each row also has the round's mouse numbers (distance, resting time, switches between phones, longest rests, scroll flips, time on each phone, hesitation score).
        It is built from the current data each time, so every participant so far is included.</p>
        <label class="check"><input type="checkbox" id="dl-mouse"> Include all mouse-movement data: every cursor point, scroll and click (<b>Mouse raw</b>), the detector's check every 0.5 s with the 5 signs and the score (<b>Mouse signs</b>), and the replay's unsure marks. Large file, takes longer.</label>
        <label class="check"><input type="checkbox" id="dl-sim"> Include simulated (test) participants</label>
        <div class="actions" style="justify-content:flex-start">
          <button class="primary" id="dl-xlsx">Download Excel (Pilot + Main)</button></div>
        <div id="dl-out"></div></div>
      <div class="panel"><h2>Study data (CSV)</h2>
        <p><b>Download CSV</b> saves everything recorded in this study in one file: every participant and round, the mouse movement, the answers, the pop-ups, the replay labels and the settings (including the freeze).</p>
        <p><b>Upload CSV</b> loads such a file, for example the one from the laptop that ran the experiment. It <b>overrides all study data on this laptop</b>: after loading, every page of this dashboard uses only the data from the file
        (participants, the pilot analysis and freeze, the main-study results, the Excel download) and so does <code>analysis/make_figures.py</code>.</p>
        <p class="small muted">Upload the CSV exactly as it was downloaded; do not open and save it in Excel first. A backup is saved automatically before loading (Backups &amp; tools).</p>
        <div class="actions" style="justify-content:flex-start;flex-wrap:wrap">
          <button class="primary" id="csv-dl">Download CSV</button>
          <input type="file" id="csv-file" accept=".csv" style="max-width:320px">
          <button id="csv-up">Upload CSV</button></div>
        <div id="csv-out"></div></div>
      <div class="panel"><h2>View data</h2>
        <div class="actions" style="justify-content:flex-start;flex-wrap:wrap;gap:8px">
          <button id="v-pilot" class="primary">Pilot</button><button id="v-main">Main</button>
          <label class="check" style="margin:0"><input type="checkbox" id="v-all"> Show all columns</label></div>
        <div id="v-loaded"></div><div id="v-sum"></div><div id="v-table"></div></div>`;
    const simQ = () => `include_sim=${view.querySelector("#dl-sim").checked ? 1 : 0}`;
    let study = "pilot", sheet = null;
    const KEY = ["site", "participant", "age", "gender", "status", "round", "condition_name", "phone_set", "decision_time_s", "correct", "rank", "switched", "popups_shown", "unsure_yes", "confidence"];
    const cell = v => v === true ? "✓" : v === false ? "✗" : v == null ? "" : esc(v);
    const med = a => {
      const s = a.filter(x => x != null).sort((x, y) => x - y);
      if (!s.length) return null;
      return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
    };
    const render = () => {
      const rows = sheet.rows;
      const cols = view.querySelector("#v-all").checked ? sheet.columns : KEY;
      const people = new Set(rows.map(r => `${r.site}|${r.participant}`)).size;
      const byC = {};
      rows.forEach(r => { const c = r.condition_name || r.condition; (byC[c] = byC[c] || []).push(r); });
      const ld = sheet.loaded;
      view.querySelector("#v-loaded").innerHTML = ld
        ? `<p class="small muted">Data from <b>${esc(ld.filename)}</b> (laptop ${esc(ld.from_site || "?")}, downloaded ${esc((ld.exported_at || "").replace("T", " "))}), loaded ${esc((ld.loaded_at || "").replace("T", " "))}.</p>` : "";
      const persons = {};
      rows.forEach(r => { persons[`${r.site}|${r.participant}`] = r; });
      const ages = Object.values(persons).map(r => r.age).filter(a => a != null);
      const mean = ages.length ? ages.reduce((a, b) => a + b, 0) / ages.length : null;
      const sd = ages.length > 1 ? Math.sqrt(ages.reduce((a, b) => a + (b - mean) ** 2, 0) / (ages.length - 1)) : null;
      const gcount = {};
      Object.values(persons).forEach(r => { const g = r.gender || "not given"; gcount[g] = (gcount[g] || 0) + 1; });
      const demoLine = ages.length
        ? `<p class="small">Age: mean <b>${num(mean, 1)}</b>${sd != null ? ` (SD ${num(sd, 1)})` : ""}, range ${Math.min(...ages)}–${Math.max(...ages)} · Gender: ${Object.entries(gcount).map(([g, n]) => `${esc(g)} ${n}`).join(", ")}</p>` : "";
      view.querySelector("#v-sum").innerHTML = `<p><b>${rows.length}</b> rows from <b>${people}</b> participants.</p>` + demoLine + (rows.length ? table([
        ["Condition", c => esc(c)], ["Rounds", c => byC[c].length],
        ["% correct (first choice)", c => { const v = byC[c].filter(r => r.correct != null); return v.length ? `${Math.round(100 * v.filter(r => r.correct).length / v.length)}%` : "–"; }],
        ["Median time (s)", c => num(med(byC[c].map(r => r.decision_time_s)), 1)],
        ["Pop-ups", c => byC[c].reduce((a, r) => a + (r.popups_shown || 0), 0)],
        ["'Unsure' yes", c => byC[c].reduce((a, r) => a + (r.unsure_yes || 0), 0)]], Object.keys(byC).sort()) : "");
      view.querySelector("#v-table").innerHTML = rows.length
        ? `<div style="overflow:auto;max-height:520px"><table class="data"><tr>${cols.map(c => `<th title="${esc(sheet.meanings[c] || "")}">${esc(c)}</th>`).join("")}</tr>
           ${rows.map(r => `<tr>${cols.map(c => `<td>${cell(r[c])}</td>`).join("")}</tr>`).join("")}</table></div>`
        : '<p class="muted">No rows yet.</p>';
    };
    const load = async () => {
      sheet = await API.get(`/api/admin/sheet?study=${study}&${simQ()}`);
      view.querySelector("#v-pilot").classList.toggle("primary", study === "pilot");
      view.querySelector("#v-main").classList.toggle("primary", study === "main");
      render();
    };
    view.querySelector("#dl-sim").onchange = load;
    view.querySelector("#v-pilot").onclick = () => { study = "pilot"; load(); };
    view.querySelector("#v-main").onclick = () => { study = "main"; load(); };
    view.querySelector("#v-all").onchange = render;
    view.querySelector("#dl-xlsx").onclick = e => downloadFile(`/api/admin/export.xlsx?${simQ()}&include_mouse=${view.querySelector("#dl-mouse").checked ? 1 : 0}`, "beyond_clicks_results.xlsx", e.target, view.querySelector("#dl-out"));
    view.querySelector("#csv-dl").onclick = e => downloadFile("/api/admin/data.csv", "beyond_clicks_study_data.csv", e.target, view.querySelector("#csv-out"));
    view.querySelector("#csv-up").onclick = async e => {
      const f = view.querySelector("#csv-file").files[0];
      const out = view.querySelector("#csv-out");
      if (!f) { out.innerHTML = '<p class="notice">Choose the CSV file first.</p>'; return; }
      if (!confirm(`Upload "${f.name}"?\n\nAll study data on this laptop will be OVERRIDDEN by the data in this file (participants, results, pilot analysis, freeze). A backup of the current data is saved first.`)) return;
      const btn = e.target; btn.disabled = true;
      out.innerHTML = '<p class="muted">Loading… (large files can take a minute)</p>';
      try {
        const r = await fetch(`/api/admin/data.csv?filename=${encodeURIComponent(f.name)}`, { method: "POST", body: f, credentials: "same-origin" });
        const ct = r.headers.get("content-type") || "";
        const d = ct.includes("json") ? await r.json() : { detail: await r.text() };
        if (!r.ok) throw new Error(d.detail || `Upload failed (${r.status})`);
        const c = d.counts || {};
        out.innerHTML = `<div class="notice good"><b>Data overridden.</b> All study data on this laptop has been replaced by <b>${esc(d.filename)}</b> (from laptop <b>${esc(d.from_site || "?")}</b>):
          ${c.participants || 0} participants, ${c.tasks || 0} rounds and tasks, ${c.event_batches || 0} blocks of mouse data, ${c.responses || 0} answers.<br>
          From now on every page uses only this data: Participants, Pilot analysis &amp; freeze, Main study results, the Excel download and <code>analysis/make_figures.py</code>.
          The previous data is kept as a backup (Backups &amp; tools).</div>`;
        view.querySelector("#csv-file").value = "";
        load();
      } catch (err) { out.innerHTML = `<div class="notice bad">${esc(err.message)}</div>`; }
      btn.disabled = false;
    };
    load();
  },

  async settings() {
    clearCharts();
    const o = await API.get("/api/admin/overview");
    const si = o.study_info;
    const fields = [["title", "Study title"], ["team", "Team (names)"], ["contact", "Contact emails"], ["supervisor", "Supervisor"],
      ["irb", "Ethics approval (number or 'pending')"], ["reward", "Reward text"], ["duration_pilot", "Pilot duration"], ["duration_main", "Main duration"]];
    const frozen = o.frozen && o.frozen.frozen;
    view.innerHTML = `
      <div class="panel"><h2>Laptop name</h2>
        <p class="small muted">Written in the <b>site</b> column of every downloaded sheet, so data from different laptops can be combined without mixing up participants (two laptops both have a P01). Give each laptop a different name before its first participant, e.g. "Riya-laptop".</p>
        <label>Name of this laptop</label><input type="text" id="site" value="${esc(o.site_name || "")}">
        <div class="actions"><button class="primary" id="savesite">Save</button></div></div>
      <div class="panel"><h2>Consent page information</h2>
        ${fields.map(([k, l]) => `<label>${l}</label><input type="text" data-si="${k}" value="${esc(si[k] || "")}">`).join("")}
        <div class="actions"><button class="primary" id="savesi">Save</button></div></div>
      <div class="panel"><h2>Pilot AI check</h2>
        <p>Turn this on for the <b>last 3 pilot participants</b>: they get one extra round with the AI pop-up (provisional threshold) to check the LLM answers, speed and pop-up design.</p>
        <label class="check"><input type="checkbox" id="aic" ${o.pilot_ai_check_next ? "checked" : ""}> Give new pilot participants the extra AI round</label>
        <div class="actions"><button class="primary" id="saveaic">Save</button></div></div>
      <div class="panel"><h2>Detector settings ${frozen ? '<span class="pill good">frozen</span>' : '<span class="pill warn">provisional</span>'}</h2>
        <p class="small muted">Every value is explained in docs/VALUES.md. ${frozen ? "Frozen settings cannot be edited." : "Only change these for a documented reason (changes are logged)."}</p>
        <textarea id="det" style="min-height:320px;font-family:monospace;font-size:.85rem" ${frozen ? "disabled" : ""}>${esc(JSON.stringify(o.detector, null, 2))}</textarea>
        <div class="actions"><button class="primary" id="savedet" ${frozen ? "disabled" : ""}>Save detector settings</button></div></div>`;
    view.querySelector("#savesi").onclick = async () => {
      const d = {}; view.querySelectorAll("[data-si]").forEach(i => d[i.dataset.si] = i.value);
      await API.post("/api/admin/settings", { study_info: d }); alert("Saved");
    };
    view.querySelector("#savesite").onclick = async () => { await API.post("/api/admin/settings", { site_name: view.querySelector("#site").value }); alert("Saved"); };
    view.querySelector("#saveaic").onclick = async () => { await API.post("/api/admin/settings", { pilot_ai_check_next: view.querySelector("#aic").checked }); alert("Saved"); };
    view.querySelector("#savedet").onclick = async () => {
      let d; try { d = JSON.parse(view.querySelector("#det").value); } catch (e) { alert("Not valid JSON"); return; }
      try { await API.post("/api/admin/settings", { detector: d }); alert("Saved"); } catch (e) { alert(e.message); }
    };
  },

  async tools() {
    clearCharts();
    view.innerHTML = `
      <div class="panel"><h2>Backups</h2>
        <p>All data lives in one file, <code>hti_study.db</code>. A complete copy is saved automatically in the <code>backups</code> folder next to it:
        when the site starts, every 15 minutes while data changes, after every participant finishes, at freeze, and before any delete or upload. The newest 40 are kept.</p>
        <div class="actions" style="justify-content:flex-start"><button id="bknow">Make a backup now</button>
          <button class="primary" id="bkdl">Download full backup (.db)</button></div>
        <div id="bkout"></div><p class="small muted" id="bkfolder"></p><div id="bklist"></div></div>
      <div class="panel"><h2>Download all raw data</h2>
        <p>A ZIP with CSV files: participants, tasks, responses, pop-ups, AI requests, replay labels, raw cursor events per task, detector ticks per task, settings and the audit log. Column meanings: docs/DATA_DICTIONARY.md.</p>
        <button class="primary" id="zipdl">Download ZIP</button><div id="zipout"></div></div>
      <div class="panel"><h2>Check the AI providers</h2>
        <p>Sends a tiny test request to Gemini and Groq.</p>
        <button id="llm">Run check</button><pre class="json" id="llmout" style="margin-top:12px">–</pre></div>
      <div class="panel"><h2>Simulated data</h2>
        <p>Delete every participant created by <code>scripts/simulate.py</code>.</p>
        <button class="danger" id="delsim">Delete simulated participants</button></div>
      <div class="panel"><h2>Clear all study data</h2>
        <p>Deletes <b>every</b> participant and everything recorded (rounds, mouse data, answers, pop-ups, replay labels), the pilot analysis and the <b>freeze</b>, so the study starts again from P01.
        The consent-page information and the laptop name are kept. A backup of the current data is saved first (listed above), so it can be restored.</p>
        <p class="small muted">Use it once before the real pilot to remove test runs. Never use it during the study.</p>
        <button class="danger" id="clearall">Clear all study data</button><div id="clearout"></div></div>`;
    const loadBk = async () => {
      const b = await API.get("/api/admin/backups");
      view.querySelector("#bkfolder").textContent = b.folder ? `Folder: ${b.folder}` : "";
      view.querySelector("#bklist").innerHTML = b.backups.length
        ? table([["Backup", x => `<code class="small">${esc(x.name)}</code>`], ["Time", x => esc(x.time.replace("T", " "))], ["Size", x => `${x.size_kb} KB`]], b.backups.slice(0, 10))
        : '<p class="muted">No backups yet.</p>';
    };
    loadBk();
    view.querySelector("#bkdl").onclick = e => downloadFile("/api/admin/backup.db", "hti_study_full_backup.db", e.target, view.querySelector("#bkout"));
    view.querySelector("#zipdl").onclick = e => downloadFile("/api/admin/export.zip", "hti_study_export.zip", e.target, view.querySelector("#zipout"));
    view.querySelector("#bknow").onclick = async () => { try { await API.post("/api/admin/backups"); loadBk(); } catch (e) { alert(e.message); } };
    view.querySelector("#llm").onclick = async () => {
      view.querySelector("#llmout").textContent = "Checking…";
      view.querySelector("#llmout").textContent = JSON.stringify(await API.post("/api/admin/llm-test"), null, 2);
    };
    view.querySelector("#clearall").onclick = async () => {
      const typed = prompt("This deletes ALL participants and all recorded data on this laptop (a backup is saved first).\n\nType DELETE ALL to confirm:");
      if (typed === null) return;
      const out = view.querySelector("#clearout");
      try {
        const r = await API.post("/api/admin/clear-all", { confirm: typed.trim() });
        out.innerHTML = `<div class="notice good">All study data cleared: ${r.deleted} participant(s) deleted. Backup saved first: <code>${esc(r.backup || "")}</code>. The next participant will be P01.</div>`;
        loadBk();
      } catch (e) { out.innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
    };
    view.querySelector("#delsim").onclick = async () => {
      if (!confirm("Delete all simulated participants?")) return;
      const r = await API.post("/api/admin/delete-simulated"); alert(`Deleted ${r.deleted}`);
    };
  },
};

function unfreezeForm() {
  return `<details style="margin-top:12px"><summary>Unfreeze (only for a serious, documented reason)</summary>
    <p class="small muted">Unfreezing is recorded permanently in the audit log and should be reported.</p>
    <label>Reason</label><input type="text" id="ufr"><div class="actions"><button class="danger" id="uf">Unfreeze</button></div></details>`;
}
function bindUnfreeze() {
  const b = document.getElementById("uf");
  if (b) b.onclick = async () => {
    try { await API.post("/api/admin/unfreeze", { reason: document.getElementById("ufr").value }); alert("Unfrozen (logged)."); TABS.pilot(); }
    catch (e) { alert(e.message); }
  };
}

function renderPilot(r, o, out) {
  clearCharts();
  if (!r.sweeps) { out.innerHTML = `<div class="panel notice">${esc(r.message || "No data")}</div>`; return; }
  const avg = r.sweeps.avg, chosen = r.chosen.avg, loo = r.loo.avg;
  const frozen = o.frozen && o.frozen.frozen;
  out.innerHTML = `
    <div class="panel">
      <div class="kpis">
        <div class="kpi"><div class="n">${r.n_people}</div><div class="l">pilot people used</div></div>
        <div class="kpi"><div class="n">${r.n_tasks}</div><div class="l">shopping tasks with labels</div></div>
        <div class="kpi"><div class="n">${chosen == null ? "none" : chosen}</div><div class="l">threshold picked by the rule</div></div>
        <div class="kpi"><div class="n">${pct(loo.precision_mean)} / ${pct(loo.recall_mean)}</div><div class="l">leave-one-out precision / recall (unseen people)</div></div>
        <div class="kpi"><div class="n">${pct(r.chance_precision)}</div><div class="l">chance level (share of time marked unsure)</div></div>
      </div>
      ${chosen == null ? '<div class="notice">No threshold passed the rule. Protocol: make ONE stated change (drop the weakest sign or relax precision to 60%) and report it.</div>' : ""}
    </div>
    ${box("Main detector (average of 5 signs): threshold sweep", `<canvas id="pr"></canvas>` + table([
      ["Threshold", x => x.threshold], ["Pop-ups", x => x.triggers], ["Hits", x => x.hits], ["Precision", x => pct(x.precision)],
      ["Unsure moments caught", x => `${x.caught} of ${x.labels}`], ["Recall", x => pct(x.recall)], ["False alarms per task", x => num(x.fa_per_task)]],
      avg, x => x.threshold === chosen ? "chosen" : ""), "Blue row = picked by the rule. Dashed lines: 70% precision requirement and chance level.")}
    ${box("Comparison detectors (reported only, not chosen from the pilot)", table([
      ["Detector", v => ({ avg: "Average (main)", max: "Maximum z", B: "Back-and-forth only", I: "Pausing only" })[v]],
      ["Threshold by rule", v => r.chosen[v] == null ? "none" : r.chosen[v]],
      ["Leave-one-out precision", v => `${pct(r.loo[v].precision_mean)} ± ${pct(r.loo[v].precision_sd)}`],
      ["Leave-one-out recall", v => `${pct(r.loo[v].recall_mean)} ± ${pct(r.loo[v].recall_sd)}`]], ["avg", "max", "B", "I"]))}
    ${box("Leave-one-person-out (main detector)", table([
      ["Held-out person", x => esc(x.person)], ["Threshold chosen on the others", x => x.threshold == null ? "none" : x.threshold],
      ["Precision on this person", x => pct(x.precision)], ["Recall on this person", x => pct(x.recall)], ["False alarms per task", x => num(x.fa_per_task)]], loo.rows))}
    <div class="grid2">
      ${box("Phone sets: % correct with no AI (target 40–60%)", `<canvas id="sets"></canvas>` + table([
        ["Set", x => x.set], ["n", x => x.n], ["% correct", x => `${pct(x.correct_rate)} ${x.correct_rate >= 0.4 && x.correct_rate <= 0.6 ? '<span class="pill good">in range</span>' : '<span class="pill warn">adjust</span>'}`],
        ["Median time", x => `${num(x.median_time_s, 0)} s`]], r.sets))}
      ${box("Timing checks", `<ul>
        <li>Median 'unsure' moment: <b>${num(r.label_durations.median_s, 1)} s</b> (n = ${r.label_durations.n}). Detection needs about <b>${num(r.detection_delay_s, 1)} s</b> ${r.label_durations.median_s > r.detection_delay_s ? '<span class="pill good">fast enough</span>' : '<span class="pill warn">too slow</span>'}</li>
        <li>Unsure moments per task (mean): <b>${num(r.labels_per_task_mean, 1)}</b> (max pop-ups per task is ${o.detector.max_popups})</li>
        <li>Best label lag (score vs labels): <b>${num(r.label_lag.best_lag_s, 1)} s</b> (match margin is 3 s)</li>
        <li>Pop-ups per minute at the chosen threshold (used for the random condition): <b>${num(r.c4_rate_per_min, 2)}</b></li></ul>
        <canvas id="lag"></canvas>`)}
    </div>
    <div class="grid2">
      ${box("Cursor speed histogram (check of the 50 px/s resting cut-off)", `<canvas id="speed"></canvas>`, "The dip between 'still' and 'moving' should be near the dashed line.")}
      ${box("Minimum spreads from pilot baselines", table([["Sign", s => s], ["Minimum spread (median of pilot spreads)", s => num(r.min_spread[s], 3)],
        ["People below it", s => `${pct(r.floor_use[s])} ${r.floor_use[s] > 0.3 ? '<span class="pill warn">less reliable (&gt;30%)</span>' : ""}`]], ["B", "F", "I", "W", "S"]))
        + box("Pilot AI check", `<pre class="json">${esc(JSON.stringify(r.ai_check, null, 2))}</pre>`)}
    </div>
    <div class="panel"><h2>Freeze the settings</h2>
      ${frozen ? `<div class="notice good">Already frozen on ${esc(o.frozen.frozen_at)} (threshold ${o.frozen.threshold}).</div>${unfreezeForm()}` : `
      <p>Freezing saves the threshold <b>${chosen == null ? "(none)" : chosen}</b>, the minimum spreads and the random pop-up rate shown above, locks them, and <b>opens the main study</b>. ${r.n_people < 8 ? `<span class="pill warn">only ${r.n_people} pilot people</span>` : ""}</p>
      <label>Threshold to freeze</label><input type="text" id="fthr" value="${chosen == null ? "" : chosen}">
      <label>Note (required if you change the rule's threshold)</label><input type="text" id="fnote">
      <div class="actions"><button class="primary big" id="freeze">Freeze settings and open the main study</button></div>`}
    </div>`;
  if (frozen) bindUnfreeze();
  else out.querySelector("#freeze").onclick = async () => {
    const v = out.querySelector("#fthr").value.trim();
    if (!confirm("Freeze the settings now? The main study will open, and these values will be locked.")) return;
    try {
      const s = await API.post("/api/admin/freeze", { threshold: v === "" ? null : Number(v), note: out.querySelector("#fnote").value });
      alert(`Frozen with threshold ${s.threshold}. The main study is now open.`); TABS.overview();
    } catch (e) { alert(e.message); }
  };
  const thr = avg.map(x => x.threshold);
  chart(out.querySelector("#pr"), { type: "line", data: { labels: thr, datasets: [
    { label: "Precision", data: avg.map(x => x.precision == null ? null : 100 * x.precision), borderColor: "#3557d6", tension: .2 },
    { label: "Recall", data: avg.map(x => x.recall == null ? null : 100 * x.recall), borderColor: "#e07b28", tension: .2 },
    { label: "70% precision rule", data: thr.map(() => 70), borderColor: "#999", borderDash: [6, 4], pointRadius: 0 },
    { label: "Chance", data: thr.map(() => r.chance_precision == null ? null : 100 * r.chance_precision), borderColor: "#c0392b", borderDash: [2, 4], pointRadius: 0 },
  ] }, options: { scales: { y: { min: 0, max: 100, title: { display: true, text: "%" } }, x: { title: { display: true, text: "Threshold" } } } } });
  chart(out.querySelector("#sets"), { type: "bar", data: { labels: r.sets.map(s => s.set), datasets: [{ label: "% correct (no AI)", data: r.sets.map(s => 100 * s.correct_rate), backgroundColor: "#7a9cff" }] },
    options: { scales: { y: { min: 0, max: 100 } } } });
  chart(out.querySelector("#lag"), { type: "line", data: { labels: r.label_lag.lags_s, datasets: [{ label: "Correlation of score with labels", data: r.label_lag.corr, borderColor: "#3557d6" }] },
    options: { scales: { x: { title: { display: true, text: "Lag (s); positive = label comes after the score" } } } } });
  const edges = r.speed_hist.log10_edges;
  chart(out.querySelector("#speed"), { type: "bar", data: { labels: edges.slice(0, -1).map(e => `${Math.round(10 ** e)}`),
    datasets: [{ label: "Segments", data: r.speed_hist.counts, backgroundColor: edges.slice(0, -1).map(e => e < r.speed_hist.rest_cutoff_log10 ? "#9db0f5" : "#c5c9d6") }] },
    options: { scales: { x: { title: { display: true, text: "Cursor speed (px/s, log scale bins); blue = counted as resting" } }, y: { beginAtZero: true } } } });
}

function renderMain(r, out) {
  clearCharts();
  if (!r.conditions) { out.innerHTML = `<div class="panel notice">${esc(r.message || "No data")}</div>`; return; }
  const C = r.conditions, pop = r.popups;
  const pd = r.paired_vs_C1;
  const fmtCI = x => x ? `${num(x.mean)} [${num(x.lo)}, ${num(x.hi)}]` : "–";
  out.innerHTML = `
    <div class="panel"><div class="kpis">
      <div class="kpi"><div class="n">${r.n_people}</div><div class="l">participants</div></div>
      <div class="kpi"><div class="n">${r.n_tasks_done}</div><div class="l">rounds completed</div></div>
      <div class="kpi"><div class="n">${pct(pop.C3.yes_rate)} vs ${pct(pop.C4.yes_rate)}</div><div class="l">"unsure just now?" yes: smart vs random pop-up</div></div>
      <div class="kpi"><div class="n">${num(r.auc_at_random_moments.avg.auc)}</div><div class="l">main detector AUC at random moments (0.5 = chance)</div></div>
    </div></div>
    ${box("Claim 1: does the detector catch real hesitation?", `<canvas id="yes"></canvas>` + table([
      ["Condition", c => COND_NAMES[c]], ["Pop-ups", c => pop[c].n_popups], ["Answered", c => pop[c].answered],
      ["Yes, I was unsure", c => `${pct(pop[c].yes_rate)} [${pct(pop[c].yes_lo)}, ${pct(pop[c].yes_hi)}]`],
      ["Accepted help", c => pct(pop[c].accept_rate)], ["Clicked the predicted help type", c => pct(pop[c].type_match_rate)], ["Pop-ups per round", c => num(pop[c].per_task, 1)]], ["C3", "C4"])
      + table([["Detector", v => ({ avg: "Average (main)", max: "Maximum z", B: "Back-and-forth only", I: "Pausing only" })[v]],
        ["AUC at random C4 moments", v => num(r.auc_at_random_moments[v].auc)], ["n yes / no", v => `${r.auc_at_random_moments[v].n_yes} / ${r.auc_at_random_moments[v].n_no}`]], ["avg", "max", "B", "I"]),
      "95% Wilson intervals. The AUC test uses the unbiased random-moment answers (protocol section 8).")}
    ${box("Claims 2 and 3: speed and decision quality per condition", `<div class="grid2"><div class="chart-cell"><canvas id="time"></canvas></div><div class="chart-cell"><canvas id="corr"></canvas></div></div>` + table([
      ["Condition", c => COND_NAMES[c.condition]], ["n", c => c.n], ["Median time (IQR)", c => `${num(c.median_time_s, 0)} s (${num(c.q1_time_s, 0)}–${num(c.q3_time_s, 0)})`],
      ["Mean rank (1 best, main quality)", c => num(c.mean_rank)], ["% correct [95% CI]", c => `${pct(c.correct)} [${pct(c.correct_lo)}, ${pct(c.correct_hi)}]`],
      ["Switched after full table", c => pct(c.switch_rate)], ["Chose dominated phone", c => pct(c.dominated_rate)]], C)
      + table([["Compared with No AI", c => COND_NAMES[c]], ["n pairs", c => pd[c].n], ["Median time ratio", c => num(pd[c].time_ratio_median)],
        ["Rank difference [95% CI]", c => fmtCI(pd[c].rank_diff)], ["Correct difference [95% CI]", c => fmtCI(pd[c].correct_diff)]], ["C2", "C3", "C4"]),
      "Time ratio below 1 = faster than No AI. Rank difference below 0 = better choices than No AI.")}
    ${box("Claim 6: hesitation score around the pop-up", `<canvas id="aligned"></canvas>` + table([["Group", g => esc(g)], ["n", g => r.before_after[g].n],
      ["Score 10 s before", g => num(r.before_after[g].before)], ["Score 10 s after", g => num(r.before_after[g].after)]], Object.keys(r.before_after)))}
    ${box("Questionnaires (means per condition)", table([["Condition", c => COND_NAMES[c]],
      ...["confidence", "tlx", "valence", "arousal", "helpful", "timing", "intrusive", "trust"].map(k => [k, c => num((r.questionnaires[c] || {})[k])]),
      ["SUS", c => r.sus[c] ? `${num(r.sus[c].mean, 1)} (n=${r.sus[c].n})` : "–"], ["Preference rank (1 best)", c => num(r.preference_rank[c])]], ["C1", "C2", "C3", "C4"]))}
    <div class="grid2">
      ${box("Order check (counterbalancing)", table([["Position", x => x.position], ["n", x => x.n], ["% correct", x => pct(x.correct_rate)], ["Median time", x => `${num(x.median_time_s, 0)} s`]], r.order_check))}
      ${box("AI usage", `<p>Ask AI (C2): ${r.ask_ai.requests} requests in ${r.ask_ai.tasks_with_use} of ${r.ask_ai.c2_tasks} rounds.</p><pre class="json">${esc(JSON.stringify(r.llm, null, 2))}</pre>`)}
    </div>`;
  chart(out.querySelector("#yes"), { type: "bar", data: { labels: ["Smart pop-up (C3)", "Random pop-up (C4)"],
    datasets: [{ label: "% 'yes, I was unsure'", data: [pop.C3.yes_rate, pop.C4.yes_rate].map(v => v == null ? null : 100 * v), backgroundColor: ["#3557d6", "#c5c9d6"] }] },
    options: { scales: { y: { min: 0, max: 100 } } } });
  chart(out.querySelector("#time"), { type: "bar", data: { labels: C.map(c => COND_NAMES[c.condition]),
    datasets: [{ label: "Median decision time (s)", data: C.map(c => c.median_time_s), backgroundColor: "#7a9cff" }] }, options: { scales: { y: { beginAtZero: true } } } });
  chart(out.querySelector("#corr"), { type: "bar", data: { labels: C.map(c => COND_NAMES[c.condition]),
    datasets: [{ label: "% correct", data: C.map(c => c.correct == null ? null : 100 * c.correct), backgroundColor: "#3d8b5f" }] }, options: { scales: { y: { min: 0, max: 100 } } } });
  const al = r.aligned;
  const xs = [...new Set([...(al.C3 || []), ...(al.C4 || [])].map(p => p[0]))].sort((a, b) => a - b);
  const ser = arr => xs.map(x => { const f = (arr || []).find(p => p[0] === x); return f ? f[1] : null; });
  chart(out.querySelector("#aligned"), { type: "line", data: { labels: xs, datasets: [
    { label: "Smart pop-up (C3)", data: ser(al.C3), borderColor: "#3557d6" }, { label: "Random pop-up (C4)", data: ser(al.C4), borderColor: "#999" }] },
    options: { scales: { x: { title: { display: true, text: "Seconds from pop-up" } }, y: { beginAtZero: true, title: { display: true, text: "Hesitation score" } } } } });
}

boot();
