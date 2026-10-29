import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  Check,
  CheckCircle2,
  Circle,
  Download,
  ExternalLink,
  FilePlus2,
  FileText,
  FolderLock,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import '../planning.css';

type PlanStatus = 'pending' | 'in_progress' | 'complete';
type NoteType = '' | 'finding' | 'progress' | 'error' | 'test';

interface PlanCriterion { text: string; checked: boolean }
interface PlanPhase { number: number; title: string; status: PlanStatus; criteria: PlanCriterion[] }
interface PlanGate {
  complete: boolean;
  phaseCount?: number;
  completePhases?: number;
  pending?: { phase: number; title: string; status: PlanStatus; uncheckedCriteria: string[] }[];
  rule?: string;
  commandsExecuted?: boolean;
}
interface PlanSummary {
  planId: string;
  title: string;
  goal?: string;
  nextStep?: string;
  currentPhase?: number;
  phases?: PlanPhase[];
  gate: PlanGate;
  sha256?: string;
  downloadUrls?: Record<string, string>;
  updatedAt?: string;
  invalid?: boolean;
  error?: string;
}
interface PlanDetails extends PlanSummary {
  goal: string;
  nextStep: string;
  currentPhase: number;
  phases: PlanPhase[];
  sha256: string;
  contents: Record<string, string>;
  recovery: Record<string, string>;
  historyRead: boolean;
}

const initialPhases = 'Preparar | escopo e critérios registrados\nValidar | testes e evidências anexados\nEntregar | gate completo e resultado revisado';
const fileLabels: Record<string, string> = {
  'task_plan.md': 'Plano e fases',
  'findings.md': 'Descobertas e decisões',
  'progress.md': 'Progresso e evidências',
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function PlanningPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [listError, setListError] = useState('');
  const [loadingPlans, setLoadingPlans] = useState(false);

  const [title, setTitle] = useState('Entrega do projeto');
  const [planId, setPlanId] = useState('');
  const [goal, setGoal] = useState('Planejar e validar uma entrega com recuperação persistente.');
  const [phasesInput, setPhasesInput] = useState(initialPhases);
  const [requirements, setRequirements] = useState('Sem comandos executados a partir do Markdown\nRecuperação apenas pelo ID do plano');
  const [createPreview, setCreatePreview] = useState<Record<string, unknown> | null>(null);
  const [createConfirmed, setCreateConfirmed] = useState(false);
  const [createBusy, setCreateBusy] = useState<'dry' | 'write' | null>(null);
  const [createError, setCreateError] = useState('');

  const [selected, setSelected] = useState<PlanDetails | null>(null);
  const [resumeBusy, setResumeBusy] = useState('');
  const [resumeError, setResumeError] = useState('');
  const [activeFile, setActiveFile] = useState('task_plan.md');

  const [phase, setPhase] = useState(0);
  const [status, setStatus] = useState<'' | PlanStatus>('');
  const [nextStep, setNextStep] = useState('');
  const [evidence, setEvidence] = useState('');
  const [noteType, setNoteType] = useState<NoteType>('');
  const [note, setNote] = useState('');
  const [updatePreview, setUpdatePreview] = useState<Record<string, unknown> | null>(null);
  const [updateConfirmed, setUpdateConfirmed] = useState(false);
  const [updateBusy, setUpdateBusy] = useState<'dry' | 'write' | null>(null);
  const [updateError, setUpdateError] = useState('');

  const loadPlans = useCallback(async () => {
    if (!backendOnline) return;
    setLoadingPlans(true);
    setListError('');
    try {
      const response = await executeSkill('planning.list', {});
      if (response.ok && response.result) setPlans((response.result.plans as unknown as PlanSummary[]) ?? []);
      else setListError(response.error?.message ?? 'Não foi possível listar os planos.');
    } catch (error) {
      setListError(errorMessage(error, 'Falha ao listar planos.'));
    } finally {
      setLoadingPlans(false);
    }
  }, [backendOnline, executeSkill]);

  useEffect(() => { void loadPlans(); }, [loadPlans]);

  const resume = useCallback(async (id: string) => {
    if (!backendOnline || !id) return;
    setResumeBusy(id);
    setResumeError('');
    setUpdatePreview(null);
    setUpdateConfirmed(false);
    setUpdateError('');
    try {
      const response = await executeSkill('planning.resume', { planId: id });
      if (response.ok && response.result) {
        setSelected(response.result as unknown as PlanDetails);
        setActiveFile('task_plan.md');
        setPhase(0);
        setStatus('');
        setNextStep('');
        setEvidence('');
        setNoteType('');
        setNote('');
      } else {
        setResumeError(response.error?.message ?? 'O plano não pôde ser retomado.');
      }
    } catch (error) {
      setResumeError(errorMessage(error, 'Falha ao retomar o plano.'));
    } finally {
      setResumeBusy('');
    }
  }, [backendOnline, executeSkill]);

  const invalidateCreate = () => {
    setCreatePreview(null);
    setCreateConfirmed(false);
    setCreateError('');
  };

  const createParameters = () => ({ planId, title, goal, phases: phasesInput, requirements });

  const simulateCreate = async () => {
    if (!backendOnline || createBusy) return;
    setCreateBusy('dry');
    setCreateError('');
    setCreatePreview(null);
    setCreateConfirmed(false);
    try {
      const response = await executeSkill('planning.create', createParameters(), { dryRun: true });
      if (response.ok && response.result) setCreatePreview(response.result);
      else setCreateError(response.error?.message ?? 'A criação foi recusada.');
    } catch (error) {
      setCreateError(errorMessage(error, 'Falha ao simular o plano.'));
    } finally {
      setCreateBusy(null);
    }
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!createPreview || !createConfirmed || createBusy || !backendOnline) return;
    setCreateBusy('write');
    setCreateError('');
    try {
      const response = await executeSkill('planning.create', createParameters(), { confirmed: true });
      if (response.ok && response.result) {
        const id = String(response.result.planId);
        pushToast('Plano persistente criado', `${id} · 3 arquivos`);
        setCreatePreview(null);
        setCreateConfirmed(false);
        await loadPlans();
        await resume(id);
      } else {
        setCreateError(response.error?.message ?? 'A criação foi recusada.');
      }
    } catch (error) {
      setCreateError(errorMessage(error, 'Falha ao criar o plano.'));
    } finally {
      setCreateBusy(null);
    }
  };

  const invalidateUpdate = () => {
    setUpdatePreview(null);
    setUpdateConfirmed(false);
    setUpdateError('');
  };

  const updateParameters = () => ({
    planId: selected?.planId ?? '',
    expectedSha256: selected?.sha256 ?? '',
    phase,
    status,
    nextStep,
    evidence,
    noteType,
    note,
  });

  const simulateUpdate = async () => {
    if (!selected || updateBusy || !backendOnline) return;
    setUpdateBusy('dry');
    setUpdateError('');
    setUpdatePreview(null);
    setUpdateConfirmed(false);
    try {
      const response = await executeSkill('planning.update', updateParameters(), { dryRun: true });
      if (response.ok && response.result) setUpdatePreview(response.result);
      else setUpdateError(response.error?.message ?? 'A atualização foi recusada.');
    } catch (error) {
      setUpdateError(errorMessage(error, 'Falha ao simular a atualização.'));
    } finally {
      setUpdateBusy(null);
    }
  };

  const update = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected || !updatePreview || !updateConfirmed || updateBusy || !backendOnline) return;
    const id = selected.planId;
    setUpdateBusy('write');
    setUpdateError('');
    try {
      const response = await executeSkill('planning.update', updateParameters(), { confirmed: true });
      if (response.ok) {
        pushToast('Plano atualizado', `${id} · estado verificado por hash`);
        setUpdatePreview(null);
        setUpdateConfirmed(false);
        await loadPlans();
        await resume(id);
      } else {
        setUpdateError(response.error?.message ?? 'A atualização foi recusada.');
      }
    } catch (error) {
      setUpdateError(errorMessage(error, 'Falha ao atualizar o plano.'));
    } finally {
      setUpdateBusy(null);
    }
  };

  const checkGate = async () => {
    if (!selected || resumeBusy) return;
    setResumeBusy(selected.planId);
    try {
      const response = await executeSkill('planning.gate', { planId: selected.planId });
      if (response.ok && response.result) {
        const gate = response.result.gate as unknown as PlanGate;
        setSelected((current) => current ? { ...current, gate } : current);
        pushToast(gate.complete ? 'Gate completo' : 'Gate ainda incompleto', `${gate.completePhases ?? 0}/${gate.phaseCount ?? 0} fases concluídas`);
      } else setResumeError(response.error?.message ?? 'O gate foi recusado.');
    } catch (error) {
      setResumeError(errorMessage(error, 'Falha ao verificar o gate.'));
    } finally {
      setResumeBusy('');
    }
  };

  return (
    <div className="planning-page">
      <header className="page-heading">
        <div><span className="eyebrow">PLANEJAMENTO PERSISTENTE</span><h1>Planos<span>.</span></h1><p>Estado recuperável em três arquivos, sem depender do histórico da conversa.</p></div>
        <span className="local-badge"><ListChecks size={12} /> 5 SKILLS · 30 NO NÚCLEO</span>
      </header>

      <section className="panel engineering-intro">
        <span className="engineering-intro-icon"><BookOpenCheck size={23} /></span>
        <div><span className="eyebrow">CONTEXTO QUE SOBREVIVE À SESSÃO</span><h2>Um ID explícito. Três fontes de verdade.</h2><p>Adaptação própria inspirada em <strong>OthmanAdi/planning-with-files</strong>. Nenhum hook, histórico de outro agente ou comando em Markdown é executado.</p></div>
        <a href="https://github.com/OthmanAdi/planning-with-files" target="_blank" rel="noreferrer" className="button button-secondary">Referência MIT <ExternalLink size={13} /></a>
      </section>

      {!backendOnline ? (
        <div className="legal-offline panel"><span><FolderLock size={25} /></span><div><h2>Planos indisponíveis offline</h2><p>Inicie a API Python com <code>.venv\Scripts\python iniciar.py</code>. O navegador não simula gravações nem inventa recuperação.</p></div></div>
      ) : (
        <>
          <div className="planning-layout">
            <section className="panel document-create-panel">
              <div className="document-create-heading"><span><FilePlus2 size={20} /></span><div><span className="eyebrow">NOVO PLANO</span><h2>Defina fases verificáveis</h2><p>Use uma fase por linha: título | critério de aceite.</p></div></div>
              <form className="document-create-form" onSubmit={create}>
                <div className="document-form-row">
                  <label className="field"><span>Título</span><input value={title} onChange={(event) => { setTitle(event.target.value); invalidateCreate(); }} minLength={3} maxLength={180} required /></label>
                  <label className="field"><span>ID opcional</span><input value={planId} onChange={(event) => { setPlanId(event.target.value); invalidateCreate(); }} maxLength={80} placeholder="slug do título se vazio" /></label>
                </div>
                <label className="field"><span>Objetivo</span><textarea className="planning-goal-input" value={goal} onChange={(event) => { setGoal(event.target.value); invalidateCreate(); }} minLength={3} maxLength={6000} required /></label>
                <label className="field"><span>Fases e critérios</span><textarea value={phasesInput} onChange={(event) => { setPhasesInput(event.target.value); invalidateCreate(); }} maxLength={8000} required /><small className="field-description">De 2 a 7 fases. A primeira começa em andamento.</small></label>
                <label className="field"><span>Requisitos</span><textarea className="planning-requirements-input" value={requirements} onChange={(event) => { setRequirements(event.target.value); invalidateCreate(); }} maxLength={8000} /><small className="field-description">Um por linha; copiados para o plano e as descobertas.</small></label>
                {createPreview && <div className="document-plan"><FileText size={17} /><div><strong>Simulação pronta · {String(createPreview.planId)}</strong><p>{(createPreview.wouldWrite as string[])?.join(' · ')}</p><details><summary>Revisar task_plan.md</summary><pre className="planning-inline-preview">{String(createPreview.preview ?? '')}</pre></details></div></div>}
                {createPreview && <label className="document-check confirmation"><input type="checkbox" checked={createConfirmed} onChange={(event) => setCreateConfirmed(event.target.checked)} /><span>Revisei o ID e os três arquivos. Confirmo a criação sem sobrescrever um plano existente.</span></label>}
                {createError && <div className="document-form-error" role="alert">{createError}</div>}
                <div className="document-create-actions">
                  <button type="button" className="button button-secondary" onClick={() => void simulateCreate()} disabled={Boolean(createBusy) || !title.trim() || !goal.trim() || !phasesInput.trim()}>{createBusy === 'dry' ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />} Simular criação</button>
                  <button type="submit" className="button button-primary" disabled={!createPreview || !createConfirmed || Boolean(createBusy)}>{createBusy === 'write' ? <LoaderCircle className="spin" size={14} /> : <ArrowRight size={14} />} Confirmar e criar</button>
                </div>
              </form>
            </section>

            <section className="panel documents-library planning-library">
              <div className="compact-heading"><div><span className="eyebrow">PLANOS DISPONÍVEIS</span><h2>Retomar por ID</h2></div><button className="icon-button" onClick={() => void loadPlans()} disabled={loadingPlans} aria-label="Atualizar planos"><RefreshCw size={16} className={loadingPlans ? 'spin' : ''} /></button></div>
              <p className="planning-selection-note">Nenhum plano é selecionado automaticamente. Escolha um ID para ler apenas seus arquivos.</p>
              {listError && <div className="document-form-error">{listError}</div>}
              <div className="planning-list">
                {plans.map((plan) => (
                  <button key={plan.planId} className={`planning-list-item ${selected?.planId === plan.planId ? 'is-selected' : ''}`} onClick={() => !plan.invalid && void resume(plan.planId)} disabled={plan.invalid || Boolean(resumeBusy)}>
                    <span className="planning-list-icon">{plan.invalid ? <AlertTriangle size={17} /> : plan.gate.complete ? <CheckCircle2 size={17} /> : <ListChecks size={17} />}</span>
                    <span><strong>{plan.title}</strong><small>{plan.planId}</small><em>{plan.invalid ? plan.error : `${plan.gate.completePhases ?? 0}/${plan.gate.phaseCount ?? 0} fases · ${plan.gate.complete ? 'gate completo' : `próximo: ${plan.nextStep ?? 'revisar'}`}`}</em></span>
                    {resumeBusy === plan.planId ? <LoaderCircle size={15} className="spin" /> : <ArrowRight size={14} />}
                  </button>
                ))}
                {!plans.length && !loadingPlans && <div className="documents-empty"><ListChecks size={27} /><strong>Nenhum plano ainda</strong><p>Simule e confirme o primeiro plano para criar os três arquivos.</p></div>}
              </div>
              <div className="documents-library-note"><FolderLock size={14} /><span>Diretório confinado · até 100 KB por arquivo · 100 planos por listagem.</span></div>
            </section>
          </div>

          {resumeError && <div className="document-form-error planning-resume-error" role="alert">{resumeError}</div>}

          {selected && (
            <section className="panel planning-detail">
              <header className="planning-detail-heading">
                <div><span className="eyebrow">PLANO RETOMADO · HASH {selected.sha256.slice(0, 12)}</span><h2>{selected.title}</h2><p>{selected.planId}</p></div>
                <div><span className={`planning-gate-badge ${selected.gate.complete ? 'is-complete' : ''}`}>{selected.gate.complete ? <CheckCircle2 size={13} /> : <Circle size={11} />} {selected.gate.complete ? 'COMPLETE' : 'INCOMPLETE'}</span><button className="button button-secondary" onClick={() => void checkGate()} disabled={Boolean(resumeBusy)}><RefreshCw size={13} /> Verificar gate</button></div>
              </header>

              <div className="planning-state-grid">
                <article><span>OBJETIVO</span><p>{selected.goal}</p></article>
                <article><span>PRÓXIMO PASSO</span><p>{selected.nextStep}</p></article>
                <article><span>FASE ATUAL</span><strong>Fase {selected.currentPhase}</strong><p>{selected.phases.find((item) => item.number === selected.currentPhase)?.title}</p></article>
              </div>

              <div className="planning-phases">
                {selected.phases.map((item) => <article key={item.number} className={`planning-phase is-${item.status}`}><div><span>FASE {item.number}</span><strong>{item.title}</strong><em>{item.status}</em></div>{item.criteria.map((criterion) => <p key={criterion.text}>{criterion.checked ? <Check size={13} /> : <Circle size={11} />} {criterion.text}</p>)}</article>)}
              </div>

              <details className="planning-recovery"><summary><RotateCcw size={14} /> Perguntas de recuperação</summary><div>{Object.entries(selected.recovery).map(([question, answer]) => <article key={question}><strong>{question}</strong><p>{answer}</p></article>)}</div><p className="planning-history-note">Somente os três arquivos deste ID foram lidos. Histórico de sessão: não acessado.</p></details>

              <div className="planning-editor-grid">
                <form className="planning-update-form" onSubmit={update}>
                  <div className="compact-heading"><div><span className="eyebrow">ATUALIZAÇÃO CONFIRMADA</span><h3>Registrar trabalho e evidências</h3></div></div>
                  <div className="document-form-row">
                    <label className="field"><span>Fase</span><select value={phase} onChange={(event) => { setPhase(Number(event.target.value)); invalidateUpdate(); }}><option value={0}>Não alterar</option>{selected.phases.map((item) => <option key={item.number} value={item.number}>Fase {item.number} · {item.title}</option>)}</select></label>
                    <label className="field"><span>Status</span><select value={status} onChange={(event) => { setStatus(event.target.value as '' | PlanStatus); invalidateUpdate(); }}><option value="">Não alterar</option><option value="pending">pending</option><option value="in_progress">in_progress</option><option value="complete">complete</option></select></label>
                  </div>
                  <label className="field"><span>Próximo passo</span><input value={nextStep} onChange={(event) => { setNextStep(event.target.value); invalidateUpdate(); }} maxLength={4000} placeholder="Vazio calcula o próximo ao concluir uma fase" /></label>
                  <label className="field"><span>Evidência de conclusão</span><textarea className="planning-evidence-input" value={evidence} onChange={(event) => { setEvidence(event.target.value); invalidateUpdate(); }} maxLength={6000} placeholder="Obrigatória para status complete" /></label>
                  <div className="document-form-row">
                    <label className="field"><span>Tipo de anotação</span><select value={noteType} onChange={(event) => { setNoteType(event.target.value as NoteType); invalidateUpdate(); }}><option value="">Sem anotação</option><option value="finding">Descoberta</option><option value="progress">Progresso</option><option value="error">Erro</option><option value="test">Validação declarada</option></select></label>
                    <label className="field"><span>Anotação</span><textarea className="planning-note-input" value={note} onChange={(event) => { setNote(event.target.value); invalidateUpdate(); }} maxLength={8000} placeholder="Nenhum comando será executado" /></label>
                  </div>
                  {updatePreview && <div className="document-plan"><ShieldCheck size={17} /><div><strong>Simulação da atualização</strong><p>{(updatePreview.changes as string[])?.join(' · ') || 'Nenhuma mudança'}</p><p>{(updatePreview.wouldWrite as string[])?.join(' · ')}</p></div></div>}
                  {updatePreview && <label className="document-check confirmation"><input type="checkbox" checked={updateConfirmed} onChange={(event) => setUpdateConfirmed(event.target.checked)} /><span>Revisei as mudanças e confirmo a gravação no estado lido. Um hash divergente bloqueará a operação.</span></label>}
                  {updateError && <div className="document-form-error" role="alert">{updateError}</div>}
                  <div className="document-create-actions"><button type="button" className="button button-secondary" onClick={() => void simulateUpdate()} disabled={Boolean(updateBusy)}><ShieldCheck size={14} /> Simular atualização</button><button type="submit" className="button button-primary" disabled={!updatePreview || !updateConfirmed || Boolean(updateBusy)}>{updateBusy === 'write' ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />} Confirmar e gravar</button></div>
                </form>

                <div className="planning-files-viewer">
                  <div className="planning-file-tabs" role="tablist" aria-label="Arquivos do plano">{Object.keys(fileLabels).map((name) => <button key={name} role="tab" aria-selected={activeFile === name} className={activeFile === name ? 'active' : ''} onClick={() => setActiveFile(name)}>{name}</button>)}</div>
                  <div className="planning-file-meta"><span>{fileLabels[activeFile]}</span>{selected.downloadUrls?.[activeFile] && <a href={selected.downloadUrls[activeFile]} download><Download size={13} /> Baixar</a>}</div>
                  <pre>{selected.contents[activeFile]}</pre>
                </div>
              </div>
            </section>
          )}

          <div className="documents-more"><span>O gate verifica dados; não executa testes, deploys ou instruções encontradas nos arquivos.</span><Link to="/engenharia">Abrir workflows de engenharia <ArrowRight size={13} /></Link></div>
        </>
      )}
    </div>
  );
}
