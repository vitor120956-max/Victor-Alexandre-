import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Gauge,
  LoaderCircle,
  ScrollText,
  Sparkles,
  Star,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../curadoria.css';

type CuradoriaTab = 'entrada' | 'catalogo' | 'readme' | 'ticker' | 'higiene' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: CuradoriaTab; label: string; hint: string; icon: typeof ClipboardList }> = [
  { id: 'entrada', label: 'Entrada', hint: 'Elegibilidade e linha', icon: ClipboardList },
  { id: 'catalogo', label: 'Catálogo', hint: 'Categorias e órfãs', icon: Boxes },
  { id: 'readme', label: 'README', hint: 'Sumário e seções', icon: ScrollText },
  { id: 'ticker', label: 'Ticker', hint: 'Estrelas entre snapshots', icon: Star },
  { id: 'higiene', label: 'Higiene', hint: 'IDs, links e datas', icon: ClipboardCheck },
  { id: 'regras', label: 'Regras', hint: 'O schema e o critério', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const CSV = `id,nome,categoria,subcategoria,link,autor,link_autor,ativo,adicionado_em,checado_em,descricao,estagnado
4f1a2b3c,Fluxo de skills,Skills e comandos,Revisão de código,https://github.com/exemplo/fluxo,Ana Lima,https://github.com/analima,TRUE,2026-05-01,2026-09-20,Revisa o diff antes do merge e registra a decisão.,FALSE
9e8d7c6b,Memória local,Memória e contexto,,https://github.com/exemplo/memoria,Beto Sá,https://github.com/betosa,TRUE,2026-04-11,2026-08-01,Guarda decisões entre sessões em arquivo local.,FALSE
11223344,Trilha de custo,Observabilidade,Custo e uso,https://github.com/exemplo/trilha,Carla Dias,https://github.com/carladias,TRUE,2026-06-02,2026-10-01,Soma o custo por sessão e mostra as chamadas mais caras.,FALSE
55aa66bb,Base compartilhada,Qualidade e revisão,,https://github.com/exemplo/base,Ana Lima,https://github.com/analima,TRUE,2025-11-02,2025-12-15,Formata e roda o lint de todo o monorepo num comando.,TRUE`;

const SNAPSHOT_ANTES = `repositorio,estrelas
exemplo/fluxo,1200
exemplo/memoria,410
exemplo/trilha,260
exemplo/base,95
alguem/claude-code,840
alguem/meu-source-code,300`;

const SNAPSHOT_AGORA = `repositorio,estrelas
exemplo/fluxo,1340
exemplo/memoria,455
exemplo/trilha,258
exemplo/base,101
alguem/claude-code,910
alguem/meu-source-code,315
exemplo/novo,14`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nada contra as regras deste nível.</p>;
  return (
    <div className="diagram-findings">
      {items.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`diagram-finding is-${group}`} key={`${text(finding.id)}-${text(finding.kind)}-${text(finding.location)}`}>
            <header>
              <span className="diagram-group">{groupLabel[group] ?? group}</span>
              <strong>{text(finding.title)}</strong>
              <code>{text(finding.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{text(finding.what)}</dd></div>
              <div><dt>Problema</dt><dd>{text(finding.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{text(finding.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{text(finding.ifSkipped)}</dd></div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function Limitations({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="diagram-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Verdict({ children, blocked }: { children: React.ReactNode; blocked?: boolean }) {
  return (
    <p className="diagram-verdict">
      {blocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
      {children}
    </p>
  );
}

const blocked = (result: Row): boolean => count(asRow(result.counts).must) > 0;

function EntradaView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const elegivel = result.elegivel === true;
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="ELEGÍVEL" value={elegivel ? 'sim' : 'não'} tone={elegivel ? 'ok' : 'danger'} />
        <Metric label="CAMINHO" value={text(metrics.regra)} tone={text(metrics.regra) === 'nenhuma' ? 'danger' : 'ok'} />
        <Metric label="ID" value={<code>{text(metrics.id)}</code>} />
        <Metric label="DESCRIÇÃO" value={`${count(metrics.caracteres)} car.`} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <div className="curadoria-line">
        <header><strong>LINHA PRONTA</strong><span>12 colunas · ID opaco de 8 dígitos</span></header>
        <pre>{text(result.linha)}</pre>
      </div>
      <Findings items={asRows(result.findings)} />
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Campo</th><th>Valor</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={text(row.campo)}><td><code>{text(row.campo)}</code></td><td>{text(row.valor) || '—'}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <Limitations items={result.limitations} />
    </div>
  );
}

function CatalogoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="LINHAS" value={count(metrics.linhas)} />
        <Metric label="ATIVOS" value={count(metrics.ativos)} />
        <Metric label="VAZIAS" value={count(metrics.vazias)} tone={count(metrics.vazias) ? 'warning' : 'ok'} />
        <Metric label="SEM CHECAGEM" value={count(metrics.nunca_checados)} tone={count(metrics.nunca_checados) ? 'warning' : 'ok'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Categoria</th><th>Recursos</th><th>Subcategorias</th><th>Declarada</th></tr></thead>
          <tbody>{asRows(result.rows).map((row) => (
            <tr key={text(row.categoria)}>
              <td><strong>{text(row.categoria)}</strong></td>
              <td>{count(row.total)}</td>
              <td>{count(row.subcategorias)}</td>
              <td><span className={`diagram-state ${text(row.declarada) === 'sim' ? 'is-ok' : 'is-danger'}`}>{text(row.declarada)}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function ReadmeView({ result, onCopy }: { result: Row; onCopy: () => void }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="RECURSOS" value={count(metrics.linhas)} />
        <Metric label="SEÇÕES" value={count(metrics.secoes)} />
        <Metric label="CARACTERES" value={count(metrics.caracteres)} />
        <Metric label="ATUALIZADO" value={text(metrics.hoje)} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <div className="curadoria-line">
        <header>
          <strong>README GERADO</strong>
          <button type="button" className="curadoria-copy" onClick={onCopy}>Copiar</button>
        </header>
        <pre>{text(result.markdown)}</pre>
      </div>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function TickerView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const excluidos = asRows(result.excluidos);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="EM COMUM" value={count(metrics.comum)} />
        <Metric label="SUBIRAM" value={count(metrics.subiram)} tone="ok" />
        <Metric label="NOVOS" value={count(metrics.novos)} />
        <Metric label="EXCLUÍDOS" value={count(metrics.excluidos)} tone={count(metrics.excluidos) ? 'warning' : 'ok'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Repositório</th><th>Antes</th><th>Agora</th><th>Δ</th><th>%</th><th>Estado</th></tr></thead>
          <tbody>{asRows(result.rows).slice(0, 20).map((row) => (
            <tr key={text(row.repo)}>
              <td><code>{text(row.repo)}</code></td>
              <td>{count(row.antes)}</td>
              <td>{count(row.depois)}</td>
              <td><span className={`diagram-state ${count(row.delta) > 0 ? 'is-ok' : count(row.delta) < 0 ? 'is-danger' : ''}`}>{count(row.delta) > 0 ? '+' : ''}{count(row.delta)}</span></td>
              <td>{count(row.percentual).toFixed(1)}</td>
              <td>{text(row.estado)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {excluidos.length > 0 && (
        <div className="diagram-note-card">
          <h4><AlertTriangle size={14} /> Fora do ticker</h4>
          <ul className="diagram-traps">
            {excluidos.map((row) => <li key={text(row.repo)}><code>{text(row.repo)}</code> — {text(row.motivo)}</li>)}
          </ul>
        </div>
      )}
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function HigieneView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="LINHAS" value={count(metrics.linhas)} />
        <Metric label="BLOQUEIOS" value={count(asRow(result.counts).must)} tone={count(asRow(result.counts).must) ? 'danger' : 'ok'} />
        <Metric label="IDS REPETIDOS" value={count(metrics.ids_repetidos)} tone={count(metrics.ids_repetidos) ? 'danger' : 'ok'} />
        <Metric label="JANELA" value={`${count(metrics.dias_para_checar)} dias`} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Findings items={asRows(result.findings)} />
      <div className="diagram-vocab">
        {asRows(result.rows).map((row, index) => <span key={`${index}-${text(row.checagem)}`}>{text(row.checagem)}</span>)}
      </div>
      <Limitations items={result.limitations} />
    </div>
  );
}

function RegrasView({ regras }: { regras: Row | null }) {
  if (!regras) return <p className="diagram-empty">O catálogo de regras ainda não chegou da API.</p>;
  const categorias = asRows(regras.categorias);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="COLUNAS" value={asList(regras.colunas).length} />
        <Metric label="CATEGORIAS" value={categorias.length} />
        <Metric label="REGRAS" value={asList(regras.elegibilidade).length + asList(regras.estilo).length} />
        <Metric label="LICENÇA" value={text(asRow(regras.licenca).id)} />
      </div>
      <p className="diagram-verdict"><Sparkles size={14} />{text(regras.principio)}</p>
      <div className="curadoria-line">
        <header><strong>SCHEMA DE 12 COLUNAS</strong><span>aceita cabeçalho em português ou inglês</span></header>
        <pre>{asList(regras.colunas).join(',')}</pre>
      </div>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr><th>Categoria</th><th>Subcategorias</th><th>Submetível</th></tr></thead>
          <tbody>{categorias.map((row) => (
            <tr key={text(row.nome)}>
              <td><strong>{text(row.nome)}</strong><br /><small>{text(row.descricao)}</small></td>
              <td>{asList(row.subcategorias).join(', ') || '—'}</td>
              <td><span className={`diagram-state ${row.submetivel === true ? 'is-ok' : 'is-danger'}`}>{row.submetivel === true ? 'sim' : 'curada'}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="curadoria-rules">
        {asRows(regras.elegibilidade).map((row) => (
          <article key={`e-${text(row.id)}`}><span>elegibilidade · {text(row.id)}</span><p>{text(row.regra)}</p></article>
        ))}
        {asRows(regras.estilo).map((row) => (
          <article key={`s-${text(row.id)}`}><span>estilo · {text(row.id)}</span><p>{text(row.regra)}</p></article>
        ))}
        {asRows(regras.licenca_regras).map((row) => (
          <article key={`l-${text(row.id)}`}><span>licença · {text(row.id)}</span><p>{text(row.regra)}</p></article>
        ))}
      </div>
      <div className="diagram-limitations">
        <strong>ATRIBUIÇÃO</strong>
        <ul>
          <li>{text(regras.fonte)} — o catálogo do upstream não é copiado nem adaptado.</li>
          <li>{text(asRow(regras.licenca).resumo)}: {text(asRow(regras.licenca).efeito)}</li>
        </ul>
      </div>
    </div>
  );
}

export function CuradoriaPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<CuradoriaTab>('entrada');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [view, setView] = useState<CuradoriaTab>('entrada');
  const [regras, setRegras] = useState<Row | null>(null);

  const [nome, setNome] = useState('Fluxo de skills');
  const [link, setLink] = useState('https://github.com/exemplo/fluxo');
  const [autor, setAutor] = useState('Ana Lima');
  const [linkAutor, setLinkAutor] = useState('https://github.com/analima');
  const [categoria, setCategoria] = useState('Skills e comandos');
  const [subcategoria, setSubcategoria] = useState('Revisão de código');
  const [descricao, setDescricao] = useState('Revisa o diff antes do merge e registra a decisão.');
  const [licenca, setLicenca] = useState('MIT');
  const [dias, setDias] = useState('40');
  const [commits, setCommits] = useState('12');
  const [estrelas, setEstrelas] = useState('7');
  const [cadastro, setCadastro] = useState(false);
  const [pago, setPago] = useState(false);
  const [existentes, setExistentes] = useState('');

  const [csv, setCsv] = useState(CSV);
  const [anterior, setAnterior] = useState(SNAPSHOT_ANTES);
  const [atual, setAtual] = useState(SNAPSHOT_AGORA);

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('curadoria.regras', {});
        if (active && response.ok) setRegras(asRow(response.result));
      } catch {
        if (active) setRegras(null);
      }
    })();
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

  const result = execution?.ok ? asRow(execution.result) : null;
  const resultMarkdown = useMemo(() => text(result?.markdown), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>, next: CuradoriaTab) => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi lido.');
      return;
    }
    setBusy(true);
    setError('');
    setExecution(null);
    setView(next);
    try {
      const response = await executeSkill(skillId, parameters);
      if (!response.ok) {
        setError(response.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(response);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Falha ao executar a skill.');
    } finally {
      setBusy(false);
    }
  };

  const copy = async (conteudo: string, titulo: string) => {
    if (!conteudo) return;
    try {
      await navigator.clipboard.writeText(conteudo);
      pushToast(titulo, 'O conteúdo está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (tab === 'entrada') {
      void run('curadoria.entrada', {
        nome, link, autor, link_autor: linkAutor, categoria, subcategoria, descricao, licenca,
        dias_desde_o_primeiro_commit: Number(dias) || 0,
        commits_depois_do_primeiro_dia: Number(commits) || 0,
        estrelas: Number(estrelas) || 0,
        exige_cadastro: cadastro, pago, existentes, modo: level,
      }, 'entrada');
      return;
    }
    if (tab === 'catalogo') {
      void run('curadoria.catalogo', { csv, modo: level }, 'catalogo');
      return;
    }
    if (tab === 'readme') {
      void run('curadoria.readme', { csv, modo: level }, 'readme');
      return;
    }
    if (tab === 'ticker') {
      void run('curadoria.ticker', { anterior, atual, modo: level }, 'ticker');
      return;
    }
    if (tab === 'higiene') {
      void run('curadoria.higiene', { csv, modo: level }, 'higiene');
      return;
    }
    setError('O catálogo de regras é lido ao abrir a página.');
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const buttonLabel: Record<CuradoriaTab, string> = {
    entrada: 'Validar entrada', catalogo: 'Agrupar catálogo', readme: 'Gerar README',
    ticker: 'Comparar estrelas', higiene: 'Auditar higiene', regras: 'Ler regras',
  };

  return (
    <div className="diagram-section curadoria-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Gauge size={22} /></span>
        <div>
          <span className="eyebrow">CRITÉRIO ANTES DO CATÁLOGO</span>
          <h2>Entra pouco, entra revisado, e o que envelhece sai</h2>
          <p>Uma lista vale pelo que recusa. Esta camada valida a entrada contra as regras de elegibilidade — 14 dias de desenvolvimento ativo ou 100 estrelas —, agrupa o CSV pela configuração editorial, deriva o README, compara snapshots de estrelas e audita a higiene do arquivo. Nada é buscado na rede e nada do catálogo de terceiros é copiado.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Uma linha, um recurso</strong><span>O ID é opaco; o link é a chave de deduplicação.</span></li>
          <li><strong>Descrição factual</strong><span>Presente do indicativo, sem emoji, sem superlativo, sem falar com o leitor.</span></li>
          <li><strong>README derivado</strong><span>O CSV é a fonte; o sumário é gerado com âncoras do GitHub.</span></li>
          <li><strong>Proteção no ranking</strong><span>Imitacão de produto e cópia de fonte ficam fora do ticker.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos da curadoria">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); }} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="diagram-layout">
        <section className="panel diagram-form">
          <header className="diagram-form-head">
            <div>
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="diagram-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>

          <form className="form-stack" onSubmit={submit}>
            {tab === 'entrada' && (
              <>
                <label className="field">
                  <span>Nome do recurso</span>
                  <input value={nome} onChange={(event) => setNome(event.target.value)} maxLength={80} />
                </label>
                <div className="field-row">
                  <label className="field">
                    <span>Link principal</span>
                    <input value={link} onChange={(event) => setLink(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>Licença</span>
                    <input value={licenca} onChange={(event) => setLicenca(event.target.value)} placeholder="MIT, Apache-2.0…" />
                  </label>
                </div>
                <div className="field-row">
                  <label className="field">
                    <span>Autor</span>
                    <input value={autor} onChange={(event) => setAutor(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>Link do autor</span>
                    <input value={linkAutor} onChange={(event) => setLinkAutor(event.target.value)} />
                  </label>
                </div>
                <div className="field-row">
                  <label className="field">
                    <span>Categoria</span>
                    <input value={categoria} onChange={(event) => setCategoria(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>Subcategoria</span>
                    <input value={subcategoria} onChange={(event) => setSubcategoria(event.target.value)} />
                  </label>
                </div>
                <label className="field">
                  <span>Descrição em uma linha</span>
                  <textarea value={descricao} onChange={(event) => setDescricao(event.target.value)} rows={3} maxLength={500} />
                </label>
                <div className="field-row">
                  <label className="field">
                    <span>Dias desde o primeiro commit</span>
                    <input value={dias} onChange={(event) => setDias(event.target.value)} inputMode="numeric" />
                  </label>
                  <label className="field">
                    <span>Commits depois do primeiro dia</span>
                    <input value={commits} onChange={(event) => setCommits(event.target.value)} inputMode="numeric" />
                  </label>
                  <label className="field">
                    <span>Estrelas</span>
                    <input value={estrelas} onChange={(event) => setEstrelas(event.target.value)} inputMode="numeric" />
                  </label>
                </div>
                <label className="diagram-check">
                  <input type="checkbox" checked={cadastro} onChange={(event) => setCadastro(event.target.checked)} />
                  <span>Exige cadastro para usar</span>
                </label>
                <label className="diagram-check">
                  <input type="checkbox" checked={pago} onChange={(event) => setPago(event.target.checked)} />
                  <span>Exige pagamento para usar</span>
                </label>
                <label className="field">
                  <span>Já no catálogo (opcional)</span>
                  <textarea value={existentes} onChange={(event) => setExistentes(event.target.value)} rows={2} placeholder="https://github.com/exemplo/fluxo|Fluxo de skills" />
                </label>
              </>
            )}
            {(tab === 'catalogo' || tab === 'readme' || tab === 'higiene') && (
              <label className="field">
                <span>Catálogo em CSV</span>
                <textarea value={csv} onChange={(event) => setCsv(event.target.value)} rows={14} spellCheck={false} />
              </label>
            )}
            {tab === 'ticker' && (
              <>
                <label className="field">
                  <span>Snapshot anterior</span>
                  <textarea value={anterior} onChange={(event) => setAnterior(event.target.value)} rows={9} spellCheck={false} />
                </label>
                <label className="field">
                  <span>Snapshot atual</span>
                  <textarea value={atual} onChange={(event) => setAtual(event.target.value)} rows={9} spellCheck={false} />
                </label>
              </>
            )}
            {tab === 'regras' && (
              <p className="diagram-empty"><ClipboardCheck size={14} />As regras vêm do servidor e aparecem ao lado, sem precisar executar nada.</p>
            )}

            <button className="button primary" type="submit" disabled={busy || tab === 'regras'}>
              {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <ClipboardList size={16} />}
              {busy ? 'Processando…' : buttonLabel[tab]}
            </button>
            {error && <p className="diagram-error" role="alert"><AlertTriangle size={14} />{error}</p>}
          </form>
        </section>

        <section className="panel diagram-result">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h3>{activeTab.hint}</h3>
            </div>
            {result && (
              <div className="diagram-result-actions">
                <span className="diagram-badge">{view}</span>
                {resultMarkdown && (
                  <button type="button" className="button ghost" onClick={() => void copy(resultMarkdown, 'Parecer copiado')}>
                    Copiar parecer
                  </button>
                )}
              </div>
            )}
          </header>

          {!result && tab === 'regras' && <RegrasView regras={regras} />}
          {!result && tab !== 'regras' && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <ClipboardList size={14} />}
              {busy ? 'Lendo a lista…' : 'Preencha à esquerda. O resultado é determinístico: mesma entrada, mesmo parecer.'}
            </p>
          )}
          {result && view === 'entrada' && <EntradaView result={result} />}
          {result && view === 'catalogo' && <CatalogoView result={result} />}
          {result && view === 'readme' && <ReadmeView result={result} onCopy={() => void copy(text(result.markdown), 'README copiado')} />}
          {result && view === 'ticker' && <TickerView result={result} />}
          {result && view === 'higiene' && <HigieneView result={result} />}
        </section>
      </div>
    </div>
  );
}
