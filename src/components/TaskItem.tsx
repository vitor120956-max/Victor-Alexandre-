import { Check, Trash2 } from 'lucide-react';
import type { Task } from '../types';
import { classNames, todayISO } from '../lib/utils';
import { useApp } from '../context/AppContext';

function dueLabel(date: string): string {
  if (date === todayISO()) return 'Hoje';
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowValue = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
  if (date === tomorrowValue) return 'Amanhã';
  return new Date(`${date}T12:00:00`).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '');
}

export function TaskItem({ task, compact = false }: { task: Task; compact?: boolean }) {
  const { toggleTask, deleteTask } = useApp();
  return (
    <article className={classNames('task-item', task.completed && 'task-completed', compact && 'task-item-compact')}>
      <button
        className="task-check"
        onClick={() => toggleTask(task.id)}
        aria-label={task.completed ? `Reabrir ${task.title}` : `Concluir ${task.title}`}
      >
        <Check size={14} strokeWidth={2.5} />
      </button>
      <div className="task-content">
        <strong>{task.title}</strong>
        <div className="task-meta">
          <span className="project-dot" />
          <span>{task.project}</span>
          <span className="meta-divider">/</span>
          <span>{dueLabel(task.dueDate)}</span>
        </div>
      </div>
      <span className={`priority priority-${task.priority}`}>{task.priority === 'media' ? 'média' : task.priority}</span>
      {!compact && (
        <button className="task-delete" onClick={() => deleteTask(task.id)} aria-label={`Excluir ${task.title}`}>
          <Trash2 size={16} />
        </button>
      )}
    </article>
  );
}
