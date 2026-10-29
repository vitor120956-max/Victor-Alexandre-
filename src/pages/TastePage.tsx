import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Brush,
  CheckCircle2,
  Clipboard,
  Compass,
  FileText,
  Layers,
  LoaderCircle,
  Palette,
  PenLine,
  ScanEye,
  Sparkles,
  Tags,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../taste.css';

type TasteTab = 'direction' | 'argument' | 'copy' | 'lint' | 'tells' | 'judge' | 'library';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: TasteTab; label: string; hint: string; icon: typeof Palette }> = [
  { id: 'direction', label: 'Direção', hint: 'Três opções e ficha', icon: Compass },
  { id: 'argument', label: 'Argumento', hint: 'Afirmação e prova', icon: FileText },
  { id: 'copy', label: 'Copy', hint: 'Deck medido', icon: PenLine },
  { id: 'lint', label: 'Regras', hint: 'Linter caseiro', icon: ScanEye },
  { id: 'tells', label: 'Tells', hint: 'Registro datado', icon: Tags },
  { id: 'judge', label: 'Júri', hint: 'Nota e tetos', icon: Sparkles },
  { id: 'library', label: 'Biblioteca', hint: 'Vocabulário', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string; description: string }> = [
  { id: 'lite', label: 'Lite', description: 'Só o que bloqueia.' },
  { id: 'full', label: 'Full', description: 'Padrão: bloqueios e correções.' },
  { id: 'ultra', label: 'Ultra', description: 'Inclui perguntas para a revisão.' },
];

const laws = [
  { key: 'sujeito', title: 'O sujeito antes do estilo', text: 'A direção sorteada só vale se carregar algo que só este cliente tem: lugar, material, número, rito.' },
  { key: 'prova', title: 'Toda afirmação pede prova', text: 'Seção sem prova é preenchimento. Número sem fonte é prova inventada e sai da peça.' },
  { key: 'cota', title: 'A cota do título é curta', text: 'Cerca de 32 caracteres e duas linhas em 390 px. Encolher a fonte não resolve título longo.' },
  { key: 'teto', title: 'Defeito visível tem teto', text: 'Manchete em três linhas, gradiente, sombra ou faixa em branco limitam a nota inteira.' },
];

const analysisLabels: Record<string, string> = {
  direction: 'Direção', argument: 'Argumento', copy: 'Copy', lint: 'Regras', tells: 'Tells', judge: 'Júri', reference: 'Biblioteca',
};

const SAMPLE_BRIEF = 'Padaria de fermentação natural na rua das Palmeiras, 7 anos de forno a lenha, pão a 12 reais e mesa às 9h.';
const SAMPLE_SECTIONS = 'sobre, vitrine, como-funciona, contato';
const SAMPLE_REDRAWS = 'hero | a foto de capa do forno já existe e não pode ser trocada pela direção';

const SAMPLE_CLAIMS = `sobre | A massa descansa 18 horas antes de assar | foto do forno a lenha aceso
vitrine | Sete pães saem do forno às 7h | tabela com nome, farinha e preço de cada pão
como-funciona | A encomenda fecha no dia anterior às 18h | capture do formulário com horário
contato | A padaria fica na rua das Palmeiras, 120 | mapa e horário de terça a domingo`;

const SAMPLE_DECK = `manchete | Pão de fermentação natural
apoio | Forno a lenha na rua das Palmeiras, desde 2019.
corpo | A massa descansa 18 horas e sai do forno às 7h.
acao | Ver o cardápio
nav | Pães
nav | Forno
nav | Visita
legenda | Mesa às 9h.`;

const SAMPLE_LINT = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Ateliê Barro</title>
<style>
:root { --bg: #faf9f5; --ink: #1c1917; --accent: #d97757; }
.hero { background: linear-gradient(120deg, #6366f1, #a855f7); color: #faf9f5; }
.hero h1 { font-family: Inter, sans-serif; background-clip: text; color: transparent; }
.card { border: 1px solid #e7e5e4; box-shadow: 0 4px 12px rgba(0,0,0,.18); border-radius: 999px; }
.label { text-transform: uppercase; letter-spacing: .1em; font-family: ui-monospace, monospace; }
.cta { background: var(--accent); transition: all 200ms ease-in; outline: none; }
</style></head>
<body>
<div class="eyebrow">Field notes</div>
<h2>01 / Coleção</h2>
<p>Lorem ipsum dolor sit amet, plataforma para times modernos.</p>
<h1>Ateliê Barro ✨</h1>
<img src="vaso.jpg" alt="Vaso de barro">
<div class="card">Feito à mão em 12 etapas</div>
<pre><code>.x { background: linear-gradient(90deg, #6366f1, #fff); }</code></pre>
<div data-ui><span class="label">TABELA DE MEDIDAS</span></div>
</body></html>`;

const SAMPLE_TELLS = `Não é só uma olaria, é um laboratório de terra.
Est. 2024 · 48.5° N, 48.5483° W · Vol. 04
Rápido. Simples. Seguro.

<div class="eyebrow">Field notes</div>
<p class="mono">Desbloqueie o potencial da sua marca.</p>`;

const SAMPLE_JUDGE = `design | 8 | Margens iguais em 1440 e 390; grid de 12 colunas e respiro constante.
usabilidade | 7 | Foco visível no botão; o formulário conclui em três campos.
criatividade | 4 | A ideia serviria a qualquer ateliê de cerâmica do país.
conteudo | 6 | As peças têm preço, mas o prazo de entrega não aparece em lugar nenhum.`;

const SAMPLE_SIGNALS = `manchete-longa | sim
serviria-a-qualquer-um | sim
menos-de-4-fotos | sim`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const fixed = (value: unknown, digits = 0): string => count(value).toFixed(digits);
const decimal = (value: unknown): string => (value === null || value === undefined ? '—' : count(value).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const severityLabel: Record<string, string> = { must: 'falha', should: 'aviso', nice: 'dica' };
const argumentStatus: Record<string, string> = { ok: 'com prova', 'sem prova': 'sem prova', vazia: 'vazia', 'prova frágil': 'prova frágil' };
const copyStatus: Record<string, string> = { lida: 'medida', vazia: 'vazia', longa: 'longa', desconhecida: 'desconhecida' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Limitations({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="taste-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="taste-empty"><CheckCircle2 size={14} />Nenhum candidato pelas regras estáticas.</p>;
  return (
    <div className="taste-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`taste-finding is-${group}`} key={`${text(finding.id)}-${text(finding.kind)}-${text(finding.location)}`}>
            <header>
              <span className="taste-group">{groupLabel[group] ?? group}</span>
              <strong>{text(finding.title)}</strong>
              <code>{text(finding.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{text(finding.what)}</dd></div>
              <div><dt>Problema</dt><dd>{text(finding.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{text(finding.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{text(finding.ifSkipped)}</dd></div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function DirectionView({ result, picked, onPick }: { result: Row; picked: string; onPick: (id: string) => void }) {
  const metrics = asRow(result.metrics);
  const options = asRows(result.options);
  const sheet = asRow(result.sheet);
  const palette = asRow(sheet.palette);
  const sections = asRows(sheet.sections);
  const traps = asList(sheet.traps);
  const redraws = asRows(result.redraws);
  const hasSheet = Boolean(text(sheet.id));
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="DIREÇÕES" value={count(metrics.directions)} />
        <Metric label="SORTEADAS" value={count(metrics.options)} />
        <Metric label="SEMENTE" value={<code>{text(metrics.seed)}</code>} />
        <Metric label="SEÇÕES" value={count(metrics.sections)} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(result.verdict)}</p>
      <div className="taste-options">
        {options.map((option) => {
          const selected = picked === text(option.id);
          return (
            <article className={`taste-option ${selected ? 'is-selected' : ''}`} key={text(option.id)}>
              <header>
                <strong>{text(option.name)}</strong>
                <code>{text(option.id)}</code>
                <button type="button" onClick={() => onPick(text(option.id))}>{selected ? 'Ficha aberta' : 'Abrir ficha'}</button>
              </header>
              <p>{text(option.thesis)}</p>
              <ul>
                {asList(option.fit).map((item) => <li key={item}>{item}</li>)}
                {asList(option.tension).map((item) => <li className="is-tension" key={item}>tensão: {item}</li>)}
              </ul>
            </article>
          );
        })}
      </div>
      {hasSheet && (
        <div className="taste-sheet">
          <h3>{text(sheet.name)}<code>{text(sheet.seed)}</code></h3>
          <p className="taste-sheet-idea">{text(sheet.idea)}</p>
          <div className="taste-sheet-grid">
            <section><h4>Herói</h4><p>{text(sheet.hero)}</p></section>
            <section><h4>Tipografia</h4><p>{text(sheet.type)}</p></section>
            <section>
              <h4>Paleta · {text(palette.mode)}</h4>
              <div className="taste-palette">
                <span>fundo: {text(palette.ground)}</span>
                <span>tinta: {text(palette.ink)}</span>
                <span>acento: {text(palette.accent)}</span>
                <span>campo: {text(palette.field)}</span>
              </div>
              <p>{text(palette.proportion) || text(palette.note)}</p>
            </section>
            <section><h4>Imagens</h4><p>{text(sheet.imagery)}</p></section>
            <section><h4>Movimento</h4><p>{text(sheet.motion)}</p></section>
            <section>
              <h4>Evitar</h4>
              <p>{asList(sheet.avoids).join(' · ') || '—'}</p>
            </section>
          </div>
          <div className="taste-scroll">
            <table className="taste-table">
              <thead><tr><th>Seção</th><th>Composição</th></tr></thead>
              <tbody>{sections.map((section) => (
                <tr key={text(section.role)}><td><strong>{text(section.label)}</strong><br /><code>{text(section.role)}</code></td><td>{text(section.layout)}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <section>
            <h4>Armadilhas</h4>
            <ul className="taste-traps">{traps.map((trap) => <li key={trap}>{trap}</li>)}</ul>
          </section>
          {redraws.length > 0 && (
            <section>
              <h4>Redesenhos registrados</h4>
              <ul className="taste-traps">{redraws.map((item) => <li key={text(item.slot)}><code>{text(item.slot)}</code> — {text(item.reason)}</li>)}</ul>
            </section>
          )}
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ArgumentView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="SEÇÕES" value={count(metrics.sections)} />
        <Metric label="COM PROVA" value={`${count(metrics.proofs)}/${count(metrics.sections)}`} tone={count(metrics.proofs) === count(metrics.sections) ? 'ok' : 'danger'} />
        <Metric label="TÍTULO" value={`${count(metrics.headlineChars)} car.`} tone={count(metrics.headlineChars) > 42 ? 'danger' : count(metrics.headlineChars) > 32 ? 'warning' : 'ok'} />
        <Metric label="APOIO" value={`${count(metrics.supportWords)} palavras`} tone={count(metrics.supportWords) > 22 ? 'warning' : undefined} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(result.verdict)}</p>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Seção</th><th>Afirmação</th><th>Prova</th><th>Estado</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={`${text(row.line)}-${text(row.label)}`}>
              <td><strong>{text(row.label)}</strong></td>
              <td>{text(row.claim) || '—'}</td>
              <td>{text(row.proof) || '—'}</td>
              <td><span className={`taste-state ${text(row.status) === 'ok' ? 'is-ok' : 'is-warning'}`}>{argumentStatus[text(row.status)] ?? text(row.status)}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function CopyView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="PEÇAS" value={count(metrics.pieces)} />
        <Metric label="TÍTULO" value={`${count(metrics.headlineChars)} car.`} tone={count(metrics.headlineChars) > 42 ? 'danger' : count(metrics.headlineChars) > 32 ? 'warning' : 'ok'} />
        <Metric label="AÇÕES" value={count(metrics.actions)} tone={count(metrics.actions) > 1 ? 'warning' : undefined} />
        <Metric label="CATÁLOGO" value={count(metrics.stockWords)} tone={count(metrics.stockWords) ? 'warning' : 'ok'} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(result.verdict)}</p>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Peça</th><th>Texto</th><th>Palavras</th><th>Estado</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={`${text(row.line)}-${text(row.role)}-${text(row.text)}`}>
              <td><strong>{text(row.label)}</strong><br /><code>{text(row.role)}</code></td>
              <td>{text(row.text) || '—'}</td>
              <td>{String(text(row.text).split(/\s+/).filter(Boolean).length)}</td>
              <td><span className={`taste-state ${text(row.status) === 'lida' ? 'is-ok' : 'is-danger'}`}>{copyStatus[text(row.status)] ?? text(row.status)}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function LintView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="REGRAS" value={count(metrics.rules)} />
        <Metric label="ACIONADAS" value={count(metrics.rulesHit)} tone={count(metrics.must) ? 'danger' : count(metrics.should) ? 'warning' : 'ok'} />
        <Metric label="ISENÇÕES" value={count(metrics.escapes)} />
        <Metric label="IMAGENS" value={count(metrics.images)} tone={count(metrics.images) < 4 ? 'warning' : 'ok'} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(result.verdict)}</p>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Regra</th><th>Grupo</th><th>Ocorrências</th><th>Amostra</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={text(row.rule)}>
              <td><strong>{text(row.title)}</strong><br /><code>{text(row.rule)}</code></td>
              <td><span className={`taste-state is-${text(row.severity) === 'must' ? 'danger' : text(row.severity) === 'should' ? 'warning' : 'ok'}`}>{severityLabel[text(row.severity)] ?? text(row.severity)}</span></td>
              <td>{count(row.count)}<br /><span className="taste-chip">{asList(row.lines).join(', ') || '—'}</span></td>
              <td>{asList(row.samples)[0] ?? '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function TellsView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const catalog = asRows(result.catalog);
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="REGISTRO" value={count(metrics.catalog)} />
        <Metric label="ENCONTRADOS" value={count(metrics.hits)} tone={count(metrics.hits) ? 'warning' : 'ok'} />
        <Metric label="ONDA DOMINANTE" value={text(metrics.dominant)} />
        <Metric label="POR MIL PALAVRAS" value={decimal(metrics.perK)} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(result.verdict)}</p>
      <div className="taste-wave">
        {asRows(result.waves).map((wave) => (
          <section key={text(wave.wave)}>
            <header><strong>{text(wave.label)}</strong><span>{count(wave.count)}</span></header>
            <p>{text(wave.hint)}</p>
            <ul>{asList(wave.tells).map((name) => <li key={name}>{name}</li>)}</ul>
          </section>
        ))}
      </div>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Tell</th><th>Onda</th><th>Tipo</th><th>Ocorrências</th><th>Contramedida</th></tr></thead>
          <tbody>{catalog.map((tell) => (
            <tr key={text(tell.id)}>
              <td><strong>{text(tell.name)}</strong><br /><code>{text(tell.id)}</code></td>
              <td><span className={`taste-state ${count(tell.wave) === 3 ? 'is-danger' : count(tell.wave) === 2 ? 'is-warning' : 'is-ok'}`}>{text(tell.waveLabel)}</span></td>
              <td>{text(tell.kind)}</td>
              <td>{asRows(result.rows).filter((row) => text(row.id) === text(tell.id)).map((row) => count(row.count)).reduce((total, value) => total + value, 0) || '—'}</td>
              <td>{text(tell.fix)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function JudgeView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const band = asRow(result.band);
  const dimensions = asRows(result.dimensions);
  const caps = asRows(result.caps);
  const order = asRows(result.order);
  const top = asRows(result.top);
  const complete = metrics.final !== null && metrics.final !== undefined;
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="DIMENSÕES" value={`${count(metrics.dimensions)}/4`} tone={count(metrics.dimensions) === 4 ? 'ok' : 'danger'} />
        <Metric label="MÉDIA PONDERADA" value={decimal(metrics.weighted)} />
        <Metric label="PERDA POR TETO" value={decimal(metrics.capLoss)} tone={count(metrics.capLoss) > 0 ? 'warning' : 'ok'} />
        <Metric label="TETOS" value={count(metrics.caps)} tone={count(metrics.caps) ? 'warning' : 'ok'} />
      </div>
      <div className="taste-score">
        <strong>{complete ? decimal(metrics.final) : '—'}</strong>
        <div>
          <span>{text(band.label)}</span>
          <small>{text(band.meaning)}</small>
          <em>{text(metrics.weakest) ? `eixo mais fraco: ${text(metrics.weakest)} · ` : ''}{count(metrics.signals)} sinais declarados</em>
        </div>
      </div>
      <div className="taste-weights">
        {dimensions.map((dimension) => {
          const score = count(dimension.capped);
          return (
            <div className="taste-weight" key={text(dimension.key)}>
              <div><span>{text(dimension.label)}</span><strong>{decimal(dimension.score)} → {decimal(dimension.capped)}</strong><em>{count(dimension.weight)}%</em></div>
              <div className="taste-track"><i style={{ width: `${Math.max(0, Math.min(10, score)) * 10}%` }} /></div>
            </div>
          );
        })}
      </div>
      {caps.length > 0 && (
        <div className="taste-scroll">
          <table className="taste-table">
            <thead><tr><th>Sinal</th><th>Alvo</th><th>Teto</th><th>Motivo</th></tr></thead>
            <tbody>{caps.map((cap) => (
              <tr key={text(cap.signal)}>
                <td><strong>{text(cap.label)}</strong><br /><code>{text(cap.signal)}</code></td>
                <td>{text(cap.target) === 'global' ? 'nota final' : text(cap.target)}</td>
                <td>{decimal(cap.cap)}</td>
                <td>{text(cap.why)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {order.length > 0 && (
        <ol className="taste-order">
          {order.map((step) => (
            <li className={step.active ? 'is-active' : undefined} key={text(step.step)}>
              <span>{fixed(step.step, 0).padStart(2, '0')}</span>
              <div><strong>{text(step.label)}</strong> — {text(step.action)}{step.active ? ' · comece aqui' : ''}</div>
            </li>
          ))}
        </ol>
      )}
      {top.length > 0 && (
        <div className="taste-note-card">
          <h4>Três problemas</h4>
          {top.map((item) => <p key={text(item.dimension)}><strong>{text(item.dimension)} ({decimal(item.score)})</strong> — {text(item.evidence)}</p>)}
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function LibraryView({ reference }: { reference: Row | null }) {
  if (!reference) {
    return <p className="taste-empty"><AlertTriangle size={14} />A biblioteca vem da API Python. Suba a API com .venv\Scripts\python iniciar.py.</p>;
  }
  const metrics = asRow(reference.metrics);
  const directions = asRows(reference.directions);
  const caps = asRows(reference.caps);
  const waves = asRows(reference.waves);
  return (
    <div className="taste-view">
      <div className="taste-metrics">
        <Metric label="DIREÇÕES" value={count(metrics.directions)} tone="ok" />
        <Metric label="SETORES" value={count(metrics.sectors)} />
        <Metric label="PAPÉIS DE SEÇÃO" value={count(metrics.roles)} />
        <Metric label="TETOS" value={count(metrics.signals)} />
      </div>
      <p className="taste-verdict"><CheckCircle2 size={14} />{text(reference.verdict)}</p>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Direção</th><th>Tese</th><th>Setores</th><th>Ativos</th></tr></thead>
          <tbody>{directions.map((direction) => (
            <tr key={text(direction.id)}>
              <td><strong>{text(direction.name)}</strong><br /><code>{text(direction.id)}</code></td>
              <td>{text(direction.thesis)}</td>
              <td>{asList(direction.sectors).join(', ')}</td>
              <td>{asList(direction.needs).join(', ')}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="taste-note-card">
        <h4>Setores</h4>
        <div className="taste-chips">{asRows(reference.sectors).map((sector) => <span className="taste-chip" key={text(sector.id)}>{text(sector.label)}<small>{text(sector.id)}</small></span>)}</div>
        <h4 style={{ marginTop: 10 }}>Tons</h4>
        <div className="taste-chips">{asRows(reference.tones).map((tone) => <span className="taste-chip" key={text(tone.id)}>{text(tone.label)}<small>{text(tone.id)}</small></span>)}</div>
        <h4 style={{ marginTop: 10 }}>Papéis de seção</h4>
        <div className="taste-chips">{asRows(reference.roles).map((role) => <span className="taste-chip" key={text(role.id)}>{text(role.label)}<small>{text(role.id)}</small></span>)}</div>
      </div>
      <div className="taste-scroll">
        <table className="taste-table">
          <thead><tr><th>Nome</th><th>Sinal</th><th>Alvo</th><th>Teto</th><th>Motivo</th></tr></thead>
          <tbody>{caps.map((cap) => (
            <tr key={text(cap.id)}>
              <td><strong>{text(cap.label)}</strong></td>
              <td><code>{text(cap.id)}</code></td>
              <td>{text(cap.target) === 'global' ? 'nota final' : text(cap.target)}</td>
              <td>{decimal(cap.cap)}</td>
              <td>{text(cap.why)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="taste-wave">
        {waves.map((wave) => (
          <section key={text(wave.label)}>
            <header><strong>{text(wave.label)}</strong><span>{asList(wave.tells).length}</span></header>
            <p>{text(wave.hint)}</p>
            <ul>{asList(wave.tells).map((name) => <li key={name}>{name}</li>)}</ul>
          </section>
        ))}
      </div>
    </div>
  );
}

export function TastePage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<TasteTab>('direction');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);

  const [brief, setBrief] = useState('');
  const [sector, setSector] = useState('');
  const [tone, setTone] = useState('');
  const [sections, setSections] = useState('');
  const [have, setHave] = useState('');
  const [keep, setKeep] = useState('');
  const [seed, setSeed] = useState('');
  const [direction, setDirection] = useState('');
  const [redraws, setRedraws] = useState('');

  const [claims, setClaims] = useState('');
  const [headline, setHeadline] = useState('');
  const [support, setSupport] = useState('');
  const [action, setAction] = useState('');

  const [deck, setDeck] = useState('');
  const [source, setSource] = useState('');
  const [surface, setSurface] = useState<'page' | 'app'>('page');
  const [material, setMaterial] = useState('');
  const [kind, setKind] = useState<'todos' | 'texto' | 'visual' | 'codigo'>('todos');
  const [scores, setScores] = useState('');
  const [signals, setSignals] = useState('');

  const result = execution?.result ?? null;
  const resultMarkdown = useMemo(() => (result && typeof result.markdown === 'string' ? result.markdown : ''), [result]);
  const analysis = result ? text(result.analysis) : '';
  const picked = result ? text(result.sheet && asRow(result.sheet).id) : '';

  useEffect(() => {
    if (!backendOnline || reference) return;
    let active = true;
    void executeSkill('taste.library', {}).then((response) => {
      if (!active || !response.ok || !response.result) return;
      setReference(response.result);
    }).catch(() => { /* a aba Biblioteca mostra o estado offline */ });
    return () => { active = false; };
  }, [backendOnline, executeSkill, reference]);

  const run = async (skillId: string, parameters: Record<string, unknown>) => {
    if (!backendOnline) {
      setError('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.');
      return;
    }
    setBusy(true);
    setError('');
    setExecution(null);
    try {
      const response = await executeSkill(skillId, parameters);
      if (!response.ok) {
        setError(response.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(response);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Falha ao executar a verificação.');
    } finally {
      setBusy(false);
    }
  };

  const toggleSection = (id: string) => {
    const current = sections.split(',').map((item) => item.trim()).filter(Boolean);
    setSections((current.includes(id) ? current.filter((item) => item !== id) : [...current, id]).join(', '));
  };

  const loadSample = () => {
    if (tab === 'direction') {
      setBrief(SAMPLE_BRIEF); setSector('alimentacao'); setTone('quente'); setSections(SAMPLE_SECTIONS);
      setHave('fotografia'); setKeep(''); setSeed(''); setDirection(''); setRedraws(SAMPLE_REDRAWS);
    } else if (tab === 'argument') {
      setBrief(SAMPLE_BRIEF); setClaims(SAMPLE_CLAIMS); setHeadline('Pão de fermentação natural');
      setSupport('Forno a lenha na rua das Palmeiras, desde 2019.'); setAction('Ver o cardápio');
    } else if (tab === 'copy') {
      setDeck(SAMPLE_DECK);
    } else if (tab === 'lint') {
      setSource(SAMPLE_LINT); setSurface('page');
    } else if (tab === 'tells') {
      setMaterial(SAMPLE_TELLS); setKind('todos');
    } else if (tab === 'judge') {
      setScores(SAMPLE_JUDGE); setSignals(SAMPLE_SIGNALS);
    }
    setError('');
  };

  const submitDirection = (event: React.FormEvent) => {
    event.preventDefault();
    if (!brief.trim()) return;
    void run('taste.direction', {
      brief, sector, tone, sections, have, keep, seed, direction, redraws, mode: level,
    });
  };

  const openSheet = (id: string) => {
    setDirection(id);
    void run('taste.direction', {
      brief, sector, tone, sections, have, keep, seed, direction: id, redraws, mode: level,
    });
  };

  const submitArgument = (event: React.FormEvent) => {
    event.preventDefault();
    if (!brief.trim() || !claims.trim()) return;
    void run('taste.argument', { brief, claims, headline, support, action, mode: level });
  };

  const submitCopy = (event: React.FormEvent) => {
    event.preventDefault();
    if (!deck.trim()) return;
    void run('taste.copy', { deck, mode: level });
  };

  const submitLint = (event: React.FormEvent) => {
    event.preventDefault();
    if (!source.trim()) return;
    void run('taste.lint', { source, surface, mode: level });
  };

  const submitTells = (event: React.FormEvent) => {
    event.preventDefault();
    if (!material.trim()) return;
    void run('taste.tells', { text: material, kind, mode: level });
  };

  const submitJudge = (event: React.FormEvent) => {
    event.preventDefault();
    if (!scores.trim()) return;
    void run('taste.judge', { scores, signals, mode: level });
  };

  const copyMarkdown = async () => {
    if (!resultMarkdown) return;
    try {
      await navigator.clipboard.writeText(resultMarkdown);
      pushToast('Parecer copiado', 'O Markdown do resultado está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto do resultado manualmente.', 'warning');
    }
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const hasInput = tab === 'direction' ? Boolean(brief.trim())
    : tab === 'argument' ? Boolean(brief.trim() && claims.trim())
      : tab === 'copy' ? Boolean(deck.trim())
        : tab === 'lint' ? Boolean(source.trim())
          : tab === 'tells' ? Boolean(material.trim())
            : tab === 'judge' ? Boolean(scores.trim())
              : false;
  const roleOptions = asRows(reference?.roles).slice(0, 12);
  const sectorOptions = asRows(reference?.sectors);
  const toneOptions = asRows(reference?.tones);

  return (
    <div className="taste-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">DIREÇÃO DE ARTE · CRÍTICA ESTÁTICA</span>
          <h1>Uma página com sujeito, <span>não com preset</span></h1>
          <p>Sorteia direções determinísticas, exige argumento com prova, mede o deck de copy, varre regras caseiras, confronta o registro datado de tells e fecha a nota com tetos. Nada é renderizado, compilado ou publicado.</p>
        </div>
      </header>

      <section className="panel taste-intro">
        <span className="taste-intro-icon"><Brush size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>Sem sujeito, a direção vira decoração</h2>
          <p>A adaptação do taste-skill é editorial: direção, argumento, copy, linter, tells e júri. Os scripts Node, o navegador de inspeção, os plugins de Claude/Codex e o `npx skills` ficam de fora — o JARVIS só lê o que foi declarado.</p>
        </div>
        <ul className="taste-laws">
          {laws.map((law) => <li key={law.key}><strong>{law.title}</strong><span>{law.text}</span></li>)}
        </ul>
      </section>

      <nav className="taste-tabs" aria-label="Modos da direção de arte">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); if (id === 'library') setExecution(null); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="taste-layout">
        <section className="panel taste-form">
          <header className="taste-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            {tab !== 'library' && (
              <label className="taste-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          {tab !== 'library' && <p className="taste-level-note">{levels.find((item) => item.id === level)?.description}</p>}

          {tab === 'direction' && (
            <form className="form-stack" onSubmit={submitDirection}>
              <label className="field">
                <span>Briefing *</span>
                <textarea value={brief} onChange={(event) => setBrief(event.target.value)} maxLength={4000} rows={3} required placeholder="O que só este sujeito tem: nome, lugar, material, número, rito." />
              </label>
              <div className="taste-split">
                <label className="field">
                  <span>Setor</span>
                  {sectorOptions.length ? (
                    <select value={sector} onChange={(event) => setSector(event.target.value)}>
                      <option value="">livre</option>
                      {sectorOptions.map((item) => <option key={text(item.id)} value={text(item.id)}>{text(item.label)}</option>)}
                    </select>
                  ) : (
                    <input value={sector} onChange={(event) => setSector(event.target.value)} maxLength={80} placeholder="alimentacao" />
                  )}
                </label>
                <label className="field">
                  <span>Tom</span>
                  {toneOptions.length ? (
                    <select value={tone} onChange={(event) => setTone(event.target.value)}>
                      <option value="">livre</option>
                      {toneOptions.map((item) => <option key={text(item.id)} value={text(item.id)}>{text(item.label)}</option>)}
                    </select>
                  ) : (
                    <input value={tone} onChange={(event) => setTone(event.target.value)} maxLength={80} placeholder="quente" />
                  )}
                </label>
              </div>
              <label className="field">
                <span>Seções na ordem</span>
                <input value={sections} onChange={(event) => setSections(event.target.value)} maxLength={2000} placeholder="sobre, vitrine, como-funciona, contato" />
              </label>
              {roleOptions.length > 0 && (
                <div className="taste-chips">
                  {roleOptions.map((role) => {
                    const on = sections.split(',').map((item) => item.trim()).includes(text(role.id));
                    return <button type="button" key={text(role.id)} className={`taste-chip ${on ? 'is-on' : ''}`} onClick={() => toggleSection(text(role.id))}>{text(role.label)}</button>;
                  })}
                </div>
              )}
              <div className="taste-split">
                <label className="field"><span>Ativos que você tem</span><input value={have} onChange={(event) => setHave(event.target.value)} maxLength={400} placeholder="fotografia, interface" /></label>
                <label className="field"><span>Peças da marca</span><input value={keep} onChange={(event) => setKeep(event.target.value)} maxLength={400} placeholder="paleta, tipografia" /></label>
              </div>
              <div className="taste-split">
                <label className="field"><span>Semente</span><input value={seed} onChange={(event) => setSeed(event.target.value)} maxLength={32} placeholder="vazio deriva do briefing" /></label>
                <label className="field">
                  <span>Direção escolhida</span>
                  <input value={direction} onChange={(event) => setDirection(event.target.value)} maxLength={40} placeholder="abra a ficha de uma opção" />
                </label>
              </div>
              <label className="field">
                <span>Redesenhos · peça | motivo</span>
                <textarea className="taste-mono taste-short" value={redraws} onChange={(event) => setRedraws(event.target.value)} maxLength={8000} rows={3} placeholder={SAMPLE_REDRAWS} />
              </label>
              <p className="taste-note">O sorteio é determinístico pela semente. Redesenhar exige um motivo com 20 caracteres ou mais; trocar a direção inteira é o caso mais caro.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <Compass size={15} />}Sortear direções</button>
              </div>
            </form>
          )}

          {tab === 'argument' && (
            <form className="form-stack" onSubmit={submitArgument}>
              <label className="field"><span>Sujeito *</span><input value={brief} onChange={(event) => setBrief(event.target.value)} maxLength={4000} required placeholder="Uma linha sobre o que está sendo argumentado." /></label>
              <label className="field">
                <span>Afirmações e provas *</span>
                <textarea className="taste-mono" value={claims} onChange={(event) => setClaims(event.target.value)} maxLength={50000} rows={8} required placeholder={'papel | o que a seção afirma | o que prova\nsobre | A massa descansa 18 horas | foto do forno'} />
              </label>
              <label className="field"><span>Título</span><input value={headline} onChange={(event) => setHeadline(event.target.value)} maxLength={400} placeholder="Pão de fermentação natural" /></label>
              <div className="taste-split">
                <label className="field"><span>Linha de apoio</span><input value={support} onChange={(event) => setSupport(event.target.value)} maxLength={800} placeholder="Forno a lenha na rua das Palmeiras." /></label>
                <label className="field"><span>Ação principal</span><input value={action} onChange={(event) => setAction(event.target.value)} maxLength={200} placeholder="Ver o cardápio" /></label>
              </div>
              <p className="taste-note">Cada seção precisa de uma afirmação e uma prova. Número, prêmio ou avaliação sem fonte vira <code>prova sem fonte</code> e precisa sair da peça.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <FileText size={15} />}Auditar argumento</button>
              </div>
            </form>
          )}

          {tab === 'copy' && (
            <form className="form-stack" onSubmit={submitCopy}>
              <label className="field">
                <span>Deck de copy *</span>
                <textarea className="taste-mono" value={deck} onChange={(event) => setDeck(event.target.value)} maxLength={50000} rows={10} required placeholder={'manchete | Pão de fermentação natural\napoio | Forno a lenha na rua das Palmeiras.\nacao | Ver o cardápio'} />
              </label>
              <p className="taste-note">Papéis: <code>manchete</code>, <code>apoio</code>, <code>corpo</code>, <code>acao</code>, <code>nav</code>, <code>legenda</code>, <code>statement</code>, <code>rotulo</code>, <code>eyebrow</code>. A sobrancelha é bloqueio.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <PenLine size={15} />}Medir deck</button>
              </div>
            </form>
          )}

          {tab === 'lint' && (
            <form className="form-stack" onSubmit={submitLint}>
              <label className="field">
                <span>HTML ou CSS *</span>
                <textarea className="taste-mono" value={source} onChange={(event) => setSource(event.target.value)} maxLength={200000} rows={12} required placeholder={'<!doctype html>\n<html lang="pt-BR">\n  … CSS e HTML no mesmo bloco'} />
              </label>
              <label className="field">
                <span>Superfície</span>
                <select value={surface} onChange={(event) => setSurface(event.target.value as 'page' | 'app')}>
                  <option value="page">Página · compara com o estudo</option>
                  <option value="app">Aplicativo · desliga fio, mono e numeração</option>
                </select>
              </label>
              <p className="taste-note">Blocos em <code>&lt;pre&gt;</code>, <code>&lt;code&gt;</code>, tabelas, formulários, <code>data-ui</code>, comentários e linhas com <code>taste-skill-ignore</code> ficam isentos. O exemplo carrega problemas propositais.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <ScanEye size={15} />}Varrer regras</button>
              </div>
            </form>
          )}

          {tab === 'tells' && (
            <form className="form-stack" onSubmit={submitTells}>
              <label className="field">
                <span>Material *</span>
                <textarea className="taste-mono" value={material} onChange={(event) => setMaterial(event.target.value)} maxLength={200000} rows={10} required placeholder={'Copy, HTML ou CSS da página. O registro reconhece motivos datados em três ondas.'} />
              </label>
              <label className="field">
                <span>Tipo</span>
                <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}>
                  <option value="todos">todos</option>
                  <option value="texto">texto</option>
                  <option value="visual">visual</option>
                  <option value="codigo">código</option>
                </select>
              </label>
              <p className="taste-note">Onda 1 (2023): vidro, gradiente roxo, ícone genérico. Onda 2 (2024–2025): micro-rótulo, numeração, fio de 1 px, mobília editorial. Onda 3 (2026): creme e terracota, serifa apertada, manchete-parágrafo.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <Tags size={15} />}Confrontar tells</button>
              </div>
            </form>
          )}

          {tab === 'judge' && (
            <form className="form-stack" onSubmit={submitJudge}>
              <label className="field">
                <span>Notas por dimensão *</span>
                <textarea className="taste-mono" value={scores} onChange={(event) => setScores(event.target.value)} maxLength={50000} rows={8} required placeholder={'design | 8 | margens e grid com medida\nusabilidade | 7 | foco visível e formulário curto\ncriatividade | 4 | a ideia serviria a qualquer um\nconteudo | 6 | falta o prazo de entrega'} />
              </label>
              <label className="field">
                <span>Sinais de teto · sinal | sim/não</span>
                <textarea className="taste-mono taste-short" value={signals} onChange={(event) => setSignals(event.target.value)} maxLength={20000} rows={4} placeholder={SAMPLE_SIGNALS} />
              </label>
              <p className="taste-note">Pesos fixos: design 40 · usabilidade 30 · criatividade 20 · conteúdo 10. A revisão exige as quatro notas; não existe nota parcial. Cada sinal marcado como <code>sim</code> aplica o teto correspondente.</p>
              <div className="taste-form-actions">
                <button type="button" className="taste-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="taste-spin" /> : <Sparkles size={15} />}Calcular júri</button>
              </div>
            </form>
          )}

          {tab === 'library' && (
            <div className="taste-form-static">
              <p className="taste-note">A biblioteca reúne o vocabulário das skills: 12 direções, 10 setores, 7 tons, 16 papéis de seção, 4 dimensões de júri, 16 tetos e 3 ondas de tells. Ela é própria e embutida — não é a lista do upstream.</p>
              <div className="taste-note-card">
                <h4>Como a nota fecha</h4>
                <p>Média ponderada das quatro dimensões; cada teto marcado reduz a nota ou a dimensão até o limite. O resultado mostra a média bruta, a perda e a banda.</p>
              </div>
              <div className="taste-note-card">
                <h4>O que fica de fora</h4>
                <p>Scripts Node, Chromium de inspeção, plugins de Claude/Codex, marketplace e qualquer execução do upstream. Aqui tudo é leitura estática do que você declara.</p>
              </div>
              <button type="button" className="button button-primary" onClick={() => { setTab('direction'); setError(''); }}><ArrowRight size={15} />Sortear uma direção</button>
            </div>
          )}

          {error && <p className="taste-error" role="alert"><AlertTriangle size={15} />{error}</p>}
        </section>

        <section className="panel taste-result" aria-live="polite">
          <header className="taste-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{result ? analysisLabels[analysis] ?? 'Parecer' : tab === 'library' ? 'Biblioteca' : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="taste-result-actions">
                <span className="taste-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="taste-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
              </div>
            )}
          </header>

          {!result && tab !== 'library' && (
            <div className="taste-placeholder">
              <span><Layers size={18} /></span>
              <strong>Somente leitura</strong>
              <p>O parecer aparece aqui com evidência por achado, veredito e limites declarados. Nada é renderizado, compilado, publicado ou enviado a um provedor de design.</p>
              <ul>
                <li>Direção: três opções determinísticas e a ficha da escolhida.</li>
                <li>Argumento: afirmação e prova por seção, com orçamento de título.</li>
                <li>Copy: título, apoio, corpo, ações, navegação e micro-tipografia.</li>
                <li>Regras: 29 varreduras lexicais com isenções declaradas.</li>
                <li>Tells: três ondas datadas, com contramedida por motivo.</li>
                <li>Júri: média ponderada, tetos e ordem de correção.</li>
              </ul>
            </div>
          )}

          {tab === 'library' && <LibraryView reference={reference} />}

          {result && (
            <>
              {analysis === 'direction' && <DirectionView result={result} picked={picked} onPick={openSheet} />}
              {analysis === 'argument' && <ArgumentView result={result} />}
              {analysis === 'copy' && <CopyView result={result} />}
              {analysis === 'lint' && <LintView result={result} />}
              {analysis === 'tells' && <TellsView result={result} />}
              {analysis === 'judge' && <JudgeView result={result} />}
              <Limitations items={result.limitations} />
              <details className="taste-json">
                <summary>Resposta completa (JSON)</summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
