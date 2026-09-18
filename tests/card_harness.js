// Runs the shipped card under Node with just enough DOM to render it.
//
// Usage: node card_harness.js '<scenario json>'
// Scenario: { config, state: { state, attributes }, language, click?: { selector, clientX?, clientY? } }
//       or: { editor: { config }, language } — exercises the visual editor instead
// Prints: { html, calls, size } — the rendered body markup, every service call
// made, and what the card answers for `getCardSize()`.
// In editor mode: { data, schema } — the values the form is filled with, and the
// name of every field it offers.
//
// The card only ever writes innerHTML strings and reads a handful of element
// methods, so a fake element is enough to exercise its real render and click
// paths without a browser.

"use strict";

const fs = require("fs");
const path = require("path");

class FakeElement {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.innerHTML = "";
    this.className = "";
    this.dataset = {};
    this.listeners = {};
    this.classList = { toggle: () => {}, add: () => {}, remove: () => {} };
  }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener() {}
  setAttribute() {}
  attachShadow() { this.shadowRoot = new FakeElement("#shadow"); return this.shadowRoot; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  dispatchEvent() { return true; }
}

const registry = {};
global.HTMLElement = FakeElement;
global.customElements = {
  get: (name) => registry[name],
  define: (name, cls) => { registry[name] = cls; },
};
global.document = {
  createElement: (tag) => new FakeElement(tag),
  querySelectorAll: () => [],
  body: new FakeElement("body"),
};
global.window = global;
global.console = { ...console, info: () => {} };

const cardFile = path.join(
  __dirname, "..", "custom_components", "dooya", "frontend", "dooya-cover-card.js"
);
// eslint-disable-next-line no-eval
(0, eval)(fs.readFileSync(cardFile, "utf8"));

const scenario = JSON.parse(process.argv[2]);

// Editor mode: no card, no state — just the form the visual editor builds from
// a stored config. What matters is which field names it offers and the values
// it fills them with, since that is what gets written back to the dashboard.
if (scenario.editor) {
  const Editor = registry["dooya-cover-card-editor"];
  const editor = new Editor();
  editor.setConfig(scenario.editor.config);
  editor.hass = { language: scenario.language || "en", states: {}, entities: {} };
  process.stdout.write(
    JSON.stringify({
      data: editor._form.data,
      schema: editor._form.schema.map((f) => f.name),
    })
  );
  return;
}

const Card = registry["dooya-cover-card"];
const card = new Card();
const calls = [];
const entity = scenario.config.entity;
card.setConfig(scenario.config);
card.hass = {
  language: scenario.language || "en",
  states: { [entity]: { entity_id: entity, ...scenario.state } },
  entities: { [entity]: { platform: "dooya", device_id: "dev1" } },
  callService: (domain, service, data) => calls.push({ domain, service, data }),
};

if (scenario.click) {
  // A click on an element carrying the given data attribute, e.g. data-act="open"
  // or data-window. `closest` answers for that selector family only.
  const { selector, value, clientX = 0, clientY = 0 } = scenario.click;
  const target = {
    dataset: selector === "data-act" ? { act: value } : selector === "data-pos" ? { pos: String(value) } : {},
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 100, height: 100 }),
  };
  target.closest = (sel) => {
    if (selector === "data-window" && sel === "[data-window]") return target;
    if (selector !== "data-window" && sel.includes(`[${selector}]`)) return target;
    return null;
  };
  card._onClick({ target, clientX, clientY });
}

process.stdout.write(
  JSON.stringify({ html: card._body.innerHTML, calls, size: card.getCardSize() })
);
