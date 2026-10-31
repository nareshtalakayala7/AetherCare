(() => {
  const sensorSelect = document.getElementById('sim-sensor');
  const scenarioButtons = [...document.querySelectorAll('.scenario-button')];
  const state = { sensors:[], scenario:'normal', running:false, paused:false, timer:null, chart:null, values:[], tick:0, speed:1 };
  const statusNode = document.getElementById('sim-status');
  const scenarioNames = {normal:'Normal temperature',high:'High excursion',low:'Low excursion',spike:'Sudden spike',prolonged:'Prolonged excursion'};
  const selected = () => state.sensors.find((s) => String(s.id) === sensorSelect.value);
  const product = () => window.simProducts?.find((p) => String(p.sensor_id) === sensorSelect.value);
  function paintSensor() {
    const p = product(), s = selected();
    if (!p || !s) return;
    document.getElementById('sim-product').textContent = p.name;
    document.getElementById('sim-location').textContent = `${p.location} · Batch ${p.batch}`;
    document.getElementById('sim-min').textContent = `${p.minimum_c} °C`;
    document.getElementById('sim-max').textContent = `${p.maximum_c} °C`;
    document.getElementById('sim-range').textContent = `Configured range · ${p.minimum_c}–${p.maximum_c} °C`;
    document.getElementById('sim-sensor-code').textContent = s.code;
    const current = p.temperature_c ?? ((p.minimum_c + p.maximum_c) / 2);
    document.getElementById('sim-temperature').textContent = Number(current).toFixed(1);
    const span = p.maximum_c - p.minimum_c, marker = Math.min(97, Math.max(3, 28 + ((current - p.minimum_c) / span) * 45));
    document.getElementById('meter-marker').style.left = `${marker}%`;
    const offline = !s.online, out = current < p.minimum_c || current > p.maximum_c;
    statusNode.className = `status-pill ${offline ? 'status-offline' : out ? 'status-warning' : 'status-normal'}`;
    statusNode.textContent = offline ? '● OFFLINE' : out ? '● OUT OF RANGE' : '● IN RANGE';
  }
  async function load() {
    try {
      const [sensorData, productData] = await Promise.all([api('/api/sensors'), api('/api/products')]);
      state.sensors = sensorData.sensors.filter((s) => s.product !== 'Unassigned'); window.simProducts = productData.products;
      const previous = sensorSelect.value;
      sensorSelect.innerHTML = state.sensors.map((s) => `<option value="${s.id}">${escapeHTML(s.code)} · ${escapeHTML(s.product)}</option>`).join('');
      if (state.sensors.some((s) => String(s.id) === previous)) sensorSelect.value = previous;
      paintSensor();
      const hist = await api(`/api/readings?sensor_id=${encodeURIComponent(sensorSelect.value)}`);
      state.values = hist.readings.slice(-24).map((r) => r.temperature);
      drawChart();
    } catch (error) { showToast(error.message, 'error'); }
  }
  function targetTemperature() {
    const p = product(); if (!p) return 5;
    const center = (p.minimum_c + p.maximum_c) / 2;
    const drift = Math.sin(state.tick / 2) * .27 + (Math.random() - .5) * .28;
    if (state.scenario === 'high') return p.maximum_c + 1.1 + Math.random() * .9;
    if (state.scenario === 'low') return p.minimum_c - 1.1 - Math.random() * .9;
    if (state.scenario === 'spike') return p.maximum_c + 3.2 + Math.random() * 1.4;
    if (state.scenario === 'prolonged') return p.maximum_c + 1.1 + Math.random() * .4;
    return center + drift;
  }
  async function tick() {
    const s = selected(); if (!s) return;
    if (!s.online) { addFeed('Reading skipped · sensor is disconnected', 'warning'); return; }
    state.tick += 1;
    const temperature = targetTemperature();
    try {
      const result = await api('/api/readings', {method:'POST', body:JSON.stringify({sensor_id:s.id,temperature_c:Number(temperature.toFixed(2)),simulated:true})});
      state.values.push(result.reading.temperature_c); state.values = state.values.slice(-30);
      paintSensor(); drawChart();
      addFeed(`${scenarioNames[state.scenario]} · ${result.reading.temperature_c.toFixed(1)} °C`, result.incident?.severity || 'normal');
      if (result.incident) addFeed(`${result.incident.code} · ${result.incident.severity} incident recorded`, result.incident.severity);
      if (result.incident || result.reading.temperature_c < product().minimum_c || result.reading.temperature_c > product().maximum_c) showToast('Excursion saved and alert sent to the in-app center.', 'error');
    } catch (error) { showToast(error.message, 'error'); stop(); }
  }
  function drawChart() {
    const canvas = document.getElementById('sim-chart'); if (!window.Chart || !canvas) return;
    if (state.chart) state.chart.destroy();
    state.chart = new Chart(canvas, {type:'line',data:{labels:state.values.map((_,i)=>`${state.values.length-i} ticks ago`).reverse(),datasets:[{label:'Temperature °C',data:state.values,borderColor:'#17aa99',backgroundColor:'#17aa9918',fill:true,tension:.35,borderWidth:2,pointRadius:2}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{color:'#edf1f4'},ticks:{font:{size:9},color:'#91a1ae'}}}}});
  }
  function addFeed(message, kind='normal') {
    const list = document.getElementById('sim-feed-list');
    if (list.querySelector('.feed-empty')) list.innerHTML = '';
    const row = document.createElement('div'); row.className='feed-row';
    const severity = kind === 'critical' ? 'critical' : (kind === 'warning' || kind === 'warning') ? 'warning' : '';
    row.innerHTML = `<i class="feed-mark ${severity}"></i><div class="feed-copy"><b>${escapeHTML(message)}</b><small>${formatTime(new Date().toISOString(), false)} · ${escapeHTML(selected()?.code || '')}</small></div>`;
    list.prepend(row); while (list.children.length > 10) list.lastElementChild.remove();
  }
  function setState(text, running=false) { const n=document.getElementById('sim-state');n.textContent=`● ${text}`;n.classList.toggle('running',running); }
  function start() { if (state.running && !state.paused) return; state.running=true;state.paused=false;document.getElementById('sim-start').disabled=true;document.getElementById('sim-pause').disabled=false;document.getElementById('sim-stop').disabled=false;document.getElementById('sim-pause').textContent='Ⅱ  Pause';setState('RUNNING',true);tick();clearInterval(state.timer);state.timer=setInterval(tick,5000/state.speed); }
  function pause() { if (!state.running) return; if (state.paused) { start();return; } clearInterval(state.timer);state.paused=true;document.getElementById('sim-start').disabled=false;document.getElementById('sim-start').textContent='▶  Resume';document.getElementById('sim-pause').textContent='▶  Resume';setState('PAUSED',false); }
  function stop() { clearInterval(state.timer);state.running=false;state.paused=false;document.getElementById('sim-start').disabled=false;document.getElementById('sim-start').textContent='▶  Start simulation';document.getElementById('sim-pause').disabled=true;document.getElementById('sim-pause').textContent='Ⅱ  Pause';document.getElementById('sim-stop').disabled=true;setState('READY',false); }
  async function connection(online) { const s=selected();if(!s)return;try{await api(`/api/sensors/${s.id}/connection`,{method:'POST',body:JSON.stringify({online})});addFeed(`${s.code} ${online?'reconnected':'disconnected'}`,online?'normal':'warning');await load();}catch(error){showToast(error.message,'error');} }
  scenarioButtons.forEach((button)=>button.addEventListener('click',()=>{scenarioButtons.forEach(b=>b.classList.remove('selected'));button.classList.add('selected');state.scenario=button.dataset.scenario;addFeed(`Scenario selected · ${scenarioNames[state.scenario]}`);if(state.running&&!state.paused)tick();}));
  document.getElementById('sim-start').addEventListener('click',start);document.getElementById('sim-pause').addEventListener('click',()=>state.paused?start():pause());document.getElementById('sim-stop').addEventListener('click',stop);
  document.getElementById('sim-speed').addEventListener('input',(e)=>{state.speed=Number(e.target.value);document.getElementById('speed-value').textContent=`${state.speed}×`;if(state.running&&!state.paused){clearInterval(state.timer);state.timer=setInterval(tick,5000/state.speed);}});
  document.getElementById('disconnect-sensor').addEventListener('click',()=>connection(false));document.getElementById('reconnect-sensor').addEventListener('click',()=>connection(true));
  document.getElementById('sim-reset').addEventListener('click',async()=>{state.scenario='normal';scenarioButtons.forEach(b=>b.classList.toggle('selected',b.dataset.scenario==='normal'));stop();try{if(selected()?.online)await tick();addFeed('Simulation reset to normal conditions');await load();}catch(error){showToast(error.message,'error');}});
  sensorSelect.addEventListener('change',()=>{state.values=[];paintSensor();load();});
  load();
})();
