import type { Activity, Automation, ChatMessage, FocusState, MemoryNote, Preferences, Task } from '../types';
import { createId, todayISO } from '../lib/utils';

const now = () => new Date().toISOString();

export function seedTasks(): Task[] {
  return [
    {
      id: createId('task'),
      title: 'Revisar a arquitetura do núcleo',
      project: 'JARVIS',
      priority: 'alta',
      dueDate: todayISO(),
      completed: false,
      createdAt: now(),
    },
    {
      id: createId('task'),
      title: 'Revisar as fontes do corpus de legislação',
      project: 'JARVIS',
      priority: 'media',
      dueDate: todayISO(),
      completed: false,
      createdAt: now(),
    },
    {
      id: createId('task'),
      title: 'Testar os comandos de voz',
      project: 'Pessoal',
      priority: 'baixa',
      dueDate: todayISO(),
      completed: false,
      createdAt: now(),
    },
    {
      id: createId('task'),
      title: 'Verificar o pacote sem importar credenciais',
      project: 'JARVIS',
      priority: 'alta',
      dueDate: todayISO(),
      completed: true,
      completedAt: now(),
      createdAt: now(),
    },
  ];
}

export function seedNotes(): MemoryNote[] {
  return [
    {
      id: createId('note'),
      content: 'O JARVIS deve reunir conversa, memória, tarefas e automações em um único núcleo.',
      tag: 'Visão',
      createdAt: now(),
    },
    {
      id: createId('note'),
      content: 'Ampliar o corpus de legislação somente por sincronização controlada, preservando atribuição e fontes oficiais.',
      tag: 'Arquitetura',
      createdAt: now(),
    },
    {
      id: createId('note'),
      content: 'Chaves, cookies e sessões ficam fora do Git e fora da memória do assistente.',
      tag: 'Segurança',
      createdAt: now(),
    },
  ];
}

export function seedAutomations(): Automation[] {
  return [
    {
      id: 'automation-summary',
      name: 'Resumo do dia',
      description: 'Reúne tarefas pendentes, prioridades e tempo de foco em uma leitura rápida.',
      action: 'summary',
      schedule: { frequency: 'daily', time: '08:00', weekday: 1 },
      enabled: true,
    },
    {
      id: 'automation-organize',
      name: 'Organizar prioridades',
      description: 'Ordena as tarefas abertas por prioridade e prazo, sem excluir nada.',
      action: 'organize',
      schedule: { frequency: 'manual', time: '18:00', weekday: 5 },
      enabled: true,
    },
    {
      id: 'automation-focus',
      name: 'Sessão de foco',
      description: 'Prepara um ciclo de 25 minutos e acompanha o progresso no painel.',
      action: 'focus',
      schedule: { frequency: 'manual', time: '09:00', weekday: 1 },
      enabled: false,
    },
    {
      id: 'automation-backup',
      name: 'Backup da memória',
      description: 'Exporta tarefas, notas, conversas e preferências em um arquivo JSON local.',
      action: 'backup',
      schedule: { frequency: 'weekly', time: '18:00', weekday: 5 },
      enabled: false,
    },
  ];
}

export function seedMessages(name = 'Victor'): ChatMessage[] {
  return [
    {
      id: createId('message'),
      role: 'jarvis',
      content: `Olá, ${name}. O núcleo está pronto. Posso cuidar de tarefas, guardar notas, calcular, consultar legislação, trabalhar com documentos ou pesquisar na web. Por onde começamos?`,
      timestamp: now(),
    },
  ];
}

export function seedActivities(): Activity[] {
  return [
    {
      id: createId('activity'),
      title: 'Núcleo local iniciado',
      detail: 'Skills essenciais disponíveis',
      timestamp: now(),
      kind: 'system',
    },
    {
      id: createId('activity'),
      title: 'Workspace verificado',
      detail: 'Credenciais antigas mantidas fora do projeto',
      timestamp: now(),
      kind: 'system',
    },
  ];
}

export const defaultPreferences: Preferences = {
  name: 'Victor',
  voiceResponse: false,
  voiceRate: 1,
  notifications: false,
  aiEnabled: true,
  shareContextWithAI: false,
  accent: 'mint',
  reduceMotion: false,
};

export function initialFocus(): FocusState {
  return {
    status: 'idle',
    duration: 25 * 60,
    remaining: 25 * 60,
    elapsedToday: 0,
    sessionDate: todayISO(),
  };
}
