/**
 * Dooya Cover Card — a custom Lovelace card shipped with the `dooya` integration.
 *
 * Usage:
 *   type: custom:dooya-cover-card
 *   entity: cover.your_shutter   # only required field
 *
 * Shows an animated roller shutter that tracks the estimated position,
 * up/stop/down controls, a position slider, preset chips and (for dooya
 * entities) the manual recalibration actions mark_open / mark_closed.
 */

const VERSION = "1.1.0";
// eslint-disable-next-line no-console
console.info(`%c DOOYA-COVER-CARD %c v${VERSION} `, "background:#e8833a;color:#fff;border-radius:3px 0 0 3px", "background:#c95d2e;color:#fff;border-radius:0 3px 3px 0");

const STRINGS = {
  en: {
    open: "Open",
    closed: "Closed",
    opening: "Opening…",
    closing: "Closing…",
    position: (p) => `Open ${p}%`,
    estimated: "Position is estimated from travel time",
    up: "Open",
    stop: "Stop",
    down: "Close",
    presets: { 0: "Closed", 100: "Open" },
    calibrate: "Recalibrate",
    markOpen: "Set as open",
    markClosed: "Set as closed",
    favorite: "Favorite",
    notFound: (e) => `Entity ${e} not found`,
  },
  fr: {
    open: "Ouvert",
    closed: "Fermé",
    opening: "Ouverture…",
    closing: "Fermeture…",
    position: (p) => `Ouvert à ${p}%`,
    estimated: "Position estimée d'après le temps de trajet",
    up: "Ouvrir",
    stop: "Stop",
    down: "Fermer",
    presets: { 0: "Fermé", 100: "Ouvert" },
    calibrate: "Recaler",
    markOpen: "Marquer ouvert",
    markClosed: "Marquer fermé",
    favorite: "Favori",
    notFound: (e) => `Entité ${e} introuvable`,
  },
};

class DooyaCoverCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("cover.")) {
      throw new Error("dooya-cover-card: an `entity` pointing to a cover.* is required");
    }
    this._config = config;
    this._root = null;
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature();
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  getCardSize() {
    return this._config && this._config.view === "compact" ? 2 : 5;
  }

  static getStubConfig(hass) {
    const reg = hass.entities || {};
    const covers = Object.keys(hass.states).filter((e) => e.startsWith("cover."));
    const dooya = covers.find((e) => reg[e] && reg[e].platform === "dooya");
    return { entity: dooya || covers[0] || "cover.example" };
  }

  static getConfigElement() {
    return document.createElement("dooya-cover-card-editor");
  }

  // ---- helpers ---------------------------------------------------------

  _t() {
    const lang = (this._hass && this._hass.language) || "en";
    return lang.startsWith("fr") ? STRINGS.fr : STRINGS.en;
  }

  _isDooya() {
    const reg = (this._hass && this._hass.entities) || {};
    const e = reg[this._config.entity];
    return !!(e && e.platform === "dooya");
  }

  _favoriteButton() {
    // Sibling button entity on the same device whose id mentions the
    // favorite position (entity ids derive from EN "favorite" or FR
    // "favori(te)" names, both matched by "favori").
    const reg = (this._hass && this._hass.entities) || {};
    const coverReg = reg[this._config.entity];
    const devId = coverReg && coverReg.device_id;
    if (!devId) return null;
    return (
      Object.keys(reg).find(
        (e) => e.startsWith("button.") && reg[e].device_id === devId && /favori/i.test(e)
      ) || null
    );
  }

  _signature() {
    if (!this._config || !this._hass) return null;
    const s = this._hass.states[this._config.entity];
    if (!s) return this._config.entity + ":none";
    const a = s.attributes;
    return `${this._config.entity}:${s.state}:${a.current_position}:${this._favoriteButton() || ""}`;
  }

  _call(domain, service, data) {
    this._hass.callService(domain, service, data);
  }

  // ---- render ----------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) return;
    const t = this._t();
    const st = this._hass.states[this._config.entity];
    this._ensureRoot();
    if (!st) {
      this._body.innerHTML = `<div class="warn">${t.notFound(this._config.entity)}</div>`;
      return;
    }

    const pos = st.attributes.current_position;
    const opening = st.state === "opening";
    const closing = st.state === "closing";
    const moving = opening || closing;
    const closed = st.state === "closed" || pos === 0;
    const name = this._config.name || st.attributes.friendly_name || "Cover";

    let stateLabel;
    if (opening) stateLabel = t.opening;
    else if (closing) stateLabel = t.closing;
    else if (pos == null) stateLabel = closed ? t.closed : t.open;
    else if (pos <= 0) stateLabel = t.closed;
    else if (pos >= 100) stateLabel = t.open;
    else stateLabel = t.position(pos);

    // Curtain covers the (100 - position)% upper part of the window.
    const curtainPct = pos == null ? (closed ? 100 : 0) : 100 - pos;

    const favBtn = this._favoriteButton();

    if (this._config.view === "compact") {
      const fillPct = pos != null ? pos : closed ? 0 : 100;
      this._body.innerHTML = `
        <div class="head chead">
          <div class="title">${name}</div>
          <div class="state ${moving ? "moving" : ""}" title="${t.estimated}">${stateLabel}</div>
        </div>
        <div class="compact">
          <div class="cbar" data-bar title="${t.estimated}">
            <div class="cfill ${moving ? "moving" : ""}" style="width:${fillPct}%"></div>
          </div>
          ${favBtn ? `<button class="ctl mini" data-fav="${favBtn}" title="${t.favorite}"><ha-icon icon="mdi:star"></ha-icon></button>` : ""}
          <button class="ctl mini ${opening ? "active" : ""}" data-act="open" title="${t.up}"><ha-icon icon="mdi:chevron-up"></ha-icon></button>
          <button class="ctl mini" data-act="stop" title="${t.stop}"><ha-icon icon="mdi:stop"></ha-icon></button>
          <button class="ctl mini ${closing ? "active" : ""}" data-act="close" title="${t.down}"><ha-icon icon="mdi:chevron-down"></ha-icon></button>
        </div>
      `;
      return;
    }

    const showPresets = this._config.show_presets !== false;
    const showCalib = this._config.show_calibration !== false && this._isDooya();

    let presetHtml = "";
    if (showPresets) {
      presetHtml =
        `<div class="chips presets">` +
        [0, 25, 50, 75, 100]
          .map((p) => {
            const label = t.presets[p] || `${p}%`;
            const active = pos != null && pos === p;
            return `<button class="chip ${active ? "active" : ""}" data-pos="${p}">${label}</button>`;
          })
          .join("") +
        (favBtn
          ? `<button class="chip star" data-fav="${favBtn}" title="${t.favorite}"><ha-icon icon="mdi:star"></ha-icon></button>`
          : "") +
        `</div>`;
    }

    let calibHtml = "";
    if (showCalib) {
      calibHtml = `
        <div class="calib">
          <span class="calib-label" title="${t.estimated}"><ha-icon icon="mdi:crosshairs-gps"></ha-icon>${t.calibrate}</span>
          <button class="chip small" data-act="mark_closed" title="${t.markClosed}"><ha-icon icon="mdi:arrow-collapse-down"></ha-icon><span>${t.closed}</span></button>
          <button class="chip small" data-act="mark_open" title="${t.markOpen}"><ha-icon icon="mdi:arrow-collapse-up"></ha-icon><span>${t.open}</span></button>
        </div>`;
    }

    this._body.innerHTML = `
      <div class="head">
        <div class="title">${name}</div>
        <div class="state ${moving ? "moving" : ""}" title="${t.estimated}">${stateLabel}</div>
      </div>
      <div class="hero">
        <div class="window" data-window title="${t.estimated}">
          <div class="sky">
            <div class="sun"></div>
            <div class="hill hill1"></div>
            <div class="hill hill2"></div>
          </div>
          <div class="curtain ${moving ? "moving" : ""}" style="height:${curtainPct}%">
            <div class="bar"></div>
          </div>
          <div class="pos-label">${pos != null ? pos + "%" : "?"}</div>
        </div>
        <div class="btns">
          <button class="ctl ${opening ? "active" : ""}" data-act="open" title="${t.up}"><ha-icon icon="mdi:chevron-up"></ha-icon></button>
          <button class="ctl stop" data-act="stop" title="${t.stop}"><ha-icon icon="mdi:stop"></ha-icon></button>
          <button class="ctl ${closing ? "active" : ""}" data-act="close" title="${t.down}"><ha-icon icon="mdi:chevron-down"></ha-icon></button>
        </div>
      </div>
      <div class="sliderrow">
        <ha-icon icon="mdi:window-shutter"></ha-icon>
        <input class="slider" type="range" min="0" max="100" step="1" value="${pos != null ? pos : 0}" data-slider/>
        <ha-icon icon="mdi:window-shutter-open"></ha-icon>
      </div>
      ${presetHtml}
      ${calibHtml}
    `;
  }

  _ensureRoot() {
    if (this._root) return;
    this.attachShadow({ mode: "open" });
    const card = document.createElement("ha-card");
    const style = document.createElement("style");
    style.textContent = this._css();
    this._body = document.createElement("div");
    this._body.className = "wrap";
    card.appendChild(this._body);
    this.shadowRoot.appendChild(style);
    this.shadowRoot.appendChild(card);
    this._root = card;
    this._body.addEventListener("click", (e) => this._onClick(e));
    this._body.addEventListener("change", (e) => this._onChange(e));
  }

  _onChange(e) {
    const s = e.target.closest("[data-slider]");
    if (!s) return;
    this._call("cover", "set_cover_position", {
      entity_id: this._config.entity,
      position: Number(s.value),
    });
  }

  _onClick(e) {
    const entity_id = this._config.entity;
    const w = e.target.closest("[data-window]");
    if (w && !e.target.closest("[data-slider]")) {
      // Click inside the window sets the position: top = closed curtain fully
      // raised (100 = open), bottom = fully lowered (0 = closed).
      const r = w.getBoundingClientRect();
      const frac = (e.clientY - r.top) / r.height;
      const target = Math.max(0, Math.min(100, Math.round((1 - frac) * 100)));
      this._call("cover", "set_cover_position", { entity_id, position: target });
      return;
    }
    const bar = e.target.closest("[data-bar]");
    if (bar) {
      // Horizontal position bar (compact view): left = closed, right = open.
      const r = bar.getBoundingClientRect();
      const frac = (e.clientX - r.left) / r.width;
      const target = Math.max(0, Math.min(100, Math.round(frac * 100)));
      this._call("cover", "set_cover_position", { entity_id, position: target });
      return;
    }
    const tgt = e.target.closest("[data-act],[data-pos],[data-fav]");
    if (!tgt) return;
    if (tgt.dataset.fav) {
      this._call("button", "press", { entity_id: tgt.dataset.fav });
      return;
    }
    const act = tgt.dataset.act;
    if (act === "open") this._call("cover", "open_cover", { entity_id });
    else if (act === "close") this._call("cover", "close_cover", { entity_id });
    else if (act === "stop") this._call("cover", "stop_cover", { entity_id });
    else if (act === "mark_open") this._call("dooya", "mark_open", { entity_id });
    else if (act === "mark_closed") this._call("dooya", "mark_closed", { entity_id });
    else if (tgt.dataset.pos != null)
      this._call("cover", "set_cover_position", { entity_id, position: Number(tgt.dataset.pos) });
  }

  _css() {
    return `
      ha-card { padding: 16px; }
      .head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }
      .title { font-size:1.15rem; font-weight:600; }
      .state { font-size:.85rem; color: var(--secondary-text-color); }
      .state.moving { color: var(--primary-color); }
      .hero { display:flex; justify-content:center; align-items:stretch; gap:18px; margin:4px 0 12px; }
      .window { position:relative; width:150px; height:170px; border-radius:10px; overflow:hidden; cursor:pointer;
                border:3px solid var(--divider-color); box-shadow: inset 0 0 12px rgba(0,0,0,.15); }
      .sky { position:absolute; inset:0; background:linear-gradient(#7ec3ef, #cfe9fa 70%); }
      .sun { position:absolute; top:14px; right:16px; width:26px; height:26px; border-radius:50%;
             background:#ffd75e; box-shadow:0 0 14px 4px rgba(255,215,94,.65); }
      .hill { position:absolute; bottom:-14px; border-radius:50%; background:#8fbf6b; }
      .hill1 { left:-30px; width:120px; height:56px; }
      .hill2 { right:-36px; width:140px; height:64px; background:#7bb25a; }
      .curtain { position:absolute; top:0; left:0; right:0; transition:height .9s linear;
                 background:repeating-linear-gradient(
                   var(--dooya-slat-color, #e2e2e2) 0px,
                   var(--dooya-slat-color, #e2e2e2) 9px,
                   var(--dooya-slat-shadow, #b9b9b9) 9px,
                   var(--dooya-slat-shadow, #b9b9b9) 11px); }
      .curtain .bar { position:absolute; bottom:0; left:0; right:0; height:6px;
                      background:var(--dooya-slat-shadow, #9d9d9d); border-radius:0 0 3px 3px; }
      .curtain.moving { box-shadow:0 2px 8px rgba(0,0,0,.25); }
      .pos-label { position:absolute; bottom:6px; right:8px; font-size:.78rem; font-weight:600;
                   color:rgba(0,0,0,.55); background:rgba(255,255,255,.6); border-radius:8px; padding:1px 6px;
                   pointer-events:none; }
      .btns { display:flex; flex-direction:column; justify-content:space-between; }
      .ctl { width:52px; flex:1; border:none; border-radius:12px; margin:3px 0; cursor:pointer;
             background: var(--divider-color); color: var(--primary-text-color); }
      .ctl ha-icon { --mdc-icon-size:26px; }
      .ctl.active { background: var(--primary-color); color: var(--text-primary-color,#fff); }
      .ctl.stop ha-icon { --mdc-icon-size:22px; }
      .sliderrow { display:flex; align-items:center; gap:10px; margin:2px 0 10px; }
      .sliderrow ha-icon { color: var(--secondary-text-color); --mdc-icon-size:20px; }
      .slider { flex:1; accent-color: var(--primary-color); }
      .chips { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0; }
      .presets .chip { flex:1; justify-content:center; }
      .chip { display:inline-flex; align-items:center; gap:6px; border:none; border-radius:18px; padding:7px 10px;
              background: var(--divider-color); color: var(--primary-text-color); cursor:pointer; font-size:.85rem; }
      .chip ha-icon { --mdc-icon-size:18px; }
      .chip.active { background: var(--primary-color); color: var(--text-primary-color,#fff); }
      .chip.small { padding:5px 10px; font-size:.8rem; }
      .calib { display:flex; align-items:center; gap:8px; margin-top:8px; }
      .calib-label { display:inline-flex; align-items:center; gap:4px; font-size:.8rem;
                     color: var(--secondary-text-color); }
      .calib-label ha-icon { --mdc-icon-size:16px; }
      .chip.star ha-icon { color:#f5a623; }
      .chip.star.active { background:#f5a623; }
      .chead { margin-bottom:6px; }
      .compact { display:flex; align-items:center; gap:8px; }
      .cbar { position:relative; flex:1; height:14px; border-radius:7px; overflow:hidden;
              background: var(--divider-color); cursor:pointer; }
      .cfill { position:absolute; top:0; left:0; bottom:0; border-radius:7px;
               background: var(--primary-color); transition:width .9s linear; }
      .cfill.moving { opacity:.75; }
      .ctl.mini { width:38px; height:32px; flex:none; margin:0; border-radius:9px; }
      .ctl.mini ha-icon { --mdc-icon-size:20px; }
      .ctl, .chip { transition: filter .15s ease, transform .1s ease, background .2s ease; }
      .ctl:hover, .chip:hover { filter: brightness(1.12); }
      .ctl:active, .chip:active { transform: scale(.95); }
      .warn { color: var(--error-color); padding:12px; }
    `;
  }
}

customElements.define("dooya-cover-card", DooyaCoverCard);

/** Visual editor: a native ha-form with a cover entity picker + options. */
class DooyaCoverCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass) return;
    const fr = (this._hass.language || "en").startsWith("fr");
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({
          entity: fr ? "Entité cover (requis)" : "Cover entity (required)",
          name: fr ? "Nom (optionnel)" : "Name (optional)",
          view: fr ? "Affichage" : "View",
          show_presets: fr ? "Afficher les positions prédéfinies" : "Show preset positions",
          show_calibration: fr ? "Afficher le recalage manuel" : "Show manual recalibration",
        }[s.name] || s.name);
      this._form.addEventListener("value-changed", (e) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: e.detail.value },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { domain: "cover" } } },
      { name: "name", selector: { text: {} } },
      {
        name: "view",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "normal", label: fr ? "Normale" : "Normal" },
              { value: "compact", label: fr ? "Réduite" : "Compact" },
            ],
          },
        },
      },
      { name: "show_presets", selector: { boolean: {} } },
      { name: "show_calibration", selector: { boolean: {} } },
    ];
    this._form.data = { view: "normal", show_presets: true, show_calibration: true, ...this._config };
  }
}

customElements.define("dooya-cover-card-editor", DooyaCoverCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "dooya-cover-card",
  name: "Dooya Cover Card",
  description: "Animated roller-shutter card for Dooya RF covers (position, presets, recalibration).",
  preview: true,
  documentationURL: "https://github.com/dasimon135/ha-dooya",
});
