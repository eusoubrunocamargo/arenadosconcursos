#!/usr/bin/env python3
"""
Etapa 5 - Dashboard de auditoria (servidor local).

Abre um servidor HTTP local na porta 5000 e serve um dashboard
de auditoria com navegação por questão e edição inline dos campos.
As alterações são salvas de volta no arquivo JSON original.

Uso:
    python dashboard_auditoria.py --entrada dataset_sanitizado_lp.json
    python dashboard_auditoria.py --entrada dataset_sanitizado_lp.json --porta 8080

Navegação:
    ← →  Navega entre questões
    Ctrl+S  Salva alterações
"""

import json
import argparse
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

# =============================================================================
# HTML DO DASHBOARD
# =============================================================================

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Auditoria — rinhadeconcurseiro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg:       #f5f4ef;
  --surface:  #ffffff;
  --border:   #e2dfd8;
  --text:     #1a1916;
  --muted:    #8c8880;
  --accent:   #1a1916;
  --ok:       #2d6a4f;
  --warn:     #b5470e;
  --tag-bg:   #eceae4;
  --mono:     'DM Mono', monospace;
  --sans:     'DM Sans', sans-serif;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
}

/* ── CHROME ──────────────────────────────────────────── */
#chrome {
  display: grid;
  grid-template-rows: 52px 1fr 52px;
  height: 100vh;
  max-width: 900px;
  margin: 0 auto;
  padding: 0 24px;
}

/* ── TOPBAR ──────────────────────────────────────────── */
#topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--border);
}

.logo {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
  letter-spacing: .06em;
}
.logo b { color: var(--text); font-weight: 500; }

.pill {
  font-family: var(--mono);
  font-size: 11px;
  background: var(--tag-bg);
  border-radius: 4px;
  padding: 3px 8px;
  color: var(--muted);
}
.pill b { color: var(--text); }

#audit-btn {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1.5px solid var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
}
#audit-btn:hover { border-color: var(--ok); color: var(--ok); }
#audit-btn.done  { border-color: var(--ok); color: var(--ok); background: #f0faf5; }

#save-btn {
  margin-left: auto;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  padding: 7px 20px;
  border-radius: 6px;
  border: 1.5px solid var(--accent);
  background: var(--accent);
  color: var(--bg);
  cursor: pointer;
  transition: opacity .15s;
  letter-spacing: .01em;
}
#save-btn:hover { opacity: .85; }
#save-btn.saved { background: var(--ok); border-color: var(--ok); }
#save-btn.error { background: var(--warn); border-color: var(--warn); }

#status-msg {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  min-width: 120px;
}

/* ── CARD CENTRAL ────────────────────────────────────── */
#card-area {
  overflow-y: auto;
  padding: 28px 0;
}

#card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

/* ── LINHAS DE CAMPO ─────────────────────────────────── */
.field-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  border-bottom: 1px solid var(--border);
  min-height: 40px;
}
.field-row:last-child { border-bottom: none; }

/* Campo HTML: split code | preview */
.html-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 120px;
}
.html-code { border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.html-preview { display: flex; flex-direction: column; }
.html-pane-label {
  font-family: var(--mono);
  font-size: 9px; font-weight: 600; letter-spacing: .1em;
  color: var(--muted); text-transform: uppercase;
  padding: 5px 10px; border-bottom: 1px solid var(--border);
  background: #faf9f6; flex-shrink: 0;
}
.html-pane-label.preview-lbl { background: #f0f7f4; color: #4a8a6a; }
.html-code textarea {
  font-family: var(--mono) !important;
  font-size: 11px !important;
  flex: 1; border: none; outline: none;
  background: transparent; padding: 8px 10px;
  resize: vertical; min-height: 100px;
  line-height: 1.55; color: #4a4540;
  transition: background .12s;
}
.html-code textarea:focus { background: #f0ede6; }
.html-preview-frame {
  flex: 1; padding: 8px 12px;
  font-size: 13px; line-height: 1.7;
  color: var(--text); overflow-y: auto; min-height: 100px;
}

.field-label {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .04em;
  color: var(--muted);
  padding: 10px 16px;
  display: flex;
  align-items: flex-start;
  padding-top: 12px;
  border-right: 1px solid var(--border);
  background: #faf9f6;
  user-select: none;
}

.field-value {
  padding: 6px 10px;
  display: flex;
  align-items: flex-start;
}

/* Inputs editáveis */
.field-value input[type=text],
.field-value input[type=number],
.field-value select {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--text);
  background: transparent;
  border: none;
  outline: none;
  width: 100%;
  padding: 4px 6px;
  border-radius: 4px;
  transition: background .12s;
  line-height: 1.5;
}
.field-value input:focus,
.field-value select:focus {
  background: #f0ede6;
}

/* Readonly */
.field-value input[readonly] {
  color: var(--muted);
  cursor: default;
  font-family: var(--mono);
  font-size: 11px;
}

/* Textarea */
.field-value textarea {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--text);
  background: transparent;
  border: none;
  outline: none;
  width: 100%;
  padding: 4px 6px;
  border-radius: 4px;
  resize: vertical;
  min-height: 72px;
  line-height: 1.65;
  transition: background .12s;
  field-sizing: content;
}
.field-value textarea:focus { background: #f0ede6; }

/* Select */
.field-value select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%238c8880'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 28px;
}

/* Bool toggle */
.bool-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px;
  cursor: pointer;
  user-select: none;
}
.toggle-track {
  width: 36px; height: 20px;
  border-radius: 10px;
  background: var(--border);
  position: relative;
  transition: background .2s;
  flex-shrink: 0;
}
.toggle-track.on { background: var(--ok); }
.toggle-thumb {
  position: absolute;
  width: 14px; height: 14px;
  border-radius: 7px;
  background: white;
  top: 3px; left: 3px;
  transition: left .2s;
  box-shadow: 0 1px 3px rgba(0,0,0,.2);
}
.toggle-track.on .toggle-thumb { left: 19px; }
.bool-label { font-size: 13px; color: var(--text); }

/* Tags */
.tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 6px;
  width: 100%;
  align-items: center;
}
.tag-chip {
  font-family: var(--mono);
  font-size: 11px;
  background: var(--tag-bg);
  border-radius: 4px;
  padding: 3px 8px;
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text);
}
.tag-chip button {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 12px;
  padding: 0;
  line-height: 1;
}
.tag-chip button:hover { color: var(--warn); }
.tag-add {
  font-family: var(--mono);
  font-size: 11px;
  background: transparent;
  border: 1px dashed var(--border);
  border-radius: 4px;
  padding: 3px 8px;
  color: var(--muted);
  cursor: pointer;
  outline: none;
  width: 80px;
  transition: border-color .15s;
}
.tag-add:focus { border-color: var(--accent); color: var(--text); width: 120px; }

/* Link TEC */
.link-tec {
  font-family: var(--mono);
  font-size: 11px;
  color: #4a6fa1;
  text-decoration: none;
  padding: 4px 6px;
}
.link-tec:hover { text-decoration: underline; }

/* ── BOTTOMBAR ────────────────────────────────────────── */
#bottombar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  border-top: 1px solid var(--border);
}

.nav-btn {
  font-family: var(--mono);
  font-size: 18px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 36px; height: 36px;
  cursor: pointer;
  color: var(--text);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .12s;
}
.nav-btn:hover:not(:disabled) { background: var(--tag-bg); }
.nav-btn:disabled { opacity: .3; cursor: default; }

#nav-counter {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--muted);
  min-width: 90px;
  text-align: center;
}
#nav-counter b { color: var(--text); }

#filter-quality {
  font-family: var(--mono);
  font-size: 11px;
  background: var(--tag-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  color: var(--text);
  cursor: pointer;
  outline: none;
  margin-left: 8px;
}
</style>
</head>
<body>
<div id="chrome">

  <!-- topbar -->
  <div id="topbar">
    <span class="logo">rinha<b>deconcurseiro</b> · auditoria</span>
    <span class="pill" id="file-pill">—</span>
    <span class="pill" id="quality-pill">—</span>
    <span class="pill" id="audit-pill" style="display:none">—</span>
    <button id="audit-btn" onclick="marcarAuditado()" title="Registrar data/hora da auditoria">✓ Auditar</button>
    <span id="status-msg"></span>
    <button id="save-btn" onclick="salvar()">Salvar  <kbd>⌘S</kbd></button>
  </div>

  <!-- card central -->
  <div id="card-area">
    <div id="card"><!-- preenchido via JS --></div>
  </div>

  <!-- bottombar -->
  <div id="bottombar">
    <select id="filter-quality" onchange="aplicarFiltro()">
      <option value="">Todas as questões</option>
      <option value="REQUER_REVISAO_MANUAL">Somente revisão</option>
      <option value="PERFEITA">Somente perfeitas</option>
    </select>
    <button class="nav-btn" id="btn-prev" onclick="navegar(-1)" title="← Anterior">‹</button>
    <span id="nav-counter">— / —</span>
    <button class="nav-btn" id="btn-next" onclick="navegar(1)"  title="→ Próxima">›</button>
  </div>

</div>

<script>
// ==========================================================================
// DADOS (injetados pelo Python)
// ==========================================================================
let QUESTOES = __DADOS_JSON__;
let indices  = QUESTOES.map((_, i) => i);  // índices filtrados
let pos      = 0;   // posição dentro de 'indices'

// Campos modificados nesta sessão (id_tec → objeto questão modificado)
const modificados = {};

// ==========================================================================
// DEFINIÇÃO DOS CAMPOS
// ==========================================================================
const CAMPOS = [
  { key: 'id_tec',            label: 'id_tec',            tipo: 'readonly' },
  { key: 'link_tec',          label: 'link_tec',          tipo: 'link'     },
  { key: 'banca',             label: 'banca',             tipo: 'text'     },
  { key: 'variante_banca',    label: 'variante_banca',    tipo: 'text'     },
  { key: 'ano',               label: 'ano',               tipo: 'number'   },
  { key: 'orgao_sigla',       label: 'orgao_sigla',       tipo: 'text'     },
  { key: 'orgao_nome',        label: 'orgao_nome',        tipo: 'text'     },
  { key: 'cargo',             label: 'cargo',             tipo: 'text'     },
  { key: 'concurso_area',     label: 'concurso_area',     tipo: 'text'     },
  { key: 'id_materia_nome',   label: 'id_materia_nome',   tipo: 'text'     },
  { key: 'id_assunto_nome',   label: 'id_assunto_nome',   tipo: 'text'     },
  { key: 'texto_apoio_texto', label: 'texto_apoio_texto', tipo: 'textarea' },
  { key: 'texto_apoio_html',  label: 'texto_apoio_html',  tipo: 'html'     },
  { key: 'comando_texto',     label: 'comando_texto',     tipo: 'text'     },
  { key: 'comando_html',      label: 'comando_html',      tipo: 'html'     },
  { key: 'enunciado_texto',   label: 'enunciado_texto',   tipo: 'textarea' },
  { key: 'enunciado_html',    label: 'enunciado_html',    tipo: 'html'     },
  { key: 'gabarito',          label: 'gabarito',          tipo: 'select',
    opts: ['CERTO', 'ERRADO'] },
  { key: 'tipo_cobranca',     label: 'tipo_cobranca',     tipo: 'select',
    opts: ['INTERPRETACAO_TEXTUAL','DOUTRINA','LITERALIDADE_LEI',
           'JURISPRUDENCIA','CASO_CONCRETO'] },
  { key: 'referencia_legal',  label: 'referencia_legal',  tipo: 'text'     },
  { key: 'qualidade_extracao',label: 'qualidade_extracao',tipo: 'select',
    opts: ['PERFEITA','REQUER_REVISAO_MANUAL'] },
  { key: 'padrao_estrutural', label: 'padrao_estrutural', tipo: 'text'     },
  { key: 'conceito_principal',label: 'conceito_principal',tipo: 'text'     },
  { key: 'armadilha',         label: 'armadilha',         tipo: 'text'     },
  { key: 'nivel_dificuldade', label: 'nivel_dificuldade', tipo: 'select',
    opts: ['', 'FACIL', 'MEDIO', 'DIFICIL'] },
  { key: 'justificativa',     label: 'justificativa',     tipo: 'textarea' },
  { key: 'tags',              label: 'tags',              tipo: 'tags'     },
  { key: 'ativo',             label: 'ativo',             tipo: 'bool'     },
  { key: 'data_auditoria',    label: 'data_auditoria',    tipo: 'readonly' },
];

// ==========================================================================
// RENDER
// ==========================================================================
function questaoAtual() {
  return QUESTOES[indices[pos]];
}

function render() {
  const q   = questaoAtual();
  const card = document.getElementById('card');

  card.innerHTML = CAMPOS.map(f => {
    const val = q[f.key];
    return `<div class="field-row">
      <div class="field-label">${f.label}</div>
      <div class="field-value">${renderField(f, val)}</div>
    </div>`;
  }).join('');

  // Contador
  document.getElementById('nav-counter').innerHTML =
    `<b>${pos + 1}</b> / ${indices.length}`;
  document.getElementById('btn-prev').disabled = pos === 0;
  document.getElementById('btn-next').disabled = pos === indices.length - 1;

  // Pill qualidade
  const qe = q.qualidade_extracao || q.nivel_qualidade || '';
  const qpill = document.getElementById('quality-pill');
  qpill.textContent = qe;
  qpill.style.color = qe === 'REQUER_REVISAO_MANUAL' ? '#b5470e' : '#2d6a4f';

  // Pill auditoria
  const auditado = q.data_auditoria || '';
  const apill = document.getElementById('audit-pill');
  const abtn  = document.getElementById('audit-btn');
  if (auditado) {
    apill.textContent = 'auditado em: ' + auditado;
    apill.style.display = '';
    apill.style.color = '#2d6a4f';
    abtn.textContent = '✓ Auditado';
    abtn.className = 'done';
  } else {
    apill.style.display = 'none';
    abtn.textContent = '✓ Auditar';
    abtn.className = '';
  }

  // Status de modificações pendentes
  atualizarStatus();
}

function renderField(f, val) {
  const v = val ?? '';
  const q = questaoAtual();

  if (f.tipo === 'readonly') {
    return `<input type="text" readonly value="${esc(String(v))}">`;
  }
  if (f.tipo === 'link') {
    return `<a class="link-tec" href="${esc(String(v))}" target="_blank">${esc(String(v))}</a>`;
  }
  if (f.tipo === 'text') {
    return `<input type="text" data-key="${f.key}" value="${esc(String(v ?? ''))}"
      oninput="marcarModificado('${f.key}', this.value)">`;
  }
  if (f.tipo === 'number') {
    return `<input type="number" data-key="${f.key}" value="${esc(String(v ?? ''))}"
      oninput="marcarModificado('${f.key}', this.valueAsNumber || null)">`;
  }
  if (f.tipo === 'textarea') {
    return `<textarea data-key="${f.key}"
      oninput="marcarModificado('${f.key}', this.value)">${esc(String(v ?? ''))}</textarea>`;
  }
  if (f.tipo === 'select') {
    const opts = f.opts.map(o =>
      `<option value="${o}" ${o === String(v) ? 'selected' : ''}>${o || '—'}</option>`
    ).join('');
    return `<select data-key="${f.key}" onchange="marcarModificado('${f.key}', this.value)">${opts}</select>`;
  }
  if (f.tipo === 'bool') {
    const on = v === true || v === 'true';
    return `<div class="bool-toggle" onclick="toggleBool('${f.key}')">
      <div class="toggle-track ${on ? 'on' : ''}" id="toggle-${f.key}">
        <div class="toggle-thumb"></div>
      </div>
      <span class="bool-label" id="bool-label-${f.key}">${on ? 'true' : 'false'}</span>
    </div>`;
  }
  if (f.tipo === 'html') {
    const htmlId = 'html-' + f.key.replace(/_/g, '-');
    const previewId = 'preview-' + f.key.replace(/_/g, '-');
    // Escapa para colocar no atributo value da textarea de código
    const htmlEscaped = String(v ?? '').replace(/&/g,'&amp;').replace(/"/g,'&quot;')
                          .replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div class="html-split">
      <div class="html-code">
        <div class="html-pane-label">código</div>
        <textarea id="${htmlId}" data-key="${f.key}"
          oninput="atualizarHtmlPreview('${f.key}')"
          onchange="marcarModificado('${f.key}', this.value)">${htmlEscaped}</textarea>
      </div>
      <div class="html-preview">
        <div class="html-pane-label preview-lbl">prévia</div>
        <div class="html-preview-frame" id="${previewId}">${v ?? ''}</div>
      </div>
    </div>`;
  }
  if (f.tipo === 'tags') {
    const tags = Array.isArray(v) ? v : [];
    const chips = tags.map((t, i) =>
      `<span class="tag-chip">${esc(t)}
        <button onclick="removerTag(${i})" title="Remover">×</button>
      </span>`
    ).join('');
    return `<div class="tags-wrap">
      ${chips}
      <input class="tag-add" placeholder="+ tag" onkeydown="adicionarTag(event, this)">
    </div>`;
  }
  return `<input type="text" value="${esc(String(v ?? ''))}">`;
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;')
          .replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ==========================================================================
// EDIÇÃO
// ==========================================================================
function atualizarHtmlPreview(key) {
  const htmlId    = 'html-'    + key.replace(/_/g, '-');
  const previewId = 'preview-' + key.replace(/_/g, '-');
  const ta = document.getElementById(htmlId);
  const pv = document.getElementById(previewId);
  if (ta && pv) {
    pv.innerHTML = ta.value;
    marcarModificado(key, ta.value);
  }
}

function marcarModificado(key, value) {
  const q = questaoAtual();
  q[key] = value;
  modificados[q.id_tec] = q;
  atualizarStatus();
}

function toggleBool(key) {
  const q = questaoAtual();
  q[key] = !q[key];
  const on = q[key];
  const track = document.getElementById(`toggle-${key}`);
  const label = document.getElementById(`bool-label-${key}`);
  if (track) track.className = 'toggle-track' + (on ? ' on' : '');
  if (label) label.textContent = on ? 'true' : 'false';
  marcarModificado(key, on);
}

function removerTag(idx) {
  const q = questaoAtual();
  q.tags = (q.tags || []).filter((_, i) => i !== idx);
  marcarModificado('tags', q.tags);
  render();
}

function adicionarTag(e, input) {
  if (e.key !== 'Enter') return;
  const v = input.value.trim();
  if (!v) return;
  const q = questaoAtual();
  q.tags = [...(q.tags || []), v];
  marcarModificado('tags', q.tags);
  input.value = '';
  render();
}

function marcarAuditado() {
  const q   = questaoAtual();
  const ago = q.data_auditoria;

  // Se já auditado, confirma antes de limpar
  if (ago) {
    if (!confirm(`Já auditado em ${ago}.
Limpar a marcação?`)) return;
    q.data_auditoria = null;
  } else {
    // Formata: DD/MM/YYYY HH:MM
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    q.data_auditoria = `${pad(now.getDate())}/${pad(now.getMonth()+1)}/${now.getFullYear()} `
                     + `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  }
  marcarModificado('data_auditoria', q.data_auditoria);
  render();
}

function atualizarStatus() {
  const n = Object.keys(modificados).length;
  document.getElementById('status-msg').textContent =
    n > 0 ? `${n} questão(ões) modificada(s)` : '';
}

// ==========================================================================
// NAVEGAÇÃO
// ==========================================================================
function navegar(delta) {
  const novo = pos + delta;
  if (novo < 0 || novo >= indices.length) return;
  pos = novo;
  render();
  document.getElementById('card-area').scrollTop = 0;
}

function aplicarFiltro() {
  const filtro = document.getElementById('filter-quality').value;
  if (!filtro) {
    indices = QUESTOES.map((_, i) => i);
  } else {
    indices = QUESTOES
      .map((q, i) => ({ q, i }))
      .filter(({ q }) => (q.qualidade_extracao || q.nivel_qualidade || '') === filtro)
      .map(({ i }) => i);
  }
  pos = 0;
  render();
}

document.addEventListener('keydown', e => {
  // Não navega se foco está num campo de texto
  const tag = document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  if (e.key === 'ArrowRight') navegar(1);
  if (e.key === 'ArrowLeft')  navegar(-1);
});

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault();
    salvar();
  }
});

// ==========================================================================
// SALVAR
// ==========================================================================
function salvar() {
  const btn = document.getElementById('save-btn');
  btn.textContent = 'Salvando…';
  btn.disabled = true;

  fetch('/salvar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(QUESTOES)
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) {
      btn.textContent = '✓ Salvo';
      btn.className = 'saved';
      Object.keys(modificados).forEach(k => delete modificados[k]);
      atualizarStatus();
    } else {
      throw new Error(data.erro || 'erro desconhecido');
    }
  })
  .catch(err => {
    btn.textContent = '✗ Erro';
    btn.className = 'error';
    alert('Erro ao salvar: ' + err.message);
  })
  .finally(() => {
    setTimeout(() => {
      btn.textContent = 'Salvar  ⌘S';
      btn.className = '';
      btn.disabled = false;
    }, 2000);
  });
}

// ==========================================================================
// INIT
// ==========================================================================
document.getElementById('file-pill').innerHTML =
  `arquivo: <b>${QUESTOES.length} questões</b>`;
render();
</script>
</body>
</html>"""


# =============================================================================
# SERVIDOR HTTP LOCAL
# =============================================================================

arquivo_json = None   # preenchido no main()
questoes_mem  = []    # dataset em memória


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silencia logs do servidor

    def do_GET(self):
        if urlparse(self.path).path == '/':
            dados_js = json.dumps(questoes_mem, ensure_ascii=False)
            html = HTML.replace('__DADOS_JSON__', dados_js)
            body = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path == '/salvar':
            length  = int(self.headers.get('Content-Length', 0))
            payload = self.rfile.read(length)
            try:
                novas = json.loads(payload)
                with open(arquivo_json, 'w', encoding='utf-8') as f:
                    json.dump(novas, f, ensure_ascii=False, indent=2)
                questoes_mem.clear()
                questoes_mem.extend(novas)
                resposta = json.dumps({'ok': True}).encode()
            except Exception as e:
                resposta = json.dumps({'ok': False, 'erro': str(e)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resposta)))
            self.end_headers()
            self.wfile.write(resposta)
        else:
            self.send_response(404)
            self.end_headers()


# =============================================================================
# MAIN
# =============================================================================

def main():
    global arquivo_json

    parser = argparse.ArgumentParser(
        description='Etapa 5 — Dashboard de auditoria (servidor local)'
    )
    parser.add_argument('--entrada', required=True,
                        help='dataset_sanitizado_X.json')
    parser.add_argument('--porta', type=int, default=5000)
    args = parser.parse_args()

    arquivo_json = args.entrada
    with open(arquivo_json, encoding='utf-8') as f:
        dados = json.load(f)

    questoes_mem.extend(dados)
    print(f'  {len(dados)} questões carregadas de {arquivo_json}')

    servidor = HTTPServer(('127.0.0.1', args.porta), Handler)
    url = f'http://localhost:{args.porta}'

    print(f'  Servidor em {url}')
    print(f'  Ctrl+C para encerrar\n')

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print('\n  Servidor encerrado.')


if __name__ == '__main__':
    main()