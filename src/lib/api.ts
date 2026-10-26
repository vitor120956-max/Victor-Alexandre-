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

export interface PesquisaFonte {
  titulo: string;
  url: string;
  lida: boolean;
}

export interface PesquisaResposta {
  ok: boolean;
  pergunta: string;
  modo: 'ia' | 'sem-ia';
  resposta: string | null;
  fontes: PesquisaFonte[];
  trecho: string;
  avisos: string[];
  limites: string[];
}

export async function requestPesquisa(pergunta: string, autorizacao: string): Promise<{ ok: boolean; result: PesquisaResposta }> {
  return apiFetch('/api/pesquisa/responder', { method: 'POST', body: JSON.stringify({ pergunta, autorizacao }) });
}

export interface AgenteSkill {
  id: string;
  nome: string;
  categoria: string;
  descricao: string;
  local?: boolean;
}

export interface AgenteResultado {
  ok: boolean;
  pedido: string;
  acao: 'executado' | 'faltando' | 'criado' | 'sugerir' | 'web' | 'nada' | 'confirmar' | 'biblioteca';
  skill: AgenteSkill | null;
  confianca: number;
  parametros: Record<string, unknown>;
  faltando: string[];
  resposta: string;
  alternativas: Array<{ id: string; nome: string; confianca: number }>;
  fontes: PesquisaFonte[];
  avisos: string[];
  limites: string[];
}

export interface AgenteReceitas {
  locais: Array<{ id: string; nome: string; descricao: string; receita: string; campo: string; criado_em: string }>;
  receitas: Array<{ id: string; nome: string; descricao: string; exemplo: string; campo: string }>;
}

export async function requestAgenteLocal(
  pedido: string,
  autorizacao: string,
  confirmar = false,
): Promise<AgenteResultado> {
  const resposta = await apiFetch<{ ok: boolean; result: AgenteResultado; error?: { message?: string } }>(
    '/api/agente/executar',
    { method: 'POST', body: JSON.stringify({ pedido, autorizacao, criar: true, consultarWeb: true, confirmar }) },
  );
  if (!resposta.ok || !resposta.result) throw new ApiError(resposta.error?.message ?? 'O agente local recusou o pedido.', 200, 'AGENTE_ERROR');
  return resposta.result;
}

export async function listarSkillsLocais(): Promise<AgenteReceitas> {
  const resposta = await apiFetch<{ ok: boolean; result: AgenteReceitas }>('/api/agente/skills');
  return resposta.result;
}

export interface AgenteApelido {
  pedido: string;
  chave: string;
  skill_id: string;
  origem: string;
  criado_em: string;
}

export interface AgenteFalha {
  id: string;
  pedido: string;
  chave: string;
  motivo: string;
  tentativas: number;
  criado_em: string;
  visto_em: string;
}

export interface AgenteHistorico {
  quando: string;
  pedido: string;
  acao: string;
  skill: string | null;
  confianca: number;
  resumo: string;
}

export interface AgentePainel {
  locais: Array<{ id: string; nome: string; descricao: string; receita: string; campo: string; criado_em: string }>;
  receitas: Array<{ id: string; nome: string; descricao: string; exemplo: string; campo: string }>;
  apelidos: AgenteApelido[];
  fila: AgenteFalha[];
  historico: AgenteHistorico[];
  respostas: Array<{ pedido: string; criado_em: string; fontes: PesquisaFonte[] }>;
}

export async function painelAgente(): Promise<AgentePainel> {
  const resposta = await apiFetch<{ ok: boolean; result: AgentePainel }>('/api/agente/painel');
  return resposta.result;
}

export async function ensinarAgente(pedido: string, alvo: string): Promise<AgenteApelido> {
  const resposta = await apiFetch<{ ok: boolean; result: AgenteApelido; error?: { message?: string } }>(
    '/api/agente/ensinar',
    { method: 'POST', body: JSON.stringify({ pedido, alvo }) },
  );
  if (!resposta.ok || !resposta.result) throw new ApiError(resposta.error?.message ?? 'Não consegui ensinar essa correlação.', 200, 'AGENTE_ERROR');
  return resposta.result;
}

export async function esquecerAgente(pedido: string): Promise<number> {
  const resposta = await apiFetch<{ ok: boolean; result: { removidos: number } }>(
    `/api/agente/apelidos?pedido=${encodeURIComponent(pedido)}`,
    { method: 'DELETE' },
  );
  return resposta.result.removidos;
}

export async function pesquisarAgente(pedido: string, autorizacao: string): Promise<AgenteResultado> {
  const resposta = await apiFetch<{ ok: boolean; result: AgenteResultado }>(
    '/api/agente/pesquisar',
    { method: 'POST', body: JSON.stringify({ pedido, autorizacao }) },
  );
  return resposta.result;
}

export async function removerSkillLocal(skillId: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/agente/skills/${encodeURIComponent(skillId)}`, { method: 'DELETE' });
}

export async function removerFalhaAgente(falhaId: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/agente/fila/${encodeURIComponent(falhaId)}`, { method: 'DELETE' });
}

export async function requestAIChat(input: {
  message: string;
  history: Array<{ role: 'user' | 'jarvis'; content: string }>;
  context?: Record<string, unknown>;
}): Promise<{ ok: boolean; content: string; provider: string; external: boolean }> {
  return apiFetch('/api/ai/chat', { method: 'POST', body: JSON.stringify(input) });
}

// ---------------------------------------------------------------- estação (executor real)

export interface EstacaoChamada {
  id: string;
  tarefa: string;
  ferramenta: string;
  permissao: string;
  decisao: 'allow' | 'ask' | 'deny';
  estado: 'pendente' | 'executando' | 'ok' | 'erro' | 'interrompido' | 'recusado' | 'negado';
  argumentos: Record<string, unknown>;
  resultado: Record<string, unknown>;
  duracao_ms: number;
  criado_em: string;
  atualizado_em: string;
  executou: boolean;
  ignorada?: boolean;
  motivo_ignorada?: string;
}

export interface EstacaoAutomacao {
  nome: string;
  cron: string;
  comando: string;
  minutos: number;
  ativa: boolean;
  proxima: string;
  ultima: string;
  falhas: number;
}

export interface EstacaoEstado {
  raiz: string;
  banco: string;
  politica: Record<string, 'allow' | 'ask' | 'deny'>;
  permissoes: Array<{ nome: string; risco: string; padrao: string; rotulo: string }>;
  ferramentas: Array<{ nome: string; permissao: string; descricao: string; argumentos: string[] }>;
  chamadas: EstacaoChamada[];
  pendentes: EstacaoChamada[];
  automacoes: EstacaoAutomacao[];
  contagem: Record<string, number>;
  versao: string;
  executado: boolean;
}

export async function getEstacaoEstado(): Promise<EstacaoEstado> {
  const resposta = await apiFetch<{ ok: boolean; result: EstacaoEstado }>('/api/estacao/estado');
  return resposta.result;
}

export async function executarEstacao(
  ferramenta: string,
  argumentos: Record<string, unknown>,
  tarefa = '',
): Promise<EstacaoChamada> {
  const resposta = await apiFetch<{ ok: boolean; result: EstacaoChamada; error?: { message?: string } }>(
    '/api/estacao/executar',
    { method: 'POST', body: JSON.stringify({ ferramenta, argumentos, tarefa }) },
  );
  if (!resposta.ok || !resposta.result) throw new ApiError(resposta.error?.message ?? 'O executor recusou a chamada.', 200, 'ESTACAO_ERROR');
  return resposta.result;
}

export async function decidirEstacao(chamadaId: string, aprovado: boolean, nota = ''): Promise<EstacaoChamada> {
  const resposta = await apiFetch<{ ok: boolean; result: EstacaoChamada; error?: { message?: string } }>(
    `/api/estacao/aprovacoes/${encodeURIComponent(chamadaId)}/decidir`,
    { method: 'POST', body: JSON.stringify({ aprovado, nota }) },
  );
  if (!resposta.ok || !resposta.result) throw new ApiError(resposta.error?.message ?? 'A decisão não foi aceita.', 200, 'ESTACAO_ERROR');
  return resposta.result;
}

export async function definirPoliticaEstacao(permissao: string, decisao: string): Promise<Record<string, 'allow' | 'ask' | 'deny'>> {
  const resposta = await apiFetch<{ ok: boolean; result: { politica: Record<string, 'allow' | 'ask' | 'deny'> }; error?: { message?: string } }>(
    '/api/estacao/politica',
    { method: 'PUT', body: JSON.stringify({ permissao, decisao }) },
  );
  if (!resposta.ok) throw new ApiError(resposta.error?.message ?? 'A política não foi aceita.', 200, 'ESTACAO_ERROR');
  return resposta.result.politica;
}

export async function criarAutomacaoEstacao(input: { nome: string; cron: string; comando: string; minutos: number }): Promise<EstacaoChamada> {
  const resposta = await apiFetch<{ ok: boolean; result: EstacaoChamada; error?: { message?: string } }>(
    '/api/estacao/agenda',
    { method: 'POST', body: JSON.stringify(input) },
  );
  if (!resposta.ok || !resposta.result) throw new ApiError(resposta.error?.message ?? 'A agenda recusou a automação.', 200, 'ESTACAO_ERROR');
  return resposta.result;
}

export async function alternarAutomacaoEstacao(nome: string, ativa: boolean): Promise<EstacaoAutomacao> {
  const resposta = await apiFetch<{ ok: boolean; result: EstacaoAutomacao }>(
    `/api/estacao/agenda/${encodeURIComponent(nome)}/alternar?ativa=${ativa}`,
    { method: 'POST' },
  );
  return resposta.result;
}

export async function removerAutomacaoEstacao(nome: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/estacao/agenda/${encodeURIComponent(nome)}`, { method: 'DELETE' });
}

export async function recuperarEstacao(): Promise<{ interrompidas: number; mensagem: string }> {
  const resposta = await apiFetch<{ ok: boolean; result: { interrompidas: number; mensagem: string } }>(
    '/api/estacao/recuperar', { method: 'POST' },
  );
  return resposta.result;
}
