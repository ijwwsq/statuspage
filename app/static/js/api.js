// Тонкий слой доступа к API. Общий для витрины и админки.

export async function getSummary() {
  const r = await fetch('/api/summary', { cache: 'no-store' });
  if (!r.ok) throw new Error('summary failed');
  return r.json();
}

function cookie(name) {
  const hit = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
  return hit ? decodeURIComponent(hit.split('=')[1]) : '';
}

// Админ-запросы. Кука status_admin ставится при логине; мутации несут X-CSRF (double-submit).
export async function admin(path, { method = 'GET', body } = {}) {
  const headers = body ? { 'Content-Type': 'application/json' } : {};
  if (method !== 'GET') headers['X-CSRF'] = cookie('status_csrf');
  const r = await fetch('/api/admin' + path, {
    method,
    headers,
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
    return new Date(iso).toLocaleString('en-US', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}
