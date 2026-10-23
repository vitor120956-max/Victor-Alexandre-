import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clipboard,
  Feather,
  FolderTree,
  Layers,
  LoaderCircle,
  RefreshCw,
  Ruler,
  ScanSearch,
  ShieldCheck,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { listReverseArtifacts } from '../lib/api';
import type { SkillExecution } from '../lib/api';
import '../lean.css';

type LeanTab = 'ladder' | 'review' | 'debt' | 'audit';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';
type Fit = 'none' | 'partial' | 'full';

const tabs: Array<{ id: LeanTab; label: string; hint: string; icon: typeof Ruler }> = [
  { id: 'ladder', label: 'Escada', hint: 'Menor caminho declarado', icon: Ruler },
  { id: 'review', label: 'Revisão', hint: 'Diff ou trecho', icon: ScanSearch },
  { id: 'debt', label: 'Dívida', hint: 'Atalhos e gatilhos', icon: Feather },
  { id: 'audit', label: 'Auditoria', hint: 'Árvore de código', icon: FolderTree },
];

const levels: Array<{ id: Level; label: string; description: string }> = [
  { id: 'lite', label: 'Lite', description: 'Só o essencial e os bloqueios.' },
  { id: 'full', label: 'Full', description: 'Padrão: corrige, enxuga e cobra teste.' },
  { id: 'ultra', label: 'Ultra', description: 'Questiona o pedido antes de construir.' },
];

const neverCut = [
  'validação nas fronteiras de confiança',
  'tratamento de erro que evita perda de dados',
  'segurança',
  'acessibilidade',
  'calibração exigida por hardware real',
  'qualquer coisa que o usuário pediu',
];

const fits: Array<{ value: Fit; label: string }> = [
  { value: 'none', label: 'Não existe ou não sei' },
  { value: 'partial', label: 'Cobre em parte' },
  { value: 'full', label: 'Cobre por completo' },
];

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));

function foldersFromPaths(artifacts: Row[]): string[] {
  const folders = new Set<string>();
  for (const artifact of artifacts) {
    const parts = text(artifact.path).split('/').slice(0, -1);
    for (let index = 1; index <= parts.length; index += 1) folders.add(parts.slice(0, index).join('/'));
  }
  return [...folders].sort();
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function Limitations({ items }: { items: unknown }) {
  const rows = Array.isArray(items) ? items.map(text).filter(Boolean) : [];
  if (!rows.length) return null;
  return (
    <div className="lean-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="lean-empty">Nenhum candidato pelas regras deste nível. Leia o diff completo antes de enviar.</p>;
  return (
    <div className="lean-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`lean-finding is-${group}`} key={`${text(finding.id)}-${text(finding.location)}`}>
            <header>
              <span className="lean-group">{group === 'must' ? 'obrigatório' : group === 'should' ? 'corrigir' : 'opcional'}</span>
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

function LadderResult({ result }: { result: Row }) {
  const decision = asRow(result.decision);
  const rungs = asRows(result.rungs);
  const obligation = asRow(result.testObligation);
  const warnings = Array.isArray(result.warnings) ? result.warnings.map(text) : [];
  const questions = Array.isArray(result.questions) ? result.questions.map(text) : [];
  const outOfScope = Array.isArray(result.outOfScope) ? result.outOfScope.map(text) : [];
  const reach = Array.isArray(result.reach) ? result.reach.map(text) : [];
  const risky = Array.isArray(obligation.riskySignals) ? obligation.riskySignals.map(text) : [];
  return (
    <div className="lean-view">
      <div className="lean-decision">
        <span>DEGRAU {count(decision.rung)}</span>
        <strong>{text(decision.label) || 'Mínimo necessário'}</strong>
        <p>{text(decision.evidence)}</p>
      </div>
      <table className="lean-rungs">
        <thead><tr><th>#</th><th>Degrau</th><th>Situação</th><th>Evidência</th></tr></thead>
        <tbody>
          {rungs.map((rung, index) => (
            <tr key={text(rung.key)} className={text(rung.status) === 'holds' ? 'is-holds' : undefined}>
              <td>{index + 1}</td>
              <td>{text(rung.label)}</td>
              <td><span className={`lean-status is-${text(rung.status)}`}>{text(rung.status)}</span></td>
              <td>{text(rung.evidence)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {warnings.length > 0 && (
        <div className="lean-warnings">
          {warnings.map((warning) => <p key={warning}><AlertTriangle size={14} />{warning}</p>)}
        </div>
      )}
      <div className="lean-two-columns">
        <section>
          <h3>Nunca cortar</h3>
          <ul className="lean-chips">{neverCut.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
        <section>
          <h3>Obrigação de teste</h3>
          <p className="lean-note">{obligation.required ? 'Teste pequeno obrigatório para ramo, laço, parse, dinheiro ou segurança.' : 'Mudança declarada trivial: não invente teste para inflar a entrega.'}</p>
          {risky.length > 0 && <ul className="lean-chips">{risky.slice(0, 8).map((item) => <li key={item}>{item}</li>)}</ul>}
        </section>
      </div>
      {outOfScope.length > 0 && (
        <section>
          <h3>Fora de escopo</h3>
          <ul className="lean-list">{outOfScope.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      )}
      {reach.length > 0 && (
        <section>
          <h3>Alcance da mudança</h3>
          <ul className="lean-list">{reach.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      )}
      {questions.length > 0 && (
        <section>
          <h3>Perguntas antes de construir</h3>
          <ul className="lean-list">{questions.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      )}
      <p className="lean-note">Se a entrega tiver um limite conhecido, registre <code>shortcut: &lt;limite&gt;, &lt;quando revisar&gt;</code> e colete com a aba Dívida.</p>
    </div>
  );
}

function ReviewResult({ result }: { result: Row }) {
  const counts = asRow(result.counts);
  const coverage = asRow(result.coverage);
  return (
    <div className="lean-view">
      <div className="lean-metrics">
        <Metric label="OBRIGATÓRIOS" value={count(counts.must)} />
        <Metric label="CORRIGIR" value={count(counts.should)} />
        <Metric label="OPCIONAIS" value={count(counts.nice)} />
        <Metric label="LEAN" value={`-${count(result.leanLines)} linhas`} />
      </div>
      <p className="lean-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <p className="lean-note">Entrada: {text(result.input) === 'snippet' ? 'trecho colado' : 'diff unificado'} · {count(result.addedLines)} linhas adicionadas · {count(result.removedLines)} removidas · {Array.isArray(result.testFilesTouched) && result.testFilesTouched.length ? 'teste tocado' : 'nenhum teste no diff'}.</p>
      <FindingList findings={asRows(result.findings)} />
      {Object.keys(coverage).length > 0 && <p className="lean-note">Cobertura: {count(coverage.files)} arquivo(s) varridos, limite atingido: {coverage.limitReached ? 'sim' : 'não'}.</p>}
    </div>
  );
}

function DebtResult({ result }: { result: Row }) {
  const totals = asRow(result.totals);
  const coverage = asRow(result.coverage);
  const rows = asRows(result.rows);
  return (
    <div className="lean-view">
      <div className="lean-metrics">
        <Metric label="MARCADORES" value={count(totals.markers)} />
        <Metric label="SEM GATILHO" value={count(totals.noTrigger)} />
        <Metric label="ARQUIVOS" value={count(totals.files)} />
        <Metric label="FONTES LIDAS" value={count(coverage.filesScanned)} />
      </div>
      <p className="lean-note">Marcador <code>{text(result.marker)}</code> · origem: {text(result.source) === 'tree' ? 'pasta de código' : 'trecho colado'}.</p>
      {rows.length === 0
        ? <p className="lean-empty">Nenhum marcador encontrado. A convenção só entra quando aparece em um comentário, por exemplo <code>// shortcut: sem cache, revisar com 100 usuários</code>.</p>
        : (
          <div className="lean-scroll">
            <table className="lean-table">
              <thead><tr><th>Arquivo</th><th>Linha</th><th>Teto</th><th>Quando revisar</th><th>Sinal</th></tr></thead>
              <tbody>
                {rows.slice(0, 200).map((row, index) => (
                  <tr key={`${text(row.file)}-${text(row.line)}-${index}`}>
                    <td><code>{text(row.file)}</code></td>
                    <td>{count(row.line)}</td>
                    <td>{text(row.ceiling)}</td>
                    <td>{text(row.upgrade) || '—'}</td>
                    <td>{row.noTrigger ? <span className="lean-badge is-warning">no-trigger</span> : <span className="lean-badge">ok</span>}{row.legacy ? <span className="lean-badge is-legacy">ponytail:</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length > 200 && <p className="lean-note">Exibindo 200 de {rows.length} marcadores.</p>}
          </div>
        )}
    </div>
  );
}

function AuditResult({ result }: { result: Row }) {
  const inventory = asRow(result.inventory);
  const counts = asRow(result.counts);
  const coverage = asRow(result.coverage);
  const debt = asRow(result.debt);
  const skipped = asRows(coverage.skipped);
  return (
    <div className="lean-view">
      <div className="lean-metrics">
        <Metric label="ARQUIVOS" value={count(inventory.files)} />
        <Metric label="LINHAS" value={count(inventory.lines)} />
        <Metric label="OBRIGATÓRIOS" value={count(counts.must)} />
        <Metric label="LEAN" value={`-${count(result.leanLines)} linhas`} />
      </div>
      <p className="lean-verdict"><ShieldCheck size={15} />{text(result.verdict)}</p>
      <p className="lean-note">{count(inventory.codeFiles)} arquivo(s) de código, {count(inventory.testFiles)} de teste e {count(debt.markers)} marcador(es) de atalho ({count(debt.noTrigger)} sem gatilho).</p>
      <FindingList findings={asRows(result.findings)} />
      {count(result.omitted) > 0 && <p className="lean-note">{count(result.omitted)} achado(s) menor(es) foram omitidos pelo limite.</p>}
      {skipped.length > 0 && <p className="lean-note">Não lidos: {skipped.slice(0, 6).map((item) => `${text(item.path)} (${text(item.reason)})`).join(', ')}{skipped.length > 6 ? '…' : ''}.</p>}
      <p className="lean-note">Limite: {count(coverage.maxFiles)} arquivos; limite atingido: {coverage.limitReached ? 'sim' : 'não'}.</p>
    </div>
  );
}

export function LeanPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<LeanTab>('ladder');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [resultTab, setResultTab] = useState<LeanTab>('ladder');
  const [folders, setFolders] = useState<string[]>([]);

  const [task, setTask] = useState('');
  const [proposal, setProposal] = useState('');
  const [reuseFit, setReuseFit] = useState<Fit>('none');
  const [reuseEvidence, setReuseEvidence] = useState('');
  const [stdlibFit, setStdlibFit] = useState<Fit>('none');
  const [stdlibEvidence, setStdlibEvidence] = useState('');
  const [dependencyFit, setDependencyFit] = useState<Fit>('none');
  const [dependencyEvidence, setDependencyEvidence] = useState('');
  const [oneLiner, setOneLiner] = useState(false);
  const [estimatedLines, setEstimatedLines] = useState(20);
  const [unrequested, setUnrequested] = useState('');
  const [reach, setReach] = useState('');

  const [diff, setDiff] = useState('');
  const [notes, setNotes] = useState('');

  const [debtSource, setDebtSource] = useState<'code' | 'tree'>('code');
  const [debtPath, setDebtPath] = useState('');
  const [debtCode, setDebtCode] = useState('');
  const [marker, setMarker] = useState('shortcut');
  const [includeLegacy, setIncludeLegacy] = useState(true);

  const [auditPath, setAuditPath] = useState('');
  const [maxFiles, setMaxFiles] = useState(400);

  const loadFolders = useCallback(async () => {
    try {
      const response = await listReverseArtifacts();
      setFolders(foldersFromPaths(response.artifacts as unknown as Row[]));
    } catch {
      setFolders([]);
    }
  }, []);

  useEffect(() => { void loadFolders(); }, [loadFolders]);

  const result = execution?.result ?? null;
  const resultMarkdown = useMemo(() => (result && typeof result.markdown === 'string' ? result.markdown : ''), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>, targetTab: LeanTab) => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi analisado.');
      return;
    }
    setBusy(true);
    setError('');
    setExecution(null);
    setResultTab(targetTab);
    try {
      const response = await executeSkill(skillId, parameters);
      if (!response.ok) {
        setError(response.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(response);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Falha ao executar a skill lean.');
    } finally {
      setBusy(false);
    }
  };

  const submitLadder = (event: React.FormEvent) => {
    event.preventDefault();
    if (!task.trim()) return;
    void run('lean.ladder', {
      mode: level, task, proposal, reuseFit, reuseEvidence, stdlibFit, stdlibEvidence,
      dependencyFit, dependencyEvidence, oneLiner, estimatedLines: Number(estimatedLines),
      unrequested, reach,
    }, 'ladder');
  };

  const submitReview = (event: React.FormEvent) => {
    event.preventDefault();
    if (!diff.trim()) return;
    void run('lean.review', { diff, mode: level, notes }, 'review');
  };

  const submitDebt = (event: React.FormEvent) => {
    event.preventDefault();
    if (debtSource === 'code' ? !debtCode.trim() : !debtPath.trim()) {
      setError('Informe exatamente uma fonte: o trecho colado ou a pasta de código.');
      return;
    }
    void run('lean.debt', {
      code: debtSource === 'code' ? debtCode : '', path: debtSource === 'tree' ? debtPath.trim() : '',
      marker: marker.trim() || 'shortcut', includeLegacy,
    }, 'debt');
  };

  const submitAudit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!auditPath.trim()) return;
    void run('lean.audit', { path: auditPath.trim(), mode: level, maxFiles: Number(maxFiles) }, 'audit');
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

  return (
    <div className="lean-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">ENGENHARIA ENXUTA · ANÁLISE ESTÁTICA</span>
          <h1>Menos código, <span>mesma entrega</span></h1>
          <p>Aplica a escada do ponytail ao que você declara, revisa diffs e audita dívida de atalhos. Nada é executado, instalado ou enviado à IA.</p>
        </div>
        <Link to="/reversa" className="button button-ghost"><FolderTree size={15} /> Enviar código</Link>
      </header>

      <section className="panel lean-intro">
        <span className="lean-intro-icon"><Layers size={22} /></span>
        <div>
          <span className="eyebrow">REGRA CENTRAL</span>
          <h2>Preguiçoso com a solução, nunca com a leitura</h2>
          <p>Primeiro entender o problema e o código; depois cortar. A escada para no primeiro degrau que cobre o pedido por completo — e só então escreva o mínimo que funciona, com teste quando a lógica é arriscada.</p>
        </div>
        <ol className="lean-ladder-legend">
          <li>precisa existir?</li>
          <li>já existe no projeto?</li>
          <li>stdlib ou nativo?</li>
          <li>dependência instalada?</li>
          <li>cabe em uma linha?</li>
          <li>o mínimo que funciona</li>
        </ol>
      </section>

      <nav className="lean-tabs" aria-label="Modos da engenharia enxuta">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="lean-layout">
        <section className="panel lean-form">
          <header className="lean-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            <label className="lean-level">
              <span>NÍVEL</span>
              <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
          </header>
          <p className="lean-level-note">{levels.find((item) => item.id === level)?.description}</p>

          {tab === 'ladder' && (
            <form className="form-stack" onSubmit={submitLadder}>
              <label className="field"><span>Tarefa *</span><input value={task} onChange={(event) => setTask(event.target.value)} maxLength={4000} required placeholder="Ex.: adicionar seletor de data na agenda" /></label>
              <label className="field"><span>Proposta atual</span><textarea value={proposal} onChange={(event) => setProposal(event.target.value)} maxLength={8000} rows={3} placeholder="O que você pensa em construir. A escada corta o que não é necessário." /></label>
              <div className="lean-rung-input">
                <label className="field"><span>Já existe no projeto?</span>
                  <select value={reuseFit} onChange={(event) => setReuseFit(event.target.value as Fit)}>{fits.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
                </label>
                <label className="field"><span>Evidência (caminho)</span><input value={reuseEvidence} onChange={(event) => setReuseEvidence(event.target.value)} maxLength={2000} placeholder="src/components/Input.tsx" /></label>
              </div>
              <div className="lean-rung-input">
                <label className="field"><span>Biblioteca padrão ou nativo?</span>
                  <select value={stdlibFit} onChange={(event) => setStdlibFit(event.target.value as Fit)}>{fits.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
                </label>
                <label className="field"><span>Evidência (API)</span><input value={stdlibEvidence} onChange={(event) => setStdlibEvidence(event.target.value)} maxLength={2000} placeholder="input type=date" /></label>
              </div>
              <div className="lean-rung-input">
                <label className="field"><span>Dependência já instalada?</span>
                  <select value={dependencyFit} onChange={(event) => setDependencyFit(event.target.value as Fit)}>{fits.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
                </label>
                <label className="field"><span>Evidência (pacote)</span><input value={dependencyEvidence} onChange={(event) => setDependencyEvidence(event.target.value)} maxLength={2000} placeholder="date-fns no package.json" /></label>
              </div>
              <div className="lean-inline-fields">
                <label className="lean-check"><input type="checkbox" checked={oneLiner} onChange={(event) => setOneLiner(event.target.checked)} /><span>Cabe em uma linha legível</span></label>
                <label className="field lean-lines"><span>Linhas estimadas</span><input type="number" min={1} max={5000} value={estimatedLines} onChange={(event) => setEstimatedLines(Number(event.target.value))} /></label>
              </div>
              <label className="field"><span>O que ninguém pediu</span><textarea value={unrequested} onChange={(event) => setUnrequested(event.target.value)} maxLength={4000} rows={2} placeholder="Um item por linha: tema escuro, atalhos, flexibilidade futura." /></label>
              <label className="field"><span>Alcance da mudança</span><textarea value={reach} onChange={(event) => setReach(event.target.value)} maxLength={4000} rows={2} placeholder="Um por linha: callers, testes, fixtures, config, exports." /></label>
              <button type="submit" className="button button-primary" disabled={busy || !task.trim()}>{busy ? <LoaderCircle size={15} className="lean-spin" /> : <ArrowRight size={15} />}Avaliar escada</button>
            </form>
          )}

          {tab === 'review' && (
            <form className="form-stack" onSubmit={submitReview}>
              <label className="field"><span>Diff ou trecho *</span>
                <textarea className="lean-mono" value={diff} onChange={(event) => setDiff(event.target.value)} maxLength={200000} rows={14} required placeholder={'Cole um diff unificado:\n--- a/src/app.js\n+++ b/src/app.js\n@@ -1,3 +1,3 @@\n-const ok = validate(x);\n+const ok = eval(x);'} />
              </label>
              <label className="field"><span>Contexto</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={4000} rows={2} placeholder="O que esta mudança deveria fazer." /></label>
              <p className="lean-note">Ordene por correto, seguro, aguenta carga, testado, rápido, enxuto. Achados são candidatos: confirme no código real.</p>
              <button type="submit" className="button button-primary" disabled={busy || !diff.trim()}>{busy ? <LoaderCircle size={15} className="lean-spin" /> : <ScanSearch size={15} />}Revisar mudança</button>
            </form>
          )}

          {tab === 'debt' && (
            <form className="form-stack" onSubmit={submitDebt}>
              <div className="lean-source-tabs" role="group" aria-label="Fonte do levantamento">
                <button type="button" className={debtSource === 'code' ? 'is-active' : undefined} onClick={() => setDebtSource('code')}>Código colado</button>
                <button type="button" className={debtSource === 'tree' ? 'is-active' : undefined} onClick={() => setDebtSource('tree')}>Pasta de código</button>
              </div>
              {debtSource === 'code'
                ? <label className="field"><span>Código *</span><textarea className="lean-mono" value={debtCode} onChange={(event) => setDebtCode(event.target.value)} maxLength={500000} rows={12} placeholder={'// shortcut: cache em memória, revisar com 100 usuários\nfunction load() { ... }'} /></label>
                : <label className="field"><span>Pasta *</span><input list="lean-folders" value={debtPath} onChange={(event) => setDebtPath(event.target.value)} maxLength={200} placeholder="app" /></label>}
              <div className="lean-inline-fields">
                <label className="field"><span>Marcador</span><input value={marker} onChange={(event) => setMarker(event.target.value)} maxLength={21} placeholder="shortcut" /></label>
                <label className="lean-check lean-check-inline"><input type="checkbox" checked={includeLegacy} onChange={(event) => setIncludeLegacy(event.target.checked)} /><span>Aceitar <code>ponytail:</code> antigo</span></label>
              </div>
              <p className="lean-note">Um atalho sem limite e sem data vira decisão permanente. O levantamento só lê comentários com o marcador.</p>
              <button type="submit" className="button button-primary" disabled={busy}>{busy ? <LoaderCircle size={15} className="lean-spin" /> : <Feather size={15} />}Levantar dívida</button>
            </form>
          )}

          {tab === 'audit' && (
            <form className="form-stack" onSubmit={submitAudit}>
              <label className="field"><span>Pasta de código *</span><input list="lean-folders" value={auditPath} onChange={(event) => setAuditPath(event.target.value)} maxLength={200} required placeholder="app" /></label>
              <div className="lean-inline-fields">
                <label className="field"><span>Máximo de arquivos</span><input type="number" min={10} max={400} value={maxFiles} onChange={(event) => setMaxFiles(Number(event.target.value))} /></label>
                <button type="button" className="button button-ghost lean-refresh" onClick={() => void loadFolders()}><RefreshCw size={14} />Atualizar pastas</button>
              </div>
              <p className="lean-note">A varredura ignora <code>node_modules</code>, build, dist, cobertura e symlinks; lê no máximo 400 arquivos e 3 MB. Envie a árvore de código em <Link to="/reversa">Reversa</Link>.</p>
              <div className="lean-budget">
                <strong>{folders.length ? `${folders.length} pasta(s) com código enviado` : 'Nenhuma pasta de código encontrada'}</strong>
                <span>Ordem: correção → teste → duplicação → superfície morta.</span>
              </div>
              <button type="submit" className="button button-primary" disabled={busy || !auditPath.trim()}>{busy ? <LoaderCircle size={15} className="lean-spin" /> : <FolderTree size={15} />}Auditar código</button>
            </form>
          )}

          {error && <p className="lean-error" role="alert"><AlertTriangle size={15} />{error}</p>}
          <datalist id="lean-folders">{folders.map((folder) => <option key={folder} value={folder} />)}</datalist>
        </section>

        <section className="panel lean-result" aria-live="polite">
          <header className="lean-result-head">
            <div>
              <span className="eyebrow">PARECER</span>
              <h2>{execution?.ok ? tabs.find((item) => item.id === resultTab)?.label : 'Aguardando análise'}</h2>
            </div>
            {result && (
              <div className="lean-result-actions">
                <span className="lean-readonly"><CheckCircle2 size={13} /> executado: não</span>
                {resultMarkdown && <button type="button" className="lean-copy" onClick={() => void copyMarkdown()}><Clipboard size={13} />Copiar Markdown</button>}
              </div>
            )}
          </header>

          {!result && (
            <div className="lean-placeholder">
              <span><CheckCircle2 size={18} /></span>
              <strong>Somente leitura</strong>
              <p>O parecer aparece aqui com evidência por degrau, quatro partes por achado e os limites declarados. Nada é executado.</p>
              <ul>
                <li>Escada: qual degrau cobre o pedido e o que cortar.</li>
                <li>Revisão: risco novo, proteção removida e teste ausente.</li>
                <li>Dívida: <code>shortcut:</code> sem gatilho vira <code>no-trigger</code>.</li>
                <li>Auditoria: achados ordenados, até 20, com cobertura.</li>
              </ul>
            </div>
          )}

          {result && (
            <>
              {resultTab === 'ladder' && <LadderResult result={result} />}
              {resultTab === 'review' && <ReviewResult result={result} />}
              {resultTab === 'debt' && <DebtResult result={result} />}
              {resultTab === 'audit' && <AuditResult result={result} />}
              <Limitations items={result.limitations} />
              <details className="lean-json">
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
