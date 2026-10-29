import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Compass,
  Download,
  FileJson,
  Frame,
  GitBranch,
  Layers,
  LoaderCircle,
  PenTool,
  Ruler,
  ScanEye,
  Tags,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import { EditorialSection } from './EditorialSection';
import '../diagramas.css';

type DiagramTab = 'type' | 'spec' | 'layout' | 'render' | 'legend' | 'delivery' | 'library';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';
type Format = 'html' | 'svg' | 'mermaid' | 'ascii' | 'dot';

const tabs: Array<{ id: DiagramTab; label: string; hint: string; icon: typeof Compass }> = [
  { id: 'type', label: 'Tipo', hint: 'Pergunta → diagrama', icon: Compass },
  { id: 'spec', label: 'IR', hint: 'Validar a especificação', icon: FileJson },
  { id: 'layout', label: 'Layout', hint: 'Medir o desenho', icon: Ruler },
  { id: 'render', label: 'Desenho', hint: 'HTML, SVG e texto', icon: PenTool },
  { id: 'legend', label: 'Legenda', hint: 'Variantes e presets', icon: Tags },
  { id: 'delivery', label: 'Entrega', hint: 'Gates em ordem', icon: GitBranch },
  { id: 'library', label: 'Catálogo', hint: 'Vocabulário do IR', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string; description: string }> = [
  { id: 'lite', label: 'Lite', description: 'Só o que bloqueia.' },
  { id: 'full', label: 'Full', description: 'Padrão: bloqueios e correções.' },
  { id: 'ultra', label: 'Ultra', description: 'Inclui perguntas antes de liberar.' },
];

const laws = [
  { key: 'verdade', title: 'Verdade antes do espetáculo', text: 'O desenho só afirma o que a especificação declara. Setas, protocolos e condições precisam existir no IR.' },
  { key: 'narrativa', title: 'Uma narrativa espacial', text: 'Caminho principal vizinho na ordem de leitura. Ramo fica acima ou abaixo do dono, nunca no meio do corredor.' },
  { key: 'legenda', title: 'Legenda honesta', text: 'Quatro variantes com significado fixo. A legenda automática lista só o que o desenho usa; esconder linha com sentido é defeito.' },
  { key: 'prova', title: 'Prova portátil', text: 'Um HTML com SVG inline, CSS embutido e nenhum runtime. Abre de um pendrive e imprime sem servidor.' },
];

const formats: Array<{ id: Format; label: string; description: string }> = [
  { id: 'html', label: 'HTML', description: 'Página autocontida com SVG inline.' },
  { id: 'svg', label: 'SVG', description: 'Só o desenho, para editar ou embutir.' },
  { id: 'mermaid', label: 'Mermaid', description: 'Texto para outra ferramenta abrir.' },
  { id: 'ascii', label: 'Texto', description: 'Mapa em monoespaçado.' },
  { id: 'dot', label: 'DOT', description: 'Graphviz para quem já usa.' },
];

const analysisLabels: Record<string, string> = {
  type: 'Roteiro de tipo',
  spec: 'Validação',
  layout: 'Layout medido',
  render: 'Desenho',
  legend: 'Legenda e presets',
  delivery: 'Contrato de entrega',
  library: 'Catálogo',
};

const sampleRequest = 'Quero mostrar onde o tempo foi num checkout lento, com a consulta ao banco e a cobrança do cartão.';

const sampleSpec = `{
  "tipo": "arquitetura",
  "titulo": "Checkout da loja",
  "subtitulo": "Do clique ao pedido pago, com a fronteira de confiança desenhada.",
  "saida": "checkout.html",
  "preset": "classico",
  "legenda": "auto",
  "componentes": [
    { "id": "loja", "rotulo": "Loja", "tipo": "frontend", "subrotulo": "web e aplicativo", "faixa": 0 },
    { "id": "checkout", "rotulo": "Checkout", "tipo": "backend", "subrotulo": "carrinho e preço", "faixa": 1 },
    { "id": "pagamentos", "rotulo": "Pagamentos", "tipo": "security", "subrotulo": "tokenização", "faixa": 1 },
    { "id": "pedidos", "rotulo": "Pedidos", "tipo": "database", "subrotulo": "fonte da verdade", "faixa": 2 },
    { "id": "fila", "rotulo": "Fila", "tipo": "messagebus", "subrotulo": "confirmação", "faixa": 2 }
  ],
  "conexoes": [
    { "de": "loja", "para": "checkout", "rotulo": "HTTPS" },
    { "de": "checkout", "para": "pagamentos", "rotulo": "cobra" },
    { "de": "checkout", "para": "pedidos", "rotulo": "grava", "variante": "emphasis" },
    { "de": "pedidos", "para": "fila", "rotulo": "evento", "variante": "dashed" }
  ],
  "fronteiras": [
    { "id": "pci", "rotulo": "Perímetro PCI", "membros": ["pagamentos"] }
  ],
  "cartoes": [
    { "cor": "cyan", "titulo": "Contrato", "itens": ["Toda chamada é HTTPS.", "O pedido só existe depois do commit."] },
    { "cor": "emerald", "titulo": "Assíncrono", "itens": ["A confirmação para a fila não bloqueia a resposta."] }
  ]
}`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const gateTone: Record<string, string> = {
  passou: 'is-ok', 'passou com ressalvas': 'is-warning', falhou: 'is-danger',
  'nao-executado': 'is-warning', 'nao-solicitada': 'is-warning', pendente: 'is-warning',
};
const gateLabel: Record<string, string> = {
  passou: 'passou', 'passou com ressalvas': 'ressalvas', falhou: 'falhou',
  'nao-executado': 'não executado', 'nao-solicitada': 'não solicitada', pendente: 'pendente',
};

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Limitations({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="diagram-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nenhum candidato pelas regras estáticas.</p>;
  return (
    <div className="diagram-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`diagram-finding is-${group}`} key={`${text(finding.id)}-${text(finding.kind)}-${text(finding.location)}`}>
            <header>
              <span className="diagram-group">{groupLabel[group] ?? group}</span>
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

function TypeView({ result, onUse }: { result: Row; onUse: (skeleton: Row) => void }) {
  const metrics = asRow(result.metrics);
  const schema = asRow(result.esquema);
  const skeleton = asRow(result.esqueleto);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="TIPO" value={text(result.rotulo)} />
        <Metric label="PONTOS" value={count(metrics.pontuacao)} tone={count(metrics.pontuacao) ? 'ok' : 'warning'} />
        <Metric label="ORÇAMENTO" value={`${count(schema.orcamento)} nós`} />
        <Metric label="CANDIDATOS" value={count(metrics.candidatos)} tone={count(metrics.candidatos) > 1 ? 'warning' : 'ok'} />
      </div>
      <p className="diagram-verdict"><Compass size={14} />{text(result.verdict)}</p>
      <p className="diagram-note">{text(result.porQue)}</p>
      <div className="diagram-candidates">
        {asRows(result.rows).map((row) => (
          <article className={`diagram-candidate ${text(row.tipo) === text(result.tipo) ? 'is-picked' : ''}`} key={text(row.tipo)}>
            <strong>{text(row.rotulo)}<small>{text(row.tipo)}</small></strong>
            <span>{text(row.pergunta)}<small>Sinais: {text(row.sinais)}</small></span>
            <span className="diagram-score">{count(row.pontos)}</span>
          </article>
        ))}
      </div>
      <FindingList findings={asRows(result.findings)} />
      <div className="diagram-skeleton">
        <span className="diagram-hint">Esqueleto do tipo escolhido — cole na aba IR e troque pelos fatos reais.</span>
        <pre className="diagram-code">{JSON.stringify(skeleton, null, 2)}</pre>
        <div className="diagram-skeleton-actions">
          <button type="button" className="button button-primary" onClick={() => onUse(skeleton)}><ArrowRight size={14} />Usar este esqueleto</button>
        </div>
      </div>
    </div>
  );
}

function SpecView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const counts = asRow(result.contagens);
  const notes = asList(result.avisos);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="NÓS" value={count(counts.nos)} tone={count(counts.nos) > count(metrics.orcamento) ? 'warning' : 'ok'} />
        <Metric label="RELAÇÕES" value={count(counts.arestas)} />
        <Metric label="REGIÕES" value={count(counts.regioes)} />
        <Metric label="CARTÕES" value={count(counts.cartoes)} tone={count(counts.cartoes) > 4 ? 'warning' : undefined} />
      </div>
      <p className="diagram-verdict"><FileJson size={14} />{text(result.verdict)}</p>
      <div className="diagram-vocab">
        <span className="is-on">{text(result.tipo)}</span>
        <span>{count(metrics.largura)} × {count(metrics.altura)} px</span>
        <span>orçamento {count(metrics.orcamento)}</span>
        <span>{count(metrics.cruzamentos)} cruzamento(s)</span>
      </div>
      {notes.length > 0 && <ul className="diagram-traps">{notes.map((note) => <li key={note}>{note}</li>)}</ul>}
      <FindingList findings={asRows(result.findings)} />
      <details className="diagram-json">
        <summary>IR normalizado (copiar de volta)</summary>
        <pre>{JSON.stringify(result.normalizado, null, 2)}</pre>
      </details>
    </div>
  );
}

function LayoutView({ result }: { result: Row }) {
  const metrics = asRow(result.metricas);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="CANVAS" value={`${count(metrics.largura)} × ${count(metrics.altura)}`} />
        <Metric label="CRUZAMENTOS" value={count(metrics.cruzamentos)} tone={count(metrics.cruzamentos) ? 'warning' : 'ok'} />
        <Metric label="COLISÕES" value={count(metrics.colisoes)} tone={count(metrics.colisoes) ? 'danger' : 'ok'} />
        <Metric label="FOLGA" value={count(metrics.rotulosApertados)} tone={count(metrics.rotulosApertados) ? 'warning' : 'ok'} />
        <Metric label="PREENCHIMENTO" value={`${count(metrics.preenchimento)}%`} tone={count(metrics.preenchimento) < 20 ? 'warning' : 'ok'} />
      </div>
      <p className="diagram-verdict"><Ruler size={14} />{text(result.verdict)}</p>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Nó</th><th>x</th><th>y</th><th>Largura</th><th>Altura</th><th>Linha</th></tr></thead>
          <tbody>{asRows(result.grade).map((row) => (
            <tr key={text(row.id)}>
              <td><strong>{text(row.id)}</strong></td>
              <td>{count(row.x)}</td>
              <td>{count(row.y)}</td>
              <td>{count(row.largura)}</td>
              <td>{count(row.altura)}</td>
              <td>{count(row.linha)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <span className="diagram-hint">Mapa em texto — o mesmo desenho sem navegador.</span>
      <pre className="diagram-code">{text(result.mapa)}</pre>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function RenderView({ result, onFormat, onCopy }: { result: Row; onFormat: (format: Format) => void; onCopy: () => void }) {
  const [showCode, setShowCode] = useState(false);
  const format = text(result.formato) as Format;
  const content = text(result.conteudo);
  const legend = asRows(result.legenda);
  const canPreview = format === 'html' || format === 'svg';

  const download = () => {
    const extension: Record<string, string> = { html: 'html', svg: 'svg', mermaid: 'mmd', ascii: 'txt', dot: 'dot' };
    const mime: Record<string, string> = { html: 'text/html', svg: 'image/svg+xml', mermaid: 'text/plain', ascii: 'text/plain', dot: 'text/plain' };
    const blob = new Blob([content], { type: `${mime[format] ?? 'text/plain'};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = text(result.saida) || `diagrama.${extension[format] ?? 'txt'}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="FORMATO" value={text(result.rotuloFormato)} />
        <Metric label="TAMANHO" value={`${count(result.bytes).toLocaleString('pt-BR')} B`} />
        <Metric label="NÓS" value={count(asRow(result.metrics).nos)} />
        <Metric label="LEGENDA" value={`${legend.length} item(ns)`} />
      </div>
      <p className="diagram-verdict"><PenTool size={14} />{text(result.verdict)}</p>
      <div className="diagram-toolbar">
        {formats.map((item) => (
          <button key={item.id} type="button" className={format === item.id ? 'is-on' : undefined} onClick={() => onFormat(item.id)}>{item.label}</button>
        ))}
        <button type="button" onClick={onCopy}><Clipboard size={13} />Copiar</button>
        <button type="button" onClick={download}><Download size={13} />Baixar</button>
        {canPreview && <button type="button" className={showCode ? 'is-on' : undefined} onClick={() => setShowCode((value) => !value)}><ScanEye size={13} />{showCode ? 'Ver prévia' : 'Ver código'}</button>}
      </div>
      {canPreview && !showCode ? (
        <iframe className="diagram-frame" title={`Prévia do diagrama em ${format}`} sandbox="" srcDoc={content} />
      ) : (
        <pre className="diagram-code">{content}</pre>
      )}
      <span className="diagram-hint">A prévia roda em sandbox sem scripts. O arquivo baixado abre sozinho, sem servidor e sem dependência externa.</span>
      {legend.length > 0 && (
        <ul className="diagram-legend">
          {legend.map((entry) => (
            <li key={text(entry.variante)}>
              <span className={`line ${text(entry.traco) === 'solid' ? '' : 'is-dashed'}`} style={{ ['--cor' as string]: text(entry.cor) }} />
              {text(entry.rotulo)}
            </li>
          ))}
        </ul>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function LegendView({ result }: { result: Row }) {
  const policy = asRow(result.politicaDeMovimento);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="TIPO" value={text(result.tipo)} />
        <Metric label="PRESET" value={text(result.preset)} />
        <Metric label="VARIANTES EM USO" value={count(asRow(result.metrics).variantes)} />
        <Metric label="ENTRADAS" value={asRows(result.entradas).length} />
      </div>
      <p className="diagram-verdict"><Tags size={14} />{text(result.verdict)}</p>
      <div className="diagram-presets">
        {asRows(result.presets).map((preset) => (
          <article className="diagram-preset" key={text(preset.preset)}>
            <header><strong>{text(preset.rotulo)}</strong><code>{text(preset.preset)}</code></header>
            <div className="diagram-swatch">
              <span style={{ background: text(preset.papel) }} />
              <span style={{ background: text(preset.tinta) }} />
              <span style={{ background: text(preset.acento) }} />
            </div>
            <p>{text(preset.contraste)} de contraste · {text(preset.papel)}</p>
          </article>
        ))}
      </div>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Variante</th><th>Rótulo</th><th>Traço</th><th>Cor</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={text(row.variante)}>
              <td><code>{text(row.variante)}</code></td>
              <td>{text(row.rotulo)}</td>
              <td>{text(row.traco) === 'solid' ? 'linha' : 'tracejada'}</td>
              <td><span className="diagram-chip">{text(row.cor)}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="diagram-note-card">
        <h4>Política de movimento</h4>
        <p><strong>Padrão:</strong> {text(policy.padrao)}</p>
        <p><strong>Desenho denso:</strong> {text(policy.denso)}</p>
        <p><strong>Dono:</strong> {text(policy.dono)}</p>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function DeliveryView({ result }: { result: Row }) {
  const summary = asRow(result.resumo);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="GATES" value={count(asRow(result.metrics).gates)} />
        <Metric label="FALHAS" value={count(asRow(result.metrics).falhas)} tone={count(asRow(result.metrics).falhas) ? 'danger' : 'ok'} />
        <Metric label="PAROU EM" value={text(result.parouEm) || 'nenhum'} tone={text(result.parouEm) ? 'danger' : 'ok'} />
        <Metric label="VISUAL" value={text(result.visualReview) === 'requested' ? 'pedida' : 'não pedida'} />
      </div>
      <p className="diagram-verdict"><GitBranch size={14} />{text(result.verdict)}</p>
      <div className="diagram-gates">
        {asRows(result.gates).map((gate, index) => (
          <article className="diagram-gate" key={text(gate.gate)}>
            <strong>{String(index + 1).padStart(2, '0')} · {text(gate.rotulo)}</strong>
            <p>{text(gate.evidencia)}</p>
            <span className={`diagram-state ${gateTone[text(gate.status)] ?? ''}`}>{gateLabel[text(gate.status)] ?? text(gate.status)}</span>
          </article>
        ))}
      </div>
      <details className="diagram-json" open>
        <summary>Resumo para gravar junto do HTML</summary>
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </details>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function LibraryView({ reference }: { reference: Row | null }) {
  if (!reference) return <p className="diagram-empty"><LoaderCircle size={14} className="diagram-spin" />Carregando o catálogo do núcleo…</p>;
  const limits = asRow(reference.limites);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="TIPOS" value={asRows(reference.tipos).length} />
        <Metric label="NÓS" value={asRows(reference.nos).length} />
        <Metric label="PRESETS" value={asRows(reference.presets).length} />
        <Metric label="FORMATOS" value={asRows(reference.formatos).length} />
      </div>
      <p className="diagram-verdict"><BookOpen size={14} />{text(reference.verdict)}</p>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Tipo</th><th>Pergunta que responde</th><th>Arrays</th><th>Orçamento</th></tr></thead>
          <tbody>{asRows(reference.tipos).map((row) => (
            <tr key={text(row.tipo)}>
              <td><strong>{text(row.rotulo)}</strong><br /><code>{text(row.tipo)}</code></td>
              <td>{text(row.pergunta)}</td>
              <td><code>{text(row.arrays)}</code><br /><small>{text(row.opcional)}</small></td>
              <td>{count(row.orcamento)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <span className="diagram-hint">Componentes</span>
      <div className="diagram-vocab">{asRows(reference.nos).map((item) => <span key={text(item.tipo)}>{text(item.rotulo)}</span>)}</div>
      <span className="diagram-hint">Estados de ciclo de vida</span>
      <div className="diagram-vocab">{asRows(reference.ciclo).map((item) => <span key={text(item.tipo)}>{text(item.rotulo)}</span>)}</div>
      <span className="diagram-hint">Tipos de classe e relações</span>
      <div className="diagram-vocab">
        {asRows(reference.classes).map((item) => <span key={text(item.tipo)}>{text(item.rotulo)}</span>)}
        {asRows(reference.relacoes).map((item) => <span key={text(item.tipo)}>{text(item.rotulo)} · {text(item.notacao)}</span>)}
      </div>
      <div className="diagram-presets">
        {asRows(reference.presets).map((preset) => (
          <article className="diagram-preset" key={text(preset.preset)}>
            <header><strong>{text(preset.rotulo)}</strong><code>{text(preset.preset)}</code></header>
            <div className="diagram-swatch">
              <span style={{ background: text(preset.papel) }} />
              <span style={{ background: text(preset.tinta) }} />
              <span style={{ background: text(preset.acento) }} />
            </div>
            <p>{text(preset.papel)} · {text(preset.acento)}</p>
          </article>
        ))}
      </div>
      <div className="diagram-note-card">
        <h4>Limites do IR</h4>
        <p>{count(limits.nos)} nós · {count(limits.arestas)} relações · {count(limits.rotulo)} caracteres por rótulo · {count(limits.cartoes)} cartões · {count(limits.especificacao).toLocaleString('pt-BR')} caracteres de especificação.</p>
      </div>
      <Limitations items={reference.limitations} />
    </div>
  );
}

export function DiagramPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [mode, setMode] = useState<'ir' | 'editorial'>('ir');
  const [tab, setTab] = useState<DiagramTab>('type');
  const [view, setView] = useState<DiagramTab>('type');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);
  const [pedido, setPedido] = useState(sampleRequest);
  const [audience, setAudience] = useState('');
  const [spec, setSpec] = useState(sampleSpec);
  const [format, setFormat] = useState<Format>('html');
  const [legendType, setLegendType] = useState('');
  const [legendPreset, setLegendPreset] = useState('');
  const [legendMode, setLegendMode] = useState('');
  const [legendSpec, setLegendSpec] = useState('');
  const [visualReview, setVisualReview] = useState<'nao-solicitada' | 'pedida'>('nao-solicitada');
  const [capture, setCapture] = useState<'nao' | 'sim'>('nao');

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('diagram.library', {});
        if (active && response.ok) setReference(asRow(response.result));
      } catch {
        if (active) setReference(null);
      }
    })();
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

  const result = execution?.ok ? asRow(execution.result) : null;
  const resultMarkdown = useMemo(() => text(result?.markdown), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>, next: DiagramTab) => {
    if (!backendOnline) {
      setError('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi desenhado.');
      return;
    }
    setBusy(true);
    setError('');
    setExecution(null);
    setView(next);
    try {
      const response = await executeSkill(skillId, parameters);
      if (!response.ok) {
        setError(response.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(response);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Falha ao executar a skill.');
    } finally {
      setBusy(false);
    }
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

  const copyContent = async () => {
    const content = text(result?.conteudo);
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      pushToast('Desenho copiado', `O conteúdo em ${text(result?.formato)} está na área de transferência.`);
    } catch {
      pushToast('Não foi possível copiar', 'Use o botão Baixar ou selecione o código manualmente.', 'warning');
    }
  };

  const submitType = (event: React.FormEvent) => {
    event.preventDefault();
    if (!pedido.trim()) return;
    void run('diagram.type', { pedido, plateia: audience, detalhe: 'resumo' }, 'type');
  };

  const submitSpec = (event: React.FormEvent) => {
    event.preventDefault();
    if (!spec.trim()) return;
    void run('diagram.spec', { especificacao: spec, modo: level }, 'spec');
  };

  const submitLayout = (event: React.FormEvent) => {
    event.preventDefault();
    if (!spec.trim()) return;
    void run('diagram.layout', { especificacao: spec, modo: level }, 'layout');
  };

  const submitRender = (event: React.FormEvent, nextFormat: Format = format) => {
    event.preventDefault();
    if (!spec.trim()) return;
    void run('diagram.render', { especificacao: spec, formato: nextFormat, modo: level }, 'render');
  };

  const submitLegend = (event: React.FormEvent) => {
    event.preventDefault();
    void run('diagram.legend', {
      tipo: legendType, preset: legendPreset, legenda: legendMode, especificacao: legendSpec, modo: level,
    }, 'legend');
  };

  const submitDelivery = (event: React.FormEvent) => {
    event.preventDefault();
    if (!spec.trim()) return;
    void run('diagram.delivery', {
      especificacao: spec, modo: level, checagem_visual: visualReview, captura: capture,
    }, 'delivery');
  };

  const useSkeleton = (skeleton: Row) => {
    setSpec(JSON.stringify(skeleton, null, 2));
    setTab('spec');
    setView('spec');
    setExecution(null);
    setError('');
  };

  const loadSample = () => {
    if (tab === 'type') {
      setPedido(sampleRequest);
      setAudience('');
    } else if (tab === 'legend') {
      setLegendType(''); setLegendPreset(''); setLegendMode(''); setLegendSpec('');
    } else {
      setSpec(sampleSpec);
    }
    setError('');
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const hasInput = tab === 'type' ? Boolean(pedido.trim())
    : tab === 'library' ? false
      : tab === 'legend' ? true
        : Boolean(spec.trim());
  const requiresLevel = tab === 'spec' || tab === 'layout' || tab === 'render' || tab === 'legend' || tab === 'delivery';

  return (
    <div className="diagram-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">DIAGRAMAS · IR VALIDADO, CAMADA EDITORIAL</span>
          <h1>Um desenho que se explica <span>sem runtime</span></h1>
          <p>Duas camadas: o IR desenha com especificação JSON própria, layout medido e entrega em HTML autocontido; a camada editorial escolhe tipo e orçamento, mede a marca, confere conectores e escreve o recibo da importação. Nenhuma das duas abre navegador.</p>
        </div>
      </header>

      <nav className="diagram-modes" aria-label="Camadas dos diagramas">
        <button type="button" className={mode === 'ir' ? 'is-active' : undefined} onClick={() => setMode('ir')} aria-pressed={mode === 'ir'}>
          <PenTool size={16} />
          <span>Desenho por IR<small>especificação, layout e arquivo</small></span>
        </button>
        <button type="button" className={mode === 'editorial' ? 'is-active' : undefined} onClick={() => setMode('editorial')} aria-pressed={mode === 'editorial'}>
          <Frame size={16} />
          <span>Camada editorial<small>tipo, marca, conectores e recibo</small></span>
        </button>
      </nav>

      {mode === 'editorial' ? <EditorialSection /> : (
      <>
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Frame size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>A verdade do diagrama é a especificação</h2>
          <p>A adaptação do archify é estática: tipo, IR, geometria, desenho, legenda e contrato de entrega. O CLI de 288 KB, o template de 786 KB, o `archify.zip`, os plugins de agente e a inspeção de Chrome ficam de fora — o JARVIS só desenha o que você declarou.</p>
        </div>
        <ul className="diagram-laws">
          {laws.map((law) => <li key={law.key}><strong>{law.title}</strong><span>{law.text}</span></li>)}
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos dos diagramas">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); if (id === 'library') setExecution(null); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="diagram-layout">
        <section className="panel diagram-form">
          <header className="diagram-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            {requiresLevel && (
              <label className="diagram-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          {requiresLevel && <p className="diagram-level-note">{levels.find((item) => item.id === level)?.description}</p>}

          {tab === 'type' && (
            <form className="form-stack" onSubmit={submitType}>
              <label className="field">
                <span>O que precisa ser explicado *</span>
                <textarea value={pedido} onChange={(event) => setPedido(event.target.value)} maxLength={4000} rows={4} required placeholder="A pergunta que o desenho responde: componentes, ordem, chamadas, dados, estados, tabelas ou tempo." />
              </label>
              <label className="field">
                <span>Quem lê</span>
                <input value={audience} onChange={(event) => setAudience(event.target.value)} maxLength={120} placeholder="Opcional: time de plantão, diretoria, quem chega agora" />
              </label>
              <p className="diagram-note">O roteador pontua dez tipos por sinal no pedido. Empate não é escondido: vira aviso com a pergunta que separa cada candidato. O esqueleto volta pronto para colar na aba IR.</p>
              <div className="diagram-form-actions">
                <button type="button" className="diagram-sample" onClick={loadSample}><Compass size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="diagram-spin" /> : <Compass size={15} />}Escolher tipo</button>
              </div>
            </form>
          )}

          {(tab === 'spec' || tab === 'layout' || tab === 'render' || tab === 'delivery') && (
            <form className="form-stack" onSubmit={tab === 'spec' ? submitSpec : tab === 'layout' ? submitLayout : tab === 'render' ? submitRender : submitDelivery}>
              <label className="field">
                <span>Especificação JSON *</span>
                <textarea className="diagram-mono" value={spec} onChange={(event) => setSpec(event.target.value)} maxLength={200000} rows={14} required spellCheck={false} placeholder='{ "tipo": "arquitetura", "titulo": "…", "componentes": [ … ] }' />
              </label>
              {tab === 'render' && (
                <label className="field">
                  <span>Formato</span>
                  <select value={format} onChange={(event) => setFormat(event.target.value as Format)}>
                    {formats.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.description}</option>)}
                  </select>
                </label>
              )}
              {tab === 'delivery' && (
                <div className="diagram-split">
                  <label className="field">
                    <span>Revisão visual</span>
                    <select value={visualReview} onChange={(event) => setVisualReview(event.target.value as 'nao-solicitada' | 'pedida')}>
                      <option value="nao-solicitada">não solicitada</option>
                      <option value="pedida">pedida · alguém vai olhar</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Captura de tela</span>
                    <select value={capture} onChange={(event) => setCapture(event.target.value as 'nao' | 'sim')}>
                      <option value="nao">não</option>
                      <option value="sim">sim · declarar como não executada</option>
                    </select>
                  </label>
                </div>
              )}
              <p className="diagram-note">
                {tab === 'spec' && 'O IR é validado contra o vocabulário do tipo: ids, pontas, hierarquia, datas, orçamento e rótulos. O IR normalizado volta em JSON para copiar.'}
                {tab === 'layout' && 'O layout é determinístico: mesmas coordenadas a cada execução. Cruzamento, colisão, folga de rótulo e leque são medidos, não estimados.'}
                {tab === 'render' && 'O HTML carrega SVG inline e CSS embutido; o SVG é XML puro; Mermaid, texto e DOT são exportações honestas para outra ferramenta.'}
                {tab === 'delivery' && 'Os gates rodam em ordem e param no primeiro que falha. Navegador e revisão visual nunca são marcados como feitos quando não foram.'}
              </p>
              <div className="diagram-form-actions">
                <button type="button" className="diagram-sample" onClick={loadSample}><Frame size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>
                  {busy ? <LoaderCircle size={15} className="diagram-spin" />
                    : tab === 'spec' ? <FileJson size={15} />
                      : tab === 'layout' ? <Ruler size={15} />
                        : tab === 'render' ? <PenTool size={15} /> : <GitBranch size={15} />}
                  {tab === 'spec' ? 'Validar IR' : tab === 'layout' ? 'Medir layout' : tab === 'render' ? 'Desenhar' : 'Rodar gates'}
                </button>
              </div>
            </form>
          )}

          {tab === 'legend' && (
            <form className="form-stack" onSubmit={submitLegend}>
              <label className="field">
                <span>Tipo</span>
                <select value={legendType} onChange={(event) => setLegendType(event.target.value)}>
                  <option value="">usar o vocabulário completo</option>
                  {asRows(reference?.tipos).map((item) => <option key={text(item.tipo)} value={text(item.tipo)}>{text(item.rotulo)}</option>)}
                </select>
              </label>
              <div className="diagram-split">
                <label className="field">
                  <span>Preset</span>
                  <select value={legendPreset} onChange={(event) => setLegendPreset(event.target.value)}>
                    <option value="">clássico</option>
                    {asRows(reference?.presets).map((item) => <option key={text(item.preset)} value={text(item.preset)}>{text(item.rotulo)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Legenda</span>
                  <select value={legendMode} onChange={(event) => setLegendMode(event.target.value)}>
                    <option value="">auto · só o que usa</option>
                    <option value="tudo">tudo · quatro variantes</option>
                    <option value="oculta">oculta</option>
                  </select>
                </label>
              </div>
              <label className="field">
                <span>Especificação para conferir (opcional)</span>
                <textarea className="diagram-mono diagram-short" value={legendSpec} onChange={(event) => setLegendSpec(event.target.value)} maxLength={200000} rows={5} spellCheck={false} placeholder="Cole o IR para a legenda conferir se as variantes usadas estão cobertas." />
              </label>
              <p className="diagram-note">A legenda automática só lista as variantes que o desenho realmente usa. Esconder legenda com mais de uma variante é aviso; preset fora do catálogo é bloqueio.</p>
              <div className="diagram-form-actions">
                <button type="button" className="diagram-sample" onClick={loadSample}><Tags size={14} />Limpar</button>
                <button type="submit" className="button button-primary" disabled={busy}>{busy ? <LoaderCircle size={15} className="diagram-spin" /> : <Tags size={15} />}Compor legenda</button>
              </div>
            </form>
          )}

          {tab === 'library' && (
            <div className="diagram-form-static">
              <p className="diagram-note">O catálogo é próprio: dez tipos com orçamento, sete componentes, oito estados de ciclo de vida, cinco tipos de classe, seis relações UML, quatro presets e cinco formatos.</p>
              <div className="diagram-note-card">
                <h4>Como o desenho é feito</h4>
                <p>O IR vira um modelo comum, o layout posiciona cada nó por faixa, raia, estágio, nível ou tempo, e o roteador ortogonal liga as pontas. Nenhuma etapa abre navegador.</p>
              </div>
              <div className="diagram-note-card">
                <h4>O que fica de fora</h4>
                <p>CLI `archify.mjs`, `archify.zip`, template de 786 KB, plugins DSH, captura de Chrome e renderer do upstream. Aqui o desenho é gerado pelo Python do JARVIS.</p>
              </div>
              <button type="button" className="button button-primary" onClick={() => { setTab('type'); setError(''); }}><ArrowRight size={15} />Escolher um tipo</button>
            </div>
          )}

          {error && <p className="diagram-error" role="alert"><AlertTriangle size={15} />{error}</p>}
        </section>

        <section className="panel diagram-result" aria-live="polite">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{result ? analysisLabels[view] ?? 'Parecer' : tab === 'library' ? 'Catálogo' : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="diagram-result-actions">
                <span className="diagram-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="diagram-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
              </div>
            )}
          </header>

          {!result && tab !== 'library' && (
            <div className="diagram-placeholder">
              <span><Layers size={18} /></span>
              <strong>Somente leitura</strong>
              <p>O parecer aparece aqui com evidência por achado, veredito e limites declarados. Nada é instalado, renderizado em navegador ou publicado.</p>
              <ul>
                <li>Tipo: dez candidatos pontuados e um esqueleto JSON para colar.</li>
                <li>IR: validação estrutural com o IR normalizado de volta.</li>
                <li>Layout: coordenadas, cruzamentos, colisões e folga de rótulo.</li>
                <li>Desenho: HTML autocontido, SVG, Mermaid, texto e DOT.</li>
                <li>Legenda: variantes, presets com contraste e movimento.</li>
                <li>Entrega: gates em ordem, com o que não foi verificado.</li>
              </ul>
            </div>
          )}

          {tab === 'library' && <LibraryView reference={reference} />}

          {result && (
            <>
              {view === 'type' && <TypeView result={result} onUse={useSkeleton} />}
              {view === 'spec' && <SpecView result={result} />}
              {view === 'layout' && <LayoutView result={result} />}
              {view === 'render' && <RenderView result={result} onFormat={(next) => { setFormat(next); void run('diagram.render', { especificacao: spec, formato: next, modo: level }, 'render'); }} onCopy={() => void copyContent()} />}
              {view === 'legend' && <LegendView result={result} />}
              {view === 'delivery' && <DeliveryView result={result} />}
              <Limitations items={result.limitations} />
              <details className="diagram-json">
                <summary>Resposta completa (JSON)</summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      </div>
      </>
      )}
    </div>
  );
}
