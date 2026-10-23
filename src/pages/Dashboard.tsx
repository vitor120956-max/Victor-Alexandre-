import { ArrowRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ChatPanel } from '../components/ChatPanel';
import { CommandCenter } from '../components/CommandCenter';
import { TaskItem } from '../components/TaskItem';
import { AutomationCard } from '../components/AutomationCard';
import { useApp } from '../context/AppContext';
import { greetingFor } from '../lib/utils';
import { useNow } from '../hooks/useNow';

export function Dashboard() {
  const { preferences, tasks, openTaskModal, automations } = useApp();
  const now = useNow();
  const todayTasks = tasks.filter((task) => !task.completed).slice(0, 4);
  const completed = tasks.filter((task) => task.completed).length;
  const progress = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;

  return (
    <div className="dashboard-page">
      <header className="page-heading dashboard-heading">
        <div>
          <span className="eyebrow">{now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })}</span>
          <h1>{greetingFor(now)}, {preferences.name}<span>.</span></h1>
          <p>Seu núcleo está pronto. O que vamos resolver primeiro?</p>
        </div>
        <button className="button button-primary heading-action" onClick={openTaskModal}><Plus size={17} /> Nova tarefa</button>
      </header>

      <div className="dashboard-layout">
        <div className="dashboard-main-column">
          <CommandCenter />
          <section className="panel tasks-preview">
            <div className="section-heading">
              <div><span className="eyebrow">PLANO DE AÇÃO</span><h2>Prioridades de hoje</h2></div>
              <Link to="/tarefas" className="text-link">Ver todas <ArrowRight size={15} /></Link>
            </div>
            <div className="task-progress-line">
              <div><span style={{ width: `${progress}%` }} /></div>
              <small>{completed} de {tasks.length} concluídas</small>
            </div>
            <div className="task-list">
              {todayTasks.map((task) => <TaskItem key={task.id} task={task} compact />)}
              {todayTasks.length === 0 && <div className="empty-inline">Tudo em dia. Que bom! <button onClick={openTaskModal}>Adicionar próxima tarefa</button></div>}
            </div>
          </section>
          <section className="dashboard-automations">
            <div className="section-heading">
              <div><span className="eyebrow">ROTINAS</span><h2>Automações</h2></div>
              <Link to="/automacoes" className="text-link">Gerenciar <ArrowRight size={15} /></Link>
            </div>
            <div className="automation-preview-grid">
              {automations.slice(0, 2).map((automation) => <AutomationCard key={automation.id} automation={automation} compact />)}
            </div>
          </section>
        </div>
        <div className="dashboard-chat-column"><ChatPanel /></div>
      </div>
    </div>
  );
}
