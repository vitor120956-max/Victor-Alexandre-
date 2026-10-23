import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Code2,
  FileText,
  Gauge,
  Globe,
  Hand,
  Layers,
  LoaderCircle,
  MousePointerClick,
  ReceiptText,
  Route,
  ScanText,
  ShieldAlert,
  Target,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../navegador.css';

type BrowserTab = 'snapshot' | 'alvo' | 'roteiro' | 'checagem' | 'recibos' | 'limites' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: BrowserTab; label: string; hint: string; icon: typeof Globe }> = [
  { id: 'snapshot', label: 'Snapshot', hint: 'Árvore → índice', icon: ScanText },
  { id: 'alvo', label: 'Alvo', hint: 'Locator → comando', icon: Target },
  { id: 'roteiro', label: 'Roteiro', hint: 'Objetivo → rodadas', icon: Route },
  { id: 'checagem', label: 'Checagem', hint: 'Plano → bloqueios', icon: ShieldAlert },
  { id: 'recibos', label: 'Recibos', hint: 'Log → fechamento', icon: ReceiptText },
  { id: 'limites', label: 'Limites', hint: 'Ação → consentimento', icon: Hand },
  { id: 'regras', label: 'Regras', hint: 'O vocabulário usado', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite' },
  { id: 'full', label: 'Full' },
  { id: 'ultra', label: 'Ultra' },
];

const laws = [
  ['Uma space por objetivo', 'A space nasce uma vez e é retomada pelo nome ou pelo spaceId. Recuperar de página travada criando outra space é a falha clássica.'],
  ['Documento principal antes dos frames', 'O alvo acionável do topo vence; só se não houver correspondência a busca desce para o frame. Dois matches no mesmo escopo é ambíguo.'],
  ['Recibo não é prova', 'O recibo descreve o despacho e os efeitos imediatos. A conclusão precisa de uma condição observável: URL, seletor ou título.'],
  ['Quem decide é você', 'O JARVIS lê o que você cola. Não abre navegador, não clica, não paga e devolve o controle quando a ação exige gente.'],
];

const sampleSnapshot = `root
  heading "Entrar na conta" [level=1]
  textbox "E-mail" [ref=5, loc=css:#email]
  textbox "Senha" [ref=6, loc=css:#senha]
  checkbox "Lembrar de mim" [ref=7]
  button "Entrar" [ref=21, loc=role:button[name="Entrar"]]
  link "Esqueci minha senha" [ref=22, url=https://app.exemplo.com/recuperar]
  iframe [ref=12]
    textbox "Busca" [ref=901, loc=css:#busca]
    button "Pesquisar" [ref=902]
  text "Acesso restrito a clientes."`;

const samplePlan = `const task = await taskSpace("entrar-na-conta-20261023");
const page = task.page("p1");
await page.goto("https://app.exemplo.com/login");
await page.fill("@5", "ana@exemplo.com");
await page.click("@21", { label: "entrar na conta" });
await page.waitForTimeout(2000);
console.log(await page.snapshot());
await task.finish({ keep: [] });`;

const sampleSteps = `clicar | @21 | coberto
preencher | @5 | desabilitado
esperar | loc=css:#home | visivel`;

const sampleLog = `1. clique @21 ok popup=p2
2. esperei #home ok 1200ms
3. baixei relatorio.pdf
4. fechei keep=[p1, p2]`;

const sampleActions = `abrir o painel da conta
preencher o e-mail de acesso
pagar a fatura do cartão
baixar o relatório mensal
resolver o captcha da tela`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const levelLabel: Record<string, string> = { bloqueado: 'bloqueado', confirmar: 'confirmar', liberado: 'liberado' };
const verdictLabel: Record<string, string> = { ok: 'ok', bloqueado: 'bloqueado', atencao: 'atenção', revisar: 'revisar' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="browser-empty"><CheckCircle2 size={14} />Nada bloqueando pelas regras estáticas.</p>;
  return (
    <div className="browser-findings">
      {findings.map((item) => {
        const group = text(item.group);
        return (
          <article className={`browser-finding is-${group}`} key={`${text(item.id)}-${text(item.kind)}-${text(item.location)}`}>
            <header>
              <span className="browser-group">{groupLabel[group] ?? group}</span>
              <strong>{text(item.title)}</strong>
              <code>{text(item.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{text(item.what)}</dd></div>
              <div><dt>Problema</dt><dd>{text(item.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{text(item.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{text(item.ifSkipped)}</dd></div>
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
    <div className="browser-limits">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Report({ markdown }: { markdown: string }) {
  if (!markdown) return null;
  return (
    <details className="browser-report">
      <summary><FileText size={13} />Relatório completo em markdown</summary>
      <pre>{markdown}</pre>
    </details>
  );
}

function SnapshotView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const nodes = asRows(result.rows);
  const roles = asRow(result.porPapel);
  return (
    <div className="browser-view">
      <div className="browser-metrics">
        <Metric label="NÓS" value={count(metrics.total)} />
        <Metric label="ACIONÁVEIS" value={count(metrics.acionaveis)} tone={count(metrics.acionaveis) ? 'ok' : 'danger'} />
        <Metric label="COM REF" value={count(metrics.comRef)} />
        <Metric label="SEM REF" value={count(metrics.semRef)} tone={count(metrics.semRef) ? 'warning' : 'ok'} />
        <Metric label="FRAMES" value={count(metrics.frames)} />
        <Metric label="PROFUNDIDADE" value={count(metrics.profundidade)} />
      </div>
      {Object.keys(roles).length > 0 && (
        <div className="browser-chips">
          {Object.entries(roles).slice(0, 10).map(([role, total]) => (
            <span key={role}><b>{role}</b><i>{String(total)}</i></span>
          ))}
        </div>
      )}
      <div className="browser-table-wrap">
        <table className="browser-table">
          <thead><tr><th>#</th><th>Papel</th><th>Nome</th><th>Ref</th><th>Locator</th><th>Frame</th></tr></thead>
          <tbody>
            {nodes.map((node) => (
              <tr key={`${text(node.linha)}-${text(node.ref)}`} className={node.acionavel ? 'is-actionable' : undefined}>
                <td>{text(node.linha)}</td>
                <td><code>{text(node.papel)}</code></td>
                <td>{text(node.nome) || <em>sem nome</em>}</td>
                <td>{text(node.ref) ? `@${text(node.ref)}` : '—'}</td>
                <td className="is-mono">{text(node.loc) || '—'}</td>
                <td>{text(node.quadro) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function TargetView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const candidates = asRows(result.candidatos);
  const suggestions = asRows(result.sugestoes);
  const resolved = Boolean(metrics.resolvido);
  return (
    <div className="browser-view">
      <div className={`browser-verdict ${resolved ? 'is-ok' : 'is-danger'}`}>
        {resolved ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
        <div>
          <strong>{resolved ? 'Alvo resolvido' : Boolean(metrics.ambiguo) ? 'Alvo ambíguo' : 'Alvo não encontrado'}</strong>
          <p>
            {resolved
              ? `${text(metrics.candidatos)} candidato no ${text(metrics.escopo)}.`
              : 'Ajuste o locator ou tire um novo snapshot antes de agir.'}
          </p>
        </div>
      </div>
      <div className="browser-metrics">
        <Metric label="TIPO" value={text(metrics.tipo)} />
        <Metric label="ESCOPO" value={text(metrics.escopo)} />
        <Metric label="CANDIDATOS" value={count(metrics.candidatos)} tone={count(metrics.candidatos) === 1 ? 'ok' : 'warning'} />
        <Metric label="ACIONÁVEL" value={metrics.acionavel ? 'sim' : 'não'} tone={metrics.acionavel ? 'ok' : 'danger'} />
      </div>
      {text(metrics.comando) && (
        <div className="browser-command">
          <span>COMANDO</span>
          <code>{text(metrics.comando)}</code>
        </div>
      )}
      {candidates.length > 0 && (
        <div className="browser-table-wrap">
          <table className="browser-table">
            <thead><tr><th>#</th><th>Papel</th><th>Nome</th><th>Ref</th><th>Locator</th></tr></thead>
            <tbody>
              {candidates.map((node) => (
                <tr key={`${text(node.linha)}-${text(node.ref)}`}>
                  <td>{text(node.linha)}</td>
                  <td><code>{text(node.papel)}</code></td>
                  <td>{text(node.nome) || '—'}</td>
                  <td>{text(node.ref) ? `@${text(node.ref)}` : '—'}</td>
                  <td className="is-mono">{text(node.loc) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {suggestions.length > 0 && (
        <div className="browser-suggestions">
          <strong>CANDIDATOS PRÓXIMOS</strong>
          {suggestions.map((item) => (
            <code key={`${text(item.papel)}-${text(item.nome)}`}>{text(item.papel)} "{text(item.nome)}" → {text(item.seletor)}</code>
          ))}
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function PlanView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const rounds = asRows(result.rodadas);
  return (
    <div className="browser-view">
      {result.exigeConfirmacao ? (
        <div className="browser-banner">
          <Hand size={15} />
          <div><strong>Ponto de confirmação humana.</strong><p>O objetivo tem verbo de risco; o roteiro para antes de pagar, excluir ou publicar.</p></div>
        </div>
      ) : null}
      <div className="browser-metrics">
        <Metric label="RODADAS" value={count(metrics.rodadas)} />
        <Metric label="ORÇAMENTO" value={count(metrics.orcamento)} tone={count(metrics.rodadas) > count(metrics.orcamento) ? 'danger' : 'ok'} />
        <Metric label="PASSOS" value={count(metrics.passos)} />
        <Metric label="RISCO" value={text(metrics.risco)} tone={text(metrics.risco) === 'alto' ? 'warning' : 'ok'} />
      </div>
      <div className="browser-rounds">
        {rounds.map((round) => (
          <article className="browser-round" key={text(round.numero)}>
            <header>
              <span>RODADA {text(round.numero)}</span>
              <strong>{text(round.titulo)}</strong>
              <small>{text(round.objetivo)}</small>
            </header>
            <pre className="browser-code">{text(round.codigo)}</pre>
            <div className="browser-actions-list">
              {asRows(round.acoes).map((action) => (
                <span key={`${text(round.numero)}-${text(action.passo)}-${text(action.acao)}`}>
                  <b>{text(action.acao)}</b>{text(action.alvo) || '—'}
                </span>
              ))}
            </div>
            <p className="browser-note">{text(round.observacao)}</p>
          </article>
        ))}
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function CheckView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const steps = asRows(result.passos);
  const patterns = asRows(result.padroes);
  return (
    <div className="browser-view">
      <div className="browser-metrics">
        <Metric label="PASSOS" value={count(metrics.passos)} />
        <Metric label="BLOQUEADOS" value={count(metrics.bloqueados)} tone={count(metrics.bloqueados) ? 'danger' : 'ok'} />
        <Metric label="ATENÇÃO" value={count(metrics.atencao)} tone={count(metrics.atencao) ? 'warning' : 'ok'} />
        <Metric label="PADRÕES" value={count(metrics.padroes)} tone={count(metrics.padroes) ? 'warning' : 'ok'} />
      </div>
      {patterns.length > 0 && (
        <div className="browser-chips">
          {patterns.map((pattern) => <span key={text(pattern.regra)}><b>{text(pattern.regra)}</b><i>{text(pattern.titulo)}</i></span>)}
        </div>
      )}
      {steps.length > 0 && (
        <div className="browser-table-wrap">
          <table className="browser-table">
            <thead><tr><th>#</th><th>Ação</th><th>Alvo</th><th>Estado</th><th>Veredito</th></tr></thead>
            <tbody>
              {steps.map((step) => (
                <tr key={text(step.passo)}>
                  <td>{text(step.passo)}</td>
                  <td><code>{text(step.acao)}</code></td>
                  <td className="is-mono">{text(step.alvo) || '—'}</td>
                  <td>{text(step.estado) || '—'}</td>
                  <td><span className={`browser-badge is-${text(step.veredito)}`}>{verdictLabel[text(step.veredito)] ?? text(step.veredito)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ReceiptView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const receipts = asRows(result.recibos);
  return (
    <div className="browser-view">
      <div className="browser-metrics">
        <Metric label="PASSOS" value={count(metrics.passos)} />
        <Metric label="AÇÕES" value={count(metrics.acoes)} />
        <Metric label="OBSERVAÇÕES" value={count(metrics.observacoes)} tone={count(metrics.observacoes) ? 'ok' : 'warning'} />
        <Metric label="FECHAMENTOS" value={count(metrics.fechamentos)} tone={count(metrics.fechamentos) === 1 ? 'ok' : 'danger'} />
      </div>
      <div className="browser-table-wrap">
        <table className="browser-table">
          <thead><tr><th>#</th><th>Ação</th><th>Alvo</th><th>Resultado</th><th>Efeito</th></tr></thead>
          <tbody>
            {receipts.map((receipt) => (
              <tr key={text(receipt.passo)}>
                <td>{text(receipt.passo)}</td>
                <td><code>{text(receipt.acao)}</code></td>
                <td className="is-mono">{text(receipt.alvo) || '—'}</td>
                <td><span className={`browser-badge is-${text(receipt.resultado) === 'ok' ? 'ok' : 'atencao'}`}>{text(receipt.resultado)}</span></td>
                <td>{text(receipt.popup) ? `popup ${text(receipt.popup)}` : text(receipt.dialogo) ? `diálogo: ${text(receipt.dialogo)}` : text(receipt.baixado) || text(receipt.salvo) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function LimitsView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const verdicts = asRows(result.veredictos);
  return (
    <div className="browser-view">
      <div className="browser-metrics">
        <Metric label="AÇÕES" value={count(metrics.acoes)} />
        <Metric label="BLOQUEADAS" value={count(metrics.bloqueadas)} tone={count(metrics.bloqueadas) ? 'danger' : 'ok'} />
        <Metric label="CONFIRMAR" value={count(metrics.confirmar)} tone={count(metrics.confirmar) ? 'warning' : 'ok'} />
        <Metric label="LIBERADAS" value={count(metrics.liberadas)} tone="ok" />
      </div>
      <div className="browser-table-wrap">
        <table className="browser-table">
          <thead><tr><th>#</th><th>Ação</th><th>Nível</th><th>Regra</th><th>O que fazer</th></tr></thead>
          <tbody>
            {verdicts.map((verdict) => (
              <tr key={text(verdict.passo)}>
                <td>{text(verdict.passo)}</td>
                <td>{text(verdict.acao)}</td>
                <td><span className={`browser-badge is-${text(verdict.nivel)}`}>{levelLabel[text(verdict.nivel)] ?? text(verdict.nivel)}</span></td>
                <td>{text(verdict.titulo)}</td>
                <td>{text(verdict.fazer)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {text(result.handoff) && (
        <div className="browser-handoff">
          <Hand size={15} />
          <div><strong>Handoff</strong><p>{text(result.handoff)}</p></div>
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function ReferenceView({ reference }: { reference: Row | null }) {
  if (!reference) return <p className="browser-empty"><LoaderCircle size={14} />Carregando o catálogo…</p>;
  const roles = asRows(reference.papeis);
  const targets = asRows(reference.alvos);
  const actions = asRows(reference.acoes);
  const states = asRows(reference.estados);
  const limits = asRows(reference.limites);
  const patterns = asRows(reference.padroes);
  const budget = asRows(reference.orcamento);
  return (
    <div className="browser-reference">
      <div className="browser-columns">
        <section>
          <h3><Layers size={13} />Papéis</h3>
          {roles.map((role) => (
            <div className="browser-ref-row" key={text(role.papel)}>
              <code>{text(role.papel)}</code><span>{text(role.rotulo)}</span>
            </div>
          ))}
        </section>
        <section>
          <h3><Target size={13} />Formatos de alvo</h3>
          {targets.map((target) => (
            <div className="browser-ref-row" key={text(target.tipo)}>
              <code>{text(target.tipo)}</code><span>{text(target.formato)}</span>
            </div>
          ))}
        </section>
        <section>
          <h3><Gauge size={13} />Estados</h3>
          {states.map((state) => (
            <div className="browser-ref-row" key={text(state.estado)}>
              <code>{text(state.estado)}</code><span>{text(state.titulo)}</span>
            </div>
          ))}
        </section>
        <section>
          <h3><Code2 size={13} />Ações</h3>
          {actions.slice(0, 20).map((action) => (
            <div className="browser-ref-row" key={text(action.acao)}>
              <code>{text(action.acao)}</code><span>page.{text(action.api)}</span>
            </div>
          ))}
        </section>
      </div>
      <section>
        <h3><ShieldAlert size={13} />Limites</h3>
        <div className="browser-table-wrap">
          <table className="browser-table">
            <thead><tr><th>Nível</th><th>Regra</th><th>Por que</th></tr></thead>
            <tbody>
              {limits.map((limit) => (
                <tr key={text(limit.id)}>
                  <td><span className={`browser-badge is-${text(limit.nivel)}`}>{levelLabel[text(limit.nivel)] ?? text(limit.nivel)}</span></td>
                  <td>{text(limit.titulo)}</td>
                  <td>{text(limit.porque)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><AlertTriangle size={13} />Padrões de código</h3>
        <div className="browser-table-wrap">
          <table className="browser-table">
            <thead><tr><th>Grupo</th><th>Regra</th><th>Correção</th></tr></thead>
            <tbody>
              {patterns.map((pattern) => (
                <tr key={text(pattern.id)}>
                  <td>{groupLabel[text(pattern.grupo)] ?? text(pattern.grupo)}</td>
                  <td>{text(pattern.titulo)}</td>
                  <td>{text(pattern.correcao)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><MousePointerClick size={13} />Orçamento</h3>
        {budget.map((item) => (
          <div className="browser-ref-row" key={text(item.regra)}>
            <code>{text(item.regra)}</code><span>{text(item.limite)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

export function NavegadorPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<BrowserTab>('snapshot');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);
  const [snapshot, setSnapshot] = useState(sampleSnapshot);
  const [target, setTarget] = useState('loc=role:button[name="Entrar"]');
  const [action, setAction] = useState('clicar');
  const [value, setValue] = useState('');
  const [label, setLabel] = useState('entrar na conta');
  const [goal, setGoal] = useState('entrar na conta e chegar ao painel');
  const [url, setUrl] = useState('https://app.exemplo.com/login');
  const [budget, setBudget] = useState(4);
  const [plan, setPlan] = useState(samplePlan);
  const [steps, setSteps] = useState(sampleSteps);
  const [log, setLog] = useState(sampleLog);
  const [actions, setActions] = useState(sampleActions);

  const result = execution?.ok ? asRow(execution.result) : null;
  const markdown = useMemo(() => text(result?.markdown), [result]);

  const loadReference = async () => {
    if (!backendOnline) return;
    try {
      const response = await executeSkill('navegador.regras', {});
      if (response.ok) setReference(asRow(response.result));
    } catch {
      setReference(null);
    }
  };

  const openTab = (next: BrowserTab) => {
    setTab(next);
    setError('');
    setExecution(null);
    if (next === 'regras' && !reference) void loadReference();
  };

  const run = async () => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi calculado.');
      return;
    }
    const skill = `navegador.${tab}`;
    const parameters: Record<string, unknown> = { modo: level };
    if (tab === 'snapshot') Object.assign(parameters, { snapshot });
    if (tab === 'alvo') Object.assign(parameters, { snapshot, alvo: target, acao: action, valor: value, rotulo: label });
    if (tab === 'roteiro') Object.assign(parameters, { objetivo: goal, url, snapshot, orcamento: budget });
    if (tab === 'checagem') Object.assign(parameters, { plano: plan, passos: steps });
    if (tab === 'recibos') Object.assign(parameters, { log });
    if (tab === 'limites') Object.assign(parameters, { acoes: actions });
    setBusy(true);
    setError('');
    setExecution(null);
    try {
      const response = await executeSkill(skill, parameters);
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

  const copyReport = async () => {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      pushToast('Relatório copiado.', 'success');
    } catch {
      pushToast('Não foi possível copiar; selecione o texto do relatório.', 'error');
    }
  };

  const loadSample = () => {
    setSnapshot(sampleSnapshot);
    setTarget('loc=role:button[name="Entrar"]');
    setAction('clicar');
    setValue('');
    setLabel('entrar na conta');
    setGoal('entrar na conta e chegar ao painel');
    setUrl('https://app.exemplo.com/login');
    setBudget(4);
    setPlan(samplePlan);
    setSteps(sampleSteps);
    setLog(sampleLog);
    setActions(sampleActions);
  };

  const needsSnapshot = tab === 'snapshot' || tab === 'alvo' || tab === 'roteiro';
  const heading = tab === 'snapshot' ? 'Leitura do snapshot'
    : tab === 'alvo' ? 'Resolução de alvo'
      : tab === 'roteiro' ? 'Roteiro de rodadas'
        : tab === 'checagem' ? 'Checagem antes de agir'
          : tab === 'recibos' ? 'Recibos e fechamento'
            : tab === 'limites' ? 'Limites e consentimento' : 'Catálogo de regras';
  const description = tab === 'snapshot' ? 'A árvore vira índice: papéis, nomes, refs, locators e frames.'
    : tab === 'alvo' ? 'Um locator por vez; o documento principal vence os frames.'
      : tab === 'roteiro' ? 'Três rodadas: abrir, agir, verificar e fechar.'
        : tab === 'checagem' ? 'Código e estados do alvo contra 15 padrões e 10 causas.'
          : tab === 'recibos' ? 'Despacho separado de verificação; popup, diálogo e download cobrados.'
            : tab === 'limites' ? 'Bloqueado, confirmar ou liberado — com o handoff escrito.'
              : 'Papéis, alvos, estados, padrões, limites e orçamento.';

  return (
    <div className="browser-page">
      <section className="browser-intro panel">
        <span className="browser-intro-icon"><Globe size={20} /></span>
        <div>
          <span className="eyebrow">TRABALHO · NAVEGADOR ASSISTIDO</span>
          <h2>Navegador</h2>
          <p>
            Lê o snapshot que você cola, resolve alvos como o ego-browser, monta o roteiro de rodadas,
            checa planos e recibos e classifica o que exige a sua mão. Nada é aberto, clicado ou pago aqui.
          </p>
          <ul className="browser-laws">
            {laws.map(([title, body]) => (
              <li key={title}><strong>{title}</strong><span>{body}</span></li>
            ))}
          </ul>
        </div>
      </section>

      <nav className="browser-tabs">
        {tabs.map(({ id, label: tabLabel, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => openTab(id)}>
            <Icon size={15} />
            <span>{tabLabel}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="browser-layout">
        <section className="browser-form panel">
          <header className="browser-form-head">
            <div>
              <span className="eyebrow">ENTRADA</span>
              <h2>{heading}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="browser-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          <p className="browser-level-note">{description}</p>

          {tab === 'regras' && (
            <div className="browser-about">
              <p>O catálogo é lido da skill <code>navegador.regras</code>. Ele descreve o vocabulário usado pelas outras seis: 18 ações de página, 10 estados de alvo, 15 padrões de código e 11 regras de consentimento.</p>
              <p><b>Escopo:</b> o JARVIS não abre navegador. Ele prepara e audita o texto que o seu agente executa no ego-browser, inclusive quando o certo é parar e devolver o controle.</p>
            </div>
          )}

          {needsSnapshot && (
            <label className="field">
              <span>Snapshot <b>*</b></span>
              <textarea
                className="browser-mono"
                rows={tab === 'roteiro' ? 8 : 10}
                value={snapshot}
                onChange={(event) => setSnapshot(event.target.value)}
                spellCheck={false}
              />
            </label>
          )}

          {tab === 'alvo' && (
            <>
              <label className="field">
                <span>Alvo</span>
                <input value={target} onChange={(event) => setTarget(event.target.value)} spellCheck={false} />
              </label>
              <div className="browser-inline">
                <label className="field">
                  <span>Ação</span>
                  <select value={action} onChange={(event) => setAction(event.target.value)}>
                    {['clicar', 'clicar-duplo', 'pairar', 'preencher', 'selecionar', 'focar', 'teclar', 'enviar-arquivo', 'esperar'].map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Valor</span>
                  <input value={value} onChange={(event) => setValue(event.target.value)} placeholder="<valor real>" />
                </label>
              </div>
              <label className="field">
                <span>Rótulo do cursor</span>
                <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="3 a 6 palavras" />
              </label>
            </>
          )}

          {tab === 'roteiro' && (
            <>
              <label className="field">
                <span>Objetivo <b>*</b></span>
                <textarea rows={3} value={goal} onChange={(event) => setGoal(event.target.value)} />
              </label>
              <div className="browser-inline">
                <label className="field">
                  <span>URL de partida</span>
                  <input value={url} onChange={(event) => setUrl(event.target.value)} spellCheck={false} />
                </label>
                <label className="field">
                  <span>Rodadas</span>
                  <select value={budget} onChange={(event) => setBudget(Number(event.target.value))}>
                    {[2, 3, 4, 5, 6, 7, 8].map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
              </div>
            </>
          )}

          {tab === 'checagem' && (
            <>
              <label className="field">
                <span>Plano em JavaScript</span>
                <textarea className="browser-mono" rows={10} value={plan} onChange={(event) => setPlan(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Passos <em>ação | alvo | estado</em></span>
                <textarea className="browser-mono" rows={4} value={steps} onChange={(event) => setSteps(event.target.value)} spellCheck={false} />
              </label>
            </>
          )}

          {tab === 'recibos' && (
            <label className="field">
              <span>Log de execução <b>*</b></span>
              <textarea className="browser-mono" rows={10} value={log} onChange={(event) => setLog(event.target.value)} spellCheck={false} />
            </label>
          )}

          {tab === 'limites' && (
            <label className="field">
              <span>Ações pretendidas <b>*</b></span>
              <textarea className="browser-mono" rows={10} value={actions} onChange={(event) => setActions(event.target.value)} spellCheck={false} />
            </label>
          )}

          {tab !== 'regras' && (
            <div className="browser-form-actions">
              <button type="button" className="browser-sample" onClick={loadSample}><Clipboard size={12} />Carregar exemplo</button>
              <button type="button" className="button-primary" onClick={() => void run()} disabled={busy || !backendOnline}>
                {busy ? <LoaderCircle size={13} className="spin" /> : <ArrowRight size={13} />}
                {busy ? 'Lendo…' : 'Executar'}
              </button>
            </div>
          )}
          {!backendOnline && <p className="browser-note">A API Python está offline; nada será calculado até ela voltar.</p>}
          {error && <div className="browser-error"><AlertTriangle size={14} /><span>{error}</span></div>}
        </section>

        <section className="browser-result panel">
          <header className="browser-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h2>{tab === 'regras' ? 'Catálogo de regras' : result ? heading : 'Aguardando execução'}</h2>
            </div>
            <div className="browser-result-actions">
              {markdown && <button type="button" className="browser-ghost" onClick={() => void copyReport()}><Clipboard size={12} />Copiar</button>}
            </div>
          </header>

          {!result && tab !== 'regras' && (
            <div className="browser-placeholder">
              <MousePointerClick size={22} />
              <strong>Cole o texto e rode a skill.</strong>
              <p>O resultado é determinístico: mesmas entradas, mesmos achados. Nada é lido de portais nem de arquivos seus.</p>
              <button type="button" className="browser-sample" onClick={() => void run()} disabled={!backendOnline || busy}><ArrowRight size={12} />Preencher com o exemplo</button>
            </div>
          )}

          {tab === 'regras' && !reference && <p className="browser-empty"><LoaderCircle size={14} />Carregando…</p>}
          {tab === 'regras' && reference && <ReferenceView reference={reference} />}

          {result && tab === 'snapshot' && <SnapshotView result={result} />}
          {result && tab === 'alvo' && <TargetView result={result} />}
          {result && tab === 'roteiro' && <PlanView result={result} />}
          {result && tab === 'checagem' && <CheckView result={result} />}
          {result && tab === 'recibos' && <ReceiptView result={result} />}
          {result && tab === 'limites' && <LimitsView result={result} />}
          {result && <Limitations items={result.limitations} />}
          {result && <Report markdown={markdown} />}
        </section>
      </div>
    </div>
  );
}
