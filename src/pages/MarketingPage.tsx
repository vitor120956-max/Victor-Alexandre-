import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  CheckCircle2,
  Clipboard,
  FlaskConical,
  Link2,
  LoaderCircle,
  Mail,
  Megaphone,
  Radar,
  Search,
  Target,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../marketing.css';

type MarketingTab = 'orcamento' | 'teste' | 'utm' | 'email' | 'seo' | 'anuncio' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';
type Moeda = 'BRL' | 'USD' | 'EUR';
type Modelo = 'assinatura' | 'unica';
type TipoNegocio = 'b2c' | 'b2b';
type TipoEmail = 'lifecycle' | 'cold';
type Plataforma = 'google' | 'meta' | 'linkedin';

const tabs: Array<{ id: MarketingTab; label: string; hint: string; icon: typeof Target }> = [
  { id: 'orcamento', label: 'Orçamento', hint: 'Funil e economia unitária', icon: BarChart3 },
  { id: 'teste', label: 'Teste', hint: 'Amostra e duração', icon: FlaskConical },
  { id: 'utm', label: 'Campanha', hint: 'Higiene de URL', icon: Link2 },
  { id: 'email', label: 'E-mail', hint: 'Antes do disparo', icon: Mail },
  { id: 'seo', label: 'SEO', hint: 'A página que a busca lê', icon: Search },
  { id: 'anuncio', label: 'Anúncio', hint: 'Limite por plataforma', icon: Megaphone },
  { id: 'regras', label: 'Regras', hint: 'Limites e fórmulas', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const moedas: Array<{ id: Moeda; label: string }> = [
  { id: 'BRL', label: 'BRL — real' },
  { id: 'USD', label: 'USD — dólar' },
  { id: 'EUR', label: 'EUR — euro' },
];

const plataformas: Array<{ id: Plataforma; label: string }> = [
  { id: 'google', label: 'Google Ads — responsivo de pesquisa' },
  { id: 'meta', label: 'Meta Ads — feed' },
  { id: 'linkedin', label: 'LinkedIn Ads — feed' },
];

const CSV_UTM = `https://exemplo.com/preco?utm_source=linkedin&utm_medium=creator&utm_campaign=lancamento-2026-10&utm_content=hero-cta
https://exemplo.com/blog/preco?utm_source=newsletter&utm_medium=newsletter&utm_campaign=lancamento-2026-10&utm_content=abertura
https://exemplo.com/?utm_source=LinkedIn&utm_medium=Creator&utm_campaign=2026_10&utm_content=hero_CTA
https://exemplo.com/landing?utm_source=google&utm_medium=cpc`;

const EMAIL_CORPO = `O relatório de outubro está pronto.

Ele traz a queda de conversão da página de preço e as três hipóteses que testamos para explicar o recuo.

A leitura leva oito minutos.

Abra o relatório no link.`;

const PAGINA_HTML = `<!doctype html>
<html lang="pt-BR"><head>
<title>Como calcular o preço de um plano SaaS em 2026</title>
<meta name="description" content="Um método para calcular o preço de um plano SaaS a partir de valor percebido, custo e disposição a pagar, com planilha de exemplo para copiar.">
<link rel="canonical" href="https://exemplo.com/preco-saas">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article"}</script>
</head><body>
<h1>Como calcular o preço de um plano SaaS</h1>
<p>O preço de um plano SaaS sai de três números: o valor que o cliente percebe, o custo de servir aquela conta e a disposição a pagar do segmento. Comece pelo valor percebido, use o custo como piso e a disposição a pagar como teto. O número final fica no meio, e é onde o cliente aceita sem negociar.</p>
<h2>Qual é o custo de servir cada cliente?</h2>
<p>Some infraestrutura, suporte e tempo de implantação por conta. Esse total é o piso do preço, não o preço. Uma conta que consome duas horas de suporte por mês custa mais do que o servidor que ela usa, e o plano precisa refletir isso. Separe custo fixo de custo variável antes de dividir pelo número de contas ativas.</p>
<h2>Como medir a disposição a pagar?</h2>
<p>A conversa com dez clientes atuais informa mais do que qualquer planilha de concorrente. Pergunte o que a ferramenta substitui, quanto custava esse substituto e o que aconteceria se o acesso terminasse amanhã. Anote as faixas que aparecem e compare com o preço praticado hoje.</p>
<h2>Onde entra o valor percebido?</h2>
<p>O valor percebido é o que o cliente deixa de perder ou de gastar. Se o produto economiza quatro horas de trabalho por semana, o preço se ancora nessa economia, não no custo do servidor. Ancore no resultado e mantenha o custo como margem de segurança.</p>
<h2>Como testar o preço sem perder receita?</h2>
<p>Comece pelo segmento novo, nunca pelo cliente antigo. O reajuste só vale para quem entra depois da mudança, e o aviso precisa sair com meses de antecedência. Teste a página de preço com o plano mais caro primeiro, depois o plano do meio, e observe a escolha de cada coorte.</p>
<h2>Qual é o erro mais comum?</h2>
<p>Ancorar no preço errado. Quando o plano barato aparece primeiro, o cliente usa aquele número como referência e todo o resto parece caro. Mostre a entrega completa, com o preço correspondente, e deixe a comparação acontecer a partir do topo.</p>
<img src="grafico.png" alt="Disposição a pagar por segmento">
<a href="/blog/preco">Outro texto sobre preço</a>
</body></html>`;

const ANUNCIOS = `Automatize o funil de vendas
Teste grátis por 14 dias
Painel único para o time
Relatório sem planilha`;

const DESCRICOES = `Organize leads, propostas e follow-up em um painel só, sem planilha paralela.
Comece em cinco minutos e veja o funil inteiro no mesmo lugar, com histórico.`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const simbolo: Record<string, string> = { BRL: 'R$', USD: 'US$', EUR: '€' };
const fmt = (value: unknown, casas = 2): string => {
  const numero = Number(value);
  if (!Number.isFinite(numero)) return '—';
  return numero.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
};
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

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

function Tabela({ titulo, colunas, children }: { titulo: string; colunas: string[]; children: React.ReactNode }) {
  return (
    <div className="marketing-table-block">
      <h4>{titulo}</h4>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr>{colunas.map((coluna) => <th key={coluna}>{coluna}</th>)}</tr></thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

function OrcamentoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const moeda = simbolo[text(metrics.moeda)] ?? 'R$';
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="CAC" value={`${moeda} ${fmt(metrics.cac)}`} tone={count(metrics.ltv_cac) < 1 ? 'danger' : 'ok'} />
        <Metric label="ROAS" value={`${fmt(metrics.roas)}×`} tone={count(metrics.roas) < 1 ? 'danger' : 'ok'} />
        <Metric label="PAYBACK" value={`${fmt(metrics.payback_meses)} ${text(metrics.modelo) === 'assinatura' ? 'meses' : 'vendas'}`} />
        <Metric label="LTV / CAC" value={`${fmt(metrics.ltv_cac)}×`} tone={count(metrics.ltv_cac) < 3 ? 'warning' : 'ok'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Do investimento ao cliente" colunas={['Etapa', 'Número', 'Fórmula']}>
        {asRows(result.rows).map((row) => (
          <tr key={text(row.etapa)}>
            <td><strong>{text(row.etapa)}</strong></td>
            <td>{text(row.numero)}</td>
            <td><code>{text(row.formula)}</code></td>
          </tr>
        ))}
      </Tabela>
      {asRows(result.sensibilidade).length > 0 && (
        <Tabela titulo="O que precisa mudar para bater o CAC alvo" colunas={['Alavanca', 'Hoje', 'Necessário', 'Variação']}>
          {asRows(result.sensibilidade).map((row) => (
            <tr key={text(row.alavanca)}>
              <td>{text(row.alavanca)}</td><td>{text(row.atual)}</td>
              <td><strong>{text(row.necessario)}</strong></td><td>{text(row.delta)}</td>
            </tr>
          ))}
        </Tabela>
      )}
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function TesteView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="POR VARIANTE" value={fmt(metrics.por_variante, 0)} />
        <Metric label="TOTAL" value={fmt(metrics.total, 0)} />
        <Metric label="DURAÇÃO" value={`${count(metrics.dias)} dias`} tone={count(metrics.viavel) ? 'ok' : 'danger'} />
        <Metric label="ALFA" value={fmt(metrics.alfa_ajustado, 5)} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="A conta" colunas={['Etapa', 'Número', 'Fórmula']}>
        {asRows(result.rows).map((row) => (
          <tr key={text(row.etapa)}>
            <td><strong>{text(row.etapa)}</strong></td>
            <td>{text(row.numero)}</td>
            <td><code>{text(row.formula)}</code></td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function UtmView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="URLS" value={count(metrics.urls)} />
        <Metric label="PRONTAS" value={count(metrics.ok)} tone="ok" />
        <Metric label="CORRIGIR" value={count(metrics.corrigir)} tone={count(metrics.corrigir) ? 'warning' : 'ok'} />
        <Metric label="ACHADOS" value={count(metrics.achados)} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Por URL" colunas={['Origem', 'Mídia', 'Campanha', 'Situação']}>
        {asRows(result.rows).map((row) => (
          <tr key={text(row.url)}>
            <td><code>{text(row.source) || '—'}</code></td>
            <td><code>{text(row.medium) || '—'}</code></td>
            <td><code>{text(row.campaign) || '—'}</code></td>
            <td><span className={`diagram-state ${text(row.status) === 'ok' ? 'is-ok' : 'is-danger'}`}>{text(row.status)}</span></td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function EmailView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="ASSUNTO" value={`${count(metrics.assunto)} car.`} tone={count(metrics.assunto) >= 40 && count(metrics.assunto) <= 60 ? 'ok' : 'warning'} />
        <Metric label="PRÉ-CABEÇALHO" value={`${count(metrics.preview)} car.`} />
        <Metric label="LINKS" value={count(metrics.links)} />
        <Metric label="MARCAS DE IA" value={count(metrics.tells)} tone={count(metrics.tells) ? 'warning' : 'ok'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Campos medidos" colunas={['Campo', 'Conteúdo', 'Tamanho']}>
        {asRows(result.rows).map((row) => (
          <tr key={text(row.campo)}>
            <td><strong>{text(row.campo)}</strong></td>
            <td>{text(row.valor)}</td>
            <td>{count(row.tamanho)}</td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function SeoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="PALAVRAS" value={count(metrics.palavras)} tone={count(metrics.palavras) < 300 ? 'warning' : 'ok'} />
        <Metric label="H1" value={count(metrics.h1)} tone={count(metrics.h1) === 1 ? 'ok' : 'danger'} />
        <Metric label="IMAGENS SEM ALT" value={count(metrics.sem_alt)} tone={count(metrics.sem_alt) ? 'danger' : 'ok'} />
        <Metric label="LINKS" value={`${count(metrics.links_internos)} / ${count(metrics.links_externos)}`} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="O que a página declara" colunas={['Elemento', 'Conteúdo', 'Medida']}>
        {asRows(result.rows).map((row) => (
          <tr key={text(row.elemento)}>
            <td><strong>{text(row.elemento)}</strong></td>
            <td>{text(row.valor)}</td>
            <td>{count(row.medida)}</td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function AnuncioView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="PEÇAS" value={count(metrics.pecas)} />
        <Metric label="TÍTULOS" value={count(metrics.titulos)} />
        <Metric label="DESCRIÇÕES" value={count(metrics.descricoes)} />
        <Metric label="ACIMA DO LIMITE" value={count(metrics.acima_do_limite)} tone={count(metrics.acima_do_limite) ? 'danger' : 'ok'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Caractere por peça" colunas={['Campo', '#', 'Texto', 'Tamanho', 'Limite', 'Situação']}>
        {asRows(result.rows).map((row) => (
          <tr key={`${text(row.campo)}-${text(row.indice)}`}>
            <td>{text(row.campo)}</td>
            <td>{count(row.indice)}</td>
            <td>{text(row.texto)}</td>
            <td>{count(row.tamanho)}</td>
            <td>{count(row.limite)}</td>
            <td><span className={`diagram-state ${text(row.situacao) === 'ok' ? 'is-ok' : 'is-danger'}`}>{text(row.situacao)}</span></td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function RegrasView({ regras }: { regras: Row | null }) {
  if (!regras) return <p className="diagram-empty">O catálogo de regras ainda não chegou da API.</p>;
  const plataformasLista = asRows(regras.plataformas);
  const amostra = asRows(regras.amostra);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="PLATAFORMAS" value={plataformasLista.length} />
        <Metric label="MEDIUMS" value={asList(regras.mediums).length} />
        <Metric label="FÓRMULAS" value={asRows(regras.formulas).length} />
        <Metric label="RUBRICA" value={asRows(regras.integridade).length} />
      </div>
      <p className="diagram-verdict"><Target size={14} />{text(regras.principio)}</p>
      <Tabela titulo="Amostra por variante — α 0,05 · poder 0,80" colunas={['Base', '10% de ganho', '20%', '50%']}>
        {amostra.map((row) => (
          <tr key={text(row.baseline)}>
            <td><strong>{text(row.baseline)}%</strong></td>
            <td>{fmt(row.lift_10, 0)}</td>
            <td>{fmt(row.lift_20, 0)}</td>
            <td>{fmt(row.lift_50, 0)}</td>
          </tr>
        ))}
      </Tabela>
      <div className="marketing-platforms">
        {plataformasLista.map((plataforma) => (
          <article key={text(plataforma.id)}>
            <header><strong>{text(plataforma.nome)}</strong></header>
            <p>{text(plataforma.nota)}</p>
            <ul>
              {Object.entries(asRow(plataforma.campos)).map(([campo, valor]) => {
                const regra = asRow(valor);
                return (
                  <li key={campo}>
                    <span>{text(regra.rotulo)}</span>
                    <code>{count(regra.limite)} car. · {count(regra.minimo)}–{count(regra.maximo)} peças</code>
                  </li>
                );
              })}
            </ul>
          </article>
        ))}
      </div>
      <div className="marketing-rules">
        {asRows(regras.formulas).map((row) => (
          <article key={text(row.id)}><span>{text(row.id)}</span><p><code>{text(row.formula)}</code></p></article>
        ))}
      </div>
      <div className="diagram-note-card">
        <h4>Rubrica de integridade da recomendação</h4>
        <ul className="diagram-traps">
          {asRows(regras.integridade).map((row) => (
            <li key={text(row.id)}><strong>{text(row.id)}</strong> — {text(row.regra)}</li>
          ))}
        </ul>
      </div>
      <div className="diagram-limitations">
        <strong>DEIXADO DE FORA</strong>
        <ul>{asList(regras.deixado_de_fora).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </div>
  );
}

export function MarketingPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<MarketingTab>('orcamento');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [view, setView] = useState<MarketingTab>('orcamento');
  const [regras, setRegras] = useState<Row | null>(null);

  const [orcamento, setOrcamento] = useState('30000');
  const [cpm, setCpm] = useState('28');
  const [ctr, setCtr] = useState('1.8');
  const [cvr, setCvr] = useState('6');
  const [fechamento, setFechamento] = useState('22');
  const [ticket, setTicket] = useState('199');
  const [margem, setMargem] = useState('78');
  const [vidaUtil, setVidaUtil] = useState('18');
  const [cacAlvo, setCacAlvo] = useState('');
  const [metaArr, setMetaArr] = useState('');
  const [arpc, setArpc] = useState('');
  const [retencao, setRetencao] = useState('');
  const [moeda, setMoeda] = useState<Moeda>('BRL');
  const [modelo, setModelo] = useState<Modelo>('assinatura');

  const [baseline, setBaseline] = useState('3');
  const [mde, setMde] = useState('20');
  const [trafego, setTrafego] = useState('4000');
  const [variantes, setVariantes] = useState('2');
  const [alfa, setAlfa] = useState('0.05');
  const [poder, setPoder] = useState('0.8');
  const [exposicao, setExposicao] = useState('80');
  const [tipoNegocio, setTipoNegocio] = useState<TipoNegocio>('b2b');

  const [urls, setUrls] = useState(CSV_UTM);

  const [assunto, setAssunto] = useState('O relatório de outubro está pronto');
  const [preview, setPreview] = useState('Cinco páginas com o que mudou no funil e o que fazer nesta semana.');
  const [cta, setCta] = useState('Abrir o relatório');
  const [corpo, setCorpo] = useState(EMAIL_CORPO);
  const [tipoEmail, setTipoEmail] = useState<TipoEmail>('lifecycle');
  const [htmlEmail, setHtmlEmail] = useState('');

  const [html, setHtml] = useState(PAGINA_HTML);
  const [palavraChave, setPalavraChave] = useState('preço');
  const [urlPagina, setUrlPagina] = useState('https://exemplo.com/preco-saas');

  const [plataforma, setPlataforma] = useState<Plataforma>('google');
  const [titulos, setTitulos] = useState(ANUNCIOS);
  const [descricoes, setDescricoes] = useState(DESCRICOES);
  const [textoPrincipal, setTextoPrincipal] = useState('');
  const [urlFinal, setUrlFinal] = useState('https://exemplo.com/x?utm_content=pesquisa-marca');

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('marketing.regras', {});
        if (active && response.ok) setRegras(asRow(response.result));
      } catch {
        if (active) setRegras(null);
      }
    })();
    return () => { active = false; };
  }, [backendOnline, executeSkill]);

  const result = execution?.ok ? asRow(execution.result) : null;
  const resultMarkdown = useMemo(() => text(result?.markdown), [result]);

  const run = async (skillId: string, parameters: Record<string, unknown>, next: MarketingTab) => {
    if (!backendOnline) {
      setError('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi medido.');
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

  const copiar = async (conteudo: string, titulo: string) => {
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
    if (tab === 'orcamento') {
      void run('marketing.orcamento', {
        orcamento: Number(orcamento) || 0,
        cpm: Number(cpm) || 0,
        ctr: Number(ctr) || 0,
        cvr: Number(cvr) || 0,
        fechamento: Number(fechamento) || 0,
        ticket: Number(ticket) || 0,
        margem: Number(margem) || 0,
        vida_util_meses: Number(vidaUtil) || 0,
        cac_alvo: Number(cacAlvo) || 0,
        meta_arr: Number(metaArr) || 0,
        arpc: Number(arpc) || 0,
        retencao_anual: Number(retencao) || 0,
        moeda,
        modelo,
        modo: level,
      }, 'orcamento');
      return;
    }
    if (tab === 'teste') {
      void run('marketing.teste', {
        baseline: Number(baseline) || 0,
        mde: Number(mde) || 0,
        trafego_diario: Number(trafego) || 0,
        variantes: Number(variantes) || 2,
        alfa: Number(alfa) || 0.05,
        poder: Number(poder) || 0.8,
        exposicao: Number(exposicao) || 100,
        tipo: tipoNegocio,
        modo: level,
      }, 'teste');
      return;
    }
    if (tab === 'utm') {
      void run('marketing.utm', { urls, modo: level }, 'utm');
      return;
    }
    if (tab === 'email') {
      void run('marketing.email', {
        assunto, preview, cta, corpo, tipo: tipoEmail, html: htmlEmail, modo: level,
      }, 'email');
      return;
    }
    if (tab === 'seo') {
      void run('marketing.seo', { html, palavra_chave: palavraChave, url: urlPagina, modo: level }, 'seo');
      return;
    }
    if (tab === 'anuncio') {
      void run('marketing.anuncio', {
        plataforma, titulos, descricoes, texto_principal: textoPrincipal, url_final: urlFinal, modo: level,
      }, 'anuncio');
      return;
    }
    setError('O catálogo de regras é lido ao abrir a página.');
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const buttonLabel: Record<MarketingTab, string> = {
    orcamento: 'Calcular o funil', teste: 'Dimensionar o teste', utm: 'Conferir campanha',
    email: 'Revisar e-mail', seo: 'Auditar a página', anuncio: 'Conferir anúncio', regras: 'Ler regras',
  };

  return (
    <div className="diagram-section marketing-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Radar size={22} /></span>
        <div>
          <span className="eyebrow">MEDIR ANTES DE ESCREVER</span>
          <h2>Marketing se decide por número medido</h2>
          <p>Copy é julgamento; conta é fato. Esta camada faz a conta que sustenta a decisão: o funil e a economia unitária, a amostra que o teste precisa, a higiene da URL de campanha, o que o e-mail carrega antes do disparo, o que a página declara ao buscador e o que cabe no limite de cada plataforma de anúncio. Ela não escreve copy e não abre conta de anúncio.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Número declarado, conta explícita</strong><span>Cada resultado mostra a fórmula; nenhuma taxa vem de benchmark de mercado.</span></li>
          <li><strong>Teste antes do resultado</strong><span>Amostra e regra de parada se decidem antes de olhar o painel.</span></li>
          <li><strong>Atribuição é texto</strong><span>Sem UTM limpa, o relatório inventa um canal.</span></li>
          <li><strong>Limite é lei</strong><span>Caractere a mais é peça recusada, não questão de estilo.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos do marketing">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => { setTab(id); setError(''); if (id === 'regras') setExecution(null); }} aria-pressed={tab === id}>
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
            {tab === 'orcamento' && (
              <>
                <div className="field-row">
                  <label className="field"><span>Orçamento mensal</span><input value={orcamento} onChange={(event) => setOrcamento(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Moeda</span>
                    <select value={moeda} onChange={(event) => setMoeda(event.target.value as Moeda)}>
                      {moedas.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                    </select>
                  </label>
                </div>
                <div className="field-row">
                  <label className="field"><span>CPM</span><input value={cpm} onChange={(event) => setCpm(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>CTR (%)</span><input value={ctr} onChange={(event) => setCtr(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Clique → lead (%)</span><input value={cvr} onChange={(event) => setCvr(event.target.value)} inputMode="decimal" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Lead → cliente (%)</span><input value={fechamento} onChange={(event) => setFechamento(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Ticket</span><input value={ticket} onChange={(event) => setTicket(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Margem (%)</span><input value={margem} onChange={(event) => setMargem(event.target.value)} inputMode="decimal" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Modelo</span>
                    <select value={modelo} onChange={(event) => setModelo(event.target.value as Modelo)}>
                      <option value="assinatura">Assinatura</option>
                      <option value="unica">Venda única</option>
                    </select>
                  </label>
                  <label className="field"><span>Vida útil (meses)</span><input value={vidaUtil} onChange={(event) => setVidaUtil(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>CAC alvo</span><input value={cacAlvo} onChange={(event) => setCacAlvo(event.target.value)} inputMode="decimal" placeholder="opcional" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Meta de ARR</span><input value={metaArr} onChange={(event) => setMetaArr(event.target.value)} inputMode="decimal" placeholder="opcional" /></label>
                  <label className="field"><span>ARPC</span><input value={arpc} onChange={(event) => setArpc(event.target.value)} inputMode="decimal" placeholder="opcional" /></label>
                  <label className="field"><span>Retenção anual (%)</span><input value={retencao} onChange={(event) => setRetencao(event.target.value)} inputMode="decimal" placeholder="opcional" /></label>
                </div>
              </>
            )}
            {tab === 'teste' && (
              <>
                <div className="field-row">
                  <label className="field"><span>Linha de base (%)</span><input value={baseline} onChange={(event) => setBaseline(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>MDE (%)</span><input value={mde} onChange={(event) => setMde(event.target.value)} inputMode="decimal" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Tráfego diário</span><input value={trafego} onChange={(event) => setTrafego(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Variantes</span><input value={variantes} onChange={(event) => setVariantes(event.target.value)} inputMode="numeric" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Alfa</span><input value={alfa} onChange={(event) => setAlfa(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Poder</span><input value={poder} onChange={(event) => setPoder(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Exposição (%)</span><input value={exposicao} onChange={(event) => setExposicao(event.target.value)} inputMode="decimal" /></label>
                </div>
                <label className="field"><span>Tipo de negócio</span>
                  <select value={tipoNegocio} onChange={(event) => setTipoNegocio(event.target.value as TipoNegocio)}>
                    <option value="b2c">B2C — ciclo semanal</option>
                    <option value="b2b">B2B — dois ciclos de semana</option>
                  </select>
                </label>
              </>
            )}
            {tab === 'utm' && (
              <label className="field">
                <span>URLs de campanha, uma por linha</span>
                <textarea value={urls} onChange={(event) => setUrls(event.target.value)} rows={10} spellCheck={false} />
              </label>
            )}
            {tab === 'email' && (
              <>
                <label className="field"><span>Assunto</span><input value={assunto} onChange={(event) => setAssunto(event.target.value)} maxLength={200} /></label>
                <label className="field"><span>Pré-cabeçalho</span><input value={preview} onChange={(event) => setPreview(event.target.value)} maxLength={300} /></label>
                <label className="field"><span>Chamada principal</span><input value={cta} onChange={(event) => setCta(event.target.value)} maxLength={200} /></label>
                <label className="field"><span>Corpo em texto</span><textarea value={corpo} onChange={(event) => setCorpo(event.target.value)} rows={9} /></label>
                <div className="field-row">
                  <label className="field"><span>Tipo</span>
                    <select value={tipoEmail} onChange={(event) => setTipoEmail(event.target.value as TipoEmail)}>
                      <option value="lifecycle">Ciclo de vida</option>
                      <option value="cold">Primeiro contato</option>
                    </select>
                  </label>
                </div>
                <label className="field"><span>HTML do e-mail (opcional)</span><textarea value={htmlEmail} onChange={(event) => setHtmlEmail(event.target.value)} rows={4} placeholder="Com HTML, a regra de descadastro é conferida no rodapé." spellCheck={false} /></label>
              </>
            )}
            {tab === 'seo' && (
              <>
                <div className="field-row">
                  <label className="field"><span>Palavra-chave principal</span><input value={palavraChave} onChange={(event) => setPalavraChave(event.target.value)} /></label>
                  <label className="field"><span>URL da página</span><input value={urlPagina} onChange={(event) => setUrlPagina(event.target.value)} /></label>
                </div>
                <label className="field"><span>HTML da página</span><textarea value={html} onChange={(event) => setHtml(event.target.value)} rows={14} spellCheck={false} /></label>
              </>
            )}
            {tab === 'anuncio' && (
              <>
                <label className="field"><span>Plataforma</span>
                  <select value={plataforma} onChange={(event) => setPlataforma(event.target.value as Plataforma)}>
                    {plataformas.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
                <label className="field"><span>Títulos, um por linha</span><textarea value={titulos} onChange={(event) => setTitulos(event.target.value)} rows={5} /></label>
                <label className="field"><span>Descrições, uma por linha</span><textarea value={descricoes} onChange={(event) => setDescricoes(event.target.value)} rows={4} /></label>
                <label className="field"><span>Texto principal</span><textarea value={textoPrincipal} onChange={(event) => setTextoPrincipal(event.target.value)} rows={3} placeholder="Meta: 125 caracteres. LinkedIn: 150." /></label>
                <label className="field"><span>URL final</span><input value={urlFinal} onChange={(event) => setUrlFinal(event.target.value)} /></label>
              </>
            )}
            {tab === 'regras' && (
              <p className="diagram-empty"><Clipboard size={14} />As regras vêm do servidor: limites por plataforma, fórmulas, grade de amostra e rubrica de integridade.</p>
            )}

            <button className="button primary" type="submit" disabled={busy || (tab === 'regras' && !regras)}>
              {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Target size={16} />}
              {busy ? 'Calculando…' : buttonLabel[tab]}
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
                  <button type="button" className="button ghost" onClick={() => void copiar(resultMarkdown, 'Parecer copiado')}>
                    Copiar parecer
                  </button>
                )}
              </div>
            )}
          </header>

          {!result && tab === 'regras' && <RegrasView regras={regras} />}
          {!result && tab !== 'regras' && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <Target size={14} />}
              {busy ? 'Rodando a conta…' : 'Preencha à esquerda. A conta é determinística e mostra a fórmula.'}
            </p>
          )}
          {result && view === 'orcamento' && <OrcamentoView result={result} />}
          {result && view === 'teste' && <TesteView result={result} />}
          {result && view === 'utm' && <UtmView result={result} />}
          {result && view === 'email' && <EmailView result={result} />}
          {result && view === 'seo' && <SeoView result={result} />}
          {result && view === 'anuncio' && <AnuncioView result={result} />}
        </section>
      </div>
    </div>
  );
}
