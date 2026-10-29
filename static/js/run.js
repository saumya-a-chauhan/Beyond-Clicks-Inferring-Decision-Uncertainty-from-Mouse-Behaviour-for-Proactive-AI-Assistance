/* Participant runner: shows the steps of the plan one after another. */
const app = document.getElementById("app");
let S = null;          // {token, code, study, plan, step_index}
let INFO = null;       // study info (team, IRB, ...)
let leaving = false;   // warn before closing the tab during a task

window.addEventListener("beforeunload", e => { if (leaving) { e.preventDefault(); e.returnValue = ""; } });

async function boot() {
  const saved = Session.load();
  if (!saved) { location.href = "/"; return; }
  try {
    const [me, st] = await Promise.all([API.get("/api/me", saved.token), API.get("/api/status")]);
    S = Object.assign({ token: saved.token }, me);
    INFO = st.study_info;
  } catch (e) {
    app.innerHTML = `<div class="wrap"><div class="panel"><h2>Session not found</h2><p>${esc(e.message)}</p><a class="btn primary" href="/">Back to start</a></div></div>`;
    Session.clear(); return;
  }
  document.getElementById("pcode").textContent = S.code;
  render();
}

function step() { return S.plan[S.step_index]; }

function progress() {
  document.getElementById("prog").style.width = `${Math.round(100 * S.step_index / Math.max(1, S.plan.length - 1))}%`;
}

async function submit(data, extra) {
  const st = step();
  const body = Object.assign({ token: S.token, step_index: S.step_index, step_key: st.key, kind: st.kind, data: data || {} }, extra || {});
  const me = await API.post("/api/step", body);
  Object.assign(S, me);
  window.scrollTo(0, 0);
  render();
}

function page(html) {
  app.innerHTML = `<div class="wrap"><div class="panel">${html}</div></div>`;
  return app.querySelector(".panel");
}

function render() {
  progress();
  leaving = false;
  AiPanel.close();
  document.querySelectorAll(".ai-fab").forEach(n => n.remove());
  const st = step();
  if (!st) return;
  const fn = STEPS[st.kind];
  if (!fn) { page(`<p>Unknown step ${esc(st.kind)}</p>`); return; }
  fn(st);
}

/* ---------- reusable question widgets ---------- */
function likert(name, text, n, left, right) {
  const opts = Array.from({ length: n }, (_, i) => i + 1).map(v =>
    `<input type="radio" name="${name}" id="${name}_${v}" value="${v}"><label class="opt" for="${name}_${v}">${v}</label>`).join("");
  return `<div class="q" data-q="${name}"><div class="qtext">${esc(text)}</div>
    <div class="likert"><span class="anchor">${esc(left)}</span>${opts}<span class="anchor right">${esc(right)}</span></div></div>`;
}
function slider(name, text, left, right) {
  return `<div class="q slider-q" data-q="${name}"><div class="qtext">${esc(text)} <span class="val" id="${name}_v">(move the slider)</span></div>
    <input type="range" min="0" max="100" step="5" value="50" name="${name}" data-touched="0"
      oninput="this.dataset.touched=1;document.getElementById('${name}_v').textContent=this.value">
    <div class="ends"><span>${esc(left)}</span><span>${esc(right)}</span></div></div>`;
}
function collect(root, names) {
  const out = {}, missing = [];
  for (const n of names) {
    const r = root.querySelector(`input[name="${n}"]:checked`);
    const s = root.querySelector(`input[type=range][name="${n}"]`);
    if (r) out[n] = Number(r.value);
    else if (s && s.dataset.touched === "1") out[n] = Number(s.value);
    else missing.push(n);
  }
  root.querySelectorAll(".q").forEach(q => q.style.outline = missing.includes(q.dataset.q) ? "2px solid #f3b4ad" : "");
  return { out, missing };
}

/* ---------- static texts ---------- */
const PAGES = {
  pilot_intro: `<h2>How this session works</h2>
    <ol>
      <li>Two short warm-up tasks (about 3 minutes).</li>
      <li>Four shopping rounds: read a card about who the phone is for, then choose the best phone for them.</li>
      <li>You then watch a replay of your own mouse movement and mark the moments you felt unsure.</li>
      <li>A few short questions at the end.</li>
    </ol>
    <p>There is no AI help in this session. Take the time you need, as you would when really buying a phone.</p>
    <div class="notice info">Please keep this browser window the same size for the whole session, and use the mouse normally.</div>`,
  main_intro: `<h2>How this session works</h2>
    <ol>
      <li>Two short warm-up tasks and a practice round (about 6 minutes).</li>
      <li>Four shopping rounds. Each round has a card saying who the phone is for: choose the best phone for that person.</li>
      <li>In some rounds an AI assistant can help you. The screen before each round tells you what kind of help there is.</li>
      <li>Short questions after each round and at the end.</li>
    </ol>
    <p>Take the time you need, as you would when really buying a phone. There is a small bonus for each correct choice.</p>
    <div class="notice info">Please keep this browser window the same size for the whole session, and use the mouse normally.</div>`,
  tasks_intro: `<h2>Now the real rounds</h2>
    <p>Each round shows four phones. Click <b>View details</b> on a phone to see all its specs; you can open several phones at once. Read carefully: the numbers are not all written in the same units.</p>
    <p>Choose the phone that best fits the card, then click <b>Buy this phone</b>.</p>`,
  replay_intro: `<h2>Replay: when did you feel unsure?</h2>
    <p>You will now watch a replay of your mouse movement for each of the 4 rounds, at normal speed.</p>
    <div class="notice info"><b>Press and hold the SPACE bar</b> whenever you remember feeling unsure (for example torn between phones, or confused by a spec). <b>Release it</b> when that feeling ended.</div>
    <p style="margin-top:12px">There are no right or wrong answers. If you were never unsure in a round, just watch it to the end.</p>`,
  ai_check_intro: `<h2>One extra round, with an AI assistant</h2>
    <p>This round tests our AI assistant. While you shop, it may offer help in a small box at the bottom right. You can use it or close it.</p>`,
  pilot_end: `<h2>Thank you!</h2><p>You have finished the pilot session. Please tell the researcher you are done.</p>`,
  main_end: `<h2>Thank you!</h2><p>You have finished the study. Please tell the researcher you are done.</p>`,
};

/* ---------- step renderers ---------- */
const STEPS = {
  consent(st) {
    const dur = S.study === "pilot" ? INFO.duration_pilot : INFO.duration_main;
    const p = page(`
      <h2>${esc(INFO.title)}: information and consent</h2>
      <p><b>What is this study about?</b> We study how people choose between products online, and how an assistant could help at the right moment.</p>
      <p><b>What will I do?</b> Shop for phones on this website (fictional phones, no real money) and answer short questions. It takes ${esc(dur)}.</p>
      <p><b>What is recorded?</b> Your age and gender, your mouse movements, scrolling and clicks on this website, your choices and your answers. <b>No camera, no microphone, no name.</b> You are identified only by a code (${esc(S.code)}).</p>
      <p><b>Your rights.</b> Taking part is voluntary. You can stop at any time without giving a reason, and ask for your data to be deleted.</p>
      <p><b>Who are we?</b> ${esc(INFO.team)}. Supervisor: ${esc(INFO.supervisor)}. Contact: ${esc(INFO.contact)}. ${esc(INFO.irb)}.</p>
      <p><b>Reward.</b> ${esc(INFO.reward)}</p>
      <label class="check"><input type="checkbox" id="c1"> I have read this information and I am 18 years or older.</label>
      <label class="check"><input type="checkbox" id="c2"> I agree that my anonymous data can be used for research and teaching.</label>
      <div class="actions"><button id="no">I do not agree</button><button class="primary big" id="yes">I agree, start</button></div>`);
    p.querySelector("#yes").onclick = () => {
      if (!p.querySelector("#c1").checked || !p.querySelector("#c2").checked) { alert("Please tick both boxes to continue."); return; }
      submit({ agree: true });
    };
    p.querySelector("#no").onclick = async () => {
      if (!confirm("You will not take part. Is that right?")) return;
      await submit({ agree: false });
      Session.clear();
    };
  },

  demographics(st) {
    const genders = [["woman", "Woman"], ["man", "Man"], ["non-binary", "Non-binary"], ["self-describe", "Prefer to self-describe"], ["prefer-not", "Prefer not to say"]];
    const p = page(`
      <h2>About you</h2>
      <p class="muted">Two short questions. We do not ask for your name.</p>
      <div class="q"><label class="qtext" for="age">Your age (in years)</label>
        <input type="number" id="age" min="18" max="100" step="1" inputmode="numeric" style="max-width:160px"></div>
      <div class="q"><div class="qtext">Your gender</div>
        ${genders.map(([v, l]) => `<label class="check"><input type="radio" name="gender" value="${v}"> ${l}</label>`).join("")}
        <input type="text" id="gself" maxlength="40" placeholder="Please describe" style="max-width:280px;display:none;margin-top:6px"></div>
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    const self = p.querySelector("#gself");
    p.querySelectorAll('input[name="gender"]').forEach(r => r.onchange = () => { self.style.display = r.value === "self-describe" && r.checked ? "block" : "none"; });
    p.querySelector("#go").onclick = () => {
      const age = Number(p.querySelector("#age").value);
      const g = p.querySelector('input[name="gender"]:checked');
      if (!Number.isInteger(age) || age < 18 || age > 100) { alert("Please enter your age as a whole number (18 or older)."); return; }
      if (!g) { alert("Please choose an option for gender (you can choose 'Prefer not to say')."); return; }
      if (g.value === "self-describe" && !self.value.trim()) { alert("Please describe your gender, or choose another option."); return; }
      submit({ age, gender: g.value, gender_self: g.value === "self-describe" ? self.value.trim() : "" });
    };
  },

  device_check(st) {
    const types = new Set();
    const onPtr = e => types.add(e.pointerType);
    window.addEventListener("pointermove", onPtr);
    const w = window.innerWidth, h = window.innerHeight;
    const okW = w >= 1200;
    const p = page(`
      <h2>Quick setup check</h2>
      <ul>
        <li>Window size: <b>${w} × ${h}</b> ${okW ? '<span class="pill good">OK</span>' : '<span class="pill bad">too small</span>'}</li>
      </ul>
      ${okW ? "" : '<div class="notice">Please make the browser window larger (full screen is best: press F11), then reload this page.</div>'}
      <label class="check"><input type="checkbox" id="m"> I am using an external mouse (not a touchpad or touch screen).</label>
      <label class="check"><input type="checkbox" id="z"> Browser zoom is at 100% (press Ctrl + 0 to reset it).</label>
      <div class="actions"><button class="primary big" id="go" ${okW ? "" : "disabled"}>Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      if (!p.querySelector("#m").checked || !p.querySelector("#z").checked) { alert("Please confirm both points (ask the researcher for a mouse if needed)."); return; }
      window.removeEventListener("pointermove", onPtr);
      submit({ viewport_w: window.innerWidth, viewport_h: window.innerHeight, screen_w: screen.width, screen_h: screen.height,
               dpr: window.devicePixelRatio, ua: navigator.userAgent, pointer_types: [...types], mouse_confirmed: true, zoom_confirmed: true });
    };
  },

  instructions(st) {
    const p = page(`${PAGES[st.page] || ""}<div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => submit({});
  },

  condition_intro(st) {
    const p = page(`<div class="round-badge">Round ${st.round} of 4</div><h2>${esc(st.text)}</h2>
      <p class="muted">Read the card at the top, look at the phones, and buy the one that best fits the card.</p>
      <div class="actions"><button class="primary big" id="go">Start round ${st.round}</button></div>`);
    p.querySelector("#go").onclick = () => submit({});
  },

  async task(st) {
    app.innerHTML = `<div class="wide"><p class="muted">Loading<span class="dots"></span></p></div>`;
    const vp = { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio };
    const t = await API.post("/api/task/start", { token: S.token, task_key: st.task_key, viewport: vp });
    if (t.ended) { await submit({}); return; }
    const prompts = {
      baseline1: "Warm-up 1: find the phone that comes in Blue, and choose it.",
      baseline2: "Warm-up 2: find the phone with a 4 nm processor, and choose it.",
      practice: "Practice round: buy the phone with the most storage. Try the \"Ask AI\" button, and you will see an example AI pop-up.",
    };
    const header = st.task_kind === "baseline1" ? "Warm-up 1 of 2" : st.task_kind === "baseline2" ? "Warm-up 2 of 2"
      : st.task_kind === "practice" ? "Practice" : st.task_kind === "pilot_ai" ? "Extra round" : `Round ${st.position} of 4`;
    app.innerHTML = `<div class="wide" id="shoproot"></div>`;
    leaving = true;
    let logger = null;
    const ctx = { token: S.token, taskId: t.task_id, set: t.set, card_order: t.card_order, now: () => logger.now(), demo: t.condition === "DEMO" };
    logger = new Logger(t.task_id, S.token, t.time_offset_ms, t.next_seq, r => AiPanel.showPopup(r.popup, ctx));
    let done = false;
    Shop.render(document.getElementById("shoproot"), {
      set: t.set, card_order: t.card_order, header, prompt: prompts[st.task_kind],
      buyLabel: st.task_kind.startsWith("baseline") ? "Choose this phone" : "Buy this phone",
      onBuy: async pid => {
        if (done) return;
        done = true;
        const decision = logger.now();
        AiPanel.close();
        document.querySelectorAll(".ai-fab").forEach(n => n.remove());
        app.innerHTML = `<div class="wrap"><div class="panel"><p>Saving<span class="dots"></span></p></div></div>`;
        await logger.stop();
        await API.post(`/api/task/${t.task_id}/end`, { token: S.token, chosen: pid, decision_ms: decision });
        leaving = false;
        await submit({}, { task_key: st.task_key });
      },
    });
    logger.start();
    if (t.condition === "C2" || t.condition === "DEMO") AiPanel.askButton(ctx);
    if (t.condition === "DEMO") {
      const demo = () => {
        if (done) return;
        if (AiPanel.isOpen()) { setTimeout(demo, 3000); return; }   // wait until the Ask-AI panel is closed
        const ids = t.card_order;
        const name = id => t.set.phones.find(p => p.id === id).name;
        AiPanel.showPopup({ id: 0, predicted_type: "compare", pair: [{ id: ids[0], name: name(ids[0]) }, { id: ids[1], name: name(ids[1]) }],
                            spec: { key: "storage", label: t.set.spec_labels.storage } }, ctx);
      };
      setTimeout(demo, 12000);
    }
  },

  async switch(st) {
    const t = await API.get(`/api/task/by-key/${st.task_key}`, S.token);
    const phones = t.card_order.map(id => t.set.phones.find(p => p.id === id));
    const specCell = v => v.split(" · ").map(esc).join("<br>");
    const specRows = SPEC_ORDER.map(k => `<tr><th>${esc(t.set.spec_labels[k])}</th>${phones.map(p => `<td>${specCell(p.specs[k])}</td>`).join("")}</tr>`).join("");
    const detKeys = [...new Set(phones.flatMap(p => (p.details || []).map(d => d[0])))];
    const detRows = detKeys.map(k => `<tr><th>${esc(k)}</th>${phones.map(p => { const d = (p.details || []).find(x => x[0] === k); return `<td>${esc(d ? d[1] : "")}</td>`; }).join("")}</tr>`).join("")
      + `<tr><th>Review</th>${phones.map(p => `<td>${esc(p.review || "")}</td>`).join("")}</tr>`;
    const radios = phones.map(p => `<label class="check"><input type="radio" name="fin" value="${p.id}" ${p.id === t.chosen ? "checked" : ""}> ${esc(p.name)}${p.id === t.chosen ? " (your choice)" : ""}</label>`).join("");
    app.innerHTML = `<div class="wide"><div class="panel">
      <h2>Here are all four phones side by side</h2>
      <p class="muted">The card said: ${esc(t.set.card.persona)} ${esc(t.set.card.text)}</p>
      <div style="overflow:auto"><table class="cmp"><tr><th></th>${phones.map(p => `<th>${esc(p.name)}</th>`).join("")}</tr>${specRows}
        <tr class="cmp-sec"><th colspan="${phones.length + 1}">Lab test results and reviews</th></tr>${detRows}</table></div>
      <h3>Now that you see everything together, would you like to change your choice?</h3>
      ${radios}
      <div class="actions"><button class="primary big" id="go">Continue</button></div></div></div>`;
    app.querySelector("#go").onclick = async () => {
      const fin = app.querySelector("input[name=fin]:checked").value;
      await API.post(`/api/task/${t.task_id}/switch`, { token: S.token, final_choice: fin });
      submit({ final_choice: fin, switched: fin !== t.chosen }, { task_key: st.task_key });
    };
  },

  confidence(st) {
    const p = page(`<h2>One question about that round</h2>
      ${likert("confidence", "How confident are you that your first choice was the best phone for the card?", 7, "Not at all", "Completely")}
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      const { out, missing } = collect(p, ["confidence"]);
      if (missing.length) { alert("Please answer the question."); return; }
      submit(out, { task_key: st.task_key });
    };
  },

  post_task(st) {
    const ai = st.condition !== "C1";
    const tlx = [
      ["mental", "How mentally demanding was choosing?", "Very low", "Very high"],
      ["physical", "How physically demanding was it?", "Very low", "Very high"],
      ["temporal", "How hurried or rushed did you feel?", "Very low", "Very high"],
      ["performance", "How successful were you in doing what you were asked?", "Perfect", "Failure"],
      ["effort", "How hard did you have to work?", "Very low", "Very high"],
      ["frustration", "How insecure, discouraged, irritated or stressed were you?", "Very low", "Very high"],
    ];
    const names = ["confidence", ...tlx.map(x => x[0]), "valence", "arousal"];
    let aiQs = "";
    if (ai) {
      aiQs = `<h3 style="margin-top:28px">About the AI assistant in this round</h3>
        <p class="small muted">If you did not use it, answer about what you saw of it.</p>
        ${likert("helpful", "The AI help was useful.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("timing", "The AI help came at the right time.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("intrusive", "The AI help was annoying or got in the way.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("trust1", "I could trust the AI assistant.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("trust2", "The AI assistant was reliable.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("trust3", "I felt confident using the AI assistant's information.", 7, "Strongly disagree", "Strongly agree")}
        ${likert("trust4", "The AI assistant's information was accurate.", 7, "Strongly disagree", "Strongly agree")}`;
      names.push("helpful", "timing", "intrusive", "trust1", "trust2", "trust3", "trust4");
    }
    const p = page(`<div class="round-badge">${st.round <= 4 ? `After round ${st.round}` : "After the extra round"}</div>
      <h2>A few questions about that round</h2>
      ${likert("confidence", "How confident are you that your first choice was the best phone for the card?", 7, "Not at all", "Completely")}
      <h3 style="margin-top:28px">Workload</h3>
      ${tlx.map(x => slider(x[0], x[1], x[2], x[3])).join("")}
      <h3 style="margin-top:28px">How did you feel?</h3>
      ${likert("valence", "While choosing, I felt...", 9, "Very unpleasant", "Very pleasant")}
      ${likert("arousal", "While choosing, I felt...", 9, "Very calm", "Very excited / tense")}
      ${aiQs}
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      const { out, missing } = collect(p, names);
      if (missing.length) { alert(`Please answer all questions (${missing.length} left, marked in red). For sliders, move each slider at least once.`); return; }
      submit(Object.assign(out, { condition: st.condition }), { task_key: st.task_key });
    };
  },

  async replay(st) {
    const t = await API.get(`/api/task/by-key/${st.task_key}`, S.token);
    const R = await API.get(`/api/task/${t.task_id}/replay`, S.token);
    runReplay(st, R);
  },

  interview(st) {
    const p = page(`<h2>Last questions</h2>
      ${st.questions.map((q, i) => `<label>${esc(q)}</label><textarea id="q${i}"></textarea>`).join("")}
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      const d = {};
      st.questions.forEach((q, i) => d[`q${i + 1}`] = p.querySelector(`#q${i}`).value.trim());
      submit(d);
    };
  },

  sus(st) {
    const items = [
      "I think that I would like to use this AI help frequently.",
      "I found the AI help unnecessarily complex.",
      "I thought the AI help was easy to use.",
      "I think that I would need the support of a technical person to be able to use this AI help.",
      "I found the various functions of this AI help were well integrated.",
      "I thought there was too much inconsistency in this AI help.",
      "I would imagine that most people would learn to use this AI help very quickly.",
      "I found the AI help very cumbersome to use.",
      "I felt very confident using the AI help.",
      "I needed to learn a lot of things before I could get going with this AI help.",
    ];
    const p = page(`<h2>Think about round ${st.round}</h2>
      <p class="muted">Round ${st.round}: ${esc((S.plan.find(x => x.kind === "condition_intro" && x.round === st.round) || {}).text || "")}</p>
      ${items.map((q, i) => likert(`q${i + 1}`, q, 5, "Strongly disagree", "Strongly agree")).join("")}
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      const { out, missing } = collect(p, items.map((_, i) => `q${i + 1}`));
      if (missing.length) { alert("Please answer all questions."); return; }
      submit(Object.assign(out, { condition: st.condition, round: st.round }));
    };
  },

  ranking(st) {
    const rows = st.rounds.map(r => `<tr><td><b>Round ${r.round}</b><br><span class="small muted">${esc(r.text)}</span></td>
      <td><select data-c="${r.condition}"><option value="">Choose</option>${[1, 2, 3, 4].map(v => `<option value="${v}">${v}</option>`).join("")}</select></td></tr>`).join("");
    const p = page(`<h2>Which round did you like best?</h2>
      <p>Give each round a different number: <b>1 = best</b>, 4 = worst.</p>
      <table class="cmp">${rows}</table>
      <div class="actions"><button class="primary big" id="go">Continue</button></div>`);
    p.querySelector("#go").onclick = () => {
      const ranks = {};
      p.querySelectorAll("select").forEach(s => ranks[s.dataset.c] = Number(s.value));
      const vals = Object.values(ranks);
      if (vals.some(v => !v) || new Set(vals).size !== vals.length) { alert("Please give each round a different number from 1 to 4."); return; }
      submit({ ranks });
    };
  },

  debrief(st) {
    const p = page(`<h2>Thank you: what this study was really about</h2>
      <p>We are testing whether a computer can tell from <b>mouse movement</b> when someone is unsure while choosing, and offer help at that moment.</p>
      <p>In one of the rounds, the AI pop-ups appeared at <b>random times</b> instead of when our system thought you were unsure. We could not tell you before, because it would have changed how you used them. Comparing the two kinds of round tells us whether our system's timing really helps.</p>
      <p>The phones were fictional, and each round had one best answer based on the lab test results.</p>
      <p>If you are not comfortable with this, you can ask us to delete all your data now. Nothing happens to you either way.</p>
      <div class="actions"><button class="danger" id="del">Delete my data</button><button class="primary big" id="keep">Keep my data and finish</button></div>`);
    p.querySelector("#keep").onclick = () => submit({ keep: true });
    p.querySelector("#del").onclick = async () => {
      if (!confirm("Delete all your data from this study? This cannot be undone.")) return;
      await API.post("/api/delete-my-data", { token: S.token });
      Session.clear();
      app.innerHTML = `<div class="wrap"><div class="panel"><h2>Your data has been deleted</h2><p>Thank you for your time. Please tell the researcher.</p></div></div>`;
    };
  },

  end(st) {
    page(`${PAGES[st.page] || PAGES.main_end}<p class="muted">Your code: <b>${esc(S.code)}</b></p>
      <div class="actions"><a class="btn" href="/">Back to start page</a></div>`);
    document.getElementById("prog").style.width = "100%";
    Session.clear();
  },
};

/* ---------- replay labelling ---------- */
function runReplay(st, R) {
  const ev = R.events;
  const vw = (R.viewport && R.viewport.w) || window.innerWidth;
  const scale = window.innerWidth / vw;
  const dur = R.decision_ms || Math.max(1000, ...ev.m.map(e => e[0]));
  app.innerHTML = `<div class="wide replay-stage" id="stage"></div>`;
  const shop = Shop.render(document.getElementById("stage"), {
    set: R.set, card_order: R.card_order, header: `Replay of round ${st.position} of 4`, interactive: false });
  const intro = el(`<div class="modal-back"><div class="modal">
    <h2>Replay of round ${st.position}</h2>
    <p>The blue dot shows where your mouse was. <b>Hold SPACE</b> while you remember feeling unsure, <b>release</b> when it ended.</p>
    ${Math.abs(scale - 1) > 0.05 ? '<p class="notice">The window size changed since this round, so the dot may be slightly off.</p>' : ""}
    <div class="actions"><button class="primary big" id="startrp">Start replay</button></div></div></div>`);
  document.body.appendChild(intro);
  const bar = el(`<div class="replay-bar"><b>Round ${st.position}</b><div class="track"><div class="fill"></div></div>
    <span class="clock">0:00</span><span class="holding hidden">Marking: unsure</span></div>`);
  const dot = el(`<div class="replay-cursor hidden"></div>`);
  let intervals = [], holdStart = null, t0 = 0, raf = 0, playing = false;
  const fmt = ms => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;
  const now = () => performance.now() - t0;

  function addMark(a, b) {
    const m = el(`<div class="mark"></div>`);
    m.style.left = `${100 * a / dur}%`; m.style.width = `${Math.max(0.4, 100 * (b - a) / dur)}%`;
    bar.querySelector(".track").appendChild(m);
  }
  function keydown(e) {
    if (e.code !== "Space") return;
    e.preventDefault();
    if (!playing || e.repeat || holdStart !== null) return;
    holdStart = Math.min(now(), dur);
    bar.querySelector(".holding").classList.remove("hidden");
  }
  function keyup(e) {
    if (e.code !== "Space") return;
    e.preventDefault();
    if (holdStart === null) return;
    const end = Math.min(now(), dur);
    if (end - holdStart >= 150) { intervals.push([Math.round(holdStart), Math.round(end)]); addMark(holdStart, end); }
    holdStart = null;
    bar.querySelector(".holding").classList.add("hidden");
  }

  function play() {
    intervals = []; holdStart = null;
    bar.querySelectorAll(".mark").forEach(m => m.remove());
    document.body.appendChild(bar); document.body.appendChild(dot);
    dot.classList.remove("hidden");
    let im = 0, is = 0, ic = 0;
    window.scrollTo(0, 0);
    t0 = performance.now(); playing = true;
    const frame = () => {
      const t = now();
      while (im < ev.m.length && ev.m[im][0] <= t) {
        dot.style.left = `${ev.m[im][1] * scale}px`; dot.style.top = `${ev.m[im][2]}px`; im++;
      }
      while (is < ev.s.length && ev.s[is][0] <= t) { window.scrollTo(0, ev.s[is][1]); is++; }
      while (ic < ev.c.length && ev.c[ic][0] <= t) {
        const lab = ev.c[ic][4] || "";
        if (lab.startsWith("details:")) shop.toggleDetails(lab.slice(8));
        ic++;
      }
      bar.querySelector(".fill").style.width = `${Math.min(100, 100 * t / dur)}%`;
      bar.querySelector(".clock").textContent = `${fmt(t)} / ${fmt(dur)}`;
      if (t >= dur) { clearInterval(raf); finish(); }
    };
    raf = setInterval(frame, 25);   // a timer (not animation frames) keeps time even if the tab is briefly hidden
  }
  function finish() {
    playing = false;
    if (holdStart !== null) { intervals.push([Math.round(holdStart), Math.round(dur)]); addMark(holdStart, dur); holdStart = null; }
    bar.querySelector(".holding").classList.add("hidden");
    const done = el(`<div class="modal-back"><div class="modal">
      <h2>End of round ${st.position} replay</h2>
      <p>You marked <b>${intervals.length}</b> moment${intervals.length === 1 ? "" : "s"} of feeling unsure.</p>
      <div class="actions"><button id="again">Watch again and re-mark</button><button class="primary big" id="save">Save and continue</button></div></div></div>`);
    document.body.appendChild(done);
    done.querySelector("#again").onclick = () => { done.remove(); play(); };
    done.querySelector("#save").onclick = async () => {
      done.remove(); cleanup();
      await API.post(`/api/task/${R.task_id}/labels`, { token: S.token, intervals, replay_speed: 1 });
      submit({ n_marked: intervals.length }, { task_key: st.task_key });
    };
  }
  function cleanup() {
    clearInterval(raf);
    window.removeEventListener("keydown", keydown); window.removeEventListener("keyup", keyup);
    bar.remove(); dot.remove();
  }
  window.addEventListener("keydown", keydown);
  window.addEventListener("keyup", keyup);
  intro.querySelector("#startrp").onclick = () => { intro.remove(); play(); };
}

boot();
