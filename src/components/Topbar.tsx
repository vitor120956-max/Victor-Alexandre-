import { useState } from 'react';
import { Bell, ChevronDown, Command, Menu, Search, ShieldCheck } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ActivityFeed } from './ActivityFeed';
import { useApp } from '../context/AppContext';

const pageNames: Record<string, string> = {
  '/': 'Visão geral',
  '/conversa': 'Conversa',
  '/tarefas': 'Tarefas',
  '/automacoes': 'Automações',
  '/memoria': 'Memória',
  '/leis': 'Legislação',
  '/documentos': 'Documentos',
  '/engenharia': 'Engenharia',
  '/planejamento': 'Planos',
  '/reversa': 'Reversa',
  '/lean': 'Enxuto',
  '/agencia': 'Agentes',
  '/estudio': 'Estúdio',
  '/skills': 'Skills',
  '/configuracoes': 'Configurações',
};

export function Topbar({ onMenu, onCommand }: { onMenu: () => void; onCommand: () => void }) {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { preferences, activities, backendOnline } = useApp();
  return (
    <header className="topbar">
      <div className="topbar-location">
        <button className="mobile-menu icon-button" onClick={onMenu} aria-label="Abrir menu"><Menu size={20} /></button>
        <span>CENTRAL</span><i>/</i><strong>{pageNames[pathname] ?? 'JARVIS'}</strong>
      </div>
      <button className="command-trigger" onClick={onCommand}>
        <Search size={17} />
        <span>Buscar ou executar um comando...</span>
        <kbd><Command size={12} /> K</kbd>
      </button>
      <div className="topbar-actions">
        <div className="secure-status"><ShieldCheck size={15} /><span>{backendOnline ? 'API PYTHON ATIVA' : 'MODO NAVEGADOR'}</span></div>
        <div className="notification-wrap">
          <button className="icon-button notification-button" onClick={() => setNotificationsOpen((value) => !value)} aria-label="Abrir atividades" aria-expanded={notificationsOpen}>
            <Bell size={19} />
            {activities.length > 0 && <span />}
          </button>
          {notificationsOpen && (
            <div className="notification-popover">
              <div className="popover-heading"><strong>Atividade recente</strong><span>{activities.length} registros</span></div>
              <ActivityFeed limit={5} compact />
              <button className="popover-footer" onClick={() => { setNotificationsOpen(false); navigate('/automacoes'); }}>Ver histórico completo</button>
            </div>
          )}
        </div>
        <button className="profile-button" onClick={() => navigate('/configuracoes')} aria-label="Abrir configurações de perfil">
          <span>{preferences.name.slice(0, 1).toUpperCase()}</span>
          <div><strong>{preferences.name}</strong><small>Administrador</small></div>
          <ChevronDown size={14} />
        </button>
      </div>
    </header>
  );
}
