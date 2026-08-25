// Плавающий тултип (для полоски аптайма). Позиционируется над засечкой.
let tip = null;

function ensure() {
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'tip';
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  return tip;
}

export function showTip(html, anchorRect) {
  const t = ensure();
  t.innerHTML = html;
  t.hidden = false;
  const r = t.getBoundingClientRect();
  let left = anchorRect.left + anchorRect.width / 2 - r.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - r.width - 8));
  let top = anchorRect.top - r.height - 10;
  if (top < 8) top = anchorRect.bottom + 10;
  t.style.left = left + 'px';
  t.style.top = top + 'px';
}

export function hideTip() {
  if (tip) tip.hidden = true;
}
