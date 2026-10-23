export interface WorkspaceFile {
  path: string;
  bytes: number;
  modifiedAt: string;
  downloadUrl: string;
}

export interface DocumentReadResult {
  path: string;
  format: string;
  bytes: number;
  text: string;
  downloadUrl: string;
  pages?: number;
  slides?: number;
  sheets?: number;
  paragraphs?: number;
  tables?: number;
  truncated?: boolean;
}

export interface UploadedFile {
  ok: boolean;
  path: string;
  bytes: number;
  downloadUrl: string;
}

export interface ReverseArtifact {
  path: string;
  bytes: number;
  kind: string;
  format: string;
  downloadUrl: string;
}

export interface ReverseArtifactList {
  ok: boolean;
  root: string;
  artifacts: ReverseArtifact[];
  count: number;
  limit: number;
}

export interface SchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  enumLabels?: string[];
  format?: string;
  maxLength?: number;
}

export interface PythonSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  runtime: 'python';
  inputSchema: {
    type: string;
    properties: Record<string, SchemaProperty>;
    required?: string[];
  };
  sideEffects: boolean;
  dryRunSupported: boolean;
  requiresConfirmation: boolean;
}

export function normalizeSkillParameters(skill: PythonSkill, parameters: Record<string, unknown>): Record<string, unknown> {
  const normalized = { ...parameters };
  for (const [name, property] of Object.entries(skill.inputSchema.properties)) {
    if (property.type !== 'integer' && property.type !== 'number') continue;
    const current = normalized[name];
    if (typeof current !== 'string') continue;
    if (!current.trim()) {
      if (property.default !== undefined) normalized[name] = property.default;
      else throw new Error(`Preencha o campo numérico “${property.title ?? name}”.`);
    } else {
      const numeric = Number(current);
      if (!Number.isFinite(numeric)) throw new Error(`Use um número válido em “${property.title ?? name}”.`);
      normalized[name] = numeric;
    }
  }
  return normalized;
}

export interface SkillExecution {
  ok: boolean;
  skill?: string;
  dryRun?: boolean;
  result?: Record<string, unknown>;
  durationMs?: number;
  executedAt?: string;
  error?: { code: string; message: string };
}

export interface LegalDocumentSource {
  id: string;
  title: string;
  shortTitle: string;
  type: string;
  number: string;
  date: string;
  ementa: string;
  situation: string;
  version: string;
  source: string;
  articleCount: number;
  upstreamPath: string;
}

export interface LegalSourcesResult {
  documents: LegalDocumentSource[];
  documentCount: number;
  articleCount: number;
  upstream: { repository: string; commit: string; url: string; description: string };
  notice: string;
}

export interface LegalArticleResult {
  documentId: string;
  documentTitle: string;
  documentShortTitle: string;
  article: string;
  articleNumber: string;
  text: string;
  snippet: string;
  source: string;
  truncated: boolean;
  notice: string;
}

export interface LegalSearchItem extends LegalArticleResult {
  score: number;
}

export interface LegalSearchResult {
  query: string;
  results: LegalSearchItem[];
  resultCount: number;
  returned: number;
  searchedDocuments: number;
  notice: string;
}

export interface AIStatus {
  configured: boolean;
  provider: string;
  model: string | null;
  external: boolean;
}

export interface BackendHealth {
  ok: boolean;
  service: string;
  version: string;
  time: string;
  skills: number;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code = 'API_ERROR') {
    super(message);
    this.name = 'ApiError';
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const isForm = typeof FormData !== 'undefined' && init?.body instanceof FormData;
    response = await fetch(path, {
      ...init,
      headers: isForm ? { ...init?.headers } : { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError('A API Python não está acessível. Verifique se o servidor está em execução.', 0, 'API_OFFLINE');
  }
  const payload = await response.json().catch(() => null) as {
    error?: { code?: string; message?: string };
    detail?: string;
  } | null;
  if (!response.ok) {
    throw new ApiError(
      payload?.error?.message ?? payload?.detail ?? `A API respondeu com HTTP ${response.status}.`,
      response.status,
      payload?.error?.code ?? 'HTTP_ERROR',
    );
  }
  return payload as T;
}

export async function getBackendHealth(): Promise<BackendHealth> {
  return apiFetch<BackendHealth>('/api/health');
}

export async function listPythonSkills(): Promise<PythonSkill[]> {
  const response = await apiFetch<{ ok: boolean; skills: PythonSkill[] }>('/api/skills');
  return response.skills;
}

export async function executePythonSkill(
  skillId: string,
  parameters: Record<string, unknown>,
  options: { dryRun?: boolean; confirmed?: boolean } = {},
): Promise<SkillExecution> {
  return apiFetch<SkillExecution>(`/api/skills/${encodeURIComponent(skillId)}/execute`, {
    method: 'POST',
    body: JSON.stringify({ parameters, dryRun: options.dryRun ?? false, confirmed: options.confirmed ?? false }),
  });
}

export async function uploadUserFile(input: {
  file: File;
  directory: string;
  overwrite: boolean;
  confirmed: boolean;
}): Promise<UploadedFile> {
  const body = new FormData();
  body.append('upload', input.file, input.file.name);
  body.append('directory', input.directory);
  body.append('overwrite', String(input.overwrite));
  body.append('confirmed', String(input.confirmed));
  return apiFetch<UploadedFile>('/api/files/upload', { method: 'POST', body });
}

export async function listReverseArtifacts(): Promise<ReverseArtifactList> {
  return apiFetch<ReverseArtifactList>('/api/reverse/files');
}

export async function uploadReverseArtifact(input: {
  file: File;
  directory: string;
  overwrite: boolean;
  confirmed: boolean;
}): Promise<UploadedFile> {
  const body = new FormData();
  body.append('upload', input.file, input.file.name);
  body.append('directory', input.directory);
  body.append('overwrite', String(input.overwrite));
  body.append('confirmed', String(input.confirmed));
  return apiFetch<UploadedFile>('/api/reverse/upload', { method: 'POST', body });
}

export async function getAIStatus(): Promise<AIStatus> {
  return apiFetch<AIStatus>('/api/ai/status');
}

export async function requestAIChat(input: {
  message: string;
  history: Array<{ role: 'user' | 'jarvis'; content: string }>;
  context?: Record<string, unknown>;
}): Promise<{ ok: boolean; content: string; provider: string; external: boolean }> {
  return apiFetch('/api/ai/chat', { method: 'POST', body: JSON.stringify(input) });
}
