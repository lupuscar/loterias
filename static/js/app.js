/**
 * PRIMITIVA ANALYTICS - Client Application Logic
 */

let appState = {
  activeTab: 'pronosticos',
  ultimoSorteo: null,
  statsData: null,
  selectedPosition: 1,
  chartInstance: null,
  historicoPage: 1,
  historicoSearchTimeout: null,
  nuevoSorteoNums: new Set()
};

// ==========================================
// INICIALIZACIÓN
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  cargarHeroUltimoSorteo();
  generarPronosticos();
  initNumberPicker();
  setDefaultFechaNuevoSorteo();
});

function switchTab(tabId) {
  appState.activeTab = tabId;

  // Actualizar botones de navegación
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(`btn-tab-${tabId}`);
  if (activeBtn) activeBtn.classList.add('active');

  // Alternar vistas
  document.querySelectorAll('.tab-view').forEach(view => view.style.display = 'none');
  const activeView = document.getElementById(`view-${tabId}`);
  if (activeView) activeView.style.display = 'block';

  // Carga bajo demanda
  if (tabId === 'analisis') {
    cargarEstadisticasDiferencias();
  } else if (tabId === 'historico') {
    cargarHistorico(1);
  }
}

// ==========================================
// HERO: ÚLTIMO SORTEO
// ==========================================
async function cargarHeroUltimoSorteo() {
  try {
    const res = await fetch('/api/sorteos/ultimo');
    if (!res.ok) throw new Error('No se pudo cargar el último sorteo');
    const sorteo = await res.json();
    appState.ultimoSorteo = sorteo;

    document.getElementById('hero-fecha').textContent = formatearFecha(sorteo.fecha);
    document.getElementById('hero-bote').textContent = sorteo.bote ? formatEuros(sorteo.bote) : 'Sin bote asignado';

    const nums = [sorteo.n1, sorteo.n2, sorteo.n3, sorteo.n4, sorteo.n5, sorteo.n6];
    let html = nums.map(n => `<div class="ball ball-normal ball-lg">${padZero(n)}</div>`).join('');

    if (sorteo.complementario) {
      html += `
        <div class="ball-container" style="margin-left: 10px;">
          <div class="ball ball-comp">${padZero(sorteo.complementario)}</div>
          <span class="ball-badge">Comp</span>
        </div>`;
    }

    if (sorteo.reintegro !== null && sorteo.reintegro !== undefined) {
      html += `
        <div class="ball-container">
          <div class="ball ball-reint">${sorteo.reintegro}</div>
          <span class="ball-badge">Reint</span>
        </div>`;
    }

    document.getElementById('hero-balls').innerHTML = html;
  } catch (err) {
    console.error(err);
    document.getElementById('hero-fecha').textContent = 'Error al conectar con la base de datos';
  }
}

// ==========================================
// TAB 1: PRONÓSTICOS INTELIGENTES
// ==========================================
async function generarPronosticos() {
  const btn = document.getElementById('btn-generar-pronosticos');
  const container = document.getElementById('predictions-container');

  const strategy = document.getElementById('select-strategy').value;
  const windowVal = document.getElementById('select-window').value;
  const count = document.getElementById('input-count').value;

  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Calculando diferencias...';
  container.innerHTML = `
    <div style="text-align: center; color: var(--text-secondary); grid-column: 1/-1; padding: 40px;">
      <div style="font-size: 2rem; margin-bottom: 12px; animation: pulse 1s infinite;">🎱</div>
      Analizando distribuciones estadísticas y generando combinaciones...
    </div>`;

  try {
    const res = await fetch(`/api/pronosticos?strategy=${strategy}&window=${windowVal}&count=${count}`);
    if (!res.ok) throw new Error('Error al generar los pronósticos');
    const data = await res.json();

    renderPronosticos(data.pronosticos);
  } catch (err) {
    showToast('Error al generar pronósticos: ' + err.message, 'error');
    container.innerHTML = `<div style="text-align: center; color: var(--accent-rose); grid-column: 1/-1; padding: 30px;">Error al calcular los pronósticos.</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>🔮</span> Generar Pronósticos';
  }
}

function renderPronosticos(forecasts) {
  const container = document.getElementById('predictions-container');
  if (!forecasts || forecasts.length === 0) {
    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); grid-column: 1/-1;">No se pudieron generar combinaciones.</div>';
    return;
  }

  container.innerHTML = forecasts.map((f, idx) => {
    const ballsHtml = f.combination.map(n => `<div class="ball ball-normal">${padZero(n)}</div>`).join('');
    const tagClass = `tag-${f.tag || 'media'}`;

    const diffBadges = f.applied_diffs.map(d => {
      let cls = 'diff-zero';
      let sign = '';
      if (d > 0) { cls = 'diff-positive'; sign = '+'; }
      else if (d < 0) { cls = 'diff-negative'; }
      return `<span class="diff-badge ${cls}">${sign}${d}</span>`;
    }).join('');

    return `
      <div class="pred-card">
        <div>
          <div class="pred-header">
            <div>
              <div class="pred-title">Apuesta #${idx + 1}: ${f.name}</div>
              <div class="pred-desc">${f.description}</div>
            </div>
            <span class="pred-tag ${tagClass}">${f.tag || 'PRONÓSTICO'}</span>
          </div>

          <div class="pred-balls">
            ${ballsHtml}
          </div>
        </div>

        <div>
          <div class="pred-diff-row">
            <span>Saltos aplicados:</span>
            <div class="diff-badges-group">${diffBadges}</div>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px;">
            <span style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted); font-weight: 700;">
              ${f.combination_str}
            </span>
            <button class="btn-secondary" style="padding: 6px 12px; font-size: 0.8rem;" onclick="copiarCombinacion('${f.combination_str}', this)">
              📋 Copiar
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function copiarCombinacion(combStr, btn) {
  navigator.clipboard.writeText(combStr).then(() => {
    const originalText = btn.innerHTML;
    btn.innerHTML = '✓ Copiado';
    btn.style.borderColor = 'var(--accent-emerald)';
    btn.style.color = 'var(--accent-emerald)';
    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.style.borderColor = '';
      btn.style.color = '';
    }, 2000);
    showToast('Combinación copiada al portapapeles: ' + combStr, 'success');
  });
}

// Backtesting
async function ejecutarBacktest() {
  const btn = document.getElementById('btn-run-backtest');
  const resultsDiv = document.getElementById('backtest-results-container');
  const strategy = document.getElementById('select-strategy').value;
  const windowVal = document.getElementById('select-window').value;
  const evalsVal = document.getElementById('select-bt-evals') ? document.getElementById('select-bt-evals').value : 250;
  const betsVal = document.getElementById('select-bt-bets') ? document.getElementById('select-bt-bets').value : 1;

  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Simulando sorteos...';

  try {
    const winParam = windowVal > 0 ? windowVal : 100;
    const stratParam = strategy === 'all' ? 'reversion' : strategy;
    const res = await fetch(`/api/pronosticos/backtesting?strategy=${stratParam}&window_size=${winParam}&max_evals=${evalsVal}&bets_per_draw=${betsVal}`);
    if (!res.ok) throw new Error('Error al ejecutar backtest');
    const data = await res.json();

    // Actualizar banner resumen
    if (document.getElementById('bt-summary-text')) {
      document.getElementById('bt-summary-text').textContent = 
        `Sorteos con al menos 1 premio (≥ 3 aciertos): ${data.pct_sorteos_con_premio}% (${data.sorteos_con_premio} de ${data.total_evaluados} sorteos)`;
    }
    if (document.getElementById('bt-total-tickets-text')) {
      document.getElementById('bt-total-tickets-text').textContent = 
        `Total apuestas analizadas: ${data.total_boletos_jugados.toLocaleString()} (${data.boletos_por_sorteo} boletos/sorteo)`;
    }

    document.getElementById('bt-hits-3').textContent = data.aciertos['3_aciertos'];
    document.getElementById('bt-pct-3').textContent = `${data.porcentajes['3_aciertos']}%`;

    document.getElementById('bt-hits-4').textContent = data.aciertos['4_aciertos'];
    document.getElementById('bt-pct-4').textContent = `${data.porcentajes['4_aciertos']}%`;

    document.getElementById('bt-hits-5').textContent = data.aciertos['5_aciertos'];
    document.getElementById('bt-pct-5').textContent = `${data.porcentajes['5_aciertos']}%`;

    document.getElementById('bt-hits-6').textContent = data.aciertos['6_aciertos'];
    document.getElementById('bt-pct-6').textContent = `${data.porcentajes['6_aciertos']}%`;

    document.getElementById('bt-total-evals').textContent = data.total_evaluados;

    // Tabla de muestras
    const tbody = document.getElementById('bt-samples-body');
    tbody.innerHTML = data.muestras.slice(0, 15).map(s => `
      <tr>
        <td>${s.fecha.substring(0, 10)}</td>
        <td><strong style="color:var(--text-primary);">${s.real}</strong></td>
        <td>
          <span style="color:var(--text-secondary); font-family:var(--font-mono); font-size:0.85rem;">${s.pronostico}</span>
          <div style="font-size:0.75rem; color:var(--text-muted);">${s.estrategia}</div>
        </td>
        <td>
          <span class="diff-badge ${s.aciertos >= 3 ? 'diff-positive' : 'diff-zero'}">
            ${s.aciertos} aciertos
          </span>
        </td>
      </tr>
    `).join('');

    resultsDiv.style.display = 'block';
    showToast(`Backtest completado: ${data.total_evaluados} sorteos simulados con ${data.boletos_por_sorteo} pronóstico(s) por sorteo`, 'success');
  } catch (err) {
    showToast('Error en simulación: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>▶</span> Ejecutar Simulación';
  }
}

// ==========================================
// TAB 2: ANÁLISIS DIFERENCIAL
// ==========================================
async function cargarEstadisticasDiferencias() {
  const windowVal = document.getElementById('select-stats-window').value;

  try {
    const res = await fetch(`/api/estadisticas/diferencias?window=${windowVal}`);
    if (!res.ok) throw new Error('Error al cargar estadísticas');
    const data = await res.json();
    appState.statsData = data;

    renderPosStatCards(data.positions);
    selectPosicion(appState.selectedPosition || 1);
    cargarRecientesDiferencias();
  } catch (err) {
    showToast('Error cargando estadísticas: ' + err.message, 'error');
  }
}

function renderPosStatCards(positions) {
  const container = document.getElementById('pos-stat-cards');
  container.innerHTML = positions.map(p => `
    <div class="pos-stat-card ${p.position === appState.selectedPosition ? 'active' : ''}" onclick="selectPosicion(${p.position})">
      <div class="pos-num">Posición ${p.position}</div>
      <div class="pos-mean">${p.mean >= 0 ? '+' : ''}${p.mean}</div>
      <div class="pos-sub">Salto típico: ±${p.abs_mean}</div>
      <div class="pos-sub" style="color:var(--accent-gold); margin-top:2px;">Moda: ${p.mode >= 0 ? '+' : ''}${p.mode} (${p.mode_pct}%)</div>
    </div>
  `).join('');
}

function selectPosicion(pos) {
  appState.selectedPosition = pos;

  // Actualizar tarjetas activas
  document.querySelectorAll('.pos-stat-card').forEach((card, idx) => {
    if (idx + 1 === pos) card.classList.add('active');
    else card.classList.remove('active');
  });

  if (!appState.statsData || !appState.statsData.positions) return;
  const p = appState.statsData.positions.find(item => item.position === pos);
  if (!p) return;

  // Renderizar detalle
  document.getElementById('chart-title').textContent = `Histograma de Saltos Frecuentes - Posición ${p.position}`;
  document.getElementById('pos-metrics-detail').innerHTML = `
    <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
      <span style="color:var(--text-secondary);">Media Aritmética Diferencial:</span>
      <strong style="color:var(--text-primary); font-family:var(--font-mono);">${p.mean >= 0 ? '+' : ''}${p.mean}</strong>
    </div>
    <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
      <span style="color:var(--text-secondary);">Magnitud Media de Salto (|d|):</span>
      <strong style="color:var(--accent-blue); font-family:var(--font-mono);">${p.abs_mean} números</strong>
    </div>
    <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
      <span style="color:var(--text-secondary);">Salto más frecuente (Moda):</span>
      <strong style="color:var(--accent-gold); font-family:var(--font-mono);">${p.mode >= 0 ? '+' : ''}${p.mode} (ocurre en el ${p.mode_pct}%)</strong>
    </div>
    <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
      <span style="color:var(--text-secondary);">Desviación Estándar (σ):</span>
      <strong style="color:var(--text-primary); font-family:var(--font-mono);">±${p.std_dev}</strong>
    </div>
    <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:8px;">
      <span style="color:var(--text-secondary);">Centro Teórico Esperado:</span>
      <strong style="color:var(--accent-emerald); font-family:var(--font-mono);">${p.theoretical_mean}</strong>
    </div>
    <div style="display:flex; justify-content:space-between;">
      <span style="color:var(--text-secondary);">Rango histórico de saltos:</span>
      <strong style="color:var(--text-muted); font-family:var(--font-mono);">${p.min} a ${p.max}</strong>
    </div>
  `;

  renderChart(p);
}

function renderChart(posData) {
  const ctx = document.getElementById('diffChart').getContext('2d');
  const dist = posData.distribution;

  // Filtrar claves para centrar en saltos más representativos (-20 a +20)
  const sortedKeys = Object.keys(dist).map(Number).sort((a, b) => a - b);
  const filteredKeys = sortedKeys.filter(k => k >= -22 && k <= 22);

  const labels = filteredKeys.map(k => (k > 0 ? `+${k}` : `${k}`));
  const values = filteredKeys.map(k => dist[String(k)] || 0);

  if (appState.chartInstance) {
    appState.chartInstance.destroy();
  }

  // Colores: verde para positivos, rojo para negativos, dorado para la moda
  const backgroundColors = filteredKeys.map(k => {
    if (k === posData.mode) return '#fbbf24';
    if (k > 0) return 'rgba(59, 130, 246, 0.75)';
    if (k < 0) return 'rgba(139, 92, 246, 0.75)';
    return 'rgba(16, 185, 129, 0.75)';
  });

  appState.chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Frecuencia de Ocurrencia',
        data: values,
        backgroundColor: backgroundColors,
        borderRadius: 4,
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e293b',
          titleColor: '#f8fafc',
          bodyColor: '#cbd5e1',
          callbacks: {
            title: (items) => `Salto: ${items[0].label}`,
            label: (item) => `Apariciones: ${item.formattedValue}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#94a3b8' }
        }
      }
    }
  });
}

async function cargarRecientesDiferencias() {
  try {
    const res = await fetch('/api/estadisticas/recientes-diferencias?limit=15');
    if (!res.ok) throw new Error('Error al cargar recientes');
    const records = await res.json();

    const tbody = document.getElementById('recent-diffs-body');
    tbody.innerHTML = records.map(r => {
      const badges = r.diffs.map(d => {
        let cls = 'diff-zero';
        let sign = '';
        if (d > 0) { cls = 'diff-positive'; sign = '+'; }
        else if (d < 0) { cls = 'diff-negative'; }
        return `<span class="diff-badge ${cls}">${sign}${d}</span>`;
      }).join(' ');

      return `
        <tr>
          <td>${r.fecha.substring(0, 16)}</td>
          <td><span style="color:var(--text-muted);">${r.prev_combinacion}</span></td>
          <td><strong style="color:var(--text-primary);">${r.curr_combinacion}</strong></td>
          <td><div class="diff-badges-group">${badges}</div></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// TAB 3: HISTÓRICO DE SORTEOS
// ==========================================
async function cargarHistorico(page = 1) {
  appState.historicoPage = page;
  const searchDate = document.getElementById('search-date').value.trim();
  const searchNum = document.getElementById('search-number').value.trim();

  let url = `/api/sorteos?page=${page}&page_size=15`;
  if (searchDate) url += `&search_date=${encodeURIComponent(searchDate)}`;
  if (searchNum) url += `&has_number=${encodeURIComponent(searchNum)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Error al consultar sorteos');
    const data = await res.json();

    document.getElementById('historico-total-badge').textContent = `${data.total.toLocaleString()} sorteos encontrados`;
    document.getElementById('pagination-info').textContent = `Página ${data.page} de ${data.total_pages || 1}`;

    document.getElementById('btn-page-prev').disabled = data.page <= 1;
    document.getElementById('btn-page-next').disabled = data.page >= data.total_pages;

    const tbody = document.getElementById('historico-table-body');
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">No se encontraron sorteos con ese criterio.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.items.map(s => {
      const nums = [s.n1, s.n2, s.n3, s.n4, s.n5, s.n6];
      const balls = nums.map(n => `<div class="ball ball-normal ball-sm">${padZero(n)}</div>`).join('');
      const comp = s.complementario ? `<div class="ball ball-comp ball-sm">${padZero(s.complementario)}</div>` : '-';
      const reint = (s.reintegro !== null && s.reintegro !== undefined) ? `<div class="ball ball-reint ball-sm">${s.reintegro}</div>` : '-';

      return `
        <tr>
          <td><strong style="color:var(--text-primary);">${s.fecha.substring(0, 10)}</strong><div style="font-size:0.75rem; color:var(--text-muted);">${s.fecha.substring(11, 16)}</div></td>
          <td><div style="display:flex; gap:6px;">${balls}</div></td>
          <td>${comp}</td>
          <td>${reint}</td>
          <td><span style="font-family:var(--font-mono); font-size:0.8rem; color:var(--text-muted);">${s.joker || '-'}</span></td>
          <td><span style="color:var(--accent-gold); font-weight:700;">${s.bote > 0 ? formatEuros(s.bote) : '-'}</span></td>
          <td>
            <button class="btn-secondary" style="padding:4px 8px; font-size:0.75rem;" onclick="abrirPremiosModal(${s.id})">
              🏆 Premios
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    showToast('Error cargando histórico: ' + err.message, 'error');
  }
}

function debounceBuscarHistorico() {
  clearTimeout(appState.historicoSearchTimeout);
  appState.historicoSearchTimeout = setTimeout(() => {
    cargarHistorico(1);
  }, 350);
}

function limpiarFiltrosHistorico() {
  document.getElementById('search-date').value = '';
  document.getElementById('search-number').value = '';
  cargarHistorico(1);
}

function cambiarPagina(delta) {
  cargarHistorico(appState.historicoPage + delta);
}

// Modal Premios
async function abrirPremiosModal(sorteoId) {
  try {
    const res = await fetch(`/api/sorteos/${sorteoId}`);
    if (!res.ok) throw new Error('Error al cargar premios del sorteo');
    const data = await res.json();

    document.getElementById('modal-sorteo-title').textContent = `Premios del Sorteo: ${data.sorteo.fecha.substring(0, 10)}`;
    const tbody = document.getElementById('modal-premios-body');

    if (!data.premios || data.premios.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:20px; color:var(--text-muted);">Sin desglose de premios registrado para este sorteo.</td></tr>`;
    } else {
      tbody.innerHTML = data.premios.map(p => `
        <tr>
          <td><strong style="color:var(--text-primary);">${p.categoria_nombre}</strong></td>
          <td>${p.ganadores.toLocaleString()}</td>
          <td><span style="color:var(--accent-gold); font-weight:700;">${formatEuros(p.importe_premio)}</span></td>
        </tr>
      `).join('');
    }

    document.getElementById('modal-premios').style.display = 'flex';
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function cerrarModalPremios(e) {
  document.getElementById('modal-premios').style.display = 'none';
}

// ==========================================
// TAB 4: NUEVO SORTEO
// ==========================================
function initNumberPicker() {
  const grid = document.getElementById('grid-number-picker');
  grid.innerHTML = '';

  for (let i = 1; i <= 49; i++) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'num-pick-btn';
    btn.textContent = padZero(i);
    btn.id = `pick-num-${i}`;
    btn.onclick = () => toggleNumeroSeleccionado(i);
    grid.appendChild(btn);
  }
}

function toggleNumeroSeleccionado(num) {
  if (appState.nuevoSorteoNums.has(num)) {
    appState.nuevoSorteoNums.delete(num);
  } else {
    if (appState.nuevoSorteoNums.size >= 6) {
      showToast('Ya has seleccionado los 6 números obligatorios', 'error');
      return;
    }
    appState.nuevoSorteoNums.add(num);
  }

  // Actualizar UI
  const btn = document.getElementById(`pick-num-${num}`);
  if (btn) btn.classList.toggle('selected', appState.nuevoSorteoNums.has(num));

  actualizarPreviewSeleccionados();
}

function actualizarPreviewSeleccionados() {
  const container = document.getElementById('preview-bolas-seleccionadas');
  const badge = document.getElementById('selected-count-badge');
  const sorted = Array.from(appState.nuevoSorteoNums).sort((a, b) => a - b);

  badge.textContent = `${sorted.length} de 6 seleccionados`;

  if (sorted.length === 0) {
    container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.9rem;">Pulsa los números en la cuadrícula inferior...</span>';
  } else {
    container.innerHTML = sorted.map(n => `<div class="ball ball-normal">${padZero(n)}</div>`).join('');
  }
}

function setDefaultFechaNuevoSorteo() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const input = document.getElementById('nuevo-fecha');
  if (input) input.value = now.toISOString().slice(0, 16);
}

function resetFormNuevoSorteo() {
  appState.nuevoSorteoNums.clear();
  document.querySelectorAll('.num-pick-btn').forEach(btn => btn.classList.remove('selected'));
  actualizarPreviewSeleccionados();
  document.getElementById('nuevo-comp').value = '';
  document.getElementById('nuevo-reint').value = '';
  document.getElementById('nuevo-joker').value = '';
  document.getElementById('nuevo-bote').value = '';
  setDefaultFechaNuevoSorteo();
}

async function guardarNuevoSorteo(e) {
  e.preventDefault();
  const sorted = Array.from(appState.nuevoSorteoNums).sort((a, b) => a - b);

  if (sorted.length !== 6) {
    showToast('Debes seleccionar exactamente 6 números para la combinación', 'error');
    return;
  }

  const fechaVal = document.getElementById('nuevo-fecha').value;
  if (!fechaVal) {
    showToast('La fecha del sorteo es obligatoria', 'error');
    return;
  }

  const payload = {
    fecha: fechaVal.replace('T', ' ') + ':00',
    n1: sorted[0],
    n2: sorted[1],
    n3: sorted[2],
    n4: sorted[3],
    n5: sorted[4],
    n6: sorted[5],
    complementario: document.getElementById('nuevo-comp').value ? parseInt(document.getElementById('nuevo-comp').value) : null,
    reintegro: document.getElementById('nuevo-reint').value !== '' ? parseInt(document.getElementById('nuevo-reint').value) : null,
    joker: document.getElementById('nuevo-joker').value.trim() || null,
    bote: parseFloat(document.getElementById('nuevo-bote').value || 0.0)
  };

  const btn = document.getElementById('btn-submit-sorteo');
  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Guardando...';

  try {
    const res = await fetch('/api/sorteos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Error al guardar el sorteo');
    }

    const data = await res.json();
    showToast('¡Sorteo guardado y base de datos actualizada!', 'success');
    resetFormNuevoSorteo();
    cargarHeroUltimoSorteo();
    switchTab('pronosticos');
    generarPronosticos();
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>💾</span> Guardar Sorteo en Base de Datos';
  }
}

// ==========================================
// UTILIDADES Y NOTIFICACIONES
// ==========================================
function padZero(num) {
  return num < 10 ? `0${num}` : `${num}`;
}

function formatEuros(amount) {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(amount);
}

function formatearFecha(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.replace(' ', 'T'));
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString('es-ES', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✅' : '⚠️'}</span>
    <div>${msg}</div>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
