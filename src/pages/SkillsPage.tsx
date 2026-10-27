import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Blocks, Brain, Calculator, Check, Clock3, Code2, FileText, Fingerprint, Globe2, ListTodo, Play, RefreshCw, Scale, ShieldAlert, Sparkles, Terminal, Workflow, Wrench } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Modal } from '../components/Modal';
import { PythonSkillRunner } from '../components/PythonSkillRunner';
import { skills } from '../data/skills';
import type { Skill } from '../data/skills';
import { listarPlanosPendentes } from '../lib/api';
import { parametrosDeExecucao } from '../lib/planos';
import type { PlanoPendente, PythonSkill } from '../lib/api';
import { useApp } from '../context/AppContext';
import { classNames } from '../lib/utils';

const icons = { sparkles: Sparkles, tasks: ListTodo, brain: Brain, calculator: Calculator, timer: Clock3, globe: Globe2, workflow: Workflow, code: Code2 };

export function SkillsPage() {
  const [filter, setFilter] = useState('Todas');
  const [selected, setSelected] = useState<Skill | null>(null);
  const [runnerSkill, setRunnerSkill] = useState<PythonSkill | null>(null);
  const { sendMessage, pythonSkills, backendOnline, backendVersion, refreshBackend, executeSkill, hostToken, modoDono, pushToast } = useApp();
  const [planos, setPlanos] = useState<PlanoPendente[]>([]);
  const [instalarLigado, setInstalarLigado] = useState(false);
  const [planoEscolhido, setPlanoEscolhido] = useState<PlanoPendente | null>(null);
  const [confirmouPlano, setConfirmouPlano] = useState(false);
  const [executando, setExecutando] = useState(false);
  const [resultadoPlano, setResultadoPlano] = useState<string>('');

  const carregarPlanos = useCallback(async () => {
    if (!backendOnline) {
      setPlanos([]);
      return;
    }
    try {
      const resposta = await listarPlanosPendentes();
      setPlanos(resposta.planos ?? []);
      setInstalarLigado(Boolean(resposta.instalar));
    } catch {
      setPlanos([]);
    }
  }, [backendOnline]);

  useEffect(() => {
    void carregarPlanos();
    if (!backendOnline) return;
    const timer = window.setInterval(() => void carregarPlanos(), 30000);
    return () => window.clearInterval(timer);
  }, [carregarPlanos, backendOnline]);

  const abrirPlano = (plano: PlanoPendente) => {
    setPlanoEscolhido(plano);
    setConfirmouPlano(false);
    setResultadoPlano('');
  };

  const executarPlanoEscolhido = async () => {
    if (!planoEscolhido || executando || !confirmouPlano) return;
    setExecutando(true);
    setResultadoPlano('');
    try {
      const resposta = await executeSkill(
        'sistema.executar',
        parametrosDeExecucao(planoEscolhido, { hostToken, modoDono }),
        { confirmed: true },
      );
      if (resposta.ok) {
        const saida = resposta.result ?? {};
        setResultadoPlano(
          [saida.summary, saida.verdict, saida.markdown, JSON.stringify(saida, null, 2)]
            .find((valor) => typeof valor === 'string' && valor.trim()) as string ?? 'Plano executado.',
        );
        pushToast('Plano executado', planoEscolhido.rotulo || planoEscolhido.arquivo || planoEscolhido.confirmacao);
      } else {
        setResultadoPlano(`Recusado: ${resposta.error?.message ?? 'erro desconhecido'}`);
        pushToast('Plano recusado', resposta.error?.message, 'warning');
      }
    } catch (error) {
      setResultadoPlano(`Falha: ${error instanceof Error ? error.message : 'desconhecido'}`);
    } finally {
      setExecutando(false);
      void carregarPlanos();
    }
  };
  const navigate = useNavigate();
  const categories = ['Todas', 'Essencial', 'Produtividade', 'Conectividade', 'Python'];
  const visible = filter === 'Todas' ? skills : filter === 'Python' ? [] : skills.filter((skill) => skill.category === filter);
  const activeCount = skills.filter((skill) => skill.active).length + pythonSkills.length;

  const testSkill = (skill: Skill) => {
    if (!skill.active || !skill.commands[0]) return;
    sendMessage(skill.commands[0]);
    setSelected(null);
    navigate('/conversa');
  };

  return (
    <div className="skills-page">
      <header className="page-heading">
        <div><span className="eyebrow">ARQUITETURA MODULAR</span><h1>Skills<span>.</span></h1><p>Capacidades independentes, reunidas em um único núcleo.</p></div>
        <span className="local-badge"><i /> {activeCount} SKILLS ATIVAS</span>
      </header>
      <div className="skill-overview">
        <div><span className="skill-overview-icon"><Blocks size={22} /></span><div><strong>Um núcleo. Novas possibilidades.</strong><p>Skills do navegador, Python e IA externa com origem identificada e permissões separadas.</p></div></div>
        <button className="backend-refresh" onClick={() => void refreshBackend()}><RefreshCw size={13} />{backendOnline ? `API v${backendVersion}` : 'API offline'}</button>
      </div>
      {planos.length > 0 && (
        <div className="planos-pendentes">
          <div className="planos-cabeca">
            <Terminal size={16} />
            <strong>{planos.length === 1 ? 'Um plano pronto' : `${planos.length} planos prontos`}</strong>
            <span>gerado por <code>sistema.instalar</code>, válido por poucos minutos</span>
          </div>
          {planos.map((plano) => (
            <div className="plano-linha" key={plano.confirmacao}>
              <div>
                <strong>{plano.rotulo || plano.arquivo || plano.confirmacao}</strong>
                <small>{plano.acao} · {plano.tipo || 'pacote'} · expira em {Math.max(0, Math.round(plano.expira_em / 60))} min</small>
              </div>
              <button className="button button-primary" onClick={() => abrirPlano(plano)} disabled={!instalarLigado}>
                <Play size={14} /> Executar este plano
              </button>
            </div>
          ))}
          {!instalarLigado && (
            <p className="planos-aviso"><ShieldAlert size={14} /> A instalação está desligada: suba a API com <code>JARVIS_HOST_INSTALAR=1</code> para executar.</p>
          )}
        </div>
      )}
      {!backendOnline && <div className="python-offline-note"><Code2 size={16} /><span>O catálogo Python está indisponível. Inicie a API com <code>npm run dev</code>; as skills do navegador continuam funcionando.</span></div>}
      <div className="skill-filters">{categories.map((category) => <button key={category} className={classNames(filter === category && 'active')} onClick={() => setFilter(category)}>{category}{category === 'Python' && backendOnline ? ` · ${pythonSkills.length}` : ''}</button>)}</div>
      <div className="skills-grid">
        {visible.map((skill) => {
          const Icon = icons[skill.icon];
          const active = skill.id === 'python' ? backendOnline && pythonSkills.length > 0 : skill.active;
          const displaySkill = { ...skill, active };
          return (
            <article className={classNames('skill-card', !active && 'skill-inactive')} key={skill.id}>
              <div className="skill-card-top"><span className="skill-icon"><Icon size={21} /></span><span className={active ? 'skill-status active' : 'skill-status'}>{active ? <><i /> ATIVA</> : 'CONEXÃO PENDENTE'}</span></div>
              <span className="skill-category">{skill.category}</span>
              <h2>{skill.name}</h2>
              <p>{skill.id === 'python' && active ? `${pythonSkills.length} skills Python disponíveis pela API local, com parâmetros validados e histórico.` : skill.description}</p>
              {skill.commands[0] && <code>“{skill.commands[0]}”</code>}
              <div className="skill-card-footer"><span>{skill.local ? 'Execução local' : 'Conexão externa'}</span><button onClick={() => setSelected(displaySkill)}>Detalhes <ArrowRight size={14} /></button></div>
            </article>
          );
        })}
        {(filter === 'Todas' || filter === 'Python') && pythonSkills.map((skill) => {
          const legal = skill.id.startsWith('legal.');
          const document = skill.id === 'document.read' || skill.id === 'document.create';
          const engineering = skill.id.startsWith('engineering.');
          const planning = skill.id.startsWith('planning.');
          const reverse = skill.id.startsWith('reverse.');
          const dedicated = legal || document || engineering || planning || reverse;
          return (
            <article className="skill-card python-skill-card" key={skill.id}>
              <div className="skill-card-top"><span className="skill-icon">{legal ? <Scale size={21} /> : document ? <FileText size={21} /> : engineering ? <Wrench size={21} /> : planning ? <ListTodo size={21} /> : reverse ? <Fingerprint size={21} /> : <Code2 size={21} />}</span><span className="skill-status active"><i /> PYTHON</span></div>
              <span className="skill-category">API / {skill.category}</span>
              <h2>{skill.name}</h2>
              <p>{skill.description}</p>
              <code>{skill.id}</code>
              <div className="skill-card-footer"><span>{skill.requiresConfirmation ? 'Exige confirmação' : legal || reverse ? 'Somente leitura · sem IA' : 'Sem efeitos externos'}</span><button onClick={() => legal ? navigate('/leis') : document ? navigate('/documentos') : engineering ? navigate('/engenharia') : planning ? navigate('/planejamento') : reverse ? navigate('/reversa') : setRunnerSkill(skill)}>{dedicated ? legal ? 'Abrir Legislação' : document ? 'Abrir Documentos' : engineering ? 'Abrir Engenharia' : planning ? 'Abrir Planos' : 'Abrir Reversa' : 'Executar'} {dedicated ? <ArrowRight size={13} /> : <Play size={13} />}</button></div>
            </article>
          );
        })}
      </div>
      <Modal open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.name ?? ''} eyebrow={selected?.category.toUpperCase()}>
        {selected && <div className="skill-detail"><div className="skill-detail-status"><span className={selected.active ? 'skill-status active' : 'skill-status'}>{selected.active ? <><Check size={13} /> INSTALADA E ATIVA</> : 'CONEXÃO PENDENTE'}</span><span>{selected.local ? 'LOCAL' : 'EXTERNA'}</span></div><p>{selected.detail}</p>{selected.commands.length > 0 && <div className="skill-command-list"><span>EXEMPLOS DE COMANDO</span>{selected.commands.map((command) => <button key={command} onClick={() => { sendMessage(command); setSelected(null); navigate('/conversa'); }}>“{command}” <Play size={13} /></button>)}</div>}<div className="modal-actions"><button className="button button-ghost" onClick={() => setSelected(null)}>Fechar</button>{selected.active && selected.commands.length > 0 && <button className="button button-primary" onClick={() => testSkill(selected)}>Testar skill <ArrowRight size={16} /></button>}</div></div>}
      </Modal>
      <Modal open={Boolean(planoEscolhido)} onClose={() => setPlanoEscolhido(null)} title="Executar plano" eyebrow="SISTEMA · EFEITO REAL NA MÁQUINA">
        {planoEscolhido && (
          <div className="plano-execucao">
            <div className="plano-detalhes-box">
              <div><span>Alvo</span><strong>{planoEscolhido.rotulo || planoEscolhido.arquivo}</strong></div>
              <div><span>Ação</span><strong>{planoEscolhido.acao}</strong></div>
              <div><span>Tipo</span><strong>{planoEscolhido.tipo || '—'}</strong></div>
              <div><span>Expira em</span><strong>{Math.max(0, Math.round(planoEscolhido.expira_em / 60))} min</strong></div>
            </div>
            {planoEscolhido.comando && <pre className="plano-comando">{planoEscolhido.comando}</pre>}
            {planoEscolhido.sha256 && <p className="plano-sha-linha">SHA-256 do arquivo: <code>{planoEscolhido.sha256.slice(0, 24)}…</code></p>}
            <p className="plano-ressalva">Isto roda o comando acima com os privilégios do processo da API. O código vale uma vez; depois de executar, ele morre.</p>
            <label className="confirmation-box">
              <ShieldAlert size={18} />
              <span>Li o comando e confirmo a execução neste PC.</span>
              <input type="checkbox" checked={confirmouPlano} onChange={(event) => setConfirmouPlano(event.target.checked)} />
            </label>
            {resultadoPlano && <pre className="plano-resultado">{resultadoPlano}</pre>}
            <div className="modal-actions">
              <button className="button button-ghost" onClick={() => setPlanoEscolhido(null)}>Fechar</button>
              <button className="button button-primary" onClick={() => void executarPlanoEscolhido()} disabled={!confirmouPlano || executando}>
                <Play size={15} />{executando ? 'Executando…' : 'Executar agora'}
              </button>
            </div>
          </div>
        )}
      </Modal>
      <PythonSkillRunner skill={runnerSkill} onClose={() => setRunnerSkill(null)} onExecuted={() => void carregarPlanos()} />
    </div>
  );
}
