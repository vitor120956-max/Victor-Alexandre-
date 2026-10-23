import { useMemo, useState } from 'react';
import { CheckCheck, CheckSquare2, Circle, Flag, Plus, Search } from 'lucide-react';
import { FocusWidget } from '../components/FocusWidget';
import { TaskItem } from '../components/TaskItem';
import { useApp } from '../context/AppContext';
import { classNames, normalizeText } from '../lib/utils';

type Filter = 'todas' | 'pendentes' | 'concluidas';

export function TasksPage() {
  const { tasks, openTaskModal } = useApp();
  const [filter, setFilter] = useState<Filter>('todas');
  const [query, setQuery] = useState('');
  const pending = tasks.filter((task) => !task.completed).length;
  const completed = tasks.length - pending;
  const high = tasks.filter((task) => !task.completed && task.priority === 'alta').length;
  const progress = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;

  const visibleTasks = useMemo(() => tasks.filter((task) => {
    const matchesFilter = filter === 'todas' || (filter === 'pendentes' ? !task.completed : task.completed);
    const matchesQuery = normalizeText(`${task.title} ${task.project}`).includes(normalizeText(query));
    return matchesFilter && matchesQuery;
  }), [filter, query, tasks]);

  return (
    <div className="tasks-page">
      <header className="page-heading">
        <div><span className="eyebrow">EXECUÇÃO</span><h1>Tarefas<span>.</span></h1><p>Transforme intenção em próximos passos claros.</p></div>
        <button className="button button-primary" onClick={openTaskModal}><Plus size={17} /> Nova tarefa</button>
      </header>
      <div className="metric-grid task-metrics">
        <div className="metric-card"><span className="metric-icon"><CheckSquare2 size={18} /></span><div><strong>{tasks.length}</strong><span>Total de tarefas</span></div><small>neste dispositivo</small></div>
        <div className="metric-card"><span className="metric-icon"><Circle size={18} /></span><div><strong>{pending}</strong><span>Pendentes</span></div><small>{pending ? 'próximas ações' : 'lista em dia'}</small></div>
        <div className="metric-card"><span className="metric-icon"><CheckCheck size={18} /></span><div><strong>{completed}</strong><span>Concluídas</span></div><small>{progress}% do total</small></div>
        <div className="metric-card"><span className="metric-icon metric-warm"><Flag size={18} /></span><div><strong>{high}</strong><span>Alta prioridade</span></div><small>pedem atenção</small></div>
      </div>
      <div className="tasks-page-layout">
        <section className="panel tasks-workspace">
          <div className="task-toolbar">
            <div className="filter-tabs" role="tablist" aria-label="Filtrar tarefas">
              {(['todas', 'pendentes', 'concluidas'] as Filter[]).map((value) => (
                <button key={value} role="tab" aria-selected={filter === value} className={classNames(filter === value && 'active')} onClick={() => setFilter(value)}>
                  {value === 'concluidas' ? 'Concluídas' : value[0].toUpperCase() + value.slice(1)}
                  <span>{value === 'todas' ? tasks.length : value === 'pendentes' ? pending : completed}</span>
                </button>
              ))}
            </div>
            <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar tarefa..." aria-label="Buscar tarefa" /></label>
          </div>
          <div className="task-list task-list-full">
            {visibleTasks.map((task) => <TaskItem key={task.id} task={task} />)}
            {visibleTasks.length === 0 && (
              <div className="empty-state"><span><CheckSquare2 size={25} /></span><h3>Nenhuma tarefa por aqui</h3><p>Ajuste o filtro ou crie um novo próximo passo.</p><button className="button button-secondary" onClick={openTaskModal}><Plus size={16} /> Criar tarefa</button></div>
            )}
          </div>
        </section>
        <aside className="tasks-aside">
          <FocusWidget />
          <section className="panel progress-panel">
            <span className="eyebrow">PROGRESSO GERAL</span>
            <div className="progress-number"><strong>{progress}%</strong><span>concluído</span></div>
            <div className="large-progress"><span style={{ width: `${progress}%` }} /></div>
            <p>Pequeno progresso ainda é progresso. Continue no seu ritmo.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
