import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Blocks,
  Brain,
  CheckSquare2,
  Clock3,
  Download,
  FileText,
  Fingerprint,
  Leaf,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  ShieldCheck,
  Scale,
  Search,
  SwatchBook,
  Workflow,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { normalizeText } from '../lib/utils';

interface PaletteAction {
  id: string;
  label: string;
  group: string;
  icon: LucideIcon;
  keywords: string;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { openTaskModal, startFocus, runAutomation, exportBackup } = useApp();

  const actions = useMemo<PaletteAction[]>(() => [
    { id: 'home', label: 'Ir para visão geral', group: 'Navegação', icon: LayoutDashboard, keywords: 'inicio dashboard', run: () => navigate('/') },
    { id: 'chat', label: 'Abrir conversa com o JARVIS', group: 'Navegação', icon: MessageSquareText, keywords: 'chat assistente', run: () => navigate('/conversa') },
    { id: 'new-task', label: 'Criar nova tarefa', group: 'Ações rápidas', icon: CheckSquare2, keywords: 'adicionar todo', run: openTaskModal },
    { id: 'focus', label: 'Iniciar foco de 25 minutos', group: 'Ações rápidas', icon: Clock3, keywords: 'timer pomodoro', run: () => startFocus(25) },
    { id: 'summary', label: 'Executar resumo do dia', group: 'Ações rápidas', icon: Workflow, keywords: 'automação tarefas', run: () => runAutomation('automation-summary') },
    { id: 'backup', label: 'Exportar backup local', group: 'Ações rápidas', icon: Download, keywords: 'dados memoria json', run: exportBackup },
    { id: 'tasks', label: 'Abrir tarefas', group: 'Navegação', icon: CheckSquare2, keywords: 'lista projetos', run: () => navigate('/tarefas') },
    { id: 'automations', label: 'Abrir automações', group: 'Navegação', icon: Workflow, keywords: 'rotinas agenda', run: () => navigate('/automacoes') },
    { id: 'memory', label: 'Abrir memória', group: 'Navegação', icon: Brain, keywords: 'notas lembrar', run: () => navigate('/memoria') },
    { id: 'legal', label: 'Consultar legislação brasileira', group: 'Navegação', icon: Scale, keywords: 'leis artigo juridico cdc constituição lgpd', run: () => navigate('/leis') },
    { id: 'documents', label: 'Abrir documentos locais', group: 'Navegação', icon: FileText, keywords: 'arquivos docx xlsx pptx pdf upload download', run: () => navigate('/documentos') },
    { id: 'engineering', label: 'Abrir workflows de engenharia', group: 'Navegação', icon: Wrench, keywords: 'spec plano testes revisão segurança web vitals adr release', run: () => navigate('/engenharia') },
    { id: 'planning', label: 'Abrir planos persistentes', group: 'Navegação', icon: ListChecks, keywords: 'planejamento recuperação progresso descobertas gate task plan findings', run: () => navigate('/planejamento') },
    { id: 'reverse', label: 'Abrir engenharia reversa', group: 'Navegação', icon: Fingerprint, keywords: 'artefato binario elf pe macho electron javascript strings entropia hash analise reversa', run: () => navigate('/reversa') },
    { id: 'lean', label: 'Abrir engenharia enxuta', group: 'Navegação', icon: Leaf, keywords: 'lean ponytail escada diff divida atalho auditoria enxuto', run: () => navigate('/lean') },
    { id: 'agency', label: 'Abrir governo de agentes', group: 'Navegação', icon: ShieldCheck, keywords: 'agentes equipe orcamento watchdog hierarquia permissao paperclip governanca heartbeat', run: () => navigate('/agencia') },
    { id: 'studio', label: 'Abrir estúdio de design', group: 'Navegação', icon: SwatchBook, keywords: 'design sistema tokens contraste wcag critica artefato clichê open-design studio', run: () => navigate('/estudio') },
    { id: 'skills', label: 'Explorar skills', group: 'Navegação', icon: Blocks, keywords: 'ferramentas modulos', run: () => navigate('/skills') },
  ], [exportBackup, navigate, openTaskModal, runAutomation, startFocus]);

  const filtered = useMemo(() => {
    const normalized = normalizeText(query);
    if (!normalized) return actions;
    return actions.filter((action) => normalizeText(`${action.label} ${action.group} ${action.keywords}`).includes(normalized));
  }, [actions, query]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(0);
      window.setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  useEffect(() => setSelected(0), [query]);

  if (!open) return null;
  const execute = (index: number) => {
    const action = filtered[index];
    if (!action) return;
    onClose();
    action.run();
  };

  return (
    <div className="palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="command-palette" role="dialog" aria-modal="true" aria-label="Paleta de comandos">
        <div className="palette-search">
          <Search size={20} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') onClose();
              if (event.key === 'ArrowDown') { event.preventDefault(); setSelected((value) => Math.min(filtered.length - 1, value + 1)); }
              if (event.key === 'ArrowUp') { event.preventDefault(); setSelected((value) => Math.max(0, value - 1)); }
              if (event.key === 'Enter') execute(selected);
            }}
            placeholder="O que você quer fazer?"
            aria-label="Buscar comando"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="palette-results">
          {filtered.map((action, index) => {
            const Icon = action.icon;
            const showGroup = index === 0 || filtered[index - 1].group !== action.group;
            return (
              <div key={action.id}>
                {showGroup && <div className="palette-group">{action.group}</div>}
                <button className={index === selected ? 'selected' : ''} onMouseEnter={() => setSelected(index)} onClick={() => execute(index)}>
                  <span className="palette-icon"><Icon size={17} /></span>
                  <span>{action.label}</span>
                  <ArrowRight size={15} />
                </button>
              </div>
            );
          })}
          {filtered.length === 0 && <div className="palette-empty">Nenhum comando encontrado. Tente “tarefa”, “foco” ou “memória”.</div>}
        </div>
        <footer className="palette-footer"><span><kbd>↑</kbd><kbd>↓</kbd> navegar</span><span><kbd>↵</kbd> executar</span><span>Dados somente neste dispositivo</span></footer>
      </section>
    </div>
  );
}
