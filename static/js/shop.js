/* The phone shop: rendering, cursor logging, AI pop-up and Ask-AI panel. */
const COLOURS = {
  Black: "#2b2f38", Green: "#3d8b5f", Blue: "#3466c2", White: "#e6e9f0", Silver: "#b4bac6", Grey: "#737a87",
  Red: "#c0392b", Purple: "#7b4fc4", Orange: "#e07b28", Gold: "#c9a24b", Pink: "#e58fb2", Lavender: "#b6a4e3",
  Teal: "#2a8c8c",
};
const SPEC_ORDER = ["price", "battery", "chip", "display", "camera", "storage"];

/* Mix a #rrggbb colour towards white (f > 0) or black (f < 0). */
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16), t = f < 0 ? 0 : 255, a = Math.abs(f);
  const mix = v => Math.round(v + (t - v) * a);
  return `rgb(${mix(n >> 16)},${mix((n >> 8) & 255)},${mix(n & 255)})`;
}

/* Product picture: the front (screen) and the back (colour and camera) of the phone. Every phone has its own design
   (p.look in phone_sets.json: camera layout, body shape, finish, front-camera cutout, wallpaper). */
const SHAPES = { round: [64, 128, 14], boxy: [66, 124, 5], slim: [56, 134, 12], curved: [62, 130, 20] };

function phoneSvg(p) {
  const L = p.look || {};
  const c = COLOURS[p.colours[0]] || "#555", c2 = COLOURS[p.colours[1]] || c, id = `ph-${p.id}`;
  const [bw, bh, r] = SHAPES[L.shape] || SHAPES.round;
  const bx = 136 - bw, by = 142 - bh, fx = 22, fy = by - 6;
  const light = parseInt(c.slice(1, 3), 16) + parseInt(c.slice(3, 5), 16) + parseInt(c.slice(5, 7), 16) > 520;
  const mod = shade(c, -0.3), rim = "rgba(255,255,255,.35)";
  const lens = (x, y, rr) => `<circle cx="${x}" cy="${y}" r="${rr}" fill="#15171c" stroke="#5a5f6b" stroke-width="1.2"/>
    <circle cx="${x}" cy="${y}" r="${rr * 0.45}" fill="#26324d"/><circle cx="${x - rr * 0.3}" cy="${y - rr * 0.3}" r="${rr * 0.18}" fill="#cfd8ff" opacity=".8"/>`;
  const flash = (x, y) => `<circle cx="${x}" cy="${y}" r="2.6" fill="#fff4d2" stroke="#d8c48a" stroke-width=".6"/>`;
  const x = bx, y = by;
  const cams = {
    square: `<rect x="${x + 7}" y="${y + 8}" width="30" height="30" rx="8" fill="${mod}" stroke="${rim}"/>${lens(x + 15, y + 16, 5)}${lens(x + 29, y + 16, 5)}${lens(x + 15, y + 30, 5)}${flash(x + 29, y + 30)}`,
    pill: `<rect x="${x + 8}" y="${y + 7}" width="15" height="42" rx="7.5" fill="${mod}" stroke="${rim}"/>${lens(x + 15.5, y + 15, 5)}${lens(x + 15.5, y + 28, 5)}${lens(x + 15.5, y + 41, 5)}${flash(x + 29, y + 12)}`,
    ring: `<circle cx="${x + bw - 26}" cy="${y + 26}" r="17" fill="${mod}" stroke="${rim}"/>${lens(x + bw - 33, y + 20, 5.5)}${lens(x + bw - 19, y + 32, 5.5)}${lens(x + bw - 33, y + 33, 3.5)}${flash(x + bw - 19, y + 19)}`,
    bar: `<rect x="${x + 5}" y="${y + 9}" width="${bw - 10}" height="18" rx="9" fill="${mod}" stroke="${rim}"/>${lens(x + 15, y + 18, 5.5)}${lens(x + 29, y + 18, 5.5)}${flash(x + bw - 14, y + 18)}`,
    duo: `<circle cx="${x + 16}" cy="${y + 17}" r="9" fill="none" stroke="${shade(c, -0.4)}" stroke-width="2.5"/>${lens(x + 16, y + 17, 6.5)}
      <circle cx="${x + 16}" cy="${y + 39}" r="9" fill="none" stroke="${shade(c, -0.4)}" stroke-width="2.5"/>${lens(x + 16, y + 39, 6.5)}${flash(x + 31, y + 14)}`,
    center: `<circle cx="${x + bw / 2}" cy="${y + 30}" r="19" fill="${mod}" stroke="${rim}" stroke-width="1.5"/>${lens(x + bw / 2 - 7, y + 23, 4.8)}${lens(x + bw / 2 + 7, y + 23, 4.8)}${lens(x + bw / 2 - 7, y + 37, 4.8)}${lens(x + bw / 2 + 7, y + 37, 4.8)}${flash(x + bw / 2, y + 55)}`,
    strip: `<rect x="${x + 5}" y="${y + 6}" width="19" height="60" rx="9.5" fill="rgba(10,12,18,.55)" stroke="${rim}"/>${lens(x + 14.5, y + 17, 6)}${lens(x + 14.5, y + 33, 6)}${lens(x + 14.5, y + 49, 4)}${flash(x + 14.5, y + 60)}`,
    island: `<rect x="${x + 5}" y="${y + 6}" width="${bw - 10}" height="34" rx="11" fill="rgba(10,12,18,.42)" stroke="${rim}"/>${lens(x + 19, y + 23, 8.5)}${lens(x + 37, y + 16, 5)}${lens(x + 37, y + 30, 5)}${flash(x + bw - 15, y + 15)}`,
  };
  const finishes = {
    gloss: `<path d="M${x + 4} ${y + 6} Q${x + bw * 0.8} ${y + 4} ${x + bw - 4} ${y + bh * 0.45} L${x + bw - 4} ${y + 10} Z" fill="rgba(255,255,255,.22)"/>`,
    matte: "",
    twotone: `<rect x="${x}" y="${y}" width="${bw}" height="${bh * 0.36}" fill="${shade(c2 === c ? c : c2, -0.15)}" opacity=".9"/>`,
    leather: `<rect x="${x + 4}" y="${y + 4}" width="${bw - 8}" height="${bh - 8}" rx="${Math.max(2, r - 4)}" fill="none" stroke="${shade(c, light ? -0.25 : 0.35)}" stroke-width=".9" stroke-dasharray="2.2 1.8"/>`,
    stripe: `<rect x="${x + bw * 0.66}" y="${y}" width="7" height="${bh}" fill="${c2 === c ? shade(c, 0.35) : c2}" opacity=".85"/>`,
  };
  const bodyFill = L.finish === "matte" || L.finish === "leather"
    ? `<stop offset="0" stop-color="${shade(c, 0.06)}"/><stop offset="1" stop-color="${shade(c, -0.1)}"/>`
    : `<stop offset="0" stop-color="${shade(c, 0.25)}"/><stop offset="1" stop-color="${shade(c, -0.2)}"/>`;
  const sx = fx + 3.5, sy = fy + 3.5, sw = bw - 7, sh = bh - 7, sr = Math.max(2, r - 3);
  const walls = [
    "",
    `<path d="M${sx} ${sy + sh * 0.55} Q${sx + sw * 0.3} ${sy + sh * 0.42} ${sx + sw * 0.6} ${sy + sh * 0.56} T${sx + sw} ${sy + sh * 0.5} L${sx + sw} ${sy + sh} L${sx} ${sy + sh} Z" fill="${shade(c2, 0.2)}" opacity=".55"/>
     <path d="M${sx} ${sy + sh * 0.72} Q${sx + sw * 0.4} ${sy + sh * 0.6} ${sx + sw} ${sy + sh * 0.74} L${sx + sw} ${sy + sh} L${sx} ${sy + sh} Z" fill="${shade(c, 0.1)}" opacity=".6"/>`,
    `<circle cx="${sx + sw * 0.3}" cy="${sy + sh * 0.35}" r="${sw * 0.45}" fill="${shade(c2, 0.25)}" opacity=".55"/>
     <circle cx="${sx + sw * 0.8}" cy="${sy + sh * 0.7}" r="${sw * 0.38}" fill="${shade(c, 0.2)}" opacity=".55"/>`,
    `<path d="M${sx} ${sy + sh * 0.2} L${sx + sw} ${sy + sh * 0.05} L${sx + sw} ${sy + sh * 0.35} L${sx} ${sy + sh * 0.6} Z" fill="rgba(255,255,255,.18)"/>`,
  ];
  const cx = L.notch === "left" ? sx + 9 : fx + bw / 2;
  const notch = {
    center: `<circle cx="${cx}" cy="${sy + 6}" r="2.3" fill="#05060a"/>`,
    left: `<circle cx="${cx}" cy="${sy + 6}" r="2.3" fill="#05060a"/>`,
    drop: `<path d="M${cx - 7} ${sy} Q${cx - 3} ${sy} ${cx - 3} ${sy + 4} A3 3 0 0 0 ${cx + 3} ${sy + 4} Q${cx + 3} ${sy} ${cx + 7} ${sy} Z" fill="#05060a"/>`,
    island: `<rect x="${cx - 9}" y="${sy + 3.5}" width="18" height="5.5" rx="2.75" fill="#05060a"/>`,
  }[L.notch || "center"];
  const mark = `<text x="${x + bw / 2}" y="${y + bh - 14}" text-anchor="middle" font-size="6.5" font-weight="700" letter-spacing="1"
    fill="${light ? "rgba(0,0,0,.35)" : "rgba(255,255,255,.55)"}">${esc(p.name.split(" ")[0].toUpperCase())}</text>`;
  return `<svg class="phone-svg" viewBox="0 0 160 150" role="img" aria-label="${esc(p.name)}">
    <defs>
      <linearGradient id="${id}-b" x1="0" y1="0" x2="1" y2="1">${bodyFill}</linearGradient>
      <linearGradient id="${id}-s" x1="0" y1="0" x2="${L.wallpaper === 3 ? 0 : 1}" y2="1"><stop offset="0" stop-color="${shade(c2, 0.1)}"/><stop offset=".55" stop-color="${shade(c, -0.1)}"/><stop offset="1" stop-color="#0d1020"/></linearGradient>
      <clipPath id="${id}-sc"><rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="${sr}"/></clipPath>
      <clipPath id="${id}-bc"><rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="${r}"/></clipPath>
    </defs>
    <ellipse cx="80" cy="145" rx="60" ry="3.5" fill="rgba(0,0,0,.10)"/>
    <rect x="${fx}" y="${fy}" width="${bw}" height="${bh}" rx="${r}" fill="#14161b"/>
    <g clip-path="url(#${id}-sc)"><rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" fill="url(#${id}-s)"/>${walls[L.wallpaper || 0]}</g>
    ${notch}
    ${L.shape === "curved" ? `<rect x="${fx + 1}" y="${fy + 14}" width="2" height="${bh - 28}" rx="1" fill="rgba(255,255,255,.25)"/>` : ""}
    <rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="${r}" fill="url(#${id}-b)"/>
    <g clip-path="url(#${id}-bc)">${finishes[L.finish] || ""}</g>
    <rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="${r}" fill="none" stroke="rgba(0,0,0,.18)"/>
    ${L.shape === "curved" ? `<rect x="${x + bw - 3}" y="${y + 14}" width="2" height="${bh - 28}" rx="1" fill="rgba(255,255,255,.3)"/>` : ""}
    ${cams[L.camera] || cams.square}
    ${mark}
  </svg>`;
}

const Shop = {
  /* Render the shop into `root`. opts: {set, card_order, header, prompt, buyLabel, interactive, onBuy}
     Each card shows the picture, colours, price and the start of the specs; "View details" opens all spec rows. */
  render(root, opts) {
    const set = opts.set;
    const byId = Object.fromEntries(set.phones.map(p => [p.id, p]));
    const order = opts.card_order.map(id => byId[id]);
    const card = set.card;
    const reqText = opts.prompt
      ? `<div class="what">${esc(opts.prompt)}</div>`
      : `<div class="who">${esc(card.persona)}</div><div class="what">${esc(card.text)}</div>`;
    const first = v => v.split(" · ")[0];
    const cards = order.map(p => {
      const specs = SPEC_ORDER.map(k => `
        <div class="spec" data-zone="spec:${p.id}:${k}">
          <span class="k">${esc(set.spec_labels[k])}</span>${p.specs[k].split(" · ").map(v => `<span class="v">${esc(v)}</span>`).join("")}
        </div>`).join("");
      const dots = p.colours.map(n => `<i style="background:${COLOURS[n] || "#888"}" title="${esc(n)}"></i>`).join("");
      return `
      <div class="card" data-zone="card:${p.id}" data-phone="${p.id}">
        <div class="phone-pic">${phoneSvg(p)}</div>
        <h3>${esc(p.name)}</h3>
        <div class="colours"><span class="swatches">${dots}</span>${esc(p.colours.join(", "))}</div>
        <div class="price">${esc(first(p.specs.price))}</div>
        <div class="teaser">${esc(first(p.specs.display))} · ${esc(first(p.specs.camera))} · ${esc(first(p.specs.storage))} …</div>
        <div class="specs-full">${specs}</div>
        <div class="btns">
          <button class="details-btn" data-log="details:${p.id}" data-phone="${p.id}">View details</button>
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
      </div>`;
    /* Opens or closes one phone's full specs. The replay calls this for every logged click, so it stays in step. */
    const toggleDetails = pid => {
      const c = root.querySelector(`.card[data-phone="${pid}"]`);
      if (!c) return;
      const open = c.classList.toggle("open");
      c.querySelector(".details-btn").textContent = open ? "Hide details" : "View details";
    };
    root.querySelectorAll(".details-btn").forEach(b => b.addEventListener("click", () => toggleDetails(b.dataset.phone)));
    if (opts.interactive !== false) {
      root.querySelectorAll(".buy-btn").forEach(b => b.addEventListener("click", () => {
        const p = byId[b.dataset.phone];
        Modal.confirm(`${opts.buyLabel || "Buy"}: ${p.name}?`, "You cannot change it in this step.",
          opts.buyLabel ? "Yes, choose it" : "Yes, buy it", "Go back").then(ok => { if (ok) opts.onBuy(p.id); });
      }));
    }
    return { toggleDetails, byId };
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
