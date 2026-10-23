export interface Skill {
  id: string;
  name: string;
  description: string;
  category: 'Essencial' | 'Produtividade' | 'Conectividade';
  icon: 'sparkles' | 'tasks' | 'brain' | 'calculator' | 'timer' | 'globe' | 'workflow' | 'code';
  active: boolean;
  local: boolean;
  commands: string[];
  detail: string;
}

export const skills: Skill[] = [
  {
    id: 'commands',
    name: 'Comandos naturais',
    description: 'Interpreta pedidos em português e direciona cada ação para a skill certa.',
    category: 'Essencial',
    icon: 'sparkles',
    active: true,
    local: true,
    commands: ['ajuda', 'o que você pode fazer?', 'status do sistema'],
    detail: 'O roteador local reconhece intenções sem enviar sua conversa para servidores externos. Pedidos fora das skills instaladas recebem uma resposta transparente.',
  },
  {
    id: 'tasks',
    name: 'Gestão de tarefas',
    description: 'Cria, lista, conclui e organiza tarefas por projeto e prioridade.',
    category: 'Produtividade',
    icon: 'tasks',
    active: true,
    local: true,
    commands: ['criar tarefa revisar o projeto', 'mostrar tarefas', 'concluir tarefa revisar'],
    detail: 'As tarefas são persistidas localmente. O comando de conclusão encontra a primeira tarefa pendente cujo título contenha o texto informado.',
  },
  {
    id: 'memory',
    name: 'Memória pessoal',
    description: 'Guarda notas e contexto importante com busca e exportação local.',
    category: 'Essencial',
    icon: 'brain',
    active: true,
    local: true,
    commands: ['anotar revisar a arquitetura amanhã', 'mostrar notas'],
    detail: 'Notas são armazenadas apenas neste navegador. Use o backup em JSON para transferir ou preservar seus dados.',
  },
  {
    id: 'calculator',
    name: 'Calculadora segura',
    description: 'Resolve expressões matemáticas sem executar código arbitrário.',
    category: 'Essencial',
    icon: 'calculator',
    active: true,
    local: true,
    commands: ['calcular 1250 * 0,18', 'quanto é (42 + 8) / 2'],
    detail: 'Aceita adição, subtração, multiplicação, divisão, resto, potência e parênteses. Um parser próprio substitui eval e bloqueia código.',
  },
  {
    id: 'focus',
    name: 'Ciclos de foco',
    description: 'Controla sessões cronometradas com pausa, retomada e histórico diário.',
    category: 'Produtividade',
    icon: 'timer',
    active: true,
    local: true,
    commands: ['iniciar foco de 25 minutos', 'pausar foco', 'retomar foco'],
    detail: 'O timer continua correndo enquanto o aplicativo estiver aberto e recupera o estado após uma atualização da página.',
  },
  {
    id: 'web',
    name: 'Navegação web',
    description: 'Abre pesquisas e destinos conhecidos em uma nova aba, sob seu comando.',
    category: 'Conectividade',
    icon: 'globe',
    active: true,
    local: true,
    commands: ['pesquisar por automação pessoal', 'abrir github', 'abrir youtube'],
    detail: 'A navegação só acontece após um comando explícito. Nenhum histórico ou credencial do navegador é lido pelo JARVIS.',
  },
  {
    id: 'automations',
    name: 'Automações locais',
    description: 'Executa resumos, organização, foco e backups manualmente ou por agenda.',
    category: 'Produtividade',
    icon: 'workflow',
    active: true,
    local: true,
    commands: ['executar resumo do dia', 'organizar prioridades', 'iniciar foco de 50 minutos'],
    detail: 'A agenda funciona enquanto o aplicativo estiver aberto. Execuções e resultados aparecem no histórico de atividades.',
  },
  {
    id: 'python',
    name: 'Núcleo Python',
    description: 'Skills allowlisted para texto, dados, arquivos isolados, sistema e legislação.',
    category: 'Conectividade',
    icon: 'code',
    active: false,
    local: true,
    commands: [],
    detail: 'O adaptador FastAPI usa allowlist, validação com Pydantic e timeout. Texto, cálculo, arquivos isolados, status e legislação já usam esta arquitetura; gravação exige confirmação e o corpus jurídico é somente leitura.',
  },
];
