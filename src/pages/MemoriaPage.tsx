import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Clock,
  Copy,
  GitFork,
  LoaderCircle,
  Network,
  Play,
  Route,
  ScanSearch,
  Sprout,
  Trash2,
  Waypoints,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../memoria.css';

type MemoriaTab = 'roteamento' | 'entidades' | 'grafo' | 'sessao' | 'recall' | 'esquecer' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: MemoriaTab; label: string; hint: string; icon: typeof Brain }> = [
  { id: 'roteamento', label: 'Roteamento', hint: 'Por onde procurar', icon: Route },
  { id: 'entidades', label: 'Entidades', hint: 'O que vira nó', icon: ScanSearch },
  { id: 'grafo', label: 'Grafo', hint: 'O que liga o quê', icon: Network },
  { id: 'sessao', label: 'Sessão', hint: 'O que promover', icon: Sprout },
  { id: 'recall', label: 'Recall', hint: 'O que volta e por quê', icon: Waypoints },
  { id: 'esquecer', label: 'Esquecer', hint: 'Raio de alcance', icon: Trash2 },
  { id: 'regras', label: 'Regras', hint: 'Pesos e limites', icon: GitFork },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const vias = ['', 'chunks', 'grafo', 'hibrido', 'resumo', 'temporal', 'codigo', 'procedimento', 'regras'];

const CONSULTA = 'Onde fica o índice vetorial do Atlas?';

const TEXTO = `Marie Curie nasceu em Warsaw em 1867-11-07 e trabalhou na University of Paris.
Pierre Curie foi professor na ESPCI e descobriu o polônio com Marie Curie.
O ticket SDM-2041 trata do orçamento de R$ 45.000 para o projeto Atlas em 12/03/2024.
O arquivo server/memoria.py implementa a rota e o datasource usa o Graphiti.
A política de retenção define 90% dos dados por 365 dias em São Paulo.`;

const ARESTAS = `Marie Curie -> trabalhou em -> University of Paris
Marie Curie -> descobriu -> polônio
Pierre Curie -> casado com -> Marie Curie
Marie Curie -> casado com -> Pierre Curie
polônio -> relaciona -> física
Nanismo`;

const CONVERSA = `usuário: O deploy do Atlas usa o cluster de São Paulo e o banco é Postgres 16.
agente: Entendi.
usuário: decisão: o índice vetorial vai para o pgvector e não para um serviço externo.
usuário: ok
agente: regra: nunca rodar migration sem rollback escrito.
usuário: feedback: -1 prefiro manter a migration no mesmo PR do código.
usuário: aprendizado: o limite de 5 MB por asset é conferido no portão antes da revisão.
usuário: A retenção de 365 dias foi acordada com o jurídico em 12/03/2024.`;

const MEMORIAS = `m1 | decisao | 2026-03-12 | ata.md | atlas | O índice vetorial do Atlas vai para o pgvector e não para serviço externo.
m2 | fato | 2025-11-02 | doc.md | atlas | Marie Curie nasceu em Warsaw em 1867-11-07.
m3 | regra | 2026-09-30 | runbook.md | atlas | Migration sempre com rollback escrito e testado no mesmo PR.
m4 | fato | 2024-01-05 | antigo.md | atlas | O deploy do Atlas roda no cluster de Dublin e em Warsaw.
m5 | procedimento | 2026-10-01 | runbook.md | outros | Como instalar o plugin do cognee no Claude Code com o marketplace.`;

const HOJE = '2026-10-24';

const asObj = (valor: unknown): Row => (typeof valor === 'object' && valor !== null && !Array.isArray(valor) ? valor as Row : {});
const asRows = (valor: unknown): Row[] => (Array.isArray(valor) ? valor.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (valor: unknown): string[] => (Array.isArray(valor) ? valor.map((item) => String(item)) : []);
const txt = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));
const num = (valor: unknown): number => (typeof valor === 'number' ? valor : Number(valor ?? 0));
const decimal = (valor: string, padrao = 0): number => {
  const n = Number(valor.replace(',', '.'));
  return Number.isFinite(n) ? n : padrao;
};

const grupos: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const tom = (valor: string): string => {
  if (['obrigatório', 'must', 'negado', 'isolado', 'apaga tudo', 'esquecimento-total', 'descarta'].includes(valor)) return 'is-danger';
  if (['corrigir', 'should', 'promove', 'hub', 'folha', 'interno', 'origem'].includes(valor)) return 'is-warning';
  if (['opcional', 'nice', 'conta', 'ok', 'apaga memória'].includes(valor)) return 'is-ok';
  return '';
};

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill'; largura?: string };

const colunas: Record<Exclude<MemoriaTab, 'regras'>, Coluna[]> = {
  roteamento: [
    { chave: 'via', titulo: 'Via', tipo: 'code' },
    { chave: 'regra', titulo: 'Regra' },
    { chave: 'peso', titulo: 'Peso', largura: '52px' },
    { chave: 'trecho', titulo: 'Trecho da consulta' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
  ],
  entidades: [
    { chave: 'tipo', titulo: 'Tipo', tipo: 'pill' },
    { chave: 'entidade', titulo: 'Entidade' },
    { chave: 'ocorrencias', titulo: 'Ocorr.', largura: '60px' },
    { chave: 'linha', titulo: 'Linha', largura: '54px' },
    { chave: 'trecho', titulo: 'Trecho' },
  ],
  grafo: [
    { chave: 'no', titulo: 'Nó', tipo: 'code' },
    { chave: 'grau', titulo: 'Grau', largura: '54px' },
    { chave: 'entrada', titulo: 'Entra', largura: '54px' },
    { chave: 'saida', titulo: 'Sai', largura: '54px' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
    { chave: 'componente', titulo: 'Comp.', largura: '56px' },
  ],
  sessao: [
    { chave: 'turno', titulo: 'Turno', largura: '54px' },
    { chave: 'papel', titulo: 'Papel' },
    { chave: 'pontos', titulo: 'Nota', largura: '52px' },
    { chave: 'tipo', titulo: 'Classe', tipo: 'pill' },
    { chave: 'decisao', titulo: 'Decisão', tipo: 'pill' },
    { chave: 'motivo', titulo: 'Por quê' },
  ],
  recall: [
    { chave: 'ordem', titulo: '#', largura: '40px' },
    { chave: 'id', titulo: 'Id', tipo: 'code' },
    { chave: 'tipo', titulo: 'Tipo' },
    { chave: 'bm25', titulo: 'BM25', largura: '60px' },
    { chave: 'afinidade', titulo: 'Afinidade', largura: '76px' },
    { chave: 'recencia', titulo: 'Recência', largura: '76px' },
    { chave: 'pontuacao', titulo: 'Pontos', largura: '66px' },
    { chave: 'texto', titulo: 'Texto' },
  ],
  esquecer: [
    { chave: 'id', titulo: 'Id', tipo: 'code' },
    { chave: 'dataset', titulo: 'Dataset' },
    { chave: 'tipo', titulo: 'Tipo' },
    { chave: 'criado', titulo: 'Criado', largura: '84px' },
    { chave: 'alcance', titulo: 'Alcance', largura: '68px' },
    { chave: 'acao', titulo: 'Ação', tipo: 'pill' },
  ],
};

const titulos: Record<MemoriaTab, string> = {
  roteamento: 'Via escolhida',
  entidades: 'Entidades extraídas',
  grafo: 'Grafo medido',
  sessao: 'Lições da sessão',
  recall: 'Recall com lastro',
  esquecer: 'Plano de esquecimento',
  regras: 'Catálogo da memória',
};

type Formato = 'int' | 'dec' | 'pct' | 'score';

const formatar = (valor: number, formato: Formato = 'int'): string => {
  if (formato === 'pct') return `${valor.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 1 })}%`;
  if (formato === 'score') return valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (formato === 'dec') return valor.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
  return valor.toLocaleString('pt-BR');
};

const metricasDoTab: Record<Exclude<MemoriaTab, 'regras'>, Array<{ label: string; chave: string; formato?: Formato }>> = {
  roteamento: [
    { label: 'TERMOS', chave: 'termos' },
    { label: 'REGRAS', chave: 'regras' },
    { label: 'NEGADOS', chave: 'negados' },
    { label: 'PONTOS', chave: 'pontuacao', formato: 'dec' },
    { label: 'MARGEM', chave: 'margem', formato: 'dec' },
    { label: 'PADRÃO', chave: 'fallback' },
  ],
  entidades: [
    { label: 'ENTIDADES', chave: 'entidades' },
    { label: 'LINHAS', chave: 'linhas' },
    { label: 'TRIPLAS', chave: 'triplas' },
    { label: 'NOMES', chave: 'tipo_nome' },
    { label: 'SIGLAS', chave: 'tipo_sigla' },
    { label: 'DATAS', chave: 'tipo_data' },
    { label: 'VALORES', chave: 'tipo_valor' },
  ],
  grafo: [
    { label: 'NÓS', chave: 'nos' },
    { label: 'ARESTAS', chave: 'arestas' },
    { label: 'COMPONENTES', chave: 'componentes' },
    { label: 'COBERTURA', chave: 'cobertura', formato: 'pct' },
    { label: 'CICLOS', chave: 'ciclos' },
    { label: 'ISOLADOS', chave: 'isolados' },
    { label: 'DENSIDADE', chave: 'densidade', formato: 'dec' },
  ],
  sessao: [
    { label: 'TURNOS', chave: 'turnos' },
    { label: 'CANDIDATOS', chave: 'candidatos' },
    { label: 'PROMOVIDOS', chave: 'promovidos' },
    { label: 'DESCARTADOS', chave: 'descartados' },
    { label: 'PENDENTES', chave: 'pendentes' },
    { label: 'DO AGENTE', chave: 'do_agente' },
  ],
  recall: [
    { label: 'MEMÓRIAS', chave: 'memorias' },
    { label: 'RECORTE', chave: 'recorte' },
    { label: 'RESULTADOS', chave: 'resultados' },
    { label: 'DESCARTADOS', chave: 'descartados' },
    { label: 'VENCIDAS', chave: 'vencidas' },
    { label: 'COBERTURA', chave: 'cobertura_media', formato: 'pct' },
    { label: 'TOPO', chave: 'topo', formato: 'score' },
  ],
  esquecer: [
    { label: 'MEMÓRIAS', chave: 'memorias' },
    { label: 'APAGADAS', chave: 'apagadas' },
    { label: 'RESTANTES', chave: 'restantes' },
    { label: 'RAIO', chave: 'raio' },
    { label: 'DEPENDENTES', chave: 'dependentes' },
    { label: 'DATASETS', chave: 'datasets' },
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
          <thead><tr>{cols.map((coluna) => <th key={coluna.chave} style={{ width: coluna.largura }}>{coluna.titulo}</th>)}</tr></thead>
          <tbody>
            {linhas.map((linha, indice) => (
              <tr key={indice}>
                {cols.map((coluna) => {
                  const bruto = linha[coluna.chave];
                  const valor = typeof bruto === 'number' ? formatar(bruto, coluna.chave === 'alcance' ? 'int' : 'dec') : txt(bruto) || '—';
                  if (coluna.tipo === 'code') return <td key={coluna.chave}><code>{valor}</code></td>;
                  if (coluna.tipo === 'pill') return <td key={coluna.chave}><span className={['diagram-state', tom(valor)].filter(Boolean).join(' ')}>{valor}</span></td>;
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

export function MemoriaPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<MemoriaTab>('roteamento');
  const [nivel, setNivel] = useState('full');
  const [consulta, setConsulta] = useState(CONSULTA);
  const [texto, setTexto] = useState(TEXTO);
  const [arestas, setArestas] = useState(ARESTAS);
  const [conversa, setConversa] = useState(CONVERSA);
  const [memorias, setMemorias] = useState(MEMORIAS);
  const [limiar, setLimiar] = useState('4');
  const [via, setVia] = useState('');
  const [dataset, setDataset] = useState('');
  const [limite, setLimite] = useState('10');
  const [ids, setIds] = useState('m2');
  const [escopo, setEscopo] = useState('item');
  const [somenteMemoria, setSomenteMemoria] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);
  const usaMemorias = tab === 'recall' || tab === 'esquecer';

  const trocarTab = (destino: MemoriaTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    const comum = { modo: nivel };
    if (tab === 'roteamento') return { consulta, ...comum };
    if (tab === 'entidades') return { texto, ...comum };
    if (tab === 'grafo') return { arestas, ...comum };
    if (tab === 'sessao') return { conversa, limiar: decimal(limiar, 4), ...comum };
    if (tab === 'recall') return { consulta, memorias, via, dataset, limite: Number(limite) || 10, hoje: HOJE, ...comum };
    if (tab === 'esquecer') return { memorias, ids, dataset, escopo, somente_memoria: somenteMemoria, ...comum };
    return {};
  };

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi calculado.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`memoria.${tab}`, parametros());
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

  const copiar = async (valor: string, titulo: string) => {
    if (!valor) return;
    try {
      await navigator.clipboard.writeText(valor);
      pushToast(titulo, 'O texto está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const rotuloBotao: Record<MemoriaTab, string> = {
    roteamento: 'Escolher a via',
    entidades: 'Extrair entidades',
    grafo: 'Medir o grafo',
    sessao: 'Destilar a sessão',
    recall: 'Buscar com lastro',
    esquecer: 'Planejar o esquecimento',
    regras: 'Abrir o catálogo',
  };

  const bloqueado = num(asObj(resultado?.counts).must) > 0;
  const catalogo = tab === 'regras' ? resultado : null;
  const viasCatalogo = asRows(catalogo?.vias);
  const regrasRota = asRows(asObj(catalogo?.roteamento).regras);
  const limites = asObj(catalogo?.limites);

  return (
    <div className="diagram-section selecao-page revisao-page memoria-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Brain size={22} /></span>
        <div>
          <span className="eyebrow">MEMÓRIA QUE SOBREVIVE À SESSÃO, COM A CONTA À VISTA</span>
          <h2>Lembrar é rotear, ligar e esquecer</h2>
          <p>O cognee existe porque agente sem memória recomeça toda conversa. Lá a via de busca é escolhida por modelo e a lição da sessão sobe por pipeline; aqui a parte determinística é explícita — a via sai da forma da pergunta, a entidade sai de padrão lexical, o grafo é medido, a lição é pontuada antes de promover e o esquecimento mostra o raio de alcance antes de apagar. Nenhum modelo é chamado e nada é gravado.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Via vem da pergunta</strong><span>“Quem” não é “como fazer”.</span></li>
          <li><strong>Entidade sem aresta é menção</strong><span>Grafo é relação declarada.</span></li>
          <li><strong>Sessão promove pouco</strong><span>Regra é o que muda a próxima decisão.</span></li>
          <li><strong>Esquecer tem alcance</strong><span>O que cita o alvo também cai.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações de memória">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => trocarTab(id)} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="diagram-layout">
        <section className="panel diagram-form">
          <header className="diagram-form-head">
            <div>
              <span className="eyebrow">{tabs.find((item) => item.id === tab)?.label.toUpperCase()}</span>
              <h2>{tabs.find((item) => item.id === tab)?.hint}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="diagram-level">
                <span>NÍVEL</span>
                <select value={nivel} onChange={(event) => setNivel(event.target.value)}>
                  {niveis.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>

          <form className="form-stack" onSubmit={executar}>
            {(tab === 'roteamento' || tab === 'recall') && (
              <label className="field">
                <span>A pergunta do agente — a via sai da forma da frase</span>
                <textarea value={consulta} onChange={(event) => setConsulta(event.target.value)} rows={3} spellCheck={false} />
              </label>
            )}

            {tab === 'entidades' && (
              <label className="field">
                <span>Texto — documento, nota ou transcrição</span>
                <textarea value={texto} onChange={(event) => setTexto(event.target.value)} rows={12} spellCheck={false} />
                <small className="selecao-contador">{texto.length.toLocaleString('pt-BR')} caracteres</small>
              </label>
            )}

            {tab === 'grafo' && (
              <label className="field">
                <span>Arestas — <code>A -&gt; relação -&gt; B</code>, uma por linha; linha sozinha é nó isolado</span>
                <textarea value={arestas} onChange={(event) => setArestas(event.target.value)} rows={10} spellCheck={false} />
              </label>
            )}

            {tab === 'sessao' && (
              <>
                <label className="field">
                  <span>Conversa — <code>usuário:</code> e <code>agente:</code>, um turno por bloco</span>
                  <textarea value={conversa} onChange={(event) => setConversa(event.target.value)} rows={12} spellCheck={false} />
                </label>
                <label className="field">
                  <span>Limiar de promoção (1–10)</span>
                  <input type="number" min={1} max={10} step={0.5} value={limiar} onChange={(event) => setLimiar(event.target.value)} />
                </label>
              </>
            )}

            {usaMemorias && (
              <label className="field">
                <span>Memórias — <code>id | tipo | criado | fonte | dataset | texto</code></span>
                <textarea value={memorias} onChange={(event) => setMemorias(event.target.value)} rows={10} spellCheck={false} className="memoria-conjunto" />
                <small className="selecao-contador">{memorias.split('\n').filter(Boolean).length} linha(s)</small>
              </label>
            )}

            {tab === 'recall' && (
              <div className="selecao-filtros">
                <label>
                  <span>Via</span>
                  <select value={via} onChange={(event) => setVia(event.target.value)}>
                    {vias.map((item) => <option key={item || 'auto'} value={item}>{item || 'rotear pela pergunta'}</option>)}
                  </select>
                </label>
                <label><span>Dataset</span><input value={dataset} onChange={(event) => setDataset(event.target.value)} placeholder="todos" /></label>
                <label><span>Resultados</span><input type="number" min={1} max={50} value={limite} onChange={(event) => setLimite(event.target.value)} /></label>
              </div>
            )}

            {tab === 'esquecer' && (
              <>
                <div className="selecao-filtros">
                  <label>
                    <span>Escopo</span>
                    <select value={escopo} onChange={(event) => setEscopo(event.target.value)}>
                      <option value="item">item</option>
                      <option value="dataset">dataset</option>
                      <option value="tudo">tudo</option>
                    </select>
                  </label>
                  <label><span>Ids</span><input value={ids} onChange={(event) => setIds(event.target.value)} placeholder="m2, m4" /></label>
                  <label><span>Dataset</span><input value={dataset} onChange={(event) => setDataset(event.target.value)} placeholder="atlas" /></label>
                </div>
                <label className="memoria-check">
                  <input type="checkbox" checked={somenteMemoria} onChange={(event) => setSomenteMemoria(event.target.checked)} />
                  <span>Só a memória — remove grafo e vetor e mantém o arquivo bruto</span>
                </label>
              </>
            )}

            {tab === 'regras' && (
              <p className="diagram-empty"><GitFork size={14} />O catálogo mostra vias, pesos, tipos, limites e a fórmula do recall — sem calcular nada.</p>
            )}

            <div className="selecao-acoes">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Play size={16} />}
                {busy ? 'Calculando…' : rotuloBotao[tab]}
              </button>
              <button type="button" className="button ghost" onClick={() => { setConsulta(CONSULTA); setTexto(TEXTO); setArestas(ARESTAS); setConversa(CONVERSA); setMemorias(MEMORIAS); setLimiar('4'); setVia(''); setDataset(''); setIds('m2'); setEscopo('item'); setSomenteMemoria(false); }}>
                Restaurar amostra
              </button>
            </div>
            {erro && <p className="diagram-error" role="alert"><AlertTriangle size={14} />{erro}</p>}
          </form>
        </section>

        <section className="panel diagram-result">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h3>{titulos[tab]}</h3>
            </div>
            {resultado && markdown && (
              <button type="button" className="button ghost" onClick={() => void copiar(markdown, 'Parecer copiado')}><Copy size={14} />Copiar parecer</button>
            )}
          </header>

          {!resultado && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <Brain size={14} />}
              {busy ? 'Lendo a memória…' : 'A amostra traz memórias com data, grafo com ciclo e sessão com lição: rode para ver cada decisão.'}
            </p>
          )}

          {resultado && tab !== 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                {metricasDoTab[tab].map((metrica) => (
                  <Metric key={metrica.chave} label={metrica.label} value={formatar(num(asObj(resultado.metrics)[metrica.chave]), metrica.formato)} />
                ))}
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>
              {tab === 'recall' && (
                <p className="memoria-via">
                  <Route size={14} />
                  Via <code>{txt(asObj(resultado.metrics).via)}</code> · dataset <code>{txt(asObj(resultado.metrics).dataset)}</code>
                  {num(asObj(resultado.metrics).roteada) ? ' · roteada pela pergunta' : ' · declarada'}
                  <Clock size={14} />
                  Hoje {HOJE}
                </p>
              )}
              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(resultado.rows)} />
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}

          {resultado && tab === 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                <Metric label="VIAS" value={formatar(viasCatalogo.length)} />
                <Metric label="REGRAS" value={formatar(regrasRota.length)} />
                <Metric label="ENTRADAS" value={formatar(num(limites.entradas))} />
                <Metric label="ARESTAS" value={formatar(num(limites.arestas))} />
                <Metric label="TURNOS" value={formatar(num(limites.turnos))} />
                <Metric label="VERSÃO" value={txt(catalogo?.versao)} />
              </div>
              <Verdict blocked={false}>{txt(asObj(catalogo).principio) || 'Catálogo publicado pela skill.'}</Verdict>
              <Tabela
                titulo="Vias e prioridade"
                colunas={[
                  { chave: 'via', titulo: 'Via', tipo: 'code' },
                  { chave: 'prioridade', titulo: 'Prioridade', largura: '90px' },
                  { chave: 'padrao', titulo: 'Padrão', largura: '70px' },
                ]}
                linhas={viasCatalogo.map((item) => ({ ...item, padrao: item.padrao ? 'sim' : 'não' }))}
              />
              <Tabela
                titulo="Regras de roteamento"
                colunas={[
                  { chave: 'via', titulo: 'Via', tipo: 'code' },
                  { chave: 'regra', titulo: 'Regra' },
                  { chave: 'peso', titulo: 'Peso', largura: '52px' },
                  { chave: 'padrao', titulo: 'Padrão', tipo: 'code' },
                ]}
                linhas={regrasRota}
              />
              <Tabela
                titulo="Pesos da destilação"
                colunas={[
                  { chave: 'sinal', titulo: 'Sinal' },
                  { chave: 'peso', titulo: 'Peso', largura: '70px' },
                ]}
                linhas={Object.entries(asObj(asObj(catalogo?.sessao).pesos)).map(([sinal, peso]) => ({ sinal, peso }))}
              />
              <Tabela
                titulo="Escopos de esquecimento"
                colunas={[{ chave: 'escopo', titulo: 'Escopo', tipo: 'pill' }]}
                linhas={asList(asObj(catalogo?.esquecimento).escopos).map((item) => ({ escopo: item }))}
              />
              {asObj(catalogo?.origem).projeto ? (
                <p className="memoria-origem">
                  <Network size={14} />
                  Insumo: <code>{txt(asObj(catalogo?.origem).projeto)}</code> — licença {txt(asObj(catalogo?.origem).licenca)} · operações{' '}
                  {asList(asObj(catalogo?.origem).operacoes).join(', ')}
                </p>
              ) : null}
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={catalogo?.deixado_de_fora} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
