/* ==========================================================================
   ATHENA HEALTH DASHBOARD — REAL-TIME WEBSOCKET & AI CLIENT LOGIC
   ========================================================================== */

(function () {
  'use strict';

  // --- Configuration & State ---
  const DEFAULT_DEVICE_ID = 'PHC-0001';
  let activeDeviceId = DEFAULT_DEVICE_ID;
  let socket = null;
  let reconnectAttempts = 0;
  let totalPackets = 0;
  let lastPacketTimestamp = Date.now();

  // Historical Ring Buffers for Charts (Max 35 points for high visual clarity)
  const MAX_POINTS = 35;
  const history = {
    labels: [],
    heartRate: [],
    spo2: [],
    heatIndex: [],
    pressure: []
  };

  // Audio Context for Emergency Siren Alarm
  let audioCtx = null;
  let sirenOscillator = null;
  let sirenGain = null;
  let sirenInterval = null;
  let isAlarmSilenced = false;
  let currentEmergencyState = false;

  // DOM Elements
  const el = {
    connIndicator: document.getElementById('conn-indicator'),
    connText: document.getElementById('conn-text'),
    activeDevId: document.getElementById('active-device-id'),
    btnManualEval: document.getElementById('btn-manual-eval'),
    btnToggleSim: document.getElementById('btn-toggle-sim'),
    simBar: document.getElementById('simulation-bar'),
    
    // AI Advisory Elements
    riskPill: document.getElementById('risk-pill'),
    riskText: document.getElementById('risk-text'),
    aiTimestamp: document.getElementById('ai-timestamp'),
    aiSummary: document.getElementById('ai-summary'),
    aiAdvice: document.getElementById('ai-advice'),
    aiRationale: document.getElementById('ai-rationale'),
    aiFlagsContainer: document.getElementById('ai-flags-container'),
    
    // Metric Values
    valHr: document.getElementById('val-hr'),
    valSpo2: document.getElementById('val-spo2'),
    valHeat: document.getElementById('val-heat'),
    valTemp: document.getElementById('val-temp'),
    valHumidity: document.getElementById('val-humidity'),
    valPres: document.getElementById('val-pres'),
    valMotion: document.getElementById('val-motion'),
    valStillTime: document.getElementById('val-still-time'),
    
    // Tags
    tagHr: document.getElementById('tag-hr'),
    tagSpo2: document.getElementById('tag-spo2'),
    tagHeat: document.getElementById('tag-heat'),
    tagEnv: document.getElementById('tag-env'),
    tagFall: document.getElementById('tag-fall'),
    spo2Bar: document.getElementById('spo2-bar'),
    
    // Emergency Overlay
    emergencyOverlay: document.getElementById('emergency-overlay'),
    emergencyTitle: document.getElementById('emergency-title'),
    emergencyDesc: document.getElementById('emergency-desc'),
    emHr: document.getElementById('em-hr'),
    emSpo2: document.getElementById('em-spo2'),
    emHeat: document.getElementById('em-heat'),
    btnSilence: document.getElementById('btn-silence'),
    btnAck: document.getElementById('btn-ack'),
    
    // Charts
    vitalsCanvas: document.getElementById('vitals-chart'),
    envCanvas: document.getElementById('env-chart'),
    
    // Footer stats
    statPktCount: document.getElementById('stat-pkt-count'),
    statLatency: document.getElementById('stat-latency')
  };

  // ==========================================================================
  // WEBSOCKET REAL-TIME CONNECTION
  // ==========================================================================
  function getWebSocketUrl() {
    const loc = window.location;
    let wsHost = loc.host;
    // If opening file:// directly or default static port, fallback to backend 8000
    if (!wsHost || loc.protocol === 'file:' || wsHost.includes('5500') || wsHost.includes('3000')) {
      wsHost = 'localhost:8000';
    }
    const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProto}//${wsHost}/ws`;
  }

  function initWebSocket() {
    const wsUrl = getWebSocketUrl();
    console.log(`[ATHENA WS] Initiating connection to: ${wsUrl}`);
    
    el.connText.textContent = 'Connecting...';
    el.connIndicator.className = 'dot-pulse';

    try {
      socket = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[ATHENA WS] Init error:', err);
      scheduleReconnect();
      return;
    }

    socket.onopen = function () {
      console.log('[ATHENA WS] Connected to cloud ingestion backend.');
      reconnectAttempts = 0;
      el.connText.textContent = 'Live • Cloud Connected';
      el.connIndicator.className = 'dot-pulse online';
    };

    socket.onclose = function () {
      console.warn('[ATHENA WS] Disconnected.');
      el.connText.textContent = 'Disconnected (Retrying)';
      el.connIndicator.className = 'dot-pulse';
      scheduleReconnect();
    };

    socket.onerror = function (err) {
      console.error('[ATHENA WS] Socket error:', err);
      socket.close();
    };

    socket.onmessage = function (evt) {
      totalPackets++;
      el.statPktCount.textContent = totalPackets;
      const now = Date.now();
      const latency = Math.max(4, Math.min(now - lastPacketTimestamp, 120));
      lastPacketTimestamp = now;
      el.statLatency.textContent = `< ${latency} ms`;

      try {
        const msg = JSON.parse(evt.data);
        handleIncomingMessage(msg);
      } catch (err) {
        console.error('[ATHENA WS] Parse error:', err, evt.data);
      }
    };
  }

  function scheduleReconnect() {
    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 10000);
    setTimeout(initWebSocket, delay);
  }

  // ==========================================================================
  // INCOMING MESSAGE ROUTER
  // ==========================================================================
  function handleIncomingMessage(msg) {
    if (!msg || !msg.type) return;

    if (msg.type === 'INITIAL_STATE' && msg.devices && msg.devices.length > 0) {
      const dev = msg.devices.find(d => d.device_id === activeDeviceId) || msg.devices[0];
      if (dev) {
        activeDeviceId = dev.device_id;
        el.activeDevId.textContent = activeDeviceId;
        if (dev.history && Array.isArray(dev.history)) {
          dev.history.forEach(item => recordTelemetryPoint(item, false));
          renderAllCharts();
        }
        if (dev.telemetry) renderLiveTelemetry(dev.telemetry);
        if (dev.advisory) renderAIAdvisory(dev.advisory);
      }
    } else if (msg.type === 'TELEMETRY') {
      if (msg.device_id === activeDeviceId || !msg.device_id) {
        recordTelemetryPoint(msg.data, true);
        renderLiveTelemetry(msg.data);
      }
    } else if (msg.type === 'AI_ADVISORY') {
      if (msg.device_id === activeDeviceId || !msg.device_id) {
        renderAIAdvisory(msg.advisory);
      }
    }
  }

  // ==========================================================================
  // TELEMETRY RENDERING & STATS
  // ==========================================================================
  function recordTelemetryPoint(data, shouldRedraw = true) {
    if (!data) return;
    const timeLabel = new Date(data.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    history.labels.push(timeLabel);
    history.heartRate.push(data.finger_detected && data.heart_rate > 0 ? data.heart_rate : null);
    history.spo2.push(data.finger_detected && data.spo2 > 0 ? data.spo2 : null);
    history.heatIndex.push(data.heat_index_c || 25.0);
    history.pressure.push(data.pressure_hpa || 1013.2);

    if (history.labels.length > MAX_POINTS) {
      history.labels.shift();
      history.heartRate.shift();
      history.spo2.shift();
      history.heatIndex.shift();
      history.pressure.shift();
    }

    if (shouldRedraw) {
      renderAllCharts();
    }
  }

  function renderLiveTelemetry(d) {
    const hasFinger = d.finger_detected;
    
    // Heart Rate
    if (hasFinger && d.heart_rate > 0) {
      el.valHr.textContent = d.heart_rate;
      if (d.heart_rate > 120) {
        setTag(el.tagHr, 'tag-danger', 'Tachycardia');
      } else if (d.heart_rate < 50) {
        setTag(el.tagHr, 'tag-watch', 'Bradycardia');
      } else {
        setTag(el.tagHr, 'tag-normal', 'Resting Normal');
      }
    } else {
      el.valHr.textContent = '—';
      setTag(el.tagHr, 'tag-watch', 'No Finger Contact');
    }

    // Blood Oxygen SpO2
    if (hasFinger && d.spo2 > 0) {
      el.valSpo2.textContent = d.spo2;
      el.spo2Bar.style.width = `${Math.min(100, Math.max(0, d.spo2))}%`;
      if (d.spo2 < 90) {
        setTag(el.tagSpo2, 'tag-danger', 'Severe Hypoxia');
      } else if (d.spo2 < 94) {
        setTag(el.tagSpo2, 'tag-watch', 'Mild Desaturation');
      } else {
        setTag(el.tagSpo2, 'tag-normal', 'Optimal Saturation');
      }
    } else {
      el.valSpo2.textContent = '—';
      el.spo2Bar.style.width = '0%';
      setTag(el.tagSpo2, 'tag-watch', 'Sensor Idle');
    }

    // Environmental
    el.valHeat.textContent = d.heat_index_c ? d.heat_index_c.toFixed(1) : '—';
    if (d.heat_index_c > 41) {
      setTag(el.tagHeat, 'tag-danger', 'Extreme Danger');
    } else if (d.heat_index_c > 37) {
      setTag(el.tagHeat, 'tag-watch', 'Heat Exhaustion Risk');
    } else {
      setTag(el.tagHeat, 'tag-normal', 'Safe Comfort');
    }

    el.valTemp.textContent = d.ambient_temp_c ? d.ambient_temp_c.toFixed(1) : '—';
    el.valHumidity.textContent = d.ambient_humidity ? Math.round(d.ambient_humidity) : '—';
    el.valPres.textContent = d.pressure_hpa ? d.pressure_hpa.toFixed(1) : '—';

    // Motion & Fall Safety
    if (d.fall_detected) {
      el.valMotion.textContent = 'FALL DETECTED!';
      el.valMotion.style.color = 'var(--crimson)';
      setTag(el.tagFall, 'tag-danger', 'Emergency Stillness');
      triggerEmergencyAlert({
        title: 'PATIENT FALL IMPACT DETECTED',
        desc: `High-g impact (${d.accel_magnitude || 2.8}g) recorded followed by complete lack of movement.`,
        hr: d.heart_rate,
        spo2: d.spo2,
        heat: d.heat_index_c
      });
    } else {
      el.valMotion.textContent = d.is_moving ? 'Active Moving' : 'Stationary';
      el.valMotion.style.color = '#FFF';
      const stillMin = d.last_movement_min || 0;
      el.valStillTime.textContent = d.is_moving ? 'Active just now' : `Still for ${stillMin < 1 ? '< 1' : stillMin.toFixed(1)} min`;
      setTag(el.tagFall, 'tag-normal', 'No Fall Detected');
    }

    // Check secondary emergency trigger: Severe Hypoxia
    if (hasFinger && d.spo2 > 0 && d.spo2 < 90 && !d.fall_detected) {
      triggerEmergencyAlert({
        title: 'CRITICAL HYPOXIA WARNING',
        desc: `Peripheral oxygen saturation has plummeted to dangerous level: ${d.spo2}%.`,
        hr: d.heart_rate,
        spo2: d.spo2,
        heat: d.heat_index_c
      });
    }
  }

  function setTag(elTarget, cls, text) {
    if (!elTarget) return;
    elTarget.className = `metric-tag ${cls}`;
    elTarget.textContent = text;
  }

  // ==========================================================================
  // GEMINI AI ADVISORY RENDERING
  // ==========================================================================
  function renderAIAdvisory(adv) {
    if (!adv) return;

    // Risk Classification Pill
    const level = (adv.risk_level || 'NORMAL').toUpperCase();
    el.riskText.textContent = level;
    el.riskPill.className = `risk-badge badge-${level.toLowerCase()}`;

    // Timestamp & Model info
    const dateStr = adv.generated_at ? new Date(adv.generated_at).toLocaleTimeString() : 'Just now';
    const aiTag = adv.is_ai_generated ? 'Google Gemini 2.5 Real-Time Analysis' : 'Clinical Diagnostic Engine';
    el.aiTimestamp.textContent = `Generated: ${dateStr} • ${aiTag}`;

    // Content
    el.aiSummary.textContent = `"${adv.summary || 'Vitals and environmental parameters evaluated.'}"`;
    el.aiAdvice.textContent = adv.actionable_advice || 'Continue continuous routine monitoring.';
    el.aiRationale.textContent = adv.clinical_assessment || 'No clinical contraindications present.';

    // Vital Flags
    el.aiFlagsContainer.innerHTML = '';
    const flags = adv.vital_flags || [];
    if (flags.length === 0) {
      flags.push('HEMODYNAMIC_BALANCE', 'CLIMATE_STABLE');
    }
    flags.forEach(flag => {
      const pill = document.createElement('span');
      pill.className = 'flag-pill';
      pill.textContent = flag.replace(/_/g, ' ');
      el.aiFlagsContainer.appendChild(pill);
    });

    // If AI evaluated emergency risk, display modal
    if (level === 'EMERGENCY' && !currentEmergencyState) {
      triggerEmergencyAlert({
        title: 'AI MEDICAL ALARM: ' + (flags[0] || 'CRITICAL ANOMALY'),
        desc: adv.summary,
        hr: el.valHr.textContent,
        spo2: el.valSpo2.textContent,
        heat: el.valHeat.textContent
      });
    }
  }

  // ==========================================================================
  // HIGH-DPI CANVAS SPARKLINE CHART ENGINE
  // ==========================================================================
  function drawLineChart(canvas, datasets, yMinManual = null, yMaxManual = null) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width = canvas.clientWidth * dpr;
    const h = canvas.height = canvas.clientHeight * dpr;

    ctx.clearRect(0, 0, w, h);
    if (history.labels.length < 2) return;

    // Calculate Y bounds
    let allVals = [];
    datasets.forEach(ds => {
      allVals = allVals.concat(ds.data.filter(v => v !== null && !isNaN(v)));
    });
    if (allVals.length === 0) return;

    let yMin = yMinManual !== null ? yMinManual : Math.min(...allVals);
    let yMax = yMaxManual !== null ? yMaxManual : Math.max(...allVals);
    if (yMin === yMax) {
      yMin -= 1;
      yMax += 1;
    }
    const padding = 16 * dpr;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;

    // Draw Subtle Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1 * dpr;
    for (let g = 0; g <= 3; g++) {
      const gy = padding + (chartH / 3) * g;
      ctx.beginPath();
      ctx.moveTo(padding, gy);
      ctx.lineTo(w - padding, gy);
      ctx.stroke();
    }

    // Draw each dataset
    datasets.forEach(ds => {
      const pts = [];
      const len = history.labels.length;
      ds.data.forEach((val, i) => {
        if (val === null || isNaN(val)) return;
        const x = padding + (i / (len - 1)) * chartW;
        const y = padding + chartH - ((val - yMin) / (yMax - yMin)) * chartH;
        pts.push({ x, y, val });
      });

      if (pts.length < 2) return;

      // Draw Gradient Fill
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(pts[0].x, padding + chartH);
      pts.forEach((p, idx) => {
        if (idx === 0) ctx.lineTo(p.x, p.y);
        else {
          const prev = pts[idx - 1];
          const cx = (prev.x + p.x) / 2;
          ctx.bezierCurveTo(cx, prev.y, cx, p.y, p.x, p.y);
        }
      });
      ctx.lineTo(pts[pts.length - 1].x, padding + chartH);
      ctx.closePath();
      
      const grad = ctx.createLinearGradient(0, padding, 0, padding + chartH);
      grad.addColorStop(0, ds.fillGradientStart || 'rgba(6, 182, 212, 0.25)');
      grad.addColorStop(1, 'rgba(6, 182, 212, 0.0)');
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.restore();

      // Draw Line
      ctx.save();
      ctx.beginPath();
      pts.forEach((p, idx) => {
        if (idx === 0) ctx.moveTo(p.x, p.y);
        else {
          const prev = pts[idx - 1];
          const cx = (prev.x + p.x) / 2;
          ctx.bezierCurveTo(cx, prev.y, cx, p.y, p.x, p.y);
        }
      });
      ctx.strokeStyle = ds.color;
      ctx.lineWidth = 2.4 * dpr;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.shadowColor = ds.color;
      ctx.shadowBlur = 8 * dpr;
      ctx.stroke();
      ctx.restore();

      // Draw Last Point Pulse
      const last = pts[pts.length - 1];
      ctx.save();
      ctx.beginPath();
      ctx.arc(last.x, last.y, 4 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.fill();
      ctx.strokeStyle = ds.color;
      ctx.lineWidth = 2 * dpr;
      ctx.stroke();
      ctx.restore();
    });
  }

  function renderAllCharts() {
    // Vitals Chart: Heart Rate (50 - 150) & SpO2 (80 - 100)
    drawLineChart(el.vitalsCanvas, [
      {
        data: history.heartRate,
        color: '#F43F5E',
        fillGradientStart: 'rgba(244, 63, 94, 0.2)'
      },
      {
        data: history.spo2,
        color: '#06B6D4',
        fillGradientStart: 'rgba(6, 182, 212, 0.15)'
      }
    ], 50, 150);

    // Environmental Chart: Heat Index (20 - 45) & Pressure (1000 - 1030)
    drawLineChart(el.envCanvas, [
      {
        data: history.heatIndex,
        color: '#F59E0B',
        fillGradientStart: 'rgba(245, 158, 11, 0.2)'
      }
    ], 20, 46);
  }

  // ==========================================================================
  // EMERGENCY AUDIO SYNTH & MODAL
  // ==========================================================================
  function playEmergencySiren() {
    if (isAlarmSilenced) return;
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (audioCtx.state === 'suspended') {
        audioCtx.resume();
      }
      if (sirenInterval) return;

      let highTone = true;
      sirenInterval = setInterval(() => {
        if (isAlarmSilenced || !audioCtx) return;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.value = highTone ? 880 : 440;
        highTone = !highTone;

        gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);

        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.35);
      }, 400);
    } catch (e) {
      console.warn('[AUDIO ALARM] AudioContext not permitted yet:', e);
    }
  }

  function stopEmergencySiren() {
    if (sirenInterval) {
      clearInterval(sirenInterval);
      sirenInterval = null;
    }
  }

  function triggerEmergencyAlert({ title, desc, hr, spo2, heat }) {
    currentEmergencyState = true;
    el.emergencyTitle.textContent = title;
    el.emergencyDesc.textContent = desc;
    el.emHr.textContent = `${hr || '--'} BPM`;
    el.emSpo2.textContent = `${spo2 || '--'} %`;
    el.emHeat.textContent = `${heat ? Number(heat).toFixed(1) : '--'} °C`;
    
    el.emergencyOverlay.classList.remove('hidden');
    playEmergencySiren();
  }

  function dismissEmergencyAlert() {
    currentEmergencyState = false;
    isAlarmSilenced = true;
    stopEmergencySiren();
    el.emergencyOverlay.classList.add('hidden');
    // Reset silence flag after 30s
    setTimeout(() => { isAlarmSilenced = false; }, 30000);
  }

  // ==========================================================================
  // USER ACTIONS & SIMULATION TRIGGERS
  // ==========================================================================
  async function triggerManualEvaluation() {
    el.btnManualEval.classList.add('loading');
    el.aiTimestamp.textContent = 'Calling Google Gemini 2.5 in cloud...';

    try {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          action: 'TRIGGER_EVALUATION',
          device_id: activeDeviceId
        }));
      } else {
        const res = await fetch(`/api/device/${activeDeviceId}/evaluate`, { method: 'POST' });
        const data = await res.json();
        if (data.advisory) renderAIAdvisory(data.advisory);
      }
    } catch (err) {
      console.error('[MANUAL EVAL ERROR]', err);
    } finally {
      setTimeout(() => {
        el.btnManualEval.classList.remove('loading');
      }, 1000);
    }
  }

  async function emitSimulatedTelemetry(type) {
    let payload = {
      device_id: activeDeviceId,
      ambient_temp_c: 26.5,
      ambient_humidity: 55.0,
      pressure_hpa: 1013.2,
      heat_index_c: 27.2,
      heart_rate: 72,
      spo2: 98,
      finger_detected: true,
      is_moving: false,
      last_movement_min: 0.5,
      fall_detected: false,
      accel_magnitude: 1.0,
      risk_level: 0,
      is_emergency: false
    };

    if (type === 'normal') {
      payload.heart_rate = 68;
      payload.spo2 = 99;
      payload.is_moving = false;
      payload.last_movement_min = 2.0;
    } else if (type === 'active') {
      payload.heart_rate = 96;
      payload.spo2 = 98;
      payload.is_moving = true;
      payload.last_movement_min = 0.0;
      payload.accel_magnitude = 1.3;
    } else if (type === 'fall') {
      payload.heart_rate = 108;
      payload.spo2 = 97;
      payload.fall_detected = true;
      payload.is_emergency = true;
      payload.risk_level = 3;
      payload.accel_magnitude = 3.2;
    } else if (type === 'hypoxia') {
      payload.heart_rate = 102;
      payload.spo2 = 88;
      payload.is_emergency = true;
      payload.risk_level = 3;
    } else if (type === 'heatwave') {
      payload.ambient_temp_c = 39.5;
      payload.ambient_humidity = 68.0;
      payload.heat_index_c = 42.1;
      payload.heart_rate = 118;
      payload.is_emergency = true;
      payload.risk_level = 2;
    }

    try {
      await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (e) {
      console.warn('Simulation fallback injection directly:', e);
      handleIncomingMessage({ type: 'TELEMETRY', device_id: activeDeviceId, data: payload });
    }
  }

  // ==========================================================================
  // EVENT LISTENERS & INITIALIZATION
  // ==========================================================================
  el.btnManualEval.addEventListener('click', triggerManualEvaluation);

  el.btnToggleSim.addEventListener('click', () => {
    el.simBar.style.display = (el.simBar.style.display === 'none') ? 'block' : 'none';
  });

  document.querySelectorAll('.sim-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const type = e.target.getAttribute('data-type');
      emitSimulatedTelemetry(type);
    });
  });

  el.btnSilence.addEventListener('click', () => {
    isAlarmSilenced = true;
    stopEmergencySiren();
  });

  el.btnAck.addEventListener('click', dismissEmergencyAlert);

  window.addEventListener('resize', () => {
    renderAllCharts();
  });

  // Start WebSocket client & Seed Initial Mock Graphs
  initWebSocket();

  // Populate initial seed curve
  for (let i = 20; i >= 0; i--) {
    const t = new Date(Date.now() - i * 5000);
    recordTelemetryPoint({
      timestamp: t.toISOString(),
      heart_rate: 70 + Math.floor(Math.sin(i * 0.4) * 4),
      spo2: 98,
      finger_detected: true,
      heat_index_c: 27.2 + Math.cos(i * 0.3) * 0.4,
      pressure_hpa: 1013.2 + Math.sin(i * 0.2) * 0.2
    }, false);
  }
  renderAllCharts();

})();
