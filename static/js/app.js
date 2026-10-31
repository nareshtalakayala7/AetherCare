(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  window.api = async (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    if (options.method && options.method.toUpperCase() !== 'GET') headers['X-CSRFToken'] = csrf;
    const response = await fetch(url, { credentials: 'same-origin', ...options, headers });
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) throw new Error(data?.error || `Request failed (${response.status})`);
    return data;
  };
  window.escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.formatTime = (value, withDate = true) => {
    if (!value) return '—';
    const date = new Date(value);
    return new Intl.DateTimeFormat(undefined, withDate ? { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' } : { hour:'2-digit', minute:'2-digit', second:'2-digit' }).format(date);
  };
  window.tempStatus = (p) => !p.online ? 'offline' : p.temperature_c == null ? 'unknown' : (p.temperature_c < p.minimum_c || p.temperature_c > p.maximum_c ? 'warning' : 'normal');
  window.showToast = (message, kind = '') => {
    const region = document.getElementById('toast-region');
    if (!region) return;
    const toast = document.createElement('div'); toast.className = `toast ${kind}`; toast.textContent = message; region.appendChild(toast);
    setTimeout(() => toast.remove(), 3600);
  };
  const date = document.getElementById('today-date');
  if (date) date.textContent = new Intl.DateTimeFormat(undefined, { weekday:'short', month:'short', day:'numeric' }).format(new Date());
  document.getElementById('menu-toggle')?.addEventListener('click', () => document.getElementById('sidebar')?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    const sidebar = document.getElementById('sidebar');
    if (sidebar?.classList.contains('open') && !sidebar.contains(event.target) && !event.target.closest('#menu-toggle')) sidebar.classList.remove('open');
  });
  const refreshUnread = async () => {
    try {
      const { alerts } = await window.api('/api/alerts?unread=1');
      const count = alerts.length;
      const nav = document.getElementById('nav-alert-count');
      if (nav) { nav.textContent = count ? (count > 9 ? '9+' : count) : ''; nav.classList.toggle('show', count > 0); }
      document.getElementById('top-alert-dot')?.classList.toggle('show', count > 0);
    } catch (_) { /* Signed-out or restricted surfaces may not show alert counts. */ }
  };
  if (document.getElementById('nav-alert-count')) { refreshUnread(); setInterval(refreshUnread, 5000); }
})();
