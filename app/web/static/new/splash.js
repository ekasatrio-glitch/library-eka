// First-visit splash. Flag logic is DOM-free + tested; mountSplash wires the DOM.

const FLAG = "libeka.splashSeen";

export function shouldShowSplash(storage) {
  return storage.getItem(FLAG) !== "1";
}

export function markSplashSeen(storage) {
  storage.setItem(FLAG, "1");
}

export function mountSplash(doc, storage) {
  const el = doc.getElementById("splash");
  if (!el) return;
  if (!shouldShowSplash(storage)) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  const dismiss = () => {
    markSplashSeen(storage);
    el.hidden = true;
  };
  ["splash-close", "splash-enter", "splash-skip"].forEach(id => {
    const b = doc.getElementById(id);
    if (b) b.addEventListener("click", dismiss);
  });
}
