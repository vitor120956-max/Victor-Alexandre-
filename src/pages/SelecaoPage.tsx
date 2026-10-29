import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Copy,
  Layers,
  ListChecks,
  LoaderCircle,
  ScanSearch,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';

type SelecaoTab = 'brief' | 'buscar' | 'stack' | 'plano' | 'cobertura' | 'catalogo' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: SelecaoTab; label: string; hint: string; icon: typeof Layers }> = [
  { id: 'brief', label: 'Briefing', hint: 'O que o pedido cobre', icon: Sparkles },
  { id: 'buscar', label: 'Buscar', hint: 'Ranking do catálogo', icon: Search },
  { id: 'stack', label: 'Stack', hint: 'Ids, lacunas e risco', icon: ShieldCheck },
  { id: 'plano', label: 'Plano', hint: 'Fases e checagens', icon: ListChecks },
  { id: 'cobertura', label: 'Cobertura', hint: 'Dimensão por dimensão', icon: ScanSearch },
  { id: 'catalogo', label: 'Catálogo', hint: 'Saúde do índice', icon: Layers },
  { id: 'regras', label: 'Regras', hint: 'Fórmulas e limites', icon: BookOpen },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const riscos = ['', 'safe', 'none', 'unknown', 'offensive', 'critical'];

const AMOSTRA = JSON.stringify(
  [
    { id: 'stripe-integration', category: 'api-integration', name: 'stripe-integration', description: 'Cobra assinatura e webhook com Stripe no servidor.', risk: 'critical', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'payment-integration', category: 'api-integration', name: 'payment-integration', description: 'Integra Stripe e PayPal com checkout e reembolso.', risk: 'critical', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'nextjs-best-practices', category: 'frontend', name: 'nextjs-best-practices', description: 'Estrutura rotas e componentes do Next.js App Router.', risk: 'safe', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'vercel-deployment', category: 'devops', name: 'vercel-deployment', description: 'Publica deploy na Vercel com rollback e variável de ambiente.', risk: 'safe', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'supabase', category: 'backend', name: 'supabase', description: 'Cria tabela, política e função no banco Supabase.', risk: 'critical', source: 'community', plugin: { targets: { claude: 'supported' }, setup: { type: 'manual', summary: 'rodar supabase link' }, reasons: [] } },
    { id: 'ab-testing', category: 'testing', name: 'ab-testing', description: 'Planeja teste A/B com tamanho de amostra e leitura.', risk: 'critical', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'api-security', category: 'backend', name: 'api-security', description: 'Revisa autenticação, rate limit e entrada de API.', risk: 'offensive', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
    { id: 'accessibility-audit', category: 'design', name: 'accessibility-audit', description: 'Audita contraste, foco e rótulo de acessibilidade.', risk: 'safe', source: 'community', plugin: { targets: { claude: 'supported', codex: 'supported' }, setup: { type: 'none' }, reasons: [] } },
  ],
  null,
  2,
);

const BRIEF = `Preciso de uma API de cobrança com Stripe para um SaaS em Next.js, com teste de integração e deploy na Vercel. O sucesso é fechar o checkout em menos de 3 segundos. A equipe tem dois devs, o prazo é de seis semanas e o dado pessoal precisa seguir a LGPD.`;

const STACK = `{"skills": ["stripe-integration", "nextjs-best-practices", "supabase", "vercel-deployment"]}`;

const asObj = (valor: unknown): Row => (typeof valor === 'object' && valor !== null && !Array.isArray(valor) ? valor as Row : {});
const asRows = (valor: unknown): Row[] => (Array.isArray(valor) ? valor.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (valor: unknown): string[] => (Array.isArray(valor) ? valor.map((item) => String(item)) : []);
const txt = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));
const num = (valor: unknown): number => (typeof valor === 'number' ? valor : Number(valor ?? 0));
const inteiro = (valor: string, padrao = 0): number => {
  const n = Number(valor.replace(',', '.'));
  return Number.isFinite(n) ? Math.trunc(n) : padrao;
};

const grupos: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const tomDoGrupo = (valor: string): string => {
  if (['obrigatório', 'critical', 'alto', 'lacuna'].includes(valor)) return 'is-danger';
  if (['corrigir', 'offensive', 'médio'].includes(valor)) return 'is-warning';
  if (['opcional', 'safe', 'baixo', 'livre'].includes(valor)) return 'is-ok';
  return '';
};

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill'; largura?: string };

const colunas: Record<Exclude<SelecaoTab, 'regras'>, Coluna[]> = {
  brief: [
    { chave: 'dimensao', titulo: 'Dimensão' },
    { chave: 'evidencia', titulo: 'Palavras que casaram', tipo: 'code' },
    { chave: 'termos', titulo: 'Termos' },
  ],
  buscar: [
    { chave: 'rank', titulo: '#' },
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'categoria', titulo: 'Categoria' },
    { chave: 'risco', titulo: 'Risco', tipo: 'pill' },
    { chave: 'score', titulo: 'Score' },
    { chave: 'termos', titulo: 'Casou com' },
  ],
  stack: [
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'categoria', titulo: 'Categoria' },
    { chave: 'risco', titulo: 'Risco', tipo: 'pill' },
    { chave: 'dimensoes', titulo: 'Dimensões' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
  ],
  plano: [
    { chave: 'fase', titulo: 'Fase' },
    { chave: 'dimensao', titulo: 'Dimensão' },
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'artefato', titulo: 'Artefato' },
    { chave: 'checagem', titulo: 'Checagem de saída' },
    { chave: 'depende', titulo: 'Depende' },
  ],
  cobertura: [
    { chave: 'dimensao', titulo: 'Dimensão' },
    { chave: 'skills', titulo: 'Skills' },
    { chave: 'cobertura', titulo: 'Cobertura %' },
    { chave: 'melhor', titulo: 'Melhor candidata', tipo: 'code' },
    { chave: 'candidatas', titulo: 'Candidatas' },
  ],
  catalogo: [
    { chave: 'id', titulo: 'Id', tipo: 'code' },
    { chave: 'problema', titulo: 'Problema' },
  ],
};

const titulos: Record<SelecaoTab, string> = {
  brief: 'Briefing lido',
  buscar: 'Recomendação',
  stack: 'Stack validada',
  plano: 'Plano por dimensão',
  cobertura: 'Cobertura do catálogo',
  catalogo: 'Saúde do catálogo',
  regras: 'Fórmulas e limites',
};

type Formato = 'int' | 'score' | 'pct' | 'dec';

const formatar = (valor: number, formato: Formato = 'int'): string => {
  if (formato === 'score') return valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (formato === 'pct') return valor.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  if (formato === 'dec') return valor.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
  return valor.toLocaleString('pt-BR');
};

const metricasDoTab: Record<Exclude<SelecaoTab, 'regras'>, Array<{ label: string; chave: string; formato?: Formato }>> = {
  brief: [
    { label: 'PALAVRAS', chave: 'palavras' },
    { label: 'DIMENSÕES', chave: 'dimensoes' },
    { label: 'ENTREGÁVEIS', chave: 'entregaveis' },
    { label: 'RESTRIÇÕES', chave: 'restricoes' },
    { label: 'CRITÉRIO', chave: 'tem_criterio' },
    { label: 'PÚBLICO', chave: 'tem_publico' },
  ],
  buscar: [
    { label: 'ENTRADAS', chave: 'entradas' },
    { label: 'FILTRADAS', chave: 'filtradas' },
    { label: 'TERMOS', chave: 'consulta' },
    { label: 'RESULTADOS', chave: 'resultados' },
    { label: 'MELHOR SCORE', chave: 'melhor', formato: 'score' },
    { label: 'COBERTAS', chave: 'cobertas' },
  ],
  stack: [
    { label: 'SKILLS', chave: 'skills' },
    { label: 'VÁLIDAS', chave: 'validas' },
    { label: 'COBERTAS', chave: 'cobertas' },
    { label: 'LACUNAS', chave: 'lacunas' },
    { label: 'SOBREPOSTAS', chave: 'sobrepostas' },
    { label: 'PONTOS DE RISCO', chave: 'pontos_risco' },
  ],
  plano: [
    { label: 'FASES', chave: 'fases' },
    { label: 'PASSOS', chave: 'linhas' },
    { label: 'COBERTAS', chave: 'cobertas' },
    { label: 'DIMENSÕES', chave: 'dimensoes' },
    { label: 'CRÍTICAS', chave: 'criticas' },
    { label: 'PORTÃO', chave: 'portao' },
  ],
  cobertura: [
    { label: 'ENTRADAS', chave: 'entradas' },
    { label: 'DIMENSÕES', chave: 'dimensoes' },
    { label: 'COBERTAS', chave: 'cobertas' },
    { label: 'LACUNAS', chave: 'lacunas' },
    { label: 'MÉDIA %', chave: 'media', formato: 'pct' },
  ],
  catalogo: [
    { label: 'ENTRADAS', chave: 'entradas' },
    { label: 'CATEGORIAS', chave: 'categorias' },
    { label: 'CRÍTICOS', chave: 'criticos' },
    { label: 'INDEFINIDOS', chave: 'indefinidos' },
    { label: 'MANUAIS', chave: 'manuais' },
    { label: 'MÉDIA PALAVRAS', chave: 'media_palavras', formato: 'pct' },
  ],
};

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function Verdict({ children, blocked }: { children: React.ReactNode; blocked: boolean }) {
  return (
    <p className="diagram-verdict">
      {blocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
      {children}
    </p>
  );
}

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nada contra as regras deste nível.</p>;
  return (
    <div className="diagram-findings">
      {items.map((item) => {
        const grupo = txt(item.group);
        return (
          <article className={`diagram-finding is-${grupo}`} key={`${txt(item.id)}-${txt(item.kind)}`}>
            <header>
              <span className="diagram-group">{grupos[grupo] ?? grupo}</span>
              <strong>{txt(item.title)}</strong>
              <code>{txt(item.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{txt(item.what)}</dd></div>
              <div><dt>Problema</dt><dd>{txt(item.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{txt(item.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{txt(item.ifSkipped)}</dd></div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function Limitations({ items }: { items: unknown }) {
  const linhas = asList(items);
  if (!linhas.length) return null;
  return (
    <div className="diagram-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{linhas.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Tabela({ titulo, colunas: cols, linhas }: { titulo: string; colunas: Coluna[]; linhas: Row[] }) {
  if (!linhas.length) return null;
  return (
    <div className="selecao-table-block">
      <h4>{titulo}</h4>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr>{cols.map((coluna) => <th key={coluna.chave}>{coluna.titulo}</th>)}</tr></thead>
          <tbody>
            {linhas.map((linha, indice) => (
              <tr key={indice}>
                {cols.map((coluna) => {
                  const valor = txt(linha[coluna.chave]) || '—';
                  if (coluna.tipo === 'code') return <td key={coluna.chave}><code>{valor}</code></td>;
                  if (coluna.tipo === 'pill') return <td key={coluna.chave}><span className={['diagram-state', tomDoGrupo(valor)].filter(Boolean).join(' ')}>{valor}</span></td>;
                  return <td key={coluna.chave}>{valor}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SelecaoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<SelecaoTab>('buscar');
  const [nivel, setNivel] = useState('full');
  const [brief, setBrief] = useState(BRIEF);
  const [catalogo, setCatalogo] = useState(AMOSTRA);
  const [stack, setStack] = useState(STACK);
  const [categoria, setCategoria] = useState('');
  const [risco, setRisco] = useState('');
  const [alvo, setAlvo] = useState('');
  const [limite, setLimite] = useState('8');
  const [limiteRisco, setLimiteRisco] = useState('4');
  const [maxSkills, setMaxSkills] = useState('128');
  const [porDimensao, setPorDimensao] = useState('3');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [regras, setRegras] = useState<Row | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);
  const precisaCatalogo = tab !== 'brief' && tab !== 'regras';
  const precisaBrief = tab !== 'catalogo' && tab !== 'regras';

  const carregarRegras = async () => {
    if (regras !== null || !backendOnline) return;
    try {
      const resposta = await executeSkill('selecao.regras', {});
      if (resposta.ok) setRegras(asObj(resposta.result));
    } catch {
      setRegras(null);
    }
  };

  const trocarTab = (destino: SelecaoTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
    if (destino === 'regras' && regras === null) void carregarRegras();
  };

  const parametros = (ativo: Exclude<SelecaoTab, 'regras'>): Record<string, unknown> => {
    const comum = { modo: nivel };
    if (ativo === 'brief') return { brief, ...comum };
    if (ativo === 'buscar') return { brief, catalogo, categoria, risco, alvo, limite: inteiro(limite, 8), ...comum };
    if (ativo === 'stack') return { brief, skills: stack, catalogo, alvo: alvo || 'claude', limite_risco: inteiro(limiteRisco, 4), max_skills: inteiro(maxSkills, 128), ...comum };
    if (ativo === 'plano') return { brief, skills: stack, catalogo, alvo: alvo || 'claude', ...comum };
    if (ativo === 'cobertura') return { brief, catalogo, limite_por_dimensao: inteiro(porDimensao, 3), ...comum };
    return { catalogo, ...comum };
  };

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (tab === 'regras') {
      await carregarRegras();
      return;
    }
    if (!backendOnline) {
      setErro('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi calculado.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`selecao.${tab}`, parametros(tab));
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(resposta);
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao executar a skill.');
    } finally {
      setBusy(false);
    }
  };

  const copiar = async () => {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      pushToast('Parecer copiado', 'O texto está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const rotuloBotao: Record<SelecaoTab, string> = {
    brief: 'Ler o briefing',
    buscar: 'Buscar no catálogo',
    stack: 'Validar stack',
    plano: 'Montar plano',
    cobertura: 'Mapear cobertura',
    catalogo: 'Auditar catálogo',
    regras: 'Recarregar catálogo',
  };

  const bloqueado = num(asObj(resultado?.counts).must) > 0;

  return (
    <div className="diagram-section selecao-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Layers size={22} /></span>
        <div>
          <span className="eyebrow">ESCOLHER ENTRE MILHARES SEM CHUTAR</span>
          <h2>Seleção é cobertura</h2>
          <p>O catálogo do AAS tem 2.743 skills em 114 categorias, e o Core do upstream recusa ranquear: ele valida ids e devolve a decisão para o agente. Aqui a conta é explícita — BM25 com pesos declarados, dez dimensões de capacidade, orçamento de risco e um plano com checagem de saída. O catálogo é o JSON que você cola.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Lacuna não é escolha</strong><span>Dimensão sem skill bloqueia, não empata.</span></li>
          <li><strong>Score não é risco</strong><span>Relevância ranqueia; risco se soma depois.</span></li>
          <li><strong>Fase tem saída</strong><span>Sem checagem, o plano é lista de desejos.</span></li>
          <li><strong>Id errado derruba tudo</strong><span>Um id fora do índice recusa a stack.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos de seleção">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => trocarTab(id)} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className={`diagram-layout${tab === 'regras' ? ' is-single' : ''}`}>
        {tab !== 'regras' && (
          <section className="panel diagram-form">
            <header className="diagram-form-head">
              <div>
                <span className="eyebrow">{tabs.find((item) => item.id === tab)?.label.toUpperCase()}</span>
                <h2>{tabs.find((item) => item.id === tab)?.hint}</h2>
              </div>
              <label className="diagram-level">
                <span>NÍVEL</span>
                <select value={nivel} onChange={(event) => setNivel(event.target.value)}>
                  {niveis.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            </header>

            <form className="form-stack" onSubmit={executar}>
              {precisaBrief && (
                <label className="field">
                  <span>Briefing</span>
                  <textarea value={brief} onChange={(event) => setBrief(event.target.value)} rows={5} spellCheck={false} />
                </label>
              )}

              {(tab === 'stack' || tab === 'plano') && (
                <label className="field">
                  <span>Stack (ids em JSON ou um por linha)</span>
                  <textarea value={stack} onChange={(event) => setStack(event.target.value)} rows={4} spellCheck={false} />
                </label>
              )}

              {precisaCatalogo && (
                <label className="field">
                  <span>Catálogo — índice em JSON ou linhas “id | categoria | descrição”</span>
                  <textarea value={catalogo} onChange={(event) => setCatalogo(event.target.value)} rows={8} spellCheck={false} />
                  <small className="selecao-contador">{catalogo.length.toLocaleString('pt-BR')} caracteres</small>
                </label>
              )}

              {tab === 'buscar' && (
                <div className="selecao-filtros">
                  <label><span>Categoria</span><input value={categoria} onChange={(event) => setCategoria(event.target.value)} placeholder="security" /></label>
                  <label>
                    <span>Risco</span>
                    <select value={risco} onChange={(event) => setRisco(event.target.value)}>
                      {riscos.map((item) => <option key={item || 'todos'} value={item}>{item || 'todos'}</option>)}
                    </select>
                  </label>
                  <label><span>Alvo</span><input value={alvo} onChange={(event) => setAlvo(event.target.value)} placeholder="claude" /></label>
                  <label><span>Resultados</span><input type="number" min={1} max={50} value={limite} onChange={(event) => setLimite(event.target.value)} /></label>
                </div>
              )}

              {tab === 'stack' && (
                <div className="selecao-filtros">
                  <label><span>Alvo</span><input value={alvo} onChange={(event) => setAlvo(event.target.value)} placeholder="claude" /></label>
                  <label><span>Limite de risco</span><input type="number" min={0} value={limiteRisco} onChange={(event) => setLimiteRisco(event.target.value)} /></label>
                  <label><span>Teto de skills</span><input type="number" min={1} max={128} value={maxSkills} onChange={(event) => setMaxSkills(event.target.value)} /></label>
                </div>
              )}

              {tab === 'cobertura' && (
                <div className="selecao-filtros">
                  <label><span>Candidatas por dimensão</span><input type="number" min={1} max={10} value={porDimensao} onChange={(event) => setPorDimensao(event.target.value)} /></label>
                </div>
              )}

              <div className="selecao-acoes">
                <button className="button primary" type="submit" disabled={busy}>
                  {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Search size={16} />}
                  {busy ? 'Calculando…' : rotuloBotao[tab]}
                </button>
                <button type="button" className="button ghost" onClick={() => { setCatalogo(AMOSTRA); setBrief(BRIEF); setStack(STACK); }}>
                  Restaurar amostra
                </button>
              </div>
              {erro && <p className="diagram-error" role="alert"><AlertTriangle size={14} />{erro}</p>}
            </form>
          </section>
        )}

        <section className="panel diagram-result">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h3>{titulos[tab]}</h3>
            </div>
            {resultado && markdown && (
              <button type="button" className="button ghost" onClick={() => void copiar()}><Copy size={14} />Copiar parecer</button>
            )}
          </header>

          {tab === 'regras' && <Regras regras={regras} />}

          {tab !== 'regras' && !resultado && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <Layers size={14} />}
              {busy ? 'Rodando a conta…' : 'Preencha à esquerda. A amostra já vem com oito skills reais do índice para você testar.'}
            </p>
          )}

          {tab !== 'regras' && resultado && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                {metricasDoTab[tab].map((metrica) => (
                  <Metric key={metrica.chave} label={metrica.label} value={formatar(num(asObj(resultado.metrics)[metrica.chave]), metrica.formato)} />
                ))}
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>
              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(resultado.rows)} />
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Regras({ regras }: { regras: Row | null }) {
  if (!regras) return <p className="diagram-empty">O catálogo ainda não chegou da API.</p>;
  const busca = asObj(regras.busca);
  const risco = asObj(regras.risco);
  const stack = asObj(regras.stack);
  const plano = asObj(regras.plano);
  const catalogo = asObj(regras.catalogo);
  const limites = asObj(regras.limites);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="DIMENSÕES" value={asList(regras.dimensoes).length} />
        <Metric label="K1" value={formatar(num(busca.k1), 'dec')} />
        <Metric label="B" value={formatar(num(busca.b), 'dec')} />
        <Metric label="TETO DE SKILLS" value={num(stack.max_skills)} />
        <Metric label="SOBREPOSIÇÃO" value={formatar(num(stack.sobreposicao), 'dec')} />
        <Metric label="REGRAS DO ÍNDICE" value={asList(catalogo.regras).length} />
      </div>
      <p className="diagram-verdict"><CheckCircle2 size={14} />{txt(regras.principio)}</p>

      <Tabela
        titulo="Dez dimensões de capacidade"
        colunas={[{ chave: 'chave', titulo: 'Chave', tipo: 'code' }, { chave: 'rotulo', titulo: 'Dimensão' }, { chave: 'palavras', titulo: 'Léxico' }]}
        linhas={asRows(regras.dimensoes).map((item) => ({ chave: item.chave, rotulo: item.rotulo, palavras: asList(item.palavras).join(', ') }))}
      />
      <Tabela
        titulo="Pontos de risco"
        colunas={[{ chave: 'nivel', titulo: 'Risco', tipo: 'code' }, { chave: 'pontos', titulo: 'Pontos' }]}
        linhas={Object.entries(asObj(risco.pontos)).map(([nivel, pontos]) => ({ nivel, pontos }))}
      />
      <Tabela
        titulo="Categoria vira dimensão"
        colunas={[{ chave: 'trecho', titulo: 'Categoria contém', tipo: 'code' }, { chave: 'dimensao', titulo: 'Dimensão' }]}
        linhas={Object.entries(asObj(regras.categorias)).map(([trecho, dimensao]) => ({ trecho, dimensao }))}
      />

      <div className="selecao-cards">
        <article className="selecao-card">
          <h4>Busca</h4>
          <ul>
            <li><strong>Algoritmo</strong> — {txt(busca.algoritmo)}</li>
            <li><strong>Normalização</strong> — {txt(busca.normalizacao)}</li>
            <li><strong>Limiar de score</strong> — {num(busca.limiar_de_score)}</li>
            <li><strong>Empate</strong> — diferença de até {num(busca.empate)} no topo</li>
          </ul>
        </article>
        <article className="selecao-card">
          <h4>Stack</h4>
          <ul>
            <li><strong>Regra</strong> — {txt(stack.regra)}</li>
            <li><strong>Manifesto</strong> — {txt(stack.manifesto)}</li>
            <li><strong>Cobertura mínima</strong> — {num(stack.cobertura_minima)}%</li>
            <li><strong>Alvos</strong> — {asList(stack.alvos).join(', ')}</li>
          </ul>
        </article>
        <article className="selecao-card">
          <h4>Plano</h4>
          <ul>
            <li><strong>Regra</strong> — {txt(plano.regra)}</li>
            <li><strong>Ordem</strong> — {asList(plano.ordem).join(' → ')}</li>
            <li><strong>Portões</strong> — {asList(plano.portoes).join(', ')}</li>
          </ul>
        </article>
        <article className="selecao-card">
          <h4>Limites</h4>
          <ul>
            <li><strong>Texto</strong> — {num(limites.texto).toLocaleString('pt-BR')} caracteres</li>
            <li><strong>Entradas</strong> — {num(limites.entradas).toLocaleString('pt-BR')}</li>
            <li><strong>Resultados</strong> — {num(asObj(limites.resultados).minimo)} a {num(asObj(limites.resultados).maximo)}</li>
            <li><strong>Teto de skills</strong> — {num(limites.skills)}</li>
          </ul>
        </article>
      </div>

      <div className="selecao-card">
        <h4>Regras do índice</h4>
        <ol>{asList(catalogo.regras).map((item) => <li key={item}>{item}</li>)}</ol>
      </div>

      <div className="diagram-limitations">
        <strong>DEIXADO DE FORA</strong>
        <ul>{asList(regras.deixado_de_fora).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </div>
  );
}
