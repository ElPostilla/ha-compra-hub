// Tarjeta «Compra Hub» para los paneles de Home Assistant.
//
// Dos formas de usarla:
// - Con pestañas (sin `section`): Compra, Hoy y Gastos en una sola tarjeta.
// - Una sección suelta (`section: compra | hoy | gastos`): sin pestañas, con
//   su propia cabecera y tamaños pensados para el dedo. Es la que va en una
//   tablet de pared, con las tres tarjetas a la vista a la vez.
//
// Compra: lista con añadir/tachar en directo, agrupada por pasillos como en la
// app (el pasillo y los fijados vienen de compra_hub/list). Hoy: tareas que
// vencen, añadir una tarea, agenda y menú. Gastos: este mes, saldos, quién
// debe a quién y apuntar un gasto. Qué entidades son de qué cuenta lo dice
// compra_hub/info, que elige la cuenta del usuario que mira el panel (o
// config.entry_id).
//
// Opciones: section, tab (pestaña inicial), title, entry_id, list (lista
// inicial, entity_id), days (días de agenda en Hoy, 1 por defecto) y
// max_height (alto máximo del contenido, con scroll dentro: «520px»).
//
// Sin dependencias: custom element con shadow DOM. Los formularios viven
// fuera de las zonas que se repintan, para no perder lo que se está
// escribiendo cuando llega una actualización.

// Colores de cada app en el hub («cuaderno de casa»).
const SECTIONS = {
  compra: { label: "Compra", icon: "mdi:cart-outline", color: "#e2b13c" },
  hoy: { label: "Hoy", icon: "mdi:calendar-today", color: "#5f9fd6" },
  gastos: { label: "Gastos", icon: "mdi:wallet-outline", color: "#5aa97c" },
};
const AGENDA_COLOR = "#d7708b";
const MENU_COLOR = "#e3874a";

// Pasillos en el orden de la app (recorrido típico del súper).
const AISLES = [
  ["fruver", "Frutas y verduras", "mdi:food-apple-outline"],
  ["pan", "Panadería", "mdi:baguette"],
  ["lacteos", "Lácteos y huevos", "mdi:cheese"],
  ["carne", "Carnicería y pescadería", "mdi:food-drumstick-outline"],
  ["despensa", "Despensa", "mdi:pasta"],
  ["congelados", "Congelados", "mdi:snowflake"],
  ["bebidas", "Bebidas", "mdi:bottle-soda-outline"],
  ["limpieza", "Limpieza y hogar", "mdi:spray-bottle"],
  ["higiene", "Higiene y cuidado personal", "mdi:lotion-outline"],
  ["otros", "Otros", "mdi:basket-outline"],
];
const CATEGORIES = [
  ["otros", "Otros"],
  ["comida", "Comida"],
  ["casa", "Casa"],
  ["ocio", "Ocio"],
  ["transporte", "Transporte"],
  ["salud", "Salud"],
];
const HOY_REFRESH_MS = 5 * 60 * 1000;

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const euros = (n) =>
  Number(n).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const isoDay = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const icon = (name) => `<ha-icon icon="${name}"></ha-icon>`;

const storage = {
  get(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* sin almacenamiento (modo privado): no pasa nada */
    }
  },
};

class CompraHubCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._tab = "compra";
    this._listIdx = 0;
    this._rows = null;
    this._unsub = null;
    this._sig = "";
    this._rowsToken = 0;
    this._hoyToken = 0;
  }

  static getStubConfig() {
    return { section: "compra" };
  }

  setConfig(config) {
    this._config = config || {};
    if (this._config.section && !SECTIONS[this._config.section]) {
      throw new Error("section debe ser compra, hoy o gastos");
    }
    if (this._config.tab && SECTIONS[this._config.tab]) this._tab = this._config.tab;
    if (this._info) this._renderAll();
  }

  getCardSize() {
    return { compra: 8, hoy: 6, gastos: 5 }[this._config?.section] || 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  get _view() {
    return this._config?.section || this._tab;
  }

  get _single() {
    return !!this._config?.section;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
    else if (this._info && this._view !== "compra") {
      const sig = this._stateSignature();
      if (sig !== this._sig) {
        this._sig = sig;
        this._renderHead();
        this._renderBody();
      }
    }
  }

  connectedCallback() {
    if (this._info && this._view === "compra" && !this._unsub) this._subscribeList();
    this._startTimer();
  }

  disconnectedCallback() {
    this._unsubscribe();
    clearInterval(this._timer);
    this._timer = null;
  }

  // Hoy depende de la fecha y de la agenda, que no siempre cambian el estado
  // de una entidad: se repinta cada cinco minutos (y así pasa de día solo).
  _startTimer() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      if (this._info && this._view === "hoy") {
        this._renderHead();
        this._renderBody();
      }
    }, HOY_REFRESH_MS);
  }

  // ------------------------------------------------------------- datos

  async _load() {
    try {
      const msg = { type: "compra_hub/info" };
      if (this._config?.entry_id) msg.entry_id = this._config.entry_id;
      this._info = await this._hass.callWS(msg);
      this._error = null;
      this._pickInitialList();
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._renderAll();
  }

  get _listKey() {
    return `compra-hub-card:list:${this._info?.entry_id}`;
  }

  // Lista inicial: la de config.list; si no, la última elegida en este
  // dispositivo (una tablet de pared vuelve a la suya tras recargar).
  _pickInitialList() {
    const lists = this._info.lists;
    const wanted = this._config?.list || storage.get(this._listKey);
    const idx = lists.findIndex((l) => l.entity_id === wanted);
    this._listIdx = idx >= 0 ? idx : 0;
  }

  _state(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _stateSignature() {
    const i = this._info;
    const ids = [
      i.month_spent,
      i.tasks_today,
      ...i.tasks.map((t) => t.entity_id),
      ...i.balances.flatMap((b) => [b.balance, b.debts]),
      ...i.meals.flatMap((m) => [m.comida, m.cena]),
    ];
    return ids.map((id) => this._state(id)?.last_updated || "").join("|");
  }

  _unsubscribe() {
    if (this._unsub) {
      this._unsub.then((u) => u()).catch(() => {});
      this._unsub = null;
    }
  }

  _currentList() {
    return this._info?.lists[this._listIdx];
  }

  // La suscripción a la entidad todo avisa de cada cambio al momento; el
  // detalle (pasillo, fijado) se pide después a compra_hub/list.
  _subscribeList() {
    this._unsubscribe();
    const list = this._currentList();
    if (!list) return;
    this._rows = null;
    this._unsub = this._hass.connection.subscribeMessage(
      (msg) => {
        this._todoItems = msg.items || [];
        this._fetchRows();
      },
      { type: "todo/item/subscribe", entity_id: list.entity_id },
    );
  }

  async _fetchRows() {
    const token = ++this._rowsToken;
    const list = this._currentList();
    let rows;
    try {
      rows = (await this._hass.callWS({ type: "compra_hub/list", entity_id: list.entity_id })).items;
    } catch {
      // Sin detalle: la lista tal cual, sin pasillos.
      rows = (this._todoItems || []).map((i) => ({
        id: i.uid,
        name: i.summary,
        qty: i.description || "",
        category: "otros",
        done: i.status === "completed",
        recurring: false,
      }));
    }
    if (token !== this._rowsToken) return; // llegó otra actualización mientras tanto
    this._rows = rows;
    this._renderHead();
    this._renderBody();
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
    const view = this._view;
    const sec = SECTIONS[view];
    const title = this._config?.title || (this._single ? sec.label : "Compra Hub");
    const dev = this._info?.hub?.includes("-dev") ? ' <span class="badge">dev</span>' : "";
    const tabs = this._single
      ? ""
      : `<div class="tabs" role="tablist">${Object.entries(SECTIONS)
          .map(([id, s]) => `<button role="tab" data-tab="${id}" style="--c:${s.color}" aria-selected="${id === view}">${s.label}</button>`)
          .join("")}</div>`;
    this._root.innerHTML = `
      <style>${CSS}</style>
      <ha-card class="${this._single ? "single" : "tabbed"} view-${view}" style="--accent:${sec.color}">
        <div class="head">
          ${this._single ? `<span class="bubble">${icon(sec.icon)}</span>` : ""}
          <div class="titles">
            <div class="title">${esc(title)}${dev}</div>
            <div class="sub"></div>
          </div>
        </div>
        ${tabs}
        <div class="content">
          ${this._error ? `<p class="error">${esc(this._error)}</p>` : this._info ? this._shell() : `<p class="muted">Cargando…</p>`}
        </div>
        <div class="toast" hidden></div>
      </ha-card>`;
    const body = this._root.querySelector(".body");
    if (body && this._config?.max_height) body.style.maxHeight = String(this._config.max_height);
    this._root.querySelectorAll("[data-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        this._tab = b.dataset.tab;
        this._renderAll();
      }),
    );
    if (!this._info) return;
    this._bindForms();
    if (view === "compra") {
      if (!this._unsub) this._subscribeList();
    } else {
      this._unsubscribe();
    }
    this._sig = this._stateSignature();
    this._renderHead();
    this._renderBody();
  }

  _shell() {
    const view = this._view;
    if (view === "compra") {
      const lists = this._info.lists;
      if (!lists.length) return `<p class="muted">No hay listas de la compra.</p>`;
      const chips =
        lists.length > 1
          ? `<div class="chips" role="tablist">${lists
              .map((l, i) => `<button class="chip" data-list="${i}" aria-pressed="${i === this._listIdx}">${esc(l.group || l.name)}</button>`)
              .join("")}</div>`
          : "";
      return `${chips}
        <form class="add" data-form="item">
          <input name="name" placeholder="Añadir a la lista…" autocomplete="off" enterkeyhint="done" required>
          <input name="qty" class="qty" placeholder="Cant." autocomplete="off">
          <button type="submit" class="go" aria-label="Añadir">${icon("mdi:plus")}</button>
        </form>
        <div class="body"></div>`;
    }
    if (view === "hoy") {
      return `<div class="body"></div>
        <form class="add task" data-form="task">
          <input name="title" placeholder="Nueva tarea para hoy…" autocomplete="off" enterkeyhint="done" required>
          ${this._scopeSelect(this._info.tasks.map((t) => t.group))}
          <button type="submit" class="go" aria-label="Añadir tarea">${icon("mdi:plus")}</button>
        </form>`;
    }
    const groups = this._info.groups;
    return `<div class="body"></div>
      <form class="expense" data-form="expense">
        <div class="row">
          <input name="description" placeholder="Concepto" autocomplete="off" required>
          <input name="amount" class="amount" placeholder="0,00 €" inputmode="decimal" autocomplete="off" required>
        </div>
        <div class="row">
          <select name="group" aria-label="Grupo">
            <option value="">Personal</option>
            ${groups.map((g) => `<option value="${esc(g.id)}">${esc(g.name)}</option>`).join("")}
          </select>
          <select name="category" aria-label="Categoría">${CATEGORIES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
          <button type="submit" class="go wide">Apuntar</button>
        </div>
      </form>`;
  }

  // Selector de ámbito: personal y los grupos que tengan esa app.
  _scopeSelect(groups) {
    const opts = groups.map((g) => `<option value="${esc(g || "")}">${esc(g || "Personal")}</option>`).join("");
    return groups.length > 1 ? `<select name="scope" aria-label="Para quién">${opts}</select>` : "";
  }

  _bindForms() {
    this._root.querySelectorAll("[data-list]").forEach((b) =>
      b.addEventListener("click", () => {
        this._listIdx = Number(b.dataset.list);
        storage.set(this._listKey, this._currentList().entity_id);
        this._root.querySelectorAll("[data-list]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        this._subscribeList();
        this._renderHead();
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
      await this._call("todo", "add_item", data, { entity_id: this._currentList().entity_id });
    });
    const taskForm = this._root.querySelector('[data-form="task"]');
    taskForm?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = new FormData(taskForm);
      const title = String(f.get("title") || "").trim();
      if (!title) return;
      const scope = String(f.get("scope") || "");
      const target = this._info.tasks.find((t) => (t.group || "") === scope) || this._info.tasks[0];
      if (!target) return this._toast("No hay listas de tareas.");
      if (await this._call("todo", "add_item", { item: title, due_date: isoDay(new Date()) }, { entity_id: target.entity_id })) {
        taskForm.reset();
        this._toast("Tarea apuntada para hoy");
        this._renderBody();
      }
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

  // Subtítulo de la cabecera: recuento (Compra), fecha (Hoy), gasto del mes.
  _renderHead() {
    const sub = this._root.querySelector(".sub");
    if (!sub || !this._info) return;
    const view = this._view;
    let text = "";
    if (view === "compra" && this._rows) {
      const pending = this._rows.filter((r) => !r.done).length;
      const done = this._rows.length - pending;
      const list = this._currentList();
      const name = this._info.lists.length > 1 ? `${list.group || list.name} · ` : "";
      text = `${name}${plural(pending, "pendiente", "pendientes")}${done ? ` · ${plural(done, "comprado", "comprados")}` : ""}`;
    } else if (view === "hoy") {
      text = new Date().toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
    } else if (view === "gastos") {
      const month = this._state(this._info.month_spent);
      text = month ? `Este mes, ${euros(Number(month.state))}` : "";
    }
    sub.textContent = this._single ? text : "";
  }

  _renderBody() {
    const body = this._root.querySelector(".body");
    if (!body || !this._info) return;
    if (this._view === "compra") this._renderCompra(body);
    else if (this._view === "hoy") this._renderHoy(body);
    else this._renderGastos(body);
  }

  _renderCompra(body) {
    if (this._rows === null) {
      body.innerHTML = `<p class="muted">Cargando…</p>`;
      return;
    }
    const pending = this._rows.filter((r) => !r.done);
    const done = this._rows.filter((r) => r.done);
    const row = (r) => `
      <li>
        <button class="item ${r.done ? "done" : ""}" role="checkbox" aria-checked="${r.done}" data-uid="${esc(r.id)}">
          <span class="box">${icon("mdi:check")}</span>
          <span class="name">${esc(r.name)}</span>
          ${r.recurring ? `<span class="pin" title="Fijo: vuelve a la lista al quitar los comprados">${icon("mdi:pin-outline")}</span>` : ""}
          ${r.qty && r.qty !== "1" ? `<span class="qty">${esc(r.qty)}</span>` : ""}
        </button>
      </li>`;
    const known = new Set(AISLES.map(([k]) => k));
    const aisles = AISLES.map(([key, label, ic]) => {
      const inAisle = pending.filter((r) => (known.has(r.category) ? r.category : "otros") === key);
      return inAisle.length
        ? `<section class="aisle"><h4>${icon(ic)}<span>${label}</span></h4><ul class="items">${inAisle.map(row).join("")}</ul></section>`
        : "";
    }).join("");
    body.innerHTML = this._rows.length
      ? `${pending.length ? aisles : `<p class="muted big">Todo comprado.</p>`}
         ${
           done.length
             ? `<section class="aisle bought"><h4>${icon("mdi:check-all")}<span>Comprados</span></h4>
                <ul class="items">${done.map(row).join("")}</ul>
                <button class="link" data-clear>Quitar comprados (${done.length})</button></section>`
             : ""
         }`
      : `<p class="muted big">La lista está vacía.</p>`;
    const entity = { entity_id: this._currentList().entity_id };
    body.querySelectorAll("[data-uid]").forEach((b) =>
      b.addEventListener("click", () => {
        const r = this._rows.find((x) => x.id === b.dataset.uid);
        if (!r) return;
        r.done = !r.done; // al momento; la suscripción trae lo guardado
        this._renderHead();
        this._renderBody();
        this._call("todo", "update_item", { item: r.id, status: r.done ? "completed" : "needs_action" }, entity);
      }),
    );
    body.querySelector("[data-clear]")?.addEventListener("click", () => this._call("todo", "remove_completed_items", {}, entity));
  }

  async _renderHoy(body) {
    const token = ++this._hoyToken;
    const today = isoDay(new Date());
    const days = Math.max(1, Math.min(7, Number(this._config?.days) || 1));
    // Tareas: las pendientes que vencen hoy o antes, de todas las listas de tareas.
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
    // Agenda: de hoy (y los días siguientes si days > 1), de todos los calendarios.
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + days);
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
    const evStart = (e) => String(e.start.dateTime || e.start.date);
    events.sort((a, b) => evStart(a).localeCompare(evStart(b)));
    const meals = this._info.meals
      .map((m) => ({ group: m.group, comida: this._state(m.comida)?.state, cena: this._state(m.cena)?.state }))
      .filter((m) => (m.comida && m.comida !== "Sin planificar") || (m.cena && m.cena !== "Sin planificar") || !m.group);
    const tag = (g) => (g ? `<span class="tag">${esc(g)}</span>` : "");
    const time = (e) =>
      e.start.dateTime ? new Date(e.start.dateTime).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "Todo el día";
    const dayLabel = (iso) => {
      if (iso === today) return "Hoy";
      const d = new Date(`${iso}T12:00:00`);
      const tomorrow = new Date(start);
      tomorrow.setDate(tomorrow.getDate() + 1);
      if (iso === isoDay(tomorrow)) return "Mañana";
      return d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric" });
    };
    const byDay = new Map();
    for (const e of events) {
      const iso = e.start.dateTime ? isoDay(new Date(e.start.dateTime)) : String(e.start.date).slice(0, 10);
      const key = iso < today ? today : iso; // los de varios días que empezaron antes cuentan hoy
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push(e);
    }
    const agenda = [...byDay.entries()]
      .map(
        ([iso, evs]) => `
        ${days > 1 ? `<div class="day">${esc(dayLabel(iso))}</div>` : ""}
        <ul class="plain">${evs.map((e) => `<li><span class="time">${time(e)}</span><span class="grow">${esc(e.summary)}</span>${tag(e.group)}</li>`).join("")}</ul>`,
      )
      .join("");
    body.innerHTML = `
      <h3 style="--c:${SECTIONS.hoy.color}">${icon("mdi:checkbox-marked-circle-outline")}<span>Tareas</span></h3>
      ${
        tasks.length
          ? `<ul class="items">${tasks
              .map(
                (t) => `<li><button class="item" role="checkbox" aria-checked="false" data-task="${esc(t.uid)}" data-entity="${esc(t.entity_id)}">
                  <span class="box">${icon("mdi:check")}</span>
                  <span class="name">${esc(t.summary)}</span>${tag(t.group)}
                  ${t.due.slice(0, 10) < today ? `<span class="late">atrasada</span>` : ""}</button></li>`,
              )
              .join("")}</ul>`
          : `<p class="muted">Nada que vence hoy.</p>`
      }
      <h3 style="--c:${AGENDA_COLOR}">${icon("mdi:calendar-clock")}<span>${days > 1 ? "Agenda" : "Agenda de hoy"}</span></h3>
      ${events.length ? agenda : `<p class="muted">${days > 1 ? "Nada apuntado estos días." : "Hoy no hay nada apuntado."}</p>`}
      <h3 style="--c:${MENU_COLOR}">${icon("mdi:silverware-fork-knife")}<span>Menú de hoy</span></h3>
      <ul class="plain meals">
        ${meals
          .map(
            (m) => `<li>${tag(m.group) || '<span class="tag mine">Tú</span>'}
              <span class="meal"><b>Comida</b> ${esc(m.comida || "—")}</span>
              <span class="meal"><b>Cena</b> ${esc(m.cena || "—")}</span></li>`,
          )
          .join("")}
      </ul>`;
    body.querySelectorAll("[data-task]").forEach((b) =>
      b.addEventListener("click", async () => {
        b.classList.add("done");
        b.setAttribute("aria-checked", "true");
        if (!(await this._call("todo", "update_item", { item: b.dataset.task, status: "completed" }, { entity_id: b.dataset.entity }))) {
          b.classList.remove("done");
          b.setAttribute("aria-checked", "false");
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
        <div class="grow-row"><b>${esc(b.group)}</b>
          <span class="${v > 0 ? "pos" : v < 0 ? "neg" : "even"}">${v > 0 ? "te deben " + euros(v) : v < 0 ? "debes " + euros(-v) : "en paz"}</span></div>
        ${debts.length ? `<ul class="plain small">${debts.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}
      </div>`;
    });
    body.innerHTML = `
      ${this._single ? "" : `<div class="month"><span>Este mes</span><strong>${month ? euros(Number(month.state)) : "—"}</strong></div>`}
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

const CSS = `
  :host { --tap: 44px; }
  ha-card { overflow: hidden; position: relative; height: 100%; box-sizing: border-box; }
  ha-icon { --mdc-icon-size: 20px; display: inline-flex; }
  .head { display: flex; align-items: center; gap: 12px; padding: 14px 16px 0; }
  .tabbed .head { border-top: 4px solid var(--accent); }
  .bubble { flex: 0 0 auto; display: grid; place-items: center; width: 40px; height: 40px; border-radius: 12px;
    background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
  .bubble ha-icon { --mdc-icon-size: 24px; }
  .titles { min-width: 0; }
  .title { font-size: 1.25rem; font-weight: 600; line-height: 1.2; color: var(--primary-text-color); }
  .sub { color: var(--secondary-text-color); font-size: .95rem; }
  .sub:empty { display: none; }
  .single .sub::first-letter { text-transform: uppercase; }
  .badge { font-size: .7rem; padding: 1px 6px; border-radius: 8px; background: var(--secondary-background-color);
    color: var(--secondary-text-color); vertical-align: middle; font-weight: 400; }
  .tabs { display: flex; gap: 4px; margin: 8px 16px 0; border-bottom: 1px solid var(--divider-color); }
  .tabs button { flex: 1; min-height: var(--tap); padding: 0 4px; border: 0; background: none; cursor: pointer; font: inherit;
    font-weight: 500; color: var(--secondary-text-color); border-bottom: 3px solid transparent; }
  .tabs button[aria-selected="true"] { color: var(--primary-text-color); border-bottom-color: var(--c); }
  .content { padding: 12px 16px 16px; }
  .body { overflow-y: auto; overscroll-behavior: contain; }
  .muted { color: var(--secondary-text-color); margin: 8px 0; }
  .muted.big { font-size: 1.05rem; padding: 18px 0; text-align: center; }
  .small { font-size: .9em; }
  .error { color: var(--error-color); }
  .chips { display: flex; gap: 8px; margin-bottom: 12px; overflow-x: auto; scrollbar-width: none; }
  .chip { flex: 0 0 auto; min-height: 36px; padding: 0 14px; border-radius: 18px; border: 1px solid var(--divider-color);
    background: none; cursor: pointer; font: inherit; font-size: .95rem; color: var(--primary-text-color); }
  .chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #1b1b1b; font-weight: 600; }
  form { display: flex; gap: 8px; }
  form.add { margin-bottom: 6px; }
  form.task { margin-top: 12px; }
  form.expense { flex-direction: column; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--divider-color); }
  form .row { display: flex; gap: 8px; }
  input, select { flex: 1 1 auto; min-width: 0; min-height: var(--tap); box-sizing: border-box; padding: 0 12px;
    border-radius: 10px; border: 1px solid var(--divider-color); background: var(--card-background-color);
    color: var(--primary-text-color); font: inherit; font-size: 1rem; }
  input:focus, select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  select { flex: 0 1 auto; max-width: 40%; }
  input.qty { flex: 0 0 76px; }
  input.amount { flex: 0 0 110px; text-align: right; }
  .go { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; min-width: var(--tap);
    min-height: var(--tap); padding: 0 12px; border: 0; border-radius: 10px; background: var(--accent); color: #1b1b1b;
    cursor: pointer; font: inherit; font-weight: 600; }
  .go.wide { padding: 0 18px; }
  .go ha-icon { --mdc-icon-size: 24px; }
  ul { list-style: none; margin: 4px 0; padding: 0; }
  .aisle { margin-top: 10px; }
  .aisle h4, h3 { display: flex; align-items: center; gap: 8px; margin: 14px 0 2px; font-size: .9rem; font-weight: 600;
    color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
  .aisle h4 ha-icon { --mdc-icon-size: 18px; color: var(--accent); }
  .aisle:first-child h4, h3:first-child { margin-top: 2px; }
  h3 { color: var(--primary-text-color); text-transform: none; letter-spacing: 0; font-size: 1rem; }
  h3 ha-icon { color: var(--c); }
  .items li + li { border-top: 1px solid var(--divider-color); }
  .item { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 50px; padding: 4px 2px; border: 0;
    background: none; cursor: pointer; font: inherit; font-size: 1.05rem; color: var(--primary-text-color); text-align: left;
    -webkit-tap-highlight-color: transparent; }
  .box { flex: 0 0 auto; display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%;
    border: 2px solid var(--accent); color: transparent; box-sizing: border-box; }
  .box ha-icon { --mdc-icon-size: 18px; }
  .item.done .box { background: var(--accent); color: #1b1b1b; }
  .item .name { flex: 1 1 auto; min-width: 0; }
  .item.done .name { text-decoration: line-through; color: var(--secondary-text-color); }
  .pin { color: var(--secondary-text-color); }
  .pin ha-icon { --mdc-icon-size: 16px; }
  .qty { flex: 0 0 auto; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .bought { opacity: .85; }
  .plain li { display: flex; align-items: baseline; gap: 10px; padding: 7px 0; }
  .plain li + li { border-top: 1px solid var(--divider-color); }
  .plain .grow { flex: 1 1 auto; min-width: 0; }
  .time { flex: 0 0 auto; min-width: 4.5em; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .day { margin: 8px 0 0; font-size: .85rem; font-weight: 600; color: var(--secondary-text-color); }
  .day::first-letter { text-transform: uppercase; }
  .meals li { flex-wrap: wrap; align-items: center; }
  .meal b { font-weight: 600; color: var(--secondary-text-color); margin-right: 4px; }
  .tag { display: inline-block; flex: 0 0 auto; font-size: .75rem; padding: 2px 8px; border-radius: 8px;
    background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .tag.mine { background: none; border: 1px solid var(--divider-color); }
  .late { font-size: .75rem; color: var(--error-color); }
  .link { margin-top: 6px; min-height: var(--tap); padding: 0; border: 0; background: none; color: var(--primary-color);
    cursor: pointer; font: inherit; }
  .month { display: flex; flex-direction: column; margin-bottom: 8px; }
  .month span { color: var(--secondary-text-color); }
  .month strong { font-size: 2rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .group { padding: 8px 0; }
  .group + .group { border-top: 1px solid var(--divider-color); }
  .grow-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .even { color: var(--secondary-text-color); }
  .pos { color: var(--success-color, #3c8c5a); font-weight: 600; }
  .neg { color: var(--error-color); font-weight: 600; }
  .toast { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); padding: 10px 16px; border-radius: 18px;
    background: var(--primary-text-color); color: var(--card-background-color); font-size: .95rem; white-space: nowrap; }
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
      description: "La lista de la compra, lo de hoy y los gastos del hub. Con section: compra, hoy o gastos, una sección suelta para tablets.",
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
