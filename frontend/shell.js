/* Presentation-only behavior. Debate and configuration state stays in app.js. */
window.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sessionSidebar");
  const toggle = document.getElementById("toggleSidebarBtn");
  const workspace = document.querySelector(".workspace");
  const shell = document.querySelector(".app-shell");
  const mobile = window.matchMedia("(max-width: 720px)");
  const dialogs = [...document.querySelectorAll(".modal")];
  const openers = new WeakMap();
  const outsideFocus = new WeakMap();
  let activeDialogs = [];
  const sidebarPreferenceKey = "debateStudio.sidebarCollapsed";
  let desktopSidebarOpen = true;
  let mobileSidebarOpen = false;
  try { desktopSidebarOpen = localStorage.getItem(sidebarPreferenceKey) !== "true"; } catch { /* Storage may be unavailable. */ }
  const focusable = (root) => [...root.querySelectorAll("button, a[href], input, select, textarea, [tabindex]")]
    .filter((el) => !el.disabled && el.tabIndex >= 0 && !el.closest("[inert]") && el.getClientRects().length);

  function renderSidebar() {
    const visible = mobile.matches ? mobileSidebarOpen : desktopSidebarOpen;
    document.body.classList.toggle("sidebar-open", mobile.matches && visible);
    document.body.classList.toggle("sidebar-collapsed", !desktopSidebarOpen);
    toggle.setAttribute("aria-expanded", String(visible));
    toggle.setAttribute("aria-label", visible ? "收起历史侧栏" : "展开历史侧栏");
    toggle.title = visible ? "收起历史侧栏" : "展开历史侧栏";
    sidebar.inert = !visible;
    workspace.inert = mobile.matches && visible;
  }

  function setSidebar(open, returnFocus = false) {
    if (mobile.matches) mobileSidebarOpen = open;
    else {
      desktopSidebarOpen = open;
      try { localStorage.setItem(sidebarPreferenceKey, String(!open)); } catch { /* Keep working without persistence. */ }
    }
    renderSidebar();
    if (open && mobile.matches) requestAnimationFrame(() => {
      if (mobile.matches && mobileSidebarOpen) document.getElementById("closeSidebarBtn").focus();
    });
    else if (returnFocus || (!open && sidebar.contains(document.activeElement))) toggle.focus({ preventScroll: true });
  }

  function closeMobileSidebar(returnFocus = false) {
    if (mobile.matches) setSidebar(false, returnFocus);
  }

  toggle.addEventListener("click", () => setSidebar(!(mobile.matches ? mobileSidebarOpen : desktopSidebarOpen)));
  document.getElementById("closeSidebarBtn").addEventListener("click", () => setSidebar(false, true));
  document.getElementById("sidebarBackdrop").addEventListener("click", () => setSidebar(false, true));
  sidebar.addEventListener("click", (event) => {
    if (event.target.closest("[data-session-id]") && !event.target.closest("[data-action]")) closeMobileSidebar(true);
  });
  mobile.addEventListener("change", () => {
    mobileSidebarOpen = false;
    renderSidebar();
    if (sidebar.inert && sidebar.contains(document.activeElement)) toggle.focus({ preventScroll: true });
  });
  renderSidebar();
  // Apply the saved layout before enabling transitions, avoiding a slide on reload.
  requestAnimationFrame(() => requestAnimationFrame(() => shell.classList.add("sidebar-ready")));

  // Capture the opener before app.js can focus an input inside a new dialog.
  document.addEventListener("focusin", (event) => {
    for (const modal of dialogs) {
      if (!modal.contains(event.target)) outsideFocus.set(modal, event.target);
    }
  });
  const headline = document.getElementById("currentHeadline");
  const syncHeadlineFocus = () => { headline.tabIndex = headline.classList.contains("headline-editable") ? 0 : -1; };
  syncHeadlineFocus();
  new MutationObserver(syncHeadlineFocus).observe(headline, { attributes: true, attributeFilter: ["class"] });
  headline.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && headline.classList.contains("headline-editable")) {
      event.preventDefault();
      headline.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    }
  });
  headline.addEventListener("dblclick", () => outsideFocus.set(document.getElementById("titleEditModal"), headline));

  const closeButtons = {
    settingsModal: "closeSettingsBtn", archivedModal: "closeArchivedBtn",
    markdownPreviewModal: "closeMarkdownPreviewBtn", messageDetailModal: "closeMessageDetailBtn",
    titleEditModal: "cancelTitleEditBtn", changelogModal: "closeChangelogBtn",
  };
  for (const modal of dialogs) {
    const card = modal.querySelector(".modal-card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    const heading = card.querySelector("h3");
    if (!heading.id) heading.id = `${modal.id}Heading`;
    card.setAttribute("aria-labelledby", heading.id);
    card.tabIndex = -1;
    new MutationObserver(() => {
      // Keep the page isolated until the exit animation has actually finished.
      const visible = !modal.classList.contains("hidden");
      const wasVisible = activeDialogs.includes(modal);
      if (visible && !wasVisible) {
        openers.set(modal, outsideFocus.get(modal) || document.getElementById("settingsBtn"));
        activeDialogs.push(modal);
        closeMobileSidebar();
        modal.inert = false;
        if (!card.contains(document.activeElement)) (focusable(card)[0] || card).focus({ preventScroll: true });
      } else if (!visible && wasVisible) {
        activeDialogs = activeDialogs.filter((item) => item !== modal);
      }
      shell.inert = activeDialogs.length > 0;
      for (const item of dialogs) item.inert = item !== activeDialogs.at(-1);
      if (!visible && wasVisible) {
        const opener = openers.get(modal);
        const returnTarget = opener?.isConnected && !opener.closest("[inert]") ? opener : headline;
        returnTarget.focus({ preventScroll: true });
      }
    }).observe(modal, { attributes: true, attributeFilter: ["class"] });
  }

  const presetPanel = document.getElementById("presetManagerPanel");
  let presetOpen = false;
  let presetOpener = null;
  let presetOpenerSelector = "";
  let presetFocusSelector = "";
  let presetAction = "";
  function controlSelector(element) {
    if (!(element instanceof Element)) return "";
    const attributes = [...element.attributes].filter(({ name }) => name.startsWith("data-") || ["id", "name", "type"].includes(name));
    if (element.matches('input[type="radio"]')) attributes.push({ name: "value", value: element.value });
    return attributes.length ? element.localName + attributes.map(({ name, value }) => `[${CSS.escape(name)}="${CSS.escape(value)}"]`).join("") : "";
  }
  function rememberPresetControl(event) {
    const control = event.target.closest("button, input, select, textarea");
    if (!control) return;
    presetFocusSelector = controlSelector(control);
    presetAction = control.dataset.action || "";
  }
  // Stable data attributes survive innerHTML replacement; text and classes do not.
  for (const type of ["focusin", "click", "change"]) presetPanel.addEventListener(type, rememberPresetControl, true);
  new MutationObserver(() => {
    const visible = !presetPanel.classList.contains("hidden");
    if (visible && !presetOpen) {
      presetOpener = document.activeElement;
      presetOpenerSelector = controlSelector(presetOpener);
      presetFocusSelector = "";
    }
    document.getElementById("settingsForm").inert = visible;
    if (visible && (!presetOpen || document.activeElement === document.body)) {
      const restored = presetFocusSelector ? presetPanel.querySelector(presetFocusSelector) : null;
      const flowReturn = presetAction === "close-response-flow-editor" ? presetPanel.querySelector('[data-action="open-response-flow-editor"]') : null;
      const target = (restored && !restored.disabled ? restored : null) || flowReturn || presetPanel.querySelector('[role="tab"][aria-selected="true"], [data-action="close-response-flow-editor"]');
      (target || focusable(presetPanel)[0])?.focus({ preventScroll: true });
    } else if (!visible && presetOpen && !document.getElementById("settingsModal").inert) {
      const replacement = presetOpenerSelector ? document.getElementById("settingsForm").querySelector(presetOpenerSelector) : null;
      const target = presetOpener?.isConnected ? presetOpener : replacement;
      target?.focus({ preventScroll: true });
    }
    presetOpen = visible;
  }).observe(presetPanel, { childList: true, attributes: true, attributeFilter: ["class"] });

  // Route Escape through existing close handlers to preserve save/cancel semantics.
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    const modal = activeDialogs.at(-1);
    const drawerOpen = document.body.classList.contains("sidebar-open");
    if (event.key === "Escape") {
      if (modal) {
        event.preventDefault();
        const nestedClose = modal.querySelector(".preset-overlay:not(.hidden) [data-action='close-response-flow-editor'], .preset-overlay:not(.hidden) [data-action='close-preset-manager']");
        (nestedClose || document.getElementById(closeButtons[modal.id]))?.click();
      } else if (drawerOpen) {
        event.preventDefault();
        setSidebar(false, true);
      }
    }
    if (event.key === "Tab" && (modal || drawerOpen)) {
      const root = modal || sidebar;
      const items = focusable(root);
      const taskBar = document.getElementById("detailTextTaskBar");
      if (modal && !taskBar.classList.contains("hidden")) items.push(...focusable(taskBar));
      const first = items[0];
      const last = items.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (!items.includes(document.activeElement) || document.activeElement === first)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (!items.includes(document.activeElement) || document.activeElement === last)) {
        event.preventDefault(); first.focus();
      }
    }
  });

  // Session rows contain action buttons, so the row itself is not a nested button.
  const history = document.getElementById("historyList");
  new MutationObserver(() => {
    for (const row of history.querySelectorAll(".history-item")) {
      row.tabIndex = 0;
      row.setAttribute("role", "group");
      row.setAttribute("aria-label", row.querySelector(".history-title")?.textContent || "辩论记录");
    }
  }).observe(history, { childList: true });
  history.addEventListener("keydown", (event) => {
    if (event.target.matches(".history-item") && ["Enter", " "].includes(event.key)) {
      event.preventDefault(); event.target.click();
    }
  });
});
