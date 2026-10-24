import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronsDownUp,
  Calculator,
  Gauge,
  LoaderCircle,
  MessageSquare,
  Ruler,
  Scissors,
  Sparkles,
  Wallet,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../ciencia.css';
import '../contexto.css';

type ContextoTab = 'orcamento' | 'tokens' | 'corte' | 'higiene' | 'resumo' | 'uso' | 'regras';
type TextoTab = Exclude<ContextoTab, 'regras'>;
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: ContextoTab; label: string; hint: string; icon: typeof Gauge }> = [
  { id: 'orcamento', label: 'Orçamento', hint: 'Quanto cabe na janela', icon: Calculator },
  { id: 'tokens', label: 'Tokens', hint: 'O que a conversa ocupa', icon: Ruler },
  { id: 'corte', label: 'Corte', hint: 'O que sai e o que fica', icon: Scissors },
  { id: 'higiene', label: 'Higiene', hint: 'Histórico que o provedor aceita', icon: ChevronsDownUp },
  { id: 'resumo', label: 'Resumo', hint: 'O que precisa sobreviver', icon: Sparkles },
  { id: 'uso', label: 'Uso', hint: 'Contexto, custo e hops', icon: Wallet },
  { id: 'regras', label: 'Regras', hint: 'Fórmulas e limites', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const dialetos = [
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'openai', label: 'OpenAI' },
  { id: 'google', label: 'Google' },
  { id: 'ollama', label: 'Ollama' },
];

const CONVERSA = `system: Você é o JARVIS, direto e sem enfeite.
user: [imagem 1024x768] leia este gráfico e diga a tendência.
assistant: A série sobe até 240ms em março e cai depois.
user: busca o custo do fornecedor?
assistant(tools): c1=buscar_web
tool(c1): O custo é R$ 1.200 por mês, com pico de R$ 1.800 em janeiro.
assistant: Fica R$ 1.200 por mês na média.
user: decidimos fechar com esse fornecedor em scripts/contrato.py.`;

const LONGA = `system: Você é o JARVIS.
user: Comece pelo inventário de serviços.
assistant: São doze serviços, três deles sem dono.
user: Quais ficaram sem dono?
assistant(tools): c1=buscar_servicos
tool(c1): auth, billing e webhooks respondem sem time declarado.
user: E o custo de cada um?
assistant(tools): c2=custo_por_servico
tool(c2): auth R$ 420, billing R$ 810, webhooks R$ 95.
user: Vamos priorizar billing, que é o maior.
assistant: billing é o maior custo mensal e o único com cobrança duplicada.
user: O que falta para fechar a migração?
assistant: Falta o plano de rollback e a janela de manutenção.
user: decidimos migrar billing na sexta às 22h.
assistant: Anotado: sexta às 22h, com rollback em scripts/rollback.sh.`;

const QUEBRADA = `assistant: Vou consultar a base.
tool(c1): 42 registros encontrados.
user: e o total?
assistant(tools): c2=calcular_total
assistant: O total é 42.
user: obrigado!`;

const RESUMIR = `user: precisamos fechar o banco. decidimos usar Postgres 16 no cluster de staging.
assistant: ok. o p95 ficou em 240ms e o custo em R$ 1.200 por mês.
user: próximo passo é migrar scripts/etl.py e medir de novo.
assistant(tools): c1=ler_arquivo
tool(c1): ${'registro de migração com detalhe repetido. '.repeat(120)}
user: e o rollback?
assistant: fica em scripts/rollback.sh, testado em 12 minutos.`;

const iniciais: Record<TextoTab, string> = {
  orcamento: CONVERSA,
  tokens: CONVERSA,
  corte: LONGA,
  higiene: QUEBRADA,
  resumo: RESUMIR,
  uso: '',
};

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const asMap = (value: unknown): Row => asRow(value);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const numero = (valor: string, padrao = 0): number => {
  const n = Number(valor.replace(',', '.'));
  return Number.isFinite(n) ? n : padrao;
};
const inteiro = (valor: string, padrao = 0): number => Math.trunc(numero(valor, padrao));
const opcional = (valor: string): number | undefined => (valor.trim() === '' ? undefined : inteiro(valor));

const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const toneDoGrupo = (valor: string): string => {
  if (['ok', 'mantido', 'baixo', 'livre'].includes(valor)) return 'is-ok';
  if (['corrigir', 'removido', 'moderado'].includes(valor)) return 'is-warning';
  if (['obrigatório', 'alto', 'crítico', 'bloqueio'].includes(valor)) return 'is-danger';
  return '';
};

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
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

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nada contra as regras deste nível.</p>;
  return (
    <div className="diagram-findings">
      {items.map((item) => {
        const group = text(item.group);
        return (
          <article className={`diagram-finding is-${group}`} key={`${text(item.id)}-${text(item.kind)}`}>
            <header>
              <span className="diagram-group">{groupLabel[group] ?? group}</span>
              <strong>{text(item.title)}</strong>
              <code>{text(item.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{text(item.what)}</dd></div>
              <div><dt>Problema</dt><dd>{text(item.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{text(item.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{text(item.ifSkipped)}</dd></div>
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

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill' };

function Tabela({ titulo, colunas, linhas }: { titulo: string; colunas: Coluna[]; linhas: Row[] }) {
  if (!linhas.length) return null;
  return (
    <div className="ciencia-table-block">
      <h4>{titulo}</h4>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr>{colunas.map((coluna) => <th key={coluna.chave}>{coluna.titulo}</th>)}</tr></thead>
          <tbody>
            {linhas.map((linha, indice) => (
              <tr key={indice}>
                {colunas.map((coluna) => {
                  const valor = text(linha[coluna.chave]) || '—';
                  if (coluna.tipo === 'code') return <td key={coluna.chave}><code>{valor}</code></td>;
                  if (coluna.tipo === 'pill') return <td key={coluna.chave}><span className={['diagram-state', toneDoGrupo(valor)].filter(Boolean).join(' ')}>{valor}</span></td>;
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

const colunas: Record<TextoTab, Coluna[]> = {
  orcamento: [
    { chave: 'etapa', titulo: 'Etapa' },
    { chave: 'valor', titulo: 'Valor', tipo: 'code' },
    { chave: 'regra', titulo: 'Regra' },
  ],
  tokens: [
    { chave: 'n', titulo: '#' },
    { chave: 'papel', titulo: 'Papel' },
    { chave: 'tokens', titulo: 'Tokens' },
    { chave: 'anexos', titulo: 'Anexos' },
    { chave: 'texto', titulo: 'Conteúdo', tipo: 'code' },
  ],
  corte: [
    { chave: 'turno', titulo: 'Turno' },
    { chave: 'papel', titulo: 'Papel' },
    { chave: 'tokens', titulo: 'Tokens' },
    { chave: 'decisao', titulo: 'Decisão', tipo: 'pill' },
    { chave: 'motivo', titulo: 'Motivo' },
  ],
  higiene: [
    { chave: 'correcao', titulo: 'Correção' },
    { chave: 'alvo', titulo: 'Alvo' },
    { chave: 'efeito', titulo: 'Efeito' },
  ],
  resumo: [
    { chave: 'tipo', titulo: 'Tipo', tipo: 'pill' },
    { chave: 'item', titulo: 'Item' },
    { chave: 'origem', titulo: 'Origem' },
  ],
  uso: [
    { chave: 'grandeza', titulo: 'Grandeza' },
    { chave: 'valor', titulo: 'Valor', tipo: 'code' },
    { chave: 'regra', titulo: 'Regra' },
  ],
};

const titulos: Record<ContextoTab, string> = {
  orcamento: 'Orçamento da janela', tokens: 'Estimativa de tokens', corte: 'Corte do histórico',
  higiene: 'Higiene do histórico', resumo: 'Resumo de retenção', uso: 'Uso e custo',
  regras: 'Fórmulas e limites',
};

function Barra({ valor, rotulo }: { valor: number; rotulo: string }) {
  const largura = Math.max(0, Math.min(100, valor));
  const classe = valor >= 100 ? 'is-critico' : valor >= 80 ? 'is-alto' : valor >= 50 ? 'is-moderado' : 'is-baixo';
  return (
    <div className={`contexto-bar ${classe}`}>
      <div><span>{rotulo}</span><strong>{valor}%</strong></div>
      <i><b style={{ width: `${largura}%` }} /></i>
    </div>
  );
}

function Metricas({ tab, result }: { tab: TextoTab; result: Row }) {
  const metrics = asRow(result.metrics);
  if (tab === 'orcamento') {
    return (
      <>
        <div className="diagram-metrics">
          <Metric label="JANELA" value={count(metrics.janela).toLocaleString('pt-BR')} />
          <Metric label="RESERVA" value={count(metrics.reserva).toLocaleString('pt-BR')} tone={count(metrics.reserva_pct) > 50 ? 'warning' : undefined} />
          <Metric label="SALA" value={count(metrics.sala).toLocaleString('pt-BR')} />
          <Metric label="PROMPT" value={count(metrics.prompt).toLocaleString('pt-BR')} />
        </div>
        <Barra valor={count(metrics.pressao)} rotulo="PRESSÃO NA SALA DE ENTRADA" />
      </>
    );
  }
  if (tab === 'tokens') {
    const papel = asMap(metrics.por_papel);
    return (
      <div className="diagram-metrics">
        <Metric label="TOKENS" value={count(metrics.tokens).toLocaleString('pt-BR')} />
        <Metric label="MENSAGENS" value={count(metrics.mensagens)} />
        <Metric label="IMAGENS" value={count(metrics.imagem)} />
        <Metric label="MÍDIA" value={`${count(metrics.audio)} + ${count(metrics.video)}`} />
        <Metric label="NO SISTEMA" value={count(papel.sistema).toLocaleString('pt-BR')} />
        <Metric label="NA FERRAMENTA" value={count(papel.ferramenta).toLocaleString('pt-BR')} />
      </div>
    );
  }
  if (tab === 'corte') {
    return (
      <div className="diagram-metrics">
        <Metric label="ANTES" value={count(metrics.tokens_antes).toLocaleString('pt-BR')} />
        <Metric label="DEPOIS" value={count(metrics.tokens_depois).toLocaleString('pt-BR')} tone="ok" />
        <Metric label="REMOVIDAS" value={count(metrics.removidas)} tone={count(metrics.removidas) ? 'warning' : 'ok'} />
        <Metric label="SALA" value={count(metrics.sala).toLocaleString('pt-BR')} />
        <Metric label="TURNOS" value={count(metrics.turnos)} />
        <Metric label="ECONOMIA" value={`${count(metrics.economia_pct)}%`} />
      </div>
    );
  }
  if (tab === 'higiene') {
    return (
      <div className="diagram-metrics">
        <Metric label="MENSAGENS" value={count(metrics.mensagens)} />
        <Metric label="ÓRFÃS" value={count(metrics.orfas)} tone={count(metrics.orfas) ? 'danger' : 'ok'} />
        <Metric label="INJETADAS" value={count(metrics.injetadas)} tone={count(metrics.injetadas) ? 'warning' : 'ok'} />
        <Metric label="ABERTURA" value={count(metrics.abertura) ? 'inserida' : 'ok'} tone={count(metrics.abertura) ? 'warning' : 'ok'} />
      </div>
    );
  }
  if (tab === 'resumo') {
    return (
      <div className="diagram-metrics">
        <Metric label="ITENS RETIDOS" value={count(metrics.itens)} />
        <Metric label="STUBS" value={count(metrics.stubs)} />
        <Metric label="TOKENS DO RESUMO" value={count(metrics.tokens_resumo)} tone={count(metrics.tokens_resumo) > count(metrics.limite) ? 'danger' : 'ok'} />
        <Metric label="LIMITE" value={count(metrics.limite)} />
        <Metric label="ENTRADA" value={count(metrics.tokens_stub).toLocaleString('pt-BR')} />
        <Metric label="CORTADOS" value={count(metrics.cortados)} tone={count(metrics.cortados) ? 'warning' : 'ok'} />
      </div>
    );
  }
  return (
    <>
      <div className="diagram-metrics">
        <Metric label="CONTEXTO" value={count(metrics.contexto).toLocaleString('pt-BR')} />
        <Metric label="CUSTO" value={`US$ ${numero(String(metrics.custo)).toFixed(4)}`} />
        <Metric label="EM HOPS" value={`US$ ${numero(String(metrics.custo_hop)).toFixed(4)}`} />
        <Metric label="CACHE" value={count(metrics.cache).toLocaleString('pt-BR')} />
      </div>
      {count(metrics.pressao) > 0 && <Barra valor={count(metrics.pressao)} rotulo="PRESSÃO NA JANELA" />}
    </>
  );
}

function Numero({ label, value, onChange, suffix, hint }: { label: string; value: string; onChange: (valor: string) => void; suffix?: string; hint?: string }) {
  return (
    <label className="contexto-field" title={hint}>
      <span>{label}</span>
      <div>
        <input type="number" inputMode="numeric" value={value} onChange={(event) => onChange(event.target.value)} />
        {suffix && <em>{suffix}</em>}
      </div>
    </label>
  );
}

function Selecao({ label, value, onChange }: { label: string; value: string; onChange: (valor: string) => void }) {
  return (
    <label className="contexto-field">
      <span>{label}</span>
      <div>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {dialetos.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </div>
    </label>
  );
}

export function ContextoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<ContextoTab>('orcamento');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [regras, setRegras] = useState<Row | null>(null);
  const [textos, setTextos] = useState<Record<TextoTab, string>>(iniciais);
  const [dialeto, setDialeto] = useState('anthropic');
  const [campos, setCampos] = useState({
    janela: '128000', reserva: '8192', maxSaida: '', saidaAssistente: '', margem: '0',
    manter: '6', limiteMensagens: '', limiteResumo: '2000', limiar: '4000',
    entrada: '12000', saida: '800', total: '12800', cache: '4000', inicial: '',
    precoEntrada: '2.5', precoSaida: '10', precoCache: '0.25', hops: '1', janelaUso: '32000',
  });
  const campo = (chave: keyof typeof campos) => campos[chave];
  const define = (chave: keyof typeof campos) => (valor: string) => setCampos((atual) => ({ ...atual, [chave]: valor }));

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('contexto.regras', {});
        if (active && response.ok) setRegras(asRow(response.result));
      } catch {
        if (active) setRegras(null);
      }
    })();
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

  const result = execution?.ok ? asRow(execution.result) : null;
  const resultMarkdown = useMemo(() => text(result?.markdown), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>) => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi medido.');
      return;
    }
    setBusy(true);
    setError('');
    setExecution(null);
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

  const copiar = async (conteudo: string) => {
    if (!conteudo) return;
    try {
      await navigator.clipboard.writeText(conteudo);
      pushToast('Parecer copiado', 'O texto está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const parametros = (ativo: TextoTab): Record<string, unknown> => {
    if (ativo === 'uso') {
      return {
        entrada: inteiro(campo('entrada')), saida: inteiro(campo('saida')),
        total: opcional(campo('total')), cache: inteiro(campo('cache')),
        inicial: opcional(campo('inicial')),
        preco_entrada: numero(campo('precoEntrada')), preco_saida: numero(campo('precoSaida')),
        preco_cache: numero(campo('precoCache')), hops: inteiro(campo('hops'), 1),
        janela: opcional(campo('janelaUso')), modo: level,
      };
    }
    const comum = { mensagens: textos[ativo], modo: level };
    if (ativo === 'orcamento' || ativo === 'corte') {
      return {
        ...comum, janela: inteiro(campo('janela'), 128000), dialeto,
        reserva: opcional(campo('reserva')),
        ...(ativo === 'orcamento'
          ? {
            max_saida_modelo: opcional(campo('maxSaida')),
            saida_assistente: opcional(campo('saidaAssistente')),
            assistente_habilitado: campo('saidaAssistente').trim() !== '',
            margem: inteiro(campo('margem')),
          }
          : { manter_ultimas: inteiro(campo('manter'), 6), limite_mensagens: opcional(campo('limiteMensagens')) }),
      };
    }
    if (ativo === 'tokens') return { ...comum, dialeto };
    if (ativo === 'resumo') return { ...comum, limite: inteiro(campo('limiteResumo'), 2000), limiar: inteiro(campo('limiar'), 4000) };
    return comum;
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (tab === 'regras') return;
    void run(`contexto.${tab}`, parametros(tab));
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const buttonLabel: Record<ContextoTab, string> = {
    orcamento: 'Calcular orçamento', tokens: 'Medir a conversa', corte: 'Cortar histórico',
    higiene: 'Sanear histórico', resumo: 'Preparar resumo', uso: 'Contabilizar uso', regras: 'Ler regras',
  };

  return (
    <div className="diagram-section contexto-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Gauge size={22} /></span>
        <div>
          <span className="eyebrow">O QUE CABE ANTES DE A CONVERSA QUEBRAR</span>
          <h2>Contexto é orçamento</h2>
          <p>Esta camada mede a conversa, divide a janela entre prompt e resposta, fecha o histórico por turno, conserta o que o provedor recusa e prepara o resumo que substitui o que saiu. Nada é enviado a modelo: a estimativa é lexical e a conta é explícita.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Reserva não é sugestão</strong><span>O que a saída reserva não fica com o histórico.</span></li>
          <li><strong>Turno é atômico</strong><span>Chamada e resultado saem juntos ou ficam juntos.</span></li>
          <li><strong>Cortar perde memória</strong><span>Resumo antes do corte: decisão, número e pendência.</span></li>
          <li><strong>Uso ancora o contexto</strong><span>Total sem entrada não diz o tamanho da conversa.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos do contexto">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); setExecution(null); }} aria-pressed={tab === id}>
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
              <span className="eyebrow">{activeTab.label.toUpperCase()}</span>
              <h2>{activeTab.hint}</h2>
            </div>
            <label className="diagram-level">
              <span>NÍVEL</span>
              <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
          </header>

          <form className="form-stack" onSubmit={submit}>
            {tab !== 'uso' && (
              <label className="field">
                <span>{tab === 'higiene' ? 'Conversa com defeito' : tab === 'resumo' ? 'Trecho a resumir' : 'Conversa'}</span>
                <textarea
                  value={textos[tab]}
                  onChange={(event) => setTextos((atual) => ({ ...atual, [tab]: event.target.value }))}
                  rows={12}
                  spellCheck={false}
                />
              </label>
            )}

            {tab === 'orcamento' && (
              <div className="contexto-fields">
                <Numero label="Janela" value={campo('janela')} onChange={define('janela')} suffix="tokens" />
                <Numero label="Reserva de saída" value={campo('reserva')} onChange={define('reserva')} suffix="tokens" hint="Vazio = nenhuma reserva." />
                <Numero label="Teto do modelo" value={campo('maxSaida')} onChange={define('maxSaida')} suffix="tokens" hint="Só reserva no endpoint Anthropic." />
                <Numero label="Limite do assistente" value={campo('saidaAssistente')} onChange={define('saidaAssistente')} suffix="tokens" />
                <Numero label="Margem" value={campo('margem')} onChange={define('margem')} suffix="%" />
                <Selecao label="Dialeto" value={dialeto} onChange={setDialeto} />
              </div>
            )}

            {tab === 'tokens' && (
              <div className="contexto-fields">
                <Selecao label="Dialeto" value={dialeto} onChange={setDialeto} />
              </div>
            )}

            {tab === 'corte' && (
              <div className="contexto-fields">
                <Numero label="Janela" value={campo('janela')} onChange={define('janela')} suffix="tokens" />
                <Numero label="Reserva de saída" value={campo('reserva')} onChange={define('reserva')} suffix="tokens" />
                <Numero label="Manter turnos" value={campo('manter')} onChange={define('manter')} />
                <Numero label="Limite de mensagens" value={campo('limiteMensagens')} onChange={define('limiteMensagens')} hint="Vazio = sem limite." />
                <Selecao label="Dialeto" value={dialeto} onChange={setDialeto} />
              </div>
            )}

            {tab === 'resumo' && (
              <div className="contexto-fields">
                <Numero label="Limite do resumo" value={campo('limiteResumo')} onChange={define('limiteResumo')} suffix="tokens" />
                <Numero label="Limiar de stub" value={campo('limiar')} onChange={define('limiar')} suffix="caracteres" />
              </div>
            )}

            {tab === 'uso' && (
              <>
                <div className="contexto-fields">
                  <Numero label="Entrada" value={campo('entrada')} onChange={define('entrada')} suffix="tokens" />
                  <Numero label="Saída" value={campo('saida')} onChange={define('saida')} suffix="tokens" />
                  <Numero label="Total" value={campo('total')} onChange={define('total')} suffix="tokens" hint="Vazio = contexto igual à entrada." />
                  <Numero label="Cache" value={campo('cache')} onChange={define('cache')} suffix="tokens" />
                  <Numero label="Prompt inicial" value={campo('inicial')} onChange={define('inicial')} suffix="tokens" hint="Gemini/Vertex." />
                  <Numero label="Hops" value={campo('hops')} onChange={define('hops')} />
                  <Numero label="Preço de entrada" value={campo('precoEntrada')} onChange={define('precoEntrada')} suffix="US$/1M" />
                  <Numero label="Preço de saída" value={campo('precoSaida')} onChange={define('precoSaida')} suffix="US$/1M" />
                  <Numero label="Preço de cache" value={campo('precoCache')} onChange={define('precoCache')} suffix="US$/1M" />
                  <Numero label="Janela" value={campo('janelaUso')} onChange={define('janelaUso')} suffix="tokens" />
                </div>
                <p className="diagram-empty"><Wallet size={14} />A conta usa os números do `usage` da chamada: entrada, saída e total, com o prompt inicial quando o provedor reporta.</p>
              </>
            )}

            {tab !== 'uso' && (
              <button type="button" className="button ghost contexto-reset" onClick={() => setTextos((atual) => ({ ...atual, [tab]: iniciais[tab] }))}>
                Restaurar exemplo
              </button>
            )}
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Gauge size={16} />}
              {busy ? 'Medindo…' : buttonLabel[tab]}
            </button>
            {error && <p className="diagram-error" role="alert"><AlertTriangle size={14} />{error}</p>}
          </form>
        </section>
        )}

        <section className="panel diagram-result">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h3>{titulos[tab]}</h3>
            </div>
            {result && resultMarkdown && (
              <div className="diagram-result-actions">
                <button type="button" className="button ghost" onClick={() => void copiar(resultMarkdown)}>Copiar parecer</button>
              </div>
            )}
          </header>

          {tab === 'regras' && <RegrasView regras={regras} />}
          {tab !== 'regras' && !result && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <MessageSquare size={14} />}
              {busy ? 'Rodando a conta…' : 'Preencha à esquerda. O resultado traz métrica, evidência e veredito.'}
            </p>
          )}
          {tab !== 'regras' && result && (
            <div className="diagram-view">
              <Metricas tab={tab} result={result} />
              <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(result.rows)} />
              <Findings items={asRows(result.findings)} />
              <Limitations items={result.limitations} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function RegrasView({ regras }: { regras: Row | null }) {
  if (!regras) return <p className="diagram-empty">O catálogo ainda não chegou da API.</p>;
  const imagem = asRow(regras.imagem);
  const formula = asMap(imagem.formula);
  const fallback = asMap(imagem.fallback);
  const midia = asMap(regras.midia);
  const taxas = asMap(midia.taxa_por_segundo);
  const orcamento = asMap(regras.orcamento);
  const corte = asMap(regras.corte);
  const higiene = asMap(regras.higiene);
  const resumo = asMap(regras.resumo);
  const ferramenta = asMap(regras.ferramenta);
  const limites = asMap(regras.limites);
  const estimativa = asMap(regras.estimativa);
  const limitacoes = ['orcamento', 'tokens', 'corte', 'higiene', 'resumo', 'uso']
    .reduce((total, chave) => total + asList(limites[chave]).length, 0);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="DIALETOS" value={asList(regras.dialetos).length} />
        <Metric label="FÓRMULAS" value={Object.keys(formula).length} />
        <Metric label="ESCALADA DE STUB" value={asList(resumo.escalada_de_stub).length} />
        <Metric label="LIMITES" value={limitacoes} />
        <Metric label="TEXTO" value={`${count(limites.texto).toLocaleString('pt-BR')} chars`} />
        <Metric label="MENSAGENS" value={count(limites.mensagens)} />
      </div>
      <p className="diagram-verdict"><CheckCircle2 size={14} />{text(regras.principio)}</p>
      <p className="diagram-source"><strong>{text(regras.fonte)}</strong><span>catálogo v{text(regras.versao)}</span></p>

      <Tabela
        titulo="Imagem por dialeto"
        colunas={[{ chave: 'dialeto', titulo: 'Dialeto' }, { chave: 'formula', titulo: 'Fórmula' }, { chave: 'fallback', titulo: 'Sem dimensão' }]}
        linhas={Object.keys(formula).map((dialeto) => ({ dialeto, formula: text(formula[dialeto]), fallback: count(fallback[dialeto]) }))}
      />
      <Tabela
        titulo="Mídia por segundo"
        colunas={[
          { chave: 'dialeto', titulo: 'Dialeto' },
          { chave: 'audio', titulo: 'Áudio' },
          { chave: 'video', titulo: 'Vídeo' },
        ]}
        linhas={Object.keys(taxas).map((dialeto) => {
          const taxa = asMap(taxas[dialeto]);
          return { dialeto, audio: `${count(taxa.audio)} tok/s`, video: `${count(taxa.video)} tok/s` };
        })}
      />

      <div className="ciencia-card">
        <h4>Orçamento</h4>
        <ul>
          <li><strong>Sala mínima</strong> — {Math.round(count(orcamento.sala_minima) * 100)}% da janela reservados para a entrada</li>
          <li><strong>Limiar de compactação</strong> — {count(orcamento.limiar_compactacao)}% da sala</li>
        </ul>
        <h5>Precedência da reserva</h5>
        <ul>{asList(orcamento.precedencia_da_reserva).map((item, indice) => <li key={item}><strong>{indice + 1}.</strong> {item}</li>)}</ul>
      </div>
      <div className="ciencia-card">
        <h4>Estimativa</h4>
        <ul>
          <li><strong>Regra</strong> — {text(estimativa.regra)}</li>
          <li><strong>Teto</strong> — {text(estimativa.teto)}</li>
        </ul>
      </div>
      <div className="ciencia-card">
        <h4>Corte por turno</h4>
        <ul>
          <li><strong>Unidade</strong> — {text(corte.unidade)}</li>
          <li><strong>Agrupamento</strong> — {text(corte.agrupamento)}</li>
          <li><strong>Preservados</strong> — {asList(corte.preservados).join(', ')}</li>
          <li><strong>Marca</strong> — <code>{text(corte.marca)}</code></li>
        </ul>
      </div>
      <div className="ciencia-card">
        <h4>Higiene</h4>
        <ul>{asList(higiene.regras).map((item) => <li key={item}>{item}</li>)}</ul>
        <p>Marcadores: <code>{text(asMap(higiene.marcadores).orfa)}</code> e <code>{text(asMap(higiene.marcadores).sem_resultado)}</code>.</p>
      </div>
      <div className="ciencia-card">
        <h4>Resumo</h4>
        <ul>
          <li><strong>Escalada de stub</strong> — {asList(resumo.escalada_de_stub).map((item) => `${item} chars`).join(' → ')}</li>
          <li><strong>Retenção</strong> — {asList(resumo.retencao).join(', ')}</li>
          <li><strong>Anexos</strong> — {text(resumo.placeholder_de_anexo)}</li>
        </ul>
      </div>
      <div className="ciencia-card">
        <h4>Saída de ferramenta</h4>
        <ul>
          <li><strong>Limiar padrão</strong> — {count(ferramenta.limiar_padrao)} caracteres</li>
          <li><strong>Piso</strong> — {count(ferramenta.limiar_minimo)} caracteres</li>
          <li><strong>Cauda preservada</strong> — {count(ferramenta.cauda_preservada)} caracteres</li>
          <li><strong>Marca</strong> — {text(ferramenta.marca)}</li>
        </ul>
      </div>

      <div className="diagram-limitations">
        <strong>DEIXADO DE FORA</strong>
        <ul>{asList(regras.deixado_de_fora).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </div>
  );
}
