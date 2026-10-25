import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  Dna,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  LoaderCircle,
  Map,
  Play,
  RotateCcw,
  ShieldCheck,
  Undo2,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../continuidade.css';
import '../sistema.css';
import '../evolucao.css';

type EvolucaoTab = 'mapa' | 'proposta' | 'risco' | 'guardas' | 'ensaiar' | 'promover' | 'reverter' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: EvolucaoTab; label: string; hint: string; icon: typeof Dna }> = [
  { id: 'mapa', label: 'Mapa', hint: 'Onde a mudança cai', icon: Map },
  { id: 'proposta', label: 'Proposta', hint: 'O diff aplica?', icon: GitCompareArrows },
  { id: 'risco', label: 'Risco', hint: 'O que o patch abre', icon: Gauge },
  { id: 'guardas', label: 'Guardas', hint: 'As dez leis', icon: ShieldCheck },
  { id: 'ensaiar', label: 'Ensaiar', hint: 'Suíte na cópia', icon: FlaskConical },
  { id: 'promover', label: 'Promover', hint: 'Escrever no vivo', icon: Play },
  { id: 'reverter', label: 'Reverter', hint: 'Voltar do backup', icon: Undo2 },
  { id: 'regras', label: 'Regras', hint: 'Fluxo e travas', icon: ClipboardCheck },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const EXEMPLO_DIFF = `--- a/server/review.py
+++ b/server/review.py
@@ -1,2 +1,3 @@
 """Primitivas compartilhadas das revisões estáticas do JARVIS.
+# mudança de exemplo: o primeiro hunk aplica sobre a linha atual
`;

const SEM_TOKEN = 'sem token de host';

export function EvolucaoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<EvolucaoTab>('mapa');
  const [nivel, setNivel] = useState('full');
  const [token, setToken] = useState('');
  const [area, setArea] = useState('tudo');
  const [diff, setDiff] = useState(EXEMPLO_DIFF);
  const [testes, setTestes] = useState('server/tests/test_revisao.py');
  const [timeoutS, setTimeoutS] = useState('600');
  const [confirmacao, setConfirmacao] = useState('');
  const [ensaio, setEnsaio] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);

  const trocarTab = (destino: EvolucaoTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    if (tab === 'regras') return {};
    const base = { autorizacao: token, modo: nivel };
    if (tab === 'mapa') return { ...base, area };
    if (tab === 'ensaiar') return { ...base, diff, testes, timeout: Number(timeoutS) || 600 };
    if (tab === 'promover') return { ...base, confirmacao };
    if (tab === 'reverter') return { ...base, ensaio };
    return { ...base, diff };
  };

  const opcoes = () => (tab === 'ensaiar' || tab === 'promover' || tab === 'reverter' ? { confirmed: confirmado } : undefined);

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi lido do código.');
      return;
    }
    if (tab !== 'regras' && !token.trim()) {
      setErro('Cole o token de storage/host-token.txt. Ele aparece no terminal onde a API subiu.');
      return;
    }
    if (opcoes() && !confirmado) {
      setErro('Marque a confirmação: esta aba executa código ou escreve no código-fonte.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`evoluir.${tab}`, parametros(), opcoes());
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(resposta);
      const dados = asObj(resposta.result);
      if (tab === 'ensaiar' && txt(dados.confirmacao)) setConfirmacao(txt(dados.confirmacao));
      if (tab === 'promover' && txt(dados.ensaio)) setEnsaio(txt(dados.ensaio));
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
  const fluxo = asRows(catalogo?.fluxo);
  const travas = asRows(catalogo?.travas);
  const regras = asRows(catalogo?.guardas);
  const perigos = asRows(catalogo?.perigos_monitorados);
  const naoFaz = asList(catalogo?.nao_faz);

  return (
    <div className="diagram-section selecao-page revisao-page continuidade-page sistema-page evolucao-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Dna size={22} /></span>
        <div>
          <span className="eyebrow">A ÚNICA CAMADA QUE PODE MUDAR O PRÓPRIO CÓDIGO</span>
          <h2>Provar antes de escrever</h2>
          <p>Um patch só toca a árvore viva depois de quatro provas: o hunk casa com o arquivo atual, o risco não abre shell nem embute segredo, as dez guardas do projeto continuam de pé, e a suíte real passa numa <em>cópia isolada</em>. Promover exige ainda hash idêntico ao ensaiado, arquivo sem alteração não commitada e backup antes da escrita.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Ensaio em cópia</strong><span>O vivo não é tocado.</span></li>
          <li><strong>Verde não é mérito</strong><span>Só prova que nada quebrou.</span></li>
          <li><strong>Backup primeiro</strong><span>Reverter é um comando.</span></li>
          <li><strong>Sem branch</strong><span>Nada de commit automático.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações de evolução">
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
            {tab !== 'regras' && (
              <label className="field">
                <span>Token de host — <code>storage/host-token.txt</code>, impresso no terminal da API</span>
                <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={SEM_TOKEN} autoComplete="off" spellCheck={false} />
              </label>
            )}

            {tab === 'mapa' && (
              <label className="field">
                <span>Área</span>
                <select value={area} onChange={(event) => setArea(event.target.value)}>
                  <option value="tudo">tudo</option>
                  <option value="server">server</option>
                  <option value="testes">testes</option>
                  <option value="web">web</option>
                  <option value="docs">docs</option>
                </select>
              </label>
            )}

            {['proposta', 'risco', 'guardas', 'ensaiar'].includes(tab) && (
              <label className="field">
                <span>Diff unificado — <code>git diff</code> ou <code>diff -u</code></span>
                <textarea value={diff} onChange={(event) => setDiff(event.target.value)} rows={12} spellCheck={false} className="evolucao-diff" />
                <small className="selecao-contador">{diff.split('\n').filter(Boolean).length} linha(s)</small>
              </label>
            )}

            {tab === 'ensaiar' && (
              <div className="sistema-dupla">
                <label className="field">
                  <span>Alvo dos testes</span>
                  <input value={testes} onChange={(event) => setTestes(event.target.value)} placeholder="server/tests" spellCheck={false} />
                </label>
                <label className="field">
                  <span>Timeout (s)</span>
                  <input value={timeoutS} onChange={(event) => setTimeoutS(event.target.value)} inputMode="numeric" />
                </label>
              </div>
            )}

            {tab === 'promover' && (
              <label className="field">
                <span>Confirmação — os 8 caracteres devolvidos pelo ensaio aprovado</span>
                <input value={confirmacao} onChange={(event) => setConfirmacao(event.target.value)} placeholder="a1b2c3d4" spellCheck={false} />
                <small className="selecao-contador">Consome o token: vale 15 minutos, serve uma vez, só para o diff ensaiado.</small>
              </label>
            )}

            {tab === 'reverter' && (
              <label className="field">
                <span>Ensaio promovido — o identificador devolvido na promoção</span>
                <input value={ensaio} onChange={(event) => setEnsaio(event.target.value)} placeholder="ffee9a37e6" spellCheck={false} />
              </label>
            )}

            {opcoes() && (
              <label className="continuidade-check is-warning">
                <input type="checkbox" checked={confirmado} onChange={(event) => setConfirmado(event.target.checked)} />
                <span>
                  {tab === 'ensaiar' && 'Confirmo que o ensaio executa o código do patch na cópia'}
                  {tab === 'promover' && 'Confirmo que esta operação escreve no código-fonte vivo'}
                  {tab === 'reverter' && 'Confirmo que esta operação restaura arquivos do backup'}
                </span>
              </label>
            )}

            <div className="diagram-actions">
              <button type="submit" className="primary" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
                {busy ? 'Executando' : tab === 'regras' ? 'Abrir catálogo' : tab === 'ensaiar' ? 'Ensaiar na cópia' : 'Executar'}
              </button>
              {markdown && (
                <button type="button" className="ghost" onClick={() => copiar(markdown, 'Parecer copiado')}>
                  <Copy size={14} /> Copiar parecer
                </button>
              )}
            </div>

            {erro && <p className="diagram-error"><AlertTriangle size={14} />{erro}</p>}

            <p className="sistema-aviso">
              <AlertTriangle size={14} />
              Promover não cria branch nem commita: o diff fica na árvore para você revisar, e a API precisa reiniciar para usar o código novo.
            </p>
          </form>
        </section>

        <section className="panel diagram-output">
          {!resultado ? (
            <p className="diagram-empty"><Gauge size={14} />Rode uma operação para ver o parecer.</p>
          ) : (
            <>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>

              {metricas(tab).length > 0 && (
                <div className="diagram-metrics">
                  {metricas(tab).map(({ label, chave }) => (
                    <Metric key={chave} label={label} value={valorMetrica(asObj(resultado.metrics)[chave])} />
                  ))}
                </div>
              )}

              {tab === 'mapa' && <Tabela titulo="Arquivos" colunas={[{ titulo: 'Arquivo', chave: 'arquivo', tipo: 'code' }, { titulo: 'Grupo', chave: 'grupo' }, { titulo: 'Linhas', chave: 'linhas' }, { titulo: 'Públicas', chave: 'publicas' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'proposta' && <Tabela titulo="Arquivos do patch" colunas={[{ titulo: 'Arquivo', chave: 'arquivo', tipo: 'code' }, { titulo: 'Estado', chave: 'estado', tipo: 'pill' }, { titulo: '+', chave: 'adicoes' }, { titulo: '−', chave: 'remocoes' }, { titulo: 'Hunks', chave: 'hunks' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'risco' && <Tabela titulo="Superfície tocada" colunas={[{ titulo: 'Arquivo', chave: 'arquivo', tipo: 'code' }, { titulo: 'Central', chave: 'central', tipo: 'pill' }, { titulo: '+', chave: 'adicoes' }, { titulo: '−', chave: 'remocoes' }, { titulo: 'Peso', chave: 'peso' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'guardas' && <Tabela titulo="As dez guardas" colunas={[{ titulo: 'Código', chave: 'codigo', tipo: 'code' }, { titulo: 'Regra', chave: 'regra' }, { titulo: 'Estado', chave: 'estado', tipo: 'pill' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'ensaiar' && <Tabela titulo="Aplicado na cópia" colunas={[{ titulo: 'Arquivo', chave: 'arquivo', tipo: 'code' }, { titulo: 'Estado', chave: 'estado' }, { titulo: '+', chave: 'adicoes' }, { titulo: '−', chave: 'remocoes' }]} linhas={asRows(resultado.rows)} />}
              {(tab === 'promover' || tab === 'reverter') && <Tabela titulo="Arquivos" colunas={[{ titulo: 'Arquivo', chave: 'arquivo', tipo: 'code' }, { titulo: 'Ação', chave: 'acao', tipo: 'pill' }, { titulo: 'Bytes', chave: 'bytes' }]} linhas={asRows(resultado.rows)} />}

              {tab === 'ensaiar' && txt(resultado.ensaio) && (
                <div className="sistema-hash">
                  <span>{resultado.aprovado === true ? 'ENSAIO APROVADO' : 'ENSAIO REPROVADO'}</span>
                  <code>{txt(resultado.ensaio)}</code>
                  {resultado.aprovado === true && <button type="button" onClick={() => copiar(txt(resultado.confirmacao), 'Confirmação copiada')}>Copiar confirmação</button>}
                </div>
              )}

              {tab === 'promover' && txt(resultado.backup) && (
                <div className="evolucao-alerta">
                  <RotateCcw size={14} />
                  <div>
                    <strong>Reinicie a API</strong>
                    <span>Backup em <code>{txt(resultado.backup)}</code>. Reverter usa esse diretório.</span>
                  </div>
                </div>
              )}

              <Findings items={asRows(resultado.findings)} />

              {tab === 'regras' && (
                <>
                  <Tabela titulo="Fluxo de sete passos" colunas={[{ titulo: '#', chave: 'passo' }, { titulo: 'Skill', chave: 'skill', tipo: 'code' }, { titulo: 'O que prova', chave: 'prova' }]} linhas={fluxo} />
                  <Tabela titulo="Travas" colunas={[{ titulo: '#', chave: 'ordem' }, { titulo: 'Trava', chave: 'trava' }, { titulo: 'Padrão', chave: 'padrao', tipo: 'pill' }, { titulo: 'Vale para', chave: 'vale_para' }]} linhas={travas} />
                  <Tabela titulo="Guardas" colunas={[{ titulo: 'Código', chave: 'codigo', tipo: 'code' }, { titulo: 'Regra', chave: 'regra' }, { titulo: 'Onde', chave: 'onde' }]} linhas={regras} />
                  <Tabela titulo="Padrões de perigo monitorados" colunas={[{ titulo: 'Grupo', chave: 'grupo', tipo: 'pill' }, { titulo: 'Título', chave: 'titulo' }, { titulo: 'Padrão', chave: 'padrao', tipo: 'code' }]} linhas={perigos} />
                  <div className="sistema-listas">
                    <div>
                      <h4>Recusa declarada</h4>
                      <ul>{naoFaz.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                    <div>
                      <h4>Raízes permitidas</h4>
                      <ul>{asList(catalogo?.raizes_permitidas).map((item) => <li key={item}><code>{item}</code></li>)}</ul>
                      <h4>Limites</h4>
                      <ul>
                        {Object.entries(asObj(catalogo?.limites)).map(([chave, valor]) => (
                          <li key={chave}><code>{chave}</code> = {valorMetrica(valor)}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4>Capacidades</h4>
                      <ul>
                        {Object.entries(asObj(catalogo?.capacidades)).map(([chave, valor]) => (
                          <li key={chave}><code>{chave}</code> = {valorMetrica(valor)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </>
              )}

              <Limitations items={resultado.limitations} />

              {markdown && (
                <details className="diagram-markdown">
                  <summary>Parecer em Markdown</summary>
                  <pre>{markdown}</pre>
                </details>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

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

type Coluna = { titulo: string; chave: string; tipo?: 'code' | 'pill' };

const grupos: Record<string, string> = { must: 'Corrigir obrigatoriamente', should: 'Corrigir', nice: 'Opcional' };

const formatar = (valor: number): string => valor.toLocaleString('pt-BR');

const tom = (valor: string): string => {
  const baixo = valor.toLowerCase();
  if (['must', 'viola', 'não aplica', 'alto', 'não', 'remove'].includes(baixo)) return 'is-alert';
  if (['should', 'revisar', 'médio'].includes(baixo)) return 'is-warn';
  if (['nice', 'preserva', 'aplica', 'baixo', 'sim', 'altera', 'cria'].includes(baixo)) return 'is-ok';
  return '';
};

const valorMetrica = (valor: unknown): React.ReactNode => {
  if (typeof valor === 'boolean') return valor ? 'sim' : 'não';
  if (typeof valor === 'number') return formatar(valor);
  return txt(valor) || '—';
};

const metricas = (tab: EvolucaoTab): Array<{ label: string; chave: string }> => {
  if (tab === 'mapa') return [{ label: 'ARQUIVOS', chave: 'arquivos' }, { label: 'LINHAS', chave: 'linhas' }, { label: 'MÓDULOS', chave: 'modulos' }, { label: 'SEM TESTE', chave: 'semTeste' }];
  if (tab === 'proposta') return [{ label: 'ARQUIVOS', chave: 'arquivos' }, { label: 'ADIÇÕES', chave: 'adicoes' }, { label: 'REMOÇÕES', chave: 'remocoes' }, { label: 'APLICÁVEL', chave: 'aplicavel' }];
  if (tab === 'risco') return [{ label: 'PONTUAÇÃO', chave: 'pontuacao' }, { label: 'PERIGOS', chave: 'perigos' }, { label: 'GUARDAS', chave: 'guardas' }, { label: 'CENTRAIS', chave: 'centrais' }];
  if (tab === 'guardas') return [{ label: 'REGRAS', chave: 'regras' }, { label: 'PRESERVADAS', chave: 'preservadas' }, { label: 'VIOLADAS', chave: 'violadas' }, { label: 'REVISAR', chave: 'revisar' }];
  if (tab === 'ensaiar') return [{ label: 'PASSARAM', chave: 'passed' }, { label: 'FALHARAM', chave: 'failed' }, { label: 'CÓDIGO', chave: 'codigo' }, { label: 'SEGUNDOS', chave: 'duracao' }];
  if (tab === 'promover') return [{ label: 'ARQUIVOS', chave: 'arquivos' }, { label: 'REINÍCIO', chave: 'reinicioPendente' }];
  if (tab === 'reverter') return [{ label: 'ARQUIVOS', chave: 'arquivos' }, { label: 'REINÍCIO', chave: 'reinicioPendente' }];
  return [];
};

function asObj(valor: unknown): Row {
  return valor && typeof valor === 'object' && !Array.isArray(valor) ? (valor as Row) : {};
}

function asRows(valor: unknown): Row[] {
  return Array.isArray(valor) ? valor.filter((item): item is Row => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function asList(valor: unknown): string[] {
  return Array.isArray(valor) ? valor.filter((item): item is string => typeof item === 'string') : [];
}

function txt(valor: unknown): string {
  if (typeof valor === 'string') return valor;
  if (typeof valor === 'number' || typeof valor === 'boolean') return String(valor);
  return '';
}

function num(valor: unknown): number {
  return typeof valor === 'number' ? valor : Number(valor) || 0;
}
