const ROLE_LABELS = {
  judge: "裁判",
  pro: "正方",
  con: "反方",
  user: "用户消息",
  system: "系统",
};

const MODAL_MOTION_MS = 180;
const SESSION_SUMMARY_REFRESH_MS = 2000;
const SESSION_LIST_REFRESH_DEBOUNCE_MS = 320;
const DEFAULT_API_TIMEOUT_MS = 45000;
const EXPORT_API_TIMEOUT_MS = 90000;
const MODEL_TASK_API_TIMEOUT_MS = 360000;
const NUMBER_FORMATTER = new Intl.NumberFormat("zh-CN");
const DEFAULT_CONTEXT_ROUNDS = 3;
const MIN_CONTEXT_ROUNDS = 2;
const MAX_CONTEXT_ROUNDS = 6;
const RESPONSE_FLOW_MAX_BLOCKS = 10;
const RESPONSE_FLOW_MIN_THINKING_TOKENS = 128;
const RESPONSE_FLOW_MAX_THINKING_TOKENS = 32768;
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
      output_truncate_chars: 2500,
    },
  },
];
const CONFIG_MANAGER_TABS = [
  { id: "supplier", label: "配置供应商", listTitle: "供应商列表", countLabel: "供应商" },
  { id: "tool", label: "配置工具", listTitle: "工具列表", countLabel: "工具" },
  { id: "debater", label: "配置辩手", listTitle: "辩手列表", countLabel: "辩手" },
];
const UTILITY_MODEL_TABS = [
  { id: "judge", label: "裁判模型", note: "裁判也从供应商中选择接入信息，只在这里填写模型和裁判专属参数。", supplierLabel: "裁判供应商" },
  { id: "translator", label: "翻译模型", note: "预留给后续翻译功能使用，配置方式与裁判模型一致，目前暂不参与辩论流程。", supplierLabel: "翻译供应商" },
  { id: "summarizer", label: "总结模型", note: "预留给后续总结功能使用，配置方式与裁判模型一致，目前暂不参与辩论流程。", supplierLabel: "总结供应商" },
];
const MIN_DEBATE_ROUNDS = 2;
const MAX_DEBATE_ROUNDS = 10;
const DEFAULT_MIN_ROUNDS = 4;
const DEFAULT_MAX_ROUNDS = 6;

const state = {
  settings: null,
  sessions: [],
  archivedSessions: [],
  currentSession: null,
  currentSessionId: null,
  typing: null,
  eventSource: null,
  eventSourceSessionId: "",
  eventSourceReconnectTimer: null,
  inlineError: "",
  selectedPresetEditorId: "",
  selectedSupplierId: "",
  selectedToolConfigId: "",
  activeUtilityModelKey: "judge",
  utilityModelSwitcherOpen: false,
  presetManagerOpen: false,
  presetManagerTab: "debater",
  responseFlowEditorOpen: false,
  responseFlowDraggingBlockId: "",
  expandedToolChoiceIds: {},
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
  homeBindingSavePromise: null,
  startDebateLocked: false,
  settingsSnapshot: null,
  settingsDarkModeSnapshot: false,
  settingsModalTimer: null,
  archivedModalTimer: null,
  markdownPreviewModalTimer: null,
  markdownPreviewRequestId: 0,
  markdownPreviewController: null,
  markdownPreview: null,
  messageDetailModalTimer: null,
  messageDetailLoadingKey: "",
  messageDetailTask: null,
  messageDetail: null,
  sessionSummaryRefreshTimer: null,
  sessionSummaryRefreshInFlight: false,
  sessionListRequestId: 0,
  sessionListRefreshTimer: null,
  sessionOpenRequestId: 0,
  sessionOpenController: null,
  reviewTopicExpanded: false,
  expandedEvaluationGroups: {},
  userMessageTargetRole: "",
  userTargetMenuOpen: false,
  userTargetSubmenuOpen: false,
  userTargetSubmenuCloseTimer: null,
  userComposerDisabled: false,
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
  const initialLoads = [
    ["设置", loadSettings],
    ["会话", loadSessions],
    ["归档", loadArchivedSessions],
    ["须知", loadNotice],
    ["工作区", loadWorkspace],
  ];
  const results = await Promise.allSettled(initialLoads.map(([, loader]) => loader()));
  renderCurrentSession();
  const failedLabels = results
    .map((result, index) => (result.status === "rejected" ? initialLoads[index][0] : ""))
    .filter(Boolean);
  if (failedLabels.length) {
    showLocalError(`部分数据加载失败：${failedLabels.join("、")}。请检查服务状态后刷新页面。`);
  }
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
  els.terminateDebateBtn = document.getElementById("terminateDebateBtn");
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
  els.messageDetailModal = document.getElementById("messageDetailModal");
  els.closeMessageDetailBtn = document.getElementById("closeMessageDetailBtn");
  els.messageDetailEyebrow = document.getElementById("messageDetailEyebrow");
  els.messageDetailTitle = document.getElementById("messageDetailTitle");
  els.messageDetailBody = document.getElementById("messageDetailBody");
  els.detailTextTaskBar = document.getElementById("detailTextTaskBar");
  els.detailTextTaskLabel = document.getElementById("detailTextTaskLabel");
  els.cancelDetailTextTaskBtn = document.getElementById("cancelDetailTextTaskBtn");
  els.titleEditModal = document.getElementById("titleEditModal");
  els.titleEditInput = document.getElementById("titleEditInput");
  els.cancelTitleEditBtn = document.getElementById("cancelTitleEditBtn");
  els.confirmTitleEditBtn = document.getElementById("confirmTitleEditBtn");
  els.settingsForm = document.getElementById("settingsForm");
  els.presetManagerPanel = document.getElementById("presetManagerPanel");
  els.debateView = document.getElementById("debateView");
  els.landingPanel = document.getElementById("landingPanel");
  els.livePanel = document.getElementById("livePanel");
  els.reviewPanel = document.getElementById("reviewPanel");
  els.workspaceViewer = document.getElementById("workspaceViewer");
  els.archivedList = document.getElementById("archivedList");
  els.appErrorToast = document.getElementById("appErrorToast");
  els.appErrorToastMessage = document.getElementById("appErrorToastMessage");
  els.closeAppErrorToastBtn = document.getElementById("closeAppErrorToastBtn");
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
  document.getElementById("archivedSessionsBtn").addEventListener("click", openArchivedModal);
  document.getElementById("refreshSessionsBtn").addEventListener("click", async () => {
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  });
  document.getElementById("closeArchivedBtn").addEventListener("click", closeArchivedModal);
  els.closeAppErrorToastBtn?.addEventListener("click", clearInlineError);
  els.toggleReviewTopicBtn.addEventListener("click", toggleReviewTopicExpanded);
  els.previewErrorBtn.addEventListener("click", () => openMarkdownPreview("error"));
  els.closeMarkdownPreviewBtn.addEventListener("click", closeMarkdownPreviewModal);
  els.downloadMarkdownPreviewBtn.addEventListener("click", downloadMarkdownPreview);
  els.markdownPreviewModal.addEventListener("click", (event) => {
    if (event.target === els.markdownPreviewModal) {
      closeMarkdownPreviewModal();
    }
  });
  els.closeMessageDetailBtn.addEventListener("click", closeMessageDetailModal);
  els.messageDetailModal.addEventListener("click", (event) => {
    if (event.target === els.messageDetailModal) {
      closeMessageDetailModal();
    }
  });
  els.messageDetailBody.addEventListener("click", handleMessageDetailBodyClick);
  els.cancelDetailTextTaskBtn?.addEventListener("click", cancelMessageDetailTextTask);
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
  els.terminateDebateBtn?.addEventListener("click", terminateCurrentDebate);
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
    const detailAction = event.target.closest("[data-action='open-message-details']");
    if (detailAction) {
      openMessageDetails(detailAction.dataset.messageId);
      return;
    }
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
    const detailAction = event.target.closest("[data-action='open-message-details']");
    if (detailAction) {
      openMessageDetails(detailAction.dataset.messageId);
      return;
    }
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

  els.settingsForm.addEventListener("input", handleSettingsFormInput);
  els.settingsForm.addEventListener("change", handleSettingsFormChange);
  els.settingsForm.addEventListener("click", handleSettingsFormClick);
  els.presetManagerPanel.addEventListener("input", handlePresetManagerInput);
  els.presetManagerPanel.addEventListener("change", handlePresetManagerChange);
  els.presetManagerPanel.addEventListener("click", handlePresetManagerClick);
  els.presetManagerPanel.addEventListener("dragstart", handleResponseFlowDragStart);
  els.presetManagerPanel.addEventListener("dragover", handleResponseFlowDragOver);
  els.presetManagerPanel.addEventListener("drop", handleResponseFlowDrop);
  els.presetManagerPanel.addEventListener("dragend", handleResponseFlowDragEnd);
}

async function fetchWithTimeout(path, options = {}) {
  const {
    timeoutMs = DEFAULT_API_TIMEOUT_MS,
    signal: externalSignal,
    ...fetchOptions
  } = options;
  const controller = new AbortController();
  let timedOut = false;
  let timeoutId = null;
  const abortFromExternalSignal = () => controller.abort();

  if (externalSignal?.aborted) {
    controller.abort();
  } else if (externalSignal) {
    externalSignal.addEventListener("abort", abortFromExternalSignal, { once: true });
  }
  if (Number(timeoutMs) > 0) {
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, Number(timeoutMs));
  }

  try {
    const response = await fetch(path, { ...fetchOptions, signal: controller.signal });
    const method = String(fetchOptions.method || "GET").toUpperCase();
    const hasNoBody = method === "HEAD" || [204, 205, 304].includes(response.status);
    const body = hasNoBody ? null : await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  } catch (error) {
    if (timedOut) {
      const timeoutError = new Error(`请求超时（${Math.ceil(Number(timeoutMs) / 1000)} 秒），请检查网络或服务状态。`);
      timeoutError.name = "TimeoutError";
      throw timeoutError;
    }
    throw error;
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
    externalSignal?.removeEventListener("abort", abortFromExternalSignal);
  }
}

async function api(path, options = {}) {
  const finalOptions = { ...options };
  if (finalOptions.body && !finalOptions.headers) {
    finalOptions.headers = { "Content-Type": "application/json" };
  }
  const response = await fetchWithTimeout(path, finalOptions);
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
    const response = await fetchWithTimeout(`/assets/Notice.txt?ts=${Date.now()}`, { timeoutMs: 15000 });
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
    const response = await fetchWithTimeout(`/assets/workspace.md?ts=${Date.now()}`, { timeoutMs: 15000 });
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
    state.settingsSnapshot = null;
    ensureSelectedPresetEditor(selectedPresetId);
    closeSettings({ discard: false });
  } catch (error) {
    const message = error?.message || "保存设置失败。";
    window.alert(message);
  }
}

async function persistSettings(payload = buildSettingsPayload(), options = {}) {
  const savedSettings = await api("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (options.applyResult !== false) {
    state.settings = savedSettings;
  }
  ensurePresetManagerSelections();
  renderHomeDebaterBinding();
  return savedSettings;
}

function buildSettingsPayload() {
  const judge = state.settings?.judge || {};
  const translator = state.settings?.translator || {};
  const summarizer = state.settings?.summarizer || {};
  return {
    judge: serializeJudgeSettings(judge, "裁判模型"),
    translator: serializeJudgeSettings(translator, "翻译模型"),
    summarizer: serializeJudgeSettings(summarizer, "总结模型"),
    model_suppliers: getModelSuppliers().slice(0, getSupplierLimit()).map((supplier) => serializeSupplierSettings(supplier)),
    tool_configs: getToolConfigs().slice(0, getToolLimit()).map((toolConfig) => serializeToolConfig(toolConfig)),
    pro_preset_id: state.settings?.pro_preset_id || "",
    con_preset_id: state.settings?.con_preset_id || "",
    context_rounds: parseContextRoundsValue(state.settings?.context_rounds),
    usage_tracking_enabled: Boolean(state.settings?.usage_tracking_enabled),
    debater_presets: getDebaterPresets().slice(0, getPresetLimit()).map((preset) => serializeDebaterPresetSettings(preset)),
  };
}

function serializeJudgeSettings(judge, label = "模型配置") {
  return {
    supplier_id: String(judge?.supplier_id || "").trim(),
    model: String(judge?.model || "").trim(),
    azure_deployment: String(judge?.azure_deployment || "").trim(),
    max_tokens: Number(judge?.max_tokens || 0),
    extra_body: parseExtraBodyPayload(judge?.extra_body_input ?? judge?.extra_body, label),
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
    response_flow: serializeResponseFlow(preset),
  };
}

function serializeResponseFlow(preset) {
  const flow = getPresetResponseFlow(preset);
  if (flow.mode !== "manual") {
    return flow;
  }
  const selectedToolIds = new Set(getPresetToolSelection(preset).enabled_tool_ids || []);
  flow.blocks.forEach((block) => {
    if (block.type === "deep_thinking") {
      const tokenLimit = Number(block.max_tokens);
      if (!Number.isInteger(tokenLimit) || tokenLimit < RESPONSE_FLOW_MIN_THINKING_TOKENS || tokenLimit > RESPONSE_FLOW_MAX_THINKING_TOKENS) {
        throw new Error(`深度思考 Token 数必须是 ${RESPONSE_FLOW_MIN_THINKING_TOKENS} 到 ${RESPONSE_FLOW_MAX_THINKING_TOKENS} 之间的整数。`);
      }
    }
    if (block.type === "tool_call") {
      const tool = findToolById(block.tool_id || "");
      if (!tool || !tool.enabled || !selectedToolIds.has(tool.id)) {
        throw new Error("人工编排中的工具调用块必须选择一个已启用、且已绑定到当前辩手的工具。");
      }
    }
  });
  return flow;
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
    output_truncate_chars: Number(toolConfig?.output_truncate_chars || 0),
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
    fallback_enabled: Boolean(selection?.fallback_enabled),
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
    state.settings?.translator?.supplier_id,
    state.settings?.summarizer?.supplier_id,
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

function normalizeUtilityModelKey(key) {
  return UTILITY_MODEL_TABS.some((item) => item.id === key) ? key : "judge";
}

function getUtilityModelMeta(key = state.activeUtilityModelKey) {
  const normalizedKey = normalizeUtilityModelKey(key);
  return UTILITY_MODEL_TABS.find((item) => item.id === normalizedKey) || UTILITY_MODEL_TABS[0];
}

function getUtilityModelSettings(key = state.activeUtilityModelKey) {
  const normalizedKey = normalizeUtilityModelKey(key);
  if (!state.settings[normalizedKey] || typeof state.settings[normalizedKey] !== "object") {
    state.settings[normalizedKey] = {};
  }
  return state.settings[normalizedKey];
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
    output_truncate_chars: Number(defaults.output_truncate_chars || 2500) || 2500,
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
    fallback_enabled: Boolean(selection.fallback_enabled),
  };
}

function createResponseFlowBlock(type, options = {}) {
  const blockId = `flow_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  if (type === "tool_call") {
    return { id: blockId, type, tool_id: String(options.tool_id || "") };
  }
  return {
    id: blockId,
    type: "deep_thinking",
    max_tokens: Number(options.max_tokens || 2048) || 2048,
  };
}

function getPresetResponseFlow(preset) {
  const raw = preset?.response_flow && typeof preset.response_flow === "object" ? preset.response_flow : {};
  const rawBlocks = Array.isArray(raw.blocks) ? raw.blocks : [];
  const blocks = [{ id: "flow_start", type: "start" }];
  rawBlocks.forEach((block) => {
    if (!block || !["deep_thinking", "tool_call"].includes(block.type) || blocks.length >= RESPONSE_FLOW_MAX_BLOCKS - 1) {
      return;
    }
    if (block.type === "tool_call") {
      blocks.push({
        id: String(block.id || createResponseFlowBlock("tool_call").id),
        type: "tool_call",
        tool_id: String(block.tool_id || ""),
      });
      return;
    }
    blocks.push({
      id: String(block.id || createResponseFlowBlock("deep_thinking").id),
      type: "deep_thinking",
      max_tokens: Number(block.max_tokens || 2048) || 2048,
    });
  });
  blocks.push({ id: "flow_final", type: "final_response" });
  return {
    mode: raw.mode === "manual" ? "manual" : "autonomous",
    blocks,
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
      fallback_enabled: seedToolSelection.fallback_enabled,
    },
    response_flow: cloneObjectValue(getPresetResponseFlow(seed)),
  };
}

function openSettings() {
  state.settingsSnapshot = state.settings ? cloneObjectValue(state.settings) : null;
  state.settingsDarkModeSnapshot = state.darkMode;
  state.presetManagerOpen = false;
  state.responseFlowEditorOpen = false;
  state.activeUtilityModelKey = "judge";
  state.utilityModelSwitcherOpen = false;
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

function closeSettings(options = {}) {
  if (els.settingsModal.classList.contains("hidden")) {
    return;
  }
  const shouldDiscard = options?.discard !== false;
  if (shouldDiscard && state.settingsSnapshot) {
    state.settings = cloneObjectValue(state.settingsSnapshot);
    setDarkMode(state.settingsDarkModeSnapshot);
    ensurePresetManagerSelections();
    renderHomeDebaterBinding();
  }
  state.settingsSnapshot = null;
  state.presetManagerOpen = false;
  state.responseFlowEditorOpen = false;
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
  state.responseFlowEditorOpen = false;
  ensurePresetManagerSelections();
  renderPresetManagerPanel();
}

function closePresetManager() {
  state.presetManagerOpen = false;
  state.responseFlowEditorOpen = false;
  renderSettingsForm({ presetManagerOptions: { preserveListScroll: false, preserveEditorScroll: false } });
}

function renderSettingsForm(options = {}) {
  if (!state.settings) {
    return;
  }
  ensurePresetManagerSelections();
  state.activeUtilityModelKey = normalizeUtilityModelKey(state.activeUtilityModelKey);
  els.settingsForm.innerHTML = [
    createJudgeSettingsCard(getUtilityModelSettings(state.activeUtilityModelKey), state.activeUtilityModelKey),
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

function createUtilityModelSwitchMenu(activeKey) {
  const options = UTILITY_MODEL_TABS.filter((item) => item.id !== activeKey);
  return `
    <div class="utility-model-menu ${state.utilityModelSwitcherOpen ? "" : "hidden"}">
      ${options
        .map(
          (item) => `
            <button class="utility-model-option" type="button" data-action="switch-utility-model" data-utility-model-key="${escapeAttribute(item.id)}">
              <span>${escapeHtml(item.label)}</span>
              <small>切换配置</small>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function getUtilityModelSwitchIconSvg() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 7h10" />
      <path d="M14 4l3 3-3 3" />
      <path d="M17 17H7" />
      <path d="M10 14l-3 3 3 3" />
    </svg>
  `;
}

function createJudgeSettingsCard(config, modelKey = "judge") {
  const activeKey = normalizeUtilityModelKey(modelKey);
  const meta = getUtilityModelMeta(activeKey);
  const supplier = getJudgeSupplier(config);
  const provider = supplier?.provider === "azure" ? "azure" : "chatopenai";
  return `
    <section class="settings-card judge-settings-card utility-model-card">
      <div class="utility-model-switcher">
        <button
          class="utility-model-switch-button"
          type="button"
          data-action="toggle-utility-model-switcher"
          aria-label="切换模型配置"
          aria-expanded="${state.utilityModelSwitcherOpen ? "true" : "false"}"
        >
          ${getUtilityModelSwitchIconSvg()}
        </button>
        ${createUtilityModelSwitchMenu(activeKey)}
      </div>
      <div class="settings-card-head settings-card-head-compact">
        <div>
          <h4>${escapeHtml(meta.label)}</h4>
          <p class="card-note">${escapeHtml(meta.note)}</p>
        </div>
      </div>
      <div class="utility-model-actions">
        <button class="ghost-button compact-button" type="button" data-action="open-preset-manager" data-preset-manager-tab="supplier">管理供应商</button>
      </div>
      <label>
        <span>${escapeHtml(meta.supplierLabel)}</span>
        <select data-utility-model-key="${escapeAttribute(activeKey)}" data-utility-model-field="supplier_id">
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
        <input data-utility-model-key="${escapeAttribute(activeKey)}" data-utility-model-field="model" value="${escapeAttribute(config.model || "")}" placeholder="例如 gpt-5.2 / kimi-k2.5" />
      </label>
      <div class="provider-fields ${provider === "chatopenai" ? "" : "hidden"}">
        <label>
          <span>额外参数 extra_body</span>
          <textarea class="json-textarea" data-utility-model-key="${escapeAttribute(activeKey)}" data-utility-model-field="extra_body" rows="4" spellcheck="false" placeholder='例如 {"enable_thinking": true}'>${escapeHtml(formatExtraBodyInput(config.extra_body_input ?? config.extra_body))}</textarea>
        </label>
        <p class="card-note">仅在 ChatOpenAI 供应商下生效。支持标准 JSON，也兼容 {"enable_thinking": True} 这种写法。</p>
      </div>
      <div class="provider-fields ${provider === "azure" ? "" : "hidden"}">
        <label>
          <span>Azure Deployment</span>
          <input data-utility-model-key="${escapeAttribute(activeKey)}" data-utility-model-field="azure_deployment" value="${escapeAttribute(config.azure_deployment || "")}" placeholder="例如 my-deployment" />
        </label>
      </div>
      <label>
        <span>Max Tokens</span>
        <input data-utility-model-key="${escapeAttribute(activeKey)}" data-utility-model-field="max_tokens" type="number" min="1" value="${escapeAttribute(config.max_tokens || 4096)}" />
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
    ? `${selectedTools.map((toolConfig) => toolConfig.name || "未命名工具").join(" / ")} · ${selection.mode || "bind_tools"} · ${selection.fallback_enabled ? "兜底开" : "兜底关"}`
    : "无工具";
  const flow = getPresetResponseFlow(preset);
  const flowLabel = flow.mode === "manual" ? `人工编排 · ${Math.max(0, flow.blocks.length - 2)} 个内部块` : "模型自主链路";
  return `${supplierLabel} · ${providerLabel} · ${modelLabel} · ${toolLabel} · ${flowLabel}`;
}

function createPresetManagerOverlay() {
  const activeTab = normalizeConfigManagerTab(state.presetManagerTab);
  const preset = getSelectedPreset();
  if (state.responseFlowEditorOpen && preset) {
    return createResponseFlowEditorOverlay(preset);
  }

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

function createResponseFlowEditorOverlay(preset) {
  const flow = getPresetResponseFlow(preset);
  const intermediateBlocks = flow.blocks.filter((block) => !["start", "final_response"].includes(block.type));
  const canAdd = flow.blocks.length < RESPONSE_FLOW_MAX_BLOCKS;
  return `
    <div class="preset-overlay-surface response-flow-overlay panel">
      <div class="preset-overlay-head config-overlay-head">
        <div class="preset-overlay-heading-row">
          <div>
            <p class="eyebrow">Manual Response Flow</p>
            <h3>内部回复流程 · ${escapeHtml(preset.name || "未命名辩手")}</h3>
            <p class="card-note">中间块只在本次发言内部共享上下文；对手与后续轮次只能看到“正式发言”块的输出。</p>
          </div>
          <div class="config-head-actions">
            <span class="status-badge">${flow.blocks.length} / ${RESPONSE_FLOW_MAX_BLOCKS} 块</span>
            <button class="config-tab config-tab-return" type="button" data-action="close-response-flow-editor">
              <span>返回辩手配置</span>
            </button>
          </div>
        </div>
      </div>
      <div class="response-flow-editor-body">
        <aside class="response-flow-palette">
          <div>
            <p class="eyebrow">Blocks</p>
            <h4>添加内部步骤</h4>
            <p class="card-note">拖动中间块可排序，也可以使用块右侧的上下按钮。</p>
          </div>
          <button class="flow-palette-button thinking" type="button" data-action="add-response-flow-block" data-flow-block-type="deep_thinking" ${canAdd ? "" : "disabled"}>
            <span class="flow-palette-icon" aria-hidden="true">思</span>
            <span><strong>深度思考</strong><small>独立请求一次模型，可设置 Token 上限</small></span>
          </button>
          <button class="flow-palette-button tool" type="button" data-action="add-response-flow-block" data-flow-block-type="tool_call" ${canAdd ? "" : "disabled"}>
            <span class="flow-palette-icon" aria-hidden="true">搜</span>
            <span><strong>工具调用</strong><small>强制模型生成参数并执行已绑定工具</small></span>
          </button>
          <div class="response-flow-privacy-note">
            <strong>上下文隔离</strong>
            <p>内部思考、参数与工具返回会写入详细记录，但不会进入双方公开辩论历史。</p>
          </div>
        </aside>
        <div class="response-flow-scroll preset-editor-scroller">
          <div class="response-flow-canvas" data-response-flow-dropzone>
            ${createResponseFlowFixedBlock("start")}
            ${intermediateBlocks.map((block, index) => createResponseFlowBlockCard(preset, block, index, intermediateBlocks.length)).join("")}
            ${createResponseFlowFixedBlock("final_response")}
          </div>
        </div>
      </div>
    </div>
  `;
}

function createResponseFlowFixedBlock(type) {
  const isStart = type === "start";
  return `
    <div class="response-flow-node fixed ${isStart ? "start" : "final"}" data-flow-fixed-type="${escapeAttribute(type)}">
      <span class="flow-node-index">${isStart ? "01" : "END"}</span>
      <div>
        <strong>${isStart ? "开始" : "正式发言"}</strong>
        <p>${isStart ? "载入辩题、角色任务与可见的最近辩论上下文。" : "汇总内部步骤，只把最终发言写入辩论历史。"}</p>
      </div>
      <span class="flow-node-lock" aria-label="固定积木">固定</span>
    </div>
  `;
}

function createResponseFlowBlockCard(preset, block, index, total) {
  const isThinking = block.type === "deep_thinking";
  const selectedTools = getPresetSelectedTools(preset).filter((tool) => tool.enabled);
  const toolOptions = selectedTools.map((tool) => `
    <option value="${escapeAttribute(tool.id)}" ${tool.id === block.tool_id ? "selected" : ""}>${escapeHtml(tool.name || "未命名工具")}</option>
  `).join("");
  return `
    <div class="response-flow-node movable ${isThinking ? "thinking" : "tool"}" draggable="true" data-flow-block-id="${escapeAttribute(block.id)}">
      <span class="flow-drag-handle" title="拖动排序" aria-hidden="true">⋮⋮</span>
      <div class="flow-node-content">
        <div class="flow-node-title-row">
          <div>
            <span class="flow-node-type">${isThinking ? "Deep Thinking" : "Forced Tool"}</span>
            <strong>${isThinking ? "深度思考" : "工具调用"}</strong>
          </div>
          <div class="flow-node-actions">
            <button type="button" data-action="move-response-flow-block" data-flow-block-id="${escapeAttribute(block.id)}" data-flow-direction="up" aria-label="上移" ${index === 0 ? "disabled" : ""}>↑</button>
            <button type="button" data-action="move-response-flow-block" data-flow-block-id="${escapeAttribute(block.id)}" data-flow-direction="down" aria-label="下移" ${index === total - 1 ? "disabled" : ""}>↓</button>
            <button class="danger" type="button" data-action="remove-response-flow-block" data-flow-block-id="${escapeAttribute(block.id)}" aria-label="删除积木">×</button>
          </div>
        </div>
        ${isThinking ? `
          <label class="flow-node-field">
            <span>本次请求 Token 上限</span>
            <input type="number" min="${RESPONSE_FLOW_MIN_THINKING_TOKENS}" max="${RESPONSE_FLOW_MAX_THINKING_TOKENS}" step="128" value="${escapeAttribute(block.max_tokens || 2048)}" data-flow-block-id="${escapeAttribute(block.id)}" data-flow-block-field="max_tokens" />
          </label>
        ` : `
          <label class="flow-node-field">
            <span>强制调用工具</span>
            <select data-flow-block-id="${escapeAttribute(block.id)}" data-flow-block-field="tool_id">
              <option value="">${selectedTools.length ? "请选择工具" : "请先在辩手配置中绑定并启用工具"}</option>
              ${toolOptions}
            </select>
          </label>
        `}
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
        <label>
          <span>输出截断字符数</span>
          <input data-tool-config-id="${escapeAttribute(toolConfig.id || "")}" data-tool-config-field="output_truncate_chars" type="number" min="500" max="20000" step="100" value="${escapeAttribute(toolConfig.output_truncate_chars || 2500)}" />
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
        ${createResponseFlowSettings(preset)}
        ${createPresetToolSelector(selection)}
      </div>
      <div class="preset-editor-actions">
        <button class="danger-button compact-button" type="button" data-action="delete-preset" ${deleteDisabled ? "disabled" : ""}>删除当前配置</button>
      </div>
    </div>
  `;
}

function createResponseFlowSettings(preset) {
  const flow = getPresetResponseFlow(preset);
  const intermediateCount = Math.max(0, flow.blocks.length - 2);
  return `
    <div class="search-section response-flow-settings">
      <div class="toggle-row response-flow-mode-row">
        <div>
          <strong>内部回复链路</strong>
          <p class="card-note">自主链路沿用当前 bind_tools / react 流程；人工编排按固定积木顺序执行。</p>
        </div>
        <span class="status-badge">${flow.mode === "manual" ? `${intermediateCount} 个内部块` : "自主"}</span>
      </div>
      <div class="response-flow-mode-grid">
        <label class="response-flow-mode-option ${flow.mode === "autonomous" ? "active" : ""}">
          <input type="radio" name="response-flow-mode-${escapeAttribute(preset.id)}" value="autonomous" data-preset-flow-field="mode" ${flow.mode === "autonomous" ? "checked" : ""} />
          <span><strong>模型自主工具链路</strong><small>模型自行判断是否调用工具，并使用当前工具模式。</small></span>
        </label>
        <label class="response-flow-mode-option ${flow.mode === "manual" ? "active" : ""}">
          <input type="radio" name="response-flow-mode-${escapeAttribute(preset.id)}" value="manual" data-preset-flow-field="mode" ${flow.mode === "manual" ? "checked" : ""} />
          <span><strong>人工编排链路</strong><small>按纵向积木依次思考、调用工具并生成正式发言。</small></span>
        </label>
      </div>
      <button class="primary-button response-flow-editor-button" type="button" data-action="open-response-flow-editor" ${flow.mode === "manual" ? "" : "disabled"}>
        <span>打开积木流程编辑器</span>
        <small>${flow.blocks.length} / ${RESPONSE_FLOW_MAX_BLOCKS} 块</small>
      </button>
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
      <div class="tool-strategy-row">
        <div class="form-grid compact-form-grid">
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
      <div class="tool-choice-list">
        ${tools.map((toolConfig) => createToolChoice(toolConfig, selectedIds.has(toolConfig.id), selection)).join("") || '<div class="empty-state compact-empty-state">暂无通用工具，请先在上方配置 Tavily Search。</div>'}
      </div>
    </div>
  `;
}

function createToolChoice(toolConfig, selected, selection) {
  const disabledClass = toolConfig.enabled ? "" : "tool-choice-disabled";
  const template = getToolTemplate(toolConfig.template_id || toolConfig.type || "tavily_search");
  const typeLabel = template?.name || toolConfig.type || "未知工具";
  const keyLabel = toolConfig.has_api_key || toolConfig.api_key ? "已配置 Key" : "未配置 Key";
  const toolId = String(toolConfig.id || "");
  const expanded = Boolean(state.expandedToolChoiceIds[toolId]);
  return `
    <div class="tool-choice-card ${disabledClass} ${expanded ? "expanded" : ""}">
      <div class="tool-choice-main">
        <label class="tool-choice-check" aria-label="选择工具">
          <input class="checkbox" type="checkbox" data-preset-tool-id="${escapeAttribute(toolId)}" ${selected ? "checked" : ""} />
        </label>
        <button class="tool-choice-summary" type="button" data-action="toggle-tool-choice-details" data-tool-id="${escapeAttribute(toolId)}" aria-expanded="${expanded ? "true" : "false"}">
          <span>
            <strong>${escapeHtml(toolConfig.name || "Tavily Search")}</strong>
            <small>${escapeHtml(typeLabel)} · ${toolConfig.enabled ? "通用已启用" : "通用未启用"} · ${escapeHtml(keyLabel)}</small>
          </span>
          <span class="tool-choice-caret" aria-hidden="true">${expanded ? "收起" : "展开"}</span>
        </button>
      </div>
      ${expanded ? createToolChoiceDetails(toolConfig, typeLabel, keyLabel, selection) : ""}
    </div>
  `;
}

function createToolChoiceDetails(toolConfig, typeLabel, keyLabel, selection) {
  const statusLabel = toolConfig.enabled ? "通用已启用" : "通用未启用";
  const truncateChars = Number(toolConfig.output_truncate_chars || 2500) || 2500;
  return `
    <div class="tool-choice-details">
      <div><span>工具模板</span><strong>${escapeHtml(typeLabel)}</strong></div>
      <div><span>启用状态</span><strong>${escapeHtml(statusLabel)}</strong></div>
      <div><span>API Key</span><strong>${escapeHtml(keyLabel)}</strong></div>
      <div><span>超时</span><strong>${escapeHtml(String(toolConfig.timeout || 60))} 秒</strong></div>
      <div><span>返回条数</span><strong>${escapeHtml(String(toolConfig.max_results || 5))}</strong></div>
      <div><span>搜索深度</span><strong>${escapeHtml(toolConfig.search_depth || "advanced")}</strong></div>
      <div><span>输出截断</span><strong>${escapeHtml(String(truncateChars))} 字符</strong></div>
      <div class="toggle-row tool-choice-fallback-row">
        <div>
          <strong>后端兜底搜索</strong>
          <p class="card-note">开启后，模型未调用搜索工具或搜索工具协议失败时，后端会自动搜索一轮；关闭后完全由模型自行决定是否调用搜索工具。</p>
        </div>
        <label class="mini-switch" aria-label="后端兜底搜索开关">
          <input type="checkbox" data-preset-tool-field="fallback_enabled" ${selection.fallback_enabled ? "checked" : ""} />
          <span></span>
        </label>
      </div>
    </div>
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
    return;
  }
  if (actionTarget.dataset.action === "toggle-utility-model-switcher") {
    state.utilityModelSwitcherOpen = !state.utilityModelSwitcherOpen;
    actionTarget.setAttribute("aria-expanded", state.utilityModelSwitcherOpen ? "true" : "false");
    actionTarget.closest(".utility-model-switcher")?.querySelector(".utility-model-menu")?.classList.toggle("hidden", !state.utilityModelSwitcherOpen);
    return;
  }
  if (actionTarget.dataset.action === "switch-utility-model") {
    state.activeUtilityModelKey = normalizeUtilityModelKey(actionTarget.dataset.utilityModelKey || "");
    state.utilityModelSwitcherOpen = false;
    renderSettingsForm();
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
  const field = target.dataset.bindingField;
  const previousValue = state.settings[field] || "";
  const nextValue = String(target.value || "");
  state.settings[field] = nextValue;
  ensureSelectedPresetEditor();
  state.savingHomeBinding = true;
  updateStartDebateAvailability();
  renderHomeDebaterBinding();
  const payload = buildSettingsPayload();
  const previousSave = state.homeBindingSavePromise;
  const savePromise = (previousSave || Promise.resolve())
    .catch(() => null)
    .then(() => persistSettings(payload, { applyResult: false }));
  state.homeBindingSavePromise = savePromise;
  try {
    const savedSettings = await savePromise;
    if (state.homeBindingSavePromise === savePromise) {
      state.settings = savedSettings;
      ensurePresetManagerSelections();
    }
  } catch (error) {
    if (state.homeBindingSavePromise === savePromise) {
      try {
        state.settings = await api("/api/settings");
        ensurePresetManagerSelections();
      } catch {
        state.settings[field] = previousValue;
      }
      window.alert(error?.message || "保存辩手选择失败。");
    }
  } finally {
    if (state.homeBindingSavePromise === savePromise) {
      state.homeBindingSavePromise = null;
      state.savingHomeBinding = false;
    }
    updateStartDebateAvailability();
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
    || event.target.dataset.presetFlowField
    || event.target.dataset.flowBlockField
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
    state.responseFlowEditorOpen = false;
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
    state.responseFlowEditorOpen = false;
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
  if (action === "toggle-tool-choice-details") {
    const toolId = actionTarget.dataset.toolId || "";
    if (toolId) {
      state.expandedToolChoiceIds = {
        ...state.expandedToolChoiceIds,
        [toolId]: !state.expandedToolChoiceIds[toolId],
      };
      renderPresetManagerPanel({ preserveListScroll: true, preserveEditorScroll: true });
    }
    return;
  }
  if (action === "open-response-flow-editor") {
    const preset = getSelectedPreset();
    if (!preset) {
      return;
    }
    preset.response_flow = getPresetResponseFlow(preset);
    preset.response_flow.mode = "manual";
    state.responseFlowEditorOpen = true;
    renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: false });
    return;
  }
  if (action === "close-response-flow-editor") {
    state.responseFlowEditorOpen = false;
    renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: false });
    return;
  }
  if (action === "add-response-flow-block") {
    addResponseFlowBlock(actionTarget.dataset.flowBlockType || "deep_thinking");
    return;
  }
  if (action === "remove-response-flow-block") {
    removeResponseFlowBlock(actionTarget.dataset.flowBlockId || "");
    return;
  }
  if (action === "move-response-flow-block") {
    moveResponseFlowBlock(actionTarget.dataset.flowBlockId || "", actionTarget.dataset.flowDirection || "up");
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

  const utilityModelField = target.dataset.utilityModelField || target.dataset.judgeField;
  if (utilityModelField) {
    const modelKey = normalizeUtilityModelKey(target.dataset.utilityModelKey || "judge");
    const modelConfig = getUtilityModelSettings(modelKey);
    if (utilityModelField === "extra_body") {
      modelConfig.extra_body_input = String(target.value || "");
      return false;
    }
    modelConfig[utilityModelField] = readFieldValue(target);
    return utilityModelField === "supplier_id";
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

  const presetFlowField = target.dataset.presetFlowField;
  if (presetFlowField) {
    preset.response_flow = getPresetResponseFlow(preset);
    preset.response_flow[presetFlowField] = readFieldValue(target);
    return presetFlowField === "mode";
  }

  const flowBlockField = target.dataset.flowBlockField;
  if (flowBlockField) {
    preset.response_flow = getPresetResponseFlow(preset);
    const block = preset.response_flow.blocks.find((item) => item.id === target.dataset.flowBlockId);
    if (block) {
      block[flowBlockField] = readFieldValue(target);
    }
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

function addResponseFlowBlock(type) {
  const preset = getSelectedPreset();
  if (!preset) {
    return;
  }
  const flow = getPresetResponseFlow(preset);
  if (flow.blocks.length >= RESPONSE_FLOW_MAX_BLOCKS) {
    window.alert(`内部回复流程最多只能包含 ${RESPONSE_FLOW_MAX_BLOCKS} 个积木。`);
    return;
  }
  const selectedTool = getPresetSelectedTools(preset).find((tool) => tool.enabled);
  const block = createResponseFlowBlock(type === "tool_call" ? "tool_call" : "deep_thinking", {
    tool_id: selectedTool?.id || "",
  });
  flow.blocks.splice(flow.blocks.length - 1, 0, block);
  flow.mode = "manual";
  preset.response_flow = flow;
  renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: true });
}

function removeResponseFlowBlock(blockId) {
  const preset = getSelectedPreset();
  if (!preset || !blockId) {
    return;
  }
  const flow = getPresetResponseFlow(preset);
  flow.blocks = flow.blocks.filter((block) => block.id !== blockId || ["start", "final_response"].includes(block.type));
  preset.response_flow = flow;
  renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: true });
}

function moveResponseFlowBlock(blockId, direction, targetId = "", placeAfter = false) {
  const preset = getSelectedPreset();
  if (!preset || !blockId) {
    return;
  }
  const flow = getPresetResponseFlow(preset);
  const intermediates = flow.blocks.filter((block) => !["start", "final_response"].includes(block.type));
  const sourceIndex = intermediates.findIndex((block) => block.id === blockId);
  if (sourceIndex < 0) {
    return;
  }
  const [source] = intermediates.splice(sourceIndex, 1);
  let nextIndex;
  if (targetId) {
    const targetIndex = intermediates.findIndex((block) => block.id === targetId);
    nextIndex = targetIndex < 0 ? intermediates.length : targetIndex + (placeAfter ? 1 : 0);
  } else {
    nextIndex = direction === "down" ? sourceIndex + 1 : sourceIndex - 1;
  }
  intermediates.splice(Math.max(0, Math.min(nextIndex, intermediates.length)), 0, source);
  flow.blocks = [{ id: "flow_start", type: "start" }, ...intermediates, { id: "flow_final", type: "final_response" }];
  preset.response_flow = flow;
  renderPresetManagerPanel({ preserveListScroll: false, preserveEditorScroll: true });
}

function handleResponseFlowDragStart(event) {
  const block = event.target.closest?.("[data-flow-block-id][draggable='true']");
  if (!block) {
    return;
  }
  state.responseFlowDraggingBlockId = block.dataset.flowBlockId || "";
  block.classList.add("dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", state.responseFlowDraggingBlockId);
}

function handleResponseFlowDragOver(event) {
  const target = event.target.closest?.("[data-flow-block-id][draggable='true']");
  if (!target || !state.responseFlowDraggingBlockId || target.dataset.flowBlockId === state.responseFlowDraggingBlockId) {
    return;
  }
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
}

function handleResponseFlowDrop(event) {
  const target = event.target.closest?.("[data-flow-block-id][draggable='true']");
  const sourceId = state.responseFlowDraggingBlockId || event.dataTransfer.getData("text/plain");
  if (!target || !sourceId || target.dataset.flowBlockId === sourceId) {
    return;
  }
  event.preventDefault();
  const rect = target.getBoundingClientRect();
  moveResponseFlowBlock(sourceId, "", target.dataset.flowBlockId || "", event.clientY > rect.top + rect.height / 2);
  state.responseFlowDraggingBlockId = "";
}

function handleResponseFlowDragEnd(event) {
  event.target.closest?.("[data-flow-block-id][draggable='true']")?.classList.remove("dragging");
  state.responseFlowDraggingBlockId = "";
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
  UTILITY_MODEL_TABS.forEach((item) => {
    const modelConfig = getUtilityModelSettings(item.id);
    if (!modelConfig.supplier_id) {
      modelConfig.supplier_id = nextSupplier.id;
    }
  });
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
  UTILITY_MODEL_TABS.forEach((item) => {
    const modelConfig = getUtilityModelSettings(item.id);
    if (modelConfig.supplier_id === supplier.id || !modelConfig.supplier_id) {
      modelConfig.supplier_id = replacementId;
    }
  });
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
    const flow = getPresetResponseFlow(preset);
    flow.blocks = flow.blocks.filter((block) => block.type !== "tool_call" || block.tool_id !== toolConfig.id);
    preset.response_flow = flow;
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
  const requestId = ++state.sessionListRequestId;
  const sessions = await api("/api/debates");
  if (requestId !== state.sessionListRequestId) {
    return false;
  }
  state.sessions = sessions;
  syncCurrentSessionSummary();
  renderSessions();
  scheduleSessionSummaryRefresh();
  return true;
}

function scheduleSessionListRefresh(delay = SESSION_LIST_REFRESH_DEBOUNCE_MS) {
  window.clearTimeout(state.sessionListRefreshTimer);
  state.sessionListRefreshTimer = window.setTimeout(() => {
    state.sessionListRefreshTimer = null;
    void loadSessions().catch(() => {
      // 实时消息已经更新当前界面，列表刷新失败留待下一轮重试。
    });
  }, Math.max(0, Number(delay) || 0));
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
    await loadSessions();
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

function getMessageDetailIconSvg() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0 -17Z" />
      <path d="M12 10.75v5" />
      <path d="M12 7.75h.01" />
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

  const pendingBindingSave = state.homeBindingSavePromise;
  if (pendingBindingSave) {
    try {
      await pendingBindingSave;
    } catch {
      return;
    }
  }

  try {
    clearInlineError();
    cancelSessionOpenRequest();
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

function isCurrentSession(sessionId) {
  const normalizedId = String(sessionId || "");
  return Boolean(
    normalizedId
    && state.currentSessionId === normalizedId
    && state.currentSession?.id === normalizedId
  );
}

function cancelSessionOpenRequest() {
  state.sessionOpenRequestId += 1;
  state.sessionOpenController?.abort();
  state.sessionOpenController = null;
}

async function fetchSession(sessionId, options = {}) {
  const session = await api(`/api/debates/${sessionId}`, { signal: options.signal });
  if (session?.status === "error") {
    await hydrateErrorDetails(session, options);
  }
  return session;
}

async function hydrateErrorDetails(session, options = {}) {
  if (!session || session.status !== "error") {
    return session;
  }
  if (session.error_message && session.error_traceback) {
    return session;
  }
  try {
    const record = await api(`/api/records/error/${session.id}`, { signal: options.signal });
    const parsed = parseErrorRecord(record.content || "");
    if (!session.error_message && parsed.errorMessage) {
      session.error_message = parsed.errorMessage;
    }
    if (!session.error_traceback && parsed.traceback) {
      session.error_traceback = parsed.traceback;
    }
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    // 旧会话可能没有单独的错误记录，直接保持现状即可。
  }
  return session;
}

async function openSession(sessionId, shouldConnect, switchToDebate = true) {
  state.sessionOpenController?.abort();
  const controller = new AbortController();
  const requestId = ++state.sessionOpenRequestId;
  state.sessionOpenController = controller;
  try {
    closeTitleEditModal({ immediate: true });
    const session = await fetchSession(sessionId, { signal: controller.signal });
    if (requestId !== state.sessionOpenRequestId) {
      return;
    }
    state.currentSession = session;
    state.currentSessionId = session.id;
    state.typing = isRunningSessionStatus(session?.status) ? session.live_status || null : null;
    clearInlineError();
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
    if (isAbortError(error) || requestId !== state.sessionOpenRequestId) {
      return;
    }
    showLocalError(error.message);
  } finally {
    if (requestId === state.sessionOpenRequestId) {
      state.sessionOpenController = null;
    }
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
    await Promise.all([loadSessions(), loadArchivedSessions()]);
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    } else {
      renderSessions();
    }
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
    await Promise.all([loadSessions(), loadArchivedSessions()]);
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    } else {
      renderSessions();
    }
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
    const tasks = [loadSessions()];
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
    if (state.eventSource !== source || state.eventSourceSessionId !== sessionId) {
      return;
    }
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      showLocalError("收到无法解析的实时事件，连接将继续保持。", true);
      return;
    }
    const payloadSessionId = payload.session_id || payload.session?.id || "";
    if (payloadSessionId && payloadSessionId !== sessionId) {
      return;
    }
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
    scheduleSessionListRefresh(payload.type === "error" ? 0 : SESSION_LIST_REFRESH_DEBOUNCE_MS);
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

function hasMessageDetails(message) {
  return Array.isArray(message?.details) && message.details.some((item) => item && typeof item === "object");
}

function findCurrentMessageById(messageId) {
  const id = String(messageId || "");
  if (!id) {
    return null;
  }
  return (state.currentSession?.messages || []).find((message) => String(message.id || "") === id) || null;
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
    upsertSessionSummary(nextSession);
    if (isCurrentSession(sessionId)) {
      disconnectStream();
      state.currentSession = nextSession;
      state.currentSessionId = nextSession.id;
      state.typing = null;
      state.reviewTopicExpanded = false;
      state.expandedEvaluationGroups = {};
      resetUserTargetState({ clearSelection: true });
      switchView("debate");
      renderCurrentSession();
    } else {
      renderSessions();
    }
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message);
    }
  } finally {
    if (state.rewindingMessageActionKey === actionKey) {
      state.rewindingMessageActionKey = "";
    }
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    }
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
    upsertSessionSummary(nextSession);
    if (isCurrentSession(sessionId)) {
      state.currentSession = nextSession;
      state.currentSessionId = nextSession.id;
      closeTitleEditModal();
      renderCurrentSession();
    } else {
      renderSessions();
    }
    await Promise.all([loadSessions(), loadArchivedSessions()]);
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message);
    }
  } finally {
    if (state.savingTitleSessionId === sessionId) {
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
}

function openNewDebate() {
  cancelSessionOpenRequest();
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
  if (state.togglingPauseSessionId === sessionId || state.stoppingSessionId === sessionId) {
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
    upsertSessionSummary(nextSession);
    if (isCurrentSession(sessionId)) {
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
    } else {
      renderSessions();
    }
    await loadSessions();
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message);
    }
  } finally {
    if (state.togglingPauseSessionId === sessionId) {
      state.togglingPauseSessionId = "";
    }
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    }
  }
}

async function terminateCurrentDebate() {
  const session = state.currentSession;
  const sessionId = session?.id || state.currentSessionId;
  if (!sessionId || !session || !isLiveSessionStatus(session.status)) {
    return;
  }
  if (state.stoppingSessionId === sessionId || state.togglingPauseSessionId === sessionId) {
    return;
  }
  if (!window.confirm("确认终止当前辩论吗？终止后不能继续，只能从回放中查看记录。")) {
    return;
  }

  state.stoppingSessionId = sessionId;
  renderCurrentSession();
  try {
    const nextSession = await api(`/api/debates/${sessionId}/stop`, { method: "POST" });
    upsertSessionSummary(nextSession);
    if (isCurrentSession(sessionId)) {
      disconnectStream();
      state.currentSession = nextSession;
      state.currentSessionId = nextSession.id;
      state.typing = null;
      switchView("debate");
      renderCurrentSession();
    } else {
      renderSessions();
    }
    await loadSessions();
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message, true);
    }
  } finally {
    if (state.stoppingSessionId === sessionId) {
      state.stoppingSessionId = "";
    }
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    }
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
    upsertSessionSummary(nextSession);
    if (isCurrentSession(sessionId)) {
      state.currentSession = nextSession;
      state.currentSessionId = nextSession.id;
      if (els.userInterjectionInput) {
        els.userInterjectionInput.value = "";
      }
      renderCurrentSession();
    } else {
      renderSessions();
    }
    await loadSessions();
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message, true);
    }
  } finally {
    if (state.sendingUserMessageSessionId === sessionId) {
      state.sendingUserMessageSessionId = "";
    }
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    }
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
      upsertSessionSummary(result.session);
    }
    if (isCurrentSession(sessionId)) {
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
    } else {
      renderSessions();
    }
    await loadSessions();
  } catch (error) {
    if (isCurrentSession(sessionId)) {
      showLocalError(error.message, true);
    }
  } finally {
    if (state.retractingUserMessageSessionId === sessionId) {
      state.retractingUserMessageSessionId = "";
    }
    if (isCurrentSession(sessionId)) {
      renderCurrentSession();
    }
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
  renderInlineErrorToast();
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
  const isStopping = state.stoppingSessionId === session.id;
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
  els.liveStatusBadge.textContent = isStopping ? "终止中" : (isToggling ? (isPaused ? "继续中" : "暂停中") : statusText);
  els.stopDebateBtn.disabled = isToggling || isStopping;
  els.stopDebateBtn.textContent = isToggling ? (isPaused ? "继续中..." : "暂停中...") : (isPaused ? "继续辩论" : "暂停辩论");
  els.stopDebateBtn.classList.toggle("resume-mode", isPaused && !isToggling);
  if (els.terminateDebateBtn) {
    els.terminateDebateBtn.disabled = isToggling || isStopping;
    els.terminateDebateBtn.textContent = isStopping ? "终止中..." : "终止辩论";
  }
  const operationText = isStopping
    ? "正在终止辩论..."
    : (isToggling ? (isPaused ? "正在继续辩论..." : "正在暂停辩论...") : statusText);
  setRunningState(isRunningSessionStatus(session.status), operationText);

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
  const canShowDetails = ["pro", "con"].includes(String(message.role || "")) && hasMessageDetails(message);
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
  const detailButtonHtml = canShowDetails
    ? `
        <button
          class="message-detail-button"
          type="button"
          data-action="open-message-details"
          data-message-id="${escapeAttribute(message.id || "")}"
          title="查看本步调用细节"
          aria-label="查看本步调用细节"
        >
          ${getMessageDetailIconSvg()}
        </button>
      `
    : "";
  const sideActionsHtml = rewindButtonHtml || detailButtonHtml
    ? `<div class="message-side-actions">${detailButtonHtml}${rewindButtonHtml}</div>`
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
        ${sideActionsHtml}
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

function switchView() {
  els.debateView.classList.add("view-active");
  state.reviewTopicExpanded = false;
  resetUserTargetState();
  state.expandedEvaluationGroups = {};
}

function setRunningState(isRunning, text) {
  els.runStatusBadge.textContent = text;
  state.startDebateLocked = Boolean(isRunning);
  updateStartDebateAvailability();
  renderHomeDebaterBinding();
}

function updateStartDebateAvailability() {
  if (els.startDebateBtn) {
    els.startDebateBtn.disabled = Boolean(state.startDebateLocked || state.savingHomeBinding);
  }
}

function setExportButtonsEnabled(enabled) {
  els.exportSimpleBtn.disabled = !enabled;
  els.exportDetailBtn.disabled = !enabled;
}

function getExportSessionId() {
  return state.currentSession?.id || state.currentSessionId || "";
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

async function fetchSessionExportMarkdown(sessionId, kind, options = {}) {
  const response = await fetchWithTimeout(`/api/debates/${encodeURIComponent(sessionId)}/export/${encodeURIComponent(kind)}`, {
    signal: options.signal,
    timeoutMs: EXPORT_API_TIMEOUT_MS,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const content = await response.text();
  const fileName = parseDownloadFilename(response.headers.get("Content-Disposition")) || `${sessionId}-${kind}.md`;
  return { content, fileName };
}

async function fetchErrorRecordMarkdown(session, options = {}) {
  const sessionId = session?.id || getExportSessionId();
  if (!sessionId) {
    throw new Error("请先选择一条可预览的辩论记录。");
  }
  try {
    const record = await api(`/api/records/error/${encodeURIComponent(sessionId)}`, {
      signal: options.signal,
      timeoutMs: EXPORT_API_TIMEOUT_MS,
    });
    const displayTitle = getRecordDisplayTitle({ ...record, kind: "error", sessionId });
    return {
      content: normalizeRecordContent({ ...record, kind: "error", sessionId, displayTitle }),
      fileName: `${sessionId}-error.md`,
    };
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
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

function showMarkdownPreviewShell(kind, sessionId) {
  const meta = getMarkdownPreviewMeta(kind);
  state.markdownPreview = {
    kind,
    sessionId,
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

  state.markdownPreviewController?.abort();
  const controller = new AbortController();
  const requestId = ++state.markdownPreviewRequestId;
  const session = state.currentSession;
  state.markdownPreviewController = controller;
  showMarkdownPreviewShell(kind, sessionId);
  try {
    const payload = kind === "error"
      ? await fetchErrorRecordMarkdown(session, { signal: controller.signal })
      : await fetchSessionExportMarkdown(sessionId, kind, { signal: controller.signal });
    if (requestId !== state.markdownPreviewRequestId) {
      return;
    }
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
    if (isAbortError(error) || requestId !== state.markdownPreviewRequestId) {
      return;
    }
    state.markdownPreview = null;
    els.markdownPreviewViewer.classList.add("empty-viewer");
    els.markdownPreviewViewer.textContent = error.message || "读取 Markdown 记录失败。";
    els.downloadMarkdownPreviewBtn.disabled = true;
    showLocalError(error.message, true);
  } finally {
    if (requestId === state.markdownPreviewRequestId) {
      state.markdownPreviewController = null;
    }
  }
}

function closeMarkdownPreviewModal({ immediate = false } = {}) {
  state.markdownPreviewRequestId += 1;
  state.markdownPreviewController?.abort();
  state.markdownPreviewController = null;
  state.markdownPreview = null;
  els.downloadMarkdownPreviewBtn.disabled = true;
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

function getMessageDetailKindLabel(kind) {
  const map = {
    reasoning: "思考",
    tool_call: "工具调用",
    tool_result: "工具返回",
    output: "正式输出",
  };
  return map[kind] || "步骤";
}

function getMessageDetailStepClass(step) {
  const kind = String(step?.kind || "step");
  const classes = ["message-detail-step-card", `detail-kind-${kind.replace(/[^a-z0-9_-]/gi, "-")}`];
  if (step?.fallback) {
    classes.push("detail-kind-fallback");
  }
  return classes.join(" ");
}

function getMessageDetailStepKindLabel(step) {
  const kind = String(step?.kind || "step");
  if (step?.fallback && kind === "tool_call") {
    return "兜底搜索";
  }
  if (step?.fallback && kind === "tool_result") {
    return "兜底返回";
  }
  return getMessageDetailKindLabel(kind);
}

function renderDetailValue(value) {
  if (value === null || value === undefined || value === "") {
    return '<span class="message-detail-empty">未填写</span>';
  }
  if (typeof value === "object") {
    return `<pre class="message-detail-code"><code>${escapeHtml(JSON.stringify(value, null, 2))}</code></pre>`;
  }
  return `<span class="message-detail-value">${escapeHtml(String(value))}</span>`;
}

function renderStructuredArgs(args) {
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    return renderDetailValue(args || {});
  }
  const entries = Object.entries(args);
  if (!entries.length) {
    return '<div class="message-detail-empty">没有参数。</div>';
  }
  return `
    <div class="message-detail-kv">
      ${entries
        .map(
          ([key, value]) => `
            <div class="message-detail-kv-row">
              <span class="message-detail-kv-key">${escapeHtml(key)}</span>
              <div class="message-detail-kv-value">${renderDetailValue(value)}</div>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function getPreviewLines(text, maxLines = 10) {
  const normalized = String(text || "").replace(/\r/g, "");
  const lines = normalized.split("\n");
  return {
    preview: lines.slice(0, maxLines).join("\n").trim(),
    omitted: Math.max(0, lines.length - maxLines),
  };
}

function renderRenderedText(text, emptyText = "暂无内容。") {
  const content = String(text || "").trim() || emptyText;
  return `<div class="message-detail-rendered">${renderMarkdown(content)}</div>`;
}

function getDetailTargetKey(target) {
  const kind = String(target?.contentKind || "");
  const detailIndex = Number(target?.detailIndex ?? -1);
  const entryIndex = target?.entryIndex === null || target?.entryIndex === undefined ? "" : Number(target.entryIndex);
  return `${kind}:${detailIndex}:${entryIndex}`;
}

function getActiveDetailTextView(target) {
  const key = getDetailTargetKey(target);
  return state.messageDetail?.activeViews?.[key] || "original";
}

function getDetailViewCache(views, view) {
  return views && typeof views === "object" && views[view] && typeof views[view] === "object" ? views[view] : null;
}

function renderDetailTextControls(target, activeView, views) {
  const key = getDetailTargetKey(target);
  const loadingView = state.messageDetailLoadingKey === `${key}:${activeView}` ? activeView : "";
  const hasTranslation = Boolean(getDetailViewCache(views, "translation"));
  const hasSummary = Boolean(getDetailViewCache(views, "summary"));
  const button = (view, label, title, cached) => `
    <button
      class="detail-text-view-button ${activeView === view ? "active" : ""} ${cached ? "cached" : ""}"
      type="button"
      data-action="message-detail-text-view"
      data-view="${escapeAttribute(view)}"
      data-content-kind="${escapeAttribute(target.contentKind)}"
      data-detail-index="${escapeAttribute(target.detailIndex)}"
      ${target.entryIndex === null || target.entryIndex === undefined ? "" : `data-entry-index="${escapeAttribute(target.entryIndex)}"`}
      title="${escapeAttribute(title)}"
      aria-label="${escapeAttribute(title)}"
      ${state.messageDetailLoadingKey ? "disabled" : ""}
    >
      ${loadingView === view ? '<span class="detail-text-spinner"></span>' : escapeHtml(label)}
    </button>
  `;
  return `
    <div class="detail-text-view-controls">
      ${button("translation", "译", hasTranslation ? "查看缓存翻译" : "翻译", hasTranslation)}
      ${button("summary", "摘", hasSummary ? "查看缓存总结" : "总结", hasSummary)}
      ${button("original", "原", "显示原内容", true)}
    </div>
  `;
}

function renderTranslationView(view, originalText, emptyText) {
  const sourceLanguage = String(view?.source_language || "未知").trim() || "未知";
  const translated = String(view?.translated_content || "").trim();
  const isChineseSource = ["简体中文", "中文", "汉语"].some((label) => sourceLanguage.includes(label));
  const body = translated || (isChineseSource ? originalText : "翻译模型没有返回翻译内容。");
  return `
    <div class="message-detail-rendered detail-text-rendered-with-meta">
      <div class="detail-text-language-tag">源语言：${escapeHtml(sourceLanguage)}</div>
      ${renderMarkdown(String(body || "").trim() || emptyText || "暂无翻译内容。")}
    </div>
  `;
}

function renderSummaryView(view) {
  return renderRenderedText(view?.summary_content || "", "暂无总结内容。");
}

function renderOriginalDetailText(text, emptyText, originalMaxLines) {
  if (originalMaxLines) {
    const { preview, omitted } = getPreviewLines(text, originalMaxLines);
    return `
      ${renderRenderedText(preview, emptyText)}
      ${omitted ? `<div class="message-detail-more">已预览前 ${originalMaxLines} 行，另有 ${omitted} 行可在细版记录中查看。</div>` : ""}
    `;
  }
  return renderRenderedText(text, emptyText);
}

function renderSwitchableDetailText({
  text,
  emptyText,
  target,
  views = {},
  originalMaxLines = 0,
}) {
  const activeView = getActiveDetailTextView(target);
  const key = getDetailTargetKey(target);
  const loading = state.messageDetailLoadingKey === `${key}:${activeView}`;
  const translation = getDetailViewCache(views, "translation");
  const summary = getDetailViewCache(views, "summary");
  let contentHtml = "";
  if (loading) {
    contentHtml = '<div class="message-detail-rendered detail-text-loading">正在生成，请稍候...</div>';
  } else if (activeView === "translation" && translation) {
    contentHtml = renderTranslationView(translation, text, emptyText);
  } else if (activeView === "summary" && summary) {
    contentHtml = renderSummaryView(summary);
  } else {
    contentHtml = renderOriginalDetailText(text, emptyText, originalMaxLines);
  }
  return `
    <div class="detail-text-panel" data-detail-target="${escapeAttribute(key)}">
      ${renderDetailTextControls(target, activeView, views)}
      <div class="detail-text-content">${contentHtml}</div>
    </div>
  `;
}

function isReasoningMetricEntry(entry) {
  const source = String(entry?.source || "").toLowerCase();
  const content = String(entry?.content || "").trim();
  if (!source) {
    return false;
  }
  const leaf = source.split(/[.[\]]+/).filter(Boolean).pop() || "";
  const looksLikeTokenMetric = leaf.endsWith("_tokens") || source.includes("token_usage") || source.includes("usage_metadata");
  return looksLikeTokenMetric && /^-?\d+(\.\d+)?$/.test(content);
}

function renderReasoningEntries(entries) {
  const normalized = Array.isArray(entries) ? entries : [];
  const visibleEntries = normalized.filter((entry) => String(entry?.content || "").trim() && !isReasoningMetricEntry(entry));
  if (!visibleEntries.length) {
    return '<div class="message-detail-empty">本次调用没有返回可见思考内容。</div>';
  }
  return visibleEntries
    .map((entry) => `
        <div class="message-detail-reasoning">
          ${renderSwitchableDetailText({
            text: entry.content,
            emptyText: "暂无思考内容。",
            target: {
              contentKind: "reasoning",
              detailIndex: entry._detail_index,
              entryIndex: entry._entry_index,
            },
            views: entry.views || {},
          })}
        </div>
      `)
    .join("");
}

function normalizeMessageDetailFrames(details) {
  const frames = [];
  let pendingReasoning = [];

  for (const [detailIndex, step] of details.entries()) {
    const kind = String(step?.kind || "");
    if (kind === "reasoning") {
      const entries = Array.isArray(step.entries) ? step.entries : [];
      pendingReasoning = pendingReasoning.concat(
        entries.map((entry, entryIndex) => ({
          ...(entry && typeof entry === "object" ? entry : { content: String(entry || "") }),
          _detail_index: detailIndex,
          _entry_index: entryIndex,
        })),
      );
      continue;
    }
    frames.push({
      ...step,
      _detail_index: detailIndex,
      reasoning_entries: pendingReasoning,
    });
    pendingReasoning = [];
  }

  if (pendingReasoning.length) {
    frames.push({
      kind: "reasoning",
      title: "模型思考",
      entries: pendingReasoning,
    });
  }

  return frames;
}

function renderAttachedReasoning(step) {
  const entries = Array.isArray(step?.reasoning_entries) ? step.reasoning_entries : [];
  const visibleEntries = entries.filter((entry) => String(entry?.content || "").trim() && !isReasoningMetricEntry(entry));
  if (!visibleEntries.length) {
    return "";
  }
  return `
    <div class="message-detail-attached-reasoning">
      <div class="message-detail-section-label">思考内容</div>
      ${renderReasoningEntries(visibleEntries)}
    </div>
  `;
}

function renderMessageDetailStep(step, index) {
  const kind = String(step?.kind || "step");
  const title = String(step?.title || `${getMessageDetailKindLabel(kind)} ${index + 1}`);
  let body = "";

  if (kind === "reasoning") {
    body = renderReasoningEntries(step.entries);
  } else if (kind === "tool_call") {
    body = `
      ${renderAttachedReasoning(step)}
      <div class="message-detail-tool-name">${escapeHtml(step.tool_name || "web_search")}</div>
      ${step.fallback ? '<div class="message-detail-fallback-note">模型未主动调用工具或工具协议失败，本轮由后端自动执行兜底搜索。</div>' : ""}
      ${renderStructuredArgs(step.args)}
    `;
  } else if (kind === "tool_result") {
    body = `
      <div class="message-detail-tool-name">${escapeHtml(step.tool_name || "web_search")}</div>
      ${step.fallback ? '<div class="message-detail-fallback-note">这是后端兜底搜索返回结果。</div>' : ""}
      ${renderSwitchableDetailText({
        text: step.result,
        emptyText: "工具没有返回可展示内容。",
        target: {
          contentKind: "tool_result",
          detailIndex: step._detail_index,
          entryIndex: null,
        },
        views: step.views || {},
        originalMaxLines: 12,
      })}
    `;
  } else if (kind === "output") {
    body = `
      ${renderAttachedReasoning(step)}
      <div class="message-detail-section-label">正式输出</div>
      ${renderRenderedText(step.content, "本步骤没有正式输出。")}
    `;
  } else {
    body = renderStructuredArgs(step);
  }

  return `
    <section class="${getMessageDetailStepClass(step)}">
      <div class="message-detail-step-head">
        <span class="message-detail-step-index">框 ${index + 1}</span>
        <span class="message-detail-step-kind">${escapeHtml(getMessageDetailStepKindLabel(step))}</span>
        <h4>${escapeHtml(title)}</h4>
      </div>
      <div class="message-detail-step-body">${body}</div>
    </section>
  `;
}

function renderMessageDetails(message, session) {
  const details = Array.isArray(message?.details) ? message.details.filter((item) => item && typeof item === "object") : [];
  if (!details.length) {
    return '<div class="empty-state">这条消息没有保存到可展示的调用细节。</div>';
  }
  const frames = normalizeMessageDetailFrames(details);
  const label = getRoleDisplayLabel(message, session);
  const roundLabel = message.round ? `第 ${message.round} 轮` : "";
  const meta = [label, roundLabel].filter(Boolean).join(" · ");
  return `
    <div class="message-detail-meta">${escapeHtml(meta || "模型消息")}</div>
    <div class="message-detail-steps">
      ${frames.map((step, index) => renderMessageDetailStep(step, index)).join("")}
    </div>
  `;
}

function parseDetailTextViewTarget(action) {
  const entryRaw = action.dataset.entryIndex;
  return {
    view: String(action.dataset.view || "original"),
    contentKind: String(action.dataset.contentKind || ""),
    detailIndex: Number(action.dataset.detailIndex),
    entryIndex: entryRaw === undefined || entryRaw === "" ? null : Number(entryRaw),
  };
}

function findDetailContainerForTarget(message, target) {
  const details = Array.isArray(message?.details) ? message.details : [];
  const detail = details[target.detailIndex];
  if (!detail || typeof detail !== "object") {
    return null;
  }
  if (target.contentKind === "reasoning") {
    const entries = Array.isArray(detail.entries) ? detail.entries : [];
    const entry = entries[target.entryIndex];
    return entry && typeof entry === "object" ? entry : null;
  }
  if (target.contentKind === "tool_result") {
    return detail;
  }
  return null;
}

function getCachedDetailTextView(target) {
  const message = findCurrentMessageById(state.messageDetail?.messageId || "");
  const container = findDetailContainerForTarget(message, target);
  const views = container?.views && typeof container.views === "object" ? container.views : {};
  const cached = views[target.view];
  return cached && typeof cached === "object" ? cached : null;
}

function setActiveDetailTextView(target, view) {
  if (!state.messageDetail) {
    return;
  }
  state.messageDetail.activeViews = state.messageDetail.activeViews || {};
  state.messageDetail.activeViews[getDetailTargetKey(target)] = view;
}

function rerenderMessageDetailBody({ preserveScroll = true } = {}) {
  if (!state.messageDetail?.messageId) {
    return;
  }
  const message = findCurrentMessageById(state.messageDetail.messageId);
  if (!message) {
    return;
  }
  const scrollTop = preserveScroll ? els.messageDetailBody.scrollTop : 0;
  els.messageDetailBody.innerHTML = renderMessageDetails(message, state.currentSession);
  els.messageDetailBody.scrollTop = scrollTop;
}

function renderDetailTextTaskBar() {
  if (!els.detailTextTaskBar || !els.detailTextTaskLabel) {
    return;
  }
  const task = state.messageDetailTask;
  if (!task) {
    els.detailTextTaskBar.classList.add("hidden");
    els.detailTextTaskBar.classList.remove("visible");
    els.detailTextTaskLabel.textContent = "";
    if (els.cancelDetailTextTaskBtn) {
      els.cancelDetailTextTaskBtn.disabled = false;
    }
    return;
  }
  els.detailTextTaskLabel.textContent = task.label || "正在处理模型调用细节...";
  if (els.cancelDetailTextTaskBtn) {
    els.cancelDetailTextTaskBtn.disabled = Boolean(task.cancelling);
  }
  els.detailTextTaskBar.classList.remove("hidden");
  window.requestAnimationFrame(() => {
    if (state.messageDetailTask === task) {
      els.detailTextTaskBar.classList.add("visible");
    }
  });
}

function clearMessageDetailTextTask(task) {
  if (task && state.messageDetailTask && state.messageDetailTask !== task) {
    return;
  }
  state.messageDetailTask = null;
  state.messageDetailLoadingKey = "";
  renderDetailTextTaskBar();
}

async function cancelMessageDetailTextTask() {
  const task = state.messageDetailTask;
  if (!task || task.cancelling) {
    return;
  }
  task.cancelled = true;
  task.cancelling = true;
  task.label = task.view === "translation" ? "正在取消翻译请求..." : "正在取消总结请求...";
  if (task.target) {
    setActiveDetailTextView(task.target, "original");
  }
  renderDetailTextTaskBar();
  rerenderMessageDetailBody();
  try {
    const result = await api(`/api/detail-tasks/${encodeURIComponent(task.taskId)}/cancel`, {
      method: "POST",
      timeoutMs: 15000,
    });
    if (!result?.cancelled) {
      task.cancelled = false;
      task.cancelling = false;
      task.label = task.view === "translation" ? "正在翻译模型调用细节..." : "正在总结模型调用细节...";
      renderDetailTextTaskBar();
      return;
    }
    task.controller?.abort();
    task.cancelling = false;
    clearMessageDetailTextTask(task);
    rerenderMessageDetailBody();
  } catch (error) {
    if (state.messageDetailTask !== task) {
      return;
    }
    task.cancelled = false;
    task.cancelling = false;
    task.label = task.view === "translation" ? "正在翻译模型调用细节..." : "正在总结模型调用细节...";
    renderDetailTextTaskBar();
    showLocalError(error?.message || "取消请求失败，原任务仍在继续。", true);
  }
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

async function handleMessageDetailBodyClick(event) {
  const action = event.target.closest("[data-action='message-detail-text-view']");
  if (!action || !state.messageDetail?.messageId || !state.currentSession?.id) {
    return;
  }
  const sessionId = state.currentSession.id;
  const messageId = state.messageDetail.messageId;
  const target = parseDetailTextViewTarget(action);
  if (!Number.isInteger(target.detailIndex) || (target.contentKind === "reasoning" && !Number.isInteger(target.entryIndex))) {
    showLocalError("无法定位这段调用细节文本。", true);
    return;
  }

  if (target.view === "original") {
    setActiveDetailTextView(target, "original");
    rerenderMessageDetailBody();
    return;
  }

  if (getCachedDetailTextView(target)) {
    setActiveDetailTextView(target, target.view);
    rerenderMessageDetailBody();
    return;
  }

  const loadingKey = `${getDetailTargetKey(target)}:${target.view}`;
  if (state.messageDetailTask) {
    renderDetailTextTaskBar();
    return;
  }
  const controller = new AbortController();
  const taskId = createDetailTaskId();
  const task = {
    taskId,
    key: loadingKey,
    view: target.view,
    target,
    label: target.view === "translation" ? "正在翻译模型调用细节..." : "正在总结模型调用细节...",
    controller,
    cancelled: false,
    cancelling: false,
  };
  state.messageDetailTask = task;
  state.messageDetailLoadingKey = loadingKey;
  setActiveDetailTextView(target, target.view);
  renderDetailTextTaskBar();
  rerenderMessageDetailBody();

  try {
    const result = await api(`/api/debates/${sessionId}/message-detail-view`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      timeoutMs: MODEL_TASK_API_TIMEOUT_MS,
      body: JSON.stringify({
        message_id: messageId,
        detail_index: target.detailIndex,
        content_kind: target.contentKind,
        entry_index: target.entryIndex,
        view: target.view,
        task_id: taskId,
      }),
    });
    if (result?.cancelled) {
      return;
    }
    if (result?.session) {
      if (state.currentSession?.id === sessionId) {
        state.currentSession = result.session;
      }
      upsertSessionSummary(result.session);
      renderSessions();
    }
  } catch (error) {
    if (isAbortError(error) || task.cancelled) {
      return;
    }
    setActiveDetailTextView(target, "original");
    showLocalError(error?.message || "生成内容失败，请检查翻译/总结模型配置。", true);
  } finally {
    if (!task.cancelling) {
      clearMessageDetailTextTask(task);
    }
    rerenderMessageDetailBody();
  }
}

function createDetailTaskId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `detail-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function openMessageDetails(messageId) {
  const message = findCurrentMessageById(messageId);
  if (!message || !["pro", "con"].includes(String(message.role || "")) || !hasMessageDetails(message)) {
    showLocalError("这条消息还没有可查看的调用细节。", true);
    return;
  }
  state.messageDetail = {
    messageId: message.id,
    sessionId: state.currentSession?.id || "",
    activeViews: {},
  };
  window.clearTimeout(state.messageDetailModalTimer);
  els.messageDetailModal.classList.remove("hidden", "modal-leaving");
  els.messageDetailModal.classList.add("modal-visible");
  els.messageDetailEyebrow.textContent = "Call Details";
  els.messageDetailTitle.textContent = "模型调用细节";
  els.messageDetailBody.innerHTML = renderMessageDetails(message, state.currentSession);
  els.messageDetailBody.scrollTop = 0;
}

function closeMessageDetailModal({ immediate = false } = {}) {
  window.clearTimeout(state.messageDetailModalTimer);
  state.messageDetail = null;
  if (immediate) {
    els.messageDetailModal.classList.add("hidden");
    els.messageDetailModal.classList.remove("modal-visible", "modal-leaving");
    return;
  }
  els.messageDetailModal.classList.remove("modal-visible");
  els.messageDetailModal.classList.add("modal-leaving");
  state.messageDetailModalTimer = window.setTimeout(() => {
    els.messageDetailModal.classList.add("hidden");
    els.messageDetailModal.classList.remove("modal-leaving");
  }, MODAL_MOTION_MS);
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
  renderInlineErrorToast();
}

function showLocalError(message, ephemeral = false) {
  const normalizedMessage = String(message || "发生未知错误，请检查服务日志。");
  state.inlineError = normalizedMessage;
  renderInlineErrorToast();
  if (ephemeral) {
    window.setTimeout(() => {
      if (state.inlineError === normalizedMessage) {
        clearInlineError();
      }
    }, 3600);
  }
}

function renderInlineErrorToast() {
  if (!els.appErrorToast || !els.appErrorToastMessage) {
    return;
  }
  els.appErrorToastMessage.textContent = state.inlineError;
  els.appErrorToast.classList.toggle("hidden", !state.inlineError);
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
