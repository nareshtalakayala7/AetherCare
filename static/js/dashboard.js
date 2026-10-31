(() => {
  let trendChart;
  const stateClass = (status) => status === 'normal' ? 'status-normal' : status === 'warning' ? 'status-warning' : status === 'offline' ? 'status-offline' : 'status-offline';
  const stateLabel = (status) => status === 'normal' ? 'IN RANGE' : status === 'warning' ? 'OUT OF RANGE' : status === 'offline' ? 'OFFLINE' : 'NO DATA';
  async function load() {
    try {
      const data = await api('/api/dashboard');
      Object.entries(data.summary).forEach(([key, value]) => {
        const node = document.querySelector(`[data-metric="${key}"]`); if (node) node.textContent = value;
      });
      const body = document.getElementById('product-monitor-table');
      body.innerHTML = data.products.map((p) => {
        const status = tempStatus(p);
        return `<tr><td><b>${escapeHTML(p.name)}</b><small class="cell-sub">${escapeHTML(p.batch)}</small></td><td>${escapeHTML(p.location)}</td><td><span class="temp-value ${status === 'warning' ? 'outside' : ''}">${p.temperature_c == null ? '—' : `${Number(p.temperature_c).toFixed(1)} °C`}</span></td><td><span class="threshold-copy">${p.minimum_c}° to ${p.maximum_c}°C</span></td><td><span class="status-pill ${stateClass(status)}">${stateLabel(status)}</span></td></tr>`;
      }).join('') || '<tr><td colspan="5" class="empty-state">No active products</td></tr>';
      const alerts = document.getElementById('recent-alerts');
      alerts.innerHTML = data.alerts.length ? data.alerts.slice(0, 5).map((a) => `<div class="compact-alert"><span class="alert-symbol ${a.severity === 'critical' ? 'symbol-critical' : a.severity === 'warning' ? 'symbol-warning' : 'symbol-info'}">${a.severity === 'critical' ? 'ϟ' : a.severity === 'warning' ? '!' : '⌁'}</span><div class="compact-alert-copy"><b>${escapeHTML(a.message)}</b><small>${formatTime(a.created_at)} · ${a.acknowledged_at ? 'Acknowledged' : 'Needs review'}</small></div><span class="severity-pill severity-${escapeHTML(a.severity)}">${escapeHTML(a.severity)}</span></div>`).join('') : '<div class="empty-state">No alerts yet. Monitoring is stable.</div>';
      const timeline = document.getElementById('recent-timeline');
      timeline.innerHTML = data.timeline.length ? data.timeline.map((item) => `<a class="dashboard-event" href="${item.url}"><i class="dashboard-event-dot ${item.event_type.includes('excursion') || item.event_type.includes('escalat') ? 'event-hot' : ''}"></i><div><b>${escapeHTML(item.event_type.replaceAll('_',' '))}<span>${escapeHTML(item.incident_code)}</span></b><p>${escapeHTML(item.description)}</p><small>${formatTime(item.at)} · ${escapeHTML(item.actor)}</small></div><span class="event-arrow">→</span></a>`).join('') : '<div class="empty-state">No incident events have been recorded.</div>';
      const sensorResp = await api('/api/sensors');
      document.getElementById('sensor-health').innerHTML = sensorResp.sensors.map((s) => `<div class="sensor-health-row"><span class="sensor-small-icon">⌖</span><div class="sensor-health-copy"><b>${escapeHTML(s.code)}</b><small>${escapeHTML(s.location)} · ${s.online ? 'Connected' : 'Offline'}</small></div><div class="sensor-battery">${s.battery_pct}%<div class="battery-track"><i style="width:${s.battery_pct}%"></i></div></div></div>`).join('') || '<div class="empty-state">No sensors registered.</div>';
      renderChart(data.readings);
    } catch (error) { showToast(error.message, 'error'); }
  }
  function renderChart(readings) {
    if (!window.Chart || !document.getElementById('trend-chart')) return;
    const labels = readings.map((r) => formatTime(r.at, false));
    const codes = [...new Set(readings.map((r) => r.sensor))];
    const colors = ['#4c7fe0', '#13ae9b', '#8d78d9', '#e5a13a'];
    const datasets = codes.map((code, i) => ({ label: code, data: readings.map((r) => r.sensor === code ? r.temperature : null), borderColor: colors[i % colors.length], backgroundColor: colors[i % colors.length], borderWidth: 2, pointRadius: 2, pointHoverRadius: 4, tension: .35, spanGaps: true }));
    if (trendChart) trendChart.destroy();
    trendChart = new Chart(document.getElementById('trend-chart'), { type: 'line', data: { labels, datasets }, options: { responsive:true, maintainAspectRatio:false, interaction:{intersect:false,mode:'index'}, plugins:{legend:{display:false},tooltip:{backgroundColor:'#183149',padding:10}}, scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,color:'#94a3af',font:{size:9}}},y:{min:0,max:12,grid:{color:'#edf1f4'},ticks:{stepSize:2,color:'#94a3af',font:{size:9}}}} } });
  }
  load(); setInterval(load, 12000);
})();
