import type { Priority } from '../types';
import { normalizeText, todayISO } from './utils';

export type Intent =
  | { type: 'help' }
  | { type: 'greeting' }
  | { type: 'thanks' }
  | { type: 'identity' }
  | { type: 'time' }
  | { type: 'date' }
  | { type: 'status' }
  | { type: 'clear' }
  | { type: 'calculate'; expression: string }
  | { type: 'task:add'; title: string; priority: Priority; dueDate: string }
  | { type: 'task:list' }
  | { type: 'task:complete'; query: string }
  | { type: 'note:add'; content: string }
  | { type: 'note:list' }
  | { type: 'focus:start'; minutes: number }
  | { type: 'focus:pause' }
  | { type: 'focus:resume' }
  | { type: 'focus:stop' }
  | { type: 'focus:status' }
  | { type: 'web:search'; query: string }
  | { type: 'web:open'; destination: string; url: string }
  | { type: 'automation:summary' }
  | { type: 'automation:organize' }
  | { type: 'automation:backup' }
  | { type: 'voice:toggle' }
  | { type: 'python:analyze'; text: string }
  | { type: 'python:status' }
  | { type: 'legal:search'; query: string; documentId: string }
  | { type: 'legal:article'; documentId: string; article: string }
  | { type: 'legal:sources' }
  | { type: 'document:list' }
  | { type: 'document:read'; path: string }
  | { type: 'document:workspace' }
  | { type: 'files:organize' }
  | { type: 'engineering:workspace' }
  | { type: 'engineering:review'; code: string; language: string }
  | { type: 'engineering:webvitals'; lcpMs: number; inpMs: number; cls: number }
  | { type: 'planning:list' }
  | { type: 'planning:resume'; planId: string }
  | { type: 'planning:gate'; planId: string }
  | { type: 'planning:workspace' }
  | { type: 'reverse:inspect'; path: string }
  | { type: 'reverse:strings'; path: string }
  | { type: 'reverse:entropy'; path: string }
  | { type: 'reverse:analyze'; path: string }
  | { type: 'reverse:compare'; left: string; right: string }
  | { type: 'reverse:workspace' }
  | { type: 'lean:review'; diff: string }
  | { type: 'lean:audit'; path: string }
  | { type: 'lean:debt'; path: string }
  | { type: 'lean:workspace' }
  | { type: 'agency:workspace' }
  | { type: 'studio:workspace' }
  | { type: 'taste:workspace' }
  | { type: 'diagram:workspace' }
  | { type: 'meeting:analyze'; transcript: string }
  | { type: 'changelog:generate'; commits: string; version: string }
  | { type: 'random:pick'; entries: string; count: number }
  | { type: 'unknown' };

const legalDocumentAliases: Record<string, string> = {
  constituicao: 'constituicao',
  'constituicao federal': 'constituicao',
  cf: 'constituicao',
  'codigo civil': 'codigo-civil',
  civil: 'codigo-civil',
  'lei 10406': 'codigo-civil',
  'lei 10 406': 'codigo-civil',
  'codigo penal': 'codigo-penal',
  penal: 'codigo-penal',
  'lei 2848': 'codigo-penal',
  clt: 'clt',
  'consolidacao das leis do trabalho': 'clt',
  'lei 5452': 'clt',
  eca: 'eca',
  'estatuto da crianca': 'eca',
  'estatuto da crianca e do adolescente': 'eca',
  'estatuto da crianca e adolescente': 'eca',
  'lei 8069': 'eca',
  cdc: 'cdc',
  'codigo de defesa do consumidor': 'cdc',
  'defesa do consumidor': 'cdc',
  'lei 8078': 'cdc',
  lgpd: 'lgpd',
  'lei geral de protecao de dados': 'lgpd',
  'lei geral de protecao de dados pessoais': 'lgpd',
  'lei 13709': 'lgpd',
  'marco civil': 'marco-civil',
  'marco civil da internet': 'marco-civil',
  'lei 12965': 'marco-civil',
};

function resolveLegalDocument(value: string): string | null {
  const normalized = normalizeText(value).replace(/[^a-z0-9]+/g, ' ').trim();
  return legalDocumentAliases[normalized] ?? null;
}

const destinations: Record<string, { label: string; url: string }> = {
  github: { label: 'GitHub', url: 'https://github.com' },
  youtube: { label: 'YouTube', url: 'https://www.youtube.com' },
  google: { label: 'Google', url: 'https://www.google.com' },
  gmail: { label: 'Gmail', url: 'https://mail.google.com' },
  drive: { label: 'Google Drive', url: 'https://drive.google.com' },
  notion: { label: 'Notion', url: 'https://www.notion.so' },
};

function tomorrowISO(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function cleanTaskTitle(value: string): string {
  return value
    .replace(/[.!?]+$/g, '')
    .replace(/\s+(?:para\s+)?amanh[ãa](?=\s|$|[,.!?])/gi, '')
    .replace(/\s+(?:com\s+)?prioridade\s+(?:alta|m[ée]dia|baixa)\b/gi, '')
    .replace(/\s+(?:é\s+)?urgente\b/gi, '')
    .trim();
}

export function parseCommand(rawInput: string): Intent {
  const raw = rawInput.trim();
  const input = raw.replace(/\s+/g, ' ');
  const text = normalizeText(input);
  if (!input) return { type: 'unknown' };

  if (/^(?:ajuda|comandos|o que voce pode fazer\??|o que voce faz\??|me ajuda)$/.test(text)) {
    return { type: 'help' };
  }
  if (/^(?:oi|ola|eae|hey|bom dia|boa tarde|boa noite)[!.\s]*$/.test(text)) return { type: 'greeting' };
  if (/^(?:obrigado|obrigada|valeu|brigado|muito obrigado)[!.\s]*$/.test(text)) return { type: 'thanks' };
  if (/^(?:quem e voce|o que e voce|seu nome)\??$/.test(text)) return { type: 'identity' };

  if (/^(?:limpar|apagar|limpe|apague)(?: a| o)? (?:conversa|chat|historico)$/.test(text)) {
    return { type: 'clear' };
  }
  if (/^(?:ativar|desativar|ligar|desligar)(?: a| o)? (?:voz|resposta por voz)$/.test(text)) {
    return { type: 'voice:toggle' };
  }

  if (/que horas|horas agora|^hora\??$/.test(text)) return { type: 'time' };
  if (/que dia (?:e hoje|estamos)|data de hoje|^data\??$/.test(text)) return { type: 'date' };
  if (/status do sistema|como voce esta|como esta o sistema|resumo do sistema/.test(text)) {
    return { type: 'status' };
  }

  const calculation = input.match(/^(?:calcular|calcule|quanto\s+(?:é|e|dá|da))\s+(.+)$/i);
  const mathOnly = /^[\d\s.,+\-*/%^()×x÷−–]+$/i.test(input) && /\d/.test(input) && /[+\-*/%^()×x÷−–]/i.test(input);
  if (calculation || mathOnly) {
    const expression = (calculation?.[1] ?? input).replace(/[?=]+$/g, '').trim();
    return { type: 'calculate', expression };
  }

  if (/^(?:python|api python)\s+(?:status|info)$/.test(text)) return { type: 'python:status' };
  const analyzeText = input.match(/^(?:python\s+)?analisar(?:\s+o)?\s+texto\s+(.+)$/i)
    ?? input.match(/^contar\s+palavras\s+(?:de|em)\s+(.+)$/i);
  if (analyzeText) return { type: 'python:analyze', text: analyzeText[1].trim() };

  const meeting = raw.match(/^(?:analisar|analis[ae]|resumir|resuma)\s+(?:a\s+|esta\s+|essa\s+)?reuni[aã]o\s*:?\s+([\s\S]+)$/i);
  if (meeting?.[1].trim()) return { type: 'meeting:analyze', transcript: meeting[1].trim() };
  const changelog = raw.match(/^(?:gerar|gere|criar|crie)\s+changelog(?:\s+(?:vers[aã]o\s+)?([0-9][a-z0-9._-]*))?\s*:\s*([\s\S]+)$/i);
  if (changelog?.[2].trim()) return { type: 'changelog:generate', version: changelog[1] ?? 'Próxima versão', commits: changelog[2].trim() };
  const draw = input.match(/^sortear(?:\s+(\d+))?\s+entre\s+(.+)$/i) ?? input.match(/^sortear\s+(.+)$/i);
  if (draw) {
    const explicitCount = draw.length === 3 ? Number(draw[1] ?? 1) : 1;
    const entries = draw.length === 3 ? draw[2] : draw[1];
    if (Number.isInteger(explicitCount) && explicitCount >= 1 && explicitCount <= 100 && entries.trim()) {
      return { type: 'random:pick', entries: entries.trim(), count: explicitCount };
    }
  }

  if (/^(?:meus documentos|listar documentos|liste documentos|mostrar documentos|mostre documentos|listar arquivos|liste arquivos)$/.test(text)) {
    return { type: 'document:list' };
  }
  const documentRead = input.match(/^(?:ler|leia|extrair|extraia)\s+(?:o\s+|a\s+)?(?:documento|pdf|planilha|apresenta[cç][aã]o|docx|xlsx|pptx)\s+(.+)$/i);
  if (documentRead) return { type: 'document:read', path: documentRead[1].trim().replace(/^[\"']|[\"']$/g, '') };
  if (/^(?:criar|crie|novo|nova|abrir|abra)(?: um| uma)? (?:documento|docx|planilha|xlsx|apresentacao|pptx|pdf|documentos)$/.test(text)) {
    return { type: 'document:workspace' };
  }
  if (/^(?:organizar|organize|organizacao de|simular organizacao de|simule organizacao de)(?: os)? arquivos$/.test(text)) {
    return { type: 'files:organize' };
  }

  if (/^(?:meus planos|listar planos|liste planos|mostrar planos|mostre planos)$/.test(text)) {
    return { type: 'planning:list' };
  }
  const planningResume = raw.match(/^(?:retomar|retome|recuperar|recupere)\s+(?:o\s+)?plano\s+([a-z0-9][a-z0-9-]{0,79})$/i);
  if (planningResume) return { type: 'planning:resume', planId: planningResume[1].toLowerCase() };
  const planningGate = raw.match(/^(?:verificar|verifique|checar|cheque|mostrar|mostre)?\s*gate\s+(?:do|de|para)\s+plano\s+([a-z0-9][a-z0-9-]{0,79})$/i);
  if (planningGate) return { type: 'planning:gate', planId: planningGate[1].toLowerCase() };
  if (/^(?:criar plano|crie plano|novo plano|abrir planejamento|abra planejamento|planejamento persistente|retomar plano|retome plano|gate do plano)$/.test(text)) {
    return { type: 'planning:workspace' };
  }
  const artifact = '([A-Za-z0-9][A-Za-z0-9._/-]{0,199})';
  const inspectArtifact = input.match(new RegExp(`^(?:inspecionar|inspecione|analisar|analise)\\s+(?:o\\s+)?artefato\\s+${artifact}$`, 'i'));
  if (inspectArtifact) return { type: 'reverse:inspect', path: inspectArtifact[1] };
  const artifactStrings = input.match(new RegExp(`^(?:(?:extrair|extraia|listar|liste|mostrar|mostre)\\s+)?strings\\s+(?:de|do|da)\\s+${artifact}$`, 'i'));
  if (artifactStrings) return { type: 'reverse:strings', path: artifactStrings[1] };
  const artifactEntropy = input.match(new RegExp(`^(?:(?:medir|meca|meça|calcular|calcule|mostrar|mostre)\\s+)?entropia\\s+(?:de|do|da)\\s+${artifact}$`, 'i'));
  if (artifactEntropy) return { type: 'reverse:entropy', path: artifactEntropy[1] };
  const analyzeJavascript = input.match(new RegExp(`^(?:analisar|analise)\\s+(?:o\\s+)?(?:javascript|electron|aplicativo|app)\\s+${artifact}$`, 'i'));
  if (analyzeJavascript) return { type: 'reverse:analyze', path: analyzeJavascript[1] };
  const compareArtifacts = input.match(new RegExp(`^comparar\\s+artefatos?\\s+${artifact}\\s+e\\s+${artifact}$`, 'i'));
  if (compareArtifacts) return { type: 'reverse:compare', left: compareArtifacts[1], right: compareArtifacts[2] };
  if (/^(?:engenharia reversa|analise reversa|abrir reversa|abrir engenharia reversa|analisar binario|inspecionar binario|analisar artefato|inspecionar artefato)$/.test(text)) {
    return { type: 'reverse:workspace' };
  }

  const leanReview = raw.match(/^(?:revisar|revise|revis[ãa]o)\s+(?:a\s+)?(?:mudan[çc]a|diff|altera[çc][ãa]o)(?:\s+(?:lean|enxuta))?\s*:\s*([\s\S]+)$/i);
  if (leanReview?.[1].trim()) {
    return { type: 'lean:review', diff: leanReview[1].trim() };
  }
  const leanAudit = input.match(/^(?:auditar|audite|auditoria)\s+(?:o\s+)?(?:c[óo]digo|projeto)\s+([A-Za-z0-9][A-Za-z0-9._/-]{0,199})$/i);
  if (leanAudit) return { type: 'lean:audit', path: leanAudit[1] };
  const leanDebt = input.match(/^(?:d[íi]vida\s+de\s+atalhos|atalhos)\s+(?:em|no|na|de|do|da)\s+([A-Za-z0-9][A-Za-z0-9._/-]{0,199})$/i);
  if (leanDebt) return { type: 'lean:debt', path: leanDebt[1] };
  if (/^(?:abrir (?:enxuto|lean)|engenharia enxuta|modo enxuto|escada lean|revis[ãa]o lean|d[íi]vida de atalhos|auditoria lean)$/.test(text)) {
    return { type: 'lean:workspace' };
  }
  if (/^(?:abrir (?:agentes?|governo)|governo de agentes|governan[çc]a de agentes|revisar equipe de agentes|revisar or[çc]amento de agentes|watchdog de tarefas?|permiss[õo]es de agentes)$/.test(text)) {
    return { type: 'agency:workspace' };
  }
  if (/^(?:abrir (?:est[úu]dio|design)|est[úu]dio de design|design system|sistema de design|revisar (?:contrato|design|design system)|revisar contraste|criticar design|revisar artefato de design)$/.test(text)) {
    return { type: 'studio:workspace' };
  }
  if (/^(?:abrir (?:dire[çc][ãa]o(?: de arte)?|gosto)|dire[çc][ãa]o de arte|revisar copy|auditar copy|deck de copy|registro de tells|tells|j[úu]ri de design|auditar argumento|revisar argumento)$/.test(text)) {
    return { type: 'taste:workspace' };
  }
  if (/^(?:abrir (?:diagramas?|desenho)|diagramas?|desenhar (?:diagrama|arquitetura|fluxo|sequ[êe]ncia)|diagrama de (?:arquitetura|sequ[êe]ncia|estados|dados|classes|entidades)|validar (?:ir|diagrama)|exportar mermaid)$/.test(text)) {
    return { type: 'diagram:workspace' };
  }

  const engineeringReview = raw.match(/^(?:revisar|revise|analisar|analis[ae])\s+c[óo]digo\s+(python|javascript|typescript|jsx|tsx)\s*:\s*([\s\S]+)$/i);
  if (engineeringReview?.[2].trim()) {
    return { type: 'engineering:review', language: engineeringReview[1].toLowerCase(), code: engineeringReview[2].trim() };
  }
  if (/^(?:revisar|revise|analisar|analis[ae])\s+c[óo]digo\b/i.test(raw)) return { type: 'engineering:workspace' };
  if (/^(?:avaliar|avalie|classificar|classifique)\s+(?:os\s+)?(?:core\s+)?web\s*vitals\b/i.test(raw)) {
    const lcp = raw.match(/\blcp\s*[:=]?\s*(\d+(?:[.,]\d+)?)/i);
    const inp = raw.match(/\binp\s*[:=]?\s*(\d+(?:[.,]\d+)?)/i);
    const cls = raw.match(/\bcls\s*[:=]?\s*(\d+(?:[.,]\d+)?)/i);
    if (lcp && inp && cls) {
      const values = [lcp[1], inp[1], cls[1]].map((value) => Number(value.replace(',', '.')));
      if (values.every((value) => Number.isFinite(value) && value >= 0)) {
        return { type: 'engineering:webvitals', lcpMs: values[0], inpMs: values[1], cls: values[2] };
      }
    }
    return { type: 'engineering:workspace' };
  }
  if (/^(?:abrir engenharia|workflows de engenharia|criar especificacao|criar adr|planejar feature|planejar funcionalidade|matriz de testes|modelo de ameacas|gate de release)$/.test(text)) {
    return { type: 'engineering:workspace' };
  }

  if (/^(?:quais leis voce (?:tem|possui|conhece)|catalogo de leis|fontes da legislacao|listar leis|mostrar leis|leis disponiveis|normas disponiveis)$/.test(text)) {
    return { type: 'legal:sources' };
  }
  const legalArticle = input.match(/^(?:(?:consultar|consulte|mostrar|mostre|ler|leia|ver|veja)\s+)?(?:o\s+)?art(?:igo)?\.?\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:º)?\s*(?:-\s*([a-zA-Z]))?\s+(?:da|do|de|na|no)\s+(.+)$/i);
  if (legalArticle) {
    const documentId = resolveLegalDocument(legalArticle[3]);
    if (documentId) {
      return {
        type: 'legal:article',
        documentId,
        article: `${legalArticle[1]}${legalArticle[2] ? `-${legalArticle[2].toUpperCase()}` : ''}`,
      };
    }
  }
  const legalTopic = input.match(/^(?:pesquisar|pesquise|procurar|procure|buscar|busque)\s+(?:na\s+|no\s+)?(?:legisla[cç][aã]o|leis|lei)\s+(?:sobre|por)\s+(.+)$/i)
    ?? input.match(/^(?:legisla[cç][aã]o|lei)\s+sobre\s+(.+)$/i)
    ?? input.match(/^o\s+que\s+(?:a\s+lei\s+diz|diz\s+a\s+lei)\s+sobre\s+(.+)$/i);
  if (legalTopic) return { type: 'legal:search', query: legalTopic[1].replace(/[?]+$/g, '').trim(), documentId: '' };
  const legalDocumentSearch = input.match(/^(?:pesquisar|pesquise|procurar|procure|buscar|busque)\s+(?:na|no)\s+(.+?)\s+(?:sobre|por)\s+(.+)$/i);
  if (legalDocumentSearch) {
    const documentId = resolveLegalDocument(legalDocumentSearch[1]);
    if (documentId) return { type: 'legal:search', query: legalDocumentSearch[2].replace(/[?]+$/g, '').trim(), documentId };
  }

  const completeTask = input.match(/^(?:concluir|conclua|finalizar|finalize|marcar)\s+(?:a\s+)?tarefa\s+(.+)$/i);
  if (completeTask) return { type: 'task:complete', query: cleanTaskTitle(completeTask[1]) };

  if (/(?:mostrar|mostre|listar|liste|ver|veja|quais)(?: as| minhas)? tarefas/.test(text) || text === 'tarefas') {
    return { type: 'task:list' };
  }

  const task = input.match(/^(?:criar|crie|adicionar|adicione)\s+(?:uma\s+)?tarefa\s*:?[ \t]*(?:para\s+|de\s+)?(.+)$/i)
    ?? input.match(/^nova\s+tarefa\s*:?[ \t]*(?:para\s+|de\s+)?(.+)$/i);
  if (task) {
    const title = cleanTaskTitle(task[1]);
    if (!title) return { type: 'task:list' };
    const priority: Priority = /urgente|prioridade alta|importante/i.test(task[1])
      ? 'alta'
      : /prioridade baixa/i.test(task[1])
        ? 'baixa'
        : 'media';
    return {
      type: 'task:add',
      title,
      priority,
      dueDate: /amanh[ãa]/i.test(task[1]) ? tomorrowISO() : todayISO(),
    };
  }

  if (/(?:mostrar|mostre|listar|liste|ver|veja)(?: as| minhas)? (?:notas|memorias)/.test(text) || text === 'notas') {
    return { type: 'note:list' };
  }
  const note = input.match(/^(?:anotar|anote|anota|guardar|guarde|lembrar|lembre)(?:\s+que)?\s+(.+)$/i);
  if (note) return { type: 'note:add', content: note[1].replace(/[.!?]+$/g, '').trim() };

  if (/^(?:pausar|pause|pausa)(?: o)? foco$/.test(text)) return { type: 'focus:pause' };
  if (/^(?:retomar|retome|continuar|continue)(?: o)? foco$/.test(text)) return { type: 'focus:resume' };
  if (/^(?:parar|pare|cancelar|cancele|encerrar|encerre)(?: o)? foco$/.test(text)) return { type: 'focus:stop' };
  if (/^(?:status|tempo)(?: do)? foco$/.test(text) || /quanto tempo.*foco/.test(text)) return { type: 'focus:status' };
  const focus = text.match(/^(?:iniciar|inicie|comecar|comece|ativar|ative)(?: uma| um| o)? (?:sessao de )?foco(?: de)?\s*(\d+)?/);
  if (focus) {
    const minutes = Math.min(180, Math.max(1, Number(focus[1] ?? 25)));
    return { type: 'focus:start', minutes };
  }

  if (/executar resumo|resumo do dia|resumo de hoje/.test(text)) return { type: 'automation:summary' };
  if (/organizar prioridades|organizar tarefas|ordene (?:as )?tarefas/.test(text)) return { type: 'automation:organize' };
  if (/exportar (?:memoria|dados|backup)|fazer backup|backup da memoria/.test(text)) return { type: 'automation:backup' };

  const search = input.match(/^(?:pesquisar|pesquise|procurar|procure|buscar|busque)(?:\s+na\s+(?:web|internet))?\s+(?:por\s+|sobre\s+)?(.+)$/i);
  if (search) return { type: 'web:search', query: search[1].replace(/[?]+$/g, '').trim() };

  const open = text.match(/^(?:abrir|abra|acessar|acesse)\s+(?:o\s+|a\s+)?(.+)$/);
  if (open) {
    const key = open[1].replace(/[!.\s]+$/g, '').trim();
    const destination = destinations[key];
    if (destination) return { type: 'web:open', destination: destination.label, url: destination.url };
  }

  return { type: 'unknown' };
}

export const helpText = [
  'Estas são as skills que já posso executar localmente:',
  '• Tarefas — “criar tarefa revisar o projeto” ou “concluir tarefa revisar”.',
  '• Memória — “anotar minha ideia sobre o JARVIS” ou “mostrar notas”.',
  '• Foco — “iniciar foco de 25 minutos”, “pausar foco” ou “retomar foco”.',
  '• Cálculos — “calcular (1250 * 0,18) + 40”.',
  '• Web — “pesquisar por automação pessoal” ou “abrir GitHub”.',
  '• Python — “analisar texto JARVIS organiza minha rotina” ou “python status”.',
  '• Legislação — “artigo 49 do CDC” ou “pesquisar na legislação sobre proteção de dados”.',
  '• Documentos — “listar documentos” ou “ler PDF documentos/relatorio.pdf”. Criação exige confirmação na página Documentos.',
  '• Produtividade — “analisar reunião: Ana: revisar proposta”, “gerar changelog: feat: nova skill” ou “sortear 2 entre Ana, Bruno, Carla”.',
  '• Arquivos — “organizar arquivos” executa apenas uma simulação; a gravação exige confirmação em Skills.',
  '• Engenharia — “revisar código python: eval(entrada)” ou “avaliar web vitals LCP 2600 INP 180 CLS 0,05”.',
  '• Planos — “listar planos”, “retomar plano ID” ou “gate do plano ID”. Criação e atualização exigem confirmação na página Planos.',
  '• Reversa — “inspecionar artefato app/main.js”, “strings de app.asar”, “entropia de firmware.bin”, “analisar javascript app” ou “comparar artefatos a.bin e b.bin”. Nada é executado.',
  '• Enxuto — “revisar mudança: <diff>”, “auditar código app”, “dívida de atalhos em app” ou “abrir lean”. Análise estática, sem executar nada.',
  '• Agentes — “abrir agentes” ou “governo de agentes”. Revisa equipe, quadro, orçamento, parada de trabalho e permissões declaradas, sem executar agentes.',
  '• Estúdio — “abrir estúdio”, “design system” ou “revisar contraste”. Confere contrato de design, contraste WCAG, crítica em cinco dimensões e clichês no HTML, sem compilar nem publicar.',
  '• Sistema — “que horas são?”, “status do sistema” ou “executar resumo do dia”.',
].join('\n');
