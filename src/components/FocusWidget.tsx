import { Pause, Play, RotateCcw } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { formatDuration, formatTime } from '../lib/utils';

export function FocusWidget() {
  const { focus, startFocus, pauseFocus, resumeFocus, stopFocus } = useApp();
  const progress = focus.duration > 0 ? Math.min(1, Math.max(0, 1 - focus.remaining / focus.duration)) : 0;
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const statusLabel = {
    idle: 'Pronto para começar',
    running: 'Sessão em andamento',
    paused: 'Sessão pausada',
    completed: 'Sessão concluída',
  }[focus.status];

  return (
    <section className="panel focus-widget">
      <div className="section-heading compact-heading">
        <div><span className="eyebrow">CONCENTRAÇÃO</span><h2>Ciclo de foco</h2></div>
        <span className={`status-chip ${focus.status === 'running' ? 'status-active' : ''}`}>{focus.status === 'running' ? 'AO VIVO' : 'LOCAL'}</span>
      </div>
      <div className="focus-display">
        <div className="focus-ring">
          <svg viewBox="0 0 124 124" aria-hidden="true">
            <circle className="focus-track" cx="62" cy="62" r={radius} />
            <circle className="focus-progress" cx="62" cy="62" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - progress)} />
          </svg>
          <div><strong>{formatTime(focus.remaining)}</strong><span>{Math.round(focus.duration / 60)} MIN</span></div>
        </div>
        <div className="focus-copy">
          <strong>{statusLabel}</strong>
          <p>{formatDuration(focus.elapsedToday)} de foco acumulado hoje.</p>
          <div className="focus-controls">
            {focus.status === 'running' ? (
              <button className="button button-secondary" onClick={pauseFocus}><Pause size={15} /> Pausar</button>
            ) : focus.status === 'paused' ? (
              <button className="button button-primary" onClick={resumeFocus}><Play size={15} /> Retomar</button>
            ) : (
              <button className="button button-primary" onClick={() => startFocus(25)}><Play size={15} /> {focus.status === 'completed' ? 'Novo ciclo' : 'Iniciar 25 min'}</button>
            )}
            {focus.status !== 'idle' && <button className="icon-button" onClick={stopFocus} aria-label="Reiniciar foco"><RotateCcw size={16} /></button>}
          </div>
        </div>
      </div>
    </section>
  );
}
