import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  FileSignature,
  FlaskConical,
  Gauge,
  Layers3,
  LoaderCircle,
  MapPin,
  Play,
  Quote,
  ScanSearch,
  Users,
  Wrench,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../continuidade.css';
import '../sistema.css';
import '../evolucao.css';
import '../distilar.css';

type DistilarTab = 'perfil' | 'dimensoes' | 'esboco' | 'qualidade' | 'lastro' | 'correcao' | 'hospedeiros' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: DistilarTab; label: string; hint: string; icon: typeof Users }> = [
  { id: 'perfil', label: 'Perfil', hint: 'O que o material prova', icon: ScanSearch },
  { id: 'dimensoes', label: 'Dimensões', hint: 'O que cada família exige', icon: Layers3 },
  { id: 'esboco', label: 'Esqueleto', hint: 'SKILL.md proposto', icon: FileSignature },
  { id: 'qualidade', label: 'Qualidade', hint: 'As treze checagens', icon: FlaskConical },
  { id: 'lastro', label: 'Lastro', hint: 'Afirmação contra fonte', icon: Quote },
  { id: 'correcao', label: 'Correção', hint: '“Ele não faria isso”', icon: Wrench },
  { id: 'hospedeiros', label: 'Hospedeiros', hint: 'Oito agentes', icon: MapPin },
  { id: 'regras', label: 'Regras', hint: 'Limites e recusas', icon: ClipboardCheck },
];

const familias = [
  { id: 'colleague', label: 'Colega — trabalho' },
  { id: 'relationship', label: 'Relação — pessoal' },
  { id: 'celebrity', label: 'Figura pública' },
  { id: 'owner', label: 'Dono do agente' },
];

const EXEMPLO =
  '>>> conversa.txt\nAna: eu sempre prefiro revisar o PR antes de subir, porque já quebrou produção\nAna: teste primeiro, depois deploy — não tem atalho nesse processo\nAna: não sei nada de kubernetes, isso é com o time de infra\nAna: desculpa a resposta seca de ontem, foi mal\n';

export function DistilarPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<DistilarTab>('perfil');
  const [familia, setFamilia] = useState('colleague');
  const [corpus, setCorpus] = useState(EXEMPLO);
  const [nome, setNome] = useState('');
  const [perfilTexto, setPerfilTexto] = useState('');
  const [referencia, setReferencia] = useState('budget-friendly');
  const [correcao, setCorrecao] = useState('');
  const [secao, setSecao] = useState('');
  const [evidencia, setEvidencia] = useState('');
  const [host, setHost] = useState('');
  const [raiz, setRaiz] = useState('');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);
  const catalogo = tab === 'regras' ? resultado : null;

  const trocarTab = (destino: DistilarTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    if (tab === 'regras') return {};
    if (tab === 'perfil') return { corpus, familia, modo: 'full' };
    if (tab === 'dimensoes') return { familia, modo: 'full' };
    if (tab === 'esboco') return { nome, familia, corpus, modo: 'full' };
    if (tab === 'qualidade') return { perfil_texto: perfilTexto, referencia, modo: 'full' };
    if (tab === 'lastro') return { perfil_texto: perfilTexto, corpus, modo: 'full' };
    if (tab === 'correcao') return { correcao, secao, evidencia, modo: 'full' };
    return { host, raiz, modo: 'full' };
  };

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi analisado.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`distilar.${tab}`, parametros());
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(resposta);
      const dados = asObj(resposta.result);
      if (tab === 'esboco' && txt(dados.conteudo)) setPerfilTexto(txt(dados.conteudo));
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

  return (
    <div className="diagram-section selecao-page revisao-page continuidade-page sistema-page evolucao-page distilar-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Users size={22} /></span>
        <div>
          <span className="eyebrow">PERFIL DE PESSOA COM LASTRO, NÃO COM IMAGINAÇÃO</span>
          <h2>Destilar o que dá para provar</h2>
          <p>Esta camada porta a parte determinística do <a href="https://github.com/titanwings/distilly" target="_blank" rel="noreferrer">titanwings/distilly</a> (MIT): quatro famílias de personagem, oito hospedeiros, treze checagens de qualidade e a regra que organiza tudo — <strong>cada linha do perfil precisa de origem</strong>. Ela não escreve a persona: mede o material, mostra o que falta e recusa afirmação sem fonte.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Citação é prova</strong><span>Sem linha, é opinião.</span></li>
          <li><strong>Ausência declarada</strong><span>Vazio não se preenche.</span></li>
          <li><strong>Sem modelo</strong><span>Busca lexical e contagem.</span></li>
          <li><strong>Direito autoral</strong><span>Citação acima de 240 caracteres bloqueia.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações do perfil">
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
          </header>

          <form className="form-stack" onSubmit={executar}>
            {tab !== 'regras' && tab !== 'hospedeiros' && (
              <label className="field">
                <span>Família do perfil</span>
                <select value={familia} onChange={(event) => setFamilia(event.target.value)} disabled={tab === 'qualidade' || tab === 'correcao'}>
                  {familias.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}

            {(tab === 'perfil' || tab === 'esboco' || tab === 'lastro') && (
              <label className="field">
                <span>Material — <code>&gt;&gt;&gt; arquivo</code> separa fontes, <code>Autor: texto</code> marca falas</span>
                <textarea value={corpus} onChange={(event) => setCorpus(event.target.value)} rows={8} spellCheck={false} className="distilar-corpus" />
                <small className="selecao-contador">{corpus.split('\n').filter(Boolean).length} linha(s)</small>
              </label>
            )}

            {tab === 'esboco' && (
              <label className="field">
                <span>Nome do perfil</span>
                <input value={nome} onChange={(event) => setNome(event.target.value)} placeholder="Ana Souza" />
              </label>
            )}

            {(tab === 'qualidade' || tab === 'lastro') && (
              <label className="field">
                <span>Texto do perfil — o SKILL.md que você escreveu</span>
                <textarea value={perfilTexto} onChange={(event) => setPerfilTexto(event.target.value)} rows={10} spellCheck={false} className="distilar-corpus" placeholder="Cole aqui o perfil. O esqueleto da aba anterior serve como ponto de partida." />
              </label>
            )}

            {tab === 'qualidade' && (
              <label className="field">
                <span>Referência</span>
                <select value={referencia} onChange={(event) => setReferencia(event.target.value)}>
                  <option value="budget-friendly">budget-friendly — régua padrão</option>
                  <option value="budget-unfriendly">budget-unfriendly — régua estrita</option>
                </select>
              </label>
            )}

            {tab === 'correcao' && (
              <>
                <label className="field">
                  <span>O que está errado</span>
                  <textarea value={correcao} onChange={(event) => setCorrecao(event.target.value)} rows={3} placeholder="Ele não faria isso: ele pede opinião antes de decidir" />
                </label>
                <div className="sistema-dupla">
                  <label className="field">
                    <span>Seção afetada</span>
                    <input value={secao} onChange={(event) => setSecao(event.target.value)} placeholder="padroes_de_decisao" spellCheck={false} />
                  </label>
                  <label className="field">
                    <span>Evidência nova</span>
                    <input value={evidencia} onChange={(event) => setEvidencia(event.target.value)} placeholder="linha 42: pede opinião antes" spellCheck={false} />
                  </label>
                </div>
              </>
            )}

            {tab === 'hospedeiros' && (
              <div className="sistema-dupla">
                <label className="field">
                  <span>Hospedeiro</span>
                  <select value={host} onChange={(event) => setHost(event.target.value)}>
                    <option value="">todos os oito</option>
                    <option value="claude-code">Claude Code</option>
                    <option value="openclaw">OpenClaw</option>
                    <option value="hermes">Hermes</option>
                    <option value="codex">Codex</option>
                    <option value="deepseek-harness">DeepSeek Harness</option>
                    <option value="pi">Pi</option>
                    <option value="grok-build">Grok Build</option>
                    <option value="opencode">OpenCode</option>
                  </select>
                </label>
                <label className="field">
                  <span>Raiz do usuário — vazio usa ~</span>
                  <input value={raiz} onChange={(event) => setRaiz(event.target.value)} placeholder="/home/voce" spellCheck={false} />
                </label>
              </div>
            )}

            <div className="diagram-actions">
              <button type="submit" className="primary" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
                {busy ? 'Analisando' : tab === 'regras' ? 'Abrir catálogo' : 'Analisar'}
              </button>
              {markdown && (
                <button type="button" className="ghost" onClick={() => copiar(markdown, 'Parecer copiado')}>
                  <Copy size={14} /> Copiar parecer
                </button>
              )}
              {tab === 'esboco' && txt(resultado?.conteudo) && (
                <button type="button" className="ghost" onClick={() => copiar(txt(resultado?.conteudo), 'SKILL.md copiado')}>
                  <FileSignature size={14} /> Copiar SKILL.md
                </button>
              )}
            </div>

            {erro && <p className="diagram-error"><AlertTriangle size={14} />{erro}</p>}

            <p className="sistema-aviso">
              <AlertTriangle size={14} />
              Perfil de pessoa é afirmação sobre alguém. Sem linha de origem, a afirmação é sua — não dela.
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

              {tab === 'perfil' && <Tabela titulo="Cobertura por dimensão" colunas={[{ titulo: 'Dimensão', chave: 'dimensao', tipo: 'code' }, { titulo: 'Evidências', chave: 'evidencias' }, { titulo: 'Estado', chave: 'estado', tipo: 'pill' }, { titulo: 'Primeira citação', chave: 'citacao' }, { titulo: 'Fonte', chave: 'fonte', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'dimensoes' && <Tabela titulo="Dimensões" colunas={[{ titulo: 'Família', chave: 'familia', tipo: 'code' }, { titulo: 'Dimensão', chave: 'dimensao' }, { titulo: 'Sinais', chave: 'sinais' }, { titulo: 'Raiz', chave: 'raiz', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {(tab === 'esboco' || tab === 'lastro') && <Tabela titulo={tab === 'esboco' ? 'Seções propostas' : 'Afirmações conferidas'} colunas={tab === 'esboco' ? [{ titulo: 'Dimensão', chave: 'dimensao', tipo: 'code' }, { titulo: 'Evidências', chave: 'evidencias' }, { titulo: 'Estado', chave: 'estado', tipo: 'pill' }] : [{ titulo: 'Afirmação', chave: 'afirmacao' }, { titulo: 'Lastro', chave: 'lastro', tipo: 'pill' }, { titulo: 'Similaridade', chave: 'similaridade' }, { titulo: 'Fonte', chave: 'fonte', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'qualidade' && <Tabela titulo="Checagens" colunas={[{ titulo: 'Checagem', chave: 'checagem', tipo: 'code' }, { titulo: 'Estado', chave: 'estado', tipo: 'pill' }, { titulo: 'Obrigatória', chave: 'obrigatoria' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'correcao' && <Tabela titulo="Registro da correção" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'hospedeiros' && <Tabela titulo="Caminhos nativos" colunas={[{ titulo: 'Agente', chave: 'nome' }, { titulo: 'Skill', chave: 'skills', tipo: 'code' }, { titulo: 'Gerado', chave: 'gerado', tipo: 'code' }, { titulo: 'Invocação', chave: 'invocacao' }]} linhas={asRows(resultado.rows)} />}

              {tab === 'esboco' && txt(resultado.destino) && (
                <div className="sistema-hash">
                  <span>DESTINO</span>
                  <code>{txt(resultado.destino)}</code>
                  <button type="button" onClick={() => copiar(txt(resultado.destino), 'Destino copiado')}>Copiar</button>
                </div>
              )}

              <Findings items={asRows(resultado.findings)} />

              {tab === 'regras' && (
                <>
                  <Tabela titulo="Famílias" colunas={[{ titulo: 'Família', chave: 'familia', tipo: 'code' }, { titulo: 'Rótulo', chave: 'rotulo' }, { titulo: 'Domínio', chave: 'dominio' }, { titulo: 'Raiz', chave: 'raiz', tipo: 'code' }, { titulo: 'Dimensões', chave: 'dimensoes' }]} linhas={asRows(catalogo?.familias)} />
                  <Tabela titulo="Checagens do gate" colunas={[{ titulo: 'Checagem', chave: 'nome', tipo: 'code' }, { titulo: 'Grupo', chave: 'grupo', tipo: 'pill' }]} linhas={asRows(catalogo?.checagens)} />
                  <Tabela titulo="Hospedeiros" colunas={[{ titulo: 'Agente', chave: 'nome' }, { titulo: 'Skill', chave: 'skills', tipo: 'code' }, { titulo: 'Invocação', chave: 'invocacao' }]} linhas={asRows(catalogo?.hospedeiros)} />
                  <div className="sistema-listas">
                    <div>
                      <h4>Recusa declarada</h4>
                      <ul>{asList(catalogo?.nao_faz).map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                    <div>
                      <h4>Origem</h4>
                      <ul>
                        <li><code>{txt(asObj(catalogo?.origem).projeto)}</code> — {txt(asObj(catalogo?.origem).licenca)}</li>
                        <li>{txt(asObj(catalogo?.origem).o_que_foi_portado)}</li>
                      </ul>
                      <h4>Limites</h4>
                      <ul>
                        {Object.entries(asObj(catalogo?.limites)).map(([chave, valor]) => (
                          <li key={chave}><code>{chave}</code> = {valorMetrica(valor)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </>
              )}

              {txt(resultado.conteudo) && (
                <details className="diagram-markdown" open>
                  <summary>SKILL.md proposto</summary>
                  <pre>{txt(resultado.conteudo).slice(0, 12_000)}</pre>
                </details>
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
  if (['ausente', 'não', 'reprova', 'sem evidência', 'estrita'].includes(baixo)) return 'is-alert';
  if (['parcial', 'obrigatória'].includes(baixo)) return 'is-warn';
  if (['coberta', 'sim', 'passa', 'estrita'].includes(baixo)) return 'is-ok';
  return '';
};

const valorMetrica = (valor: unknown): React.ReactNode => {
  if (typeof valor === 'boolean') return valor ? 'sim' : 'não';
  if (typeof valor === 'number') return formatar(valor);
  return txt(valor) || '—';
};

const metricas = (tab: DistilarTab): Array<{ label: string; chave: string }> => {
  if (tab === 'perfil') return [{ label: 'MENSAGENS', chave: 'mensagens' }, { label: 'PALAVRAS', chave: 'palavras' }, { label: 'COBERTAS', chave: 'cobertas' }, { label: 'AUSENTES', chave: 'ausentes' }];
  if (tab === 'dimensoes') return [{ label: 'FAMÍLIAS', chave: 'familias' }, { label: 'DIMENSÕES', chave: 'dimensoes' }];
  if (tab === 'esboco') return [{ label: 'DIMENSÕES', chave: 'dimensoes' }, { label: 'FONTES', chave: 'fontes' }, { label: 'EVIDÊNCIAS', chave: 'evidencias' }];
  if (tab === 'qualidade') return [{ label: 'CHECAGENS', chave: 'checagens' }, { label: 'PASSAM', chave: 'passam' }, { label: 'REPROVAM', chave: 'reprovam' }, { label: 'OBRIGATÓRIAS', chave: 'obrigatorias' }];
  if (tab === 'lastro') return [{ label: 'AFIRMAÇÕES', chave: 'afirmacoes' }, { label: 'COM LASTRO', chave: 'comLastro' }, { label: 'SEM LASTRO', chave: 'semLastro' }, { label: 'CITAÇÕES', chave: 'citacoes' }];
  if (tab === 'correcao') return [{ label: 'TIPO', chave: 'tipo' }, { label: 'COM LASTRO', chave: 'comLastro' }];
  if (tab === 'hospedeiros') return [{ label: 'HOSPEDEIROS', chave: 'hospedeiros' }];
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
