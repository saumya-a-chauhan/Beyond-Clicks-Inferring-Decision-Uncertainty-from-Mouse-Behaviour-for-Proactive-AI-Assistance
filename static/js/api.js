/* Small helpers shared by all pages. */
const API = {
  async req(method, url, body, token) {
    const opt = { method, headers: {}, credentials: "same-origin" };
    if (token) opt.headers["X-Token"] = token;      // participant session token: in a header, never in the URL
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(url, opt);
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await r.json() : await r.text();
    if (!r.ok) {
      const msg = (data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : ("Request failed: " + r.status);
      const err = new Error(msg); err.status = r.status; throw err;
    }
    return data;
  },
  get(url, token) { return this.req("GET", url, undefined, token); },
  post(url, body) { return this.req("POST", url, body || {}); },
  del(url) { return this.req("DELETE", url); },
};

const Session = {
  key: "hti_session",
  load() { try { return JSON.parse(localStorage.getItem(this.key)); } catch (e) { return null; } },
  save(s) { try { localStorage.setItem(this.key, JSON.stringify(s)); } catch (e) { /* private mode */ } },
  clear() { try { localStorage.removeItem(this.key); } catch (e) { /* ignore */ } },
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
