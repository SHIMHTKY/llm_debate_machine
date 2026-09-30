/* motion.js — fluid UI animation layer.
   Public API: uiMotion.modal, uiMotion.presence, uiMotion.reveal
   Interrupted exits never hide a newly-reopened surface. */
const uiMotion = (() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const records = new WeakMap();   // element → { visible, animations[] }
  const effects  = new WeakMap();  // element → one-shot animation
  const active   = new Set();

  /* Easings ---------------------------------------------------------------- */
  const easeOut   = "cubic-bezier(.2, .8, .2, 1)";
  const easeSpring = "cubic-bezier(.3, 1.4, .6, 1)";   // slight overshoot
  const easeModal  = "cubic-bezier(.18, .9, .4, 1.06)"; // dialog spring

  /* CSS variable → milliseconds ------------------------------------------- */
  function ms(name, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n   = parseFloat(raw);
    return Number.isFinite(n) ? n * (raw.endsWith("ms") ? 1 : 1000) : fallback;
  }

  /* Core animate wrapper — respects reduced-motion, tracks active set ------ */
  function animate(el, frames, duration, easing = easeOut) {
    if (!el?.animate || reduced.matches) return null;
    const a = el.animate(frames, { duration, easing, fill: "both" });
    active.add(a);
    a.finished.catch(() => {}).finally(() => active.delete(a));
    return a;
  }

  /* Begin a new visibility transition, cancelling any in-flight one -------- */
  function start(el, visible) {
    const prev   = records.get(el);
    const record = { visible, animations: [] };
    records.set(el, record);
    prev?.animations.forEach(a => a.cancel());
    return record;
  }

  /* Wait for all animations then run complete() if still current ----------- */
  function settle(el, record, complete) {
    const finish = () => {
      if (records.get(el) !== record) return;
      complete();
      record.animations.forEach(a => a.cancel());
      record.animations = [];
    };
    if (!record.animations.length) finish();
    else Promise.all(record.animations.map(a => a.finished.catch(() => {}))).then(finish);
  }

  /* ── modal() — backdrop fade + card spring ─────────────────────────────── */
  function modal(el, visible, { immediate = false, onHidden } = {}) {
    const prev = records.get(el);
    if (prev?.visible === visible && !immediate) return;

    let backdrop = el.querySelector(".modal-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "modal-backdrop";
      backdrop.setAttribute("aria-hidden", "true");
      el.prepend(backdrop);
    }
    const card = el.querySelector(".modal-card");

    const interrupted    = Boolean(prev?.animations.length);
    const fromBackdrop   = interrupted ? getComputedStyle(backdrop).opacity
                                       : visible ? "0" : "1";
    const fromTranslate  = interrupted ? getComputedStyle(card).translate
                                       : visible ? "0 20px" : "0 0";
    const fromScale      = interrupted ? getComputedStyle(card).scale
                                       : visible ? "0.96" : "1";

    const record    = start(el, visible);
    const wasHidden = el.classList.contains("hidden");

    if (visible) { el.classList.remove("hidden"); el.inert = false; }
    el.classList.toggle("modal-visible",  visible);
    el.classList.toggle("modal-leaving",  !visible && !wasHidden);
    card.inert = !visible;

    if (!immediate && (!wasHidden || visible)) {
      const duration = ms(visible ? "--motion-dialog" : "--motion-exit", visible ? 280 : 160);
      const easing   = visible ? easeModal : easeOut;
      record.animations = [
        animate(backdrop, [
          { opacity: fromBackdrop },
          { opacity: visible ? 1 : 0 },
        ], duration, easeOut),
        animate(card, [
          { translate: fromTranslate, scale: fromScale },
          { translate: "0 0",        scale: "1"       },
        ], visible ? duration : duration * 0.85, easing),
      ].filter(Boolean);
    }

    settle(el, record, () => {
      if (!visible) {
        el.classList.add("hidden");
        el.classList.remove("modal-leaving");
        onHidden?.();
      }
    });
  }

  /* ── presence() — toasts, menus, popovers ──────────────────────────────── */
  function presence(el, visible, { onHidden } = {}) {
    const prev = records.get(el);
    if (prev?.visible === visible) return;

    const from         = prev?.animations.length ? getComputedStyle(el) : null;
    const fromOpacity  = from ? from.opacity   : visible ? "0" : "1";
    const fromTranslate = from ? from.translate : visible ? "0 8px" : "0 0";
    const fromScale    = from ? from.scale      : visible ? "0.97" : "1";

    const record    = start(el, visible);
    const wasHidden = el.classList.contains("hidden");

    if (visible) el.classList.remove("hidden");
    el.inert = !visible;

    if (visible || !wasHidden) {
      const duration = ms(visible ? "--motion-fast" : "--motion-exit", 140);
      record.animations = [animate(el, [
        { opacity: fromOpacity,  translate: fromTranslate, scale: fromScale },
        { opacity: visible ? 1 : 0, translate: "0 0",      scale: visible ? "1" : "0.97" },
      ], duration, visible ? easeSpring : easeOut)].filter(Boolean);
    }

    settle(el, record, () => {
      if (!visible) { el.classList.add("hidden"); onHidden?.(); }
    });
  }

  /* ── reveal() — panel crossfade + rise ─────────────────────────────────── */
  function reveal(el, { offset = 6, fade = true, spring = false } = {}) {
    effects.get(el)?.cancel();
    const duration = ms("--motion-medium", 220);
    const easing   = spring ? easeSpring : easeOut;
    const a = animate(el, [
      { opacity: fade ? 0 : 0.4, translate: `0 ${offset}px`, scale: spring ? "0.97" : "1" },
      { opacity: 1,               translate: "0 0",            scale: "1"                   },
    ], duration, easing);
    if (!a) return;
    effects.set(el, a);
    a.finished.catch(() => {}).then(() => {
      if (effects.get(el) === a) { a.cancel(); effects.delete(el); }
    });
  }

  /* ── popover() — menus, disclosures, submenus (enter + exit) ───────────── */
  function popover(el, visible, { onHidden, origin = "top" } = {}) {
    const prev = records.get(el);
    if (prev?.visible === visible) return;

    const from          = prev?.animations.length ? getComputedStyle(el) : null;
    const fromOpacity   = from ? from.opacity  : visible ? "0" : "1";
    const fromTranslate = from ? from.translate
      : visible ? (origin === "bottom" ? "0 6px" : "0 -6px") : "0 0";
    const fromScale     = from ? from.scale    : visible ? "0.95" : "1";

    const record    = start(el, visible);
    const wasHidden = el.classList.contains("hidden");

    if (visible) { el.classList.remove("hidden"); el.inert = false; }

    if (visible || !wasHidden) {
      const duration = ms(visible ? "--motion-fast" : "--motion-exit", visible ? 140 : 110);
      record.animations = [animate(el, [
        { opacity: fromOpacity,       translate: fromTranslate, scale: fromScale },
        { opacity: visible ? 1 : 0,   translate: "0 0",         scale: visible ? "1" : "0.95" },
      ], duration, visible ? easeSpring : easeOut)].filter(Boolean);
    }

    settle(el, record, () => {
      if (!visible) { el.classList.add("hidden"); el.inert = true; onHidden?.(); }
    });
  }

  /* ── slideToggle() — accordion / highlight-group expand/collapse ────────── */
  function slideToggle(el, visible) {
    if (reduced.matches) {
      el.style.display = visible ? "" : "none";
      return;
    }
    if (visible) {
      el.style.display = "";
      const h = el.scrollHeight;
      animate(el, [
        { opacity: 0, maxHeight: "0px", overflow: "hidden" },
        { opacity: 1, maxHeight: `${h}px`, overflow: "hidden" },
      ], ms("--motion-medium", 220), easeOut)
        ?.finished.catch(() => {}).then(() => { el.style.maxHeight = ""; el.style.overflow = ""; });
    } else {
      const h = el.scrollHeight;
      const a = animate(el, [
        { opacity: 1, maxHeight: `${h}px`, overflow: "hidden" },
        { opacity: 0, maxHeight: "0px",    overflow: "hidden" },
      ], ms("--motion-fast", 140), easeOut);
      a?.finished.catch(() => {}).then(() => { el.style.display = "none"; el.style.maxHeight = ""; el.style.overflow = ""; });
    }
  }

  /* Immediately finish all active animations when reduced-motion turns on -- */
  reduced.addEventListener("change", () => {
    if (reduced.matches) for (const a of active) a.finish();
  });

  return { modal, presence, reveal, popover, slideToggle, reduced: () => reduced.matches };
})();
