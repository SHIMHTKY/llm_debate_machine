/* Shared lifecycle: interrupted exits must never hide a newly reopened surface. */
const uiMotion = (() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const records = new WeakMap();
  const effects = new WeakMap();
  const active = new Set();
  const ease = "cubic-bezier(.2, .8, .2, 1)";

  function duration(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const number = parseFloat(value);
    return Number.isFinite(number) ? number * (value.endsWith("ms") ? 1 : 1000) : fallback;
  }

  function animate(element, frames, milliseconds) {
    if (!element?.animate || reduced.matches) return null;
    const animation = element.animate(frames, { duration: milliseconds, easing: ease, fill: "both" });
    active.add(animation);
    animation.finished.catch(() => {}).finally(() => active.delete(animation));
    return animation;
  }

  function start(element, visible) {
    const previous = records.get(element);
    const record = { visible, animations: [] };
    records.set(element, record);
    previous?.animations.forEach((animation) => animation.cancel());
    return record;
  }

  function settle(element, record, complete) {
    const finish = () => {
      if (records.get(element) !== record) return;
      complete();
      record.animations.forEach((animation) => animation.cancel());
      record.animations = [];
    };
    if (!record.animations.length) finish();
    else Promise.all(record.animations.map((animation) => animation.finished.catch(() => {}))).then(finish);
  }

  function modal(element, visible, { immediate = false, onHidden } = {}) {
    const previous = records.get(element);
    if (previous?.visible === visible && !immediate) return;
    const card = element.querySelector(".modal-card");
    let backdrop = element.querySelector(".modal-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "modal-backdrop";
      backdrop.setAttribute("aria-hidden", "true");
      element.prepend(backdrop);
    }
    const interrupted = Boolean(previous?.animations.length);
    const fromBackdrop = interrupted ? getComputedStyle(backdrop).opacity : visible ? 0 : 1;
    const fromCard = interrupted ? getComputedStyle(card).translate : visible ? "0 8px" : "0 0";
    const record = start(element, visible);
    const wasHidden = element.classList.contains("hidden");
    if (visible) { element.classList.remove("hidden"); element.inert = false; }
    element.classList.toggle("modal-visible", visible);
    element.classList.toggle("modal-leaving", !visible && !wasHidden);
    card.inert = !visible;
    if (!immediate && (!wasHidden || visible)) {
      const milliseconds = duration(visible ? "--motion-dialog" : "--motion-exit", visible ? 200 : 140);
      record.animations = [
        animate(backdrop, [{ opacity: fromBackdrop }, { opacity: visible ? 1 : 0 }], milliseconds),
        animate(card, [{ translate: fromCard }, { translate: visible ? "0 0" : "0 6px" }], milliseconds),
      ].filter(Boolean);
    }
    settle(element, record, () => {
      if (!visible) {
        element.classList.add("hidden");
        element.classList.remove("modal-leaving");
        onHidden?.();
      }
    });
  }

  function presence(element, visible, { onHidden } = {}) {
    const previous = records.get(element);
    if (previous?.visible === visible) return;
    const from = previous?.animations.length ? getComputedStyle(element) : null;
    const fromOpacity = from ? from.opacity : visible ? 0 : 1;
    const fromTranslate = from ? from.translate : visible ? "0 6px" : "0 0";
    const record = start(element, visible);
    const wasHidden = element.classList.contains("hidden");
    if (visible) element.classList.remove("hidden");
    element.inert = !visible;
    if (visible || !wasHidden) {
      record.animations = [animate(element, [
        { opacity: fromOpacity, translate: fromTranslate },
        { opacity: visible ? 1 : 0, translate: visible ? "0 0" : "0 4px" },
      ], duration(visible ? "--motion-fast" : "--motion-exit", 140))].filter(Boolean);
    }
    settle(element, record, () => {
      if (!visible) { element.classList.add("hidden"); onHidden?.(); }
    });
  }

  function reveal(element, { offset = 4, fade = true } = {}) {
    effects.get(element)?.cancel();
    const animation = animate(element, [
      { opacity: fade ? .6 : 1, translate: `0 ${offset}px` },
      { opacity: 1, translate: "0 0" },
    ], duration("--motion-medium", 220));
    if (!animation) return;
    effects.set(element, animation);
    animation.finished.catch(() => {}).then(() => {
      if (effects.get(element) === animation) { animation.cancel(); effects.delete(element); }
    });
  }

  reduced.addEventListener("change", () => {
    if (reduced.matches) for (const animation of active) animation.finish();
  });
  return { modal, presence, reveal, reduced: () => reduced.matches };
})();
