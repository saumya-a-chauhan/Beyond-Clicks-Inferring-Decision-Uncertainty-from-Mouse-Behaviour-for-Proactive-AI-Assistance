/* The phone shop: rendering, cursor logging, AI pop-up and Ask-AI panel. */
const COLOURS = {
  Black: "#2b2f38", Green: "#3d8b5f", Blue: "#3466c2", White: "#d4d8e2", Silver: "#aab1be", Grey: "#737a87",
  Red: "#c0392b", Purple: "#7b4fc4", Orange: "#e07b28", Gold: "#c9a24b", Pink: "#e58fb2",
};
const SPEC_ORDER = ["price", "battery", "chip", "display", "camera", "storage"];

const Shop = {
  /* Render the shop into `root`. opts: {set, card_order, header, prompt, buyLabel, interactive, onBuy} */
  render(root, opts) {
    const set = opts.set;
    const byId = Object.fromEntries(set.phones.map(p => [p.id, p]));
    const order = opts.card_order.map(id => byId[id]);
    const card = set.card;
    const reqText = opts.prompt
      ? `<div class="what">${esc(opts.prompt)}</div>`
      : `<div class="who">${esc(card.persona)}</div><div class="what">${esc(card.text)}</div>`;
    const cards = order.map(p => {
      const c1 = COLOURS[p.colours[0]] || "#555", c2 = COLOURS[p.colours[1]] || c1;
      const specs = SPEC_ORDER.map(k => `
        <div class="spec" data-zone="spec:${p.id}:${k}">
          <span class="k">${esc(set.spec_labels[k])}</span><span class="v">${esc(p.specs[k])}</span>
        </div>`).join("");
      return `
      <div class="card" data-zone="card:${p.id}" data-phone="${p.id}">
        <div class="phone-img" style="--c1:${c1};--c2:${c2}"></div>
        <h3>${esc(p.name)}</h3>
        <div class="colours">Colours: ${esc(p.colours.join(", "))}</div>
        ${specs}
        <div class="btns">
          <button class="details-btn" data-log="details:${p.id}" data-phone="${p.id}">Details &amp; review</button>
          <button class="primary buy-btn" data-log="buy:${p.id}" data-phone="${p.id}">${esc(opts.buyLabel || "Buy this phone")}</button>
        </div>
      </div>`;
    }).join("");
    root.innerHTML = `
      <div class="shop" data-zone="empty">
        <div class="reqcard" data-zone="read:card">
          ${opts.header ? `<div class="round-badge">${esc(opts.header)}</div>` : ""}
          ${reqText}
        </div>
        <div class="cards">${cards}</div>
        <div class="details" data-zone="read:details" id="details">
          <p class="muted">Click <b>Details &amp; review</b> on a phone to see lab test results and a short review here.</p>
        </div>
      </div>`;
    const details = root.querySelector("#details");
    const showDetails = pid => {
      const p = byId[pid];
      root.querySelectorAll(".card").forEach(c => c.classList.toggle("selected", c.dataset.phone === pid));
      details.innerHTML = `<h3>${esc(p.name)}: details and review</h3>
        <table>${(p.details || []).map(d => `<tr><td>${esc(d[0])}</td><td><b>${esc(d[1])}</b></td></tr>`).join("")}</table>
        <p>${esc(p.review)}</p>`;
    };
    root.querySelectorAll(".details-btn").forEach(b => b.addEventListener("click", () => showDetails(b.dataset.phone)));
    if (opts.interactive !== false) {
      root.querySelectorAll(".buy-btn").forEach(b => b.addEventListener("click", () => {
        const p = byId[b.dataset.phone];
        Modal.confirm(`${opts.buyLabel || "Buy"}: ${p.name}?`, "You cannot change it in this step.",
          opts.buyLabel ? "Yes, choose it" : "Yes, buy it", "Go back").then(ok => { if (ok) opts.onBuy(p.id); });
      }));
    }
    return { showDetails, byId };
  },
};

/* ---------- cursor logger ---------- */
class Logger {
  constructor(taskId, token, offset, seq, onResponse) {
    this.taskId = taskId; this.token = token; this.offset = offset || 0; this.seq = seq || 0;
    this.onResponse = onResponse; this.t0 = performance.now();
    this.m = []; this.s = []; this.c = []; this.queue = []; this.sending = false;
    this.lastMove = -1; this.lastX = 0; this.lastY = 0; this.stopped = false;
    this._move = e => this.move(e); this._scroll = () => this.scroll(); this._click = e => this.click(e);
  }
  now() { return Math.round(performance.now() - this.t0 + this.offset); }
  zone(target) { const z = target && target.closest ? target.closest("[data-zone]") : null; return z ? z.dataset.zone : "empty"; }
  start() {
    document.addEventListener("mousemove", this._move, { passive: true, capture: true });
    window.addEventListener("scroll", this._scroll, { passive: true });
    document.addEventListener("click", this._click, { capture: true });
    this.timer = setInterval(() => this.flush(), 500);
  }
  move(e) {
    const t = this.now();
    if (t - this.lastMove < 16) return;
    this.lastMove = t; this.lastX = Math.round(e.clientX); this.lastY = Math.round(e.clientY);
    this.m.push([t, this.lastX, this.lastY, this.zone(e.target)]);
  }
  scroll() {
    const t = this.now();
    const z = this.zone(document.elementFromPoint(this.lastX, this.lastY));
    this.s.push([t, Math.round(window.scrollY), z]);
  }
  click(e) {
    const lab = e.target.closest ? e.target.closest("[data-log]") : null;
    this.c.push([this.now(), Math.round(e.clientX), Math.round(e.clientY), this.zone(e.target), lab ? lab.dataset.log : ""]);
  }
  flush(final) {
    if (this.m.length || this.s.length || this.c.length || !final) {
      this.queue.push({ token: this.token, seq: this.seq++, now: this.now(), m: this.m, s: this.s, c: this.c });
      this.m = []; this.s = []; this.c = [];
    }
    return this.drain();
  }
  async drain() {
    if (this.sending) return;
    this.sending = true;
    try {
      while (this.queue.length) {
        const b = this.queue[0];
        try {
          const r = await API.post(`/api/task/${this.taskId}/events`, b);
          this.queue.shift();
          if (r && r.popup && !this.stopped && this.onResponse) this.onResponse(r);
        } catch (e) {
          if (e.status && e.status < 500 && e.status !== 408 && e.status !== 429) { this.queue.shift(); continue; }
          await new Promise(res => setTimeout(res, 1000));   // network problem: retry
          if (this.stopped && this.queue.length > 20) break;
        }
      }
    } finally { this.sending = false; }
  }
  async stop() {
    this.stopped = true;
    clearInterval(this.timer);
    document.removeEventListener("mousemove", this._move, { capture: true });
    window.removeEventListener("scroll", this._scroll);
    document.removeEventListener("click", this._click, { capture: true });
    this.flush(true);
    for (let i = 0; i < 40 && (this.queue.length || this.sending); i++) {
      await new Promise(res => setTimeout(res, 150));
      if (!this.sending && this.queue.length) this.drain();
    }
  }
}

/* ---------- modal ---------- */
const Modal = {
  confirm(title, text, yes, no) {
    return new Promise(resolve => {
      const back = el(`<div class="modal-back" data-zone="ui:modal"><div class="modal">
        <h2>${esc(title)}</h2><p class="muted">${esc(text || "")}</p>
        <div class="actions"><button class="no">${esc(no || "Cancel")}</button><button class="primary yes">${esc(yes || "OK")}</button></div>
      </div></div>`);
      document.body.appendChild(back);
      back.querySelector(".yes").onclick = () => { back.remove(); resolve(true); };
      back.querySelector(".no").onclick = () => { back.remove(); resolve(false); };
    });
  },
};

/* ---------- AI help panels ---------- */
function formatAnswer(text) { return esc(text); }

const AiPanel = {
  node: null,
  gen: 0,          // increases every time the panel content changes; late answers check it
  isOpen() { return !!this.node; },
  close() { this.gen++; if (this.node) { this.node.remove(); this.node = null; } },
  _mount(html) {
    this.close();
    this.node = el(`<div class="ai-panel" data-zone="ui:ai">${html}</div>`);
    document.body.appendChild(this.node);
    return this.node;
  },
  /* Pop-up from the detector (C3) or random timer (C4). ctx: {token, now(), set, demo} */
  showPopup(pop, ctx) {
    const n = this._mount(`
      <div class="ai-head">AI assistant</div>
      <p><b>Quick question: were you unsure just now?</b></p>
      <div class="row"><button class="primary" data-a="yes">Yes</button><button data-a="no">No</button></div>`);
    n.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
      if (!ctx.demo) API.post(`/api/popup/${pop.id}/unsure`, { token: ctx.token, t: ctx.now(), answer: b.dataset.a }).catch(() => {});
      this._offer(pop, ctx);
    });
  },
  _offer(pop, ctx) {
    const names = (pop.pair || []).map(p => p.name);
    const cmp = `<button data-c="compare">Compare ${esc(names[0] || "two phones")} and ${esc(names[1] || "")}</button>`;
    const exp = `<button data-c="explain">Explain "${esc(pop.spec ? pop.spec.label : "a spec")}"</button>`;
    const gen = `<button data-c="general">Give me a quick overview</button>`;
    const first = pop.predicted_type === "compare" ? [cmp, exp, gen] : pop.predicted_type === "explain" ? [exp, cmp, gen] : [gen, cmp, exp];
    const lead = pop.predicted_type === "compare" ? `Torn between ${esc(names[0])} and ${esc(names[1])}? I can help.`
      : pop.predicted_type === "explain" ? `Want "${esc(pop.spec.label)}" explained?` : "Need help deciding?";
    const n = this._mount(`
      <div class="ai-head">AI assistant <button class="x" data-c="dismiss" title="Close">No thanks</button></div>
      <p>${lead}</p>
      <div class="opts">${first.join("")}</div>`);
    n.querySelectorAll("[data-c]").forEach(b => b.onclick = async () => {
      const choice = b.dataset.c;
      if (choice === "dismiss") {
        if (!ctx.demo) API.post(`/api/popup/${pop.id}/choice`, { token: ctx.token, t: ctx.now(), choice }).catch(() => {});
        this.close(); return;
      }
      const g = this._loading();
      try {
        let r;
        const pair = (pop.pair || []).map(p => p.id);
        if (ctx.demo) {
          r = await API.post(`/api/task/${ctx.taskId}/ask`, { token: ctx.token, t: ctx.now(), mode: choice, pair, spec: pop.spec && pop.spec.key });
        } else {
          r = await API.post(`/api/popup/${pop.id}/choice`, { token: ctx.token, t: ctx.now(), choice, pair, spec: pop.spec && pop.spec.key });
        }
        if (g !== this.gen) return;
        this._answer(r.text, () => { if (!ctx.demo) API.post(`/api/popup/${pop.id}/closed`, { token: ctx.token, t: ctx.now() }).catch(() => {}); });
      } catch (e) { if (g === this.gen) this._answer("Sorry, the assistant could not answer right now.", () => {}); }
    });
  },
  _loading() { this._mount(`<div class="ai-head">AI assistant</div><p class="muted">Thinking<span class="dots"></span></p>`); return this.gen; },
  _answer(text, onClose) {
    const n = this._mount(`<div class="ai-head">AI assistant <button class="x">Close</button></div><div class="answer">${formatAnswer(text)}</div>`);
    n.querySelector(".x").onclick = () => { onClose(); this.close(); };
  },

  /* "Ask AI" button for condition C2 (and the practice round). */
  askButton(ctx) {
    const fab = el(`<button class="primary ai-fab" data-zone="ui:ai" data-log="ask_open">Ask AI</button>`);
    document.body.appendChild(fab);
    fab.onclick = () => this.askForm(ctx);
    return fab;
  },
  askForm(ctx) {
    const set = ctx.set;
    const opts = ctx.card_order.map(id => set.phones.find(p => p.id === id)).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
    const specs = SPEC_ORDER.map(k => `<option value="${k}">${esc(set.spec_labels[k])}</option>`).join("");
    const n = this._mount(`
      <div class="ai-head">Ask the AI assistant <button class="x">Close</button></div>
      <label>Compare two phones</label>
      <div class="row"><select class="p1" style="flex:1">${opts}</select><select class="p2" style="flex:1">${opts}</select></div>
      <div class="row" style="margin-top:6px"><button data-m="compare">Compare</button></div>
      <label>Explain a spec</label>
      <div class="row"><select class="sp" style="flex:1">${specs}</select><button data-m="explain">Explain</button></div>
      <label>Or ask your own question</label>
      <textarea class="qq" placeholder="For example: which phone lasts longest on battery?"></textarea>
      <div class="row" style="margin-top:6px"><button data-m="ask">Ask</button></div>`);
    n.querySelector(".p2").selectedIndex = 1;
    n.querySelector(".x").onclick = () => this.close();
    n.querySelectorAll("[data-m]").forEach(b => b.onclick = async () => {
      const mode = b.dataset.m;
      const body = { token: ctx.token, t: ctx.now(), mode };
      if (mode === "compare") body.pair = [n.querySelector(".p1").value, n.querySelector(".p2").value];
      if (mode === "explain") body.spec = n.querySelector(".sp").value;
      if (mode === "ask") { body.question = n.querySelector(".qq").value.trim(); if (!body.question) return; }
      if (mode === "compare" && body.pair[0] === body.pair[1]) { alert("Please pick two different phones."); return; }
      const g = this._loading();
      try {
        const r = await API.post(`/api/task/${ctx.taskId}/ask`, body);
        if (g !== this.gen) return;
        this._answer(r.text, () => {});
        const x = this.node.querySelector(".x");
        const again = el(`<button>Ask something else</button>`);
        again.onclick = () => this.askForm(ctx);
        x.parentElement.after(again);
      } catch (e) { if (g === this.gen) this._answer("Sorry, the assistant could not answer right now.", () => {}); }
    });
  },
};
