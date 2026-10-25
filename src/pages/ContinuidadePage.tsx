import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  DoorClosed,
  FileClock,
  GitFork,
  KeyRound,
  Layers,
  LoaderCircle,
  Play,
  RotateCcw,
  Siren,
  Stethoscope,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../continuidade.css';

type ContinuidadeTab = 'fases' | 'portao' | 'retomada' | 'injecao' | 'livro' | 'medico' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: ContinuidadeTab; label: string; hint: string; icon: typeof KeyRound }> = [
  { id: 'fases', label: 'Fases', hint: 'Um status por fase', icon: Layers },
  { id: 'portao', label: 'Portão', hint: 'Bloquear ou deixar parar', icon: DoorClosed },
  { id: 'retomada', label: 'Retomada', hint: 'Depois do /clear', icon: RotateCcw },
  { id: 'injecao', label: 'Injeção', hint: 'O que volta por turno', icon: ClipboardCheck },
  { id: 'livro', label: 'Livro', hint: 'Evento por linha', icon: FileClock },
  { id: 'medico', label: 'Médico', hint: 'O diretório inteiro', icon: Stethoscope },
  { id: 'regras', label: 'Regras', hint: 'Guardas e limites', icon: GitFork },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const PLANO = `# Task Plan: Atlas

## Goal

Migrar o índice para o pgvector sem downtime.

## Next Step

Escrever a migration 0042.

## Current Phase

Phase 2

## Phases

### Phase 1: Descoberta

- [x] Levantar requisitos
- [x] Documentar achados
- **Status:** complete

### Phase 2: Implementação

- [ ] Escrever migration
- [ ] Rodar teste de carga
- **Status:** in_progress

### Phase 3: Entrega

- [ ] Revisar
- **Status:** pending

## Decisions Made

| Decisão | Motivo |
| --- | --- |
| pgvector | já está no cluster |`;

const PROGRESSO = `# Progress Log

## Session: 2026-10-23

### Phase 1: Descoberta

- **Status:** complete
- **Started:** 2026-10-23T09:00:00Z
- Actions taken:
  - Li o esquema atual
- Files created/modified:
  - \`docs/esquema.md\`

### Phase 2: Implementação

- **Status:** in_progress
- Actions taken:
  - Escrevi o rascunho em \`db/0042.sql\`

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
|      |       |          |        |        |`;

const ACHADOS = `# Findings & Decisions

## Requirements

- Migrar sem downtime

## Research Findings

- pgvector aceita índice HNSW desde a 0.5

## Technical Decisions

| Decisão | Motivo |
| --- | --- |
| HNSW | recall melhor com o mesmo custo |`;

const LIVRO = `{"tick":1,"ts":"2026-10-23T09:00:00Z","agent":"main","phase":"1","event":"progress","summary":"comecei a leitura","files":[]}
{"tick":2,"ts":"2026-10-23T09:05:00Z","agent":"main","phase":"1","event":"phase_complete","summary":"fase 1 fechada","files":["docs/esquema.md"]}
{"tick":3,"ts":"2026-10-23T09:10:00Z","agent":"main","phase":"2","event":"progress","summary":"migration escrita","files":["db/0042.sql"]}`;

const DIRETORIO = `>>> atlas/task_plan.md
${PLANO}
>>> atlas/progress.md
${PROGRESSO}
>>> atlas/findings.md
${ACHADOS}
>>> atlas/ledger-main.jsonl
${LIVRO}
>>> atlas/.attest
9f2c1a77c0de5512
>>> beta/task_plan.md
# Task Plan: Atlas

## Phases

### Phase 1: Rascunho

- **Status:** in_progress`;

const asObj = (valor: unknown): Row => (typeof valor === 'object' && valor !== null && !Array.isArray(valor) ? valor as Row : {});
const asRows = (valor: unknown): Row[] => (Array.isArray(valor) ? valor.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (valor: unknown): string[] => (Array.isArray(valor) ? valor.map((item) => String(item)) : []);
const txt = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));
const num = (valor: unknown): number => (typeof valor === 'number' ? valor : Number(valor ?? 0));
const grupos: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const tom = (valor: string): string => {
  if (['must', 'obrigatório', 'block', 'para', 'diverge', 'incompleto', 'sem plano', 'json inválido', 'revisar', 'não', '?', 'ausente'].includes(valor)) return 'is-danger';
  if (['should', 'corrigir', 'allow', 'passa', 'sem registro', 'sobrando'].includes(valor)) return 'is-warning';
  if (['nice', 'opcional', 'ok', 'completo', 'registrada', 'sim', 'complete'].includes(valor)) return 'is-ok';
  return '';
};

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill'; largura?: string };

const colunas: Record<Exclude<ContinuidadeTab, 'regras'>, Coluna[]> = {
  fases: [
    { chave: 'numero', titulo: '#', largura: '36px' },
    { chave: 'titulo', titulo: 'Título' },
    { chave: 'status', titulo: 'Status', tipo: 'pill' },
    { chave: 'marcas', titulo: 'Marcas', largura: '58px' },
    { chave: 'criterios', titulo: 'Critérios', largura: '66px' },
    { chave: 'feitos', titulo: 'Feitos', largura: '54px' },
    { chave: 'linha', titulo: 'Linha', largura: '50px' },
  ],
  portao: [
    { chave: 'ordem', titulo: '#', largura: '36px' },
    { chave: 'guarda', titulo: 'Guarda' },
    { chave: 'resultado', titulo: 'Resultado', tipo: 'pill' },
    { chave: 'detalhe', titulo: 'Detalhe' },
  ],
  retomada: [
    { chave: 'fase', titulo: '#', largura: '36px' },
    { chave: 'titulo', titulo: 'Título' },
    { chave: 'plano', titulo: 'No plano', tipo: 'pill' },
    { chave: 'progresso', titulo: 'No progresso', tipo: 'pill' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
  ],
  injecao: [
    { chave: 'fonte', titulo: 'Fonte', tipo: 'code' },
    { chave: 'modo', titulo: 'Modo' },
    { chave: 'bytes', titulo: 'Bytes', largura: '72px' },
    { chave: 'teto', titulo: 'Teto', largura: '72px' },
  ],
  livro: [
    { chave: 'linha', titulo: 'Linha', largura: '50px' },
    { chave: 'tick', titulo: 'Tick', largura: '50px' },
    { chave: 'agente', titulo: 'Agente' },
    { chave: 'evento', titulo: 'Evento', tipo: 'pill' },
    { chave: 'fase', titulo: 'Fase', largura: '52px' },
    { chave: 'resumo', titulo: 'Resumo' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
  ],
  medico: [
    { chave: 'plano', titulo: 'Plano', tipo: 'code' },
    { chave: 'arquivos', titulo: 'Arq.', largura: '46px' },
    { chave: 'fases', titulo: 'Fases', largura: '50px' },
    { chave: 'completas', titulo: 'Compl.', largura: '54px' },
    { chave: 'ativa', titulo: 'Ativa' },
    { chave: 'livro', titulo: 'Livro', tipo: 'pill', largura: '60px' },
    { chave: 'attest', titulo: 'Attest', tipo: 'pill', largura: '64px' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
  ],
};

const titulos: Record<ContinuidadeTab, string> = {
  fases: 'Fases do plano',
  portao: 'Portão de conclusão',
  retomada: 'Retomada depois de limpar a sessão',
  injecao: 'Injeção por turno',
  livro: 'Livro de execução',
  medico: 'Diagnóstico do diretório',
  regras: 'Catálogo de continuidade',
};

const rotuloBotao: Record<ContinuidadeTab, string> = {
  fases: 'Ler as fases',
  portao: 'Aplicar o portão',
  retomada: 'Reconstruir o estado',
  injecao: 'Montar o bloco',
  livro: 'Validar o livro',
  medico: 'Diagnosticar',
  regras: 'Abrir o catálogo',
};

const metricas: Record<Exclude<ContinuidadeTab, 'regras'>, Array<{ label: string; chave: string }>> = {
  fases: [
    { label: 'FASES', chave: 'fases' },
    { label: 'CONCLUÍDAS', chave: 'completas' },
    { label: 'EM ANDAMENTO', chave: 'emAndamento' },
    { label: 'PENDENTES', chave: 'pendentes' },
    { label: 'CRITÉRIOS', chave: 'criterios' },
    { label: 'FEITOS', chave: 'feitos' },
  ],
  portao: [
    { label: 'BLOQUEIOS', chave: 'bloqueios' },
    { label: 'TETO', chave: 'cap' },
    { label: 'RESTANTES', chave: 'restantes' },
    { label: 'FASES', chave: 'fases' },
    { label: 'CONCLUÍDAS', chave: 'completas' },
    { label: 'LIVRO', chave: 'linhasLedger' },
  ],
  retomada: [
    { label: 'FASES', chave: 'fases' },
    { label: 'REGISTRADAS', chave: 'registradas' },
    { label: 'DIVERGENTES', chave: 'divergentes' },
    { label: 'DATAS', chave: 'datas' },
    { label: 'PERGUNTAS', chave: 'perguntas' },
    { label: 'ARQUIVOS', chave: 'arquivos' },
  ],
  injecao: [
    { label: 'PLANO', chave: 'bytesPlano' },
    { label: 'VISÃO', chave: 'bytesVisao' },
    { label: 'PROGRESSO', chave: 'bytesProgresso' },
    { label: 'BLOCO', chave: 'bytesBloco' },
    { label: 'ORÇAMENTO', chave: 'orcamento' },
    { label: 'ECONOMIA', chave: 'economia' },
  ],
  livro: [
    { label: 'ENTRADAS', chave: 'entradas' },
    { label: 'VÁLIDAS', chave: 'validas' },
    { label: 'AGENTES', chave: 'agentes' },
    { label: 'TICK INICIAL', chave: 'primeiroTick' },
    { label: 'TICK FINAL', chave: 'ultimoTick' },
    { label: 'PROBLEMAS', chave: 'problemas' },
  ],
  medico: [
    { label: 'PLANOS', chave: 'planos' },
    { label: 'COMPLETOS', chave: 'completos' },
    { label: 'SEM LIVRO', chave: 'semLivro' },
    { label: 'SEM ATTEST', chave: 'semAttest' },
    { label: 'COM ATIVA', chave: 'comAtiva' },
    { label: 'DUPLICADOS', chave: 'duplicados' },
  ],
};

const formatar = (valor: number): string => valor.toLocaleString('pt-BR');

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
                  const valor = typeof bruto === 'boolean' ? (bruto ? 'sim' : 'não') : (typeof bruto === 'number' ? formatar(bruto) : txt(bruto) || '—');
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

export function ContinuidadePage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<ContinuidadeTab>('fases');
  const [nivel, setNivel] = useState('full');
  const [plano, setPlano] = useState(PLANO);
  const [progresso, setProgresso] = useState(PROGRESSO);
  const [achados, setAchados] = useState(ACHADOS);
  const [ledger, setLedger] = useState(LIVRO);
  const [ligado, setLigado] = useState(true);
  const [bloqueios, setBloqueios] = useState('1');
  const [cap, setCap] = useState('20');
  const [anteriores, setAnteriores] = useState('0');
  const [stopAtivo, setStopAtivo] = useState(false);
  const [orcamento, setOrcamento] = useState('65536');
  const [linhas, setLinhas] = useState('120');
  const [agente, setAgente] = useState('');
  const [diretorio, setDiretorio] = useState(DIRETORIO);
  const [ativo, setAtivo] = useState('');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);

  const trocarTab = (destino: ContinuidadeTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    if (tab === 'regras') return {};
    if (tab === 'fases') return { plano, modo: nivel };
    if (tab === 'portao') {
      return {
        plano,
        ligado,
        bloqueios: Number(bloqueios) || 0,
        cap: Number(cap) || 20,
        ledger,
        linhas_anteriores: Number(anteriores) || 0,
        stop_ativo: stopAtivo,
        modo: nivel,
      };
    }
    if (tab === 'retomada') return { plano, progresso, achados, modo: nivel };
    if (tab === 'injecao') {
      return { plano, progresso, ledger, orcamento: Number(orcamento) || 65536, linhas: Number(linhas) || 120, modo: nivel };
    }
    if (tab === 'livro') return { ledger, agente, modo: nivel };
    return { planos: diretorio, ativo, modo: nivel };
  };

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi calculado.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`continuidade.${tab}`, parametros());
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

  const bloqueado = num(asObj(resultado?.counts).must) > 0;
  const catalogo = tab === 'regras' ? resultado : null;
  const guardas = asRows(catalogo?.guardas_do_portao);
  const regras = asList(catalogo?.regras);
  const eventos = asList(catalogo?.eventos);
  const limites = asObj(catalogo?.limites);
  const bloco = txt(resultado?.bloco);
  const respostas = asObj(resultado?.respostas);

  return (
    <div className="diagram-section selecao-page revisao-page continuidade-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><KeyRound size={22} /></span>
        <div>
          <span className="eyebrow">O PLANO CONTINUA VALENDO DEPOIS QUE A SESSÃO ACABA</span>
          <h2>Continuidade é o arquivo saber onde parou</h2>
          <p>A 0.6.0 já criava e retomava planos em disco. O que faltava é o outro lado do padrão: fase com um status só, portão que decide quando <em>não</em> bloquear a parada, retomada depois de <code>/clear</code>, bloco reinjetado que cabe no orçamento, livro append-only e diagnóstico do diretório inteiro. Tudo aqui é leitura: nada é escrito, nenhum hook é instalado e nenhum agente é bloqueado.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Uma marca por fase</strong><span>Duas adiantam a conclusão.</span></li>
          <li><strong>Portão sabe ceder</strong><span>Sem avanço, bloquear só repete.</span></li>
          <li><strong>Bloco estável</strong><span>Hora zerada, corte declarado.</span></li>
          <li><strong>Seletor é vínculo</strong><span>Plano inexistente não é substituído.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações de continuidade">
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
            {tab === 'medico' ? (
              <>
                <label className="field">
                  <span>Diretório — <code>&gt;&gt;&gt; &lt;plano&gt;/&lt;arquivo&gt;</code> seguido do conteúdo</span>
                  <textarea value={diretorio} onChange={(event) => setDiretorio(event.target.value)} rows={16} spellCheck={false} className="continuidade-arquivo" />
                  <small className="selecao-contador">{diretorio.split('\n').filter(Boolean).length} linha(s)</small>
                </label>
                <label className="field">
                  <span>Plano ativo declarado — vazio deixa a ambiguidade aparecer</span>
                  <input value={ativo} onChange={(event) => setAtivo(event.target.value)} placeholder="atlas" />
                </label>
              </>
            ) : (
              <label className="field">
                <span>{tab === 'livro' ? 'Livro — uma entrada JSON por linha' : 'task_plan.md'}</span>
                <textarea
                  value={tab === 'livro' ? ledger : plano}
                  onChange={(event) => (tab === 'livro' ? setLedger : setPlano)(event.target.value)}
                  rows={14}
                  spellCheck={false}
                  className="continuidade-arquivo"
                />
                <small className="selecao-contador">
                  {((tab === 'livro' ? ledger : plano).split('\n').filter(Boolean)).length} linha(s)
                </small>
              </label>
            )}

            {(tab === 'retomada' || tab === 'injecao') && (
              <label className="field">
                <span>progress.md — <code>## Session: AAAA-MM-DD</code> e as fases</span>
                <textarea value={progresso} onChange={(event) => setProgresso(event.target.value)} rows={10} spellCheck={false} className="continuidade-arquivo" />
              </label>
            )}

            {tab === 'retomada' && (
              <label className="field">
                <span>findings.md — requisito, achado e decisão</span>
                <textarea value={achados} onChange={(event) => setAchados(event.target.value)} rows={8} spellCheck={false} className="continuidade-arquivo" />
              </label>
            )}

            {(tab === 'portao' || tab === 'injecao') && (
              <label className="field">
                <span>Livro — uma entrada JSON por linha (deixe vazio para usar a cauda do progresso)</span>
                <textarea value={ledger} onChange={(event) => setLedger(event.target.value)} rows={6} spellCheck={false} className="continuidade-arquivo" />
              </label>
            )}

            {tab === 'portao' && (
              <>
                <label className="continuidade-check">
                  <input type="checkbox" checked={ligado} onChange={(event) => setLigado(event.target.checked)} />
                  <span>Modo <code>gate</code> declarado — sem isso o portão só informa</span>
                </label>
                <label className="continuidade-check">
                  <input type="checkbox" checked={stopAtivo} onChange={(event) => setStopAtivo(event.target.checked)} />
                  <span>Parada forçada (<code>stop_hook_active</code>) — desliga o bloqueio</span>
                </label>
                <div className="selecao-filtros">
                  <label><span>Bloqueios</span><input type="number" min={0} max={1000} value={bloqueios} onChange={(event) => setBloqueios(event.target.value)} /></label>
                  <label><span>Teto</span><input type="number" min={1} max={1000} value={cap} onChange={(event) => setCap(event.target.value)} /></label>
                  <label><span>Linhas no último bloqueio</span><input type="number" min={0} value={anteriores} onChange={(event) => setAnteriores(event.target.value)} /></label>
                </div>
              </>
            )}

            {tab === 'injecao' && (
              <div className="selecao-filtros">
                <label><span>Orçamento (bytes)</span><input type="number" min={512} step={512} value={orcamento} onChange={(event) => setOrcamento(event.target.value)} /></label>
                <label><span>Linhas do cabeçalho</span><input type="number" min={5} max={2000} value={linhas} onChange={(event) => setLinhas(event.target.value)} /></label>
              </div>
            )}

            {tab === 'livro' && (
              <label className="field">
                <span>Agente — vazio lê todos os livros colados</span>
                <input value={agente} onChange={(event) => setAgente(event.target.value)} placeholder="main" />
              </label>
            )}

            {tab === 'regras' && (
              <p className="diagram-empty"><GitFork size={14} />O catálogo mostra arquivos, formatos de status, eventos, guardas, orçamento e limites — sem calcular nada.</p>
            )}

            <div className="selecao-acoes">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Play size={16} />}
                {busy ? 'Calculando…' : rotuloBotao[tab]}
              </button>
              <button type="button" className="button ghost" onClick={() => { setPlano(PLANO); setProgresso(PROGRESSO); setAchados(ACHADOS); setLedger(LIVRO); setDiretorio(DIRETORIO); setAtivo(''); setAgente(''); setLigado(true); setBloqueios('1'); setCap('20'); setAnteriores('0'); setStopAtivo(false); setOrcamento('65536'); setLinhas('120'); }}>
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
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <KeyRound size={14} />}
              {busy ? 'Lendo o plano…' : 'A amostra traz plano com fase em andamento, progresso divergente e livro válido: rode para ver onde cada regra pega.'}
            </p>
          )}

          {resultado && tab !== 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                {metricas[tab].map((metrica) => (
                  <Metric key={metrica.chave} label={metrica.label} value={formatar(num(asObj(resultado.metrics)[metrica.chave]))} />
                ))}
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>

              {tab === 'portao' && (
                <p className="continuidade-decisao">
                  <DoorClosed size={14} />
                  Decisão <code>{txt(resultado.decisao)}</code> — {txt(resultado.motivo)}
                </p>
              )}

              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(resultado.rows)} />

              {tab === 'retomada' && Object.keys(respostas).length > 0 && (
                <Tabela
                  titulo="Cinco perguntas de reboot"
                  colunas={[{ chave: 'pergunta', titulo: 'Pergunta' }, { chave: 'resposta', titulo: 'Resposta' }]}
                  linhas={Object.entries(respostas).map(([pergunta, resposta]) => ({ pergunta, resposta }))}
                />
              )}

              {tab === 'injecao' && bloco && (
                <div className="continuidade-bloco">
                  <h4>BLOCO REINJETADO — <code>{txt(resultado.hash)}</code></h4>
                  <pre>{bloco}</pre>
                  <small>{num(asObj(resultado.metrics).bytesBloco).toLocaleString('pt-BR')} bytes · nada foi escrito no contexto de nenhum agente</small>
                </div>
              )}

              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}

          {resultado && tab === 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                <Metric label="GUARDAS" value={formatar(guardas.length)} />
                <Metric label="EVENTOS" value={formatar(eventos.length)} />
                <Metric label="REGRAS" value={formatar(regras.length)} />
                <Metric label="ORÇAMENTO" value={formatar(num(limites.orcamento))} />
                <Metric label="BLOQUEIOS" value={formatar(num(limites.bloqueios))} />
                <Metric label="VERSÃO" value={txt(catalogo?.versao)} />
              </div>
              <Verdict blocked={false}>{txt(asObj(catalogo).principio) || 'Catálogo publicado pela skill.'}</Verdict>
              <Tabela
                titulo="Guardas do portão"
                colunas={[
                  { chave: 'ordem', titulo: '#', largura: '36px' },
                  { chave: 'guarda', titulo: 'Guarda' },
                  { chave: 'permite_parada', titulo: 'Permite parada quando' },
                ]}
                linhas={guardas}
              />
              <Tabela
                titulo="Regras da camada"
                colunas={[{ chave: 'regra', titulo: 'Regra' }]}
                linhas={regras.map((item) => ({ regra: item }))}
              />
              <Tabela
                titulo="Arquivos do padrão"
                colunas={[{ chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' }, { chave: 'papel', titulo: 'Papel' }]}
                linhas={Object.entries(asObj(catalogo?.arquivos)).map(([arquivo, papel]) => ({ arquivo, papel }))}
              />
              <Tabela
                titulo="Limites"
                colunas={[{ chave: 'chave', titulo: 'Limite', tipo: 'code' }, { chave: 'valor', titulo: 'Valor', largura: '120px' }]}
                linhas={Object.entries(limites).map(([chave, valor]) => ({ chave, valor }))}
              />
              {asObj(catalogo?.origem).projeto ? (
                <p className="continuidade-origem">
                  <Siren size={14} />
                  Insumo: <code>{txt(asObj(catalogo?.origem).projeto)}</code> — licença {txt(asObj(catalogo?.origem).licenca)} · commit da 0.6.0{' '}
                  <code>{txt(asObj(catalogo?.origem).commit_da_0_6)}</code>
                </p>
              ) : null}
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={catalogo?.nao_faz} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
