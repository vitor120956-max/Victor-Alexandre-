import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  Copy,
  FileCode2,
  GitCompareArrows,
  GitFork,
  Layers,
  LoaderCircle,
  Package,
  Play,
  ShieldCheck,
  Table2,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../portabilidade.css';

type PortabilidadeTab = 'auditar' | 'converter' | 'deriva' | 'colisoes' | 'lote' | 'matriz' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: PortabilidadeTab; label: string; hint: string; icon: typeof ShieldCheck }> = [
  { id: 'auditar', label: 'Auditar', hint: 'Antes de converter', icon: ShieldCheck },
  { id: 'converter', label: 'Converter', hint: 'Um alvo por vez', icon: FileCode2 },
  { id: 'deriva', label: 'Deriva', hint: 'Fonte contra espelho', icon: GitCompareArrows },
  { id: 'colisoes', label: 'Colisões', hint: 'Duas skills, um caminho', icon: Layers },
  { id: 'lote', label: 'Lote', hint: 'Plugin e marketplace', icon: Package },
  { id: 'matriz', label: 'Matriz', hint: 'Skill × ferramenta', icon: Table2 },
  { id: 'regras', label: 'Regras', hint: 'Alvos e limites', icon: GitFork },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const alvos = [
  'claude-code',
  'codex',
  'gemini',
  'openclaw',
  'hermes',
  'vibe',
  'windsurf',
  'opencode',
  'antigravity',
  'cursor',
  'kilocode',
  'augment',
  'aider',
];

const BUNDLE = `>>> engineering/leitor-de-contrato/SKILL.md
---
name: leitor-de-contrato
description: Lê contrato em PDF e devolve cláusula, prazo e multa. Use quando o usuário pedir resumo de contrato.
allowed-tools: Read, Grep
license: MIT
version: 1.0.0
---
# Leitor de contrato

Rode \`scripts/extrair.py --help\` antes de tudo.

Consulte \`references/limites.md\` quando o contrato passar de 200 páginas.
>>> engineering/leitor-de-contrato/scripts/extrair.py
import sys

print("extrai")
>>> engineering/leitor-de-contrato/references/limites.md
# Limites

200 páginas por chamada.
>>> marketing/anuncio-curto/SKILL.md
---
name: anuncio-curto
description: Escreve anúncio de uma linha para o feed. Use quando pedirem texto de campanha.
license: MIT
---
# Anúncio curto

Uma linha, sem jargão.`;

const ESPELHO = `engineering/leitor-de-contrato/SKILL.md | 412 | 9f2c1a77c0de5512 | arquivo
engineering/leitor-de-contrato/scripts/extrair.py | 40 | 12ab34cd56ef7890 | symlink
engineering/leitor-de-contrato/references/limites.md | 45 | 77aa88bb99cc00dd | arquivo
engineering/leitor-de-contrato/references/antigo.md | 120 | 55ee66ff77aa88bb | arquivo`;

const AUTOR = 'Victor Alexandre';
const REPO = 'https://github.com/vitor120956-max/Victor-Alexandre-';

const asObj = (valor: unknown): Row => (typeof valor === 'object' && valor !== null && !Array.isArray(valor) ? valor as Row : {});
const asRows = (valor: unknown): Row[] => (Array.isArray(valor) ? valor.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (valor: unknown): string[] => (Array.isArray(valor) ? valor.map((item) => String(item)) : []);
const txt = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));
const num = (valor: unknown): number => (typeof valor === 'number' ? valor : Number(valor ?? 0));
const grupos: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const tom = (valor: string): string => {
  if (['must', 'obrigatório', 'alterado', 'divergente', 'so-entrada', 'descartar', 'faltando', 'zero'].includes(valor)) return 'is-danger';
  if (['should', 'corrigir', 'copia-identica', 'parcial', 'sobrando', 'reescrever'].includes(valor)) return 'is-warning';
  if (['nice', 'opcional', 'ok', 'igual', 'completo', 'unica', 'copiar', 'gerar'].includes(valor)) return 'is-ok';
  return '';
};

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill'; largura?: string };

const colunas: Record<Exclude<PortabilidadeTab, 'regras'>, Coluna[]> = {
  auditar: [
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'pasta', titulo: 'Pasta' },
    { chave: 'nome_bate', titulo: 'Nome', largura: '58px' },
    { chave: 'arquivos', titulo: 'Arq.', largura: '48px' },
    { chave: 'scripts', titulo: 'Scr.', largura: '48px' },
    { chave: 'referencias', titulo: 'Ref.', largura: '48px' },
    { chave: 'bytes', titulo: 'Bytes', largura: '66px' },
    { chave: 'problemas', titulo: 'Achados', largura: '64px' },
  ],
  converter: [
    { chave: 'origem', titulo: 'Origem' },
    { chave: 'destino', titulo: 'Destino', tipo: 'code' },
    { chave: 'acao', titulo: 'Ação', tipo: 'pill' },
    { chave: 'bytes', titulo: 'Bytes', largura: '66px' },
  ],
  deriva: [
    { chave: 'arquivo', titulo: 'Arquivo' },
    { chave: 'status', titulo: 'Status', tipo: 'pill' },
    { chave: 'fonte', titulo: 'Fonte', largura: '66px' },
    { chave: 'espelho', titulo: 'Espelho', largura: '70px' },
    { chave: 'comparacao', titulo: 'Comparação', largura: '96px' },
  ],
  colisoes: [
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'pastas', titulo: 'Pastas' },
    { chave: 'arquivos', titulo: 'Arq.', largura: '48px' },
    { chave: 'bytes', titulo: 'Bytes', largura: '66px' },
    { chave: 'estado', titulo: 'Estado', tipo: 'pill' },
  ],
  lote: [
    { chave: 'plugin', titulo: 'Plugin', tipo: 'code' },
    { chave: 'skills', titulo: 'Skills', largura: '54px' },
    { chave: 'bytes', titulo: 'Bytes', largura: '70px' },
    { chave: 'keywords', titulo: 'Keywords', largura: '74px' },
    { chave: 'manifesto', titulo: 'Manifesto', largura: '76px' },
  ],
  matriz: [
    { chave: 'skill', titulo: 'Skill', tipo: 'code' },
    { chave: 'alvo', titulo: 'Alvo' },
    { chave: 'estado', titulo: 'Estado', tipo: 'pill' },
    { chave: 'mantidos', titulo: 'Mantidos', largura: '70px' },
    { chave: 'perdidos', titulo: 'Perdidos', largura: '68px' },
    { chave: 'base', titulo: 'Base', tipo: 'code' },
  ],
};

const titulos: Record<PortabilidadeTab, string> = {
  auditar: 'Auditoria do bundle',
  converter: 'Plano de conversão',
  deriva: 'Deriva entre fonte e espelho',
  colisoes: 'Colisões e duplicatas',
  lote: 'Lote para marketplace',
  matriz: 'Matriz de portabilidade',
  regras: 'Catálogo de portabilidade',
};

const rotuloBotao: Record<PortabilidadeTab, string> = {
  auditar: 'Auditar o bundle',
  converter: 'Montar o plano',
  deriva: 'Comparar com o espelho',
  colisoes: 'Caçar colisão',
  lote: 'Montar o lote',
  matriz: 'Cruzar a matriz',
  regras: 'Abrir o catálogo',
};

const metricas: Record<Exclude<PortabilidadeTab, 'regras'>, Array<{ label: string; chave: string }>> = {
  auditar: [
    { label: 'SKILLS', chave: 'skills' },
    { label: 'ARQUIVOS', chave: 'arquivos' },
    { label: 'SCRIPTS', chave: 'scripts' },
    { label: 'REFERÊNCIAS', chave: 'referencias' },
    { label: 'SOLTOS', chave: 'soltos' },
    { label: 'MUST', chave: 'must' },
  ],
  converter: [
    { label: 'SKILLS', chave: 'skills' },
    { label: 'DESTINO', chave: 'arquivosDestino' },
    { label: 'DESCARTADOS', chave: 'descartados' },
    { label: 'BYTES', chave: 'bytes' },
    { label: 'CAMINHO', chave: 'caminhoMaximo' },
    { label: 'MUST', chave: 'must' },
  ],
  deriva: [
    { label: 'FONTE', chave: 'fonte' },
    { label: 'ESPELHO', chave: 'espelho' },
    { label: 'IGUAIS', chave: 'iguais' },
    { label: 'ALTERADOS', chave: 'alterados' },
    { label: 'FALTANDO', chave: 'faltando' },
    { label: 'SOBRANDO', chave: 'sobrando' },
  ],
  colisoes: [
    { label: 'SKILLS', chave: 'skills' },
    { label: 'NOMES', chave: 'nomes' },
    { label: 'DUPLICADAS', chave: 'duplicadas' },
    { label: 'DIVERGENTES', chave: 'divergentes' },
    { label: 'SLUGS', chave: 'slugs' },
    { label: 'ARQUIVOS', chave: 'arquivos' },
  ],
  lote: [
    { label: 'PLUGINS', chave: 'plugins' },
    { label: 'SKILLS', chave: 'skills' },
    { label: 'BYTES', chave: 'bytes' },
    { label: 'MAIOR', chave: 'maiorPlugin' },
    { label: 'MANIFESTOS', chave: 'manifestos' },
    { label: 'MUST', chave: 'must' },
  ],
  matriz: [
    { label: 'SKILLS', chave: 'skills' },
    { label: 'ALVOS', chave: 'alvos' },
    { label: 'COMPLETOS', chave: 'completos' },
    { label: 'PARCIAIS', chave: 'parciais' },
    { label: 'SEM APOIO', chave: 'perdidos' },
    { label: 'PARES', chave: 'pares' },
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

function Saida({ arquivos }: { arquivos: Row[] }) {
  const primeiro = arquivos[0];
  if (!primeiro) return null;
  return (
    <div className="portabilidade-saida">
      <h4>ARQUIVO PROPOSTO — <code>{txt(primeiro.caminho)}</code></h4>
      <pre>{txt(primeiro.conteudo) || '(sem conteúdo textual: cópia binária)'}</pre>
      <small>{arquivos.length.toLocaleString('pt-BR')} arquivo(s) no plano · nada foi escrito no disco</small>
    </div>
  );
}

export function PortabilidadePage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<PortabilidadeTab>('auditar');
  const [nivel, setNivel] = useState('full');
  const [bundle, setBundle] = useState(BUNDLE);
  const [espelho, setEspelho] = useState(ESPELHO);
  const [alvo, setAlvo] = useState('claude-code');
  const [alvoAuditar, setAlvoAuditar] = useState('');
  const [alvosLista, setAlvosLista] = useState('claude-code,cursor,aider');
  const [marketplace, setMarketplace] = useState('skills-do-projeto');
  const [versao, setVersao] = useState('1.0.0');
  const [autor, setAutor] = useState(AUTOR);
  const [repo, setRepo] = useState(REPO);
  const [licenca, setLicenca] = useState('MIT');
  const [dominio, setDominio] = useState('');
  const [estrito, setEstrito] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);

  const trocarTab = (destino: PortabilidadeTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    if (tab === 'regras') return {};
    if (tab === 'auditar') return { arquivos: bundle, alvo: alvoAuditar, modo: nivel };
    if (tab === 'converter') return { arquivos: bundle, alvo, modo: nivel };
    if (tab === 'deriva') return { arquivos: bundle, espelho, estrito, modo: nivel };
    if (tab === 'colisoes') return { arquivos: bundle, modo: nivel };
    if (tab === 'lote') return { arquivos: bundle, marketplace, versao, autor, repo, licenca, dominio, modo: nivel };
    return { arquivos: bundle, alvos: alvosLista, modo: nivel };
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
      const resposta = await executeSkill(`portabilidade.${tab}`, parametros());
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
  const alvosCatalogo = asRows(catalogo?.alvos);
  const regras = asList(catalogo?.regras);
  const limites = asObj(catalogo?.limites);
  const saida = asRows(resultado?.saida);

  return (
    <div className="diagram-section selecao-page revisao-page portabilidade-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Boxes size={22} /></span>
        <div>
          <span className="eyebrow">SKILL QUE RODA EM TREZE FERRAMENTAS SEM PERDER O SENTIDO</span>
          <h2>Portabilidade é declarar a perda</h2>
          <p>O claude-skills publica 398 skills para Claude Code, Codex, Gemini, Cursor, Aider e mais nove ferramentas, com scripts de conversão, espelho e verificação de manifesto. Aqui a parte determinística fica explícita: cada alvo tem formato declarado, a conversão vira plano arquivo a arquivo, a deriva entre fonte e espelho é medida por hash, a colisão é vista pelo destino e o plugin de marketplace só sai com as oito chaves do schema. Nada é escrito, copiado ou instalado.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Alvo não é pasta</strong><span>Regra, espelho e convenção mudam o que acompanha.</span></li>
          <li><strong>Conversão é plano</strong><span>Copiar, reescrever, embutir ou descartar — declarado.</span></li>
          <li><strong>Deriva é bloqueio</strong><span>Espelho divergente é versão publicada errada.</span></li>
          <li><strong>Manifesto é rígido</strong><span>Uma chave a mais derruba o plugin inteiro.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações de portabilidade">
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
            {tab !== 'regras' && tab !== 'deriva' && (
              <label className="field">
                <span>Bundle — <code>&gt;&gt;&gt; caminho</code> seguido do conteúdo, ou <code>caminho | bytes | sha256</code></span>
                <textarea value={bundle} onChange={(event) => setBundle(event.target.value)} rows={14} spellCheck={false} className="portabilidade-bundle" />
                <small className="selecao-contador">{bundle.split('\n').filter(Boolean).length} linha(s) · {bundle.length.toLocaleString('pt-BR')} caracteres</small>
              </label>
            )}

            {tab === 'deriva' && (
              <>
                <label className="field">
                  <span>Fonte — a árvore do repositório</span>
                  <textarea value={bundle} onChange={(event) => setBundle(event.target.value)} rows={10} spellCheck={false} className="portabilidade-bundle" />
                </label>
                <label className="field">
                  <span>Espelho — <code>caminho | bytes | sha256 | arquivo|symlink</code>, um por linha</span>
                  <textarea value={espelho} onChange={(event) => setEspelho(event.target.value)} rows={8} spellCheck={false} className="portabilidade-bundle" />
                </label>
                <label className="portabilidade-check">
                  <input type="checkbox" checked={estrito} onChange={(event) => setEstrito(event.target.checked)} />
                  <span>Estrito — arquivo sem hash nem conteúdo conta como divergente</span>
                </label>
              </>
            )}

            {tab === 'auditar' && (
              <label className="field">
                <span>Alvo — vazio audita para todos; com alvo, aponta o campo que aquele formato descarta</span>
                <select value={alvoAuditar} onChange={(event) => setAlvoAuditar(event.target.value)}>
                  <option value="">todos os alvos</option>
                  {alvos.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            )}

            {tab === 'converter' && (
              <label className="field">
                <span>Alvo — o formato que define caminho e front matter do plano</span>
                <select value={alvo} onChange={(event) => setAlvo(event.target.value)}>
                  {alvos.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            )}

            {tab === 'matriz' && (
              <label className="field">
                <span>Alvos — separados por vírgula; vazio cruza com os treze</span>
                <input value={alvosLista} onChange={(event) => setAlvosLista(event.target.value)} placeholder="claude-code,cursor,aider" />
              </label>
            )}

            {tab === 'lote' && (
              <>
                <div className="selecao-filtros">
                  <label><span>Marketplace</span><input value={marketplace} onChange={(event) => setMarketplace(event.target.value)} /></label>
                  <label><span>Versão</span><input value={versao} onChange={(event) => setVersao(event.target.value)} placeholder="1.0.0" /></label>
                  <label><span>Licença</span><input value={licenca} onChange={(event) => setLicenca(event.target.value)} /></label>
                </div>
                <div className="selecao-filtros">
                  <label><span>Autor</span><input value={autor} onChange={(event) => setAutor(event.target.value)} /></label>
                  <label><span>Repositório</span><input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="https://github.com/dono/repo" /></label>
                  <label><span>Domínio</span><input value={dominio} onChange={(event) => setDominio(event.target.value)} placeholder="pela primeira pasta" /></label>
                </div>
              </>
            )}

            {tab === 'regras' && (
              <p className="diagram-empty"><GitFork size={14} />O catálogo mostra alvos, estilos, regras, limites e o que a camada não faz — sem calcular nada.</p>
            )}

            <div className="selecao-acoes">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Play size={16} />}
                {busy ? 'Calculando…' : rotuloBotao[tab]}
              </button>
              <button type="button" className="button ghost" onClick={() => { setBundle(BUNDLE); setEspelho(ESPELHO); setAlvo('claude-code'); setAlvosLista('claude-code,cursor,aider'); setAlvoAuditar(''); setMarketplace('skills-do-projeto'); setVersao('1.0.0'); setAutor(AUTOR); setRepo(REPO); setLicenca('MIT'); setDominio(''); setEstrito(false); }}>
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
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <Boxes size={14} />}
              {busy ? 'Lendo o bundle…' : 'A amostra traz uma skill completa, uma sem apoio e um espelho com deriva: rode para ver o que muda em cada alvo.'}
            </p>
          )}

          {resultado && tab !== 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                {metricas[tab].map((metrica) => (
                  <Metric
                    key={metrica.chave}
                    label={metrica.label}
                    value={formatar(num(asObj(resultado.metrics)[metrica.chave]) || (metrica.chave === 'must' ? num(asObj(resultado.counts).must) : 0))}
                  />
                ))}
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>
              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(resultado.rows)} />
              {saida.length > 0 && <Saida arquivos={saida} />}
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}

          {resultado && tab === 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                <Metric label="ALVOS" value={formatar(alvosCatalogo.length)} />
                <Metric label="REGRAS" value={formatar(regras.length)} />
                <Metric label="CAMINHO" value={formatar(num(limites.caminho))} />
                <Metric label="PLUGIN" value={`${formatar(num(limites.plugin_bytes) / 1024 / 1024)} MB`} />
                <Metric label="SKILLS" value={formatar(num(limites.skills))} />
                <Metric label="VERSÃO" value={txt(catalogo?.versao)} />
              </div>
              <Verdict blocked={false}>{txt(asObj(catalogo).principio) || 'Catálogo publicado pela skill.'}</Verdict>
              <Tabela
                titulo="Alvos e o que carregam"
                colunas={[
                  { chave: 'nome', titulo: 'Alvo' },
                  { chave: 'estilo', titulo: 'Estilo', tipo: 'pill' },
                  { chave: 'base', titulo: 'Base', tipo: 'code' },
                  { chave: 'carrega', titulo: 'Carrega' },
                ]}
                linhas={alvosCatalogo.map((item) => ({ ...item, carrega: asList(item.carrega).join(', ') || 'só texto' }))}
              />
              <Tabela
                titulo="Regras da camada"
                colunas={[{ chave: 'regra', titulo: 'Regra' }]}
                linhas={regras.map((item) => ({ regra: item }))}
              />
              <Tabela
                titulo="Limites"
                colunas={[
                  { chave: 'chave', titulo: 'Limite', tipo: 'code' },
                  { chave: 'valor', titulo: 'Valor', largura: '110px' },
                ]}
                linhas={Object.entries(limites).map(([chave, valor]) => ({ chave, valor }))}
              />
              {asObj(catalogo?.origem).projeto ? (
                <p className="portabilidade-origem">
                  <Package size={14} />
                  Insumo: <code>{txt(asObj(catalogo?.origem).projeto)}</code> — licença {txt(asObj(catalogo?.origem).licenca)} · scripts{' '}
                  {asList(asObj(catalogo?.origem).scripts).join(', ')}
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
