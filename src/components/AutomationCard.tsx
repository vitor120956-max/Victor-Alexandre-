import { CalendarClock, Clock3, Download, ListOrdered, Play, Sparkles, Trash2 } from 'lucide-react';
import type { Automation } from '../types';
import { useApp } from '../context/AppContext';
import { relativeTime } from '../lib/utils';

const actionIcons = {
  summary: Sparkles,
  focus: Clock3,
  organize: ListOrdered,
  backup: Download,
};

function scheduleLabel(automation: Automation): string {
  const { frequency, time, weekday } = automation.schedule;
  if (frequency === 'manual') return 'Execução manual';
  if (frequency === 'daily') return `Todos os dias · ${time}`;
  const days = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  return `${days[weekday]} · ${time}`;
}

export function AutomationCard({ automation, compact = false }: { automation: Automation; compact?: boolean }) {
  const { toggleAutomation, runAutomation, deleteAutomation } = useApp();
  const Icon = actionIcons[automation.action];
  return (
    <article className={compact ? 'automation-card automation-compact' : 'automation-card'}>
      <div className="automation-top">
        <span className="automation-icon"><Icon size={19} /></span>
        <button
          className={`switch ${automation.enabled ? 'switch-on' : ''}`}
          role="switch"
          aria-checked={automation.enabled}
          aria-label={`${automation.enabled ? 'Desativar' : 'Ativar'} ${automation.name}`}
          onClick={() => toggleAutomation(automation.id)}
        ><span /></button>
      </div>
      <div className="automation-copy"><strong>{automation.name}</strong>{!compact && <p>{automation.description}</p>}</div>
      <div className="automation-schedule"><CalendarClock size={14} /><span>{scheduleLabel(automation)}</span></div>
      <div className="automation-footer">
        <span>{automation.lastRun ? `Executada ${relativeTime(automation.lastRun)}` : 'Ainda não executada'}</span>
        <div>
          {automation.custom && !compact && <button className="icon-button small" onClick={() => deleteAutomation(automation.id)} aria-label={`Excluir ${automation.name}`}><Trash2 size={14} /></button>}
          <button className="run-button" onClick={() => runAutomation(automation.id)}><Play size={13} fill="currentColor" /> Executar</button>
        </div>
      </div>
    </article>
  );
}
