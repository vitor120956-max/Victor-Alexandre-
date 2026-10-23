export type Priority = 'alta' | 'media' | 'baixa';

export interface Task {
  id: string;
  title: string;
  project: string;
  priority: Priority;
  dueDate: string;
  completed: boolean;
  createdAt: string;
  completedAt?: string;
}

export interface MemoryNote {
  id: string;
  content: string;
  tag: string;
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'jarvis';
  content: string;
  timestamp: string;
  source?: 'local' | 'python' | 'ai';
}

export type AutomationAction = 'summary' | 'focus' | 'organize' | 'backup';
export type AutomationFrequency = 'manual' | 'daily' | 'weekly';

export interface AutomationSchedule {
  frequency: AutomationFrequency;
  time: string;
  weekday: number;
}

export interface Automation {
  id: string;
  name: string;
  description: string;
  action: AutomationAction;
  schedule: AutomationSchedule;
  enabled: boolean;
  lastRun?: string;
  custom?: boolean;
}

export interface Activity {
  id: string;
  title: string;
  detail: string;
  timestamp: string;
  kind: 'system' | 'task' | 'memory' | 'automation' | 'focus';
}

export interface Preferences {
  name: string;
  voiceResponse: boolean;
  voiceRate: number;
  notifications: boolean;
  aiEnabled: boolean;
  shareContextWithAI: boolean;
  accent: 'mint' | 'cyan' | 'amber';
  reduceMotion: boolean;
}

export interface FocusState {
  status: 'idle' | 'running' | 'paused' | 'completed';
  duration: number;
  remaining: number;
  elapsedToday: number;
  lastTick?: number;
  sessionDate: string;
  completedAt?: string;
}

export interface WorkspaceBackup {
  version: 1;
  exportedAt: string;
  tasks: Task[];
  notes: MemoryNote[];
  automations: Automation[];
  messages: ChatMessage[];
  preferences: Preferences;
}
