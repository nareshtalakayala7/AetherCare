(() => {
  let chart;
  const filter = document.getElementById('monitor-filter');
  const selectedSensor = document.getElementById('history-sensor');
  async function load() {
    try {
      const { products } = await api('/api/products');
      const selected = filter.value;
      const visible = products.filter((p) => selected === 'all' || tempStatus(p) === selected || (selected === 'warning' && tempStatus(p) === 'warning'));
      document.getElementById('monitoring-grid').innerHTML = visible.map((p) => {
        const status = tempStatus(p), cls = status === 'warning' ? 'outside' : status === 'offline' ? 'offline' : '';
        return `<article class="panel monitor-card ${cls}"><div class="monitor-card-head"><span class="sensor-code">${escapeHTML(p.sensor)}</span><span class="status-pill ${status === 'normal' ? 'status-normal' : status === 'warning' ? 'status-warning' : 'status-offline'}"><i></i>${status === 'normal' ? 'IN RANGE' : status === 'warning' ? 'OUT OF RANGE' : 'OFFLINE'}</span></div><h3>${escapeHTML(p.name)}</h3><div class="batch-line">Batch ${escapeHTML(p.batch)} · ${escapeHTML(p.category)}</div><div class="monitor-temp ${status === 'warning' ? 'outside' : ''}">${p.temperature_c == null ? '—' : Number(p.temperature_c).toFixed(1)}<span class="monitor-unit"> °C</span></div><div class="monitor-threshold">Configured demo range · ${p.minimum_c}° to ${p.maximum_c}°C</div><div class="monitor-meta"><span>${escapeHTML(p.location)}</span><span>Updated <b>${formatTime(p.updated_at, false)}</b></span></div></article>`;
      }).join('') || '<div class="panel empty-state">No products match this filter.</div>';
      const sensors = await api('/api/sensors');
      const prior = selectedSensor.value;
      selectedSensor.innerHTML = sensors.sensors.map((s) => `<option value="${s.id}">${escapeHTML(s.code)} · ${escapeHTML(s.product)}</option>`).join('');
      if (sensors.sensors.some((s) => String(s.id) === prior)) selectedSensor.value = prior;
      await loadHistory();
    } catch (error) { showToast(error.message, 'error'); }
  }
  async function loadHistory() {
    try {
      if (!selectedSensor.value) return;
      const { readings } = await api(`/api/readings?sensor_id=${encodeURIComponent(selectedSensor.value)}`);
      if (!window.Chart) return;
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('history-chart'), {type:'line',data:{labels:readings.map(r=>formatTime(r.at,false)),datasets:[{label:'Temperature °C',data:readings.map(r=>r.temperature),borderColor:'#16aa98',backgroundColor:'#16aa9818',fill:true,tension:.35,borderWidth:2,pointRadius:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,color:'#94a3af',font:{size:9}}},y:{grid:{color:'#edf1f4'},ticks:{color:'#94a3af',font:{size:9}}}}}});
    } catch (error) { showToast(error.message, 'error'); }
  }
  filter.addEventListener('change', load); selectedSensor.addEventListener('change', loadHistory);
  load(); setInterval(load, 5000);
})();
