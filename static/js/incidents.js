(() => {
  const pending = document.getElementById('pending-only'), body = document.getElementById('incidents-table');
  async function load() {
    try {
      const all = await api('/api/incidents');
      const pendingRows = all.incidents.filter(i=>i.status!=='reviewed');
      document.getElementById('incident-open-count').textContent=pendingRows.length;
      document.getElementById('incident-critical-count').textContent=pendingRows.filter(i=>i.severity==='critical').length;
      document.getElementById('incident-reviewed-count').textContent=all.incidents.filter(i=>i.status==='reviewed').length;
      const rows = pending.checked ? pendingRows : all.incidents;
      body.innerHTML=rows.length?rows.map(i=>`<tr><td><a class="incident-code" href="${i.url}">${escapeHTML(i.code)}</a></td><td><b>${escapeHTML(i.product)}</b><small class="cell-sub">${escapeHTML(i.batch)} · ${escapeHTML(i.location)}</small></td><td>${formatTime(i.started_at)}</td><td>${Math.floor(i.duration_seconds/60)}m ${i.duration_seconds%60}s${i.recovered_at?' · recovered':' · active'}</td><td><span class="severity-pill severity-${escapeHTML(i.severity)}">${escapeHTML(i.severity)}</span></td><td><span class="status-pill ${i.status==='reviewed'?'status-reviewed':'status-warning'}">${escapeHTML(i.status.replaceAll('_',' '))}</span></td><td><a class="incident-link" href="${i.url}">Open →</a></td></tr>`).join(''):'<tr><td colspan="7" class="empty-state">No incidents to show. Excursions will appear here when readings cross a configured range.</td></tr>';
    } catch(error){showToast(error.message,'error');}
  }
  pending.addEventListener('change',load);document.getElementById('incidents-refresh').addEventListener('click',load);load();setInterval(load,20000);
})();
