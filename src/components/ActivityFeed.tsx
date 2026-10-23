import { Brain, CheckSquare2, Clock3, Cpu, Workflow } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { relativeTime } from '../lib/utils';
import type { Activity } from '../types';

const icons = {
  system: Cpu,
  task: CheckSquare2,
  memory: Brain,
  automation: Workflow,
  focus: Clock3,
};

export function ActivityFeed({ limit = 6, compact = false }: { limit?: number; compact?: boolean }) {
  const { activities } = useApp();
  return (
    <div className={compact ? 'activity-feed activity-compact' : 'activity-feed'}>
      {activities.slice(0, limit).map((activity: Activity) => {
        const Icon = icons[activity.kind];
        return (
          <div className="activity-item" key={activity.id}>
            <span className={`activity-icon activity-${activity.kind}`}><Icon size={15} /></span>
            <div>
              <strong>{activity.title}</strong>
              <p>{activity.detail}</p>
            </div>
            <time>{relativeTime(activity.timestamp)}</time>
          </div>
        );
      })}
      {activities.length === 0 && <p className="muted">Nenhuma atividade registrada ainda.</p>}
    </div>
  );
}
