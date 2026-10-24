import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Compass,
  Download,
  Frame,
  GitBranch,
  Import,
  Layers,
  LoaderCircle,
  Palette,
  PenTool,
  Route,
  ScanSearch,
  ScrollText,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';

type EditorialTab = 'tipo' | 'marca' | 'lint' | 'conector' | 'importar' | 'entrega' | 'catalogo';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';
type Formato = 'drawio' | 'mermaid' | 'excalidraw';
type Detalhe = 'faithful' | 'balanced' | 'simplified';
type Plateia = 'engineer' | 'mixed' | 'executive';
type Preset = 'doc-inline' | 'doc-wide' | 'slide-16x9' | 'slide-4x3' | 'social-og' | 'social-square'
  | 'print-a4-landscape' | 'print-a3-landscape' | 'print-letter-landscape' | 'fit';

const tabs: Array<{ id: EditorialTab; label: string; hint: string; icon: typeof Compass }> = [
  { id: 'tipo', label: 'Tipo', hint: '45 tipos e 9 padrões', icon: Compass },
  { id: 'marca', label: 'Marca', hint: 'Tokens e contraste', icon: Palette },
  { id: 'lint', label: 'Lint', hint: '12 anti-padrões', icon: ScanSearch },
  { id: 'conector', label: 'Conector', hint: '6 regras medidas', icon: Route },
  { id: 'importar', label: 'Importar', hint: 'Redesenho com recibo', icon: Import },
  { id: 'entrega', label: 'Entrega', hint: 'Acessível e no tamanho', icon: GitBranch },
  { id: 'catalogo', label: 'Catálogo', hint: 'O vocabulário inteiro', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const destinos = ['blog', 'readme', 'docs', 'wiki', 'deck', 'figma', 'social', 'print'] as const;
const formatos: Array<{ id: Formato; label: string }> = [
  { id: 'mermaid', label: 'Mermaid (.mmd)' },
  { id: 'drawio', label: 'draw.io (.drawio)' },
  { id: 'excalidraw', label: 'Excalidraw (.excalidraw)' },
];
const detalhes: Array<{ id: Detalhe; label: string }> = [
  { id: 'faithful', label: 'faithful — até 24 nós, com zonas' },
  { id: 'balanced', label: 'balanced — até 12 nós' },
  { id: 'simplified', label: 'simplified — até 7 nós' },
];
const plateias: Array<{ id: Plateia; label: string }> = [
  { id: 'engineer', label: 'engineer — nome exato e porta' },
  { id: 'mixed', label: 'mixed — componente e efeito' },
  { id: 'executive', label: 'executive — capacidade e resultado' },
];
const presets: Preset[] = ['doc-inline', 'doc-wide', 'slide-16x9', 'slide-4x3', 'social-og',
  'social-square', 'print-a4-landscape', 'print-a3-landscape', 'print-letter-landscape', 'fit'];

const sampleType = 'O leitor precisa entender por que o webhook de pagamento entra numa fila e espera o worker livre, e o que acontece quando a fila enche.';
const sampleBrand = 'paper=#f5f5f5\nink=#2d3142\nmuted=#4f5d75\nsoft=#5a6580\naccent=#f7591f\nlink=#2e5aa8';
const sampleLint = `<!doctype html>
<html lang="pt-BR"><head><style>
body { font-family: 'Geist', system-ui, sans-serif; background: #f5f5f5; color: #2d3142; }
.card { box-shadow: 0 12px 32px rgba(0,0,0,.25); border-radius: 24px; }
</style></head><body>
<svg viewBox="0 0 960 600" role="img" aria-labelledby="fila-title fila-desc">
<title id="fila-title">Fila de webhooks</title>
<desc id="fila-desc">Webhooks entram numa fila limitada e um worker único libera o recibo.</desc>
<rect x="10" y="10" width="200" height="48" rx="6" fill="#ececec"/>
<line x1="210" y1="34" x2="360" y2="120"/>
</svg></body></html>`;
const sampleConnectors = `[
  { "id": "entra", "de": { "x": 120, "y": 200, "w": 160, "h": 48 },
    "para": { "x": 440, "y": 200, "w": 160, "h": 48 },
    "pontos": [[280, 224], [440, 224]], "rotulo": "ENFILEIRA",
    "mascara": { "x": 320, "y": 194, "w": 80, "h": 12 }, "raio": 8 },
  { "id": "consome", "de": { "x": 440, "y": 200, "w": 160, "h": 48 },
    "para": { "x": 760, "y": 320, "w": 160, "h": 48 },
    "pontos": [[520, 248], [520, 344], [760, 344]], "raio": 8 }
]`;
const sampleImport = `flowchart LR
  A[Cliente] -->|POST /v2| B[Gateway]
  B --> C[Pedidos]
  C --> D[(Postgres)]
  C --> E[(Réplica de leitura)]
  B --> F[Métrica]
  B --> G[Tracing]
  B --> H[Log de acesso]
  A --> I[Nota adesiva]
`;
const sampleDelivery = sampleLint.replace(
  '  <line x1="210" y1="34" x2="360" y2="120"/>\n',
  '',
);

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nada contra as regras estáticas deste modo.</p>;
  return (
    <div className="diagram-findings">
      {items.map((finding) => {
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

function Verdict({ children }: { children: React.ReactNode }) {
  return <p className="diagram-verdict"><CheckCircle2 size={14} />{children}</p>;
}

function TipoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="TIPO" value={text(result.nome)} tone="ok" />
        <Metric label="PADRÃO" value={text(metrics.padrao)} />
        <Metric label="NÓS / TETO" value={`${count(metrics.nos)} / ${count(metrics.teto)}`} tone={count(metrics.nos) > count(metrics.teto) ? 'danger' : 'ok'} />
        <Metric label="PRESET" value={text(metrics.preset)} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <div className="diagram-vocab">
        {asList(result.plano).map((item) => <span key={item} className="is-on">{item}</span>)}
        <span>confiança {text(metrics.confianca)}</span>
      </div>
      <Findings items={asRows(result.findings)} />
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Tipo</th><th>Família</th><th>Nós</th><th>Arestas</th></tr></thead>
          <tbody>{asRows(result.rows).slice(0, 18).map((row) => (
            <tr key={text(row.id)}>
              <td><strong>{text(row.nome)}</strong><br /><code>{text(row.id)}</code></td>
              <td>{text(row.familia)}</td>
              <td>{count(row.nos)}</td>
              <td>{count(row.arestas)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {asList(result.questions).length > 0 && (
        <div className="diagram-note-card">
          <h4>Perguntas antes de desenhar</h4>
          <ul className="diagram-traps">{asList(result.questions).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function MarcaView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const rows = asRows(result.rows);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="PAPÉIS" value={count(metrics.tokens)} />
        <Metric label="DECLARADOS" value={count(metrics.declarados)} />
        <Metric label="ABAIXO DO MÍNIMO" value={count(metrics.falhas)} tone={count(metrics.falhas) ? 'danger' : 'ok'} />
        <Metric label="TEMA" value={text(metrics.tema)} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Papel</th><th>Valor</th><th>Contraste</th><th>Mínimo</th><th>Situação</th><th>Proposta</th></tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={text(row.papel)}>
              <td><code>{text(row.papel)}</code></td>
              <td><span className="diagram-swatches"><i style={{ background: text(row.valor) }} />{text(row.valor)}</span></td>
              <td>{count(row.contraste).toFixed(2)}:1</td>
              <td>{count(row.minimo) ? `${count(row.minimo)}:1` : 'livre'}</td>
              <td><span className={`diagram-state ${text(row.situacao) === 'falha' ? 'is-danger' : text(row.situacao) === 'ok' ? 'is-ok' : ''}`}>{text(row.situacao)}</span></td>
              <td>{text(row.proposto) || '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <Findings items={asRows(result.findings)} />
    </div>
  );
}

function LintView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="ACHADOS" value={count(metrics.achados)} tone={count(metrics.achados) ? 'warning' : 'ok'} />
        <Metric label="OBRIGATÓRIOS" value={count(metrics.obrigatorios)} tone={count(metrics.obrigatorios) ? 'danger' : 'ok'} />
        <Metric label="CARACTERES" value={count(metrics.caracteres).toLocaleString('pt-BR')} />
        <Metric label="FONTES" value={`${count(metrics.mono)} mono`} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <Findings items={asRows(result.findings)} />
      <details className="diagram-json">
        <summary>Os doze anti-padrões conferidos</summary>
        <div className="diagram-option-list">
          {asRows(result.rows).map((row) => (
            <article className="diagram-option" key={text(row.id)}>
              <header><strong>{text(row.titulo)}</strong><code>{text(row.id)}</code></header>
              <p>{text(row.porque)}</p>
            </article>
          ))}
        </div>
      </details>
    </div>
  );
}

function ConectorView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="CONECTORES" value={count(metrics.conectores)} />
        <Metric label="SEGMENTOS" value={count(metrics.segmentos)} />
        <Metric label="DIAGONAIS" value={count(metrics.diagonais)} tone={count(metrics.diagonais) ? 'danger' : 'ok'} />
        <Metric label="ROTULADOS" value={count(metrics.rotulados)} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <Findings items={asRows(result.findings)} />
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Conector</th><th>Segmentos</th><th>Rótulo</th><th>Tracejado</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={text(row.id)}>
              <td><code>{text(row.id)}</code></td>
              <td>{count(row.segmentos)}</td>
              <td>{text(row.rotulo)}</td>
              <td>{row.tracejado ? 'sim' : 'não'}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ImportarView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const ledger = asRows(result.ledger);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="ORIGEM" value={`${count(metrics.origem_nos)} nós`} />
        <Metric label="DESENHO" value={`${count(metrics.nos)} nós`} tone={count(metrics.cortes) ? 'warning' : 'ok'} />
        <Metric label="ARESTAS" value={`${count(metrics.arestas)}`} />
        <Metric label="DETALHE" value={text(metrics.detalhe)} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <div className="diagram-vocab">
        <span className="is-on">{text(metrics.tamanho)}</span>
        <span>rampa {count(metrics.nome)}</span>
        <span>plateia {text(metrics.plateia)}</span>
        <span>{count(metrics.cortes)} corte(s)</span>
      </div>
      {ledger.length > 0 ? (
        <div className="diagram-orders">
          <span className="diagram-hint">Recibo de fidelidade — o que não atravessou.</span>
          <ol className="diagram-order">
            {ledger.map((corte, index) => (
              <li className="is-active" key={`${text(corte.item)}-${index}`}>
                <span>{text(corte.passo)}</span>
                <strong>{text(corte.corta)}</strong>
                <em>{text(corte.item)}</em>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <p className="diagram-empty"><CheckCircle2 size={14} />Nenhum corte: a origem cabe no teto do detalhe.</p>
      )}
      <Findings items={asRows(result.findings)} />
    </div>
  );
}

function EntregaView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="PRESET" value={text(metrics.preset)} tone="ok" />
        <Metric label="RAMPA" value={text(metrics.rampa)} />
        <Metric label="TAMANHOS" value={count(metrics.tamanhos)} />
        <Metric label="ACHADOS" value={count(metrics.achados)} tone={count(metrics.achados) ? 'warning' : 'ok'} />
      </div>
      <Verdict>{text(result.verdict)}</Verdict>
      <Findings items={asRows(result.findings)} />
      <div className="diagram-note-card">
        <h4>Contrato acessível</h4>
        <ol className="diagram-order">
          {asRows(result.rows).map((row) => (
            <li key={text(row.criterio)}><span>{text(row.criterio)}</span>{text(row.regra)}</li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function CatalogoView({ result }: { result: Row | null }) {
  const [family, setFamily] = useState('todas');
  const tipos = asRows(result?.tipos);
  const familias = useMemo(() => ['todas', ...Array.from(new Set(tipos.map((item) => text(item.familia))))], [tipos]);
  const filtrados = family === 'todas' ? tipos : tipos.filter((item) => text(item.familia) === family);
  if (!result) return <div className="diagram-placeholder"><span><LoaderCircle className="diagram-spin" size={18} /></span><strong>Lendo o catálogo</strong><p>O vocabulário vem da API local.</p></div>;
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="TIPOS" value={tipos.length} tone="ok" />
        <Metric label="PADRÕES" value={asRows(result.padroes).length} />
        <Metric label="ANTI-PADRÕES" value={asRows(result.anti_padroes).length} />
        <Metric label="PRESETS" value={asRows(result.presets).length} />
      </div>
      <div className="diagram-toolbar">
        {familias.map((item) => (
          <button key={item} type="button" className={family === item ? 'is-on' : undefined} onClick={() => setFamily(item)}>{item}</button>
        ))}
      </div>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Tipo</th><th>Família</th><th>Orçamento</th><th>Uso</th></tr></thead>
          <tbody>{filtrados.map((row) => (
            <tr key={text(row.id)}>
              <td><strong>{text(row.nome)}</strong><br /><code>{text(row.id)}</code></td>
              <td>{text(row.familia)}</td>
              <td>{count(row.nos)} nós · {count(row.arestas)} setas</td>
              <td>{text(row.uso)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="diagram-note-card">
        <h4>Nove padrões semânticos</h4>
        <ul className="diagram-traps">
          {asRows(result.padroes).map((padrao) => (
            <li key={text(padrao.id)}><strong>{text(padrao.nome)}</strong> — {text(padrao.leitor)} <code>{text(padrao.tipo)}</code></li>
          ))}
        </ul>
      </div>
      <div className="diagram-note-card">
        <h4>Tamanhos e rampas</h4>
        <ul className="diagram-traps">
          {asRows(result.presets).map((preset) => (
            <li key={text(preset.id)}><code>{text(preset.id)}</code> {count(preset.w) ? `${count(preset.w)} × ${count(preset.h)}` : 'derivado'} — {text(preset.rampa)}, {text(preset.uso)}</li>
          ))}
        </ul>
      </div>
      <div className="diagram-note-card">
        <h4>Seis regras de conector</h4>
        <ol className="diagram-order">
          {asRows(result.conector).map((regra) => (
            <li key={text(regra.id)}><span>{text(regra.id)}</span><strong>{text(regra.titulo)}</strong><em>{text(regra.regra)}</em></li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export function EditorialSection() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<EditorialTab>('tipo');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [view, setView] = useState<EditorialTab>('tipo');
  const [catalogo, setCatalogo] = useState<Row | null>(null);

  const [pedido, setPedido] = useState(sampleType);
  const [plateia, setPlateia] = useState('');
  const [destino, setDestino] = useState('deck');
  const [nos, setNos] = useState('6');

  const [marca, setMarca] = useState(sampleBrand);
  const [escuro, setEscuro] = useState(false);

  const [html, setHtml] = useState(sampleLint);
  const [conectores, setConectores] = useState(sampleConnectors);
  const [fonte, setFonte] = useState(sampleImport);
  const [formato, setFormato] = useState<Formato>('mermaid');
  const [detalhe, setDetalhe] = useState<Detalhe>('simplified');
  const [plateiaImport, setPlateiaImport] = useState<Plateia>('mixed');
  const [tamanho, setTamanho] = useState<Preset>('slide-16x9');
  const [preset, setPreset] = useState<Preset>('doc-inline');

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('editorial.catalogo', {});
        if (active && response.ok) setCatalogo(asRow(response.result));
      } catch {
        if (active) setCatalogo(null);
      }
    })();
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

  const result = execution?.ok ? asRow(execution.result) : null;
  const resultMarkdown = useMemo(() => text(result?.markdown), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>, next: EditorialTab) => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi desenhado.');
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

  const loadSample = () => {
    if (tab === 'tipo') { setPedido(sampleType); setPlateia(''); setDestino('deck'); setNos('6'); }
    if (tab === 'marca') { setMarca(sampleBrand); setEscuro(false); }
    if (tab === 'lint') setHtml(sampleLint);
    if (tab === 'conector') setConectores(sampleConnectors);
    if (tab === 'importar') { setFonte(sampleImport); setFormato('mermaid'); }
    if (tab === 'entrega') setHtml(sampleDelivery);
    setError('');
  };

  const formId: Record<EditorialTab, string> = {
    tipo: 'editorial.tipo', marca: 'editorial.marca', lint: 'editorial.lint',
    conector: 'editorial.conector', importar: 'editorial.importar',
    entrega: 'editorial.entrega', catalogo: 'editorial.catalogo',
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (tab === 'catalogo') {
      void run('editorial.catalogo', {}, 'catalogo');
      return;
    }
    if (tab === 'tipo') {
      void run(formId.tipo, { pedido, plateia, destino, nos: Number(nos) || 0, modo: level }, 'tipo');
      return;
    }
    if (tab === 'marca') {
      void run(formId.marca, { marca, escuro, modo: level }, 'marca');
      return;
    }
    if (tab === 'conector') {
      void run(formId.conector, { conectores, modo: level }, 'conector');
      return;
    }
    if (tab === 'importar') {
      void run(formId.importar, {
        fonte, formato, tamanho, detalhe, plateia: plateiaImport, modo: level,
      }, 'importar');
      return;
    }
    if (tab === 'entrega') {
      void run(formId.entrega, { html, preset, modo: level }, 'entrega');
      return;
    }
    void run(formId.lint, { html, modo: level }, 'lint');
  };

  const downloadJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `editorial-${view}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const requiresLevel = tab !== 'catalogo';
  const buttonLabel: Record<EditorialTab, string> = {
    tipo: 'Escolher tipo e padrão', marca: 'Resolver papéis', lint: 'Rodar o lint',
    conector: 'Medir conectores', importar: 'Ler e redesenhar', entrega: 'Conferir entrega',
    catalogo: 'Ler o catálogo',
  };
  const resultTitle: Record<EditorialTab, string> = {
    tipo: 'Tipo e padrão', marca: 'Marca em papéis', lint: 'Lint editorial',
    conector: 'Geometria dos conectores', importar: 'Redesenho com recibo',
    entrega: 'Contrato de entrega', catalogo: 'Catálogo editorial',
  };

  return (
    <div className="diagram-section">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Frame size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>O melhor movimento é a exclusão</h2>
          <p>Cada nó precisa ganhar o lugar, e o acento aponta uma ou duas coisas. A camada editorial decide o tipo e o orçamento, mede o contraste da marca, confere a geometria dos conectores e escreve o recibo do que foi cortado na importação. Ela não desenha: isso continua sendo o IR.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Tipo antes de estilo</strong><span>O pedido escolhe o tipo; o padrão semântico escolhe o que o leitor precisa entender.</span></li>
          <li><strong>Contraste é contrato</strong><span>Papel, tinta e acento são medidos em WCAG 2.x; o ajuste proposto preserva o matiz.</span></li>
          <li><strong>Conector é medida</strong><span>Ortogonal, folga de 6–10px, leque de 12px e máscara antes do nó: tudo em coordenada.</span></li>
          <li><strong>Recibo de fidelidade</strong><span>Importar é redesenhar; o que ficou de fora é dito, não escondido.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos da camada editorial">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); if (id === 'catalogo') setExecution(null); }} aria-pressed={tab === id}>
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

          <form className="form-stack" onSubmit={submit}>
            {tab === 'tipo' && (
              <>
                <label className="field">
                  <span>O leitor precisa entender *</span>
                  <textarea value={pedido} onChange={(event) => setPedido(event.target.value)} maxLength={2000} rows={4} required placeholder="A pergunta que o desenho responde — comportamento, estado, risco ou ordem." />
                </label>
                <div className="diagram-split">
                  <label className="field">
                    <span>Quem lê</span>
                    <input value={plateia} onChange={(event) => setPlateia(event.target.value)} maxLength={120} placeholder="Opcional: plantão, diretoria, quem chega agora" />
                  </label>
                  <label className="field">
                    <span>Onde vai aparecer</span>
                    <select value={destino} onChange={(event) => setDestino(event.target.value)}>
                      {destinos.map((item) => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                </div>
                <label className="field">
                  <span>Quantos nós</span>
                  <input type="number" min={0} max={400} value={nos} onChange={(event) => setNos(event.target.value)} />
                </label>
                <p className="diagram-note">O destino define o preset e a rampa. A contagem de nós define o orçamento: acima do teto do tipo, o veredito bloqueia e pede divisão em visão geral + detalhe.</p>
              </>
            )}

            {tab === 'marca' && (
              <>
                <label className="field">
                  <span>Tokens da marca *</span>
                  <textarea className="diagram-mono" value={marca} onChange={(event) => setMarca(event.target.value)} maxLength={4000} rows={8} required spellCheck={false} placeholder={'paper=#f5f5f5\nink=#2d3142\naccent=#bf4520'} />
                </label>
                <label className="diagram-check">
                  <input type="checkbox" checked={escuro} onChange={(event) => setEscuro(event.target.checked)} />
                  <span>Tema escuro — mede os papéis sobre a tinta</span>
                </label>
                <p className="diagram-note">Um papel por linha, com <code>=</code> ou <code>:</code>. Texto precisa de 4,5:1; marca essencial, de 3:1. Opacidade é composta sobre o papel antes de medir.</p>
              </>
            )}

            {(tab === 'lint' || tab === 'entrega') && (
              <>
                <label className="field">
                  <span>HTML ou SVG do diagrama *</span>
                  <textarea className="diagram-mono" value={html} onChange={(event) => setHtml(event.target.value)} maxLength={60000} rows={12} required spellCheck={false} placeholder="Cole o arquivo autocontido — SVG inline, CSS embutido, sem imagem externa." />
                </label>
                {tab === 'entrega' && (
                  <label className="field">
                    <span>Preset de tamanho</span>
                    <select value={preset} onChange={(event) => setPreset(event.target.value as Preset)}>
                      {presets.map((item) => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                )}
                <p className="diagram-note">
                  {tab === 'lint' && 'O lint lê o arquivo como texto: sombra, raio grande, mono total, legenda solta, rótulo sem máscara, diagonal e recurso externo.'}
                  {tab === 'entrega' && 'A entrega confere SVG acessível, viewBox do preset, min-width, rolagem local, impressão e rampa tipográfica.'}
                </p>
              </>
            )}

            {tab === 'conector' && (
              <>
                <label className="field">
                  <span>Conectores em JSON *</span>
                  <textarea className="diagram-mono" value={conectores} onChange={(event) => setConectores(event.target.value)} maxLength={60000} rows={13} required spellCheck={false} placeholder='[{ "id": "a", "de": {…}, "para": {…}, "pontos": [[x,y]], "rotulo": "ENVIA", "mascara": {…} }]' />
                </label>
                <p className="diagram-note">Cada conector aceita <code>de</code>/<code>para</code> com <code>x, y, w, h</code> e opcionalmente <code>lado</code>, ou <code>pontos</code> explícitos. Rótulo com <code>mascara</code>, <code>raio</code>, <code>tracejado</code>, <code>cruzaCaixa</code> e <code>nosDepois</code>.</p>
              </>
            )}

            {tab === 'importar' && (
              <>
                <label className="field">
                  <span>Arquivo de origem *</span>
                  <textarea className="diagram-mono" value={fonte} onChange={(event) => setFonte(event.target.value)} maxLength={60000} rows={11} required spellCheck={false} placeholder="Cole o XML do draw.io, o bloco Mermaid ou o JSON do Excalidraw." />
                </label>
                <div className="diagram-split">
                  <label className="field">
                    <span>Formato</span>
                    <select value={formato} onChange={(event) => setFormato(event.target.value as Formato)}>
                      {formatos.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </select>
                  </label>
                  <label className="field">
                    <span>Detalhe</span>
                    <select value={detalhe} onChange={(event) => setDetalhe(event.target.value as Detalhe)}>
                      {detalhes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </select>
                  </label>
                </div>
                <div className="diagram-split">
                  <label className="field">
                    <span>Tamanho</span>
                    <select value={tamanho} onChange={(event) => setTamanho(event.target.value as Preset)}>
                      {presets.map((item) => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                  <label className="field">
                    <span>Plateia</span>
                    <select value={plateiaImport} onChange={(event) => setPlateiaImport(event.target.value as Plateia)}>
                      {plateias.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </select>
                  </label>
                </div>
                <p className="diagram-note">Importar é redesenhar: posição, cor e fonte da origem não atravessam; componentes, relações e agrupamento sim. O recibo lista o que a escada cortou.</p>
              </>
            )}

            {tab === 'catalogo' && (
              <div className="diagram-form-static">
                <p className="diagram-note">O catálogo é a fonte única do vocabulário: orçamento por tipo, nove padrões, doze papéis de cor com contraste, dez presets e seis regras de conector.</p>
                <div className="diagram-note-card">
                  <h4>O que a camada editorial não faz</h4>
                  <p>Não renderiza, não abre navegador, não executa os scripts do upstream (<code>verify-geometry.py</code>, <code>self_check.py</code>, <code>lint-render.py</code>, <code>export_png.py</code>) e não instala a skill de agente. A conta é feita em Python sobre o texto que você cola.</p>
                </div>
                <div className="diagram-note-card">
                  <h4>De onde vem</h4>
                  <p>Adaptação estática de <code>cathrynlavery/diagram-design</code>, MIT (© Cathryn Lavery). O desenho continua no IR do JARVIS; aqui entra o contrato editorial.</p>
                </div>
              </div>
            )}

            {error && <p className="diagram-error" role="alert"><AlertTriangle size={15} />{error}</p>}

            <div className="diagram-form-actions">
              <button type="button" className="diagram-sample" onClick={loadSample}><Clipboard size={14} />Carregar exemplo</button>
              <button type="submit" className="button button-primary" disabled={busy}>
                {busy ? <LoaderCircle size={15} className="diagram-spin" />
                  : tab === 'marca' ? <Palette size={15} />
                    : tab === 'lint' ? <ScanSearch size={15} />
                      : tab === 'conector' ? <Route size={15} />
                        : tab === 'importar' ? <Import size={15} />
                          : tab === 'entrega' ? <GitBranch size={15} />
                            : tab === 'catalogo' ? <BookOpen size={15} /> : <Compass size={15} />}
                {buttonLabel[tab]}
              </button>
            </div>
          </form>
        </section>

        <section className="panel diagram-result" aria-live="polite">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{result ? resultTitle[view] : tab === 'catalogo' ? 'Catálogo editorial' : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="diagram-result-actions">
                <span className="diagram-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="diagram-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
                <button type="button" className="diagram-copy" onClick={downloadJson}><Download size={13} />Baixar JSON</button>
              </div>
            )}
          </header>

          {!result && tab !== 'catalogo' && (
            <div className="diagram-placeholder">
              <span><Layers size={18} /></span>
              <strong>Nada medido ainda</strong>
              <p>A camada editorial devolve evidência por achado, veredito e limites declarados. Nada é renderizado, instalado ou publicado.</p>
              <ul>
                <li>Tipo: 45 tipos e 9 padrões semânticos, com orçamento e preset.</li>
                <li>Marca: papéis semânticos e contraste WCAG, com ajuste proposto.</li>
                <li>Lint: doze anti-padrões no texto do arquivo.</li>
                <li>Conector: seis regras medidas na geometria declarada.</li>
                <li>Importar: escada de degradação e recibo de fidelidade.</li>
                <li>Entrega: SVG acessível, viewBox, min-width, impressão e rampa.</li>
              </ul>
            </div>
          )}

          {tab === 'catalogo' && <CatalogoView result={catalogo} />}
          {result && (
            <>
              {view === 'tipo' && <TipoView result={result} />}
              {view === 'marca' && <MarcaView result={result} />}
              {view === 'lint' && <LintView result={result} />}
              {view === 'conector' && <ConectorView result={result} />}
              {view === 'importar' && <ImportarView result={result} />}
              {view === 'entrega' && <EntregaView result={result} />}
              <Limitations items={result.limitations} />
              <details className="diagram-json">
                <summary>Parecer completo em Markdown</summary>
                <pre>{resultMarkdown}</pre>
              </details>
              <details className="diagram-json">
                <summary>Resposta completa (JSON)</summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      </div>

      <section className="panel diagram-intro diagram-editorial-closing">
        <span className="diagram-intro-icon"><ScrollText size={22} /></span>
        <div>
          <span className="eyebrow">ONDE ISSO ENTRA</span>
          <h2>Editorial decide, IR desenha</h2>
          <p>Use esta camada para fechar tipo, orçamento, marca e conectores. O esqueleto aprovado vira especificação em <strong>Desenho por IR</strong>, que mede o layout e entrega o HTML autocontido.</p>
          <div className="diagram-vocab">
            <span className="is-on"><PenTool size={11} /> editorial.tipo</span>
            <span className="is-on">editorial.marca</span>
            <span className="is-on">editorial.lint</span>
            <span className="is-on">editorial.conector</span>
            <span className="is-on">editorial.importar</span>
            <span className="is-on">editorial.entrega</span>
            <span className="is-on">editorial.catalogo</span>
          </div>
        </div>
      </section>
    </div>
  );
}
