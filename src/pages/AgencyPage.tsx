import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Eye,
  LayoutList,
  LoaderCircle,
  ShieldCheck,
  Users,
  Wallet,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../agencia.css';

type AgencyTab = 'roster' | 'board' | 'budget' | 'watchdog' | 'permissions' | 'baseline';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: AgencyTab; label: string; hint: string; icon: typeof Users }> = [
  { id: 'roster', label: 'Equipe', hint: 'Quem responde a quem', icon: Users },
  { id: 'board', label: 'Quadro', hint: 'Trabalho e bloqueios', icon: LayoutList },
  { id: 'budget', label: 'Orçamento', hint: 'Teto e parada', icon: Wallet },
  { id: 'watchdog', label: 'Parada', hint: 'Watchdog de subárvore', icon: Eye },
  { id: 'permissions', label: 'Permissões', hint: 'Grants e exceções', icon: ShieldCheck },
  { id: 'baseline', label: 'Base', hint: 'O que é padrão', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string; description: string }> = [
  { id: 'lite', label: 'Lite', description: 'Só o que bloqueia.' },
  { id: 'full', label: 'Full', description: 'Padrão: bloqueios e correções.' },
  { id: 'ultra', label: 'Ultra', description: 'Inclui perguntas para a revisão.' },
];

const laws = [
  { key: 'heartbeat', title: 'Recebe heartbeat, foi contratado', text: 'Só entra no quadro quem tem identidade, estado e teto declarados. Nada é convidado por acidente.' },
  { key: 'owner', title: 'Todo trabalho tem um dono', text: 'Uma tarefa em andamento sem responsável para no próximo ciclo — e ninguém percebe.' },
  { key: 'stop', title: 'Toda parada tem revisão', text: 'Subárvore sem caminho vivo gera uma única revisão, suprimida enquanto a impressão digital não mudar.' },
  { key: 'limit', title: 'Todo limite tem parada', text: 'Alerta sem hard stop é apenas um número no painel. O teto só vale quando interrompe.' },
];

const granted = [
  ['agents:configure', 'Configurar agentes subordinados'],
  ['agents:suggest-changes', 'Sugerir mudanças em agentes'],
  ['skills:create', 'Criar skills no escopo'],
  ['skills:suggest-changes', 'Sugerir mudanças em skills'],
  ['tools:manage_connections', 'Gerenciar conexões da equipe'],
  ['tools:profiles', 'Editar perfis de ferramentas'],
  ['tools:view_audit', 'Ver auditoria das ferramentas'],
  ['tools:use', 'Usar ferramentas conectadas'],
  ['tools:manage_runtime', 'Gerenciar runtime das ferramentas'],
  ['audit:view_agent_actions', 'Ver ações de agentes'],
  ['inbox:manage', 'Gerenciar a caixa de trabalho'],
  ['tasks:assign', 'Atribuir tarefas'],
  ['tasks:assign_scope', 'Atribuir escopo'],
  ['tasks:manage_active_checkouts', 'Gerenciar checkouts'],
  ['canCreateAgents', 'Criar agentes na cota'],
  ['canCreateSkills', 'Criar skills'],
  ['config:read_own', 'Ler a própria configuração'],
  ['self:wake', 'Acordar pelo heartbeat'],
];

const denied = [
  ['agents:create', 'Criar agentes fora do fluxo'],
  ['environments:manage', 'Criar ou alterar ambientes'],
  ['tools:admin', 'Administrar ferramentas da empresa'],
  ['users:invite', 'Convidar pessoas'],
  ['users:manage_permissions', 'Alterar permissões de pessoas'],
  ['joins:approve', 'Aprovar entrada de membros'],
];

const exceptions = [
  'Agentes de baixa confiança e agentes gerenciados ficam de fora dos grants novos até revisão explícita.',
  'Sem backfill: agentes existentes mantêm o que têm até uma revisão registrada.',
  'O agente não define adapter de processo, comando de host, cwd, env arbitrário nem sandbox de filesystem.',
];

const analysisLabels: Record<string, string> = {
  roster: 'Equipe', board: 'Quadro', budget: 'Orçamento', watchdog: 'Parada', permissions: 'Permissões',
};

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const money = (value: unknown, currency = 'US$'): string => `${currency} ${count(value).toFixed(2)}`;
const stateLabels: Record<string, string> = {
  active: 'ativo', paused: 'pausado', pending: 'pendente', terminated: 'encerrado', rejected: 'rejeitado',
  budget_blocked: 'sem orçamento', triage: 'triagem', unstarted: 'a fazer', started: 'em andamento',
  review: 'em revisão', blocked: 'bloqueado', waiting: 'aguardando', done: 'concluído',
  cancelled: 'cancelado', queued: 'na fila', retry: 'reagendado', unknown: 'desconhecido',
};
const stateLabel = (value: unknown): string => stateLabels[text(value)] ?? text(value);

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function Limitations({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="agency-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="agency-empty">Nenhum candidato pelas regras estáticas.</p>;
  return (
    <div className="agency-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`agency-finding is-${group}`} key={`${text(finding.id)}-${text(finding.location)}`}>
            <header>
              <span className="agency-group">{group === 'must' ? 'obrigatório' : group === 'should' ? 'corrigir' : 'opcional'}</span>
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

function RosterResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const agents = asRows(result.rows);
  return (
    <div className="agency-view">
      <div className="agency-metrics">
        <Metric label="AGENTES" value={count(metrics.agents)} />
        <Metric label="ATIVOS" value={count(metrics.active)} />
        <Metric label="RAIZ HUMANA" value={count(metrics.roots)} />
        <Metric label="ORÇAMENTO/MÊS" value={count(metrics.monthlyBudget).toFixed(2)} />
      </div>
      <p className="agency-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="agency-scroll">
        <table className="agency-table">
          <thead><tr><th>Agente</th><th>Papel</th><th>Responde a</th><th>Estado</th><th>Limite</th><th>Permissões</th></tr></thead>
          <tbody>
            {agents.map((agent) => (
              <tr key={text(agent.name)}>
                <td><strong>{text(agent.name)}</strong></td>
                <td>{text(agent.role) || '—'}</td>
                <td>{text(agent.manager) || '—'}</td>
                <td><span className={`agency-state is-${text(agent.status)}`}>{stateLabel(agent.status)}</span></td>
                <td>{count(agent.budget).toFixed(2)}</td>
                <td>{asList(agent.permissions).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function BoardResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const tasks = asRows(result.rows);
  return (
    <div className="agency-view">
      <div className="agency-metrics">
        <Metric label="TAREFAS" value={count(metrics.tasks)} />
        <Metric label="EM ANDAMENTO" value={`${count(metrics.wip)}/${count(metrics.wipLimit)}`} />
        <Metric label="BLOQUEADAS" value={count(metrics.blocked)} />
        <Metric label="PARADAS" value={count(metrics.stale)} />
      </div>
      <p className="agency-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="agency-scroll">
        <table className="agency-table">
          <thead><tr><th>ID</th><th>Título</th><th>Dono</th><th>Estado</th><th>Bloqueadores</th><th>Atualizado</th></tr></thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={text(task.id)}>
                <td><code>{text(task.id)}</code></td>
                <td>{text(task.title)}{task.evidence ? <span className="agency-badge is-ok">evidência</span> : <span className="agency-badge is-warning">sem evidência</span>}</td>
                <td>{text(task.owner) || '—'}</td>
                <td><span className={`agency-state is-${text(task.status)}`}>{stateLabel(task.status)}</span></td>
                <td>{asList(task.blockers).join(', ') || '—'}</td>
                <td>{text(task.updated) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function BudgetResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const rows = asRows(result.rows);
  const currency = text(metrics.currency) || 'US$';
  return (
    <div className="agency-view">
      <div className="agency-metrics">
        <Metric label="LIMITE" value={money(metrics.totalLimit, currency)} />
        <Metric label="GASTO" value={money(metrics.totalSpent, currency)} />
        <Metric label="UTILIZAÇÃO" value={`${count(metrics.utilization).toFixed(1)}%`} />
        <Metric label="ACIMA DO TETO" value={count(metrics.overBudget)} />
      </div>
      <p className="agency-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="agency-scroll">
        <table className="agency-table">
          <thead><tr><th>Agente</th><th>Limite</th><th>Gasto</th><th>Uso</th><th>Parada</th><th>Projeção</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={text(row.agent)}>
                <td><strong>{text(row.agent)}</strong></td>
                <td>{money(row.limit, currency)}</td>
                <td>{money(row.spent, currency)}</td>
                <td><span className={`agency-state is-${count(row.utilization) >= 100 ? 'blocked' : count(row.utilization) >= 80 ? 'review' : 'done'}`}>{count(row.utilization).toFixed(1)}%</span></td>
                <td>{row.hardStop ? 'sim' : 'não'}</td>
                <td>{row.projected === null ? '—' : money(row.projected, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

function WatchdogResult({ result, onUseFingerprint }: { result: Row; onUseFingerprint: (fingerprint: string) => void }) {
  const metrics = asRow(result.metrics);
  const claims = asRows(result.claims);
  return (
    <div className="agency-view">
      <div className="agency-metrics">
        <Metric label="FOLHAS" value={count(metrics.leaves)} />
        <Metric label="CAMINHO VIVO" value={count(metrics.live)} />
        <Metric label="NÃO VERIFICADAS" value={count(metrics.unverified)} />
        <Metric label="REVISÃO" value={result.fired ? 'dispara' : result.suppressed ? 'suprimida' : 'não'} />
      </div>
      <p className="agency-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="agency-fingerprint">
        <div>
          <span>IMPRESSÃO DIGITAL</span>
          <code>{text(result.fingerprint) || 'não calculada enquanto houver caminho vivo'}</code>
        </div>
        <div>
          <span>TAREFA DE REVISÃO</span>
          <code>{text(result.reviewTask) || '—'}</code>
        </div>
      </div>
      {result.fingerprint ? (
        <button type="button" className="agency-copy agency-fingerprint-use" onClick={() => onUseFingerprint(text(result.fingerprint))}>
          <Clipboard size={13} />Usar esta impressão digital na próxima verificação
        </button>
      ) : null}
      {claims.length > 0 && (
        <div className="agency-scroll">
          <table className="agency-table">
            <thead><tr><th>Tarefa</th><th>Estado</th><th>Alegação</th><th>Leitura</th><th>Próximo passo</th></tr></thead>
            <tbody>
              {claims.map((claim) => (
                <tr key={text(claim.id)}>
                  <td><code>{text(claim.id)}</code></td>
                  <td><span className={`agency-state is-${text(claim.status)}`}>{stateLabel(claim.status)}</span></td>
                  <td>{claim.verified ? <span className="agency-badge is-ok">verificada</span> : <span className="agency-badge is-warning">não verificada</span>}</td>
                  <td>{text(claim.reason) || '—'}</td>
                  <td>{text(claim.action) || '—'}</td>
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

function PermissionsResult({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const rows = asRows(result.rows);
  return (
    <div className="agency-view">
      <div className="agency-metrics">
        <Metric label="AGENTES" value={count(metrics.agents)} />
        <Metric label="GRANTS" value={count(metrics.grants)} />
        <Metric label="NEGADAS CONCEDIDAS" value={count(metrics.deniedGranted)} />
        <Metric label="EXCEÇÕES" value={count(metrics.lowTrust) + count(metrics.managed)} />
      </div>
      <p className="agency-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <div className="agency-scroll">
        <table className="agency-table">
          <thead><tr><th>Agente</th><th>Concedido</th><th>Negado</th><th>Exceção</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={text(row.agent)}>
                <td><strong>{text(row.agent)}</strong></td>
                <td>{asList(row.granted).join(', ') || '—'}</td>
                <td>{asList(row.denied).join(', ') || '—'}</td>
                <td>{row.lowTrust ? 'baixa confiança' : row.managed ? 'gerenciado' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
    </div>
  );
}

export function AgencyPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<AgencyTab>('roster');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const [roster, setRoster] = useState('');
  const [tasks, setTasks] = useState('');
  const [wipLimit, setWipLimit] = useState(5);
  const [staleDays, setStaleDays] = useState(3);
  const [referenceDate, setReferenceDate] = useState('');
  const [entries, setEntries] = useState('');
  const [companyBudget, setCompanyBudget] = useState('');
  const [currency, setCurrency] = useState('US$');
  const [periodDay, setPeriodDay] = useState(0);
  const [daysInMonth, setDaysInMonth] = useState(30);
  const [watched, setWatched] = useState('');
  const [subtree, setSubtree] = useState('');
  const [instructions, setInstructions] = useState('');
  const [exclude, setExclude] = useState('');
  const [lastFingerprint, setLastFingerprint] = useState('');
  const [permissions, setPermissions] = useState('');
  const [lowTrust, setLowTrust] = useState(false);
  const [managed, setManaged] = useState(false);
  const [baseline, setBaseline] = useState({ granted, denied, exceptions });

  const result = execution?.result ?? null;
  const resultMarkdown = useMemo(() => (result && typeof result.markdown === 'string' ? result.markdown : ''), [result]);

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void executeSkill('agency.defaults', {}).then((response) => {
      if (!active || !response.ok || !response.result) return;
      const payload = response.result;
      const nextGranted = asRows(payload.granted).map((item) => [text(item.key), text(item.reason)] as [string, string]);
      const nextDenied = asRows(payload.denied).map((item) => [text(item.key), text(item.reason)] as [string, string]);
      setBaseline({
        granted: nextGranted.length ? nextGranted : granted,
        denied: nextDenied.length ? nextDenied : denied,
        exceptions: asList(payload.exceptions).length ? asList(payload.exceptions) : exceptions,
      });
    }).catch(() => { /* a linha de base local continua válida */ });
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

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

  const submitRoster = (event: React.FormEvent) => {
    event.preventDefault();
    if (!roster.trim()) return;
    void run('agency.roster', { roster, mode: level });
  };

  const submitBoard = (event: React.FormEvent) => {
    event.preventDefault();
    if (!tasks.trim()) return;
    void run('agency.board', {
      tasks, mode: level, wipLimit: Number(wipLimit), staleDays: Number(staleDays), referenceDate: referenceDate.trim(),
    });
  };

  const submitBudget = (event: React.FormEvent) => {
    event.preventDefault();
    if (!entries.trim()) return;
    void run('agency.budget', {
      entries, mode: level, companyBudget: companyBudget.trim(), currency: currency.trim() || 'US$',
      periodDay: Number(periodDay), daysInMonth: Number(daysInMonth),
    });
  };

  const submitWatchdog = (event: React.FormEvent) => {
    event.preventDefault();
    if (!watched.trim() || !subtree.trim()) return;
    void run('agency.watchdog', {
      watched: watched.trim(), tasks: subtree, instructions, exclude, lastFingerprint: lastFingerprint.trim(), mode: level,
    });
  };

  const submitPermissions = (event: React.FormEvent) => {
    event.preventDefault();
    if (!permissions.trim()) return;
    void run('agency.permissions', { entries: permissions, mode: level, lowTrust, managed });
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
  const analysis = result ? text(result.analysis) : '';

  return (
    <div className="agency-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">GOVERNO DE AGENTES · ANÁLISE ESTÁTICA</span>
          <h1>Uma empresa de agentes, <span>com dono e teto</span></h1>
          <p>Lê a equipe, o quadro, o orçamento e as permissões que você declara. Encontra trabalho sem dono, conclusão sem evidência, limite sem parada e watchdog sem mandato. Nada é executado ou conectado.</p>
        </div>
      </header>

      <section className="panel agency-intro">
        <span className="agency-intro-icon"><BadgeCheck size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>Autonomia sem dono é custo sem controle</h2>
          <p>A adaptação do paperclip aqui é de governança: identidade, hierarquia, trabalho, orçamento e revisão. O runtime, os heartbeats e os adapters ficam de fora — o JARVIS só confere o que foi declarado.</p>
        </div>
        <ul className="agency-laws">
          {laws.map((law) => <li key={law.key}><strong>{law.title}</strong><span>{law.text}</span></li>)}
        </ul>
      </section>

      <nav className="agency-tabs" aria-label="Modos do governo de agentes">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="agency-layout">
        <section className="panel agency-form">
          <header className="agency-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            {tab !== 'baseline' && (
              <label className="agency-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          {tab !== 'baseline' && <p className="agency-level-note">{levels.find((item) => item.id === level)?.description}</p>}

          {tab === 'roster' && (
            <form className="form-stack" onSubmit={submitRoster}>
              <label className="field">
                <span>Equipe *</span>
                <textarea className="agency-mono" value={roster} onChange={(event) => setRoster(event.target.value)} maxLength={50000} rows={9} required placeholder={'nome | papel | responde a | orçamento | permissões | estado\nAna | Tech lead | board | 900 | deploy, shell | ativo\nBruno | Backend | Ana | 600 | shell | ativo'} />
              </label>
              <p className="agency-note">Use <code>board</code> para a raiz humana. Estados aceitos: ativo, pausado, pendente, encerrado, rejeitado, sem_orcamento. Linhas com <code>#</code> são comentários.</p>
              <ol className="agency-checklist">
                <li>Todo agente chega a uma pessoa? Um ciclo de reporte nunca chega.</li>
                <li>Quem tem shell, segredo, deploy ou cobrança? Curinga é bloqueio.</li>
                <li>Agente encerrado ainda supervisiona alguém ativo?</li>
              </ol>
              <button type="submit" className="button button-primary" disabled={busy || !roster.trim()}>{busy ? <LoaderCircle size={15} className="agency-spin" /> : <Users size={15} />}Revisar equipe</button>
            </form>
          )}

          {tab === 'board' && (
            <form className="form-stack" onSubmit={submitBoard}>
              <label className="field">
                <span>Quadro *</span>
                <textarea className="agency-mono" value={tasks} onChange={(event) => setTasks(event.target.value)} maxLength={50000} rows={9} required placeholder={'id | título | dono | estado | objetivo | bloqueadores | evidência | atualizado\nENG-1 | Login | Ana | in_progress | lançar beta | — | — | 2026-10-19\nENG-2 | Testes | Bruno | blocked | lançar beta | ENG-1 | — | 2026-10-18'} />
              </label>
              <div className="agency-inline-fields">
                <label className="field agency-small"><span>Limite de WIP</span><input type="number" min={1} max={50} value={wipLimit} onChange={(event) => setWipLimit(Number(event.target.value))} /></label>
                <label className="field agency-small"><span>Dias parados</span><input type="number" min={1} max={90} value={staleDays} onChange={(event) => setStaleDays(Number(event.target.value))} /></label>
                <label className="field"><span>Data de referência</span><input value={referenceDate} onChange={(event) => setReferenceDate(event.target.value)} maxLength={10} placeholder="2026-10-23 (vazio = hoje UTC)" /></label>
              </div>
              <p className="agency-note">Estados aceitos: triage, backlog, todo, in_progress, in_review, blocked, waiting, done, cancelled, queued, retry. Conclusão sem evidência é bloqueio.</p>
              <button type="submit" className="button button-primary" disabled={busy || !tasks.trim()}>{busy ? <LoaderCircle size={15} className="agency-spin" /> : <LayoutList size={15} />}Revisar quadro</button>
            </form>
          )}

          {tab === 'budget' && (
            <form className="form-stack" onSubmit={submitBudget}>
              <label className="field">
                <span>Orçamentos *</span>
                <textarea className="agency-mono" value={entries} onChange={(event) => setEntries(event.target.value)} maxLength={50000} rows={8} required placeholder={'agente | limite | gasto | alerta% | parada automática\nAna | 900 | 740 | 80 | sim\nBruno | 600 | 610 | 80 | sim'} />
              </label>
              <div className="agency-inline-fields">
                <label className="field"><span>Teto da empresa</span><input value={companyBudget} onChange={(event) => setCompanyBudget(event.target.value)} maxLength={40} placeholder="1800.00" /></label>
                <label className="field agency-small"><span>Moeda</span><input value={currency} onChange={(event) => setCurrency(event.target.value)} maxLength={8} placeholder="US$" /></label>
              </div>
              <div className="agency-inline-fields">
                <label className="field agency-small"><span>Dia do período</span><input type="number" min={0} max={31} value={periodDay} onChange={(event) => setPeriodDay(Number(event.target.value))} /></label>
                <label className="field agency-small"><span>Dias no mês</span><input type="number" min={28} max={31} value={daysInMonth} onChange={(event) => setDaysInMonth(Number(event.target.value))} /></label>
                <span className="agency-note agency-inline-note">Dia 0 desliga a projeção linear. Não há conversão de moeda.</span>
              </div>
              <p className="agency-note">A parada automática é o que transforma limite em controle: sem ela, o próximo heartbeat passa do teto.</p>
              <button type="submit" className="button button-primary" disabled={busy || !entries.trim()}>{busy ? <LoaderCircle size={15} className="agency-spin" /> : <Wallet size={15} />}Revisar orçamento</button>
            </form>
          )}

          {tab === 'watchdog' && (
            <form className="form-stack" onSubmit={submitWatchdog}>
              <label className="field"><span>Tarefa observada *</span><input value={watched} onChange={(event) => setWatched(event.target.value)} maxLength={80} required placeholder="ENG-1" /></label>
              <label className="field">
                <span>Subárvore *</span>
                <textarea className="agency-mono" value={subtree} onChange={(event) => setSubtree(event.target.value)} maxLength={50000} rows={9} required placeholder={'id | estado | dono | evidência | bloqueador | interação | atualizado\nENG-1 | done | Ana | PR #3 e teste verde | — | — | 2026-10-20\nENG-2 | in_review | Bruno | — | — | — | 2026-10-19'} />
              </label>
              <label className="field"><span>Instruções do watchdog</span><textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} maxLength={4000} rows={2} placeholder="Só podem estreitar o mandato: nada de aprovar, gastar, contratar ou sair do recorte." /></label>
              <div className="agency-inline-fields">
                <label className="field"><span>IDs fora do recorte</span><input value={exclude} onChange={(event) => setExclude(event.target.value)} maxLength={1000} placeholder="tarefas do próprio watchdog" /></label>
                <label className="field"><span>Impressão digital anterior</span><input value={lastFingerprint} onChange={(event) => setLastFingerprint(event.target.value)} maxLength={64} placeholder="64 hexadecimais" /></label>
              </div>
              <div className="agency-mandate">
                <strong>MANDATO FIXO</strong>
                <ul>
                  <li>Cada folha parada é alegação, não fato.</li>
                  <li>Parada legítima: registre o que foi checado.</li>
                  <li>Parada indevida: restaure um caminho vivo.</li>
                  <li>Bloqueio real: exija dono e próximo passo.</li>
                  <li>Uma revisão por impressão digital.</li>
                </ul>
              </div>
              <button type="submit" className="button button-primary" disabled={busy || !watched.trim() || !subtree.trim()}>{busy ? <LoaderCircle size={15} className="agency-spin" /> : <Eye size={15} />}Verificar parada</button>
            </form>
          )}

          {tab === 'permissions' && (
            <form className="form-stack" onSubmit={submitPermissions}>
              <label className="field">
                <span>Permissões *</span>
                <textarea className="agency-mono" value={permissions} onChange={(event) => setPermissions(event.target.value)} maxLength={50000} rows={9} required placeholder={'agente | concedidas | negadas | flags\nAna | tasks:assign, tools:use, agents:configure | users:invite | cota:3, criados:2\nBruno | * | | baixa_confianca'} />
              </label>
              <div className="agency-flags">
                <label className="agency-check"><input type="checkbox" checked={lowTrust} onChange={(event) => setLowTrust(event.target.checked)} /><span>Tratar todos como baixa confiança</span></label>
                <label className="agency-check"><input type="checkbox" checked={managed} onChange={(event) => setManaged(event.target.checked)} /><span>Tratar todos como gerenciados</span></label>
              </div>
              <p className="agency-note">Flags por agente: <code>baixa_confianca</code>, <code>gerenciado</code>, <code>cota:N</code>, <code>criados:N</code> e <code>adapter/comando/cwd/env/sandbox</code>. Curinga e chave negada concedida são bloqueios.</p>
              <button type="submit" className="button button-primary" disabled={busy || !permissions.trim()}>{busy ? <LoaderCircle size={15} className="agency-spin" /> : <ShieldCheck size={15} />}Conferir permissões</button>
            </form>
          )}

          {tab === 'baseline' && (
            <div className="agency-form-static">
              <p className="agency-note">Esta é a linha de base da adaptação: 18 chaves concedidas a um agente comum e 6 negadas por padrão. A revisão compara a sua declaração com estas listas e nunca aplica mudanças.</p>
              <div className="agency-baseline">
                <section>
                  <h3><CheckCircle2 size={13} />Concedidas por padrão</h3>
                  <ul>{baseline.granted.map(([key, reason]) => <li key={key}><code>{key}</code><span>{reason}</span></li>)}</ul>
                </section>
                <section>
                  <h3><AlertTriangle size={13} />Negadas por padrão</h3>
                  <ul>{baseline.denied.map(([key, reason]) => <li key={key}><code>{key}</code><span>{reason}</span></li>)}</ul>
                </section>
              </div>
              <div className="agency-exceptions">
                <strong>EXCEÇÕES E SEM BACKFILL</strong>
                <ul>{baseline.exceptions.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
              <button type="button" className="button button-primary" onClick={() => { setTab('permissions'); setError(''); }}><ArrowRight size={15} />Conferir uma equipe</button>
            </div>
          )}

          {error && <p className="agency-error" role="alert"><AlertTriangle size={15} />{error}</p>}
        </section>

        <section className="panel agency-result" aria-live="polite">
          <header className="agency-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{result ? analysisLabels[analysis] ?? 'Parecer' : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="agency-result-actions">
                <span className="agency-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="agency-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
              </div>
            )}
          </header>

          {!result && (
            <div className="agency-placeholder">
              <span><ShieldCheck size={18} /></span>
              <strong>Somente leitura</strong>
              <p>O parecer aparece aqui com evidência por achado, veredito e limites declarados. Nada é executado, agendado ou conectado a um agente real.</p>
              <ul>
                <li>Equipe: raiz humana, ciclos e permissões sensíveis.</li>
                <li>Quadro: dono, evidência, bloqueio e ciclo de dependências.</li>
                <li>Orçamento: estouro, alerta e projeção linear.</li>
                <li>Parada: impressão digital e revisão idempotente.</li>
                <li>Permissões: linha de base, exceções e override de runtime.</li>
              </ul>
            </div>
          )}

          {result && (
            <>
              {analysis === 'roster' && <RosterResult result={result} />}
              {analysis === 'board' && <BoardResult result={result} />}
              {analysis === 'budget' && <BudgetResult result={result} />}
              {analysis === 'watchdog' && <WatchdogResult result={result} onUseFingerprint={(fingerprint) => { setLastFingerprint(fingerprint); pushToast('Impressão digital carregada', 'Rode a verificação de novo para ver a revisão suprimida.'); }} />}
              {analysis === 'permissions' && <PermissionsResult result={result} />}
              <Limitations items={result.limitations} />
              <details className="agency-json">
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
