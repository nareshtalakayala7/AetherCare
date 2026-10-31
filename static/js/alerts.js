(() => {
  let allAlerts = [], filter = 'all';
  const canAct = ['Admin','Healthcare Staff'].includes(document.body.dataset.role);
  const table = document.getElementById('alerts-table');
  function render() {
    const visible = allAlerts.filter((a) => filter === 'all' || (filter === 'unread' && !a.acknowledged_at) || (filter === 'critical' && a.severity === 'critical'));
    document.getElementById('alert-count-all').textContent = allAlerts.length;
    document.getElementById('alert-count-unread').textContent = allAlerts.filter(a => !a.acknowledged_at).length;
    document.getElementById('alert-count-critical').textContent = allAlerts.filter(a => a.severity === 'critical').length;
    table.innerHTML = visible.length ? visible.map((a) => `<tr><td><div class="alert-event"><span class="alert-symbol ${a.severity==='critical'?'symbol-critical':a.severity==='warning'?'symbol-warning':'symbol-info'}">${a.severity==='critical'?'ϟ':a.severity==='warning'?'!':'⌁'}</span><div><b>${escapeHTML(a.message)}</b><small>${a.incident_code ? `Incident ${escapeHTML(a.incident_code)}` : `Sensor ${escapeHTML(a.sensor || '—')}`}</small></div></div></td><td><span class="severity-pill severity-${escapeHTML(a.severity)}">${escapeHTML(a.type.replaceAll('_',' '))}</span></td><td>${formatTime(a.created_at)}</td><td><span class="status-pill ${a.acknowledged_at?'status-reviewed':'status-warning'}"><i></i>${a.acknowledged_at?'ACKNOWLEDGED':'NEEDS REVIEW'}</span></td><td>${a.incident_url?`<a class="table-action" href="${a.incident_url}">View incident</a>`:''} ${canAct && !a.acknowledged_at?`<button class="table-action ack-alert" data-id="${a.id}">Acknowledge</button>`:''}</td></tr>`).join('') : '<tr><td colspan="5" class="empty-state">No alerts in this view.</td></tr>';
    table.querySelectorAll('.ack-alert').forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true;
      try { await api(`/api/alerts/${button.dataset.id}/acknowledge`, {method:'POST',body:'{}'}); showToast('Alert acknowledged.', 'success'); await load(); }
      catch (error) { button.disabled=false; showToast(error.message,'error'); }
    }));
  }
  async function load() { try { allAlerts=(await api('/api/alerts')).alerts;render(); } catch(error) { showToast(error.message,'error'); } }
  document.querySelectorAll('[data-alert-filter]').forEach((button)=>button.addEventListener('click',()=>{filter=button.dataset.alertFilter;document.querySelectorAll('[data-alert-filter]').forEach(b=>b.classList.toggle('selected',b===button));render();}));
  document.getElementById('alerts-refresh').addEventListener('click',load);
  load();setInterval(load,8000);
})();
