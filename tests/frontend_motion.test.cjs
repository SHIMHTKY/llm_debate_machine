const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const frontend = path.join(__dirname, "../frontend");
const flush = () => new Promise((resolve) => setImmediate(resolve));

class Element {
  constructor() {
    const classes = new Set();
    this.classList = {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, value) => value ? classes.add(name) : classes.delete(name),
    };
    this.children = [];
    this.animations = [];
    this.opacity = "1";
    this.translate = "none";
    this.scrollTop = 0;
    this.clientHeight = 100;
    this.scrollCalls = [];
  }
  querySelector(selector) { return selector === ".modal-card" ? this.card : this.backdrop; }
  prepend(element) { this.backdrop = element; }
  setAttribute() {}
  animate(frames, options) {
    let resolve, reject;
    const finished = new Promise((done, fail) => { resolve = done; reject = fail; });
    const animation = { frames, options, finished, finish: resolve, cancel: () => reject(new Error("cancelled")) };
    this.animations.push(animation);
    return animation;
  }
  insertBefore(node, reference) {
    node.remove();
    const index = reference ? this.children.indexOf(reference) : this.children.length;
    this.children.splice(index, 0, node);
    node.parent = this;
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  replaceWith(node) {
    const parent = this.parent;
    const index = parent.children.indexOf(this);
    parent.children[index] = node;
    node.parent = parent;
    this.parent = null;
  }
  get scrollHeight() { return this.children.length * 100; }
  scrollTo(options) { this.scrollCalls.push(options); this.scrollTop = Math.max(0, options.top - this.clientHeight); }
  set innerHTML(value) { this.content = { firstElementChild: Object.assign(new Element(), { markup: value }) }; }
}

function fixture(reduce = false) {
  const preference = { matches: reduce, addEventListener(_name, handler) { this.handler = handler; } };
  const context = vm.createContext({
    window: { matchMedia: () => preference, addEventListener() {} },
    getComputedStyle: (element) => ({ opacity: element.opacity, translate: element.translate, getPropertyValue: () => "" }),
    document: { documentElement: {}, createElement: () => new Element() },
  });
  vm.runInContext(readFileSync(path.join(frontend, "motion.js"), "utf8"), context);
  const motion = vm.runInContext("uiMotion", context);
  const modal = new Element();
  modal.classList.add("hidden");
  modal.card = new Element();
  return { context, motion, modal, preference };
}

test("modal panels remain opaque, and repeated opens do not restart motion", async () => {
  const { motion, modal } = fixture();
  motion.modal(modal, true);
  motion.modal(modal, true);
  assert.equal(modal.card.animations.length, 1);
  assert.equal(modal.card.animations[0].frames.some((frame) => "opacity" in frame), false);
  assert.equal(modal.backdrop.animations[0].frames[0].opacity, 0);
  assert.equal(modal.classList.contains("hidden"), false);
  modal.card.animations[0].finish(); modal.backdrop.animations[0].finish();
  await flush();
});

test("reopen cancels the old exit and its delayed cleanup", async () => {
  const { motion, modal } = fixture();
  let cleaned = false;
  motion.modal(modal, true);
  motion.modal(modal, false, { onHidden: () => { cleaned = true; } });
  const oldExit = [...modal.card.animations, ...modal.backdrop.animations];
  modal.card.translate = "0 3px";
  modal.backdrop.opacity = ".4";
  motion.modal(modal, true);
  oldExit.forEach((animation) => animation.finish());
  await flush();
  assert.equal(cleaned, false);
  assert.equal(modal.classList.contains("hidden"), false);
  assert.equal(modal.classList.contains("modal-visible"), true);
  assert.equal(modal.card.inert, false);
  assert.equal(modal.card.animations.at(-1).frames[0].translate, "0 3px");
  assert.equal(modal.backdrop.animations.at(-1).frames[0].opacity, ".4");
});

test("exit blocks controls until both panel and backdrop finish", async () => {
  const { motion, modal } = fixture();
  let cleaned = 0;
  motion.modal(modal, true);
  motion.modal(modal, false, { onHidden: () => cleaned++ });
  assert.equal(modal.card.inert, true);
  modal.card.animations.at(-1).finish();
  await flush();
  assert.equal(modal.classList.contains("hidden"), false);
  modal.backdrop.animations.at(-1).finish();
  await flush();
  assert.equal(modal.classList.contains("hidden"), true);
  assert.equal(cleaned, 1);
});

test("immediate close cannot be revived by unfinished entry work", async () => {
  const { motion, modal } = fixture();
  motion.modal(modal, true);
  motion.modal(modal, false, { immediate: true });
  modal.card.animations.forEach((animation) => animation.finish());
  await flush();
  assert.equal(modal.classList.contains("hidden"), true);
  assert.equal(modal.classList.contains("modal-visible"), false);
});

test("reduced motion skips delays and reacts to a preference change mid-exit", async () => {
  const { motion, modal, preference } = fixture(true);
  motion.modal(modal, true);
  motion.modal(modal, false);
  assert.equal(modal.card.animations.length, 0);
  assert.equal(modal.classList.contains("hidden"), true);
  preference.matches = false;
  motion.modal(modal, true);
  motion.modal(modal, false);
  preference.matches = true;
  preference.handler();
  await flush();
  assert.equal(modal.classList.contains("hidden"), true);
});

test("task bar reappearance does not run obsolete cleanup or alter horizontal centering", async () => {
  const { motion } = fixture();
  const bar = new Element();
  bar.classList.add("hidden");
  let cleared = false;
  motion.presence(bar, true);
  motion.presence(bar, false, { onHidden: () => { cleared = true; } });
  motion.presence(bar, true);
  await flush();
  assert.equal(bar.classList.contains("hidden"), false);
  assert.equal(bar.inert, false);
  assert.equal(cleared, false);
  assert.equal(bar.animations[0].frames.some((frame) => "transform" in frame), false);
});

function threadFixture(reduce = false) {
  const { context } = fixture(reduce);
  const revealed = [];
  vm.runInContext(readFileSync(path.join(frontend, "app.js"), "utf8"), context);
  context.container = new Element();
  context.revealed = revealed;
  vm.runInContext("els.chatThread = container; state.currentDebateMode = 'live'; uiMotion.reveal = (node) => revealed.push(node);", context);
  context.renderMessageRow = (message) => `<div>${message.id}:${message.content}</div>`;
  context.renderTypingRow = (status) => `<div>${status.content}</div>`;
  const messages = Array.from({ length: 4 }, (_, index) => ({ id: String(index), content: "hello" }));
  return { context, container: context.container, revealed, messages };
}

test("unchanged live messages and typing indicators retain DOM identity", () => {
  const { context, container, messages, revealed } = threadFixture();
  context.renderLiveThread({ id: "a" }, messages, { content: "thinking" });
  const original = [...container.children];
  context.renderLiveThread({ id: "a" }, messages, { content: "thinking" });
  assert.deepEqual(container.children, original);
  assert.equal(revealed.length, 0);
});

test("only new rows animate; reading older messages does not force scrolling", () => {
  const { context, container, messages, revealed } = threadFixture();
  context.renderLiveThread({ id: "a" }, messages, null);
  container.scrollTop = 0;
  context.renderLiveThread({ id: "a" }, [...messages, { id: "new", content: "new" }], null);
  assert.equal(revealed.length, 1);
  assert.equal(container.scrollTop, 0);
});

test("following the bottom scrolls new content, without smooth scroll under reduced motion", () => {
  const { context, container, messages } = threadFixture(true);
  context.renderLiveThread({ id: "a" }, messages, null);
  container.scrollTop = container.scrollHeight - container.clientHeight;
  context.renderLiveThread({ id: "a" }, [...messages, { id: "new", content: "new" }], null);
  assert.equal(container.scrollTop, container.scrollHeight);
  assert.equal(container.scrollCalls.length, 0);
});

test("switching sessions and rewinding do not reuse stale rows or replay entry effects", () => {
  const { context, container, messages, revealed } = threadFixture();
  context.renderLiveThread({ id: "a" }, messages, null);
  const old = container.children[0];
  context.renderLiveThread({ id: "b" }, messages.slice(0, 2), null);
  assert.notEqual(container.children[0], old);
  context.renderLiveThread({ id: "b" }, messages.slice(0, 1), null);
  assert.equal(container.children.length, 1);
  assert.equal(revealed.length, 0);
});

test("removing a recipient changes business state immediately and cannot clear a later choice", () => {
  const { context } = threadFixture();
  const tag = new Element();
  tag.isConnected = true;
  tag.contains = () => true;
  context.HTMLElement = Element;
  context.tag = tag;
  context.document.body = {};
  context.document.activeElement = context.document.body;
  let finish, focused = false;
  const motion = vm.runInContext("uiMotion", context);
  motion.presence = (_element, _visible, options) => { finish = options.onHidden; };
  context.renderUserTargetControls = () => {};
  context.focusTarget = { focus: () => { focused = true; } };
  vm.runInContext("els.userTargetTagSlot = { querySelector: () => tag }; els.toggleUserTargetMenuBtn = focusTarget; state.userMessageTargetRole = 'pro';", context);
  context.handleUserTargetTagAction({ target: { closest: () => ({}) } });
  assert.equal(vm.runInContext("state.userMessageTargetRole", context), "");
  vm.runInContext("state.userMessageTargetRole = 'con';", context);
  finish();
  assert.equal(vm.runInContext("state.userMessageTargetRole", context), "con");
  assert.equal(focused, true);
});
