import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Code2,
  Contrast,
  FileJson2,
  Layers,
  LoaderCircle,
  Palette,
  PenLine,
  ShieldCheck,
  Sparkles,
  SwatchBook,
  Wand2,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../estudio.css';

type StudioTab = 'contract' | 'contrast' | 'critique' | 'artifact' | 'base';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: StudioTab; label: string; hint: string; icon: typeof Palette }> = [
  { id: 'contract', label: 'Contrato', hint: 'Pacote completo', icon: FileJson2 },
  { id: 'contrast', label: 'Contraste', hint: 'WCAG AA e AAA', icon: Contrast },
  { id: 'critique', label: 'Crítica', hint: 'Cinco dimensões', icon: PenLine },
  { id: 'artifact', label: 'Artefato', hint: 'Anti-clichê', icon: Code2 },
  { id: 'base', label: 'Base', hint: 'Tokens e bandas', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string; description: string }> = [
  { id: 'lite', label: 'Lite', description: 'Só o que bloqueia.' },
  { id: 'full', label: 'Full', description: 'Padrão: bloqueios e correções.' },
  { id: 'ultra', label: 'Ultra', description: 'Inclui perguntas para a revisão.' },
];

const laws = [
  { key: 'schema', title: 'Todo pacote tem contrato', text: 'Manifesto, prosa e tokens formam um só objeto. Slot ausente derruba a regra inteira no artefato.' },
  { key: 'tokens', title: 'Toda cor vem do token', text: 'Hexadecimal solto quebra o tema escuro e esconde a marca. O literal mora só em :root.' },
  { key: 'motion', title: 'Todo movimento tem saída', text: 'Entrada de 200ms com ease-out forte, saída de 140ms e alternativa para quem pede menos movimento.' },
  { key: 'slop', title: 'Todo clichê tem nome', text: 'Gradiente roxo, emoji como ícone e métrica inventada são reconhecíveis — e precisam ser ditos.' },
];

const analysisLabels: Record<string, string> = {
  contract: 'Contrato', contrast: 'Contraste', critique: 'Crítica', artifact: 'Artefato', reference: 'Referência',
};

const SAMPLE_MANIFEST = `{
  "schemaVersion": "od-design-system-project/v1",
  "id": "acme-papel",
  "name": "Acme Papel",
  "category": "SaaS editorial",
  "description": "Papel quente, serif de display e verde profundo como acento único.",
  "source": { "type": "bundled", "origin": "acme" },
  "files": { "design": "DESIGN.md", "tokens": "tokens.css" }
}`;

const SAMPLE_DESIGN = `# Acme Papel
## Tema
Editorial e quente; contraste alto, sem gradiente e sem brilho solto.
## Cor
Acento único em verde profundo, fundo branco quente e texto quase preto.
## Tipografia
Display serifada, corpo sans humanista e mono apenas para números.
## Espaçamento
Grade de 4px; seções com respiro generoso no desktop e compacto no celular.
## Componentes
Botão primário sólido, secundário com anel de 1px e foco sempre visível.
## Movimento
Entrada de 200ms com ease-out forte, saída de 140ms e alternativa reduzida.
## Acessibilidade
Texto normal a 4.5:1, grande a 3:1, foco visível e navegação por teclado.
## Antíteses
Sem gradiente roxo, sem emoji como ícone e sem métrica inventada.`;

const SAMPLE_TOKENS = `:root {
  --bg: #faf9f6; --surface: #ffffff; --surface-warm: #f5f1ea;
  --fg: #18181b; --fg-2: #27272a; --muted: #57534e; --meta: #78716c;
  --border: #e7e5e4; --border-soft: #f0efed;
  --accent: #0f766e; --accent-on: #ffffff; --accent-hover: #115e59; --accent-active: #134e4a;
  --success: #16a34a; --warn: #ca8a04; --danger: #dc2626;
  --font-display: "Fraunces", serif; --font-body: "Inter", sans-serif; --font-mono: ui-monospace, monospace;
  --text-xs: 12px; --text-sm: 14px; --text-base: 16px; --text-lg: 18px;
  --text-xl: 22px; --text-2xl: 28px; --text-3xl: 40px; --text-4xl: 56px;
  --leading-body: 1.6; --leading-tight: 1.1; --tracking-display: -0.02em;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-12: 48px;
  --section-y-desktop: 96px; --section-y-tablet: 64px; --section-y-phone: 48px;
  --radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px; --radius-pill: 9999px;
  --elev-flat: none; --elev-ring: 0 0 0 1px var(--border);
  --elev-raised: 0 2px 8px rgba(0, 0, 0, 0.08); --focus-ring: 0 0 0 3px var(--accent);
  --motion-fast: 150ms; --motion-base: 200ms; --ease-standard: cubic-bezier(0.23, 1, 0.32, 1);
  --container-max: 1120px; --container-gutter-desktop: 32px;
  --container-gutter-tablet: 24px; --container-gutter-phone: 16px;
}
[data-theme="dark"] {
  --bg: #111113; --fg: #fafafa; --surface: #18181b; --border: #27272a; --muted: #a1a1aa;
}
.card { padding: var(--space-4); border: 1px solid var(--border); background: var(--surface); }
.button { background: var(--accent); color: var(--accent-on); transition: background var(--motion-fast) var(--ease-standard); }
@media (prefers-reduced-motion: reduce) { .button { transition: none; } }`;

const SAMPLE_PAIRS = `# rótulo | frente | fundo | corpo ou grande
Corpo | #18181b | #faf9f6 | corpo
Secundário | #57534e | #faf9f6 | corpo
Botão primário | #ffffff | #0f766e | corpo
Rodapé | #a1a1aa | #fafafa | corpo
Herói | #8a8a8a | #ffffff | grande`;

const SAMPLE_CRITIQUE = `filosofia | 8 | O chrome mantém vol.04 e o kicker em .serif em todas as páginas, sem misturar registros.
hierarquia | 6 | Na página 3 o .stat usa 40px e o h1 usa 42px, então os dois competem pelo primeiro olhar.
detalhe | 5 | A coluna direita da página 8 começa 2vh acima da esquerda; .callout usa margem 3vh e a figura não.
funcao | 9 | A navegação por teclado funciona em todas as páginas e o formulário conclui com 12px de foco visível.
inovacao | 4 | Nenhum movimento tipográfico próprio: o .deck poderia ser de qualquer agência de 2024.`;

const SAMPLE_KEEP = `- A capa em .cover usa a serif no tamanho certo
- O ritmo de 200ms no hover está consistente
- A paleta de papel quente sustenta as fotos`;

const SAMPLE_FIX = `- Igualar a base das colunas na página 8
- Reduzir o peso do número em .stat na página 3
- Unificar a legenda mono e sans em .caption`;

const SAMPLE_WINS = `- Trocar o flex por grid na página 4 (10 min)
- Ajustar o tracking do kicker para 0.08em (5 min)
- Alinhar a margem do .callout com a figura (15 min)`;

const SAMPLE_ARTIFACT = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Acme Papel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg: #faf9f6; --fg: #18181b; --accent: #0f766e; --surface: #ffffff; }
.hero { background: linear-gradient(90deg, #3b82f6, #06b6d4); color: var(--fg); }
h1 { font-family: Inter, sans-serif; font-size: 56px; }
.card { border: 1px solid var(--border); border-left: 4px solid #7c3aed; padding: 24px; }
.label { text-transform: uppercase; }
.cta { background: #6366f1; transition: transform 150ms ease-in; }
</style></head>
<body><h1>Acme ✨</h1>
<p>10x faster para publicar seu sistema de design.</p>
<img src="https://cdn.example.com/hero.png">
<section><div class="card"><span class="label">Novo</span><p>Entrega em 12 minutos por semana.</p></div></section>
</body></html>`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const fixed = (value: unknown, digits = 0): string => count(value).toFixed(digits);
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const axisLabel: Record<string, string> = {
  filosofia: 'Filosofia', hierarquia: 'Hierarquia', detalhe: 'Detalhe', funcao: 'Função', inovacao: 'Inovação',
};
const levelLabel: Record<string, string> = { AAA: 'AAA', AA: 'AA', reprovado: 'reprova' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Limitations({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="studio-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="studio-empty"><CheckCircle2 size={14} />Nenhum candidato pelas regras estáticas.</p>;
  return (
    <div className="studio-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`studio-finding is-${group}`} key={`${text(finding.id)}-${text(finding.kind)}-${text(finding.location)}`}>
            <header>
              <span className="studio-group">{groupLabel[group] ?? group}</span>
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

function ContractResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const groups = asRows(result.rows);
  return (
    <div className="studio-view">
      <div className="studio-metrics">
        <Metric label="SLOTS" value={`${count(metrics.requiredFound)}/${count(metrics.requiredTotal)}`} tone={count(metrics.requiredFound) === count(metrics.requiredTotal) ? 'ok' : 'danger'} />
        <Metric label="SEÇÕES H2" value={count(metrics.headings)} />
        <Metric label="TEMAS" value={count(metrics.themes)} />
        <Metric label="COR BRUTA" value={count(metrics.rawColors)} tone={count(metrics.rawColors) ? 'warning' : undefined} />
      </div>
      <p className="studio-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="studio-scroll">
        <table className="studio-table">
          <thead><tr><th>Grupo</th><th>Declarados</th><th>Total</th><th>Estado</th></tr></thead>
          <tbody>
            {groups.map((group) => {
              const declared = count(group.declared);
              const total = count(group.total);
              return (
                <tr key={text(group.group)}>
                  <td><strong>{text(group.label)}</strong></td>
                  <td>{declared}</td>
                  <td>{total}</td>
                  <td>
                    <span className={`studio-state ${declared === total ? 'is-ok' : 'is-danger'}`}>{declared === total ? 'completo' : `${total - declared} ausente(s)`}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ContrastResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const rows = asRows(result.rows);
  return (
    <div className="studio-view">
      <div className="studio-metrics">
        <Metric label="PARES" value={count(metrics.pairs)} />
        <Metric label="REPROVADOS" value={count(metrics.failAA)} tone={count(metrics.failAA) ? 'danger' : 'ok'} />
        <Metric label="AAA" value={count(metrics.passAAA)} />
        <Metric label="PIOR RAZÃO" value={`${fixed(metrics.minRatio, 2)}:1`} tone={count(metrics.minRatio) < 3 ? 'danger' : undefined} />
      </div>
      <p className="studio-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="studio-scroll">
        <table className="studio-table">
          <thead><tr><th>Par</th><th>Cores</th><th>Razão</th><th>Limite</th><th>Nível</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${text(row.line)}-${text(row.label)}`}>
                <td><strong>{text(row.label)}</strong></td>
                <td>
                  <span className="studio-swatches">
                    <i style={{ background: text(row.foreground) }} title={`frente ${text(row.foreground)}`} />
                    <i style={{ background: text(row.background) }} title={`fundo ${text(row.background)}`} />
                    <code>{text(row.foreground)} / {text(row.background)}</code>
                  </span>
                </td>
                <td>{fixed(row.ratio, 2)}:1</td>
                <td>{`${fixed(row.aa, 1)} / ${fixed(row.aaa, 1)}`}</td>
                <td><span className={`studio-state is-${text(row.level) === 'reprovado' ? 'danger' : text(row.level) === 'AAA' ? 'ok' : 'warning'}`}>{levelLabel[text(row.level)] ?? text(row.level)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function CritiqueResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const radar = asRows(result.radar);
  const bands = asRows(result.bands);
  const keep = asList(result.keep);
  const fix = asList(result.fix);
  const wins = asList(result.quickWins);
  return (
    <div className="studio-view">
      <div className="studio-metrics">
        <Metric label="DIMENSÕES" value={`${count(metrics.dimensions)}/5`} tone={count(metrics.dimensions) === 5 ? 'ok' : 'danger'} />
        <Metric label="MÉDIA" value={fixed(metrics.mean, 2)} tone={count(metrics.mean) > 8 ? 'warning' : undefined} />
        <Metric label="EIXO FRACO" value={axisLabel[text(metrics.weakest)] ?? (text(metrics.weakest) || '—')} tone="danger" />
        <Metric label="GANHOS RÁPIDOS" value={count(metrics.quickWins)} />
      </div>
      <p className="studio-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="studio-radar">
        {radar.map((dimension) => {
          const score = count(dimension.score);
          return (
            <div className="studio-axis" key={text(dimension.axis)}>
              <div><span>{text(dimension.label)}</span><strong>{score}/10</strong><em>{text(dimension.band)}</em></div>
              <div className="studio-track"><i style={{ width: `${Math.max(score, 0) * 10}%` }} /></div>
            </div>
          );
        })}
      </div>
      <div className="studio-bands">
        {bands.map((band) => (
          <span key={text(band.label)}><code>{fixed(band.low)}–{fixed(band.high)}</code>{text(band.label)}</span>
        ))}
      </div>
      <div className="studio-actions">
        <section>
          <h3><CheckCircle2 size={13} />Manter</h3>
          <ul>{keep.length ? keep.map((item) => <li key={item}>{item}</li>) : <li>—</li>}</ul>
        </section>
        <section>
          <h3><Wand2 size={13} />Corrigir</h3>
          <ul>{fix.length ? fix.map((item) => <li key={item}>{item}</li>) : <li>—</li>}</ul>
        </section>
        <section>
          <h3><Sparkles size={13} />Ganhos rápidos</h3>
          <ul>{wins.length ? wins.map((item) => <li key={item}>{item}</li>) : <li>—</li>}</ul>
        </section>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ArtifactResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="studio-view">
      <div className="studio-metrics">
        <Metric label="REGRAS" value={count(metrics.rules)} tone={count(metrics.rules) ? 'warning' : 'ok'} />
        <Metric label="IMAGENS" value={count(metrics.images)} />
        <Metric label="SCRIPTS" value={count(metrics.scripts)} />
        <Metric label="LINHAS" value={count(metrics.lines)} />
      </div>
      <p className="studio-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ReferenceResult({ reference }: { reference: Row }) {
  const groups = asRows(reference.groups);
  const bands = asRows(reference.bands);
  const dimensions = asRows(reference.dimensions);
  const motion = asRow(reference.motion);
  const limits = asRow(reference.limits);
  return (
    <div className="studio-reference">
      <div className="studio-metrics">
        <Metric label="SLOTS" value={count(asRow(reference.metrics).slots)} tone="ok" />
        <Metric label="GRUPOS" value={count(asRow(reference.metrics).groups)} />
        <Metric label="DIMENSÕES" value={count(asRow(reference.metrics).dimensions)} />
        <Metric label="BANDAS" value={count(asRow(reference.metrics).bands)} />
      </div>
      <div className="studio-reference-grid">
        {groups.map((group) => (
          <section key={text(group.key)}>
            <header><strong>{text(group.label)}</strong><span>{count(group.slots)} slots</span></header>
            <ul>{asRows(group.tokens).map((token) => <li key={text(token.name)}><code>{text(token.name)}</code><em>{text(token.layer)}</em></li>)}</ul>
          </section>
        ))}
      </div>
      <div className="studio-reference-columns">
        <section>
          <h3>Bandas da crítica</h3>
          <ul>{bands.map((band) => <li key={text(band.label)}><code>{fixed(band.min)}–{fixed(band.max)}</code><strong>{text(band.label)}</strong><span>{text(band.meaning)}</span></li>)}</ul>
        </section>
        <section>
          <h3>Dimensões fixas</h3>
          <ul>{dimensions.map((dimension) => <li key={text(dimension.key)}><strong>{text(dimension.label)}</strong><span>{text(dimension.question)}</span></li>)}</ul>
        </section>
        <section>
          <h3>Movimento e limites</h3>
          <ul>
            <li><code>entrada</code><span>{text(motion.enter)}</span></li>
            <li><code>saída</code><span>{text(motion.exit)}</span></li>
            {asList(motion.rules).map((rule) => <li key={rule}><span>{rule}</span></li>)}
          </ul>
          <p className="studio-note">Tokens ≤ {count(limits.tokensCharacters).toLocaleString('pt-BR')} caracteres · DESIGN ≤ {count(limits.designCharacters).toLocaleString('pt-BR')} · artefato ≤ {count(limits.artifactCharacters).toLocaleString('pt-BR')} · {count(limits.rows)} linhas por entrada.</p>
        </section>
      </div>
    </div>
  );
}

export function EstudioPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<StudioTab>('contract');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);

  const [manifest, setManifest] = useState('');
  const [design, setDesign] = useState('');
  const [tokens, setTokens] = useState('');
  const [pairs, setPairs] = useState('');
  const [entries, setEntries] = useState('');
  const [keep, setKeep] = useState('');
  const [fix, setFix] = useState('');
  const [wins, setWins] = useState('');
  const [artifact, setArtifact] = useState('');

  const result = execution?.result ?? null;
  const resultMarkdown = useMemo(() => (result && typeof result.markdown === 'string' ? result.markdown : ''), [result]);
  const analysis = result ? text(result.analysis) : '';

  useEffect(() => {
    if (!backendOnline || reference) return;
    let active = true;
    void executeSkill('studio.defaults', {}).then((response) => {
      if (!active || !response.ok || !response.result) return;
      setReference(response.result);
    }).catch(() => { /* a aba Base mostra o estado offline */ });
    return () => { active = false; };
  }, [backendOnline, executeSkill, reference]);

  const run = async (skillId: string, parameters: Record<string, unknown>) => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi analisado.');
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

  const loadSample = () => {
    if (tab === 'contract') {
      setManifest(SAMPLE_MANIFEST);
      setDesign(SAMPLE_DESIGN);
      setTokens(SAMPLE_TOKENS);
    } else if (tab === 'contrast') {
      setPairs(SAMPLE_PAIRS);
    } else if (tab === 'critique') {
      setEntries(SAMPLE_CRITIQUE);
      setKeep(SAMPLE_KEEP);
      setFix(SAMPLE_FIX);
      setWins(SAMPLE_WINS);
    } else if (tab === 'artifact') {
      setArtifact(SAMPLE_ARTIFACT);
    }
    setError('');
  };

  const submitContract = (event: React.FormEvent) => {
    event.preventDefault();
    if (!manifest.trim() && !design.trim() && !tokens.trim()) return;
    void run('studio.contract', { manifest, design, tokens, mode: level });
  };

  const submitContrast = (event: React.FormEvent) => {
    event.preventDefault();
    if (!pairs.trim()) return;
    void run('studio.contrast', { pairs, mode: level });
  };

  const submitCritique = (event: React.FormEvent) => {
    event.preventDefault();
    if (!entries.trim()) return;
    void run('studio.critique', { entries, keep, fix, quickWins: wins, mode: level });
  };

  const submitArtifact = (event: React.FormEvent) => {
    event.preventDefault();
    if (!artifact.trim()) return;
    void run('studio.artifact', { artifact, mode: level });
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
  const hasInput = tab === 'contract'
    ? Boolean(manifest.trim() || design.trim() || tokens.trim())
    : tab === 'contrast' ? Boolean(pairs.trim())
      : tab === 'critique' ? Boolean(entries.trim())
        : tab === 'artifact' ? Boolean(artifact.trim()) : false;

  return (
    <div className="studio-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">ESTÚDIO DE DESIGN · CRÍTICA ESTÁTICA</span>
          <h1>Um sistema de design, <span>com contrato e evidência</span></h1>
          <p>Confere manifesto, prosa e tokens, mede contraste WCAG, exige cinco notas com evidência e procura clichês no HTML. Nada é compilado, renderizado ou publicado.</p>
        </div>
      </header>

      <section className="panel studio-intro">
        <span className="studio-intro-icon"><SwatchBook size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>Sem contrato declarado, o agente improvisa a marca</h2>
          <p>A adaptação do open-design aqui é editorial: pacote de design, contraste, crítica e linter. O daemon, o CLI, os plugins, o MCP e o runtime de agente ficam de fora — o JARVIS só lê o que foi declarado.</p>
        </div>
        <ul className="studio-laws">
          {laws.map((law) => <li key={law.key}><strong>{law.title}</strong><span>{law.text}</span></li>)}
        </ul>
      </section>

      <nav className="studio-tabs" aria-label="Modos do estúdio de design">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); if (id === 'base') setExecution(null); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="studio-layout">
        <section className="panel studio-form">
          <header className="studio-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            {tab !== 'base' && (
              <label className="studio-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          {tab !== 'base' && <p className="studio-level-note">{levels.find((item) => item.id === level)?.description}</p>}

          {tab === 'contract' && (
            <form className="form-stack" onSubmit={submitContract}>
              <label className="field">
                <span>manifest.json</span>
                <textarea className="studio-mono studio-short" value={manifest} onChange={(event) => setManifest(event.target.value)} maxLength={20000} rows={6} placeholder={'{\n  "schemaVersion": "od-design-system-project/v1",\n  "id": "acme-papel",\n  "files": { "design": "DESIGN.md", "tokens": "tokens.css" }\n}'} />
              </label>
              <label className="field">
                <span>DESIGN.md</span>
                <textarea value={design} onChange={(event) => setDesign(event.target.value)} maxLength={120000} rows={7} placeholder={'# Marca\n## Tema\n## Cor\n## Tipografia\n## Espaçamento\n## Componentes\n## Movimento\n## Acessibilidade\n## Antíteses'} />
              </label>
              <label className="field">
                <span>tokens.css</span>
                <textarea className="studio-mono" value={tokens} onChange={(event) => setTokens(event.target.value)} maxLength={120000} rows={9} placeholder={':root {\n  --bg: #faf9f6;\n  --fg: #18181b;\n  … 56 slots em 14 grupos\n}'} />
              </label>
              <p className="studio-note">Envie os três para a revisão completa. Só o CSS já confere os 56 slots, temas e movimento; só a prosa já confere seções e placeholders.</p>
              <div className="studio-form-actions">
                <button type="button" className="studio-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !hasInput}>{busy ? <LoaderCircle size={15} className="studio-spin" /> : <FileJson2 size={15} />}Revisar contrato</button>
              </div>
            </form>
          )}

          {tab === 'contrast' && (
            <form className="form-stack" onSubmit={submitContrast}>
              <label className="field">
                <span>Pares de contraste *</span>
                <textarea className="studio-mono" value={pairs} onChange={(event) => setPairs(event.target.value)} maxLength={50000} rows={9} required placeholder={'rótulo | frente | fundo | corpo ou grande\nCorpo | #18181b | #faf9f6 | corpo\nBotão | #ffffff | #0f766e | grande'} />
              </label>
              <ol className="studio-checklist">
                <li>Texto normal exige 4,5:1 (AA) e 7,0:1 (AAA).</li>
                <li>Texto grande exige 3,0:1 (AA) e 4,5:1 (AAA).</li>
                <li>Só hexadecimal de 3 ou 6 dígitos é medido; rgb() e opacidade ficam fora.</li>
              </ol>
              <div className="studio-form-actions">
                <button type="button" className="studio-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !pairs.trim()}>{busy ? <LoaderCircle size={15} className="studio-spin" /> : <Contrast size={15} />}Medir contraste</button>
              </div>
            </form>
          )}

          {tab === 'critique' && (
            <form className="form-stack" onSubmit={submitCritique}>
              <label className="field">
                <span>Notas por dimensão *</span>
                <textarea className="studio-mono" value={entries} onChange={(event) => setEntries(event.target.value)} maxLength={50000} rows={8} required placeholder={'dimensão | nota 0–10 | evidência com referência\nfilosofia | 8 | O chrome mantém vol.04 em .serif em todas as páginas.\nhierarquia | 6 | Na página 3 o .stat usa 40px e o h1 usa 42px.'} />
              </label>
              <div className="studio-split">
                <label className="field"><span>Manter</span><textarea value={keep} onChange={(event) => setKeep(event.target.value)} maxLength={8000} rows={4} placeholder="Um item por linha" /></label>
                <label className="field"><span>Corrigir</span><textarea value={fix} onChange={(event) => setFix(event.target.value)} maxLength={8000} rows={4} placeholder="Um item por linha" /></label>
              </div>
              <label className="field">
                <span>Ganhos rápidos (5–15 min)</span>
                <textarea className="studio-mono" value={wins} onChange={(event) => setWins(event.target.value)} maxLength={8000} rows={4} placeholder={'- Trocar o flex por grid na página 4 (10 min)\n- Ajustar o tracking do kicker (5 min)'} />
              </label>
              <p className="studio-note">Cada nota precisa de evidência com classe, seletor, arquivo, linha, página ou medida. Média acima de 8 é sinalizada como inflação.</p>
              <div className="studio-form-actions">
                <button type="button" className="studio-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !entries.trim()}>{busy ? <LoaderCircle size={15} className="studio-spin" /> : <PenLine size={15} />}Estruturar crítica</button>
              </div>
            </form>
          )}

          {tab === 'artifact' && (
            <form className="form-stack" onSubmit={submitArtifact}>
              <label className="field">
                <span>HTML do artefato *</span>
                <textarea className="studio-mono" value={artifact} onChange={(event) => setArtifact(event.target.value)} maxLength={200000} rows={12} required placeholder={'<!doctype html>\n<html lang="pt-BR">\n  … CSS e JS no mesmo arquivo'} />
              </label>
              <p className="studio-note">Arquivo único: CSS e JS incorporados. O linter é lexical, não renderiza e não executa o documento. O exemplo carrega problemas propositais — gradiente azul→ciano, índice, emoji, métrica e imagem remota.</p>
              <div className="studio-form-actions">
                <button type="button" className="studio-sample" onClick={loadSample}><Palette size={14} />Carregar exemplo</button>
                <button type="submit" className="button button-primary" disabled={busy || !artifact.trim()}>{busy ? <LoaderCircle size={15} className="studio-spin" /> : <Code2 size={15} />}Revisar artefato</button>
              </div>
            </form>
          )}

          {tab === 'base' && (
            <div className="studio-form-static">
              <p className="studio-note">O esquema compartilhado tem 56 slots em 14 grupos. Todo artefato cola este bloco em um <code>&lt;style&gt;</code> só, então <code>var()</code> sem alvo derruba a regra inteira — por isso o contrato trata slot ausente como bloqueio.</p>
              <div className="studio-bands">
                {[['Quebrado', '0–4', 'Reescreva a direção antes de polir.'], ['Funcional', '5–6', 'Resolve o trabalho, sem assinatura.'], ['Forte', '7–8', 'Direção clara e detalhe sob controle.'], ['Excepcional', '9–10', 'Há um momento próprio e defensável.']].map(([label, range, meaning]) => (
                  <span key={label}><code>{range}</code><strong>{label}</strong><em>{meaning}</em></span>
                ))}
              </div>
              <div className="studio-mandate">
                <strong>REGRAS FIXAS</strong>
                <ul>
                  <li>Nunca anime de <code>scale(0)</code>; parta de 0.9 com opacidade.</li>
                  <li><code>ease-in</code> atrasa o trecho que o olho acompanha.</li>
                  <li>Sempre ofereça <code>prefers-reduced-motion: reduce</code>.</li>
                  <li>Cor literal mora em <code>:root</code>; componente usa <code>var()</code>.</li>
                  <li>Preço e número sem fonte não entram na peça.</li>
                </ul>
              </div>
              {reference ? (
                <ReferenceResult reference={reference} />
              ) : (
                <p className="studio-empty"><AlertTriangle size={14} />A referência vem da API Python. {backendOnline ? 'Carregando…' : 'Inicie o núcleo com “npm run dev”.'}</p>
              )}
              <button type="button" className="button button-primary" onClick={() => { setTab('contract'); setError(''); }}><ArrowRight size={15} />Revisar um pacote</button>
            </div>
          )}

          {error && <p className="studio-error" role="alert"><AlertTriangle size={15} />{error}</p>}
        </section>

        <section className="panel studio-result" aria-live="polite">
          <header className="studio-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{result ? analysisLabels[analysis] ?? 'Parecer' : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="studio-result-actions">
                <span className="studio-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="studio-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
              </div>
            )}
          </header>

          {!result && (
            <div className="studio-placeholder">
              <span><Layers size={18} /></span>
              <strong>Somente leitura</strong>
              <p>O parecer aparece aqui com evidência por achado, veredito e limites declarados. Nada é compilado, renderizado, publicado ou enviado a um provedor de design.</p>
              <ul>
                <li>Contrato: manifesto, 8 seções de prosa e 56 slots de token.</li>
                <li>Contraste: razão WCAG por par, com limite de texto normal e grande.</li>
                <li>Crítica: cinco notas, bandas e as três listas de ação.</li>
                <li>Artefato: gradiente roxo, emoji, métrica inventada e acessibilidade.</li>
              </ul>
            </div>
          )}

          {result && (
            <>
              {analysis === 'contract' && <ContractResult result={result} />}
              {analysis === 'contrast' && <ContrastResult result={result} />}
              {analysis === 'critique' && <CritiqueResult result={result} />}
              {analysis === 'artifact' && <ArtifactResult result={result} />}
              {analysis !== 'reference' && <Limitations items={result.limitations} />}
              <details className="studio-json">
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
