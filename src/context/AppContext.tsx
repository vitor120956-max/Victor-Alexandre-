import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocalStorage } from '../hooks/useLocalStorage';
import { evaluateExpression, formatCalculation } from '../lib/calculator';
import { autorizacaoParaConfirmar } from '../lib/confirmacao';
import { helpText, parseCommand } from '../lib/jarvisEngine';
import { ensinarAgente, esquecerAgente, executePythonSkill, getAIStatus, getBackendHealth, listPythonSkills, listarLembretes, listarSkillsLocais, pesquisarAgente, requestAgenteLocal, requestAIChat, requestPesquisa } from '../lib/api';
import type { AIStatus, PythonSkill, SkillExecution } from '../lib/api';
import { montarRespostaAgente } from '../lib/agenteResposta';
import { formatPythonChatResult } from '../lib/skillResults';
import { createId, downloadJSON, formatDuration, formatTime, normalizeText, todayISO } from '../lib/utils';
import {
  defaultPreferences,
  initialFocus,
  seedActivities,
  seedAutomations,
  seedMessages,
  seedNotes,
  seedTasks,
} from '../data/seed';
import type {
  Activity,
  Automation,
  AutomationAction,
  AutomationSchedule,
  ChatMessage,
  FocusState,
  MemoryNote,
  Preferences,
  Priority,
  Task,
  WorkspaceBackup,
} from '../types';

export interface Toast {
  id: string;
  title: string;
  description?: string;
  tone: 'success' | 'info' | 'warning';
}

export interface NewTask {
  title: string;
  project: string;
  priority: Priority;
  dueDate: string;
}

export interface NewAutomation {
  name: string;
  description: string;
  action: AutomationAction;
  schedule: AutomationSchedule;
}

interface AppContextValue {
  tasks: Task[];
  notes: MemoryNote[];
  automations: Automation[];
  messages: ChatMessage[];
  activities: Activity[];
  preferences: Preferences;
  focus: FocusState;
  toasts: Toast[];
  backendOnline: boolean;
  backendVersion: string | null;
  modoDono: boolean;
  pythonSkills: PythonSkill[];
  aiStatus: AIStatus;
  processing: 'ai' | 'python' | null;
  refreshBackend: () => Promise<boolean>;
  executeSkill: (skillId: string, parameters: Record<string, unknown>, options?: { dryRun?: boolean; confirmed?: boolean }) => Promise<SkillExecution>;
  taskModalOpen: boolean;
  openTaskModal: () => void;
  closeTaskModal: () => void;
  addTask: (input: NewTask) => Task;
  toggleTask: (id: string) => void;
  deleteTask: (id: string) => void;
  addNote: (content: string, tag?: string) => void;
  deleteNote: (id: string) => void;
  hostToken: string;
  sendMessage: (text: string) => void;
  clearMessages: () => void;
  updatePreferences: (patch: Partial<Preferences>) => void;
  toggleAutomation: (id: string) => void;
  createAutomation: (input: NewAutomation) => void;
  deleteAutomation: (id: string) => void;
  runAutomation: (id: string) => void;
  startFocus: (minutes?: number) => void;
  pauseFocus: () => void;
  resumeFocus: () => void;
  stopFocus: () => void;
  exportBackup: () => void;
  resetWorkspace: () => void;
  dismissToast: (id: string) => void;
  pushToast: (title: string, description?: string, tone?: Toast['tone']) => void;
}

/**
 * Endereço que a pessoa abriu no navegador. Interface e API vêm da mesma porta
 * (`iniciar.py --porta 8001`, por exemplo), então fixar 8000 na mensagem daria
 * um endereço que não existe naquela execução.
 */
const enderecoDaApi = (): string =>
  typeof window !== 'undefined' && window.location?.host
    ? window.location.origin
    : 'http://127.0.0.1:8000';

const AppContext = createContext<AppContextValue | null>(null);

const initialAIStatus: AIStatus = { configured: false, provider: 'Não configurado', model: null, external: true };

const actionLabels: Record<AutomationAction, string> = {
  summary: 'Resumo do dia',
  focus: 'Sessão de foco',
  organize: 'Organizar prioridades',
  backup: 'Backup local',
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useLocalStorage<Task[]>('jarvis:tasks:v1', seedTasks);
  const [notes, setNotes] = useLocalStorage<MemoryNote[]>('jarvis:notes:v1', seedNotes);
  const [automations, setAutomations] = useLocalStorage<Automation[]>('jarvis:automations:v1', seedAutomations);
  const [messages, setMessages] = useLocalStorage<ChatMessage[]>('jarvis:messages:v1', () => seedMessages());
  const [activities, setActivities] = useLocalStorage<Activity[]>('jarvis:activities:v1', seedActivities);
  const [preferences, setPreferences] = useLocalStorage<Preferences>('jarvis:preferences:v1', defaultPreferences);
  const [focus, setFocus] = useLocalStorage<FocusState>('jarvis:focus:v1', initialFocus);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [backendVersion, setBackendVersion] = useState<string | null>(null);
  const [modoDono, setModoDono] = useState(false);
  const lembretesMostrados = useRef<Set<string>>(new Set());
  const [pythonSkills, setPythonSkills] = useState<PythonSkill[]>([]);
  const [aiStatus, setAIStatus] = useState<AIStatus>(initialAIStatus);
  const [processing, setProcessing] = useState<'ai' | 'python' | null>(null);
  // Token de host fica só na memória desta aba: não é persistido e não entra no backup.
  const [hostToken, setHostToken] = useState('');
  // Último pedido que o agente não resolveu: é ele que a correção ensina.
  const ultimoFalho = useRef('');
  // Pedido que parou para pedir o "sim": a próxima fala pode ser só a autorização.
  const confirmacaoPendente = useRef<{ pedido: string } | null>(null);
  const completionRef = useRef('');

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((title: string, description?: string, tone: Toast['tone'] = 'success') => {
    const id = createId('toast');
    setToasts((current) => [...current.slice(-2), { id, title, description, tone }]);
    window.setTimeout(() => dismissToast(id), 4500);
  }, [dismissToast]);

  const logActivity = useCallback((title: string, detail: string, kind: Activity['kind']) => {
    const activity: Activity = {
      id: createId('activity'),
      title,
      detail,
      kind,
      timestamp: new Date().toISOString(),
    };
    setActivities((current) => [activity, ...current].slice(0, 50));
  }, [setActivities]);

  const desktopNotification = useCallback((title: string, body: string) => {
    if (!preferences.notifications || typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    new Notification(title, { body });
  }, [preferences.notifications]);

  const speak = useCallback((text: string) => {
    if (!preferences.voiceResponse || typeof speechSynthesis === 'undefined') return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.replace(/[•—]/g, ' '));
    utterance.lang = 'pt-BR';
    utterance.rate = preferences.voiceRate;
    const voices = speechSynthesis.getVoices();
    const portugueseVoice = voices.find((voice) => voice.lang.toLowerCase().startsWith('pt'));
    if (portugueseVoice) utterance.voice = portugueseVoice;
    speechSynthesis.speak(utterance);
  }, [preferences.voiceRate, preferences.voiceResponse]);

  const appendJarvisMessage = useCallback((content: string, source: 'local' | 'python' | 'ai' = 'local') => {
    const message: ChatMessage = {
      id: createId('message'),
      role: 'jarvis',
      content,
      source,
      timestamp: new Date().toISOString(),
    };
    setMessages((current) => [...current, message].slice(-120));
    speak(content);
  }, [setMessages, speak]);

  const refreshBackend = useCallback(async () => {
    // A saúde manda: se /api/health responde, a API está de pé. Antes, um erro
    // só em /api/ai/status (ou no catálogo) marcava a API inteira como offline e
    // o chat recusava tudo, inclusive as skills.
    let health: Awaited<ReturnType<typeof getBackendHealth>> | null = null;
    try {
      health = await getBackendHealth();
    } catch {
      health = null;
    }
    if (!health?.ok) {
      setBackendOnline(false);
      setBackendVersion(null);
      setModoDono(false);
      setPythonSkills([]);
      setAIStatus(initialAIStatus);
      return false;
    }
    setBackendOnline(true);
    setBackendVersion(health.version);
    setModoDono(Boolean(health.confiarLocal));
    const [catalog, ai] = await Promise.allSettled([listPythonSkills(), getAIStatus()]);
    setPythonSkills(catalog.status === 'fulfilled' ? catalog.value : []);
    setAIStatus(ai.status === 'fulfilled' ? ai.value : initialAIStatus);
    return true;
  }, []);

  useEffect(() => {
    let cancelado = false;
    let timer = 0;
    // Com a API de pé, confere a cada 30 s. Caída, tenta a cada 3 s: assim a
    // tela volta sozinha no instante em que a API sobe, sem recarregar a página.
    const ciclo = async () => {
      const online = await refreshBackend();
      if (cancelado) return;
      timer = window.setTimeout(() => void ciclo(), online ? 30000 : 3000);
    };
    void ciclo();
    return () => {
      cancelado = true;
      window.clearTimeout(timer);
    };
  }, [refreshBackend]);

  // Lembretes da agenda: consulta sem gravar nada. O que já foi mostrado fica
  // na memória desta aba (chave id|quando|tipo), então o mesmo compromisso não
  // avisa duas vezes — e reiniciar a API não duplica o aviso.
  useEffect(() => {
    if (!backendOnline) return;
    let cancelado = false;
    const conferir = async () => {
      try {
        const resposta = await listarLembretes(30);
        if (cancelado || !resposta.ok) return;
        for (const lembrete of resposta.lembretes) {
          const chave = `${lembrete.id}|${lembrete.quando}|${lembrete.tipo}`;
          if (lembretesMostrados.current.has(chave)) continue;
          lembretesMostrados.current.add(chave);
          const quando = lembrete.tipo === 'atrasado'
            ? `atrasado há ${lembrete.minutos} min`
            : lembrete.minutos <= 0 ? 'agora' : `em ${lembrete.minutos} min`;
          pushToast(
            lembrete.tipo === 'atrasado' ? 'Compromisso atrasado' : 'Compromisso chegando',
            `${lembrete.titulo} — ${lembrete.texto} (${quando})`,
            lembrete.tipo === 'atrasado' ? 'warning' : 'success',
          );
          appendJarvisMessage(
            `Lembrete: ${lembrete.titulo} — ${lembrete.texto} (${quando}).`,
            'python',
          );
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            try {
              new Notification('JARVIS — agenda', { body: `${lembrete.titulo} — ${quando}` });
            } catch {
              // navegador sem permissão para notificação do sistema: o toast já avisou
            }
          }
        }
      } catch {
        // API fora do ar: silêncio; o próximo ciclo tenta de novo
      }
    };
    void conferir();
    const timer = window.setInterval(() => void conferir(), 45000);
    return () => {
      cancelado = true;
      window.clearInterval(timer);
    };
  }, [appendJarvisMessage, backendOnline, pushToast]);

  const executeSkill = useCallback(async (
    skillId: string,
    parameters: Record<string, unknown>,
    options: { dryRun?: boolean; confirmed?: boolean } = {},
  ): Promise<SkillExecution> => {
    try {
      const response = await executePythonSkill(skillId, parameters, options);
      if (response.ok) {
        logActivity('Skill Python executada', `${skillId}${options.dryRun ? ' · simulação' : ''}`, 'system');
      } else {
        logActivity('Skill Python recusada', response.error?.message ?? skillId, 'system');
      }
      return response;
    } catch (error) {
      logActivity('Falha na API Python', error instanceof Error ? error.message : skillId, 'system');
      throw error;
    }
  }, [logActivity]);

  const addTask = useCallback((input: NewTask): Task => {
    const task: Task = {
      id: createId('task'),
      title: input.title.trim(),
      project: input.project.trim() || 'Pessoal',
      priority: input.priority,
      dueDate: input.dueDate || todayISO(),
      completed: false,
      createdAt: new Date().toISOString(),
    };
    setTasks((current) => [task, ...current]);
    logActivity('Tarefa criada', task.title, 'task');
    return task;
  }, [logActivity, setTasks]);

  const toggleTask = useCallback((id: string) => {
    setTasks((current) => current.map((task) => {
      if (task.id !== id) return task;
      const completed = !task.completed;
      return { ...task, completed, completedAt: completed ? new Date().toISOString() : undefined };
    }));
  }, [setTasks]);

  const deleteTask = useCallback((id: string) => {
    const task = tasks.find((item) => item.id === id);
    setTasks((current) => current.filter((item) => item.id !== id));
    if (task) {
      logActivity('Tarefa removida', task.title, 'task');
      pushToast('Tarefa removida', task.title, 'info');
    }
  }, [logActivity, pushToast, setTasks, tasks]);

  const addNote = useCallback((content: string, tag = 'Anotação') => {
    const clean = content.trim();
    if (!clean) return;
    setNotes((current) => [{
      id: createId('note'),
      content: clean,
      tag: tag.trim() || 'Anotação',
      createdAt: new Date().toISOString(),
    }, ...current]);
    logActivity('Memória adicionada', clean.slice(0, 90), 'memory');
  }, [logActivity, setNotes]);

  const deleteNote = useCallback((id: string) => {
    setNotes((current) => current.filter((note) => note.id !== id));
    pushToast('Nota removida da memória', undefined, 'info');
  }, [pushToast, setNotes]);

  const clearMessages = useCallback(() => {
    setMessages([{
      id: createId('message'),
      role: 'jarvis',
      content: 'Conversa limpa. Suas tarefas e memórias continuam preservadas. O que vamos fazer agora?',
      timestamp: new Date().toISOString(),
    }]);
  }, [setMessages]);

  const startFocus = useCallback((minutes = 25) => {
    const safeMinutes = Math.min(180, Math.max(1, Math.round(minutes)));
    setFocus((current) => ({
      status: 'running',
      duration: safeMinutes * 60,
      remaining: safeMinutes * 60,
      elapsedToday: current.sessionDate === todayISO() ? current.elapsedToday : 0,
      sessionDate: todayISO(),
      lastTick: Date.now(),
      completedAt: undefined,
    }));
    logActivity('Foco iniciado', `Ciclo de ${safeMinutes} minutos`, 'focus');
    pushToast('Sessão de foco iniciada', `${safeMinutes} minutos. Você pode pausar quando precisar.`);
  }, [logActivity, pushToast, setFocus]);

  const pauseFocus = useCallback(() => {
    setFocus((current) => {
      if (current.status !== 'running') return current;
      const now = Date.now();
      const elapsed = Math.max(0, Math.floor((now - (current.lastTick ?? now)) / 1000));
      return {
        ...current,
        status: 'paused',
        remaining: Math.max(0, current.remaining - elapsed),
        elapsedToday: current.elapsedToday + elapsed,
        lastTick: undefined,
      };
    });
  }, [setFocus]);

  const resumeFocus = useCallback(() => {
    setFocus((current) => current.status === 'paused'
      ? { ...current, status: 'running', lastTick: Date.now() }
      : current);
  }, [setFocus]);

  const stopFocus = useCallback(() => {
    setFocus((current) => {
      if (current.status === 'running' && current.lastTick) {
        const elapsed = Math.max(0, Math.floor((Date.now() - current.lastTick) / 1000));
        current = { ...current, elapsedToday: current.elapsedToday + elapsed };
      }
      return {
        ...current,
        status: 'idle',
        remaining: current.duration,
        lastTick: undefined,
        completedAt: undefined,
      };
    });
    logActivity('Foco encerrado', 'O cronômetro foi reiniciado', 'focus');
  }, [logActivity, setFocus]);

  const buildSummary = useCallback(() => {
    const pending = tasks.filter((task) => !task.completed);
    const high = pending.filter((task) => task.priority === 'alta').length;
    const next = pending.slice(0, 3).map((task) => `• ${task.title}`).join('\n');
    return [
      `Você tem ${pending.length} ${pending.length === 1 ? 'tarefa pendente' : 'tarefas pendentes'}, sendo ${high} de alta prioridade.`,
      next ? `Próximas ações:\n${next}` : 'Nenhuma tarefa aberta. Bom momento para planejar o próximo passo.',
      `Tempo em foco hoje: ${formatDuration(focus.elapsedToday)}. Memórias guardadas: ${notes.length}.`,
    ].join('\n\n');
  }, [focus.elapsedToday, notes.length, tasks]);

  const exportBackup = useCallback(() => {
    const backup: WorkspaceBackup = {
      version: 1,
      exportedAt: new Date().toISOString(),
      tasks,
      notes,
      automations,
      messages,
      preferences,
    };
    downloadJSON(`jarvis-backup-${todayISO()}.json`, backup);
    logActivity('Backup exportado', 'Arquivo JSON gerado neste dispositivo', 'system');
    pushToast('Backup preparado', 'O download do arquivo JSON foi solicitado.');
  }, [automations, logActivity, messages, notes, preferences, pushToast, tasks]);

  const runAutomation = useCallback((id: string) => {
    const automation = automations.find((item) => item.id === id);
    if (!automation) {
      pushToast('Automação não encontrada', undefined, 'warning');
      return;
    }

    setAutomations((current) => current.map((item) => item.id === id
      ? { ...item, lastRun: new Date().toISOString() }
      : item));

    if (automation.action === 'summary') {
      setMessages((current) => [...current, {
        id: createId('message'),
        role: 'jarvis',
        content: buildSummary(),
        timestamp: new Date().toISOString(),
      }]);
      pushToast('Resumo do dia atualizado', 'O resultado também está disponível na conversa.');
    } else if (automation.action === 'organize') {
      const weight = { alta: 0, media: 1, baixa: 2 } as const;
      setTasks((current) => [...current].sort((a, b) => {
        if (a.completed !== b.completed) return a.completed ? 1 : -1;
        return weight[a.priority] - weight[b.priority] || a.dueDate.localeCompare(b.dueDate);
      }));
      pushToast('Prioridades organizadas', 'Tarefas abertas foram ordenadas sem excluir nada.');
    } else if (automation.action === 'focus') {
      startFocus(25);
    } else {
      exportBackup();
    }

    logActivity('Automação executada', automation.name, 'automation');
    desktopNotification('JARVIS · Automação', `${automation.name} foi executada.`);
  }, [automations, buildSummary, desktopNotification, exportBackup, logActivity, pushToast, setAutomations, setMessages, setTasks, startFocus]);

  const responderComIA = useCallback((texto: string) => {
    setProcessing('ai');
    const history = messages.slice(-12).map((message) => ({ role: message.role, content: message.content }));
    const context = preferences.shareContextWithAI ? {
      tasks: tasks.slice(0, 20).map((task) => ({ title: task.title, priority: task.priority, dueDate: task.dueDate, completed: task.completed })),
      notes: notes.slice(0, 20).map((note) => ({ content: note.content, tag: note.tag })),
    } : undefined;
    void requestAIChat({ message: texto, history, context })
      .then((response) => appendJarvisMessage(response.content, 'ai'))
      .catch((error: unknown) => appendJarvisMessage(`Não consegui concluir pela IA externa: ${error instanceof Error ? error.message : 'falha desconhecida'}\n\nOs comandos locais continuam disponíveis; diga “ajuda” para ver exemplos.`))
      .finally(() => setProcessing(null));
  }, [appendJarvisMessage, messages, notes, preferences.shareContextWithAI, tasks]);

  const sendMessage = useCallback((rawText: string) => {
    const text = rawText.trim();
    if (!text) return;
    const pendente = confirmacaoPendente.current;
    if (pendente && /^(sim|pode|confirmo|autorizo|vai|manda|beleza|ok)\b/i.test(text)) {
      confirmacaoPendente.current = null;
      setMessages((current) => [
        ...current,
        { id: createId('message'), role: 'user' as const, content: text, timestamp: new Date().toISOString() },
      ].slice(-120));
      setProcessing('python');
      // O texto da confirmação ("sim, pode") NÃO é token (bug da 0.61.9).
      void requestAgenteLocal(pendente.pedido, autorizacaoParaConfirmar(modoDono, hostToken), true)
        .then((resultado) => {
          setProcessing(null);
          appendJarvisMessage(montarRespostaAgente(resultado), 'python');
        })
        .catch((error: unknown) => {
          setProcessing(null);
          appendJarvisMessage(`Não consegui confirmar: ${error instanceof Error ? error.message : 'falha desconhecida'}.`);
        });
      return;
    }
    if (processing) {
      pushToast('Aguarde a resposta atual', 'Uma skill ou a IA externa ainda está processando.', 'info');
      return;
    }
    const intent = parseCommand(text);

    if (intent.type === 'clear') {
      clearMessages();
      return;
    }

    const userMessage: ChatMessage = {
      id: createId('message'),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage].slice(-120));

    if (intent.type === 'unknown') {
      if (backendOnline && aiStatus.configured && preferences.aiEnabled) {
        responderComIA(text);
      } else if (backendOnline) {
        // Sem IA configurada quem responde é o agente local: ele procura a
        // skill, preenche os campos, cria skill de receita ou busca na web.
        setProcessing('python');
        void requestAgenteLocal(text, hostToken)
          .then((resultado) => {
            setProcessing(null);
            if (resultado.acao === 'nada' || resultado.acao === 'sugerir') {
              ultimoFalho.current = text;
            }
            if (resultado.acao === 'confirmar') {
              confirmacaoPendente.current = { pedido: text };
            }
            if (resultado.resposta.trim()) {
              const dica = resultado.acao === 'nada' || resultado.acao === 'sugerir'
                ? '\n\nSe eu errei, diga “não é essa, é a skill <id>” para eu aprender, ou “procure na web sobre isso”.'
                : '';
              appendJarvisMessage(montarRespostaAgente(resultado) + dica, 'python');
            } else {
              appendJarvisMessage('Não achei skill, receita nem web para este pedido. Diga “ajuda” para ver os comandos que funcionam sem modelo.');
            }
          })
          .catch((error: unknown) => {
            setProcessing(null);
            appendJarvisMessage(`O agente local não conseguiu responder: ${error instanceof Error ? error.message : 'falha desconhecida'}\n\nDiga “ajuda” para ver os comandos que funcionam sem modelo.`);
          });
      } else {
        const reason = !backendOnline
          ? `A API Python não respondeu em ${enderecoDaApi()} — nada foi executado.\n\nPara subir, nesta ordem:\n  cd /d D:\\JARVIS\n  .venv\\Scripts\\python iniciar.py\n\nQuando ela voltar, esta tela reconecta sozinha em até 3 segundos: basta repetir o pedido.`
          : !aiStatus.configured
            ? 'A API Python está online, mas a IA externa ainda não foi configurada no servidor.'
            : 'A IA externa está desativada nas suas configurações.';
        appendJarvisMessage(`${reason} Posso continuar com tarefas, notas, cálculos, foco, automações, legislação, documentos, engenharia, planos persistentes, análise reversa, produtividade, pesquisa e skills Python. Diga “ajuda” para ver exemplos.`);
      }
      return;
    }

    if (
      intent.type === 'python:analyze' || intent.type === 'python:status'
      || intent.type === 'legal:search' || intent.type === 'legal:article' || intent.type === 'legal:sources'
      || intent.type === 'document:list' || intent.type === 'document:read' || intent.type === 'files:organize'
      || intent.type === 'engineering:review' || intent.type === 'engineering:webvitals'
      || intent.type === 'planning:list' || intent.type === 'planning:resume' || intent.type === 'planning:gate'
      || intent.type === 'reverse:inspect' || intent.type === 'reverse:strings' || intent.type === 'reverse:entropy'
      || intent.type === 'reverse:analyze' || intent.type === 'reverse:compare'
      || intent.type === 'lean:review' || intent.type === 'lean:audit' || intent.type === 'lean:debt'
      || intent.type === 'meeting:analyze' || intent.type === 'changelog:generate' || intent.type === 'random:pick'
    ) {
      if (!backendOnline) {
        appendJarvisMessage(`A skill Python não está acessível porque a API não respondeu em ${enderecoDaApi()}.\n\nSuba o servidor:\n  cd /d D:\\JARVIS\n  .venv\\Scripts\\python iniciar.py\n\nA tela reconecta sozinha em até 3 segundos depois que ele subir.`);
        return;
      }
      let skillId = 'system.status';
      let parameters: Record<string, unknown> = {};
      switch (intent.type) {
        case 'python:analyze': skillId = 'text.analyze'; parameters = { text: intent.text }; break;
        case 'legal:search': skillId = 'legal.search'; parameters = { query: intent.query, documentId: intent.documentId, limit: 6 }; break;
        case 'legal:article': skillId = 'legal.article'; parameters = { documentId: intent.documentId, article: intent.article }; break;
        case 'legal:sources': skillId = 'legal.sources'; break;
        case 'document:list': skillId = 'files.list'; break;
        case 'document:read': skillId = 'document.read'; parameters = { path: intent.path }; break;
        case 'files:organize': skillId = 'files.organize'; parameters = { path: '' }; break;
        case 'engineering:review': skillId = 'engineering.review'; parameters = { code: intent.code, language: intent.language, changedLines: 0 }; break;
        case 'engineering:webvitals': skillId = 'engineering.webvitals'; parameters = { lcpMs: intent.lcpMs, inpMs: intent.inpMs, cls: intent.cls, source: 'lab', sampleSize: 0 }; break;
        case 'planning:list': skillId = 'planning.list'; break;
        case 'planning:resume': skillId = 'planning.resume'; parameters = { planId: intent.planId }; break;
        case 'planning:gate': skillId = 'planning.gate'; parameters = { planId: intent.planId }; break;
        case 'reverse:inspect': skillId = 'reverse.inspect'; parameters = { path: intent.path }; break;
        case 'reverse:strings': skillId = 'reverse.strings'; parameters = { path: intent.path }; break;
        case 'reverse:entropy': skillId = 'reverse.entropy'; parameters = { path: intent.path }; break;
        case 'reverse:analyze': skillId = 'reverse.javascript'; parameters = { path: intent.path, source: '', includeNodeModules: false, maxFiles: 500 }; break;
        case 'reverse:compare': skillId = 'reverse.compare'; parameters = { left: intent.left, right: intent.right }; break;
        case 'lean:review': skillId = 'lean.review'; parameters = { diff: intent.diff, mode: 'full', notes: '' }; break;
        case 'lean:audit': skillId = 'lean.audit'; parameters = { path: intent.path, mode: 'full', maxFiles: 400 }; break;
        case 'lean:debt': skillId = 'lean.debt'; parameters = { path: intent.path, code: '', marker: 'shortcut', includeLegacy: true }; break;
        case 'meeting:analyze': skillId = 'meeting.analyze'; parameters = { transcript: intent.transcript }; break;
        case 'changelog:generate': skillId = 'changelog.generate'; parameters = { commits: intent.commits, version: intent.version }; break;
        case 'random:pick': skillId = 'random.pick'; parameters = { entries: intent.entries, count: intent.count }; break;
        default: skillId = 'system.status';
      }
      setProcessing('python');
      void executeSkill(skillId, parameters, intent.type === 'files:organize' ? { dryRun: true } : undefined)
        .then((response) => {
          if (response.ok && response.result) appendJarvisMessage(formatPythonChatResult(skillId, response.result), 'python');
          else appendJarvisMessage(`A skill Python recusou o pedido: ${response.error?.message ?? 'erro desconhecido'}`);
        })
        .catch((error: unknown) => appendJarvisMessage(`Não consegui executar a skill Python: ${error instanceof Error ? error.message : 'falha desconhecida'}`))
        .finally(() => setProcessing(null));
      return;
    }

    let reply = '';

    switch (intent.type) {
      case 'help':
        reply = helpText;
        break;
      case 'document:workspace':
        reply = backendOnline
          ? 'Abra a página Documentos para criar DOCX, XLSX, PPTX ou PDF. A interface valida uma simulação e só grava depois da sua confirmação; uploads e downloads também ficam lá.'
          : 'A página Documentos precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nenhum arquivo foi criado.';
        break;
      case 'engineering:workspace':
        reply = backendOnline
          ? 'Abra a página Engenharia para usar especificação, plano vertical, matriz de testes, revisão estática, STRIDE, Web Vitals, ADR e gate de release. Para revisar código pelo chat, informe a linguagem: “revisar código python: <trecho>”. Nenhum workflow executa deploy.'
          : 'Os workflows de Engenharia precisam da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nenhum código foi analisado ou enviado à IA.';
        break;
      case 'planning:workspace':
        reply = backendOnline
          ? 'Abra a página Planos para criar ou atualizar um plano persistente. Toda gravação passa por simulação e confirmação. Para recuperar sem escolher ambiguidades, use “retomar plano ID”; para listar os IDs, use “listar planos”.'
          : 'Os planos persistentes precisam da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nenhum arquivo foi criado ou lido.';
        break;
      case 'reverse:workspace':
        reply = backendOnline
          ? 'Abra a página Reversa para enviar um artefato e executar inspeção, layout, strings, entropia, análise JavaScript/Electron ou comparação. Tudo é estático: parsers próprios em Python, sem shell, rede, MCP ou execução do alvo. Pelo chat, use “inspecionar artefato app/main.js”, “strings de app.asar”, “entropia de firmware.bin”, “analisar javascript app” ou “comparar artefatos a.bin e b.bin”.'
          : 'A análise reversa precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nenhum artefato foi lido, executado ou enviado à IA.';
        break;
      case 'lean:workspace':
        reply = backendOnline
          ? 'Abra a página Enxuto para aplicar a escada, revisar um diff, levantar dívida de atalhos ou auditar uma árvore de código. Tudo é estático e nada é executado. Pelo chat, use “revisar mudança: <diff>”, “auditar código app” ou “dívida de atalhos em app”. O código analisado fica na área da página Reversa.'
          : 'A engenharia enxuta precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado ou enviado à IA.';
        break;
      case 'agency:workspace':
        reply = backendOnline
          ? 'Abra a página Agentes para revisar a equipe declarada, o quadro, o orçamento, a parada de trabalho e as permissões. A análise é estática: nada é executado, agendado ou conectado a um agente real. O watchdog calcula uma impressão digital da subárvore parada e suprime a revisão quando o hash não muda.'
          : 'O governo de agentes precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.';
        break;
      case 'studio:workspace':
        reply = backendOnline
          ? 'Abra a página Estúdio para revisar um pacote de design: manifesto, DESIGN.md e tokens.css, contraste WCAG, crítica em cinco dimensões e o linter anti-clichê do HTML. Nada é compilado, renderizado ou publicado, e nenhum daemon ou plugin do upstream é instalado.'
          : 'O estúdio de design precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.';
        break;
      case 'diagram:workspace':
        reply = backendOnline
          ? 'Abra a página Diagramas para escolher o tipo pelo pedido, validar o IR em JSON, medir o layout, gerar HTML autocontido com SVG e conferir o contrato de entrega em gates. Tudo é estático: nenhum CLI, template, plugin ou captura do upstream é usado.'
          : 'Os diagramas precisam da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi desenhado.';
        break;
      case 'browser:workspace':
        reply = backendOnline
          ? 'Abra a página Navegador para ler o snapshot, resolver o alvo, montar o roteiro de rodadas, checar o plano, ler os recibos e classificar os limites. Tudo é estático: nada de app, binário ou skill do upstream; nenhum navegador é aberto.'
          : 'O navegador assistido precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.';
        break;
      case 'office:workspace':
        reply = backendOnline
          ? 'Abra a página Escritório para montar o comando `gws`, planejar receitas, ler páginas, dividir lotes, comparar escopos e triar erros. Tudo é estático: o CLI não é instalado, nenhuma credencial é lida e nada é enviado ao Google.'
          : 'O escritório assistido precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi calculado.';
        break;
      case 'career:workspace':
        reply = backendOnline
          ? 'Abra a página Carreira para triar a vaga com nota 1–5 e evidência declarada, checar o ATS, auditar bullets, rascunhar a carta, planejar a entrevista e ler o funil. Tudo é estático: nada de portal, candidatura, PDF ou plugin do upstream.'
          : 'A triagem de carreira precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.';
        break;
      case 'estacao:workspace':
        reply = backendOnline
          ? 'Abra a página Estação para rodar comandos de verdade no diretório dela, decidir a fila de aprovação, auditar a execução e a recuperação após queda, checar a agenda e higienizar notas e skills. O executor é local; a VM e o navegador do upstream não existem aqui.'
          : 'A estação do agente precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi calculado.';
        break;
      case 'taste:workspace':
        reply = backendOnline
          ? 'Abra a página Direção para sortear três direções, auditar o argumento e o deck de copy, varrer as regras caseiras, confrontar o registro datado de tells e fechar a nota com tetos. Tudo é estático: nenhum script Node, navegador ou plugin do upstream é executado.'
          : 'A direção de arte precisa da API Python online. Suba a API com .venv\Scripts\python iniciar.py; nada foi analisado.';
        break;
      case 'greeting':
        reply = `Olá, ${preferences.name}. Estou por aqui. Você pode me pedir uma tarefa, uma anotação, um cálculo ou dizer “ajuda”.`;
        break;
      case 'thanks':
        reply = 'Por nada. Pode contar comigo para o próximo passo.';
        break;
      case 'identity':
        reply = 'Sou o JARVIS deste núcleo pessoal. Uso skills locais, Python e, quando configurada, uma IA externa. Cada resposta identifica sua origem e ações externas dependem do seu comando.';
        break;
      case 'time':
        reply = `Agora são ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}.`;
        break;
      case 'date':
        reply = `Hoje é ${new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}.`;
        break;
      case 'status': {
        const pending = tasks.filter((task) => !task.completed).length;
        const runningAutomations = automations.filter((automation) => automation.enabled).length;
        reply = `Núcleo operacional. ${pending} tarefas pendentes, ${notes.length} memórias, ${runningAutomations} automações ativas e foco em ${formatTime(focus.remaining)}. API Python ${backendOnline ? `online com ${pythonSkills.length} skills` : 'offline'}; IA externa ${aiStatus.configured && preferences.aiEnabled ? `configurada via ${aiStatus.provider}` : 'não ativa'}.`;
        break;
      }
      case 'calculate':
        try {
          reply = `${intent.expression} = ${formatCalculation(evaluateExpression(intent.expression))}`;
        } catch (error) {
          reply = `Não consegui calcular: ${error instanceof Error ? error.message : 'expressão inválida'}`;
        }
        break;
      case 'task:add':
        addTask({ title: intent.title, project: 'JARVIS', priority: intent.priority, dueDate: intent.dueDate });
        reply = `Tarefa criada: “${intent.title}”. Prioridade ${intent.priority}${intent.dueDate === todayISO() ? ', para hoje' : ', para amanhã'}.`;
        pushToast('Tarefa criada pelo JARVIS', intent.title);
        break;
      case 'task:list': {
        const pending = tasks.filter((task) => !task.completed);
        reply = pending.length
          ? `Encontrei ${pending.length} ${pending.length === 1 ? 'tarefa pendente' : 'tarefas pendentes'}:\n${pending.slice(0, 6).map((task) => `• ${task.title} (${task.priority})`).join('\n')}`
          : 'Sua lista está em dia. Não há tarefas pendentes.';
        break;
      }
      case 'task:complete': {
        const query = normalizeText(intent.query);
        const task = tasks.find((item) => !item.completed && normalizeText(item.title).includes(query));
        if (task) {
          toggleTask(task.id);
          reply = `Concluí “${task.title}”. Uma coisa a menos na sua lista.`;
          pushToast('Tarefa concluída', task.title);
        } else {
          reply = `Não encontrei uma tarefa pendente com “${intent.query}”. Diga “mostrar tarefas” para conferir os títulos.`;
        }
        break;
      }
      case 'note:add':
        addNote(intent.content, 'Via conversa');
        reply = 'Anotei na sua memória local. Você pode encontrar essa nota na seção Memória.';
        pushToast('Memória atualizada', intent.content.slice(0, 80));
        break;
      case 'note:list':
        reply = notes.length
          ? `Estas são suas notas mais recentes:\n${notes.slice(0, 4).map((note) => `• ${note.content}`).join('\n')}`
          : 'Sua memória está vazia. Diga “anotar” seguido do que você quer guardar.';
        break;
      case 'focus:start':
        startFocus(intent.minutes);
        reply = `Sessão de ${intent.minutes} minutos iniciada. Vou acompanhar o tempo no painel; diga “pausar foco” se precisar.`;
        break;
      case 'focus:pause':
        if (focus.status === 'running') {
          pauseFocus();
          reply = 'Foco pausado. O tempo restante está preservado; diga “retomar foco” para continuar.';
        } else reply = 'Não há uma sessão de foco em andamento para pausar.';
        break;
      case 'focus:resume':
        if (focus.status === 'paused') {
          resumeFocus();
          reply = `Foco retomado com ${formatTime(focus.remaining)} restantes.`;
        } else reply = 'Não há uma sessão pausada. Diga “iniciar foco de 25 minutos” para começar.';
        break;
      case 'focus:stop':
        stopFocus();
        reply = 'Sessão encerrada e cronômetro reiniciado. O tempo já realizado continua no total de hoje.';
        break;
      case 'focus:status':
        reply = focus.status === 'idle'
          ? `Nenhuma sessão ativa. Hoje você acumulou ${formatDuration(focus.elapsedToday)} de foco.`
          : `O foco está ${focus.status === 'running' ? 'em andamento' : focus.status === 'paused' ? 'pausado' : 'concluído'}, com ${formatTime(focus.remaining)} restantes. Total de hoje: ${formatDuration(focus.elapsedToday)}.`;
        break;
      case 'host:token': {
        setHostToken(intent.token);
        reply = 'Token de host guardado apenas nesta aba. Ele não é salvo no navegador nem no backup. Ele só é exigido para baixar, importar, instalar e executar — pesquisar na web não pede mais token.';
        break;
      }
      case 'pesquisa:responder': {
        // Buscar e ler página não pede token desde a 0.49.0: quem grava é que pede.
        setProcessing('python');
        void requestPesquisa(intent.pergunta, hostToken ?? '', intent.fonte)
          .then(({ result }) => {
            const fontes = result.fontes
              .map((fonte, indice) => `${indice + 1}. ${fonte.fonte ? `[${fonte.fonte}] ` : ''}${fonte.titulo || fonte.url} — ${fonte.url}${fonte.lida ? ' (lida)' : ''}`)
              .join('\n');
            if (result.modo === 'ia' && result.resposta) {
              appendJarvisMessage([result.resposta, '', 'Fontes:', fontes].join('\n'), 'ai');
            } else {
              const cabeca = `Encontrei ${result.fontes.length} fonte(s), mas a IA não está configurada para redigir. O texto abaixo é o que foi lido da página, sem resumo:`;
              const trecho = result.trecho ? `\n\n“${result.trecho.slice(0, 900)}…”` : '';
              appendJarvisMessage([cabeca, '', fontes, trecho].join('\n'), 'python');
            }
            if (result.avisos.length) appendJarvisMessage(`Avisos: ${result.avisos.join(' · ')}`);
          })
          .catch((error: unknown) => {
            const detalhe = error instanceof Error ? error.message : 'falha desconhecida';
            appendJarvisMessage(`Não consegui pesquisar: ${detalhe}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'agente:skills': {
        if (!backendOnline) {
          reply = 'A API Python está offline, então não consigo listar as skills locais.';
          break;
        }
        setProcessing('python');
        void listarSkillsLocais()
          .then((dados) => {
            if (!dados.locais.length) {
              const exemplos = dados.receitas.slice(0, 6).map((receita) => `“${receita.exemplo}”`).join(', ');
              appendJarvisMessage(
                `Ainda não criei nenhuma skill local. Consigo montar ${dados.receitas.length} receitas prontas. Experimente: ${exemplos}.`,
                'python',
              );
              return;
            }
            const linhas = dados.locais.map((skill) => `- ${skill.nome} (${skill.id}) — ${skill.descricao}`).join('\n');
            appendJarvisMessage(`Skills locais já criadas:\n${linhas}`, 'python');
          })
          .catch((error: unknown) => {
            appendJarvisMessage(`Não consegui listar as skills locais: ${error instanceof Error ? error.message : 'falha desconhecida'}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'agente:executar': {
        if (!backendOnline) {
          reply = 'A API Python está offline, então o agente local não pode procurar nas skills.';
          break;
        }
        setProcessing('python');
        void requestAgenteLocal(intent.pedido, hostToken)
          .then((resultado) => appendJarvisMessage(montarRespostaAgente(resultado), 'python'))
          .catch((error: unknown) => {
            appendJarvisMessage(`O agente local não conseguiu responder: ${error instanceof Error ? error.message : 'falha desconhecida'}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'agente:corrigir': {
        const pedidoFalho = ultimoFalho.current;
        if (!pedidoFalho) {
          reply = 'Ainda não tenho um pedido para corrigir. Faça o pedido primeiro; depois diga “não é essa, é a skill …”.';
          break;
        }
        if (!backendOnline) {
          reply = 'A API Python está offline, então não consigo guardar a correlação agora.';
          break;
        }
        setProcessing('python');
        void ensinarAgente(pedidoFalho, intent.alvo)
          .then((registro) => {
            ultimoFalho.current = '';
            appendJarvisMessage(`Aprendi: quando você pedir “${registro.pedido}”, uso ${registro.skill_id}.`, 'python');
          })
          .catch((error: unknown) => {
            appendJarvisMessage(`Não consegui ensinar: ${error instanceof Error ? error.message : 'falha desconhecida'}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'agente:pesquisar': {
        const pedidoFalho = ultimoFalho.current;
        if (!pedidoFalho) {
          reply = 'Não tenho um pedido pendente. Diga o que devo procurar, por exemplo “procure na web: quem inventou o pão” — ou use “pesquisar e responder …”.';
          break;
        }
        setProcessing('python');
        void pesquisarAgente(pedidoFalho, hostToken ?? '')
          .then((resultado) => {
            if (resultado.acao === 'web') {
              ultimoFalho.current = '';
              appendJarvisMessage(`${resultado.resposta}\n\nGuardei esta resposta: o mesmo pedido passa a responder da memória.`, 'python');
            } else {
              appendJarvisMessage(resultado.resposta || 'A busca não trouxe nada.', 'python');
            }
          })
          .catch((error: unknown) => {
            appendJarvisMessage(`A busca falhou: ${error instanceof Error ? error.message : 'falha desconhecida'}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'agente:esquecer': {
        if (!backendOnline) {
          reply = 'A API Python está offline, então não consigo esquecer nada agora.';
          break;
        }
        setProcessing('python');
        void esquecerAgente(intent.pedido)
          .then((removidos) => {
            appendJarvisMessage(
              removidos
                ? `Esqueci ${removidos} registro(s) de “${intent.pedido}”.`
                : `Não tinha nada guardado para “${intent.pedido}”.`,
              'python',
            );
          })
          .catch((error: unknown) => {
            appendJarvisMessage(`Não consegui esquecer: ${error instanceof Error ? error.message : 'falha desconhecida'}`);
          })
          .finally(() => setProcessing(null));
        return;
      }
      case 'web:search': {
        const url = `https://www.google.com/search?q=${encodeURIComponent(intent.query)}`;
        const opened = window.open(url, '_blank');
        if (opened) opened.opener = null;
        reply = opened
          ? `Abri uma pesquisa por “${intent.query}” em uma nova aba.`
          : 'O navegador bloqueou a nova aba. Libere pop-ups para este site e tente novamente.';
        break;
      }
      case 'web:open': {
        const opened = window.open(intent.url, '_blank');
        if (opened) opened.opener = null;
        reply = opened
          ? `${intent.destination} aberto em uma nova aba.`
          : `O navegador bloqueou a abertura do ${intent.destination}. Libere pop-ups e tente novamente.`;
        break;
      }
      case 'automation:summary':
        reply = buildSummary();
        logActivity('Resumo solicitado', 'Gerado por comando na conversa', 'automation');
        break;
      case 'automation:organize': {
        const weight = { alta: 0, media: 1, baixa: 2 } as const;
        setTasks((current) => [...current].sort((a, b) => Number(a.completed) - Number(b.completed)
          || weight[a.priority] - weight[b.priority]
          || a.dueDate.localeCompare(b.dueDate)));
        reply = 'Organizei as tarefas: pendentes primeiro, depois por prioridade e prazo. Nada foi excluído.';
        logActivity('Prioridades organizadas', 'Ação solicitada na conversa', 'automation');
        break;
      }
      case 'automation:backup':
        exportBackup();
        reply = 'Preparei o backup local em JSON. Ele contém tarefas, notas, automações, conversas e preferências.';
        break;
      case 'voice:toggle': {
        const enable = /^(?:ativar|ligar)/i.test(normalizeText(text));
        setPreferences((current) => ({ ...current, voiceResponse: enable }));
        reply = enable ? 'Respostas por voz ativadas.' : 'Respostas por voz desativadas. Continuarei respondendo por texto.';
        break;
      }
      default:
        reply = 'Não consegui direcionar esse pedido. Diga “ajuda” para ver os comandos disponíveis.';
        break;
    }

    appendJarvisMessage(reply);
  }, [addNote, addTask, aiStatus.configured, aiStatus.provider, appendJarvisMessage, automations, backendOnline, buildSummary, clearMessages, executeSkill, exportBackup, focus, hostToken, modoDono, logActivity, messages, notes, pauseFocus, preferences.aiEnabled, preferences.name, preferences.shareContextWithAI, processing, pushToast, pythonSkills.length, responderComIA, resumeFocus, setPreferences, setTasks, startFocus, stopFocus, tasks, toggleTask]);

  const updatePreferences = useCallback((patch: Partial<Preferences>) => {
    if (patch.notifications && typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
      if (Notification.permission === 'denied') {
        pushToast('Notificações bloqueadas', 'Libere a permissão nas configurações do navegador.', 'warning');
        patch = { ...patch, notifications: false };
      } else {
        Notification.requestPermission().then((permission) => {
          if (permission === 'granted') {
            setPreferences((current) => ({ ...current, notifications: true }));
            pushToast('Notificações ativadas');
          } else {
            setPreferences((current) => ({ ...current, notifications: false }));
          }
        });
      }
    }
    setPreferences((current) => ({ ...current, ...patch }));
  }, [pushToast, setPreferences]);

  const toggleAutomation = useCallback((id: string) => {
    setAutomations((current) => current.map((automation) => automation.id === id
      ? { ...automation, enabled: !automation.enabled }
      : automation));
  }, [setAutomations]);

  const createAutomation = useCallback((input: NewAutomation) => {
    const automation: Automation = {
      id: createId('automation'),
      name: input.name.trim(),
      description: input.description.trim() || `${actionLabels[input.action]} sob demanda.`,
      action: input.action,
      schedule: input.schedule,
      enabled: input.schedule.frequency !== 'manual',
      custom: true,
    };
    setAutomations((current) => [...current, automation]);
    logActivity('Automação criada', automation.name, 'automation');
    pushToast('Automação criada', automation.name);
  }, [logActivity, pushToast, setAutomations]);

  const deleteAutomation = useCallback((id: string) => {
    const automation = automations.find((item) => item.id === id);
    if (!automation?.custom) return;
    setAutomations((current) => current.filter((item) => item.id !== id));
    pushToast('Automação personalizada removida', automation.name, 'info');
  }, [automations, pushToast, setAutomations]);

  const resetWorkspace = useCallback(() => {
    setTasks(seedTasks());
    setNotes(seedNotes());
    setAutomations(seedAutomations());
    setMessages(seedMessages(defaultPreferences.name));
    setActivities(seedActivities());
    setPreferences(defaultPreferences);
    setFocus(initialFocus());
    pushToast('Núcleo restaurado', 'Os dados de exemplo foram recriados.', 'info');
  }, [pushToast, setActivities, setAutomations, setFocus, setMessages, setNotes, setPreferences, setTasks]);

  useEffect(() => {
    setPreferences((current) => current.aiEnabled === undefined || current.shareContextWithAI === undefined
      ? { ...defaultPreferences, ...current }
      : current);
  }, [setPreferences]);

  useEffect(() => {
    document.documentElement.dataset.accent = preferences.accent;
    document.documentElement.classList.toggle('reduce-motion', preferences.reduceMotion);
  }, [preferences.accent, preferences.reduceMotion]);

  useEffect(() => {
    if (focus.sessionDate !== todayISO()) {
      setFocus((current) => ({ ...current, elapsedToday: 0, sessionDate: todayISO() }));
    }
  }, [focus.sessionDate, setFocus]);

  useEffect(() => {
    if (focus.status !== 'running') return;
    const timer = window.setInterval(() => {
      setFocus((current) => {
        if (current.status !== 'running') return current;
        const now = Date.now();
        const elapsed = Math.max(1, Math.floor((now - (current.lastTick ?? now)) / 1000));
        const remaining = Math.max(0, current.remaining - elapsed);
        const sameDay = current.sessionDate === todayISO();
        return {
          ...current,
          status: remaining === 0 ? 'completed' : 'running',
          remaining,
          elapsedToday: (sameDay ? current.elapsedToday : 0) + elapsed,
          sessionDate: todayISO(),
          lastTick: remaining === 0 ? undefined : now,
          completedAt: remaining === 0 ? new Date().toISOString() : undefined,
        };
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [focus.status, setFocus]);

  useEffect(() => {
    if (focus.status !== 'completed' || !focus.completedAt || completionRef.current === focus.completedAt) return;
    completionRef.current = focus.completedAt;
    pushToast('Sessão de foco concluída', 'Respire, alongue-se e escolha o próximo passo.');
    logActivity('Foco concluído', `${Math.round(focus.duration / 60)} minutos realizados`, 'focus');
    desktopNotification('JARVIS · Foco concluído', 'Sua sessão terminou. Hora de fazer uma pausa.');
  }, [desktopNotification, focus.completedAt, focus.duration, focus.status, logActivity, pushToast]);

  const automationsRef = useRef(automations);
  const runAutomationRef = useRef(runAutomation);
  useEffect(() => { automationsRef.current = automations; }, [automations]);
  useEffect(() => { runAutomationRef.current = runAutomation; }, [runAutomation]);

  useEffect(() => {
    const checkSchedule = () => {
      const now = new Date();
      const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      automationsRef.current.forEach((automation) => {
        if (!automation.enabled || automation.schedule.frequency === 'manual') return;
        if (automation.schedule.time !== currentTime) return;
        if (automation.schedule.frequency === 'weekly' && automation.schedule.weekday !== now.getDay()) return;
        if (automation.lastRun?.slice(0, 10) === todayISO()) return;
        runAutomationRef.current(automation.id);
      });
    };
    checkSchedule();
    const timer = window.setInterval(checkSchedule, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const value: AppContextValue = {
    tasks,
    notes,
    automations,
    messages,
    activities,
    preferences,
    focus,
    toasts,
    backendOnline,
    backendVersion,
    modoDono,
    pythonSkills,
    aiStatus,
    processing,
    refreshBackend,
    executeSkill,
    taskModalOpen,
    openTaskModal: () => setTaskModalOpen(true),
    closeTaskModal: () => setTaskModalOpen(false),
    addTask,
    toggleTask,
    deleteTask,
    addNote,
    deleteNote,
    hostToken,
    sendMessage,
    clearMessages,
    updatePreferences,
    toggleAutomation,
    createAutomation,
    deleteAutomation,
    runAutomation,
    startFocus,
    pauseFocus,
    resumeFocus,
    stopFocus,
    exportBackup,
    resetWorkspace,
    dismissToast,
    pushToast,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp deve ser usado dentro de AppProvider.');
  return context;
}
