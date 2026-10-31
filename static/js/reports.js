(() => {
  let historyChart, incidentChart;
  const from = document.getElementById('report-from'), to = document.getElementById('report-to');
  function query() { const p=new URLSearchParams();if(from.value)p.set('from',from.value);if(to.value)p.set('to',to.value);return p.toString(); }
  async function load() {
    try {
      const qs=query(), suffix=qs?`?${qs}`:'';
      const [summary, readingData, incidentData] = await Promise.all([api(`/api/reports/summary${suffix}`),api(`/api/readings${suffix}`),api(`/api/incidents${suffix}`)]);
      document.getElementById('report-reading-count').textContent=summary.readings;
      document.getElementById('report-incident-count').textContent=summary.incidents;
      document.getElementById('report-alert-count').textContent=summary.alerts;
      document.getElementById('report-uptime').textContent=`${summary.uptime_pct}%`;
      document.getElementById('report-products').innerHTML=summary.products.map(p=>`<tr><td><b>${escapeHTML(p.product)}</b><small class="cell-sub">${escapeHTML(p.batch)}</small></td><td>${escapeHTML(p.location)}</td><td>${p.incidents}</td><td>${p.duration_minutes} min</td><td>${p.ack_minutes==null?'—':`${p.ack_minutes} min`}</td><td><span class="status-pill ${p.online?'status-normal':'status-offline'}">${escapeHTML(p.sensor)} · ${p.online?'online':'offline'}</span></td></tr>`).join('')||'<tr><td colspan="6" class="empty-state">No products found.</td></tr>';
      document.getElementById("report-locations").innerHTML=summary.locations.map(loc=>`<tr><td><b>${escapeHTML(loc.location)}</b></td><td>${escapeHTML(loc.facility)}</td><td>${loc.incidents}</td><td>${loc.duration_minutes} min</td></tr>`).join("")||"<tr><td colspan=\"4\" class=\"empty-state\">No locations found.</td></tr>";
      drawHistory(readingData.readings);
      const counts = new Map();incidentData.incidents.forEach(i=>counts.set(i.product,(counts.get(i.product)||0)+1));
      drawIncidents([...counts.keys()],[...counts.values()]);
      const auditBody=document.getElementById('audit-log');
      if(auditBody){const {logs}=await api('/api/audit');auditBody.innerHTML=logs.length?logs.map(log=>`<tr><td>${formatTime(log.at)}</td><td><b>${escapeHTML(log.actor)}</b></td><td><span class="category-chip">${escapeHTML(log.action.replaceAll('_',' '))}</span></td><td>${escapeHTML(log.entity)} ${escapeHTML(log.entity_id||'')}</td><td>${escapeHTML(log.details||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="empty-state">No audit events recorded.</td></tr>';}
    } catch(error) { showToast(error.message,'error'); }
  }
  function drawHistory(readings){if(!window.Chart)return;const labels=readings.map(r=>formatTime(r.at,false));const codes=[...new Set(readings.map(r=>r.sensor_id))];const colors=['#4e7fe0','#13ae9b','#907ad8'];if(historyChart)historyChart.destroy();historyChart=new Chart(document.getElementById('report-chart'),{type:'line',data:{labels,datasets:codes.map((code,i)=>({label:`Sensor ${code}`,data:readings.map(r=>r.sensor_id===code?r.temperature:null),borderColor:colors[i%colors.length],backgroundColor:colors[i%colors.length],borderWidth:2,tension:.35,pointRadius:2,spanGaps:true}))},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:9},boxWidth:8}}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,font:{size:8},color:'#94a3af'}},y:{grid:{color:'#edf1f4'},ticks:{font:{size:9},color:'#94a3af'}}}}});}
  function drawIncidents(labels,values){if(!window.Chart)return;if(incidentChart)incidentChart.destroy();incidentChart=new Chart(document.getElementById('incident-chart'),{type:'doughnut',data:{labels,datasets:[{data:values,backgroundColor:['#4c7fe0','#16b29f','#9b82d9','#e3a341','#d76a61'],borderWidth:3,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',plugins:{legend:{position:'bottom',labels:{font:{size:9},boxWidth:8,padding:12}},tooltip:{backgroundColor:'#183149'}}}});}
  document.getElementById('apply-report').addEventListener('click',load);document.getElementById('clear-report').addEventListener('click',()=>{from.value='';to.value='';load();});
  document.getElementById('export-report').addEventListener('click',()=>{location.href=`/api/reports.csv${query()?`?${query()}`:''}`;});
  load();
})();


