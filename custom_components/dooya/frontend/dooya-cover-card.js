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
 *
 * A cover whose device class is `awning` is drawn as a striped canopy on a
 * facade instead, with Home Assistant's awning control icons and labels that
 * say deployed / retracted (issue #50).
 */

// Console banner only. Cache-busting uses a digest of this file (see
// __init__.py::_async_register_card), so this does not need to be kept in sync
// with any Python constant.
const VERSION = "1.5.0";
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
    closeDialog: "Close",
    awning: {
      opening: "Deploying…",
      closing: "Retracting…",
      up: "Deploy",
      down: "Retract",
      open: "Deployed",
      closed: "Retracted",
      presets: { 0: "Retracted", 100: "Deployed" },
      markOpen: "Set as deployed",
      markClosed: "Set as retracted",
    },
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
    closeDialog: "Fermer",
    awning: {
      opening: "Déploiement…",
      closing: "Repli…",
      up: "Déployer",
      down: "Replier",
      open: "Déployé",
      closed: "Replié",
      presets: { 0: "Replié", 100: "Déployé" },
      markOpen: "Marquer déployé",
      markClosed: "Marquer replié",
    },
  },
};

// Awning glyphs drawn in currentColor, so they follow the theme like ha-icon.
const AWNING_GLYPH = {
  retracted:
    '<svg class="aw-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="7" width="20" height="4" rx="2"/></svg>',
  deployed:
    '<svg class="aw-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="3" rx="1.5"/>' +
    '<path d="M4 7H20L22 16H2Z"/><path d="M2 17H22V19Q20 21 18 19Q16 21 14 19Q12 21 10 19Q8 21 6 19Q4 21 2 19Z"/></svg>',
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
    if (this._dialogCard) this._dialogCard.hass = hass;
  }

  getCardSize() {
    const layout = this._layout();
    if (layout === "tile") return 1;
    return layout === "compact" ? 2 : 5;
  }

  /**
   * Which of the three sizes to draw: `full`, `compact` or `tile`.
   *
   * `layout` is the option, and the name the other cards in this family use.
   * `view` was this card's own spelling of it, with `normal` where the others
   * say `full`; both are still read so a dashboard written against the old
   * names keeps working. A config carrying both is not a config anyone wrote
   * on purpose -- the editor never emits one -- so `layout`, the current name,
   * decides.
   *
   * Safe before `setConfig`: `getCardSize` can be called first.
   */
  _layout() {
    const config = this._config || {};
    if (config.layout) return config.layout;
    if (config.view) return config.view === "normal" ? "full" : config.view;
    return "full";
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

  _isAwning(st) {
    return !!(st && st.attributes && st.attributes.device_class === "awning");
  }

  // Facade with a striped canopy hanging from its cassette. `pos` is the
  // Home Assistant position: 0 retracted, 100 fully deployed. Colours live in
  // the stylesheet's scene fence, so every element here only carries a class.
  _awningScene(pos) {
    const k = Math.max(0, Math.min(100, pos == null ? 0 : pos)) / 100;
    const cx0 = 34, cx1 = 156, cy = 38, ground = 142;
    const drop = 62 * k, spread = 12 * k;
    const bx0 = cx0 - spread, bx1 = cx1 + spread, by = cy + 6 + drop;
    const stripes = 9;
    const r = (v) => Math.round(v * 10) / 10;
    let fabric = "";
    if (k > 0.01) {
      const vh = 9 * Math.min(k * 3, 1), sag = 4 * Math.min(k * 3, 1);
      for (let i = 0; i < stripes; i++) {
        const t0 = i / stripes, t1 = (i + 1) / stripes;
        const tx0 = cx0 + (cx1 - cx0) * t0, tx1 = cx0 + (cx1 - cx0) * t1;
        const fx0 = bx0 + (bx1 - bx0) * t0, fx1 = bx0 + (bx1 - bx0) * t1;
        const tone = i % 2 ? "b" : "a";
        fabric +=
          `<polygon class="aw-stripe ${tone}" points="${r(tx0)},${cy + 5} ${r(tx1)},${cy + 5} ${r(fx1)},${r(by)} ${r(fx0)},${r(by)}"/>` +
          // the valance under this stripe, one scallop wide
          `<path class="aw-stripe ${tone}" d="M${r(fx0)} ${r(by + 2)}H${r(fx1)}V${r(by + vh)}Q${r((fx0 + fx1) / 2)} ${r(by + vh + sag)} ${r(fx0)} ${r(by + vh)}Z"/>`;
      }
      fabric +=
        `<line class="aw-arm" x1="${cx0 + 6}" y1="${cy + 30}" x2="${r(bx0 + 4)}" y2="${r(by)}"/>` +
        `<line class="aw-arm" x1="${cx1 - 6}" y1="${cy + 30}" x2="${r(bx1 - 4)}" y2="${r(by)}"/>` +
        `<rect class="aw-bar" x="${r(bx0 - 1)}" y="${r(by - 1)}" width="${r(bx1 - bx0 + 2)}" height="4" rx="2"/>`;
    }
    const half = (cx1 - cx0) / 2 + spread, shadeH = r(26 * k);
    return `
      <svg class="awning-scene" viewBox="0 0 190 170" preserveAspectRatio="none" aria-hidden="true">
        <rect class="aw-sky" width="190" height="24"/>
        <circle class="aw-sun" cx="170" cy="12" r="7"/>
        <rect class="aw-roof" y="20" width="190" height="6"/>
        <rect class="aw-wall" y="26" width="190" height="${ground - 26}"/>
        <rect class="aw-glass" x="52" y="62" width="86" height="${ground - 62}"/>
        <line class="aw-frame" x1="95" y1="62" x2="95" y2="${ground}"/>
        <rect class="aw-terrace" y="${ground}" width="190" height="${170 - ground}"/>
        <path class="aw-joint" d="M0 ${ground + 12}H190M30 ${ground}l-12 28M75 ${ground}l-4 28M115 ${ground}l4 28M160 ${ground}l12 28"/>
        <polygon class="aw-shade" style="opacity:${r(0.2 * Math.min(k * 2, 1))}"
          points="${r(95 - half)},${ground} ${r(95 + half)},${ground} ${r(95 + half + 10)},${ground + shadeH} ${r(95 - half - 10)},${ground + shadeH}"/>
        <rect class="aw-box" x="${cx0 - 3}" y="${cy - 4}" width="${cx1 - cx0 + 6}" height="10" rx="4"/>
        ${fabric}
      </svg>`;
  }

  _isDooya() {
    const reg = (this._hass && this._hass.entities) || {};
    const e = reg[this._config.entity];
    return !!(e && e.platform === "dooya");
  }

  _scene() {
    // Window scenery follows the sun: dawn / day / dusk / night.
    // Uses sun.sun when available (season-accurate), falls back to the clock.
    const sun = this._hass && this._hass.states["sun.sun"];
    if (sun && sun.attributes && typeof sun.attributes.elevation === "number") {
      const el = sun.attributes.elevation;
      if (el < -6) return "night";
      if (el < 8) return sun.attributes.rising ? "dawn" : "dusk";
      return "day";
    }
    const h = new Date().getHours();
    if (h < 6 || h >= 22) return "night";
    if (h < 9) return "dawn";
    if (h >= 19) return "dusk";
    return "day";
  }

  _favoriteButton() {
    // Sibling button entity on the same device. Matched on the unique-id
    // suffix the integration assigns (`<entry_id>_favorite`, see button.py),
    // never on the entity id: entity ids are derived from the *translated*
    // name, so an id-based match silently breaks on any new locale.
    const reg = (this._hass && this._hass.entities) || {};
    const coverReg = reg[this._config.entity];
    const devId = coverReg && coverReg.device_id;
    if (!devId) return null;
    return (
      Object.keys(reg).find((e) => {
        const ent = reg[e];
        if (!e.startsWith("button.") || ent.device_id !== devId) return false;
        const uid = ent.unique_id || "";
        // Fall back to the entity id for HA versions that do not expose
        // unique_id on the frontend entity registry.
        return uid ? uid.endsWith("_favorite") : /favori/i.test(e);
      }) || null
    );
  }

  _esc(value) {
    // Every interpolation below lands in innerHTML: shutter names and card
    // config are user-controlled text, not markup.
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
    );
  }

  _signature() {
    if (!this._config || !this._hass) return null;
    // The language belongs in the signature: every label rendered below is
    // translated, so a language change has to re-render even when the shutter
    // itself has not moved. Without it the card stays in the previous language
    // until the next state change.
    const lang = this._hass.language || "";
    const s = this._hass.states[this._config.entity];
    if (!s) return `${this._config.entity}:none:${lang}`;
    const a = s.attributes;
    return `${this._config.entity}:${s.state}:${a.current_position}:${this._favoriteButton() || ""}:${this._scene()}:${lang}`;
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
    this._root.classList.toggle("tilecard", this._layout() === "tile");
    if (!st) {
      this._body.innerHTML = `<div class="warn">${this._esc(t.notFound(this._config.entity))}</div>`;
      return;
    }

    const pos = st.attributes.current_position;
    const opening = st.state === "opening";
    const closing = st.state === "closing";
    const moving = opening || closing;
    const closed = st.state === "closed" || pos === 0;
    const name = this._esc(
      this._config.name || st.attributes.friendly_name || "Cover"
    );
    const awning = this._isAwning(st);
    // An awning keeps Home Assistant's open / closed state words, and says
    // deploying / retracting for everything that describes the fabric moving.
    const ta = awning ? { ...t, ...t.awning } : t;
    const openIcon = awning ? "mdi:arrow-expand-horizontal" : "mdi:chevron-up";
    const closeIcon = awning ? "mdi:arrow-collapse-horizontal" : "mdi:chevron-down";

    let stateLabel;
    if (opening) stateLabel = ta.opening;
    else if (closing) stateLabel = ta.closing;
    else if (pos == null) stateLabel = closed ? t.closed : t.open;
    else if (pos <= 0) stateLabel = t.closed;
    else if (pos >= 100) stateLabel = t.open;
    else stateLabel = t.position(pos);

    // Curtain covers the (100 - position)% upper part of the window.
    const curtainPct = pos == null ? (closed ? 100 : 0) : 100 - pos;

    const favBtn = this._favoriteButton();

    // Tile: an ultra-compact row aligned with HA's native tile cards. Tapping
    // the icon/name opens the full card in a popup (see _openCardDialog).
    if (this._layout() === "tile") {
      const icon = closed ? "mdi:window-shutter" : "mdi:window-shutter-open";
      const dot = awning
        ? AWNING_GLYPH[closed ? "retracted" : "deployed"]
        : `<ha-icon icon="${icon}"></ha-icon>`;
      this._body.innerHTML = `
        <div class="tile ${closed ? "off" : ""}">
          <div class="tinfo" data-act="tileinfo" role="button" tabindex="0" aria-label="${name}">
            <div class="tdot">${dot}</div>
            <div class="ttext">
              <span class="tname">${name}</span>
              <span class="tsub">${stateLabel}</span>
            </div>
          </div>
          <div class="tctl">
            <button class="tbtn ${opening ? "active" : ""}" data-act="open" aria-label="${ta.up}"><ha-icon icon="${openIcon}"></ha-icon></button>
            <button class="tbtn" data-act="stop" aria-label="${t.stop}"><ha-icon icon="mdi:stop"></ha-icon></button>
            <button class="tbtn ${closing ? "active" : ""}" data-act="close" aria-label="${ta.down}"><ha-icon icon="${closeIcon}"></ha-icon></button>
          </div>
        </div>`;
      return;
    }

    if (this._layout() === "compact") {
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
          ${favBtn ? `<button class="ctl mini" data-fav="${this._esc(favBtn)}" title="${t.favorite}"><ha-icon icon="mdi:star"></ha-icon></button>` : ""}
          <button class="ctl mini ${opening ? "active" : ""}" data-act="open" title="${ta.up}"><ha-icon icon="${openIcon}"></ha-icon></button>
          <button class="ctl mini" data-act="stop" title="${t.stop}"><ha-icon icon="mdi:stop"></ha-icon></button>
          <button class="ctl mini ${closing ? "active" : ""}" data-act="close" title="${ta.down}"><ha-icon icon="${closeIcon}"></ha-icon></button>
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
            const label = ta.presets[p] || `${p}%`;
            const active = pos != null && pos === p;
            return `<button class="chip ${active ? "active" : ""}" data-pos="${p}">${label}</button>`;
          })
          .join("") +
        (favBtn
          ? `<button class="chip star" data-fav="${this._esc(favBtn)}" title="${t.favorite}"><ha-icon icon="mdi:star"></ha-icon></button>`
          : "") +
        `</div>`;
    }

    let calibHtml = "";
    if (showCalib) {
      calibHtml = `
        <div class="calib">
          <span class="calib-label" title="${t.estimated}"><ha-icon icon="mdi:crosshairs-gps"></ha-icon>${t.calibrate}</span>
          <button class="chip small" data-act="mark_closed" title="${ta.markClosed}"><ha-icon icon="${awning ? closeIcon : "mdi:arrow-collapse-down"}"></ha-icon><span>${ta.closed}</span></button>
          <button class="chip small" data-act="mark_open" title="${ta.markOpen}"><ha-icon icon="${awning ? openIcon : "mdi:arrow-collapse-up"}"></ha-icon><span>${ta.open}</span></button>
        </div>`;
    }

    this._body.innerHTML = `
      <div class="head">
        <div class="title">${name}</div>
        <div class="state ${moving ? "moving" : ""}" title="${t.estimated}">${stateLabel}</div>
      </div>
      <div class="hero">
        <div class="window ${awning ? "awning" : ""} sc-${this._scene()}" data-window title="${t.estimated}">
          ${awning ? this._awningScene(pos) : `
          <div class="sky">
            <div class="stars"></div>
            <div class="sun"></div>
            <div class="moon"></div>
            <div class="hill hill1"></div>
            <div class="hill hill2"></div>
          </div>
          <div class="curtain ${moving ? "moving" : ""}" style="height:${curtainPct}%">
            <div class="bar"></div>
          </div>`}
          <div class="pos-label">${pos != null ? pos + "%" : "?"}</div>
        </div>
        <div class="btns">
          <button class="ctl ${opening ? "active" : ""}" data-act="open" title="${ta.up}"><ha-icon icon="${openIcon}"></ha-icon></button>
          <button class="ctl stop" data-act="stop" title="${t.stop}"><ha-icon icon="mdi:stop"></ha-icon></button>
          <button class="ctl ${closing ? "active" : ""}" data-act="close" title="${ta.down}"><ha-icon icon="${closeIcon}"></ha-icon></button>
        </div>
      </div>
      <div class="sliderrow">
        ${awning ? AWNING_GLYPH.retracted : `<ha-icon icon="mdi:window-shutter"></ha-icon>`}
        <input class="slider" type="range" min="0" max="100" step="1" value="${pos != null ? pos : 0}" data-slider/>
        ${awning ? AWNING_GLYPH.deployed : `<ha-icon icon="mdi:window-shutter-open"></ha-icon>`}
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
    this._body.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.closest("[data-act='tileinfo']")) {
        e.preventDefault();
        this._onTileTap();
      }
    });
    this._body.addEventListener("change", (e) => this._onChange(e));
  }

  // Tile tap → full card in a popup (or HA's native more-info when
  // `tile_tap: more-info` is configured).
  _onTileTap() {
    if (this._config.tile_tap === "more-info") {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this._config.entity },
          bubbles: true,
          composed: true,
        })
      );
      return;
    }
    this._openCardDialog();
  }

  // Self-contained modal overlay (no external dependency). Mounted on
  // document.body so it is never clipped by the tile's grid cell; HA theme
  // custom properties inherit through the shadow boundary.
  _openCardDialog() {
    if (this._dialog) return;
    // Self-heal: clear any orphaned popup a prior instance may have left, so a
    // stale full-screen overlay can never linger and swallow page clicks.
    document.querySelectorAll("[data-dooya-popup]").forEach((h) => h.remove());
    const host = document.createElement("div");
    host.setAttribute("data-dooya-popup", "");
    const sr = host.attachShadow({ mode: "open" });
    sr.innerHTML = `<style>
      .scrim { position:fixed; inset:0; z-index:1000; display:grid; place-items:center;
        box-sizing:border-box; padding:16px; background:rgba(0,0,0,.5); animation:dcf .15s ease; }
      @keyframes dcf { from{opacity:0} to{opacity:1} }
      .wrap { position:relative; width:100%; max-width:400px; }
      .x { position:absolute; top:-12px; right:-12px; z-index:1; width:34px; height:34px;
        border-radius:50%; border:none; cursor:pointer; font-size:17px; line-height:1;
        display:grid; place-items:center;
        background:var(--card-background-color,#fff); color:var(--primary-text-color,#222);
        box-shadow:0 2px 10px rgba(0,0,0,.35); }
      .x:focus-visible { outline:2px solid var(--primary-color,#03a9f4); outline-offset:2px; }
      @media (prefers-reduced-motion: reduce) { .scrim { animation:none } }
    </style>
    <div class="scrim"><div class="wrap"><button class="x" aria-label="${this._t().closeDialog}">✕</button></div></div>`;
    const card = document.createElement("dooya-cover-card");
    card.setConfig({ ...this._config, view: "normal", layout: "full" });
    card.hass = this._hass;
    sr.querySelector(".wrap").appendChild(card);
    const close = () => this._closeCardDialog();
    // Tapping anywhere off the card (scrim OR the empty area around it) closes
    // it — far easier to dismiss on a phone than aiming at a thin margin.
    sr.querySelector(".scrim").addEventListener("click", (e) => { if (!e.composedPath().includes(card)) close(); });
    sr.querySelector(".x").addEventListener("click", close);
    this._dialogKey = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", this._dialogKey);
    document.body.appendChild(host);
    this._dialog = host;
    this._dialogCard = card;
  }

  _closeCardDialog() {
    if (this._dialogKey) window.removeEventListener("keydown", this._dialogKey);
    if (this._dialog) this._dialog.remove();
    this._dialog = null;
    this._dialogCard = null;
    this._dialogKey = null;
  }

  disconnectedCallback() { this._closeCardDialog(); }

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
      // raised (100 = open), bottom = fully lowered (0 = closed). An awning
      // hangs down as it deploys, so there low in the picture is more open.
      const r = w.getBoundingClientRect();
      const frac = (e.clientY - r.top) / r.height;
      const awning = this._isAwning(this._hass.states[entity_id]);
      const share = awning ? frac : 1 - frac;
      const target = Math.max(0, Math.min(100, Math.round(share * 100)));
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
    if (act === "tileinfo") this._onTileTap();
    else if (act === "open") this._call("cover", "open_cover", { entity_id });
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
      /* Tile (ultra-compact) layout — config: view: tile */
      ha-card.tilecard { padding: 10px 12px; }
      .tile { display:flex; align-items:center; gap:12px; }
      .tinfo { flex:1 1 auto; min-width:0; display:flex; align-items:center; gap:12px;
               cursor:pointer; border-radius:8px; outline:none; }
      .tinfo:focus-visible { box-shadow: 0 0 0 2px var(--dooya-accent, var(--primary-color)); }
      .tdot { flex:0 0 auto; width:36px; height:36px; border-radius:50%; display:grid; place-items:center;
              background: var(--divider-color); color: var(--secondary-text-color); }
      .tile:not(.off) .tdot { background: color-mix(in srgb, var(--dooya-accent, var(--primary-color)) 22%, var(--card-background-color));
              color: var(--dooya-accent, var(--primary-color)); }
      .tdot ha-icon { --mdc-icon-size:24px; }
      .ttext { min-width:0; display:flex; flex-direction:column; gap:0; }
      .tname { font-weight:600; font-size:14px; line-height:20px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .tsub { font-size:12px; line-height:16px; color: var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .tctl { flex:0 0 auto; display:flex; gap:6px; }
      .tbtn { width:36px; height:34px; border-radius:9px; border:1px solid var(--divider-color);
              background: var(--card-background-color); color: var(--primary-text-color); cursor:pointer;
              display:grid; place-items:center; transition: transform .12s, border-color .2s, background .2s; }
      .tbtn ha-icon { --mdc-icon-size:20px; }
      .tbtn.active { background: var(--dooya-accent, var(--primary-color)); color: var(--text-primary-color,#fff); border-color: var(--dooya-accent, var(--primary-color)); }
      .tbtn:hover { border-color: var(--dooya-accent, var(--primary-color)); }
      .tbtn:active { transform: scale(.9); }
      .head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }
      .title { font-size:1.15rem; font-weight:600; }
      .state { font-size:.85rem; color: var(--secondary-text-color); }
      .state.moving { color: var(--dooya-accent, var(--primary-color)); }
      .hero { display:flex; justify-content:center; align-items:stretch; gap:18px; margin:4px 0 12px; }
      .window { position:relative; width:150px; height:170px; border-radius:10px; overflow:hidden; cursor:pointer;
                border:3px solid var(--divider-color); box-shadow: inset 0 0 12px rgba(0,0,0,.15); }
      /* scene: the window is an illustration of the time of day, not chrome — its colours are deliberately literal */
      .sky { position:absolute; inset:0; background:linear-gradient(#7ec3ef, #cfe9fa 70%); }
      .sun { position:absolute; top:14px; right:16px; width:26px; height:26px; border-radius:50%;
             background:#ffd75e; box-shadow:0 0 14px 4px rgba(255,215,94,.65); }
      .hill { position:absolute; bottom:-14px; border-radius:50%; background:#8fbf6b; }
      .hill1 { left:-30px; width:120px; height:56px; }
      .hill2 { right:-36px; width:140px; height:64px; background:#7bb25a; }
      .moon, .stars { display:none; }
      .window.sc-dawn .sky { background:linear-gradient(#8fb7e8, #ffb26b 55%, #ffe3c2); }
      .window.sc-dusk .sky { background:linear-gradient(#7a5f9e, #ff8e63 55%, #ffd1a1); }
      .window.sc-night .sky { background:linear-gradient(#101c33, #2e4a6b); }
      .window.sc-dawn .sun, .window.sc-dusk .sun { top:58%; background:#ff9a3d;
        box-shadow:0 0 16px 6px rgba(255,140,60,.55); }
      .window.sc-night .sun { display:none; }
      .window.sc-night .moon { display:block; position:absolute; top:16px; right:20px;
        width:22px; height:22px; border-radius:50%; background:#e8ecf5;
        box-shadow:0 0 10px 2px rgba(220,230,255,.4), inset -5px -3px 0 0 #c2c9da; }
      .window.sc-night .stars { display:block; position:absolute; top:10px; left:14px;
        width:3px; height:3px; border-radius:50%; background:#fff;
        box-shadow:26px 8px 0 0 #fff, 52px 2px 0 0 rgba(255,255,255,.8),
                   74px 14px 0 0 rgba(255,255,255,.7), 12px 26px 0 0 rgba(255,255,255,.6),
                   60px 30px 0 0 rgba(255,255,255,.75); }
      .window.sc-night .hill { filter:brightness(.45) saturate(.7); }
      .window.sc-dawn .hill, .window.sc-dusk .hill { filter:brightness(.85) saturate(1.1) hue-rotate(-12deg); }
      .window.sc-night .pos-label { color:rgba(255,255,255,.8); background:rgba(0,0,0,.35); }
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
      .window.awning { width:190px; }
      .awning-scene { position:absolute; inset:0; width:100%; height:100%; display:block; }
      .aw-sky { fill:#8fcaf0; }
      .aw-sun { fill:#ffd75e; }
      .aw-roof { fill:#8a5a44; }
      .aw-wall { fill:#e8dcc6; }
      .aw-glass { fill:#6f8fae; stroke:#f6f1e8; stroke-width:3; }
      .aw-frame { stroke:#f6f1e8; stroke-width:2.5; }
      .aw-terrace { fill:#cdbb9f; }
      .aw-joint { stroke:#b9a684; stroke-width:1; fill:none; }
      .aw-shade { fill:#000; }
      .aw-box { fill:#5d5d5d; }
      .aw-arm { stroke:#6b6b6b; stroke-width:2; }
      .aw-bar { fill:#5f5f5f; }
      .aw-stripe.a { fill: var(--dooya-awning-fabric, #efe7d8); }
      .aw-stripe.b { fill: var(--dooya-awning-stripe, #c4553b); }
      .window.sc-night .awning-scene { filter:brightness(.5) saturate(.8); }
      .window.sc-dawn .aw-sky { fill:#ffb26b; }
      .window.sc-dusk .aw-sky { fill:#ff8e63; }
      .window.sc-night .aw-sky { fill:#101c33; }
      /* /scene */
      .aw-ico { width:20px; height:20px; fill:currentColor; flex:none; }
      .tdot .aw-ico { width:24px; height:24px; }
      .btns { display:flex; flex-direction:column; justify-content:space-between; }
      .ctl { width:52px; flex:1; border:none; border-radius:12px; margin:3px 0; cursor:pointer;
             background: var(--divider-color); color: var(--primary-text-color); }
      .ctl ha-icon { --mdc-icon-size:26px; }
      .ctl.active { background: var(--dooya-accent, var(--primary-color)); color: var(--text-primary-color,#fff); }
      .ctl.stop ha-icon { --mdc-icon-size:22px; }
      .sliderrow { display:flex; align-items:center; gap:10px; margin:2px 0 10px; }
      .sliderrow ha-icon { color: var(--secondary-text-color); --mdc-icon-size:20px; }
      .slider { flex:1; accent-color: var(--dooya-accent, var(--primary-color)); }
      .chips { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0; }
      .presets .chip { flex:1; justify-content:center; }
      .chip { display:inline-flex; align-items:center; gap:6px; border:none; border-radius:18px; padding:7px 10px;
              background: var(--divider-color); color: var(--primary-text-color); cursor:pointer; font-size:.85rem; }
      .chip ha-icon { --mdc-icon-size:18px; }
      .chip.active { background: var(--dooya-accent, var(--primary-color)); color: var(--text-primary-color,#fff); }
      .chip.small { padding:5px 10px; font-size:.8rem; }
      .calib { display:flex; align-items:center; gap:8px; margin-top:8px; }
      .calib-label { display:inline-flex; align-items:center; gap:4px; font-size:.8rem;
                     color: var(--secondary-text-color); }
      .calib-label ha-icon { --mdc-icon-size:16px; }
      .chip.star ha-icon { color:var(--dooya-star, #f5a623); }
      .chip.star.active { background:var(--dooya-star, #f5a623); }
      .chead { margin-bottom:6px; }
      .compact { display:flex; align-items:center; gap:8px; }
      .cbar { position:relative; flex:1; height:14px; border-radius:7px; overflow:hidden;
              background: var(--divider-color); cursor:pointer; }
      .cfill { position:absolute; top:0; left:0; bottom:0; border-radius:7px;
               background: var(--dooya-accent, var(--primary-color)); transition:width .9s linear; }
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

// Guarded: the module can be evaluated twice on one page (auto-loaded by the
// integration AND listed as a dashboard resource, or two cache-busted URLs),
// and a second define() throws. rf-fan-card has the same guard.
if (!customElements.get("dooya-cover-card")) {
  customElements.define("dooya-cover-card", DooyaCoverCard);
}

/** Visual editor: a native ha-form with a cover entity picker + options. */
class DooyaCoverCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = DooyaCoverCardEditor._normalise(config || {});
    this._render();
  }

  /**
   * Rewrite a stored `view` as `layout`, and drop it.
   *
   * The form writes back the whole config, so a card left carrying both names
   * could be saved with the two disagreeing -- and the card would then obey
   * `layout` while the editor showed `view`. Translating on the way in means
   * anything saved from the editor carries one spelling. The card itself still
   * reads `view` for dashboards nobody has opened in the editor.
   */
  static _normalise(config) {
    if (!config.view) return config;
    const { view, ...rest } = config;
    return { layout: rest.layout || (view === "normal" ? "full" : view), ...rest };
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
    // Reassigned on every render, like `schema` below: assigning it once inside
    // the block above would close over the `fr` of the first render and leave
    // the field labels in the original language after a language change.
    this._form.computeLabel = (s) =>
      ({
        entity: fr ? "Entité cover (requis)" : "Cover entity (required)",
        name: fr ? "Nom (optionnel)" : "Name (optional)",
        layout: fr ? "Affichage" : "Layout",
        show_presets: fr ? "Afficher les positions prédéfinies" : "Show preset positions",
        show_calibration: fr ? "Afficher le recalage manuel" : "Show manual recalibration",
      }[s.name] || s.name);
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { domain: "cover" } } },
      { name: "name", selector: { text: {} } },
      {
        name: "layout",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "full", label: fr ? "Complète" : "Full" },
              { value: "compact", label: fr ? "Réduite" : "Compact" },
              { value: "tile", label: fr ? "Tuile" : "Tile" },
            ],
          },
        },
      },
      { name: "show_presets", selector: { boolean: {} } },
      { name: "show_calibration", selector: { boolean: {} } },
    ];
    this._form.data = { layout: "full", show_presets: true, show_calibration: true, ...this._config };
  }
}

if (!customElements.get("dooya-cover-card-editor")) {
  customElements.define("dooya-cover-card-editor", DooyaCoverCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "dooya-cover-card")) {
  window.customCards.push({
    type: "dooya-cover-card",
    name: "Dooya Cover Card",
    description: "Animated card for Dooya RF shutters and awnings (position, presets, recalibration).",
    preview: true,
    documentationURL: "https://github.com/dasimon135/ha-dooya",
  });
}
