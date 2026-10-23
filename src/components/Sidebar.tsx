import { NavLink } from 'react-router-dom';
import {
  Blocks,
  Brain,
  Briefcase,
  CheckSquare2,
  FileText,
  Fingerprint,
  Leaf,
  Palette,
  ShieldCheck,
  SwatchBook,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  MousePointerClick,
  Scale,
  Settings,
  Workflow,
  Wrench,
  X,
} from 'lucide-react';
import { Logo } from './Logo';
import { useApp } from '../context/AppContext';
import { classNames, formatTime } from '../lib/utils';

const navigation = [
  { to: '/', label: 'Visão geral', icon: LayoutDashboard, end: true },
  { to: '/conversa', label: 'Conversa', icon: MessageSquareText },
  { to: '/tarefas', label: 'Tarefas', icon: CheckSquare2 },
  { to: '/automacoes', label: 'Automações', icon: Workflow },
  { to: '/memoria', label: 'Memória', icon: Brain },
  { to: '/leis', label: 'Legislação', icon: Scale },
  { to: '/documentos', label: 'Documentos', icon: FileText },
  { to: '/engenharia', label: 'Engenharia', icon: Wrench },
  { to: '/planejamento', label: 'Planos', icon: ListChecks },
  { to: '/reversa', label: 'Reversa', icon: Fingerprint },
  { to: '/lean', label: 'Enxuto', icon: Leaf },
  { to: '/agencia', label: 'Agentes', icon: ShieldCheck },
  { to: '/estudio', label: 'Estúdio', icon: SwatchBook },
  { to: '/direcao', label: 'Direção', icon: Palette },
  { to: '/diagramas', label: 'Diagramas', icon: Workflow },
  { to: '/carreira', label: 'Carreira', icon: Briefcase },
  { to: '/navegador', label: 'Navegador', icon: MousePointerClick },
  { to: '/skills', label: 'Skills', icon: Blocks },
];

export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const { tasks, focus, backendVersion } = useApp();
  const pending = tasks.filter((task) => !task.completed).length;
  return (
    <>
      <aside className={classNames('sidebar', mobileOpen && 'sidebar-open')}>
        <div className="sidebar-top">
          <Logo />
          <button className="mobile-close icon-button" onClick={onClose} aria-label="Fechar menu"><X size={19} /></button>
        </div>
        <div className="nav-label">CENTRAL DE COMANDO</div>
        <nav className="main-nav" aria-label="Navegação principal">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={onClose} className={({ isActive }) => classNames('nav-item', isActive && 'active')}>
              <Icon size={19} strokeWidth={1.7} />
              <span>{label}</span>
              {label === 'Tarefas' && pending > 0 && <span className="nav-count">{pending}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className={`sidebar-focus ${focus.status === 'running' ? 'is-running' : ''}`}>
          <div className="focus-pulse"><span /></div>
          <div>
            <span>{focus.status === 'running' ? 'FOCO EM ANDAMENTO' : focus.status === 'paused' ? 'FOCO PAUSADO' : 'NÚCLEO LOCAL'}</span>
            <strong>{focus.status === 'running' || focus.status === 'paused' ? formatTime(focus.remaining) : 'Pronto para ajudar'}</strong>
          </div>
        </div>
        <NavLink to="/configuracoes" onClick={onClose} className={({ isActive }) => classNames('nav-item settings-link', isActive && 'active')}>
          <Settings size={19} strokeWidth={1.7} />
          <span>Configurações</span>
        </NavLink>
        <div className="sidebar-version"><span>JARVIS OS</span><span>v.{backendVersion ?? "0.14.0"}</span></div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" onClick={onClose} aria-label="Fechar menu" />}
    </>
  );
}
