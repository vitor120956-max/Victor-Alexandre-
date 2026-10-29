import { useState } from 'react';
import {
  ArrowRight,
  BookOpenCheck,
  Code2,
  ExternalLink,
  FileCheck2,
  Gauge,
  GitBranch,
  ListChecks,
  Rocket,
  ScanSearch,
  ShieldCheck,
  TestTube2,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { PythonSkillRunner } from '../components/PythonSkillRunner';
import { useApp } from '../context/AppContext';
import type { PythonSkill } from '../lib/api';

interface WorkflowMeta {
  id: string;
  phase: string;
  title: string;
  output: string;
  icon: LucideIcon;
}

const workflows: WorkflowMeta[] = [
  { id: 'engineering.spec', phase: '01 · DEFINIR', title: 'Especificação', output: 'Escopo, aceite e questões abertas', icon: FileCheck2 },
  { id: 'engineering.plan', phase: '02 · PLANEJAR', title: 'Plano vertical', output: 'Tarefas ordenadas e checkpoints', icon: ListChecks },
  { id: 'engineering.tests', phase: '03 · VERIFICAR', title: 'Matriz de testes', output: 'Casos e evidências para cada aceite', icon: TestTube2 },
  { id: 'engineering.review', phase: '04 · REVISAR', title: 'Revisão estática', output: 'Padrões, linhas e severidade', icon: ScanSearch },
  { id: 'engineering.threat-model', phase: '05 · PROTEGER', title: 'Modelo de ameaças', output: 'STRIDE e casos de abuso', icon: ShieldCheck },
  { id: 'engineering.webvitals', phase: '06 · MEDIR', title: 'Core Web Vitals', output: 'LCP, INP e CLS com proveniência', icon: Gauge },
  { id: 'engineering.adr', phase: '07 · DOCUMENTAR', title: 'Decisão de arquitetura', output: 'ADR com alternativas e trade-offs', icon: BookOpenCheck },
  { id: 'engineering.release', phase: '08 · ENTREGAR', title: 'Gate de release', output: 'Bloqueadores e evidências declaradas', icon: Rocket },
];

export function EngineeringPage() {
  const { backendOnline, pythonSkills } = useApp();
  const [runnerSkill, setRunnerSkill] = useState<PythonSkill | null>(null);
  const byId = new Map(pythonSkills.map((skill) => [skill.id, skill]));

  return (
    <div className="engineering-page">
      <header className="page-heading">
        <div><span className="eyebrow">WORKFLOWS DE ENGENHARIA</span><h1>Engenharia<span>.</span></h1><p>Da especificação à entrega, com evidências e limites explícitos.</p></div>
        <span className="local-badge"><Wrench size={12} /> 8 WORKFLOWS · 30 SKILLS NO NÚCLEO</span>
      </header>

      <section className="panel engineering-intro">
        <span className="engineering-intro-icon"><GitBranch size={23} /></span>
        <div><span className="eyebrow">PROCESSO ANTES DE ATALHOS</span><h2>Um workflow local para cada decisão.</h2><p>Adaptações próprias inspiradas em <strong>addyosmani/agent-skills</strong>. Nenhum plugin, hook ou script externo é executado.</p></div>
        <a href="https://github.com/addyosmani/agent-skills" target="_blank" rel="noreferrer" className="button button-secondary">Referência MIT <ExternalLink size={13} /></a>
      </section>

      {!backendOnline ? (
        <div className="legal-offline panel"><span><Code2 size={25} /></span><div><h2>Workflows indisponíveis offline</h2><p>Inicie a API Python com <code>.venv\Scripts\python iniciar.py</code>. Nenhum rascunho será simulado no navegador.</p></div></div>
      ) : (
        <>
          <div className="engineering-grid">
            {workflows.map(({ id, phase, title, output, icon: Icon }) => {
              const skill = byId.get(id);
              return (
                <article className="panel engineering-card" key={id}>
                  <div className="engineering-card-top"><span className="engineering-card-icon"><Icon size={20} /></span><span>{phase}</span></div>
                  <h2>{title}</h2>
                  <p>{skill?.description ?? output}</p>
                  <div className="engineering-output"><strong>SAÍDA</strong><span>{output}</span></div>
                  <footer><span><i /> LOCAL · SEM EFEITOS EXTERNOS</span><button onClick={() => skill && setRunnerSkill(skill)} disabled={!skill}>Abrir workflow <ArrowRight size={13} /></button></footer>
                </article>
              );
            })}
          </div>

          <section className="engineering-boundaries">
            <article><ScanSearch size={17} /><div><strong>Revisão não é aprovação</strong><p>A análise procura padrões conhecidos no trecho fornecido. Ela não executa código nem comprova segurança.</p></div></article>
            <article><Gauge size={17} /><div><strong>Métrica precisa de origem</strong><p>Web Vitals são classificados a partir dos valores informados; laboratório não substitui dados reais de campo.</p></div></article>
            <article><Rocket size={17} /><div><strong>Gate não é deploy</strong><p>O checklist de release organiza declarações e bloqueadores. Nenhum teste, publicação ou rollback é executado.</p></div></article>
          </section>
        </>
      )}
      <PythonSkillRunner skill={runnerSkill} onClose={() => setRunnerSkill(null)} />
    </div>
  );
}
