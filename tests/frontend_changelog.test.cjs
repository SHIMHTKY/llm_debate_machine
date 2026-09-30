const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const frontend = path.join(__dirname, "../frontend");
const source = readFileSync(path.join(frontend, "app.js"), "utf8");

function element() {
  const classes = new Set(["hidden"]);
  return {
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, value) => value ? classes.add(name) : classes.delete(name),
    },
    textContent: "", innerHTML: "", scrollTop: 0,
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

function fixture() {
  const context = vm.createContext({
    window: { addEventListener() {}, clearTimeout() {}, setTimeout() {} },
    requestAnimationFrame: (callback) => callback(), AbortController,
    modal: element(), viewer: element(),
    uiMotion: { modal(target, visible) {
      target.classList.toggle("hidden", !visible);
      target.classList.toggle("modal-visible", visible);
    } },
  });
  vm.runInContext(source, context);
  vm.runInContext("els.changelogModal = modal; els.changelogViewer = viewer;", context);
  return context;
}

test("extracts only release notes, retaining nested version headings", () => {
  const context = fixture();
  assert.equal(context.extractChangelog("## 项目介绍\n介绍\n## 更新日志\n### v2\n- 修复\n## 其他\n不要显示"), "### v2\n- 修复");
});

test("supports CRLF, alternate heading and trailing heading markers", () => {
  assert.equal(fixture().extractChangelog("\uFEFF# 更新记录 ###\r\n- 新功能\r\n"), "- 新功能");
});

test("does not mistake fenced examples for section boundaries", () => {
  const content = "~~~md\n## 更新日志\n示例\n~~~\n## 更新日志\n```md\n## 仍在代码内\n```\n- 正文";
  assert.equal(fixture().extractChangelog(content), "```md\n## 仍在代码内\n```\n- 正文");
});

test("missing or empty release section never falls back to the project introduction", () => {
  const context = fixture();
  for (const content of ["", "## 项目介绍\n不应显示", "## 更新日志\n\n## 其他\n内容"]) {
    assert.equal(context.extractChangelog(content), "暂无更新记录。");
  }
});

test("current workspace file produces release notes without its introduction", () => {
  const content = fixture().extractChangelog(readFileSync(path.join(frontend, "workspace.md"), "utf8"));
  assert.match(content, /9\.28/);
  assert.doesNotMatch(content, /项目介绍|本项目是一个/);
});

test("closing and reopening discards the previous response", async () => {
  const context = fixture();
  const pending = [];
  context.fetchWithTimeout = (_url, options) => new Promise((resolve) => pending.push({ resolve, options }));
  const first = context.openChangelog();
  context.closeChangelog();
  assert.equal(pending[0].options.signal.aborted, true);
  const second = context.openChangelog();
  pending[1].resolve({ ok: true, text: async () => "## 更新日志\n- 最新记录" });
  await second;
  pending[0].resolve({ ok: true, text: async () => "## 更新日志\n- 过期记录" });
  await first;
  assert.match(context.viewer.innerHTML, /最新记录/);
  assert.doesNotMatch(context.viewer.innerHTML, /过期记录/);
  assert.equal(context.viewer.attributes["aria-busy"], "false");
  assert.equal(context.modal.classList.contains("modal-visible"), true);
});

test("HTTP failures are shown in the dialog and can be retried", async () => {
  const context = fixture();
  context.fetchWithTimeout = async () => ({ ok: false, status: 503 });
  await context.openChangelog();
  assert.match(context.viewer.textContent, /HTTP 503/);
  assert.equal(context.viewer.attributes["aria-busy"], "false");
  context.fetchWithTimeout = async () => ({ ok: true, text: async () => "## 更新日志\n- 恢复正常" });
  await context.openChangelog();
  assert.match(context.viewer.innerHTML, /恢复正常/);
});
