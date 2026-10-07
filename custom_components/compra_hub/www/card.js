// Tarjeta «Compra Hub» para los paneles de Home Assistant.
//
// Tres pestañas: Compra (lista con añadir/tachar, en directo), Hoy (tareas
// que vencen, recordatorios y menú) y Gastos (este mes, saldos, quién debe a
// quién y apuntar un gasto). Usa las entidades de la integración: qué
// entidades son de qué cuenta lo dice el comando WebSocket compra_hub/info,
// que elige la cuenta del usuario que mira el panel (o config.entry_id).
//
// Sin dependencias: custom element con shadow DOM. Los formularios viven
// fuera de las zonas que se repintan, para no perder lo que se está
// escribiendo cuando llega una actualización.

const COLORS = {
  compra: "#d9a53a",
  hoy: "#5b97cf",
  gastos: "#4f9c72",
};
const TABS = [
  ["compra", "Compra"],
  ["hoy", "Hoy"],
  ["gastos", "Gastos"],
];
const CATEGORIES = [
  ["otros", "Otros"],
  ["comida", "Comida"],
  ["casa", "Casa"],
  ["ocio", "Ocio"],
  ["transporte", "Transporte"],
  ["salud", "Salud"],
];

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const euros = (n) =>
  Number(n).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

class CompraHubCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._tab = "compra";
    this._listIdx = 0;
    this._items = null;
    this._unsub = null;
    this._sig = "";
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = config || {};
    if (this._config.tab && TABS.some(([t]) => t === this._config.tab)) this._tab = this._config.tab;
    if (this._info) this._renderAll();
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
    else if (this._info && this._tab !== "compra") {
      const sig = this._stateSignature();
      if (sig !== this._sig) {
        this._sig = sig;
        this._renderBody();
      }
    }
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  connectedCallback() {
    if (this._info && this._tab === "compra" && !this._unsub) this._subscribeList();
  }

  // ------------------------------------------------------------- datos

  async _load() {
    try {
      const msg = { type: "compra_hub/info" };
      if (this._config?.entry_id) msg.entry_id = this._config.entry_id;
      this._info = await this._hass.callWS(msg);
      this._error = null;
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._renderAll();
  }

  _state(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _stateSignature() {
    const i = this._info;
    const ids = [i.month_spent, i.tasks_today, ...i.balances.flatMap((b) => [b.balance, b.debts]), ...i.meals.flatMap((m) => [m.comida, m.cena])];
    return ids.map((id) => this._state(id)?.last_updated || "").join("|");
  }

  _unsubscribe() {
    if (this._unsub) {
      this._unsub.then((u) => u()).catch(() => {});
      this._unsub = null;
    }
  }

  _subscribeList() {
    this._unsubscribe();
    const list = this._info.lists[this._listIdx];
    if (!list) return;
    this._items = null;
    this._unsub = this._hass.connection.subscribeMessage(
      (msg) => {
        this._items = msg.items || [];
        this._renderBody();
      },
      { type: "todo/item/subscribe", entity_id: list.entity_id },
    );
  }

  async _call(domain, service, data, target) {
    try {
      await this._hass.callService(domain, service, data, target);
      return true;
    } catch (err) {
      this._toast(err?.message || "No se pudo hacer.");
      return false;
    }
  }

  // --------------------------------------------------------- pintado

  _renderAll() {
    const color = COLORS[this._tab];
    const title = this._config?.title || "Compra Hub";
    this._root.innerHTML = `
      <style>${CSS}</style>
      <ha-card>
        <div class="head" style="--accent:${color}">
          <div class="title">${esc(title)}${this._info?.hub?.includes("-dev") ? ' <span class="badge">dev</span>' : ""}</div>
          <div class="tabs" role="tablist">
            ${TABS.map(([id, label]) => `<button role="tab" data-tab="${id}" style="--c:${COLORS[id]}" aria-selected="${id === this._tab}">${label}</button>`).join("")}
          </div>
        </div>
        <div class="content">
          ${this._error ? `<p class="error">${esc(this._error)}</p>` : this._info ? this._tabShell() : `<p class="muted">Cargando…</p>`}
        </div>
        <div class="toast" hidden></div>
      </ha-card>`;
    this._root.querySelectorAll("[data-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        this._tab = b.dataset.tab;
        this._renderAll();
      }),
    );
    if (!this._info) return;
    this._bindForms();
    if (this._tab === "compra") {
      if (!this._unsub) this._subscribeList();
    } else {
      this._unsubscribe();
    }
    this._sig = this._stateSignature();
    this._renderBody();
  }

  _tabShell() {
    if (this._tab === "compra") {
      const lists = this._info.lists;
      if (!lists.length) return `<p class="muted">No hay listas de la compra.</p>`;
      const chips =
        lists.length > 1
          ? `<div class="chips">${lists
              .map((l, i) => `<button class="chip" data-list="${i}" aria-pressed="${i === this._listIdx}">${esc(l.group || l.name)}</button>`)
              .join("")}</div>`
          : "";
      return `${chips}
        <form class="add" data-form="item">
          <input name="name" placeholder="Añadir a la lista…" autocomplete="off" required>
          <input name="qty" class="qty" placeholder="Cant." autocomplete="off">
          <button type="submit" aria-label="Añadir">${ICON_PLUS}</button>
        </form>
        <div class="body"></div>`;
    }
    if (this._tab === "gastos") {
      const groups = this._info.groups;
      return `<div class="body"></div>
        <form class="expense" data-form="expense">
          <div class="row">
            <input name="description" placeholder="Concepto" autocomplete="off" required>
            <input name="amount" class="amount" placeholder="0,00 €" inputmode="decimal" autocomplete="off" required>
          </div>
          <div class="row">
            <select name="group">
              <option value="">Personal</option>
              ${groups.map((g) => `<option value="${esc(g.id)}">${esc(g.name)}</option>`).join("")}
            </select>
            <select name="category">${CATEGORIES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
            <button type="submit" class="primary">Apuntar</button>
          </div>
        </form>`;
    }
    return `<div class="body"></div>`;
  }

  _bindForms() {
    this._root.querySelectorAll("[data-list]").forEach((b) =>
      b.addEventListener("click", () => {
        this._listIdx = Number(b.dataset.list);
        this._root.querySelectorAll("[data-list]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        this._subscribeList();
        this._renderBody();
      }),
    );
    const itemForm = this._root.querySelector('[data-form="item"]');
    itemForm?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = new FormData(itemForm);
      const name = String(f.get("name") || "").trim();
      if (!name) return;
      const data = { item: name };
      const qty = String(f.get("qty") || "").trim();
      if (qty) data.description = qty;
      itemForm.reset();
      itemForm.querySelector("input").focus();
      await this._call("todo", "add_item", data, { entity_id: this._info.lists[this._listIdx].entity_id });
    });
    const expForm = this._root.querySelector('[data-form="expense"]');
    expForm?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = new FormData(expForm);
      const amount = Number(String(f.get("amount")).replace(",", "."));
      if (!(amount > 0)) return this._toast("El importe no es válido.");
      const data = {
        config_entry_id: this._info.entry_id,
        description: String(f.get("description")).trim(),
        amount,
        category: f.get("category"),
      };
      const gid = f.get("group");
      if (gid) data.group = gid;
      if (await this._call("compra_hub", "add_expense", data)) {
        expForm.reset();
        this._toast(`Apuntado: ${euros(amount)}`);
      }
    });
  }

  _renderBody() {
    const body = this._root.querySelector(".body");
    if (!body || !this._info) return;
    if (this._tab === "compra") this._renderCompra(body);
    else if (this._tab === "hoy") this._renderHoy(body);
    else this._renderGastos(body);
  }

  _renderCompra(body) {
    if (this._items === null) {
      body.innerHTML = `<p class="muted">Cargando…</p>`;
      return;
    }
    const pending = this._items.filter((i) => i.status !== "completed");
    const done = this._items.filter((i) => i.status === "completed");
    const row = (i) => `
      <li class="${i.status === "completed" ? "done" : ""}">
        <label>
          <input type="checkbox" data-uid="${esc(i.uid)}" ${i.status === "completed" ? "checked" : ""}>
          <span class="name">${esc(i.summary)}</span>
          ${i.description ? `<span class="qty">${esc(i.description)}</span>` : ""}
        </label>
      </li>`;
    body.innerHTML = `
      ${this._items.length ? `<ul class="items">${pending.map(row).join("")}${done.map(row).join("")}</ul>` : `<p class="muted">La lista está vacía.</p>`}
      ${done.length ? `<button class="link" data-clear>Quitar tachados (${done.length})</button>` : ""}`;
    const entity = { entity_id: this._info.lists[this._listIdx].entity_id };
    body.querySelectorAll("[data-uid]").forEach((cb) =>
      cb.addEventListener("change", () =>
        this._call("todo", "update_item", { item: cb.dataset.uid, status: cb.checked ? "completed" : "needs_action" }, entity),
      ),
    );
    body.querySelector("[data-clear]")?.addEventListener("click", () => this._call("todo", "remove_completed_items", {}, entity));
  }

  async _renderHoy(body) {
    const token = (this._hoyToken = (this._hoyToken || 0) + 1);
    const today = todayIso();
    // Tareas: de las entidades de tareas, las pendientes que vencen hoy o antes.
    const taskLists = await Promise.all(
      this._info.tasks.map(async (t) => {
        try {
          const r = await this._hass.callWS({ type: "todo/item/list", entity_id: t.entity_id });
          return (r.items || [])
            .filter((i) => i.status !== "completed" && i.due && i.due.slice(0, 10) <= today)
            .map((i) => ({ ...i, entity_id: t.entity_id, group: t.group }));
        } catch {
          return [];
        }
      }),
    );
    // Recordatorios de hoy, de todos los calendarios del hub.
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    const events = (
      await Promise.all(
        this._info.calendars.map(async (c) => {
          try {
            const evs = await this._hass.callApi("GET", `calendars/${c.entity_id}?start=${start.toISOString()}&end=${end.toISOString()}`);
            return evs.map((e) => ({ ...e, group: c.group }));
          } catch {
            return [];
          }
        }),
      )
    ).flat();
    if (token !== this._hoyToken) return; // llegó otra actualización mientras tanto
    const tasks = taskLists.flat().sort((a, b) => a.due.localeCompare(b.due));
    events.sort((a, b) => String(a.start.dateTime || a.start.date).localeCompare(String(b.start.dateTime || b.start.date)));
    const meals = this._info.meals
      .map((m) => ({ group: m.group, comida: this._state(m.comida)?.state, cena: this._state(m.cena)?.state }))
      .filter((m) => (m.comida && m.comida !== "Sin planificar") || (m.cena && m.cena !== "Sin planificar") || !m.group);
    const tag = (g) => (g ? `<span class="tag">${esc(g)}</span>` : "");
    const time = (e) => (e.start.dateTime ? new Date(e.start.dateTime).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "Todo el día");
    body.innerHTML = `
      <h3 style="--c:${COLORS.hoy}">Tareas</h3>
      ${
        tasks.length
          ? `<ul class="items">${tasks
              .map(
                (t) => `<li><label><input type="checkbox" data-task="${esc(t.uid)}" data-entity="${esc(t.entity_id)}">
                  <span class="name">${esc(t.summary)}</span>${tag(t.group)}
                  ${t.due.slice(0, 10) < today ? `<span class="late">atrasada</span>` : ""}</label></li>`,
              )
              .join("")}</ul>`
          : `<p class="muted">Nada que vence hoy.</p>`
      }
      <h3 style="--c:#c9617f">Recordatorios</h3>
      ${
        events.length
          ? `<ul class="plain">${events.map((e) => `<li><span class="time">${time(e)}</span> ${esc(e.summary)} ${tag(e.group)}</li>`).join("")}</ul>`
          : `<p class="muted">Hoy no hay nada apuntado.</p>`
      }
      <h3 style="--c:#d97f45">Menú de hoy</h3>
      <ul class="plain">
        ${meals
          .map(
            (m) => `<li>${tag(m.group) || '<span class="tag mine">Tú</span>'} <b>Comida:</b> ${esc(m.comida || "—")} · <b>Cena:</b> ${esc(m.cena || "—")}</li>`,
          )
          .join("")}
      </ul>`;
    body.querySelectorAll("[data-task]").forEach((cb) =>
      cb.addEventListener("change", async () => {
        if (await this._call("todo", "update_item", { item: cb.dataset.task, status: "completed" }, { entity_id: cb.dataset.entity })) {
          cb.closest("li").classList.add("done");
        }
      }),
    );
  }

  _renderGastos(body) {
    const month = this._state(this._info.month_spent);
    const rows = this._info.balances.map((b) => {
      const s = this._state(b.balance);
      const v = s ? Number(s.state) : 0;
      const debts = this._state(b.debts)?.attributes?.resumen || [];
      return `<div class="group">
        <div class="grow"><b>${esc(b.group)}</b>
          <span class="${v > 0 ? "pos" : v < 0 ? "neg" : "muted"}">${v > 0 ? "te deben " + euros(v) : v < 0 ? "debes " + euros(-v) : "en paz"}</span></div>
        ${debts.length ? `<ul class="plain small">${debts.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : `<p class="muted small">Todo saldado.</p>`}
      </div>`;
    });
    body.innerHTML = `
      <div class="month"><span>Este mes</span><strong>${month ? euros(Number(month.state)) : "—"}</strong></div>
      ${rows.join("") || `<p class="muted">Sin grupos con gastos compartidos.</p>`}`;
  }

  _toast(text) {
    const t = this._root.querySelector(".toast");
    if (!t) return;
    t.textContent = text;
    t.hidden = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (t.hidden = true), 3000);
  }
}

const ICON_PLUS = `<svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/></svg>`;

const CSS = `
  ha-card { overflow: hidden; position: relative; }
  .head { padding: 14px 16px 0; border-top: 4px solid var(--accent); }
  .title { font-size: 1.25rem; font-weight: 500; color: var(--primary-text-color); }
  .badge { font-size: .7rem; padding: 1px 6px; border-radius: 8px; background: var(--secondary-background-color); color: var(--secondary-text-color); vertical-align: middle; }
  .tabs { display: flex; gap: 4px; margin-top: 8px; border-bottom: 1px solid var(--divider-color); }
  .tabs button { flex: 1; padding: 10px 4px 9px; border: 0; background: none; cursor: pointer; font: inherit; font-weight: 500;
    color: var(--secondary-text-color); border-bottom: 3px solid transparent; }
  .tabs button[aria-selected="true"] { color: var(--primary-text-color); border-bottom-color: var(--c); }
  .content { padding: 12px 16px 16px; }
  .muted { color: var(--secondary-text-color); margin: 8px 0; }
  .small { font-size: .9em; }
  .error { color: var(--error-color); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
  .chip { padding: 5px 12px; border-radius: 16px; border: 1px solid var(--divider-color); background: none; cursor: pointer;
    font: inherit; font-size: .9rem; color: var(--primary-text-color); }
  .chip[aria-pressed="true"] { background: ${COLORS.compra}; border-color: ${COLORS.compra}; color: #fff; }
  form { display: flex; gap: 6px; }
  form.expense { flex-direction: column; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--divider-color); }
  form .row { display: flex; gap: 6px; }
  input, select { flex: 1 1 auto; min-width: 0; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
  input.qty { flex: 0 0 70px; }
  input.amount { flex: 0 0 100px; text-align: right; }
  form button { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; min-width: 42px; padding: 0 12px;
    border: 0; border-radius: 8px; background: ${COLORS.compra}; color: #fff; cursor: pointer; font: inherit; font-weight: 500; }
  form button.primary { background: ${COLORS.gastos}; }
  ul { list-style: none; margin: 6px 0; padding: 0; }
  .items li { border-bottom: 1px solid var(--divider-color); }
  .items label { display: flex; align-items: center; gap: 10px; padding: 9px 2px; cursor: pointer; }
  .items input { flex: 0 0 auto; width: 18px; height: 18px; margin: 0; accent-color: ${COLORS.compra}; }
  .items .name { flex: 1 1 auto; }
  .items .qty, .time { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .items li.done .name { text-decoration: line-through; color: var(--secondary-text-color); }
  .plain li { padding: 5px 0; }
  .tag { display: inline-block; font-size: .75rem; padding: 1px 7px; border-radius: 8px; background: var(--secondary-background-color);
    color: var(--secondary-text-color); }
  .tag.mine { background: none; border: 1px solid var(--divider-color); }
  .late { font-size: .75rem; color: var(--error-color); }
  h3 { margin: 14px 0 2px; font-size: .95rem; font-weight: 600; padding-left: 8px; border-left: 3px solid var(--c); }
  h3:first-child { margin-top: 2px; }
  .link { margin-top: 8px; padding: 0; border: 0; background: none; color: var(--primary-color); cursor: pointer; font: inherit; }
  .month { display: flex; flex-direction: column; margin-bottom: 8px; }
  .month span { color: var(--secondary-text-color); }
  .month strong { font-size: 2rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .group { padding: 8px 0; border-top: 1px solid var(--divider-color); }
  .grow { display: flex; justify-content: space-between; gap: 8px; }
  .pos { color: var(--success-color, #3c8c5a); font-weight: 600; }
  .neg { color: var(--error-color); font-weight: 600; }
  .toast { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); padding: 8px 14px; border-radius: 16px;
    background: var(--primary-text-color); color: var(--card-background-color); font-size: .9rem; white-space: nowrap; }
`;

// Home Assistant sustituye window.customElements por un registro con ámbito
// (polyfill) durante el arranque, después del evento «load» y sin una
// asignación normal. Este módulo (add_extra_js_url) se ejecuta antes: si solo
// se definiera una vez, la tarjeta quedaría en el registro nativo y los
// paneles dirían «Custom element doesn't exist». Por eso se define en el
// registro activo y se vuelve a comprobar hasta que Home Assistant ha
// arrancado (home-assistant definido en ese mismo registro).
const TAG = "compra-hub-card";

function defineCard() {
  const registry = window.customElements;
  if (!registry.get(TAG)) {
    try {
      // Una subclase por registro: un constructor no se puede registrar dos veces.
      registry.define(TAG, class extends CompraHubCard {});
    } catch (err) {
      console.warn("compra-hub-card:", err);
    }
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "Compra Hub",
      description: "La lista de la compra, lo de hoy y los gastos del hub en una tarjeta.",
      preview: false,
      documentationURL: "https://github.com/ElPostilla/ha-compra-hub",
    });
  }
  return !!registry.get("home-assistant") && !!registry.get(TAG);
}

if (!defineCard()) {
  let tries = 0;
  const timer = setInterval(() => {
    if (defineCard() || ++tries > 240) clearInterval(timer); // como mucho 60 s
  }, 250);
}
