// Тонкий слой доступа к API. Общий для витрины и админки.

export async function getSummary() {
  const r = await fetch('/api/summary', { cache: 'no-store' });
  if (!r.ok) throw new Error('summary failed');
  return r.json();
}

// Админ-запросы. Кука status_admin ставится при логине; заголовок не нужен.
export async function admin(path, { method = 'GET', body } = {}) {
  const r = await fetch('/api/admin' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) throw new Error('unauthorized');
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'request failed');
  return r.status === 204 ? null : r.json();
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function fmtTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}
