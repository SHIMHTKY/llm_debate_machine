const ROLE_LABELS = {
  judge: "裁判",
  pro: "正方",
  con: "反方",
  user: "用户消息",
  system: "系统",
};

const MODAL_MOTION_MS = 180;
const SESSION_SUMMARY_REFRESH_MS = 2000;
const NUMBER_FORMATTER = new Intl.NumberFormat("zh-CN");
const DEFAULT_CONTEXT_ROUNDS = 3;
const MIN_CONTEXT_ROUNDS = 2;
const MAX_CONTEXT_ROUNDS = 6;
const TOOL_TEMPLATES = [
  {
    id: "tavily_search",
    name: "Tavily 搜索",
    description: "网页搜索工具，用于补充事实、数据和案例。",
    defaults: {
      name: "Tavily Search",
      type: "tavily_search",
      timeout: 60,
      max_results: 5,
      search_depth: "advanced",
    },
  },
];
const CONFIG_MANAGER_TABS = [
  { id: "supplier", label: "配置供应商", listTitle: "供应商列表", countLabel: "供应商" },
  { id: "tool", label: "配置工具", listTitle: "工具列表", countLabel: "工具" },
  { id: "debater", label: "配置辩手", listTitle: "辩手列表", countLabel: "辩手" },
];
const MIN_DEBATE_ROUNDS = 2;
const MAX_DEBATE_ROUNDS = 10;
const DEFAULT_MIN_ROUNDS = 4;
const DEFAULT_MAX_ROUNDS = 6;

const state = {
  settings: null,
  sessions: [],
  archivedSessions: [],
  records: { detail: [], error: [] },
  currentSession: null,
  currentSessionId: null,
  currentRecord: null,
  typing: null,
  eventSource: null,
  eventSourceSessionId: "",
  eventSourceReconnectTimer: null,
  inlineError: "",
  selectedPresetEditorId: "",
  selectedSupplierId: "",
  selectedToolConfigId: "",
  presetManagerOpen: false,
  presetManagerTab: "debater",
  noticeText: "",
  workspaceText: "",
  darkMode: false,
  userComposerExpanded: false,
  stoppingSessionId: "",
  togglingPauseSessionId: "",
  sendingUserMessageSessionId: "",
  retractingUserMessageSessionId: "",
  rewindingMessageActionKey: "",
  titleEditModalTimer: null,
  editingTitleSessionId: "",
  savingTitleSessionId: "",
  savingHomeBinding: false,
  settingsModalTimer: null,
  archivedModalTimer: null,
  markdownPreviewModalTimer: null,
  markdownPreview: null,
  sessionSummaryRefreshTimer: null,
  sessionSummaryRefreshInFlight: false,
  reviewTopicExpanded: false,
  expandedEvaluationGroups: {},
  userMessageTargetRole: "",
  userTargetMenuOpen: false,
  userTargetSubmenuOpen: false,
  userTargetSubmenuCloseTimer: null,
  userComposerDisabled: false,
  currentView: "debate",
  currentDebateMode: "",
  presetManagerEntering: false,
};

const els = {};

window.addEventListener("DOMContentLoaded", init);

async function init() {
  state.darkMode = readThemePreference();
  applyTheme(state.darkMode);
  cacheElements();
  bindEvents();
  await Promise.all([loadSettings(), loadSessions(), loadArchivedSessions(), loadRecords(), loadNotice(), loadWorkspace()]);
  renderCurrentSession();
}

function cacheElements() {
  els.historyList = document.getElementById("historyList");
  els.chatThread = document.getElementById("chatThread");
  els.reviewThread = document.getElementById("reviewThread");
  els.currentHeadline = document.getElementById("currentHeadline");
  els.livePanelTitle = document.getElementById("livePanelTitle");
  els.sessionMeta = document.getElementById("sessionMeta");
  els.reviewMeta = document.getElementById("reviewMeta");
  els.runStatusBadge = document.getElementById("runStatusBadge");
  els.liveStatusBadge = document.getElementById("liveStatusBadge");
  els.reviewStatusBadge = document.getElementById("reviewStatusBadge");
  els.toggleReviewTopicBtn = document.getElementById("toggleReviewTopicBtn");
  els.reviewTopicDisclosure = document.getElementById("reviewTopicDisclosure");
  els.reviewTopicField = document.getElementById("reviewTopicField");
  els.previewErrorBtn = document.getElementById("previewErrorBtn");
  els.stopDebateBtn = document.getElementById("stopDebateBtn");
  els.liveComposerShell = document.getElementById("liveComposerShell");
  els.userInterjectionInput = document.getElementById("userInterjectionInput");
  els.toggleUserTargetMenuBtn = document.getElementById("toggleUserTargetMenuBtn");
  els.userTargetControl = document.getElementById("userTargetControl");
  els.userTargetMenu = document.getElementById("userTargetMenu");
  els.userTargetMenuAnchor = document.getElementById("userTargetMenuAnchor");
  els.openUserTargetSubmenuBtn = document.getElementById("openUserTargetSubmenuBtn");
  els.userTargetSubmenu = document.getElementById("userTargetSubmenu");
  els.userTargetTagSlot = document.getElementById("userTargetTagSlot");
  els.toggleUserComposerExpandBtn = document.getElementById("toggleUserComposerExpandBtn");
  els.sendUserMessageBtn = document.getElementById("sendUserMessageBtn");
  els.queuedUserMessageSlot = document.getElementById("queuedUserMessageSlot");
  els.userComposerHint = document.getElementById("userComposerHint");
  els.exportSimpleBtn = document.getElementById("exportSimpleBtn");
  els.exportDetailBtn = document.getElementById("exportDetailBtn");
  els.newDebateBtn = document.getElementById("newDebateBtn");
  els.topicInput = document.getElementById("topicInput");
  els.homeDebaterBinding = document.getElementById("homeDebaterBinding");
  els.minRoundsInput = document.getElementById("minRoundsInput");
  els.maxRoundsInput = document.getElementById("maxRoundsInput");
  els.startDebateBtn = document.getElementById("startDebateBtn");
  els.debateForm = document.getElementById("debateForm");
  els.settingsModal = document.getElementById("settingsModal");
  els.archivedModal = document.getElementById("archivedModal");
  els.markdownPreviewModal = document.getElementById("markdownPreviewModal");
  els.closeMarkdownPreviewBtn = document.getElementById("closeMarkdownPreviewBtn");
  els.downloadMarkdownPreviewBtn = document.getElementById("downloadMarkdownPreviewBtn");
  els.markdownPreviewEyebrow = document.getElementById("markdownPreviewEyebrow");
  els.markdownPreviewTitle = document.getElementById("markdownPreviewTitle");
  els.markdownPreviewViewer = document.getElementById("markdownPreviewViewer");
  els.titleEditModal = document.getElementById("titleEditModal");
  els.titleEditInput = document.getElementById("titleEditInput");
  els.cancelTitleEditBtn = document.getElementById("cancelTitleEditBtn");
  els.confirmTitleEditBtn = document.getElementById("confirmTitleEditBtn");
  els.settingsForm = document.getElementById("settingsForm");
  els.presetManagerPanel = document.getElementById("presetManagerPanel");
  els.debateView = document.getElementById("debateView");
  els.recordsView = document.getElementById("recordsView");
  els.landingPanel = document.getElementById("landingPanel");
  els.livePanel = document.getElementById("livePanel");
  els.reviewPanel = document.getElementById("reviewPanel");
  els.landingNotice = document.getElementById("landingNotice");
  els.workspaceViewer = document.getElementById("workspaceViewer");
  els.detailRecordsList = document.getElementById("detailRecordsList");
  els.errorRecordsList = document.getElementById("errorRecordsList");
  els.recordViewer = document.getElementById("recordViewer");
  els.recordViewerTitle = document.getElementById("recordViewerTitle");
  els.archivedList = document.getElementById("archivedList");
  els.deleteRecordBtn = document.getElementById("deleteRecordBtn");
  els.resultWinner = document.getElementById("resultWinner");
  els.resultScores = document.getElementById("resultScores");
  els.resultUsage = document.getElementById("resultUsage");
  els.resultHighlights = document.getElementById("resultHighlights");
  els.resultConclusion = document.getElementById("resultConclusion");
  els.resultErrorBox = document.getElementById("resultErrorBox");
}

function bindEvents() {
  els.debateForm.addEventListener("submit", startDebate);
  els.homeDebaterBinding?.addEventListener("change", handleHomeBindingChange);
  els.homeDebaterBinding?.addEventListener("click", handleHomeBindingClick);
  document.getElementById("settingsBtn").addEventListener("click", openSettings);
  document.getElementById("closeSettingsBtn").addEventListener("click", closeSettings);
  document.getElementById("saveSettingsBtn").addEventListener("click", saveSettings);
  els.newDebateBtn.addEventListener("click", openNewDebate);
  const recordsButton = document.getElementById("recordsBtn");
  recordsButton?.addEventListener("click", async () => {
    switchView("records");
    await loadRecords();
  });
  document.getElementById("backToDebateBtn").addEventListener("click", () => {
    switchView("debate");
    renderCurrentSession();
  });
  document.getElementById("archivedSessionsBtn").addEventListener("click", openArchivedModal);
  document.getElementById("refreshSessionsBtn").addEventListener("click", async () => {
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  });
  document.getElementById("refreshRecordsBtn").addEventListener("click", loadRecords);
  document.getElementById("closeArchivedBtn").addEventListener("click", closeArchivedModal);
  els.deleteRecordBtn.addEventListener("click", deleteCurrentRecord);
  els.toggleReviewTopicBtn.addEventListener("click", toggleReviewTopicExpanded);
  els.previewErrorBtn.addEventListener("click", () => openMarkdownPreview("error"));
  els.closeMarkdownPreviewBtn.addEventListener("click", closeMarkdownPreviewModal);
  els.downloadMarkdownPreviewBtn.addEventListener("click", downloadMarkdownPreview);
  els.markdownPreviewModal.addEventListener("click", (event) => {
    if (event.target === els.markdownPreviewModal) {
      closeMarkdownPreviewModal();
    }
  });
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  els.toggleUserTargetMenuBtn.addEventListener("click", toggleUserTargetMenu);
  els.userTargetMenuAnchor.addEventListener("pointerenter", cancelUserTargetSubmenuClose);
  els.openUserTargetSubmenuBtn.addEventListener("pointerenter", openUserTargetSubmenu);
  els.openUserTargetSubmenuBtn.addEventListener("click", toggleUserTargetSubmenu);
  els.userTargetMenuAnchor.addEventListener("pointerleave", scheduleUserTargetSubmenuClose);
  els.userTargetSubmenu.addEventListener("pointerenter", cancelUserTargetSubmenuClose);
  els.userTargetSubmenu.addEventListener("pointerleave", closeUserTargetSubmenu);
  els.userTargetSubmenu.addEventListener("click", handleUserTargetSelection);
  els.userTargetTagSlot.addEventListener("click", handleUserTargetTagAction);
  els.resultHighlights.addEventListener("click", handleEvaluationGroupClick);
  els.resultHighlights.addEventListener("keydown", handleEvaluationGroupKeydown);
  els.stopDebateBtn.addEventListener("click", stopCurrentDebate);
  els.toggleUserComposerExpandBtn.addEventListener("click", toggleUserComposerExpanded);
  els.sendUserMessageBtn.addEventListener("click", sendUserInterjection);
  els.userInterjectionInput.addEventListener("keydown", handleUserInterjectionKeydown);
  els.currentHeadline.addEventListener("dblclick", openTitleEditModal);
  els.cancelTitleEditBtn.addEventListener("click", closeTitleEditModal);
  els.confirmTitleEditBtn.addEventListener("click", submitTitleEdit);
  els.titleEditInput.addEventListener("keydown", handleTitleEditKeydown);
  els.titleEditModal.addEventListener("click", (event) => {
    if (event.target === els.titleEditModal) {
      closeTitleEditModal();
    }
  });
  els.chatThread.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action='retract-user-message']");
    if (action) {
      await retractUserInterjection();
      return;
    }
    const rewindAction = event.target.closest("[data-action='rewind-message']");
    if (rewindAction) {
      await handleMessageRewindAction(rewindAction.dataset.messageId);
    }
  });
  els.queuedUserMessageSlot.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action='retract-user-message']");
    if (action) {
      await retractUserInterjection();
    }
  });
  els.reviewThread.addEventListener("click", async (event) => {
    const rewindAction = event.target.closest("[data-action='rewind-message']");
    if (rewindAction) {
      await handleMessageRewindAction(rewindAction.dataset.messageId);
    }
  });
  els.exportSimpleBtn.addEventListener("click", () => openMarkdownPreview("simple"));
  els.exportDetailBtn.addEventListener("click", () => openMarkdownPreview("detail"));

  els.historyList.addEventListener("click", async (event) => {
    const deleteButton = event.target.closest("[data-action='delete-session']");
    if (deleteButton) {
      await deleteSession(deleteButton.dataset.sessionId);
      return;
    }

    const archiveButton = event.target.closest("[data-action='archive-session']");
    if (archiveButton) {
      await archiveSession(archiveButton.dataset.sessionId);
      return;
    }

    const item = event.target.closest("[data-session-id]");
    if (item) {
      await openSession(item.dataset.sessionId, true, true);
    }
  });

  els.archivedList.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]");
    if (!action) {
      return;
    }
    const sessionId = action.dataset.sessionId;
    if (!sessionId) {
      return;
    }
    if (action.dataset.action === "view-archived") {
      closeArchivedModal();
      await openSession(sessionId, true, true);
      return;
    }
    if (action.dataset.action === "restore-session") {
      await restoreArchivedSession(sessionId);
      return;
    }
    if (action.dataset.action === "delete-archived-session") {
      await deleteSession(sessionId, { reloadArchived: true });
    }
  });

  [els.detailRecordsList, els.errorRecordsList].forEach((container) => {
    container.addEventListener("click", async (event) => {
      const item = event.target.closest("[data-record-kind]");
      if (item) {
        await openRecord(item.dataset.recordKind, item.dataset.sessionId);
      }
    });
  });

  els.settingsForm.addEventListener("input", handleSettingsFormInput);
  els.settingsForm.addEventListener("change", handleSettingsFormChange);
  els.settingsForm.addEventListener("click", handleSettingsFormClick);
  els.presetManagerPanel.addEventListener("input", handlePresetManagerInput);
  els.presetManagerPanel.addEventListener("change", handlePresetManagerChange);
  els.presetManagerPanel.addEventListener("click", handlePresetManagerClick);
}

async function api(path, options = {}) {
  const finalOptions = { ...options };
  if (finalOptions.body && !finalOptions.headers) {
    finalOptions.headers = { "Content-Type": "application/json" };
  }
  const response = await fetch(path, finalOptions);
  if (!response.ok) {
    const error = new Error(await readErrorMessage(response));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function readErrorMessage(response) {
  try {
    const payload = await response.json();
    return payload.detail || payload.message || JSON.stringify(payload);
  } catch {
    return response.statusText || "请求失败";
  }
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  ensureSelectedPresetEditor();
  ensureSelectedSupplierEditor();
  ensureSelectedToolEditor();
  renderHomeDebaterBinding();
}

async function loadNotice() {
  try {
    const response = await fetch(`/assets/Notice.txt?ts=${Date.now()}`);
    if (!response.ok) {
      throw new Error("failed");
    }
    const nextText = (await response.text()).trim();
    const changed = nextText !== state.noticeText;
    state.noticeText = nextText;
    return changed;
  } catch {
    const fallback = "请在 frontend/Notice.txt 中维护这里的须知内容。";
    const changed = fallback !== state.noticeText;
    state.noticeText = fallback;
    return changed;
  }
}

async function loadWorkspace() {
  try {
    const response = await fetch(`/assets/workspace.md?ts=${Date.now()}`);
    if (!response.ok) {
      throw new Error("failed");
    }
    state.workspaceText = (await response.text()).trim();
  } catch {
    state.workspaceText = "# Workspace\n- 请在 frontend/workspace.md 中维护这里的内容。";
  }
}

function readThemePreference() {
  try {
    return window.localStorage.getItem("llm-debate-theme") === "dark";
  } catch {
    return false;
  }
}

function setDarkMode(enabled) {
  state.darkMode = Boolean(enabled);
  applyTheme(state.darkMode);
  try {
    window.localStorage.setItem("llm-debate-theme", state.darkMode ? "dark" : "light");
  } catch {
    // ignore persistence errors
  }
}

function applyTheme(enabled) {
  document.body.classList.toggle("theme-dark", Boolean(enabled));
}

async function saveSettings() {
  try {
    const selectedPresetId = state.selectedPresetEditorId;
    await persistSettings();
    ensureSelectedPresetEditor(selectedPresetId);
    closeSettings();
  } catch (error) {
    const message = error?.message || "保存设置失败。";
    window.alert(message);
  }
}

async function persistSettings() {
  const payload = buildSettingsPayload();
  state.settings = await api("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  ensurePresetManagerSelections();
  renderHomeDebaterBinding();
  return state.settings;
}

function buildSettingsPayload() {
  const judge = state.settings?.judge || {};
  return {
    judge: serializeJudgeSettings(judge),
    model_suppliers: getModelSuppliers().slice(0, getSupplierLimit()).map((supplier) => serializeSupplierSettings(supplier)),
    tool_configs: getToolConfigs().slice(0, getToolLimit()).map((toolConfig) => serializeToolConfig(toolConfig)),
    pro_preset_id: state.settings?.pro_preset_id || "",
    con_preset_id: state.settings?.con_preset_id || "",
    context_rounds: parseContextRoundsValue(state.settings?.context_rounds),
    usage_tracking_enabled: Boolean(state.settings?.usage_tracking_enabled),
    debater_presets: getDebaterPresets().slice(0, getPresetLimit()).map((preset) => serializeDebaterPresetSettings(preset)),
  };
}

function serializeJudgeSettings(judge) {
  return {
    supplier_id: String(judge?.supplier_id || "").trim(),
    model: String(judge?.model || "").trim(),
    azure_deployment: String(judge?.azure_deployment || "").trim(),
    max_tokens: Number(judge?.max_tokens || 0),
    extra_body: parseExtraBodyPayload(judge?.extra_body_input ?? judge?.extra_body, "裁判模型"),
  };
}

function serializeSupplierSettings(supplier) {
  return {
    id: String(supplier?.id || "").trim(),
    name: String(supplier?.name || "").trim(),
    provider: String(supplier?.provider || "chatopenai").trim(),
    api_key: String(supplier?.api_key || "").trim(),
    base_url: String(supplier?.base_url || "").trim(),
    api_version: String(supplier?.api_version || "").trim(),
    timeout: Number(supplier?.timeout || 0),
    max_retries: Number(supplier?.max_retries || 0),
  };
}

function serializeDebaterPresetSettings(preset) {
  return {
    id: String(preset?.id || "").trim(),
    name: String(preset?.name || "").trim(),
    supplier_id: String(preset?.supplier_id || "").trim(),
    model: String(preset?.model || "").trim(),
    azure_deployment: String(preset?.azure_deployment || "").trim(),
    max_tokens: Number(preset?.max_tokens || 0),
    extra_body: parseExtraBodyPayload(preset?.extra_body_input ?? preset?.extra_body, preset?.name || "辩手配置"),
    tool_selection: serializeToolSelection(preset?.tool_selection || {}),
  };
}

function serializeToolConfig(toolConfig) {
  return {
    id: String(toolConfig?.id || "").trim(),
    name: String(toolConfig?.name || "").trim(),
    template_id: String(toolConfig?.template_id || toolConfig?.type || "tavily_search").trim(),
    type: String(toolConfig?.type || "tavily_search").trim(),
    enabled: Boolean(toolConfig?.enabled),
    api_key: String(toolConfig?.api_key || "").trim(),
    timeout: Number(toolConfig?.timeout || 0),
    max_results: Number(toolConfig?.max_results || 0),
    search_depth: String(toolConfig?.search_depth || "advanced").trim(),
  };
}

function serializeToolSelection(selection) {
  const rawIds = Array.isArray(selection?.enabled_tool_ids) ? selection.enabled_tool_ids : [];
  const availableIds = new Set(getToolConfigs().map((toolConfig) => String(toolConfig.id || "")));
  return {
    enabled_tool_ids: rawIds
      .map((toolId) => String(toolId || "").trim())
      .filter((toolId, index, arr) => toolId && availableIds.has(toolId) && arr.indexOf(toolId) === index),
    mode: String(selection?.mode || "bind_tools").trim(),
    max_tool_rounds: Number(selection?.max_tool_rounds || 0),
  };
}

function serializeModelSettings(config, includeSearch, configLabel = "模型配置") {
  const payload = {
    provider: String(config?.provider || "chatopenai").trim(),
    model: String(config?.model || "").trim(),
    api_key: String(config?.api_key || "").trim(),
    base_url: String(config?.base_url || "").trim(),
    azure_deployment: String(config?.azure_deployment || "").trim(),
    api_version: String(config?.api_version || "").trim(),
    max_tokens: Number(config?.max_tokens || 0),
    timeout: Number(config?.timeout || 0),
    max_retries: Number(config?.max_retries || 0),
    extra_body: parseExtraBodyPayload(config?.extra_body_input ?? config?.extra_body, configLabel),
  };
  return payload;
}

function parseContextRoundsValue(rawValue) {
  const parsed = Number(String(rawValue ?? "").trim());
  if (!Number.isInteger(parsed) || parsed < MIN_CONTEXT_ROUNDS || parsed > MAX_CONTEXT_ROUNDS) {
    throw new Error(`上下文轮数必须是 ${MIN_CONTEXT_ROUNDS} 到 ${MAX_CONTEXT_ROUNDS} 之间的整数。`);
  }
  return parsed;
}

function cloneObjectValue(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return JSON.parse(JSON.stringify(value));
}

function formatExtraBodyInput(value) {
  if (typeof value === "string") {
    return value;
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return JSON.stringify(value, null, 2);
  }
  return "";
}

function parseLooseObjectText(text) {
  const candidates = [text];
  const normalized = text
    .replace(/\bTrue\b/g, "true")
    .replace(/\bFalse\b/g, "false")
    .replace(/\bNone\b/g, "null");
  if (normalized !== text) {
    candidates.push(normalized);
  }

  let lastError = null;
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed;
      }
      lastError = new Error("not-object");
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("invalid");
}

function extractDebaterSpeechText(text) {
  const raw = String(text || "").trim();
  if (!raw || !raw.includes("{") || !raw.includes("speech")) {
    return "";
  }

  try {
    const parsed = parseLooseObjectText(raw);
    if (typeof parsed.speech === "string" && parsed.speech.trim()) {
      return parsed.speech.trim();
    }
    if (parsed.speech != null) {
      return String(parsed.speech).trim();
    }
  } catch {
    const match = raw.match(/"speech"\s*:\s*"((?:\\.|[^"\\])*)"/s);
    if (!match) {
      return "";
    }
    try {
      return JSON.parse(`"${match[1]}"`).trim();
    } catch {
      return match[1].replace(/\\"/g, "\"").replace(/\\n/g, "\n").trim();
    }
  }
  return "";
}

function stripDebateMarkdownStructure(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const cleanedLines = [];

  for (const rawLine of lines) {
    const stripped = rawLine.trim();
    let plainLine = stripped.replace(/[*_`]+/g, "");
    plainLine = plainLine.replace(/^[#>\s]+/g, "").trim();

    if (!plainLine) {
      if (cleanedLines.length && cleanedLines[cleanedLines.length - 1] !== "") {
        cleanedLines.push("");
      }
      continue;
    }

    if (/^-{3,}$/.test(plainLine)) {
      continue;
    }

    for (const label of ["回应观众", "本轮发言正文"]) {
      if (plainLine === label || plainLine === `${label}：` || plainLine === `${label}:`) {
        plainLine = "";
        break;
      }
      if (plainLine.startsWith(`${label}：`)) {
        plainLine = plainLine.slice(label.length + 1).trim();
        break;
      }
      if (plainLine.startsWith(`${label}:`)) {
        plainLine = plainLine.slice(label.length + 1).trim();
        break;
      }
    }

    if (plainLine) {
      cleanedLines.push(plainLine);
    }
  }

  return cleanedLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function parseExtraBodyPayload(rawValue, configLabel) {
  if (rawValue && typeof rawValue === "object" && !Array.isArray(rawValue)) {
    return cloneObjectValue(rawValue);
  }

  const text = String(rawValue || "").trim();
  if (!text) {
    return {};
  }

  try {
    return parseLooseObjectText(text);
  } catch {
    throw new Error(`${configLabel} 的 extra_body 必须是对象，例如 {"enable_thinking": true} 或 {"enable_thinking": True}。`);
  }
}

function ensureSelectedPresetEditor(preferredId = "") {
  const presets = getDebaterPresets();
  if (!presets.length) {
    state.selectedPresetEditorId = "";
    return;
  }
  const presetIds = new Set(presets.map((preset) => String(preset.id || "")).filter(Boolean));
  const candidates = [
    preferredId,
    state.selectedPresetEditorId,
    state.settings?.pro_preset_id,
    state.settings?.con_preset_id,
    presets[0]?.id,
  ];
  state.selectedPresetEditorId = candidates.find((candidate) => presetIds.has(String(candidate || ""))) || presets[0].id;
}

function ensureSelectedSupplierEditor(preferredId = "") {
  const suppliers = getModelSuppliers();
  if (!suppliers.length) {
    state.selectedSupplierId = "";
    return;
  }
  const supplierIds = new Set(suppliers.map((supplier) => String(supplier.id || "")).filter(Boolean));
  const candidates = [
    preferredId,
    state.selectedSupplierId,
    state.settings?.judge?.supplier_id,
    suppliers[0]?.id,
  ];
  state.selectedSupplierId = candidates.find((candidate) => supplierIds.has(String(candidate || ""))) || suppliers[0].id;
}

function ensureSelectedToolEditor(preferredId = "") {
  const tools = getToolConfigs();
  if (!tools.length) {
    state.selectedToolConfigId = "";
    return;
  }
  const toolIds = new Set(tools.map((toolConfig) => String(toolConfig.id || "")).filter(Boolean));
  const candidates = [
    preferredId,
    state.selectedToolConfigId,
    tools[0]?.id,
  ];
  state.selectedToolConfigId = candidates.find((candidate) => toolIds.has(String(candidate || ""))) || tools[0].id;
}

function ensurePresetManagerSelections() {
  ensureSelectedPresetEditor();
  ensureSelectedSupplierEditor();
  ensureSelectedToolEditor();
  state.presetManagerTab = normalizeConfigManagerTab(state.presetManagerTab);
}

function normalizeConfigManagerTab(tab) {
  return CONFIG_MANAGER_TABS.some((item) => item.id === tab) ? tab : "debater";
}

function getPresetLimit() {
  return Number(state.settings?.preset_limit || 24) || 24;
}

function getSupplierLimit() {
  return Number(state.settings?.supplier_limit || 24) || 24;
}

function getToolLimit() {
  return Number(state.settings?.tool_limit || 12) || 12;
}

function getDebaterPresets() {
  return Array.isArray(state.settings?.debater_presets) ? state.settings.debater_presets : [];
}

function getModelSuppliers() {
  return Array.isArray(state.settings?.model_suppliers) ? state.settings.model_suppliers : [];
}

function getToolConfigs() {
  return Array.isArray(state.settings?.tool_configs) ? state.settings.tool_configs : [];
}

function findPresetById(presetId) {
  return getDebaterPresets().find((preset) => preset.id === presetId) || null;
}

function findSupplierById(supplierId) {
  return getModelSuppliers().find((supplier) => supplier.id === supplierId) || null;
}

function findToolById(toolId) {
  return getToolConfigs().find((toolConfig) => toolConfig.id === toolId) || null;
}

function getSelectedSupplier() {
  return findSupplierById(state.selectedSupplierId);
}

function getSelectedToolConfig() {
  return findToolById(state.selectedToolConfigId);
}

function getToolTemplate(templateId) {
  return TOOL_TEMPLATES.find((template) => template.id === templateId) || TOOL_TEMPLATES[0];
}

function createToolInstanceName(template) {
  const existingNames = new Set(getToolConfigs().map((toolConfig) => String(toolConfig.name || "").trim()));
  const baseName = template?.defaults?.name || template?.name || "工具";
  let index = getToolConfigs().filter((toolConfig) => (toolConfig.template_id || toolConfig.type) === template.id).length + 1;
  let candidate = index > 1 ? `${baseName} ${index}` : baseName;
  while (existingNames.has(candidate)) {
    index += 1;
    candidate = `${baseName} ${index}`;
  }
  return candidate;
}

function createToolFromTemplate(templateId = "tavily_search") {
  const template = getToolTemplate(templateId);
  const defaults = template.defaults || {};
  return {
    id: `tool_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    name: createToolInstanceName(template),
    template_id: template.id,
    type: defaults.type || template.id,
    enabled: false,
    api_key: "",
    timeout: Number(defaults.timeout || 60) || 60,
    max_results: Number(defaults.max_results || 5) || 5,
    search_depth: String(defaults.search_depth || "advanced"),
  };
}

function getSelectedPreset() {
  return findPresetById(state.selectedPresetEditorId);
}

function getPresetSupplier(preset) {
  return findSupplierById(preset?.supplier_id) || getModelSuppliers()[0] || null;
}

function getJudgeSupplier(judge = state.settings?.judge || {}) {
  return findSupplierById(judge?.supplier_id) || getModelSuppliers()[0] || null;
}

function getPresetToolSelection(preset) {
  const selection = preset?.tool_selection && typeof preset.tool_selection === "object" ? preset.tool_selection : {};
  return {
    enabled_tool_ids: Array.isArray(selection.enabled_tool_ids) ? selection.enabled_tool_ids : [],
    mode: String(selection.mode || "bind_tools"),
    max_tool_rounds: Number(selection.max_tool_rounds || 2) || 2,
  };
}

function getPresetSelectedTools(preset) {
  const selection = getPresetToolSelection(preset);
  return selection.enabled_tool_ids
    .map((toolId) => findToolById(toolId))
    .filter(Boolean);
}

function createPresetName() {
  const existingNames = new Set(getDebaterPresets().map((preset) => String(preset.name || "").trim()));
  let index = getDebaterPresets().length + 1;
  let candidate = `辩手配置 ${index}`;
  while (existingNames.has(candidate)) {
    index += 1;
    candidate = `辩手配置 ${index}`;
  }
  return candidate;
}

function createSupplierName() {
  const existingNames = new Set(getModelSuppliers().map((supplier) => String(supplier.name || "").trim()));
  let index = getModelSuppliers().length + 1;
  let candidate = `供应商 ${index}`;
  while (existingNames.has(candidate)) {
    index += 1;
    candidate = `供应商 ${index}`;
  }
  return candidate;
}

function createEmptySupplier() {
  const seed = getModelSuppliers()[0] || {};
  return {
    id: `supplier_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    name: createSupplierName(),
    provider: String(seed.provider || "chatopenai"),
    api_key: "",
    base_url: String(seed.base_url || ""),
    api_version: String(seed.api_version || "2025-04-01-preview"),
    timeout: Number(seed.timeout || 300) || 300,
    max_retries: Number(seed.max_retries || 2) || 2,
  };
}

function createEmptyDebaterPreset() {
  const seed = getSelectedPreset() || {};
  const seedToolSelection = getPresetToolSelection(seed);
  const supplierId = seed.supplier_id || getModelSuppliers()[0]?.id || "";
  return {
    id: `preset_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    name: createPresetName(),
    supplier_id: supplierId,
    model: String(seed.model || ""),
    azure_deployment: String(seed.azure_deployment || ""),
    max_tokens: Number(seed.max_tokens || 8000) || 8000,
    extra_body: cloneObjectValue(seed.extra_body),
    extra_body_input: formatExtraBodyInput(seed.extra_body_input ?? seed.extra_body),
    tool_selection: {
      enabled_tool_ids: [...seedToolSelection.enabled_tool_ids],
      mode: seedToolSelection.mode,
      max_tool_rounds: seedToolSelection.max_tool_rounds,
    },
  };
}

function openSettings() {
  state.presetManagerOpen = false;
  ensurePresetManagerSelections();
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
  window.clearTimeout(state.settingsModalTimer);
  els.settingsModal.classList.remove("hidden", "modal-leaving");
  requestAnimationFrame(() => {
    els.settingsModal.classList.add("modal-visible");
  });
  loadNotice()
    .then((changed) => {
      if (changed && !els.settingsModal.classList.contains("hidden")) {
        renderSettingsForm();
      }
    })
    .catch(() => {
      if (!els.settingsModal.classList.contains("hidden")) {
        renderSettingsForm();
      }
    });
}

function closeSettings() {
  if (els.settingsModal.classList.contains("hidden")) {
    return;
  }
  state.presetManagerOpen = false;
  renderPresetManagerPanel();
  window.clearTimeout(state.settingsModalTimer);
  els.settingsModal.classList.remove("modal-visible");
  els.settingsModal.classList.add("modal-leaving");
  state.settingsModalTimer = window.setTimeout(() => {
    els.settingsModal.classList.add("hidden");
    els.settingsModal.classList.remove("modal-leaving");
  }, MODAL_MOTION_MS);
}

function openPresetManager(tab = "debater") {
  state.presetManagerOpen = true;
  state.presetManagerEntering = true;
  state.presetManagerTab = normalizeConfigManagerTab(tab);
  ensurePresetManagerSelections();
  renderPresetManagerPanel();
}

function closePresetManager() {
  state.presetManagerOpen = false;
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function renderSettingsForm(options = {}) {
  if (!state.settings) {
    return;
  }
  ensurePresetManagerSelections();
  els.settingsForm.innerHTML = [
    createJudgeSettingsCard(state.settings.judge || {}),
    createSettingsSideStack(),
  ].join("");
  renderPresetManagerPanel(options.presetManagerOptions || {});
  renderHomeDebaterBinding();
}

function createSettingsSideStack() {
  return `
    <div class="settings-side-stack">
      ${createDebaterManagerLaunchCard()}
      ${createThemeNoticeCard()}
    </div>
  `;
}

function createThemeNoticeCard() {
  const notice = state.noticeText || "请在 frontend/Notice.txt 中维护这里的须知内容。";
  const usageTrackingEnabled = Boolean(state.settings?.usage_tracking_enabled);
  const contextRounds = state.settings?.context_rounds ?? DEFAULT_CONTEXT_ROUNDS;
  return `
    <section class="settings-card theme-settings-card">
      <div class="settings-card-head settings-card-head-compact">
        <div>
          <h4>其他设置与须知</h4>
        </div>
      </div>
      <div class="theme-settings-shell">
        <div class="theme-toggle-row context-setting-row">
          <div>
            <strong class="theme-toggle-title">上下文轮数</strong>
            <p class="card-note theme-toggle-copy">控制双方续辩时带入的最近轮数，支持 2 到 6 轮；3 轮约等于最近 6 句话。</p>
          </div>
          <label class="context-setting-field" aria-label="上下文轮数">
            <input type="number" min="2" max="6" step="1" data-ui-field="context_rounds" value="${escapeAttribute(contextRounds)}" />
          </label>
        </div>
        <div class="theme-toggle-row">
          <div>
            <strong class="theme-toggle-title">暗色模式</strong>
            <p class="card-note theme-toggle-copy">开启后，整个前端会切换到蓝黑概念风格。</p>
          </div>
          <label class="theme-switch" aria-label="暗色模式开关">
            <input type="checkbox" data-ui-field="dark_mode" ${state.darkMode ? "checked" : ""} />
            <span class="theme-switch-track"><span class="theme-switch-thumb"></span></span>
          </label>
        </div>
        <div class="theme-toggle-row">
          <div>
            <strong class="theme-toggle-title">Token 与工具统计</strong>
            <p class="card-note theme-toggle-copy">开启后统计正反方 token 消耗和网络搜索调用次数；若供应商未返回 usage，会在结果页标注为估算。</p>
          </div>
          <label class="theme-switch" aria-label="Token 与工具统计开关">
            <input type="checkbox" data-ui-field="usage_tracking_enabled" ${usageTrackingEnabled ? "checked" : ""} />
            <span class="theme-switch-track"><span class="theme-switch-thumb"></span></span>
          </label>
        </div>
        <div class="notice-viewer">
          <div class="notice-viewer-content">${formatNoticeText(notice)}</div>
        </div>
      </div>
    </section>
  `;
}

function renderPresetManagerPanel(options = {}) {
  if (!els.presetManagerPanel) {
    return;
  }
  if (!state.presetManagerOpen || !state.settings) {
    els.presetManagerPanel.classList.add("hidden");
    els.presetManagerPanel.innerHTML = "";
    return;
  }
  const {
    preserveListScroll = true,
    preserveEditorScroll = true,
  } = options;
  const existingList = els.presetManagerPanel.querySelector(".preset-list");
  const existingEditor = els.presetManagerPanel.querySelector(".preset-editor-scroller");
  const listScrollTop = preserveListScroll && existingList ? existingList.scrollTop : 0;
  const editorScrollTop = preserveEditorScroll && existingEditor ? existingEditor.scrollTop : 0;
  ensurePresetManagerSelections();
  els.presetManagerPanel.innerHTML = createPresetManagerOverlay();
  els.presetManagerPanel.classList.toggle("preset-overlay-enter", state.presetManagerEntering);
  els.presetManagerPanel.classList.remove("hidden");
  const nextList = els.presetManagerPanel.querySelector(".preset-list");
  const nextEditor = els.presetManagerPanel.querySelector(".preset-editor-scroller");
  if (nextList) {
    restoreScrollTop(nextList, preserveListScroll ? listScrollTop : 0);
  }
  if (nextEditor) {
    restoreScrollTop(nextEditor, preserveEditorScroll ? editorScrollTop : 0);
  }
  state.presetManagerEntering = false;
}

function restoreScrollTop(element, requestedScrollTop) {
  const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
  element.scrollTop = Math.min(Math.max(0, requestedScrollTop), maxScrollTop);
}

function createJudgeSettingsCard(config) {
  const supplier = getJudgeSupplier(config);
  const provider = supplier?.provider === "azure" ? "azure" : "chatopenai";
  return `
    <section class="settings-card judge-settings-card">
      <div class="settings-card-head settings-card-head-compact">
        <div>
          <h4>裁判模型</h4>
          <p class="card-note">裁判也从供应商中选择接入信息，只在这里填写模型和裁判专属参数。</p>
        </div>
        <button class="ghost-button compact-button" type="button" data-action="open-preset-manager" data-preset-manager-tab="supplier">管理供应商</button>
      </div>
      <label>
        <span>裁判供应商</span>
        <select data-judge-field="supplier_id">
          ${createSupplierOptions(config.supplier_id || supplier?.id || "")}
        </select>
      </label>
      <div class="binding-preview judge-supplier-preview">
        <span class="binding-preview-label">当前接入</span>
        <strong class="binding-preview-name">${escapeHtml(supplier?.name || "未选择供应商")}</strong>
        <p class="card-note binding-preview-detail">${escapeHtml(provider === "azure" ? "Azure" : "ChatOpenAI")} · API Key ${supplier?.has_api_key || supplier?.api_key ? "已配置" : "未配置"}</p>
      </div>
      <label>
        <span>模型名称</span>
        <input data-judge-field="model" value="${escapeAttribute(config.model || "")}" placeholder="例如 gpt-5.2 / kimi-k2.5" />
      </label>
      <div class="provider-fields ${provider === "chatopenai" ? "" : "hidden"}">
        <label>
          <span>额外参数 extra_body</span>
          <textarea class="json-textarea" data-judge-field="extra_body" rows="4" spellcheck="false" placeholder='例如 {"enable_thinking": true}'>${escapeHtml(formatExtraBodyInput(config.extra_body_input ?? config.extra_body))}</textarea>
        </label>
        <p class="card-note">仅在 ChatOpenAI 供应商下生效。支持标准 JSON，也兼容 {"enable_thinking": True} 这种写法。</p>
      </div>
      <div class="provider-fields ${provider === "azure" ? "" : "hidden"}">
        <label>
          <span>Azure Deployment</span>
          <input data-judge-field="azure_deployment" value="${escapeAttribute(config.azure_deployment || "")}" placeholder="例如 my-deployment" />
        </label>
      </div>
      <label>
        <span>Max Tokens</span>
        <input data-judge-field="max_tokens" type="number" min="1" value="${escapeAttribute(config.max_tokens || 4096)}" />
      </label>
    </section>
  `;
}

function createDebaterManagerLaunchCard() {
  const presets = getDebaterPresets();
  const limit = getPresetLimit();
  return `
    <section class="settings-card binding-settings-card debater-manager-card">
      <div class="settings-card-head">
        <p class="eyebrow">Debaters</p>
        <h4>辩手配置表</h4>
        <p class="card-note">创建、修改供应商、工具和辩手配置。</p>
      </div>
      <button class="primary-button debater-manager-button" type="button" data-action="open-preset-manager" data-preset-manager-tab="debater">
        打开辩手配置表
        <span>${presets.length} / ${limit}</span>
      </button>
    </section>
  `;
}

function createDebaterBindingSelector({ compact = false, disabled = false } = {}) {
  const presets = getDebaterPresets();
  const createOptions = (selectedId) => presets
    .map((preset) => `<option value="${escapeAttribute(preset.id)}" ${preset.id === selectedId ? "selected" : ""}>${escapeHtml(preset.name || "未命名配置")}</option>`)
    .join("");
  const compactClass = compact ? "binding-grid-compact" : "";
  const disabledAttr = disabled ? "disabled" : "";

  return `
      <div class="binding-grid ${compactClass}">
        <div class="binding-card">
          <label>
            <span>正方使用</span>
            <select data-binding-field="pro_preset_id" ${disabledAttr}>${createOptions(state.settings?.pro_preset_id || "")}</select>
          </label>
          ${createBindingPreview("正方", state.settings?.pro_preset_id || "")}
        </div>
        <div class="binding-card">
          <label>
            <span>反方使用</span>
            <select data-binding-field="con_preset_id" ${disabledAttr}>${createOptions(state.settings?.con_preset_id || "")}</select>
          </label>
          ${createBindingPreview("反方", state.settings?.con_preset_id || "")}
        </div>
      </div>
  `;
}

function renderHomeDebaterBinding() {
  if (!els.homeDebaterBinding) {
    return;
  }
  if (!state.settings) {
    els.homeDebaterBinding.innerHTML = "";
    return;
  }
  const isDisabled = Boolean(state.savingHomeBinding || els.startDebateBtn?.disabled);
  const savingText = state.savingHomeBinding ? '<span class="status-badge">保存中</span>' : "";
  els.homeDebaterBinding.innerHTML = `
    <div class="home-binding-head">
      <div>
        <span class="form-section-label">辩手配置</span>
        <p class="card-note">选择本场辩论使用的正方和反方模型，修改后会立即保存。</p>
      </div>
      ${savingText}
    </div>
    ${createDebaterBindingSelector({ compact: true, disabled: isDisabled })}
  `;
}

function createBindingPreview(roleLabel, presetId) {
  const preset = findPresetById(presetId);
  if (!preset) {
    return `
      <div class="binding-preview empty-state compact-empty-state">
        ${roleLabel} 当前还没有绑定可用配置。
      </div>
    `;
  }
  return `
    <div class="binding-preview">
      <span class="binding-preview-label">${escapeHtml(roleLabel)}</span>
      <strong class="binding-preview-name" title="${escapeAttribute(preset.name || "")}">${escapeHtml(preset.name || "未命名配置")}</strong>
      <p class="card-note binding-preview-detail">${escapeHtml(describePreset(preset))}</p>
    </div>
  `;
}

function describePreset(preset) {
  const supplier = getPresetSupplier(preset);
  const providerLabel = supplier?.provider === "azure" ? "Azure" : "ChatOpenAI";
  const supplierLabel = supplier?.name || "未选择供应商";
  const modelLabel = String(preset?.model || preset?.azure_deployment || "未填写模型").trim() || "未填写模型";
  const selection = getPresetToolSelection(preset);
  const selectedTools = getPresetSelectedTools(preset).filter((toolConfig) => toolConfig.enabled);
  const toolLabel = selectedTools.length
    ? `${selectedTools.map((toolConfig) => toolConfig.name || "未命名工具").join(" / ")} · ${selection.mode || "bind_tools"}`
    : "无工具";
  return `${supplierLabel} · ${providerLabel} · ${modelLabel} · ${toolLabel}`;
}

function createPresetManagerOverlay() {
  const activeTab = normalizeConfigManagerTab(state.presetManagerTab);

  return `
    <div class="preset-overlay-surface panel">
      <div class="preset-overlay-head config-overlay-head">
        <div class="preset-overlay-heading-row">
          <div>
            <p class="eyebrow">Soft Config</p>
            <h3>模型与工具配置</h3>
            <p class="card-note">按供应商、通用工具和辩手配置拆分管理；右上角保存后生效。</p>
          </div>
          <div class="config-head-actions">
            ${createConfigManagerTabs(activeTab)}
            <button class="config-tab config-tab-return" type="button" data-action="close-preset-manager">
              <span>返回设置</span>
            </button>
          </div>
        </div>
      </div>
      <div class="preset-overlay-body">
        ${createConfigManagerLibrary(activeTab)}
        <div class="preset-editor-shell config-detail-shell">
          ${createConfigManagerDetail(activeTab)}
        </div>
      </div>
    </div>
  `;
}

function createConfigManagerTabs(activeTab) {
  return `
    <div class="config-tabs" role="tablist" aria-label="模型与工具配置类型">
      ${CONFIG_MANAGER_TABS.map((tab) => {
        const meta = getConfigManagerTabMeta(tab.id);
        const active = tab.id === activeTab ? "active" : "";
        return `
          <button class="config-tab ${active}" type="button" role="tab" aria-selected="${tab.id === activeTab ? "true" : "false"}" data-action="switch-config-tab" data-config-tab="${escapeAttribute(tab.id)}">
            <span>${escapeHtml(tab.label)}</span>
            <small>${meta.count} / ${meta.limit}</small>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function getConfigManagerTabMeta(tab) {
  if (tab === "supplier") {
    return {
      title: "供应商列表",
      copy: "供应商保存 API Key、Base URL、接入模式等共享信息。",
      count: getModelSuppliers().length,
      limit: getSupplierLimit(),
      createAction: "create-supplier",
      createLabel: "新建供应商",
    };
  }
  if (tab === "tool") {
    return {
      title: "工具列表",
      copy: "先创建通用工具，再在辩手配置中勾选可用工具。",
      count: getToolConfigs().length,
      limit: getToolLimit(),
      createAction: "create-tool",
      createLabel: "新建工具",
    };
  }
  return {
    title: "辩手列表",
    copy: "辩手只选择供应商、填写模型名，并绑定可用工具。",
    count: getDebaterPresets().length,
    limit: getPresetLimit(),
    createAction: "create-preset",
    createLabel: "新建辩手",
  };
}

function createConfigManagerLibrary(tab) {
  const meta = getConfigManagerTabMeta(tab);
  const createDisabled = meta.count >= meta.limit;
  return `
    <div class="preset-library config-library">
      <div class="preset-library-head">
        <div>
          <h4>${escapeHtml(meta.title)}</h4>
          <p class="card-note">${escapeHtml(meta.copy)}</p>
        </div>
        <span class="status-badge">${meta.count} / ${meta.limit}</span>
      </div>
      ${createConfigManagerCreateControl(tab, meta, createDisabled)}
      <div class="preset-list config-item-list">
        ${createConfigManagerList(tab)}
      </div>
    </div>
  `;
}

function createConfigManagerCreateControl(tab, meta, createDisabled) {
  if (tab === "tool") {
    return `
      <div class="tool-template-row config-create-row">
        <label>
          <span>可用工具模板</span>
          <select data-tool-template-picker>
            ${TOOL_TEMPLATES.map((template) => `<option value="${escapeAttribute(template.id)}">${escapeHtml(template.name)}</option>`).join("")}
          </select>
        </label>
        <div class="config-create-actions">
          <button class="ghost-button compact-button" type="button" data-action="${escapeAttribute(meta.createAction)}" ${createDisabled ? "disabled" : ""}>${escapeHtml(meta.createLabel)}</button>
        </div>
      </div>
    `;
  }
  return `
    <div class="config-create-row single-action-row">
      <button class="ghost-button compact-button" type="button" data-action="${escapeAttribute(meta.createAction)}" ${createDisabled ? "disabled" : ""}>${escapeHtml(meta.createLabel)}</button>
    </div>
  `;
}

function createConfigManagerList(tab) {
  if (tab === "supplier") {
    const suppliers = getModelSuppliers();
    return suppliers.map((supplier) => createSupplierListItem(supplier)).join("")
      || '<div class="empty-state compact-empty-state">还没有供应商配置。</div>';
  }
  if (tab === "tool") {
    const tools = getToolConfigs();
    return tools.map((toolConfig) => createToolListItem(toolConfig)).join("")
      || '<div class="empty-state compact-empty-state">还没有通用工具配置。</div>';
  }
  const presets = getDebaterPresets();
  return presets.map((preset) => createPresetListItem(preset)).join("")
    || '<div class="empty-state compact-empty-state">还没有可编辑的辩手配置。</div>';
}

function createConfigManagerDetail(tab) {
  if (tab === "supplier") {
    const supplier = getSelectedSupplier();
    return supplier ? createSupplierEditor(supplier) : '<div class="empty-state">请选择或创建一个供应商。</div>';
  }
  if (tab === "tool") {
    const toolConfig = getSelectedToolConfig();
    return toolConfig ? createToolEditor(toolConfig) : '<div class="empty-state">请选择或创建一个通用工具。</div>';
  }
  const selectedPreset = getSelectedPreset();
  return selectedPreset ? createPresetEditor(selectedPreset) : '<div class="empty-state">请选择或创建一个辩手配置。</div>';
}

function createSupplierListItem(supplier) {
  const provider = supplier.provider === "azure" ? "Azure" : "ChatOpenAI";
  const active = supplier.id === state.selectedSupplierId ? "active" : "";
  const usedByDebaters = getDebaterPresets().filter((preset) => preset.supplier_id === supplier.id).length;
  const badges = [];
  if (state.settings?.judge?.supplier_id === supplier.id) {
    badges.push('<span class="preset-role-badge">裁判</span>');
  }
  if (usedByDebaters) {
    badges.push(`<span class="preset-mode-badge">${usedByDebaters} 辩手</span>`);
  }
  badges.push(`<span class="preset-mode-badge">${supplier.has_api_key || supplier.api_key ? "Key 已配置" : "Key 未配置"}</span>`);
  return `
    <button class="preset-item config-list-item ${active}" type="button" data-action="select-supplier" data-supplier-id="${escapeAttribute(supplier.id)}">
      <div class="preset-item-head">
        <strong class="preset-item-name" title="${escapeAttribute(supplier.name || "")}">${escapeHtml(supplier.name || "未命名供应商")}</strong>
        <span class="preset-item-provider">${escapeHtml(provider)}</span>
      </div>
      <div class="preset-item-meta" title="${escapeAttribute(supplier.base_url || "")}">${escapeHtml(supplier.base_url || "未填写 Base URL")}</div>
      <div class="preset-badges">${badges.join("")}</div>
    </button>
  `;
}

function createSupplierEditor(supplier) {
  const provider = supplier.provider === "azure" ? "Azure" : "ChatOpenAI";
  const deleteDisabled = getModelSuppliers().length <= 1;
  return `
    <div class="preset-editor supplier-editor">
      <div class="preset-editor-head">
        <div>
          <h4>供应商详情</h4>
          <p class="card-note preset-editor-meta">${escapeHtml(provider)} · ${supplier.has_api_key || supplier.api_key ? "API Key 已配置" : "API Key 未配置"}</p>
          <p class="card-note">供应商保存共享接入信息；辩手和裁判只引用这里的供应商。</p>
        </div>
        <span class="status-badge">已选供应商</span>
      </div>
      <div class="preset-editor-scroller">
        ${createSupplierForm(supplier)}
      </div>
      <div class="preset-editor-actions">
        <button class="danger-button compact-button" type="button" data-action="delete-supplier" data-supplier-id="${escapeAttribute(supplier.id)}" ${deleteDisabled ? "disabled" : ""}>删除供应商</button>
      </div>
    </div>
  `;
}

function createSupplierForm(supplier) {
  const provider = supplier.provider === "azure" ? "azure" : "chatopenai";
  return `
    <div class="supplier-card supplier-editor-card" data-supplier-id="${escapeAttribute(supplier.id)}">
      <div class="form-grid">
        <label>
          <span>供应商名称</span>
          <input data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="name" value="${escapeAttribute(supplier.name || "")}" placeholder="例如 阿里百炼 / DeepSeek / Azure Sweden" />
        </label>
        <label>
          <span>接入模式</span>
          <select data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="provider">
            <option value="azure" ${provider === "azure" ? "selected" : ""}>Azure</option>
            <option value="chatopenai" ${provider === "chatopenai" ? "selected" : ""}>ChatOpenAI</option>
          </select>
        </label>
      </div>
      <label>
        <span>API Key</span>
        <input type="password" autocomplete="new-password" data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="api_key" value="${escapeAttribute(supplier.api_key || "")}" placeholder="输入供应商 API Key" />
      </label>
      <label>
        <span>Base URL / Endpoint</span>
        <input data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="base_url" value="${escapeAttribute(supplier.base_url || "")}" placeholder="Azure endpoint 或 OpenAI 兼容 base URL" />
      </label>
      <div class="form-grid">
        <label>
          <span>API Version</span>
          <input data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="api_version" value="${escapeAttribute(supplier.api_version || "")}" placeholder="Azure 可填写 2025-04-01-preview" />
        </label>
        <label>
          <span>Timeout</span>
          <input data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="timeout" type="number" min="1" value="${escapeAttribute(supplier.timeout || 300)}" />
        </label>
      </div>
      <div class="supplier-card-actions">
        <label>
          <span>Max Retries</span>
          <input data-supplier-id="${escapeAttribute(supplier.id)}" data-supplier-field="max_retries" type="number" min="1" value="${escapeAttribute(supplier.max_retries || 2)}" />
        </label>
      </div>
    </div>
  `;
}

function createToolListItem(toolConfig) {
  const active = toolConfig.id === state.selectedToolConfigId ? "active" : "";
  const template = getToolTemplate(toolConfig.template_id || toolConfig.type || "tavily_search");
  const usedByDebaters = getDebaterPresets().filter((preset) => {
    const selection = getPresetToolSelection(preset);
    return selection.enabled_tool_ids.includes(toolConfig.id);
  }).length;
  const badges = [
    `<span class="preset-role-badge">${toolConfig.enabled ? "已启用" : "未启用"}</span>`,
    `<span class="preset-mode-badge">${toolConfig.has_api_key || toolConfig.api_key ? "Key 已配置" : "Key 未配置"}</span>`,
  ];
  if (usedByDebaters) {
    badges.push(`<span class="preset-mode-badge">${usedByDebaters} 辩手</span>`);
  }
  return `
    <button class="preset-item config-list-item ${active}" type="button" data-action="select-tool" data-tool-id="${escapeAttribute(toolConfig.id || "")}">
      <div class="preset-item-head">
        <strong class="preset-item-name" title="${escapeAttribute(toolConfig.name || "")}">${escapeHtml(toolConfig.name || "未命名工具")}</strong>
        <span class="preset-item-provider">${escapeHtml(template?.name || toolConfig.type || "工具")}</span>
      </div>
      <div class="preset-item-meta" title="${escapeAttribute(template?.description || "")}">${escapeHtml(template?.description || "通用工具")}</div>
      <div class="preset-badges">${badges.join("")}</div>
    </button>
  `;
}

function createToolEditor(toolConfig) {
  const template = getToolTemplate(toolConfig.template_id || toolConfig.type || "tavily_search");
  const deleteDisabled = getToolConfigs().length <= 1;
  return `
    <div class="preset-editor tool-editor">
      <div class="preset-editor-head">
        <div>
          <h4>工具详情</h4>
          <p class="card-note preset-editor-meta">${escapeHtml(template?.name || "通用工具")} · ${toolConfig.enabled ? "已启用" : "未启用"} · ${toolConfig.has_api_key || toolConfig.api_key ? "API Key 已配置" : "API Key 未配置"}</p>
          <p class="card-note">工具配置完成后，可在“配置辩手”里勾选给指定辩手使用。</p>
        </div>
        <span class="status-badge">已选工具</span>
      </div>
      <div class="preset-editor-scroller">
        ${createToolConfigForm(toolConfig)}
      </div>
      <div class="preset-editor-actions">
        <button class="danger-button compact-button" type="button" data-action="delete-tool" data-tool-id="${escapeAttribute(toolConfig.id || "")}" ${deleteDisabled ? "disabled" : ""}>删除工具</button>
      </div>
    </div>
  `;
}

function createToolConfigForm(toolConfig) {
  const enabled = Boolean(toolConfig.enabled);
  const template = getToolTemplate(toolConfig.template_id || toolConfig.type || "tavily_search");
  const typeLabel = template?.name || toolConfig.type || "未知工具";
  return `
    <div class="tool-config-card" data-tool-id="${escapeAttribute(toolConfig.id || "")}">
      <div class="tool-config-head">
        <div>
          <strong>${escapeHtml(toolConfig.name || "Tavily Search")}</strong>
          <p class="card-note">${escapeHtml(typeLabel)} · ${escapeHtml(template?.description || "")}</p>
        </div>
        <label class="mini-switch" aria-label="启用通用工具">
          <input type="checkbox" data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="enabled" ${enabled ? "checked" : ""} />
          <span></span>
        </label>
      </div>
      <label>
        <span>工具名称</span>
        <input data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="name" value="${escapeAttribute(toolConfig.name || "")}" placeholder="Tavily Search" />
      </label>
      <label>
        <span>Tavily API Key</span>
        <input type="password" autocomplete="new-password" data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="api_key" value="${escapeAttribute(toolConfig.api_key || "")}" placeholder="输入 Tavily API Key" />
      </label>
      <div class="form-grid compact-form-grid">
        <label>
          <span>超时</span>
          <input data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="timeout" type="number" min="1" value="${escapeAttribute(toolConfig.timeout || 60)}" />
        </label>
        <label>
          <span>条数</span>
          <input data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="max_results" type="number" min="1" max="10" value="${escapeAttribute(toolConfig.max_results || 5)}" />
        </label>
      </div>
      <label>
        <span>搜索深度</span>
        <input data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="search_depth" value="${escapeAttribute(toolConfig.search_depth || "advanced")}" />
      </label>
    </div>
  `;
}

function createSupplierOptions(selectedId) {
  return getModelSuppliers()
    .map((supplier) => `<option value="${escapeAttribute(supplier.id)}" ${supplier.id === selectedId ? "selected" : ""}>${escapeHtml(supplier.name || "未命名供应商")}</option>`)
    .join("");
}

function createPresetListItem(preset) {
  const active = preset.id === state.selectedPresetEditorId ? "active" : "";
  const supplier = getPresetSupplier(preset);
  const providerLabel = supplier?.provider === "azure" ? "Azure" : "ChatOpenAI";
  const modelLabel = String(preset.model || preset.azure_deployment || "未填写模型").trim() || "未填写模型";
  const badges = [];
  if (state.settings?.pro_preset_id === preset.id) {
    badges.push('<span class="preset-role-badge">正方</span>');
  }
  if (state.settings?.con_preset_id === preset.id) {
    badges.push('<span class="preset-role-badge">反方</span>');
  }
  if (getPresetSelectedTools(preset).some((toolConfig) => toolConfig.enabled)) {
    badges.push('<span class="preset-mode-badge">工具开</span>');
  }

  return `
    <button class="preset-item ${active}" type="button" data-action="select-preset" data-preset-id="${escapeAttribute(preset.id)}">
      <div class="preset-item-head">
        <strong class="preset-item-name" title="${escapeAttribute(preset.name || "")}">${escapeHtml(preset.name || "未命名配置")}</strong>
        <span class="preset-item-provider">${escapeHtml(providerLabel)}</span>
      </div>
      <div class="preset-item-meta" title="${escapeAttribute(modelLabel)}">${escapeHtml(modelLabel)}</div>
      <div class="preset-badges">${badges.join("")}</div>
    </button>
  `;
}

function createPresetEditor(preset) {
  const supplier = getPresetSupplier(preset);
  const provider = supplier?.provider === "azure" ? "azure" : "chatopenai";
  const selection = getPresetToolSelection(preset);
  const deleteDisabled = getDebaterPresets().length <= 1;

  return `
    <div class="preset-editor">
      <div class="preset-editor-head">
        <div>
          <h4>编辑辩手配置</h4>
          <p class="card-note preset-editor-meta">${escapeHtml(describePreset(preset))}</p>
          <p class="card-note">修改后点击右上角“保存设置”生效。历史会话不会被后续修改回写。</p>
        </div>
        <span class="status-badge">已选配置</span>
      </div>
      <div class="preset-editor-scroller">
        <label>
          <span>配置名称</span>
          <input data-preset-field="name" value="${escapeAttribute(preset.name || "")}" placeholder="例如 深搜正方 / Azure 反方" />
        </label>
        <label>
          <span>供应商</span>
          <select data-preset-field="supplier_id">
            ${createSupplierOptions(preset.supplier_id || supplier?.id || "")}
          </select>
        </label>
        <label>
          <span>模型名称</span>
          <input data-preset-field="model" value="${escapeAttribute(preset.model || "")}" placeholder="例如 qwen3.5-plus / deepseek-chat" />
        </label>
        <div class="provider-fields ${provider === "chatopenai" ? "" : "hidden"}">
          <label>
            <span>额外参数 extra_body</span>
            <textarea class="json-textarea" data-preset-field="extra_body" rows="4" spellcheck="false" placeholder='例如 {"enable_thinking": true}'>${escapeHtml(formatExtraBodyInput(preset.extra_body_input ?? preset.extra_body))}</textarea>
          </label>
          <p class="card-note">仅在 ChatOpenAI 模式下生效。支持标准 JSON，也兼容 {"enable_thinking": True} 这种写法。</p>
        </div>
        <div class="provider-fields ${provider === "azure" ? "" : "hidden"}">
          <label>
            <span>Azure Deployment</span>
            <input data-preset-field="azure_deployment" value="${escapeAttribute(preset.azure_deployment || "")}" placeholder="例如 my-deployment" />
          </label>
        </div>
        <label>
          <span>Max Tokens</span>
          <input data-preset-field="max_tokens" type="number" min="1" value="${escapeAttribute(preset.max_tokens || 8000)}" />
        </label>
        ${createPresetToolSelector(selection)}
      </div>
      <div class="preset-editor-actions">
        <button class="danger-button compact-button" type="button" data-action="delete-preset" ${deleteDisabled ? "disabled" : ""}>删除当前配置</button>
      </div>
    </div>
  `;
}

function createPresetToolSelector(selection) {
  const tools = getToolConfigs();
  const selectedIds = new Set(selection.enabled_tool_ids || []);
  return `
    <div class="search-section tool-selection-section">
      <div class="toggle-row">
        <div>
          <strong>可用工具</strong>
          <p class="card-note">从通用工具配置中选择本辩手可调用的工具。未启用的通用工具即使勾选也不会执行。</p>
        </div>
      </div>
      <div class="tool-choice-list">
        ${tools.map((toolConfig) => createToolChoice(toolConfig, selectedIds.has(toolConfig.id))).join("") || '<div class="empty-state compact-empty-state">暂无通用工具，请先在上方配置 Tavily Search。</div>'}
      </div>
      <div class="form-grid">
        <label>
          <span>工具模式</span>
          <select data-preset-tool-field="mode">
            <option value="bind_tools" ${selection.mode === "bind_tools" ? "selected" : ""}>bind_tools</option>
            <option value="react" ${selection.mode === "react" ? "selected" : ""}>react</option>
          </select>
        </label>
        <label>
          <span>工具最多调用轮数</span>
          <input data-preset-tool-field="max_tool_rounds" type="number" min="1" value="${escapeAttribute(selection.max_tool_rounds || 2)}" />
        </label>
      </div>
    </div>
  `;
}

function createToolChoice(toolConfig, selected) {
  const disabledClass = toolConfig.enabled ? "" : "tool-choice-disabled";
  const template = getToolTemplate(toolConfig.template_id || toolConfig.type || "tavily_search");
  const typeLabel = template?.name || toolConfig.type || "未知工具";
  const keyLabel = toolConfig.has_api_key || toolConfig.api_key ? "已配置 Key" : "未配置 Key";
  return `
    <label class="tool-choice-card ${disabledClass}">
      <input class="checkbox" type="checkbox" data-preset-tool-id="${escapeAttribute(toolConfig.id || "")}" ${selected ? "checked" : ""} />
      <span>
        <strong>${escapeHtml(toolConfig.name || "Tavily Search")}</strong>
        <small>${escapeHtml(typeLabel)} · ${toolConfig.enabled ? "通用已启用" : "通用未启用"} · ${escapeHtml(keyLabel)}</small>
      </span>
    </label>
  `;
}

function handleSettingsFormInput(event) {
  if (event.target instanceof HTMLInputElement && event.target.type === "checkbox" && event.target.dataset.uiField) {
    return;
  }
  if (applyUiInput(event.target)) {
    return;
  }
  applySettingsInput(event.target);
}

function handleSettingsFormChange(event) {
  if (applyUiInput(event.target)) {
    return;
  }
  const shouldRerender = applySettingsInput(event.target);
  if (shouldRerender) {
    renderSettingsForm();
  }
}

function handleSettingsFormClick(event) {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }
  if (actionTarget.dataset.action === "open-preset-manager") {
    openPresetManager(actionTarget.dataset.presetManagerTab || "debater");
  }
}

function handleHomeBindingClick(event) {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }
  if (actionTarget.dataset.action === "open-preset-manager") {
    openSettings();
    openPresetManager(actionTarget.dataset.presetManagerTab || "debater");
  }
}

async function handleHomeBindingChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement) || !target.dataset.bindingField || !state.settings) {
    return;
  }
  const previousValue = state.settings[target.dataset.bindingField] || "";
  state.settings[target.dataset.bindingField] = String(target.value || "");
  ensureSelectedPresetEditor();
  state.savingHomeBinding = true;
  renderHomeDebaterBinding();
  try {
    await persistSettings();
  } catch (error) {
    state.settings[target.dataset.bindingField] = previousValue;
    renderHomeDebaterBinding();
    window.alert(error?.message || "保存辩手选择失败。");
  } finally {
    state.savingHomeBinding = false;
    renderHomeDebaterBinding();
  }
}

function handlePresetManagerInput(event) {
  applySettingsInput(event.target);
}

function handlePresetManagerChange(event) {
  const shouldRerender = applySettingsInput(event.target);
  const field = event.target.dataset.presetField
    || event.target.dataset.presetToolField
    || event.target.dataset.supplierField
    || event.target.dataset.toolConfigField
    || "";
  if (shouldRerender || ["name", "model", "supplier_id", "provider", "mode", "enabled"].includes(field)) {
    renderSettingsForm();
  }
}

function handlePresetManagerClick(event) {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }

  const action = actionTarget.dataset.action;
  if (action === "close-preset-manager") {
    closePresetManager();
    return;
  }
  if (action === "switch-config-tab") {
    state.presetManagerTab = normalizeConfigManagerTab(actionTarget.dataset.configTab || "");
    ensurePresetManagerSelections();
    renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: false });
    return;
  }
  if (action === "create-preset") {
    createPreset();
    return;
  }
  if (action === "create-supplier") {
    createSupplier();
    return;
  }
  if (action === "select-preset") {
    state.selectedPresetEditorId = actionTarget.dataset.presetId || "";
    state.presetManagerTab = "debater";
    renderPresetManagerPanel({ preserveListScroll: true, preserveEditorScroll: false });
    return;
  }
  if (action === "select-supplier") {
    state.selectedSupplierId = actionTarget.dataset.supplierId || "";
    state.presetManagerTab = "supplier";
    renderPresetManagerPanel({ preserveListScroll: true, preserveEditorScroll: false });
    return;
  }
  if (action === "select-tool") {
    state.selectedToolConfigId = actionTarget.dataset.toolId || "";
    state.presetManagerTab = "tool";
    renderPresetManagerPanel({ preserveListScroll: true, preserveEditorScroll: false });
    return;
  }
  if (action === "delete-preset") {
    deleteSelectedPreset();
    return;
  }
  if (action === "delete-supplier") {
    deleteSupplier(actionTarget.dataset.supplierId || "");
    return;
  }
  if (action === "create-tool") {
    const templatePicker = els.presetManagerPanel?.querySelector("[data-tool-template-picker]");
    createToolConfig(templatePicker?.value || "tavily_search");
    return;
  }
  if (action === "delete-tool") {
    deleteToolConfig(actionTarget.dataset.toolId || "");
  }
}

function applyUiInput(target) {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) {
    return false;
  }
  if (target.dataset.uiField === "dark_mode") {
    setDarkMode(Boolean(target.checked));
    return true;
  }
  if (target.dataset.uiField === "context_rounds") {
    if (state.settings) {
      state.settings.context_rounds = String(target.value ?? "");
    }
    return true;
  }
  if (target.dataset.uiField === "usage_tracking_enabled") {
    if (state.settings) {
      state.settings.usage_tracking_enabled = Boolean(target.checked);
    }
    return true;
  }
  return false;
}

function applySettingsInput(target) {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement)) {
    return false;
  }

  const judgeField = target.dataset.judgeField;
  if (judgeField) {
    if (judgeField === "extra_body") {
      state.settings.judge.extra_body_input = String(target.value || "");
      return false;
    }
    state.settings.judge[judgeField] = readFieldValue(target);
    return judgeField === "supplier_id";
  }

  const bindingField = target.dataset.bindingField;
  if (bindingField) {
    state.settings[bindingField] = String(target.value || "");
    ensureSelectedPresetEditor();
    return true;
  }

  const supplierField = target.dataset.supplierField;
  if (supplierField) {
    const supplier = findSupplierById(target.dataset.supplierId || "");
    if (!supplier) {
      return false;
    }
    supplier[supplierField] = readFieldValue(target);
    return supplierField === "provider" || supplierField === "name";
  }

  const toolConfigField = target.dataset.toolConfigField;
  if (toolConfigField) {
    const toolConfig = findToolById(target.dataset.toolConfigId || "");
    if (!toolConfig) {
      return false;
    }
    toolConfig[toolConfigField] = readFieldValue(target);
    return ["enabled", "name"].includes(toolConfigField);
  }

  const preset = getSelectedPreset();
  if (!preset) {
    return false;
  }

  const presetField = target.dataset.presetField;
  if (presetField) {
    if (presetField === "extra_body") {
      preset.extra_body_input = String(target.value || "");
      return false;
    }
    preset[presetField] = readFieldValue(target);
    return presetField === "supplier_id";
  }

  const presetToolField = target.dataset.presetToolField;
  if (presetToolField) {
    preset.tool_selection = getPresetToolSelection(preset);
    preset.tool_selection[presetToolField] = readFieldValue(target);
    return presetToolField === "mode";
  }

  const presetToolId = target.dataset.presetToolId;
  if (presetToolId) {
    preset.tool_selection = getPresetToolSelection(preset);
    const selectedIds = new Set(preset.tool_selection.enabled_tool_ids || []);
    if (target.checked) {
      selectedIds.add(presetToolId);
    } else {
      selectedIds.delete(presetToolId);
    }
    preset.tool_selection.enabled_tool_ids = [...selectedIds].filter((toolId) => Boolean(findToolById(toolId)));
    return true;
  }

  return false;
}

function readFieldValue(target) {
  if (target.type === "checkbox") {
    return target.checked;
  }
  if (target.type === "number") {
    return target.value === "" ? "" : Number(target.value);
  }
  return target.value;
}

function createSupplier() {
  const suppliers = getModelSuppliers();
  const limit = getSupplierLimit();
  if (suppliers.length >= limit) {
    window.alert(`供应商配置最多只能保存 ${limit} 个。`);
    return;
  }
  const nextSupplier = createEmptySupplier();
  state.settings.model_suppliers = [...suppliers, nextSupplier];
  state.selectedSupplierId = nextSupplier.id;
  state.presetManagerTab = "supplier";
  if (!state.settings.judge?.supplier_id) {
    state.settings.judge = state.settings.judge || {};
    state.settings.judge.supplier_id = nextSupplier.id;
  }
  getDebaterPresets().forEach((preset) => {
    if (!preset.supplier_id) {
      preset.supplier_id = nextSupplier.id;
    }
  });
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function deleteSupplier(supplierId) {
  const suppliers = getModelSuppliers();
  if (suppliers.length <= 1) {
    window.alert("至少需要保留一个供应商配置。");
    return;
  }
  const supplier = findSupplierById(supplierId);
  if (!supplier) {
    return;
  }
  const yes = window.confirm(`确认删除供应商“${supplier.name || "未命名供应商"}”吗？引用它的辩手配置会自动改绑到剩余供应商。`);
  if (!yes) {
    return;
  }
  const remaining = suppliers.filter((item) => item.id !== supplier.id);
  const replacementId = remaining[0]?.id || "";
  state.settings.model_suppliers = remaining;
  state.selectedSupplierId = replacementId;
  state.presetManagerTab = "supplier";
  if (state.settings.judge?.supplier_id === supplier.id || !state.settings.judge?.supplier_id) {
    state.settings.judge = state.settings.judge || {};
    state.settings.judge.supplier_id = replacementId;
  }
  getDebaterPresets().forEach((preset) => {
    if (preset.supplier_id === supplier.id || !preset.supplier_id) {
      preset.supplier_id = replacementId;
    }
  });
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function createToolConfig(templateId = "tavily_search") {
  const tools = getToolConfigs();
  const limit = getToolLimit();
  if (tools.length >= limit) {
    window.alert(`通用工具最多只能保存 ${limit} 个。`);
    return;
  }
  const nextTool = createToolFromTemplate(templateId);
  state.settings.tool_configs = [...tools, nextTool];
  state.selectedToolConfigId = nextTool.id;
  state.presetManagerTab = "tool";
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function deleteToolConfig(toolId) {
  const tools = getToolConfigs();
  if (tools.length <= 1) {
    window.alert("至少需要保留一个通用工具配置。");
    return;
  }
  const toolConfig = findToolById(toolId);
  if (!toolConfig) {
    return;
  }
  const yes = window.confirm(`确认删除工具“${toolConfig.name || "未命名工具"}”吗？引用它的辩手配置会自动解绑。`);
  if (!yes) {
    return;
  }
  const remainingTools = tools.filter((item) => item.id !== toolConfig.id);
  state.settings.tool_configs = remainingTools;
  state.selectedToolConfigId = remainingTools[0]?.id || "";
  state.presetManagerTab = "tool";
  getDebaterPresets().forEach((preset) => {
    const selection = getPresetToolSelection(preset);
    preset.tool_selection = {
      ...selection,
      enabled_tool_ids: selection.enabled_tool_ids.filter((item) => item !== toolConfig.id),
    };
  });
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function createPreset() {
  const presets = getDebaterPresets();
  const limit = getPresetLimit();
  if (presets.length >= limit) {
    window.alert(`辩手配置最多只能保存 ${limit} 个。`);
    return;
  }

  const nextPreset = createEmptyDebaterPreset();
  state.settings.debater_presets = [...presets, nextPreset];
  state.presetManagerTab = "debater";
  if (!state.settings.pro_preset_id) {
    state.settings.pro_preset_id = nextPreset.id;
  }
  if (!state.settings.con_preset_id) {
    state.settings.con_preset_id = nextPreset.id;
  }
  ensureSelectedPresetEditor(nextPreset.id);
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function deleteSelectedPreset() {
  const presets = getDebaterPresets();
  if (presets.length <= 1) {
    window.alert("至少需要保留一个辩手配置。");
    return;
  }

  const preset = getSelectedPreset();
  if (!preset) {
    return;
  }
  const yes = window.confirm(`确认删除配置“${preset.name || "未命名配置"}”吗？`);
  if (!yes) {
    return;
  }

  const remaining = presets.filter((item) => item.id !== preset.id);
  state.settings.debater_presets = remaining;
  state.presetManagerTab = "debater";
  if (state.settings.pro_preset_id === preset.id) {
    state.settings.pro_preset_id = remaining[0].id;
  }
  if (state.settings.con_preset_id === preset.id) {
    const replacement = remaining.find((item) => item.id !== state.settings.pro_preset_id) || remaining[0];
    state.settings.con_preset_id = replacement.id;
  }
  ensureSelectedPresetEditor(remaining[0].id);
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}
async function loadSessions() {
  state.sessions = await api("/api/debates");
  syncCurrentSessionSummary();
  renderSessions();
  scheduleSessionSummaryRefresh();
}

function getSessionDisplayTitle(session, fallbackTitle = "", options = {}) {
  const runtimeTitle = String(session?.runtime_state?.debate_title || "").trim();
  if (runtimeTitle) {
    return runtimeTitle;
  }
  const phase = String(session?.runtime_state?.phase || "").trim();
  if (options.placeholderDuringJudge && phase === "judge_initialize" && isLiveSessionStatus(session?.status)) {
    return "正在生成标题...";
  }
  return String(session?.topic || fallbackTitle || "").trim();
}

function canEditCurrentHeadline() {
  const session = state.currentSession;
  if (!session?.id) {
    return false;
  }
  const mode = getDebateMode(session);
  return mode === "live" || mode === "review";
}

function getSessionPreview(session, fallbackPreview = "") {
  const livePreview = String(session?.live_status?.content || "").trim();
  if (isLiveSessionStatus(session?.status) && livePreview) {
    return livePreview.slice(0, 120);
  }
  const messages = Array.isArray(session?.messages) ? session.messages : [];
  if (messages.length) {
    return String(messages[messages.length - 1]?.content || "").slice(0, 120);
  }
  return String(session?.preview || fallbackPreview || "").slice(0, 120);
}

function buildSessionSummary(session, previous = {}) {
  const result = session?.result && typeof session.result === "object" ? session.result : {};
  const previousResult = previous?.result && typeof previous.result === "object" ? previous.result : {};
  const messages = Array.isArray(session?.messages) ? session.messages : null;
  return {
    ...previous,
    id: session?.id || previous?.id,
    topic: getSessionDisplayTitle(session, previous?.topic),
    status: session?.status || previous?.status || "",
    created_at: session?.created_at || previous?.created_at || "",
    updated_at: session?.updated_at || previous?.updated_at || "",
    finished_at: session?.finished_at || previous?.finished_at || "",
    preview: getSessionPreview(session, previous?.preview),
    winner: result.winner ?? previousResult.winner ?? previous?.winner,
    message_count: messages ? messages.length : Number(session?.message_count ?? previous?.message_count ?? 0),
    archived: Boolean(session?.archived ?? previous?.archived),
    archived_at: session?.archived_at ?? previous?.archived_at ?? null,
  };
}

function upsertSessionSummary(session) {
  if (!session?.id) {
    return;
  }
  const index = state.sessions.findIndex((item) => item.id === session.id);
  const previous = index >= 0 ? state.sessions[index] : {};
  const summary = buildSessionSummary(session, previous);
  if (index >= 0) {
    state.sessions[index] = summary;
  } else {
    state.sessions = [summary, ...state.sessions];
  }
  state.sessions.sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
}

function syncCurrentSessionSummary() {
  if (!state.currentSession || state.currentSession.archived) {
    return;
  }
  upsertSessionSummary(state.currentSession);
}

function hasBackgroundLiveSessions() {
  return state.sessions.some((session) => session.id !== state.currentSessionId && isLiveSessionStatus(session.status));
}

function scheduleSessionSummaryRefresh() {
  window.clearTimeout(state.sessionSummaryRefreshTimer);
  state.sessionSummaryRefreshTimer = null;
  if (!hasBackgroundLiveSessions()) {
    return;
  }
  state.sessionSummaryRefreshTimer = window.setTimeout(() => {
    void refreshSessionSummaries();
  }, SESSION_SUMMARY_REFRESH_MS);
}

async function refreshSessionSummaries() {
  if (state.sessionSummaryRefreshInFlight) {
    return;
  }
  state.sessionSummaryRefreshInFlight = true;
  try {
    state.sessions = await api("/api/debates");
    syncCurrentSessionSummary();
    renderSessions();
  } catch {
    // 背景摘要刷新失败时直接等待下一轮，不打断当前界面。
  } finally {
    state.sessionSummaryRefreshInFlight = false;
    scheduleSessionSummaryRefresh();
  }
}

async function loadArchivedSessions() {
  state.archivedSessions = await api("/api/debates/archived");
  renderArchivedSessions();
}

function getTrashIconSvg() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" />
      <path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" />
    </svg>
  `;
}

function getArchiveIconSvg() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 6a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v2a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z" />
      <path d="M5 10v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-8" />
      <path d="M10 14h4" />
    </svg>
  `;
}

function getMessageRewindIconSvg() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 14 5 10l4-4" />
      <path d="M5 10h11a4 4 0 1 1 0 8h-1" />
    </svg>
  `;
}

function renderSessions() {
  if (!state.sessions.length) {
    els.historyList.innerHTML = '<div class="empty-state">还没有历史辩论，启动一场新的试试。</div>';
    return;
  }

  els.historyList.innerHTML = state.sessions
    .map((session) => {
      const active = session.id === state.currentSessionId ? "active" : "";
      const meta = `${formatStatus(session.status)} · ${formatDate(session.created_at)}`;
      const preview = session.preview || "暂无摘要";
      return `
        <div class="history-item ${active}" data-session-id="${session.id}">
          <div class="history-main" title="${escapeAttribute(session.topic)}">
            <p class="history-title" title="${escapeAttribute(session.topic)}">${escapeHtml(session.topic)}</p>
            <div class="history-meta">
              <div title="${escapeAttribute(meta)}">${escapeHtml(meta)}</div>
              <div title="${escapeAttribute(preview)}">${escapeHtml(preview)}</div>
            </div>
          </div>
          <div class="history-actions">
            <button class="history-action-button history-delete-button" data-action="delete-session" data-session-id="${session.id}" type="button" title="删除记录" aria-label="删除记录">
              ${getTrashIconSvg()}
            </button>
            <button class="history-action-button history-archive-button" data-action="archive-session" data-session-id="${session.id}" type="button" title="归档记录" aria-label="归档记录">
              ${getArchiveIconSvg()}
            </button>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderArchivedSessions() {
  if (!state.archivedSessions.length) {
    els.archivedList.innerHTML = '<div class="empty-state compact-empty-state">还没有已归档记录。</div>';
    return;
  }

  els.archivedList.innerHTML = state.archivedSessions
    .map((session) => {
      const meta = `${formatStatus(session.status)} · ${formatDate(session.created_at)}`;
      const archivedAt = session.archived_at ? `归档于 ${formatDate(session.archived_at)}` : "已归档";
      return `
        <article class="archived-item">
          <div class="archived-main">
            <p class="history-title" title="${escapeAttribute(session.topic)}">${escapeHtml(session.topic)}</p>
            <div class="history-meta archived-meta">
              <div title="${escapeAttribute(meta)}">${escapeHtml(meta)}</div>
              <div title="${escapeAttribute(archivedAt)}">${escapeHtml(archivedAt)}</div>
            </div>
          </div>
          <div class="archived-actions">
            <button class="ghost-button compact-button" data-action="view-archived" data-session-id="${session.id}" type="button">查看</button>
            <button class="ghost-button compact-button" data-action="restore-session" data-session-id="${session.id}" type="button">恢复</button>
            <button class="danger-button compact-button" data-action="delete-archived-session" data-session-id="${session.id}" type="button">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function startDebate(event) {
  event.preventDefault();
  const topic = els.topicInput.value.trim();
  const minRounds = Number(els.minRoundsInput.value || 0);
  const maxRounds = Number(els.maxRoundsInput.value || 0);

  if (!topic) {
    showLocalError("请先输入辩题。", true);
    return;
  }
  if (
    minRounds < MIN_DEBATE_ROUNDS
    || minRounds > MAX_DEBATE_ROUNDS
    || maxRounds < MIN_DEBATE_ROUNDS
    || maxRounds > MAX_DEBATE_ROUNDS
  ) {
    window.alert(`最少轮数和最多轮数都必须在 ${MIN_DEBATE_ROUNDS} 到 ${MAX_DEBATE_ROUNDS} 之间。`);
    return;
  }
  if (minRounds > maxRounds) {
    window.alert("最小轮数必须小于等于最大轮数。");
    return;
  }

  try {
    clearInlineError();
    disconnectStream();
    setRunningState(true, "正在创建会话...");
    const session = await api("/api/debates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, min_rounds: minRounds, max_rounds: maxRounds }),
    });
    state.currentSession = { ...session, messages: [] };
    state.currentSessionId = session.id;
    state.reviewTopicExpanded = false;
    state.expandedEvaluationGroups = {};
    resetUserTargetState({ clearSelection: true });
    state.typing = { role: "system", label: "系统", content: "辩论即将开始..." };
    switchView("debate");
    renderCurrentSession();
    connectStream(session.id);
    await loadSessions();
  } catch (error) {
    if (error?.status === 409) {
      setRunningState(false, "已到上限");
      window.alert(error.message || "已到目前进程上限。");
      return;
    }
    setRunningState(false, "启动失败");
    showLocalError(error.message, true);
  }
}

async function fetchSessionIntoState(sessionId) {
  const session = await api(`/api/debates/${sessionId}`);
  if (session?.status === "error") {
    await hydrateErrorDetails(session);
  }
  state.currentSession = session;
  state.currentSessionId = session.id;
  state.typing = isRunningSessionStatus(session?.status) ? session.live_status || null : null;
  clearInlineError();
  return session;
}

async function hydrateErrorDetails(session) {
  if (!session || session.status !== "error") {
    return session;
  }
  if (session.error_message && session.error_traceback) {
    return session;
  }
  try {
    const record = await api(`/api/records/error/${session.id}`);
    const parsed = parseErrorRecord(record.content || "");
    if (!session.error_message && parsed.errorMessage) {
      session.error_message = parsed.errorMessage;
    }
    if (!session.error_traceback && parsed.traceback) {
      session.error_traceback = parsed.traceback;
    }
  } catch {
    // 旧会话可能没有单独的错误记录，直接保持现状即可。
  }
  return session;
}

async function openSession(sessionId, shouldConnect, switchToDebate = true) {
  try {
    closeTitleEditModal({ immediate: true });
    const session = await fetchSessionIntoState(sessionId);
    state.reviewTopicExpanded = false;
    state.expandedEvaluationGroups = {};
    resetUserTargetState({ clearSelection: true });
    if (switchToDebate) {
      switchView("debate");
    }
    renderCurrentSession();
    if (shouldConnect && isLiveSessionStatus(session.status)) {
      connectStream(session.id);
    } else {
      disconnectStream();
    }
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  } catch (error) {
    showLocalError(error.message);
  }
}

function openArchivedModal() {
  void loadArchivedSessions();
  window.clearTimeout(state.archivedModalTimer);
  els.archivedModal.classList.remove("hidden", "modal-leaving");
  requestAnimationFrame(() => {
    els.archivedModal.classList.add("modal-visible");
  });
}

function closeArchivedModal() {
  if (els.archivedModal.classList.contains("hidden")) {
    return;
  }
  window.clearTimeout(state.archivedModalTimer);
  els.archivedModal.classList.remove("modal-visible");
  els.archivedModal.classList.add("modal-leaving");
  state.archivedModalTimer = window.setTimeout(() => {
    els.archivedModal.classList.add("hidden");
    els.archivedModal.classList.remove("modal-leaving");
  }, MODAL_MOTION_MS);
}

async function archiveSession(sessionId) {
  try {
    const session = await api(`/api/debates/${sessionId}/archive`, { method: "POST" });
    if (state.currentSessionId === sessionId && state.currentSession) {
      state.currentSession = session;
    }
    await Promise.all([loadSessions(), loadArchivedSessions(), loadRecords()]);
    renderCurrentSession();
  } catch (error) {
    showLocalError(error.message);
  }
}

async function restoreArchivedSession(sessionId) {
  try {
    const session = await api(`/api/debates/${sessionId}/restore`, { method: "POST" });
    if (state.currentSessionId === sessionId && state.currentSession) {
      state.currentSession = session;
    }
    await Promise.all([loadSessions(), loadArchivedSessions(), loadRecords()]);
    renderCurrentSession();
  } catch (error) {
    showLocalError(error.message);
  }
}

async function deleteSession(sessionId, options = {}) {
  const yes = window.confirm("确认删除这条辩论记录吗？这会同时删除 detail/error 日志。");
  if (!yes) {
    return;
  }
  try {
    await api(`/api/debates/${sessionId}`, { method: "DELETE" });
    if (state.currentSessionId === sessionId) {
      disconnectStream();
      state.currentSession = null;
      state.currentSessionId = null;
      state.typing = null;
      clearInlineError();
      renderCurrentSession();
    }
    const tasks = [loadSessions(), loadRecords()];
    if (options.reloadArchived) {
      tasks.push(loadArchivedSessions());
    }
    await Promise.all(tasks);
  } catch (error) {
    showLocalError(error.message);
  }
}

function connectStream(sessionId, options = {}) {
  const force = Boolean(options.force);
  if (!force && state.eventSource && state.eventSourceSessionId === sessionId) {
    return;
  }
  clearStreamReconnectTimer();
  disconnectStream();
  const source = new EventSource(`/api/debates/${sessionId}/events`);
  state.eventSource = source;
  state.eventSourceSessionId = sessionId;
  source.onopen = () => {
    clearStreamReconnectTimer();
  };
  source.onmessage = async (event) => {
    const payload = JSON.parse(event.data);
    await handleStreamEvent(payload);
  };
  source.onerror = () => {
    if (state.eventSource !== source) {
      return;
    }
    const currentStatus = state.currentSession?.status || "";
    if (state.currentSessionId === sessionId && isLiveSessionStatus(currentStatus)) {
      setRunningState(isRunningSessionStatus(currentStatus), "连接波动，正在自动重连...");
      disconnectStream({ keepReconnectTimer: true });
      scheduleStreamReconnect(sessionId);
    }
  };
}

function clearStreamReconnectTimer() {
  if (state.eventSourceReconnectTimer) {
    window.clearTimeout(state.eventSourceReconnectTimer);
    state.eventSourceReconnectTimer = null;
  }
}

function scheduleStreamReconnect(sessionId, delay = 900) {
  clearStreamReconnectTimer();
  state.eventSourceReconnectTimer = window.setTimeout(() => {
    state.eventSourceReconnectTimer = null;
    if (state.currentSessionId === sessionId && isLiveSessionStatus(state.currentSession?.status || "")) {
      connectStream(sessionId, { force: true });
    }
  }, delay);
}

function disconnectStream(options = {}) {
  if (!options.keepReconnectTimer) {
    clearStreamReconnectTimer();
  }
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  state.eventSourceSessionId = "";
}

async function handleStreamEvent(payload) {
  if (payload.type === "history" || payload.type === "session") {
    state.currentSession = payload.session;
    state.currentSessionId = payload.session?.id || state.currentSessionId;
    state.typing = isRunningSessionStatus(payload.session?.status) ? payload.session?.live_status || null : null;
    setRunningState(isRunningSessionStatus(payload.session?.status), formatStatus(payload.session?.status || "queued"));
    renderCurrentSession();
    return;
  }

  if (!state.currentSession) {
    state.currentSession = { id: payload.session_id, topic: "实时会话", messages: [] };
    state.currentSessionId = payload.session_id;
  }

  if (payload.type === "status") {
    if (state.currentSession) {
      state.currentSession.live_status = payload;
    }
    state.typing = payload;
    setRunningState(true, payload.content);
    renderCurrentSession();
    return;
  }

  if (["message", "summary", "error"].includes(payload.type)) {
    state.typing = null;
    if (state.currentSession) {
      state.currentSession.live_status = null;
    }
    upsertMessage(payload);
    if (payload.type === "error") {
      state.currentSession.status = "error";
      setRunningState(false, "运行出错");
    }
    renderCurrentSession();
    void Promise.all([loadSessions(), loadRecords()]);
    return;
  }

  if (payload.type === "done") {
    state.typing = null;
    if (state.currentSession) {
      state.currentSession.live_status = null;
    }
    disconnectStream();
    if (state.currentSessionId) {
      await openSession(state.currentSessionId, false, false);
    }
  }
}

function upsertMessage(message) {
  state.currentSession.messages = state.currentSession.messages || [];
  const index = state.currentSession.messages.findIndex((item) => item.id === message.id);
  if (index >= 0) {
    state.currentSession.messages[index] = message;
  } else {
    state.currentSession.messages.push(message);
  }
}

function isLiveSessionStatus(status) {
  return ["queued", "running", "paused"].includes(status || "");
}

function isRunningSessionStatus(status) {
  return ["queued", "running"].includes(status || "");
}

function getActiveUserMessage(session) {
  return session?.active_user_message || null;
}

function isDebaterSpeechMessage(message) {
  return ["pro", "con"].includes(String(message?.role || ""));
}

function getMessageRewindMode(session, message) {
  if (!isDebaterSpeechMessage(message)) {
    return "";
  }
  if (isLiveSessionStatus(session?.status)) {
    return "rewind";
  }
  if (session?.status === "completed") {
    return "clone";
  }
  return "";
}

function buildMessageActionKey(sessionId, messageId, mode) {
  return `${sessionId || ""}:${messageId || ""}:${mode || ""}`;
}

function isJudgePhase(session) {
  const phase = String(session?.runtime_state?.phase || "").trim();
  if (session?.status === "paused" || session?.status === "queued") {
    return ["judge_initialize", "judge_summary"].includes(phase);
  }
  const liveRole = String(state.typing?.role || session?.live_status?.role || "").trim();
  if (liveRole) {
    return liveRole === "judge";
  }
  return false;
}

function getUserComposerLockReason(session, activeUserMessage) {
  if (isJudgePhase(session)) {
    return "judge";
  }
  if (activeUserMessage?.stage === "queued") {
    return "queued";
  }
  if (activeUserMessage?.stage === "draft") {
    return "paused_sent";
  }
  return "";
}

async function handleMessageRewindAction(messageId) {
  const session = state.currentSession;
  const sessionId = session?.id || state.currentSessionId;
  if (!sessionId || !session || !messageId) {
    return;
  }

  const message = (session.messages || []).find((item) => item.id === messageId);
  const mode = getMessageRewindMode(session, message);
  if (!mode) {
    return;
  }

  const actionKey = buildMessageActionKey(sessionId, messageId, mode);
  if (state.rewindingMessageActionKey === actionKey) {
    return;
  }

  const confirmText = mode === "clone"
    ? "确认基于这条发言之前的内容创建一个“原标题-恢复”副本吗？原记录不会被改动。"
    : "确认撤回这条发言以及之后的所有记录吗？当前辩论会先转为暂停状态，并从上一条发言结束后重新继续。";
  if (!window.confirm(confirmText)) {
    return;
  }

  state.rewindingMessageActionKey = actionKey;
  renderCurrentSession();
  try {
    const nextSession = await api(`/api/debates/${sessionId}/rewind`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, clone: mode === "clone" }),
    });
    disconnectStream();
    state.currentSession = nextSession;
    state.currentSessionId = nextSession.id;
    state.typing = null;
    state.reviewTopicExpanded = false;
    state.expandedEvaluationGroups = {};
    resetUserTargetState({ clearSelection: true });
    switchView("debate");
    renderCurrentSession();
    await Promise.all([loadSessions(), loadArchivedSessions(), loadRecords()]);
  } catch (error) {
    showLocalError(error.message);
  } finally {
    state.rewindingMessageActionKey = "";
    renderCurrentSession();
  }
}

function toggleUserComposerExpanded() {
  state.userComposerExpanded = !state.userComposerExpanded;
  if (els.userInterjectionInput) {
    els.userInterjectionInput.focus();
  }
  renderCurrentSession();
}

function toggleReviewTopicExpanded() {
  const originalTopic = getOriginalTopicText(state.currentSession);
  if (!originalTopic) {
    return;
  }
  state.reviewTopicExpanded = !state.reviewTopicExpanded;
  renderReviewTopicPopover(state.currentSession);
}

function isTargetRole(role) {
  return role === "pro" || role === "con";
}

function resetUserTargetState(options = {}) {
  const clearSelection = Boolean(options.clearSelection);
  cancelUserTargetSubmenuClose();
  state.userTargetMenuOpen = false;
  state.userTargetSubmenuOpen = false;
  if (clearSelection) {
    state.userMessageTargetRole = "";
  }
}

function getUserTargetLabel(targetRole) {
  if (targetRole === "pro") {
    return "发送正方";
  }
  if (targetRole === "con") {
    return "发送反方";
  }
  return "";
}

function getUserTargetBadge(targetRole) {
  if (targetRole === "pro") {
    return "发送正方";
  }
  if (targetRole === "con") {
    return "发送反方";
  }
  return "";
}

function toggleUserTargetMenu(event) {
  event.preventDefault();
  if (state.userComposerDisabled) {
    return;
  }
  state.userTargetMenuOpen = !state.userTargetMenuOpen;
  if (!state.userTargetMenuOpen) {
    state.userTargetSubmenuOpen = false;
  }
  renderUserTargetControls();
}

function openUserTargetSubmenu() {
  if (!state.userTargetMenuOpen || state.userComposerDisabled) {
    return;
  }
  cancelUserTargetSubmenuClose();
  state.userTargetSubmenuOpen = true;
  renderUserTargetControls();
}

function toggleUserTargetSubmenu(event) {
  event.preventDefault();
  if (state.userComposerDisabled) {
    return;
  }
  state.userTargetMenuOpen = true;
  state.userTargetSubmenuOpen = !state.userTargetSubmenuOpen;
  renderUserTargetControls();
}

function closeUserTargetSubmenu() {
  cancelUserTargetSubmenuClose();
  if (!state.userTargetSubmenuOpen) {
    return;
  }
  state.userTargetSubmenuOpen = false;
  renderUserTargetControls();
}

function scheduleUserTargetSubmenuClose() {
  cancelUserTargetSubmenuClose();
  state.userTargetSubmenuCloseTimer = window.setTimeout(() => {
    state.userTargetSubmenuCloseTimer = null;
    closeUserTargetSubmenu();
  }, 140);
}

function cancelUserTargetSubmenuClose() {
  if (state.userTargetSubmenuCloseTimer) {
    window.clearTimeout(state.userTargetSubmenuCloseTimer);
    state.userTargetSubmenuCloseTimer = null;
  }
}

function handleUserTargetSelection(event) {
  const action = event.target.closest("[data-target-role]");
  if (!(action instanceof HTMLElement)) {
    return;
  }
  const targetRole = String(action.dataset.targetRole || "").trim();
  if (!isTargetRole(targetRole)) {
    return;
  }
  state.userMessageTargetRole = targetRole;
  state.userTargetMenuOpen = false;
  state.userTargetSubmenuOpen = false;
  renderUserTargetControls();
}

function handleUserTargetTagAction(event) {
  const action = event.target.closest("[data-action='clear-user-target']");
  if (!action || state.userComposerDisabled) {
    return;
  }
  const tag = els.userTargetTagSlot?.querySelector(".composer-target-tag");
  if (!(tag instanceof HTMLElement) || tag.classList.contains("is-leaving")) {
    state.userMessageTargetRole = "";
    renderUserTargetControls();
    return;
  }
  tag.classList.add("is-leaving");
  let finalized = false;
  const finalize = () => {
    if (finalized) {
      return;
    }
    finalized = true;
    if (state.userMessageTargetRole) {
      state.userMessageTargetRole = "";
    }
    renderUserTargetControls();
  };
  tag.addEventListener("animationend", finalize, { once: true });
  window.setTimeout(finalize, 220);
}

function toggleEvaluationGroup(groupKey) {
  if (!groupKey) {
    return;
  }
  state.expandedEvaluationGroups = {
    ...state.expandedEvaluationGroups,
    [groupKey]: !Boolean(state.expandedEvaluationGroups[groupKey]),
  };
  renderEvaluationGroups(state.currentSession?.result?.evaluation || {});
}

function getOriginalTopicText(session) {
  const candidates = [
    session?.topic,
    session?.runtime_state?.topic,
    session?.runtime_state?.original_topic,
  ];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function handleDocumentPointerDown(event) {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }

  if (state.reviewTopicExpanded && !target.closest("#toggleReviewTopicBtn") && !target.closest("#reviewTopicDisclosure")) {
    state.reviewTopicExpanded = false;
    renderReviewTopicPopover(state.currentSession);
  }

  if (state.userTargetMenuOpen && !target.closest("#userTargetControl")) {
    cancelUserTargetSubmenuClose();
    state.userTargetMenuOpen = false;
    state.userTargetSubmenuOpen = false;
    renderUserTargetControls();
  }
}

function handleEvaluationGroupClick(event) {
  const group = event.target.closest("[data-evaluation-group]");
  if (!(group instanceof HTMLElement)) {
    return;
  }
  toggleEvaluationGroup(group.dataset.evaluationGroup || "");
}

function handleEvaluationGroupKeydown(event) {
  const group = event.target.closest("[data-evaluation-group]");
  if (!(group instanceof HTMLElement)) {
    return;
  }
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  toggleEvaluationGroup(group.dataset.evaluationGroup || "");
}

function handleUserInterjectionKeydown(event) {
  if (!(event.target instanceof HTMLTextAreaElement) || event.target.disabled) {
    return;
  }
  if (event.key !== "Enter" || event.isComposing) {
    return;
  }
  if (event.shiftKey || state.userComposerExpanded) {
    return;
  }
  event.preventDefault();
  void sendUserInterjection();
}

function getComposerExpandIconSvg(expanded) {
  if (expanded) {
    return `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 10 4.75 4.75" />
        <path d="M4.75 8V4.75H8" />
        <path d="M14 14 19.25 19.25" />
        <path d="M16 19.25h3.25V16" />
      </svg>
    `;
  }
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 4.75H4.75V8" />
      <path d="M4.75 4.75 10 10" />
      <path d="M16 19.25h3.25V16" />
      <path d="M19.25 19.25 14 14" />
    </svg>
  `;
}

function renderCurrentSession() {
  const session = state.currentSession;
  const mode = getDebateMode(session);
  els.debateView.classList.remove("mode-landing", "mode-live", "mode-review");
  els.debateView.classList.add(`mode-${mode}`);
  els.landingPanel.classList.toggle("hidden", mode !== "landing");
  els.livePanel.classList.toggle("hidden", mode !== "live");
  els.reviewPanel.classList.toggle("hidden", mode !== "review");

  if (mode === "landing") {
    renderLandingState();
  } else if (mode === "live") {
    renderLiveState(session);
  } else {
    renderReviewState(session);
  }

  state.currentDebateMode = mode;
  syncCurrentSessionSummary();
  renderSessions();
  scheduleSessionSummaryRefresh();
}

function getDebateMode(session) {
  if (!session) {
    return "landing";
  }
  if (isLiveSessionStatus(session.status)) {
    return "live";
  }
  return "review";
}

function setHeadline(text) {
  const value = text || "";
  els.currentHeadline.textContent = value;
  els.currentHeadline.title = value;
  els.currentHeadline.classList.toggle("headline-editable", canEditCurrentHeadline());
}

function openTitleEditModal() {
  const session = state.currentSession;
  if (!canEditCurrentHeadline() || !session?.id) {
    return;
  }
  state.editingTitleSessionId = session.id;
  window.clearTimeout(state.titleEditModalTimer);
  if (els.titleEditInput) {
    els.titleEditInput.value = getSessionDisplayTitle(session, session.topic);
  }
  els.titleEditModal.classList.remove("hidden", "modal-leaving");
  requestAnimationFrame(() => {
    els.titleEditModal.classList.add("modal-visible");
    if (els.titleEditInput) {
      els.titleEditInput.focus();
      els.titleEditInput.select();
    }
  });
}

function closeTitleEditModal(options = {}) {
  state.editingTitleSessionId = "";
  if (!els.titleEditModal || els.titleEditModal.classList.contains("hidden")) {
    return;
  }
  window.clearTimeout(state.titleEditModalTimer);
  if (options.immediate) {
    els.titleEditModal.classList.add("hidden");
    els.titleEditModal.classList.remove("modal-visible", "modal-leaving");
    return;
  }
  els.titleEditModal.classList.remove("modal-visible");
  els.titleEditModal.classList.add("modal-leaving");
  state.titleEditModalTimer = window.setTimeout(() => {
    els.titleEditModal.classList.add("hidden");
    els.titleEditModal.classList.remove("modal-leaving");
  }, MODAL_MOTION_MS);
}

function handleTitleEditKeydown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    closeTitleEditModal();
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    void submitTitleEdit();
  }
}

async function submitTitleEdit() {
  const sessionId = state.editingTitleSessionId || state.currentSession?.id || state.currentSessionId;
  if (!sessionId || state.savingTitleSessionId === sessionId) {
    return;
  }

  const nextTitle = String(els.titleEditInput?.value || "").trim();
  if (!nextTitle) {
    showLocalError("请输入新的标题。");
    return;
  }

  state.savingTitleSessionId = sessionId;
  if (els.titleEditInput) {
    els.titleEditInput.disabled = true;
  }
  if (els.cancelTitleEditBtn) {
    els.cancelTitleEditBtn.disabled = true;
  }
  if (els.confirmTitleEditBtn) {
    els.confirmTitleEditBtn.disabled = true;
    els.confirmTitleEditBtn.textContent = "保存中...";
  }
  try {
    const nextSession = await api(`/api/debates/${sessionId}/title`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: nextTitle }),
    });
    state.currentSession = nextSession;
    state.currentSessionId = nextSession.id;
    closeTitleEditModal();
    renderCurrentSession();
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  } catch (error) {
    showLocalError(error.message);
  } finally {
    state.savingTitleSessionId = "";
    if (els.titleEditInput) {
      els.titleEditInput.disabled = false;
    }
    if (els.cancelTitleEditBtn) {
      els.cancelTitleEditBtn.disabled = false;
    }
    if (els.confirmTitleEditBtn) {
      els.confirmTitleEditBtn.disabled = false;
      els.confirmTitleEditBtn.textContent = "确认";
    }
  }
}

function openNewDebate() {
  disconnectStream();
  closeTitleEditModal({ immediate: true });
  state.currentSession = null;
  state.currentSessionId = null;
  state.typing = null;
  state.reviewTopicExpanded = false;
  state.expandedEvaluationGroups = {};
  resetUserTargetState({ clearSelection: true });
  state.userComposerExpanded = false;
  state.stoppingSessionId = "";
  state.togglingPauseSessionId = "";
  state.sendingUserMessageSessionId = "";
  state.retractingUserMessageSessionId = "";
  clearInlineError();
  switchView("debate");
  renderCurrentSession();
  if (els.topicInput) {
    els.topicInput.value = "";
    els.topicInput.focus();
  }
  if (els.minRoundsInput) {
    els.minRoundsInput.value = String(DEFAULT_MIN_ROUNDS);
  }
  if (els.maxRoundsInput) {
    els.maxRoundsInput.value = String(DEFAULT_MAX_ROUNDS);
  }
  if (els.userInterjectionInput) {
    els.userInterjectionInput.value = "";
  }
  void loadSessions();
}

async function stopCurrentDebate() {
  const sessionId = state.currentSession?.id || state.currentSessionId;
  const session = state.currentSession;
  if (!sessionId || !session) {
    return;
  }
  if (state.togglingPauseSessionId === sessionId) {
    return;
  }
  const paused = session.status === "paused";
  const yes = window.confirm(paused ? "确认继续当前辩论吗？" : "确认暂停当前辩论吗？");
  if (!yes) {
    return;
  }
  state.togglingPauseSessionId = sessionId;
  renderCurrentSession();
  try {
    const nextSession = await api(`/api/debates/${sessionId}/${paused ? "resume" : "pause"}`, { method: "POST" });
    state.currentSession = nextSession;
    state.currentSessionId = nextSession.id;
    state.typing = isRunningSessionStatus(nextSession.status) ? nextSession.live_status || null : null;
    if (isLiveSessionStatus(nextSession.status)) {
      connectStream(nextSession.id, { force: true });
    } else {
      disconnectStream();
    }
    switchView("debate");
    renderCurrentSession();
    await Promise.all([loadSessions(), loadRecords()]);
  } catch (error) {
    showLocalError(error.message);
  } finally {
    state.togglingPauseSessionId = "";
    renderCurrentSession();
  }
}

async function sendUserInterjection() {
  const session = state.currentSession;
  const sessionId = session?.id || state.currentSessionId;
  if (!sessionId || !session || !isLiveSessionStatus(session.status)) {
    return;
  }
  if (isJudgePhase(session)) {
    showLocalError("裁判正在拆解辩题或进行总结，当前阶段不能插入用户发言。", true);
    return;
  }
  const activeUserMessage = getActiveUserMessage(session);
  if (activeUserMessage) {
    showLocalError("请先撤回当前用户发言后再发送新消息。", true);
    return;
  }
  const content = String(els.userInterjectionInput?.value || "").trim();
  if (!content) {
    showLocalError("请输入要插入的用户发言。", true);
    return;
  }

  state.sendingUserMessageSessionId = sessionId;
  resetUserTargetState();
  renderCurrentSession();
  try {
    const nextSession = await api(`/api/debates/${sessionId}/user-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, target_role: isTargetRole(state.userMessageTargetRole) ? state.userMessageTargetRole : null }),
    });
    state.currentSession = nextSession;
    state.currentSessionId = nextSession.id;
    if (els.userInterjectionInput) {
      els.userInterjectionInput.value = "";
    }
    renderCurrentSession();
    await loadSessions();
  } catch (error) {
    showLocalError(error.message, true);
  } finally {
    state.sendingUserMessageSessionId = "";
    renderCurrentSession();
  }
}

async function retractUserInterjection() {
  const sessionId = state.currentSession?.id || state.currentSessionId;
  if (!sessionId || state.retractingUserMessageSessionId === sessionId) {
    return;
  }

  state.retractingUserMessageSessionId = sessionId;
  renderCurrentSession();
  try {
    const result = await api(`/api/debates/${sessionId}/user-message`, { method: "DELETE" });
    if (result?.session) {
      state.currentSession = result.session;
      state.currentSessionId = result.session.id;
    }
    resetUserTargetState();
    state.userMessageTargetRole = isTargetRole(result?.target_role) ? result.target_role : state.userMessageTargetRole;
    if (els.userInterjectionInput) {
      els.userInterjectionInput.value = String(result?.content || "");
      els.userInterjectionInput.focus();
      els.userInterjectionInput.setSelectionRange(els.userInterjectionInput.value.length, els.userInterjectionInput.value.length);
    }
    renderCurrentSession();
    await loadSessions();
  } catch (error) {
    showLocalError(error.message, true);
  } finally {
    state.retractingUserMessageSessionId = "";
    renderCurrentSession();
  }
}

function renderLandingState() {
  setHeadline("开始一场新的模型辩论");
  setRunningState(false, "空闲中");
  setExportButtonsEnabled(false);
  state.togglingPauseSessionId = "";
  state.sendingUserMessageSessionId = "";
  state.retractingUserMessageSessionId = "";
  renderWorkspace();
  if (state.inlineError) {
    els.landingNotice.textContent = state.inlineError;
    els.landingNotice.classList.remove("hidden");
  } else {
    els.landingNotice.textContent = "";
    els.landingNotice.classList.add("hidden");
  }
}

function renderWorkspace() {
  if (!els.workspaceViewer) {
    return;
  }
  els.workspaceViewer.innerHTML = renderMarkdown(state.workspaceText || "# Workspace\n- 暂无内容。");
  els.workspaceViewer.classList.remove("empty-viewer");
  els.workspaceViewer.scrollTop = 0;
}

function renderLiveState(session) {
  setHeadline(getSessionDisplayTitle(session, session.topic, { placeholderDuringJudge: true }));
  setExportButtonsEnabled(false);
  const statusText = formatStatus(session.status || "queued");
  const isPaused = session.status === "paused";
  const isToggling = state.togglingPauseSessionId === session.id;
  const isSending = state.sendingUserMessageSessionId === session.id;
  const isRetracting = state.retractingUserMessageSessionId === session.id;
  const activeUserMessage = getActiveUserMessage(session);
  const liveStatus = state.typing || session.live_status || null;
  const messages = [...(session.messages || [])];
  const latestMessageId = messages.length ? messages[messages.length - 1].id : "";
  if (els.livePanelTitle) {
    els.livePanelTitle.textContent = isPaused ? "辩论已暂停" : "实时辩论中";
  }
  els.sessionMeta.textContent = `${statusText} · 会话 ${session.id}`;
  els.liveStatusBadge.textContent = isToggling ? (isPaused ? "继续中" : "暂停中") : statusText;
  els.stopDebateBtn.disabled = isToggling;
  els.stopDebateBtn.textContent = isToggling ? (isPaused ? "继续中..." : "暂停中...") : (isPaused ? "继续辩论" : "暂停辩论");
  els.stopDebateBtn.classList.toggle("resume-mode", isPaused && !isToggling);
  setRunningState(isRunningSessionStatus(session.status), isToggling ? (isPaused ? "正在继续辩论..." : "正在暂停辩论...") : statusText);

  const parts = messages.map((message) => renderMessageRow(message, session, { animate: message.id === latestMessageId }));
  if (liveStatus) {
    parts.push(renderTypingRow(liveStatus, session, { animate: true }));
  }
  if (!parts.length) {
    parts.push('<div class="empty-state">辩论准备中，消息会在这里实时展开。</div>');
  }
  els.chatThread.innerHTML = parts.join("");
  scrollThreadToBottom(els.chatThread, true);
  renderQueuedUserMessage(activeUserMessage, { disabled: isRetracting });
  renderUserComposer(session, {
    isPaused,
    isSending,
    isToggling,
    isRetracting,
    activeUserMessage,
  });
}

function renderQueuedUserMessage(activeUserMessage, options = {}) {
  if (!els.queuedUserMessageSlot) {
    return;
  }
  const isQueued = activeUserMessage?.stage === "queued";
  els.queuedUserMessageSlot.classList.toggle("hidden", !isQueued);
  if (!isQueued) {
    els.queuedUserMessageSlot.innerHTML = "";
    return;
  }

  const retracting = Boolean(options.disabled);
  const effectiveTargetRole = isTargetRole(activeUserMessage?.target_role)
    ? activeUserMessage.target_role
    : state.userMessageTargetRole;
  const targetBadge = getUserTargetBadge(effectiveTargetRole);
  els.queuedUserMessageSlot.innerHTML = `
    <article class="queued-user-card">
      <div class="queued-user-copy">
        <span class="queued-user-label">待插入的用户发言</span>
        ${targetBadge ? `<div class="queued-user-target-badge">${escapeHtml(targetBadge)}</div>` : ""}
        <p>${escapeHtml(activeUserMessage.content || "")}</p>
      </div>
      <button class="ghost-button compact-button" type="button" data-action="retract-user-message" ${retracting ? "disabled" : ""}>
        ${retracting ? "撤回中..." : "撤回修改"}
      </button>
    </article>
  `;
}

function renderUserTargetControls() {
  const targetLabel = getUserTargetLabel(state.userMessageTargetRole);
  if (els.toggleUserTargetMenuBtn) {
    const expanded = state.userTargetMenuOpen && !state.userComposerDisabled;
    els.toggleUserTargetMenuBtn.disabled = state.userComposerDisabled;
    els.toggleUserTargetMenuBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
  }
  if (els.userTargetMenu) {
    els.userTargetMenu.classList.toggle("hidden", !state.userTargetMenuOpen || state.userComposerDisabled);
  }
  if (els.userTargetSubmenu) {
    els.userTargetSubmenu.classList.toggle(
      "hidden",
      !state.userTargetMenuOpen || !state.userTargetSubmenuOpen || state.userComposerDisabled,
    );
  }
  if (els.userTargetTagSlot) {
    const hasTarget = Boolean(targetLabel);
    els.userTargetTagSlot.classList.toggle("hidden", !hasTarget);
    const disabledState = state.userComposerDisabled ? "1" : "0";
    const nextStateKey = hasTarget ? `${targetLabel}|${disabledState}` : "";
    if (els.userTargetTagSlot.dataset.renderState !== nextStateKey) {
      els.userTargetTagSlot.innerHTML = hasTarget
        ? `
          <span class="composer-target-tag">
            <span>${escapeHtml(targetLabel)}</span>
            <button
              class="composer-target-tag-remove"
              type="button"
              data-action="clear-user-target"
              aria-label="移除发送对象"
              title="移除发送对象"
              ${state.userComposerDisabled ? "disabled" : ""}
            >
              ×
            </button>
          </span>
        `
        : "";
      els.userTargetTagSlot.dataset.renderState = nextStateKey;
    }
  }
}

function renderUserComposer(session, options = {}) {
  const activeUserMessage = options.activeUserMessage || null;
  if (isTargetRole(activeUserMessage?.target_role)) {
    state.userMessageTargetRole = activeUserMessage.target_role;
  }
  const lockReason = getUserComposerLockReason(session, activeUserMessage);
  const hardLocked = Boolean(lockReason);
  const disabled = options.isSending || options.isToggling || hardLocked || !isLiveSessionStatus(session?.status);
  if (disabled) {
    state.userTargetMenuOpen = false;
    state.userTargetSubmenuOpen = false;
  }
  state.userComposerDisabled = disabled;
  const inputPlaceholder = lockReason === "judge"
    ? ""
    : lockReason === "queued"
      ? "已有一条挂起中的用户发言，请先撤回修改。"
      : lockReason === "paused_sent"
        ? "本次暂停中已发送过一条用户发言，请先撤回修改。"
        : options.isPaused
          ? "暂停中发送会立即加入当前界面，可在继续前撤回修改。"
          : "运行中发送会等待当前辩手说完后插入。";

  if (els.userInterjectionInput) {
    els.userInterjectionInput.disabled = disabled;
    els.userInterjectionInput.placeholder = inputPlaceholder;
    els.userInterjectionInput.rows = state.userComposerExpanded ? 8 : 2;
  }
  if (els.sendUserMessageBtn) {
    els.sendUserMessageBtn.disabled = disabled;
    els.sendUserMessageBtn.classList.toggle("sending", Boolean(options.isSending));
  }
  if (els.toggleUserComposerExpandBtn) {
    els.toggleUserComposerExpandBtn.disabled = disabled;
    els.toggleUserComposerExpandBtn.innerHTML = getComposerExpandIconSvg(state.userComposerExpanded);
    els.toggleUserComposerExpandBtn.title = state.userComposerExpanded ? "收起编辑" : "展开编辑";
    els.toggleUserComposerExpandBtn.setAttribute("aria-label", state.userComposerExpanded ? "收起编辑" : "展开编辑");
    els.toggleUserComposerExpandBtn.setAttribute("aria-expanded", state.userComposerExpanded ? "true" : "false");
  }
  if (els.liveComposerShell) {
    els.liveComposerShell.classList.toggle("composer-locked", hardLocked);
    els.liveComposerShell.classList.toggle("composer-expanded", state.userComposerExpanded);
  }
  renderUserTargetControls();
  if (els.userComposerHint) {
    let hintText = "";
    if (options.isSending) {
      hintText = "正在提交用户发言...";
    } else if (options.isRetracting) {
      hintText = "正在撤回用户发言...";
    } else if (lockReason === "judge") {
      hintText = "";
    } else if (lockReason === "queued") {
      hintText = "当前用户发言会在正在说话的辩手结束后插入，你可以先撤回修改。";
    } else if (lockReason === "paused_sent") {
      hintText = "当前暂停阶段已经插入一条用户发言，继续辩论后会自动锁定。";
    } else if (state.userComposerExpanded) {
      hintText = "已展开编辑，Enter 换行；发送请点击右侧按钮。";
    }
    els.userComposerHint.textContent = hintText;
    els.userComposerHint.classList.toggle("hidden", !hintText);
  }
}

function renderReviewState(session) {
  setHeadline(getSessionDisplayTitle(session, session.topic));
  setExportButtonsEnabled(Boolean(session?.id));
  const statusText = formatStatus(session.status || "completed");
  els.reviewMeta.textContent = `${statusText} · 会话 ${session.id}`;
  els.reviewStatusBadge.textContent = statusText;
  renderReviewTopicPopover(session);
  renderReviewErrorAction(session);
  setRunningState(false, statusText);
  state.stoppingSessionId = "";
  state.togglingPauseSessionId = "";
  state.sendingUserMessageSessionId = "";
  state.retractingUserMessageSessionId = "";

  const result = session.result || {};
  const hasError = session.status === "error";
  const isTerminated = session.status === "terminated";
  if (hasError) {
    const errorMessage = session.error_message || "本场辩论在运行过程中发生错误。";
    const tracebackText = session.error_traceback || "暂无 Traceback，可点击回放区的“查看错误”按钮预览错误记录。";
    els.resultWinner.textContent = "本场辩论中断";
    els.resultScores.innerHTML = "";
    els.resultHighlights.innerHTML = "";
    els.resultConclusion.textContent = errorMessage;
    els.resultConclusion.classList.add("error-detail");
    els.resultErrorBox.textContent = `Traceback\n${tracebackText}`;
    els.resultErrorBox.classList.remove("hidden");
  } else if (isTerminated) {
    els.resultWinner.textContent = "本场辩论已终止";
    els.resultScores.innerHTML = "";
    els.resultHighlights.innerHTML = "";
    els.resultConclusion.textContent = session.termination_message || "用户手动终止";
    els.resultConclusion.classList.remove("error-detail");
    els.resultErrorBox.classList.add("hidden");
    els.resultErrorBox.textContent = "";
  } else {
    els.resultWinner.textContent = `裁判判定：${result.winner || "待定"}`;
    els.resultScores.innerHTML = [
      renderScoreCard("正方", result.pro_score),
      renderScoreCard("反方", result.con_score),
    ].join("");
    renderEvaluationGroups(result.evaluation || {});
    els.resultConclusion.textContent = result.conclusion || "本场辩论已经结束，可从左侧切换历史会话。";
    els.resultConclusion.classList.remove("error-detail");
    els.resultErrorBox.classList.add("hidden");
    els.resultErrorBox.textContent = "";
  }

  renderUsageSummary(session);

  const messages = [...(session.messages || [])];
  els.reviewThread.innerHTML = messages.length
    ? messages.map((message) => renderMessageRow(message, session)).join("")
    : '<div class="empty-state">这场辩论没有留下可展示的消息记录。</div>';
  els.reviewThread.scrollTop = 0;
}

function renderReviewTopicPopover(session) {
  const originalTopic = getOriginalTopicText(session);
  const canShowOriginalTopic = Boolean(originalTopic);
  if (els.toggleReviewTopicBtn) {
    els.toggleReviewTopicBtn.classList.remove("hidden");
    els.toggleReviewTopicBtn.disabled = !canShowOriginalTopic;
    els.toggleReviewTopicBtn.textContent = state.reviewTopicExpanded ? "收起辩题" : "查看辩题";
    els.toggleReviewTopicBtn.setAttribute("aria-expanded", state.reviewTopicExpanded ? "true" : "false");
    els.toggleReviewTopicBtn.title = canShowOriginalTopic ? "查看原始辩题" : "当前记录没有可显示的原始辩题";
  }
  if (els.reviewTopicField) {
    els.reviewTopicField.textContent = originalTopic;
  }
  if (els.reviewTopicDisclosure) {
    els.reviewTopicDisclosure.classList.toggle("hidden", !canShowOriginalTopic || !state.reviewTopicExpanded);
  }
}

function renderReviewErrorAction(session) {
  if (!els.previewErrorBtn) {
    return;
  }
  const hasError = session?.status === "error" || Boolean(session?.error_message || session?.error_traceback);
  els.previewErrorBtn.classList.toggle("hidden", !hasError);
  els.previewErrorBtn.disabled = !hasError || !session?.id;
  els.previewErrorBtn.title = hasError ? "预览本场辩论的错误 Markdown" : "";
}

function renderUsageSummary(session) {
  if (!els.resultUsage) {
    return;
  }
  const usageStats = session?.usage_stats;
  const roles = usageStats?.roles;
  if (!usageStats?.enabled || !roles) {
    els.resultUsage.innerHTML = "";
    els.resultUsage.classList.add("hidden");
    return;
  }

  els.resultUsage.innerHTML = [
    renderUsageCard("正方", roles.pro || {}),
    renderUsageCard("反方", roles.con || {}),
  ].join("");
  els.resultUsage.classList.remove("hidden");
}

function renderUsageCard(label, usage) {
  const totalTokens = Number(usage?.total_tokens || 0);
  const inputTokens = Number(usage?.input_tokens || 0);
  const outputTokens = Number(usage?.output_tokens || 0);
  const searchCalls = Number(usage?.search_calls || 0);
  const estimatedSuffix = usage?.estimated ? "（估算）" : "";
  return `
    <section class="usage-card">
      <div class="usage-card-head">
        <span class="score-label">${escapeHtml(label)}</span>
        <div class="usage-total-block">
          <span class="usage-total-label">总 Token</span>
          <strong class="usage-total">${escapeHtml(formatTokenCount(totalTokens))}${estimatedSuffix}</strong>
        </div>
      </div>
      <div class="usage-meta">
        <span>输入 ${escapeHtml(formatTokenCount(inputTokens))}</span>
        <span>输出 ${escapeHtml(formatTokenCount(outputTokens))}</span>
        <span>网络搜索 ${escapeHtml(searchCalls)} 次</span>
      </div>
    </section>
  `;
}

function formatTokenCount(value) {
  const count = Number(value || 0);
  return NUMBER_FORMATTER.format(Number.isFinite(count) ? count : 0);
}

function scrollThreadToBottom(container, smooth = false) {
  if (!container) {
    return;
  }
  const top = container.scrollHeight;
  if (smooth && typeof container.scrollTo === "function") {
    container.scrollTo({ top, behavior: "smooth" });
    return;
  }
  container.scrollTop = top;
}

function renderScoreCard(label, score) {
  const safeScore = score ?? "--";
  return `
    <div class="score-card">
      <span class="score-label">${escapeHtml(label)}</span>
      <strong class="score-value">${escapeHtml(safeScore)}</strong>
    </div>
  `;
}

function renderEvaluation(evaluation) {
  const groups = [
    { key: "pro_strengths", title: "正方优点", items: evaluation.pro_strengths || [] },
    { key: "pro_weaknesses", title: "正方不足", items: evaluation.pro_weaknesses || [] },
    { key: "con_strengths", title: "反方优点", items: evaluation.con_strengths || [] },
    { key: "con_weaknesses", title: "反方不足", items: evaluation.con_weaknesses || [] },
  ].filter((group) => group.items.length);

  if (!groups.length) {
    return '<div class="result-note">裁判未返回细分评价，本区保持为空。</div>';
  }

  return groups
    .map(
      (group) => `
        <section
          class="highlight-group highlight-group-collapsible${state.expandedEvaluationGroups[group.key] ? " expanded" : ""}"
          data-evaluation-group="${escapeAttribute(group.key)}"
          tabindex="0"
          role="button"
          aria-expanded="${state.expandedEvaluationGroups[group.key] ? "true" : "false"}"
        >
          <div class="highlight-group-head">
            <h5>${escapeHtml(group.title)}</h5>
            <span class="highlight-toggle-indicator" aria-hidden="true">^</span>
          </div>
          <div class="highlight-group-body">
            <p>${escapeHtml(group.items.join("，"))}</p>
          </div>
        </section>
      `,
    )
    .join("");
}

function renderEvaluationGroups(evaluation) {
  els.resultHighlights.innerHTML = renderEvaluation(evaluation);
}

function getSessionModelName(session, role) {
  const config = session?.config_summary?.[role] || {};
  return String(config.model || config.azure_deployment || "").trim();
}

function getRoleDisplayLabel(messageOrStatus, session) {
  const role = messageOrStatus?.role || "system";
  if (role === "user") {
    return "用户发言";
  }
  const baseLabel = messageOrStatus?.label || ROLE_LABELS[role] || "系统";
  if (!["pro", "con"].includes(role)) {
    return baseLabel;
  }
  const modelName = getSessionModelName(session, role);
  return modelName ? `${baseLabel} · ${modelName}` : baseLabel;
}

function renderMessageRow(message, session, options = {}) {
  let position = "center";
  let variant = "summary";
  if (message.role === "pro") {
    position = "left";
    variant = "pro";
  } else if (message.role === "con") {
    position = "right";
    variant = "con";
  } else if (message.role === "user") {
    position = "center";
    variant = message.locked ? "user" : "user draft";
  } else if (message.role === "judge") {
    position = "center";
    variant = "summary judge";
  } else if (message.type === "error") {
    variant = "error";
  }

  const displayLabel = getRoleDisplayLabel(message, session);
  const rawContent = extractDebaterSpeechText(message.content) || String(message.content || "");
  const renderedContent = (message.role === "pro" || message.role === "con")
    ? stripDebateMarkdownStructure(rawContent)
    : rawContent;
  const targetBadge = message.role === "user" ? getUserTargetBadge(message.target_role) : "";
  const animateClass = options.animate ? " entering" : "";
  const retractable = message.role === "user" && session?.status === "paused" && !message.locked && getActiveUserMessage(session)?.id === message.id;
  const roundLabel = message.round ? `第 ${message.round} 轮` : "";
  const timestampParts = formatMessageTimestamp(message.timestamp);
  const inlineTimestampText = (message.role === "user" || message.role === "judge") && timestampParts
    ? [timestampParts.major, timestampParts.minor].filter(Boolean).join(" ")
    : "";
  const rewindMode = getMessageRewindMode(session, message);
  const rewindActionKey = buildMessageActionKey(session?.id || state.currentSessionId, message?.id, rewindMode);
  const rewinding = rewindMode && state.rewindingMessageActionKey === rewindActionKey;
  const actionHtml = retractable
    ? `
        <div class="message-foot">
          <button class="ghost-button compact-button message-inline-action" type="button" data-action="retract-user-message" ${
            state.retractingUserMessageSessionId === session?.id ? "disabled" : ""
          }>
            ${state.retractingUserMessageSessionId === session?.id ? "撤回中..." : "撤回修改"}
          </button>
        </div>
      `
    : "";
  const rewindButtonHtml = rewindMode
    ? `
        <button
          class="message-rewind-button"
          type="button"
          data-action="rewind-message"
          data-message-id="${escapeAttribute(message.id || "")}"
          title="${rewindMode === "clone" ? "恢复辩论" : "撤回到这条之前"}"
          aria-label="${rewindMode === "clone" ? "恢复辩论" : "撤回到这条之前"}"
          ${rewinding ? "disabled" : ""}
        >
          ${getMessageRewindIconSvg()}
        </button>
      `
    : "";
  const headMetaHtml = roundLabel
    ? `
        <div class="message-head-meta">
          ${roundLabel ? `<span class="message-round">${roundLabel}</span>` : ""}
        </div>
      `
    : "";
  const rowClass = `message-row ${position}${message.role === "user" ? " user-message-row" : ""}${message.role === "judge" ? " judge-message-row" : ""}`;
  return `
    <div class="${rowClass}">
      <div class="message-bubble-group">
        <article class="message-card ${variant}${animateClass}">
          <div class="message-head${headMetaHtml ? " has-meta" : ""}">
            <div class="message-head-main${message.role === "user" ? " user-message-head-main" : ""}${message.role === "judge" ? " judge-message-head-main" : ""}">
              <span class="message-label">${escapeHtml(displayLabel)}</span>
              ${targetBadge ? `<span class="message-target-badge">${escapeHtml(targetBadge)}</span>` : ""}
              ${inlineTimestampText ? `<span class="message-head-timestamp">${escapeHtml(inlineTimestampText)}</span>` : ""}
            </div>
            ${headMetaHtml}
          </div>
          <div class="message-content">${formatTextBlock(renderedContent)}</div>
          ${actionHtml}
        </article>
        ${rewindButtonHtml}
        ${timestampParts && !["user", "judge"].includes(message.role) ? `
          <span class="message-timestamp">
            ${timestampParts.major ? `<span class="message-timestamp-major">${escapeHtml(timestampParts.major)}</span>` : ""}
            <span class="message-timestamp-minor">${escapeHtml(timestampParts.minor)}</span>
          </span>
        ` : ""}
      </div>
    </div>
  `;
}

function renderTypingRow(status, session, options = {}) {
  const displayLabel = getRoleDisplayLabel(status, session);
  const animateClass = options.animate ? " entering" : "";
  return `
    <div class="message-row center">
      <div class="typing-card${animateClass}">
        <strong>${escapeHtml(displayLabel)}</strong>
        <span>${escapeHtml(status.content || "思考中")}</span>
        <span class="typing-dots"><span></span><span></span><span></span></span>
      </div>
    </div>
  `;
}

async function loadRecords() {
  const records = await api("/api/records");
  state.records = {
    detail: (records.detail || []).map((item) => ({
      ...item,
      display_title: getRecordDisplayTitle(item),
    })),
    error: (records.error || []).map((item) => ({
      ...item,
      display_title: getRecordDisplayTitle(item),
    })),
  };
  renderRecordLists();
}

function renderRecordLists() {
  renderOneRecordList(els.detailRecordsList, state.records.detail, "detail");
  renderOneRecordList(els.errorRecordsList, state.records.error, "error");
}

function getRecordDisplayTitle(record) {
  const explicitTitle = String(record?.display_title || record?.displayTitle || "").trim();
  if (explicitTitle) {
    return explicitTitle;
  }
  const sessionId = String(record?.session_id || record?.sessionId || "").trim();
  const sessionCandidates = [
    ...(Array.isArray(state.sessions) ? state.sessions : []),
    ...(Array.isArray(state.archivedSessions) ? state.archivedSessions : []),
    state.currentSession,
  ];
  for (const session of sessionCandidates) {
    if (!session || String(session.id || "").trim() !== sessionId) {
      continue;
    }
    const candidate = String(session.runtime_state?.debate_title || session.topic || "").trim();
    if (candidate) {
      return candidate;
    }
  }
  return String(record?.topic || "").trim();
}

function getRecordViewerHeadline(record) {
  if (!record) {
    return "记录查看";
  }
  const prefix = record.kind === "error" ? "错误" : "详情";
  return `${prefix}·${getRecordDisplayTitle(record) || "记录查看"}`;
}

function normalizeRecordContent(record) {
  const content = String(record?.content || "");
  const displayTitle = getRecordDisplayTitle(record);
  if (!content.trim() || !displayTitle) {
    return content;
  }
  const prefix = record?.kind === "error" ? "错误" : "详情";
  return content
    .replace(/^# .*/m, `# ${prefix}·${displayTitle}`)
    .replace(/^- 辩题：.*$/m, `- 标题：${displayTitle}`);
}

function renderOneRecordList(container, items, kind) {
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">这里暂时还没有记录。</div>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const active = state.currentRecord?.kind === kind && state.currentRecord?.sessionId === item.session_id ? "active" : "";
      const meta = `${formatStatus(item.status)} · ${formatDate(item.created_at)}`;
      const displayTitle = getRecordDisplayTitle(item);
      return `
        <div class="record-item ${active}" data-record-kind="${kind}" data-session-id="${item.session_id}">
          <div title="${escapeAttribute(displayTitle)}">
            <p class="record-title" title="${escapeAttribute(displayTitle)}">${escapeHtml(displayTitle)}</p>
            <div class="record-meta" title="${escapeAttribute(meta)}">${escapeHtml(meta)}</div>
          </div>
        </div>
      `;
    })
    .join("");
}

async function openRecord(kind, sessionId) {
  try {
    const record = await api(`/api/records/${kind}/${sessionId}`);
    state.currentRecord = {
      kind,
      sessionId,
      topic: record.topic,
      displayTitle: getRecordDisplayTitle({ ...record, kind, sessionId }),
    };
    els.recordViewerTitle.textContent = getRecordViewerHeadline(state.currentRecord);
    setHeadline(getRecordViewerHeadline(state.currentRecord));
    els.recordViewer.classList.remove("empty-viewer");
    els.recordViewer.innerHTML = renderMarkdown(normalizeRecordContent({ ...record, kind, sessionId, displayTitle: state.currentRecord.displayTitle }));
    els.recordViewer.scrollTop = 0;
    els.recordViewer.scrollLeft = 0;
    els.deleteRecordBtn.disabled = false;
    renderRecordLists();
  } catch (error) {
    showLocalError(error.message);
  }
}

async function deleteCurrentRecord() {
  if (!state.currentRecord) {
    return;
  }
  const yes = window.confirm("确认删除当前记录吗？");
  if (!yes) {
    return;
  }

  try {
    await api(`/api/records/${state.currentRecord.kind}/${state.currentRecord.sessionId}`, { method: "DELETE" });
    state.currentRecord = null;
    els.recordViewerTitle.textContent = "选择一份记录";
    if (state.currentView === "records") {
      setHeadline("记录查看");
    }
    els.recordViewer.classList.add("empty-viewer");
    els.recordViewer.textContent = "选择左侧记录后，会在这里以只读 Markdown 方式展示。";
    els.deleteRecordBtn.disabled = true;
    await loadRecords();
  } catch (error) {
    showLocalError(error.message);
  }
}

function switchView(view) {
  if (view !== "debate") {
    closeTitleEditModal({ immediate: true });
  }
  const showDebate = view === "debate";
  els.debateView.classList.toggle("view-active", showDebate);
  els.recordsView.classList.toggle("view-active", !showDebate);
  state.reviewTopicExpanded = false;
  resetUserTargetState();
  state.expandedEvaluationGroups = {};
  state.currentView = view;
  if (view === "records") {
    setHeadline(state.currentRecord ? getRecordViewerHeadline(state.currentRecord) : "记录查看");
  }
}

function setRunningState(isRunning, text) {
  els.runStatusBadge.textContent = text;
  els.startDebateBtn.disabled = isRunning;
  renderHomeDebaterBinding();
}

function setExportButtonsEnabled(enabled) {
  els.exportSimpleBtn.disabled = !enabled;
  els.exportDetailBtn.disabled = !enabled;
}

function getExportSessionId() {
  return state.currentSession?.id || state.currentSessionId || state.currentRecord?.sessionId || "";
}

function parseDownloadFilename(disposition) {
  const value = String(disposition || "");
  const utfMatch = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch) {
    try {
      return decodeURIComponent(utfMatch[1]);
    } catch {
      return utfMatch[1];
    }
  }
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1] : "";
}

async function fetchSessionExportMarkdown(sessionId, kind) {
  const response = await fetch(`/api/debates/${encodeURIComponent(sessionId)}/export/${encodeURIComponent(kind)}`);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const content = await response.text();
  const fileName = parseDownloadFilename(response.headers.get("Content-Disposition")) || `${sessionId}-${kind}.md`;
  return { content, fileName };
}

async function fetchErrorRecordMarkdown(session) {
  const sessionId = session?.id || getExportSessionId();
  if (!sessionId) {
    throw new Error("请先选择一条可预览的辩论记录。");
  }
  try {
    const record = await api(`/api/records/error/${encodeURIComponent(sessionId)}`);
    const displayTitle = getRecordDisplayTitle({ ...record, kind: "error", sessionId });
    return {
      content: normalizeRecordContent({ ...record, kind: "error", sessionId, displayTitle }),
      fileName: `${sessionId}-error.md`,
    };
  } catch (error) {
    if (error?.status && error.status !== 404) {
      throw error;
    }
    return {
      content: buildErrorMarkdownFromSession(session),
      fileName: `${sessionId}-error.md`,
    };
  }
}

function buildErrorMarkdownFromSession(session) {
  const title = getSessionDisplayTitle(session, session?.topic) || "辩论错误记录";
  const createdAt = formatDate(session?.created_at);
  const errorMessage = session?.error_message || "本场辩论在运行过程中发生错误。";
  const tracebackText = session?.error_traceback || "暂无 Traceback。";
  return [
    `# 错误·${title}`,
    "",
    `- 会话 ID：${session?.id || "--"}`,
    `- 时间：${createdAt}`,
    `- 状态：${formatStatus(session?.status || "error")}`,
    "",
    "## 错误信息",
    "",
    "```text",
    errorMessage,
    "```",
    "",
    "## Traceback",
    "",
    "```text",
    tracebackText,
    "```",
  ].join("\n");
}

function getMarkdownPreviewMeta(kind) {
  if (kind === "simple") {
    return { eyebrow: "Simple Preview", title: "简版记录预览" };
  }
  if (kind === "detail") {
    return { eyebrow: "Detail Preview", title: "细版记录预览" };
  }
  if (kind === "error") {
    return { eyebrow: "Error Preview", title: "错误记录预览" };
  }
  return { eyebrow: "Markdown Preview", title: "记录预览" };
}

function showMarkdownPreviewShell(kind) {
  const meta = getMarkdownPreviewMeta(kind);
  state.markdownPreview = {
    kind,
    sessionId: getExportSessionId(),
    content: "",
    fileName: "",
  };
  window.clearTimeout(state.markdownPreviewModalTimer);
  els.markdownPreviewModal.classList.remove("hidden", "modal-leaving");
  els.markdownPreviewModal.classList.add("modal-visible");
  els.markdownPreviewEyebrow.textContent = meta.eyebrow;
  els.markdownPreviewTitle.textContent = meta.title;
  els.markdownPreviewViewer.classList.add("empty-viewer");
  els.markdownPreviewViewer.textContent = "正在读取 Markdown 记录...";
  els.downloadMarkdownPreviewBtn.disabled = true;
}

async function openMarkdownPreview(kind) {
  const sessionId = getExportSessionId();
  if (!sessionId) {
    showLocalError("请先选择一条可预览的辩论记录。", true);
    return;
  }

  showMarkdownPreviewShell(kind);
  try {
    const payload = kind === "error"
      ? await fetchErrorRecordMarkdown(state.currentSession)
      : await fetchSessionExportMarkdown(sessionId, kind);
    state.markdownPreview = {
      kind,
      sessionId,
      content: payload.content,
      fileName: payload.fileName || `${sessionId}-${kind}.md`,
    };
    els.markdownPreviewViewer.classList.remove("empty-viewer");
    els.markdownPreviewViewer.innerHTML = renderMarkdown(payload.content);
    els.markdownPreviewViewer.scrollTop = 0;
    els.markdownPreviewViewer.scrollLeft = 0;
    els.downloadMarkdownPreviewBtn.disabled = !payload.content;
  } catch (error) {
    state.markdownPreview = null;
    els.markdownPreviewViewer.classList.add("empty-viewer");
    els.markdownPreviewViewer.textContent = error.message || "读取 Markdown 记录失败。";
    els.downloadMarkdownPreviewBtn.disabled = true;
    showLocalError(error.message, true);
  }
}

function closeMarkdownPreviewModal({ immediate = false } = {}) {
  window.clearTimeout(state.markdownPreviewModalTimer);
  if (immediate) {
    els.markdownPreviewModal.classList.add("hidden");
    els.markdownPreviewModal.classList.remove("modal-visible", "modal-leaving");
    return;
  }
  els.markdownPreviewModal.classList.remove("modal-visible");
  els.markdownPreviewModal.classList.add("modal-leaving");
  state.markdownPreviewModalTimer = window.setTimeout(() => {
    els.markdownPreviewModal.classList.add("hidden");
    els.markdownPreviewModal.classList.remove("modal-leaving");
  }, MODAL_MOTION_MS);
}

function triggerMarkdownDownload(content, fileName) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = fileName || "debate-record.md";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function downloadMarkdownPreview() {
  if (!state.markdownPreview?.content) {
    showLocalError("当前没有可导出的 Markdown 内容。", true);
    return;
  }
  triggerMarkdownDownload(state.markdownPreview.content, state.markdownPreview.fileName);
}

async function downloadSessionExport(kind) {
  const sessionId = getExportSessionId();
  if (!sessionId) {
    showLocalError("请先选择一条可导出的辩论记录。", true);
    return;
  }

  try {
    const payload = await fetchSessionExportMarkdown(sessionId, kind);
    triggerMarkdownDownload(payload.content, payload.fileName);
  } catch (error) {
    showLocalError(error.message, true);
  }
}
function clearInlineError() {
  state.inlineError = "";
}

function showLocalError(message, ephemeral = false) {
  const isLiveSession = state.currentSession && isLiveSessionStatus(state.currentSession.status);
  if (!isLiveSession) {
    state.inlineError = message;
    renderCurrentSession();
    if (ephemeral) {
      setTimeout(() => {
        if (state.inlineError === message) {
          clearInlineError();
          renderCurrentSession();
        }
      }, 3600);
    }
    return;
  }

  const errorMessage = {
    id: `local-${Date.now()}`,
    type: "error",
    role: "system",
    label: "系统",
    content: message,
    timestamp: new Date().toISOString(),
  };
  upsertMessage(errorMessage);
  renderCurrentSession();
}

function parseErrorRecord(markdown) {
  const text = String(markdown || "").replace(/\r/g, "");
  const errorMatch = text.match(/## 错误信息\s+```text\n([\s\S]*?)\n```/);
  const tracebackMatch = text.match(/## Traceback\s+```text\n([\s\S]*?)\n```/);
  return {
    errorMessage: errorMatch ? errorMatch[1].trim() : "",
    traceback: tracebackMatch ? tracebackMatch[1].trim() : "",
  };
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r/g, "").split("\n");
  let html = "";
  let inCode = false;
  let codeBuffer = [];
  let paragraph = [];
  let list = [];

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html += `<p>${formatInline(paragraph.join(" "))}</p>`;
    paragraph = [];
  };

  const flushList = () => {
    if (!list.length) {
      return;
    }
    html += `<ul>${list.map((item) => `<li>${formatInline(item)}</li>`).join("")}</ul>`;
    list = [];
  };

  for (const line of lines) {
    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCode) {
        html += `<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
        codeBuffer = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    if (line.startsWith("### ")) {
      flushParagraph();
      flushList();
      html += `<h3>${formatInline(line.slice(4).trim())}</h3>`;
      continue;
    }
    if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      html += `<h2>${formatInline(line.slice(3).trim())}</h2>`;
      continue;
    }
    if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      html += `<h1>${formatInline(line.slice(2).trim())}</h1>`;
      continue;
    }
    if (line.startsWith("- ")) {
      flushParagraph();
      list.push(line.slice(2).trim());
      continue;
    }
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  if (codeBuffer.length) {
    html += `<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
  }
  const content = html || '<div class="empty-state">这份记录是空的。</div>';
  return `<div class="record-viewer-content">${content}</div>`;
}

function formatInline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function formatNoticeText(text) {
  return escapeHtml(String(text || "")).replace(/\r/g, "").replace(/\n/g, "<br />") || "暂无须知内容。";
}

function formatTextBlock(text) {
  return escapeHtml(text).replace(/\n/g, "<br />");
}

function formatStatus(status) {
  const map = {
    queued: "排队中",
    running: "运行中",
    paused: "已暂停",
    completed: "已完成",
    terminated: "已终止",
    error: "出错",
  };
  return map[status] || status || "未知";
}

function formatDate(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatMessageTimestamp(value) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  const now = new Date();
  const elapsed = Math.max(0, now.getTime() - date.getTime());
  const monthMs = 31 * 24 * 60 * 60 * 1000;
  const yearMs = 365 * 24 * 60 * 60 * 1000;
  const yyyy = String(date.getFullYear());
  const MM = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const HH = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  const minor = `${dd}日${HH}时${mm}分${ss}秒`;

  if (elapsed > yearMs) {
    return {
      major: `${yyyy}年${MM}月`,
      minor,
    };
  }
  if (elapsed > monthMs) {
    return {
      major: `${MM}月`,
      minor,
    };
  }
  return {
    major: "",
    minor,
  };
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttribute(text) {
  return escapeHtml(text).replace(/`/g, "&#96;");
}
