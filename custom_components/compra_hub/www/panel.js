// Panel «Compra Hub»: el hub dentro de Home Assistant, en un iframe, con una
// barra arriba (botón del menú lateral en móvil, título y «Abrir en una
// ventana»). Sin dependencias: un custom element con shadow DOM y los
// colores del tema de Home Assistant.
class CompraHubPanel extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._update();
  }

  set panel(panel) {
    this._panel = panel;
    this._render();
  }

  _render() {
    const url = this._panel?.config?.url;
    if (!url || this._renderedUrl === url) return;
    this._renderedUrl = url;
    const title = this._panel.title || "Compra Hub";
    this._root.innerHTML = `
      <style>
        :host {
          /* El contenedor del panel no tiene altura fija: sin esto el iframe
             se queda en sus 150 px por defecto. */
          display: flex; flex-direction: column; height: 100vh; height: 100dvh;
          background: var(--primary-background-color);
        }
        header {
          display: flex; align-items: center; gap: 4px; flex: 0 0 auto;
          height: var(--header-height, 56px); padding: 0 8px 0 4px; box-sizing: border-box;
          padding-top: env(safe-area-inset-top);
          background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, var(--text-primary-color, #fff));
          border-bottom: var(--app-header-border-bottom, none);
        }
        .title { flex: 1 1 auto; margin-left: 12px; font-size: 20px; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        button.menu {
          display: none; width: 48px; height: 48px; border: 0; border-radius: 50%;
          background: none; color: inherit; cursor: pointer; padding: 12px;
        }
        :host([narrow]) button.menu { display: inline-flex; }
        :host([narrow]) .title { margin-left: 0; }
        a.open {
          display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 18px;
          color: inherit; text-decoration: none; font-size: 14px; font-weight: 500;
          border: 1px solid currentColor; opacity: .92; white-space: nowrap;
        }
        a.open:hover { opacity: 1; background: rgba(255, 255, 255, .12); }
        svg { width: 24px; height: 24px; fill: currentColor; }
        a.open svg { width: 18px; height: 18px; }
        iframe { flex: 1 1 auto; min-height: 0; width: 100%; border: 0; background: var(--card-background-color, #fff); }
        @media (max-width: 420px) { a.open span { display: none; } a.open { padding: 6px; border-radius: 50%; } }
      </style>
      <header>
        <button class="menu" title="Menú" aria-label="Menú">
          <svg viewBox="0 0 24 24"><path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/></svg>
        </button>
        <div class="title"></div>
        <a class="open" target="_blank" rel="noopener" title="Abrir en una ventana">
          <svg viewBox="0 0 24 24"><path d="M14,3V5H17.59L7.76,14.83L9.17,16.24L19,6.41V10H21V3M19,19H5V5H12V3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19Z"/></svg>
          <span>Abrir en una ventana</span>
        </a>
      </header>
      <iframe allow="clipboard-write; microphone; notifications" referrerpolicy="no-referrer"></iframe>
    `;
    this._root.querySelector(".title").textContent = title;
    this._root.querySelector("a.open").href = url;
    this._root.querySelector("iframe").src = url;
    this._root.querySelector("iframe").title = title;
    this._root.querySelector("button.menu").addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    });
    this._update();
  }

  _update() {
    this.toggleAttribute("narrow", !!this._narrow);
  }
}

if (!customElements.get("compra-hub-panel")) customElements.define("compra-hub-panel", CompraHubPanel);
