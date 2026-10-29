import { useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Briefcase,
  Bug,
  CheckCircle2,
  Clipboard,
  Gauge,
  KeyRound,
  Layers,
  LoaderCircle,
  MousePointerClick,
  RefreshCw,
  Table2,
  Terminal,
  Wand2,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../escritorio.css';

type OfficeTab = 'comando' | 'receita' | 'paginas' | 'lote' | 'escopos' | 'erros' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: OfficeTab; label: string; hint: string; icon: typeof Terminal }> = [
  { id: 'comando', label: 'Comando', hint: 'Serviço → gws', icon: Terminal },
  { id: 'receita', label: 'Receita', hint: 'Passos com ensaio', icon: Wand2 },
  { id: 'paginas', label: 'Páginas', hint: 'Token → próxima', icon: Layers },
  { id: 'lote', label: 'Lote', hint: 'Itens → chamadas', icon: Table2 },
  { id: 'escopos', label: 'Escopos', hint: 'Operação → consentimento', icon: KeyRound },
  { id: 'erros', label: 'Erros', hint: 'Saída → causa', icon: Bug },
  { id: 'regras', label: 'Regras', hint: 'O vocabulário usado', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite' },
  { id: 'full', label: 'Full' },
  { id: 'ultra', label: 'Ultra' },
];

const servicos = [
  'drive', 'gmail', 'calendar', 'sheets', 'docs', 'slides', 'chat', 'admin', 'classroom',
  'forms', 'keep', 'meet', 'people', 'script', 'tasks', 'events', 'workflow', 'modelarmor',
];

const operacoesLote = [
  { id: 'sheets.valores', label: 'Sheets — valores' },
  { id: 'sheets.requisicoes', label: 'Sheets — requisições' },
  { id: 'docs.requisicoes', label: 'Docs — requisições' },
  { id: 'gmail.ids', label: 'Gmail — IDs' },
  { id: 'drive.permissoes', label: 'Drive — permissões' },
  { id: 'calendar.eventos', label: 'Calendar — eventos' },
];

const laws = [
  ['A descoberta manda', 'O comando nasce do documento de descoberta do Google: serviço, recurso e método. O que não estiver lá, não existe aqui.'],
  ['Menor escopo', 'Cada operação aponta o escopo que precisa. Conceder `drive` inteiro para ler uma pasta amplia o dano possível.'],
  ['Ensaio antes da escrita', '`--dry-run` mostra o pedido HTTP sem enviar. O plano só grava depois de você comparar o corpo.'],
  ['Erro não se repete às cegas', 'Cota e falha transitória esperam; escrita com erro pode ter sido aplicada. Confira o efeito antes de repetir.'],
];

const sampleParams = `{"pageSize":5,"q":"trashed = false","fields":"files(id,name,mimeType)"}`;
const sampleInputs = `{"ARQUIVO":"/home/ana/relatorio.pdf","NOME":"Relatório de outubro","PASTA":"1Pasta..."}`;
const samplePages = `{"files":[{"id":"1Ab","name":"Relatório"},{"id":"1Ac","name":"Planilha"}],"nextPageToken":"~!!~AI9..."}`;
const sampleItems = `[
  {"range":"Vendas!A1:C1","values":[["Ana","95","2026-10-23"]]},
  {"range":"Vendas!A2:C2","values":[["Bruno","88","2026-10-24"]]}
]`;
const sampleOps = `gmail users.messages list
sheets +append
drive files create`;
const sampleGrants = `gmail.modify, drive, tasks`;
const sampleError = `{"error":{"code":403,"message":"Gmail API has not been used in project 123 before or it is disabled.","errors":[{"reason":"accessNotConfigured"}]}}`;
const recipeFallback = [
  'agenda-do-dia', 'standup', 'digest-semanal', 'triagem-da-caixa', 'enviar-email',
  'responder-email', 'ler-planilha', 'acrescentar-linha', 'subir-arquivo',
  'organizar-pasta', 'convidar-evento', 'arquivar-rotulados', 'tarefa-do-email',
  'relatorio-de-planilha', 'checar-arquivos-grandes',
];

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const num = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const riskLabel: Record<string, string> = { leitura: 'leitura', escrita: 'escrita', destrutivo: 'destrutivo' };
const errorGroupLabel: Record<string, string> = {
  cota: 'cota', autenticacao: 'autenticação', configuracao: 'configuração',
  permissoes: 'permissões', validacao: 'validação', 'nao-encontrado': 'não encontrado',
  transitorio: 'transitório', desconhecido: 'desconhecido',
};

function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`office-badge is-${kind}`}>{children}</span>;
}

function CopyLine({ value }: { value: string }) {
  const { pushToast } = useApp();
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      window.setTimeout(() => setDone(false), 1400);
    } catch {
      pushToast('Não foi possível copiar; selecione o texto.', 'error');
    }
  };
  return (
    <div className="office-code">
      <button type="button" onClick={() => void copy()}>{done ? 'copiado' : 'copiar'}</button>
      <pre>{value}</pre>
    </div>
  );
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="office-empty"><CheckCircle2 size={14} />Nada bloqueando pelas regras estáticas.</p>;
  return (
    <div className="office-findings">
      {findings.map((item) => {
        const group = text(item.group);
        return (
          <article className={`office-finding is-${group}`} key={`${text(item.id)}-${text(item.kind)}-${text(item.location)}`}>
            <header>
              <span className="office-group">{groupLabel[group] ?? group}</span>
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

function Verdict({ result }: { result: Row }) {
  const danger = num(asRow(result.counts).must) > 0;
  return (
    <div className={`office-verdict ${danger ? 'is-danger' : 'is-ok'}`}>
      {danger ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
      <div>
        <strong>{text(result.verdict)}</strong>
        <p>{danger ? 'Corrija os itens obrigatórios antes de rodar o comando.' : 'O plano está coerente com as regras estáticas.'}</p>
      </div>
    </div>
  );
}

function Metrics({ items }: { items: Array<{ label: string; value: ReactNode; tone?: 'ok' | 'warning' | 'danger' }> }) {
  return <div className="office-metrics">{items.map((item) => <Metric key={item.label} {...item} />)}</div>;
}

function Limitations({ items }: { items: unknown }) {
  const list = asList(items);
  if (!list.length) return null;
  return (
    <div className="office-limits">
      <strong>NÃO VERIFICADO</strong>
      <ul>{list.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Report({ markdown }: { markdown: string }) {
  if (!markdown) return null;
  return (
    <details className="office-report">
      <summary><Clipboard size={12} />Relatório em Markdown</summary>
      <pre>{markdown}</pre>
    </details>
  );
}

function CommandView({ result }: { result: Row }) {
  const escopos = asRows(result.escopos);
  const risco = text(result.risco);
  const metrics = asRow(result.metrics);
  return (
    <div className="office-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'RISCO', value: <Badge kind={risco}>{riskLabel[risco] ?? risco}</Badge> },
        { label: 'ESCOPOS', value: num(metrics.escopos) },
        { label: 'PARÂMETROS', value: num(metrics.parametros) },
        { label: 'FLAGS', value: num(metrics.flags) },
      ]} />
      <section>
        <h3><Terminal size={13} />Comando</h3>
        <CopyLine value={text(result.comando)} />
        {Boolean(result.simular) && <p className="office-note">Ensaio ligado: a escrita sai com <code>--dry-run</code>.</p>}
      </section>
      {escopos.length > 0 && (
        <section>
          <h3><KeyRound size={13} />Escopos necessários</h3>
          <ul className="office-keys">
            {escopos.map((item) => (
              <li key={text(item.chave)}><code>{text(item.chave)}</code><span>{text(item.rotulo)} · {text(item.acesso)}</span></li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function RecipeView({ result }: { result: Row }) {
  const passos = asRows(result.passos);
  const escopos = asRows(result.escopos);
  const metrics = asRow(result.metrics);
  return (
    <div className="office-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'PASSOS', value: num(metrics.passos) },
        { label: 'SERVIÇOS', value: num(metrics.servicos) },
        { label: 'ESCOPOS', value: num(metrics.escopos) },
        { label: 'ENSAIOS', value: num(metrics.simulados) },
      ]} />
      <section>
        <h3><Wand2 size={13} />Passos</h3>
        <div className="office-steps">
          {passos.map((passo) => (
            <article className="office-step" key={text(passo.ordem)}>
              <header>
                <strong>{text(passo.ordem)}. {text(passo.titulo)}</strong>
                <Badge kind={text(passo.risco)}>{riskLabel[text(passo.risco)] ?? text(passo.risco)}</Badge>
                {Boolean(passo.simular) && <Badge kind="info">ensaio</Badge>}
              </header>
              <CopyLine value={text(passo.comando)} />
              <dl>
                <div><dt>Por quê</dt><dd>{text(passo.porque)}</dd></div>
                <div><dt>Deu certo se</dt><dd>{text(passo.verifica)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>
      {Boolean(result.verificacao) && (
        <div className="office-banner is-ok">
          <CheckCircle2 size={14} />
          <div><strong>Verificação final</strong><p>{text(result.verificacao)}</p></div>
        </div>
      )}
      {Boolean(result.rollback) && (
        <section>
          <h3><RefreshCw size={13} />Se der errado</h3>
          <p className="office-note">{text(result.rollback)}</p>
        </section>
      )}
      {escopos.length > 0 && (
        <section>
          <h3><KeyRound size={13} />Escopos</h3>
          <div className="office-tag-row">{escopos.map((item) => <Badge kind="info" key={text(item.chave)}>{text(item.chave)}</Badge>)}</div>
        </section>
      )}
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function PagesView({ result }: { result: Row }) {
  const rows = asRows(result.paginas);
  const metrics = asRow(result.metrics);
  const completa = Boolean(result.completa);
  return (
    <div className="office-view">
      <div className={`office-verdict ${completa ? 'is-ok' : 'is-warning'}`}>
        {completa ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
        <div>
          <strong>{completa ? 'Coleta completa' : 'Coleta incompleta'}</strong>
          <p>{completa ? 'A última página não trouxe nextPageToken.' : 'Ainda há token: o que você tem é uma amostra.'}</p>
        </div>
      </div>
      <Metrics items={[
        { label: 'PÁGINAS', value: num(metrics.paginas) },
        { label: 'ITENS', value: num(metrics.itens) },
        { label: 'ÚNICOS', value: num(metrics.unicos), tone: 'ok' },
        { label: 'DUPLICADOS', value: num(metrics.duplicados), tone: num(metrics.duplicados) ? 'danger' : undefined },
      ]} />
      <section>
        <h3><Layers size={13} />Páginas</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>#</th><th>Chave</th><th>Itens</th><th>Únicos</th><th>Token</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={text(row.pagina)}>
                  <td>{text(row.pagina)}</td>
                  <td><code>{text(row.chave)}</code></td>
                  <td>{text(row.itens)}</td>
                  <td>{text(row.unicos)}</td>
                  <td>{text(row.token) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {Boolean(result.proximoComando) && (
        <section>
          <h3><ArrowRight size={13} />Próxima chamada</h3>
          <CopyLine value={text(result.proximoComando)} />
        </section>
      )}
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function BatchView({ result }: { result: Row }) {
  const lotes = asRows(result.lotes);
  const invalidos = asRows(result.invalidos);
  const metrics = asRow(result.metrics);
  return (
    <div className="office-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'ITENS', value: num(metrics.itens) },
        { label: 'VÁLIDOS', value: num(metrics.validos), tone: 'ok' },
        { label: 'RECUSADOS', value: num(metrics.invalidos), tone: num(metrics.invalidos) ? 'danger' : undefined },
        { label: 'CHAMADAS', value: num(metrics.chamadas) },
      ]} />
      {invalidos.length > 0 && (
        <section>
          <h3><AlertTriangle size={13} />Itens recusados</h3>
          <ul className="office-keys">
            {invalidos.map((item) => (
              <li key={text(item.item)}><code>item {text(item.item)}</code><span>{text(item.motivo)}</span></li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h3><Table2 size={13} />Lotes</h3>
        <div className="office-steps">
          {lotes.map((lote) => (
            <article className="office-step" key={text(lote.numero)}>
              <header><strong>Lote {text(lote.numero)}</strong><Badge kind="info">{text(lote.itens)} item(ns)</Badge></header>
              <CopyLine value={text(lote.comando)} />
            </article>
          ))}
        </div>
      </section>
      {Boolean(result.verificacao) && (
        <div className="office-banner is-ok">
          <CheckCircle2 size={14} />
          <div><strong>Como verificar</strong><p>{text(result.verificacao)}</p></div>
        </div>
      )}
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function ScopesView({ result }: { result: Row }) {
  const exigidos = asRows(result.exigidos);
  const rows = asRows(result.rows);
  const metrics = asRow(result.metrics);
  const faltando = asList(result.faltando);
  const sobrando = asList(result.sobrando);
  return (
    <div className="office-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'OPERAÇÕES', value: num(metrics.operacoes) },
        { label: 'EXIGIDOS', value: num(metrics.exigidos) },
        { label: 'FALTANDO', value: num(metrics.faltando), tone: num(metrics.faltando) ? 'danger' : 'ok' },
        { label: 'SOBRANDO', value: num(metrics.sobrando), tone: num(metrics.sobrando) ? 'warning' : 'ok' },
      ]} />
      {Boolean(result.comando) && (
        <section>
          <h3><KeyRound size={13} />Reautenticar</h3>
          <CopyLine value={text(result.comando)} />
        </section>
      )}
      {(faltando.length > 0 || sobrando.length > 0) && (
        <section>
          <h3><Gauge size={13} />Diferença</h3>
          <div className="office-tag-row">
            {faltando.map((item) => <Badge kind="destrutivo" key={item}>falta {item}</Badge>)}
            {sobrando.map((item) => <Badge kind="escrita" key={item}>sobra {item}</Badge>)}
          </div>
        </section>
      )}
      <section>
        <h3><KeyRound size={13} />Escopos exigidos</h3>
        <ul className="office-keys">
          {exigidos.map((item) => (
            <li key={text(item.chave)}><code>{text(item.chave)}</code><span>{text(item.rotulo)} · {text(item.acesso)}</span></li>
          ))}
        </ul>
      </section>
      <section>
        <h3><Table2 size={13} />Operações</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>Operação</th><th>Risco</th><th>Escopos</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={text(row.operacao)}>
                  <td><code>{text(row.operacao)}</code></td>
                  <td>{text(row.risco)}</td>
                  <td>{text(row.escopos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function ErrorsView({ result }: { result: Row }) {
  const triagem = asRow(result.triagem);
  const repetir = Boolean(triagem.repetir);
  return (
    <div className="office-view">
      <div className={`office-verdict ${repetir ? 'is-warning' : 'is-danger'}`}>
        {repetir ? <RefreshCw size={15} /> : <AlertTriangle size={15} />}
        <div>
          <strong>{text(triagem.causa)}</strong>
          <p>{text(triagem.acao)}</p>
        </div>
      </div>
      <Metrics items={[
        { label: 'CÓDIGO', value: `${text(triagem.codigo)} · ${text(triagem.significado)}` },
        { label: 'STATUS', value: text(triagem.status) || '—' },
        { label: 'REASON', value: text(triagem.reason) || '—' },
        { label: 'GRUPO', value: errorGroupLabel[text(triagem.grupo)] ?? text(triagem.grupo) },
      ]} />
      <section>
        <h3><RefreshCw size={13} />Repetir</h3>
        <p className="office-note">
          {repetir
            ? `Sim, depois de ${text(triagem.espera)}s. Se o volume era grande, reduza a página antes de repetir.`
            : 'Não agora. Confira o efeito, o escopo ou o identificador antes de rodar de novo.'}
        </p>
        {Boolean(triagem.comando) && <CopyLine value={text(triagem.comando)} />}
      </section>
      {Boolean(triagem.mensagem) && (
        <section>
          <h3><Bug size={13} />Mensagem</h3>
          <div className="office-code"><pre>{text(triagem.mensagem)}</pre></div>
        </section>
      )}
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function ReferenceView({ reference }: { reference: Row | null }) {
  if (!reference) return <p className="office-empty"><LoaderCircle size={14} />Carregando…</p>;
  const services = asRows(reference.servicos);
  const flags = asRows(reference.flags);
  const codigos = asRows(reference.codigos);
  const escopos = asRows(reference.escopos);
  const receitas = asRows(reference.receitas);
  const lotes = asRows(reference.lotes);
  const erros = asRows(reference.erros);
  return (
    <div className="office-reference">
      <section>
        <h3><Briefcase size={13} />Serviços</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>Serviço</th><th>Rótulo</th><th>Ajudantes</th></tr></thead>
            <tbody>
              {services.map((item) => (
                <tr key={text(item.id)}>
                  <td><code>{text(item.id)}</code></td>
                  <td>{text(item.rotulo)}</td>
                  <td>{asList(item.ajudantes).join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="office-columns">
        <section>
          <h3><Terminal size={13} />Flags</h3>
          <ul className="office-keys">
            {flags.map((item) => (
              <li key={text(item.flag)}><code>{text(item.flag)}</code><span>{text(item.tipo)} · padrão {text(item.padrao)}</span></li>
            ))}
          </ul>
        </section>
        <section>
          <h3><Bug size={13} />Códigos de saída</h3>
          <ul className="office-keys">
            {codigos.map((item) => (
              <li key={text(item.codigo)}><code>{text(item.codigo)}</code><span>{text(item.significado)}</span></li>
            ))}
          </ul>
        </section>
      </div>
      <section>
        <h3><Wand2 size={13} />Receitas</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>Receita</th><th>Título</th><th>Passos</th></tr></thead>
            <tbody>
              {receitas.map((item) => (
                <tr key={text(item.id)}>
                  <td><code>{text(item.id)}</code></td>
                  <td>{text(item.titulo)}</td>
                  <td>{text(item.passos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><Layers size={13} />Lotes</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>Operação</th><th>Teto</th><th>Verificação</th></tr></thead>
            <tbody>
              {lotes.map((item) => (
                <tr key={text(item.operacao)}>
                  <td><code>{text(item.operacao)}</code></td>
                  <td>{text(item.limite)}</td>
                  <td>{text(item.verifica)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><KeyRound size={13} />Escopos</h3>
        <div className="office-columns">
          {escopos.map((item) => (
            <div className="office-ref-row" key={text(item.chave)}>
              <code>{text(item.chave)}</code><span>{text(item.acesso)}</span>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3><AlertTriangle size={13} />Erros</h3>
        <div className="office-table-wrap">
          <table className="office-table">
            <thead><tr><th>Reason</th><th>Grupo</th><th>Repetir</th></tr></thead>
            <tbody>
              {erros.map((item) => (
                <tr key={text(item.reason)}>
                  <td><code>{text(item.reason)}</code></td>
                  <td>{errorGroupLabel[text(item.grupo)] ?? text(item.grupo)}</td>
                  <td>{item.repetir ? 'sim' : 'não'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h3><Gauge size={13} />Limites</h3>
        {asRows(reference.limites).map((item) => (
          <div className="office-ref-row" key={text(item.regra)}>
            <code>{text(item.regra)}</code><span>{text(item.valor)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

export function EscritorioPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<OfficeTab>('comando');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);

  const [servico, setServico] = useState('drive');
  const [recurso, setRecurso] = useState('files');
  const [metodo, setMetodo] = useState('list');
  const [params, setParams] = useState(sampleParams);
  const [corpo, setCorpo] = useState('');
  const [argumentos, setArgumentos] = useState('');
  const [paginas, setPaginas] = useState(false);
  const [limitePaginas, setLimitePaginas] = useState(10);
  const [atrasoPagina, setAtrasoPagina] = useState(100);
  const [simular, setSimular] = useState(true);
  const [upload, setUpload] = useState('');
  const [sanitizar, setSanitizar] = useState('');

  const [receita, setReceita] = useState('subir-arquivo');
  const [entradas, setEntradas] = useState(sampleInputs);

  const [pages, setPages] = useState(samplePages);
  const [chaveItens, setChaveItens] = useState('');
  const [campoId, setCampoId] = useState('id');
  const [comandoBase, setComandoBase] = useState('gws drive files list');
  const [paramsBase, setParamsBase] = useState('{"q":"trashed = false"}');

  const [operacao, setOperacao] = useState('sheets.valores');
  const [itens, setItens] = useState(sampleItems);
  const [parametros, setParametros] = useState('{"valueInputOption":"USER_ENTERED"}');
  const [limite, setLimite] = useState(0);

  const [operacoes, setOperacoes] = useState(sampleOps);
  const [concedidos, setConcedidos] = useState(sampleGrants);

  const [codigo, setCodigo] = useState(1);
  const [mensagem, setMensagem] = useState(sampleError);
  const [tentativas, setTentativas] = useState(0);
  const [idempotente, setIdempotente] = useState(true);

  const result = execution?.ok ? asRow(execution.result) : null;
  const markdown = useMemo(() => text(result?.markdown), [result]);
  const recipes = useMemo(() => {
    const fromCatalog = asRows(reference?.receitas).map((item) => text(item.id));
    return fromCatalog.length ? fromCatalog : recipeFallback;
  }, [reference]);

  const loadReference = async () => {
    if (!backendOnline) return;
    try {
      const response = await executeSkill('escritorio.regras', {});
      if (response.ok) setReference(asRow(response.result));
    } catch {
      setReference(null);
    }
  };

  const openTab = (next: OfficeTab) => {
    setTab(next);
    setError('');
    setExecution(null);
    if ((next === 'regras' || next === 'receita') && !reference) void loadReference();
  };

  const run = async () => {
    if (!backendOnline) {
      setError('A API Python está offline. Suba a API com .venv\Scripts\python iniciar.py; nada foi calculado.');
      return;
    }
    const skill = `escritorio.${tab}`;
    const parameters: Record<string, unknown> = { modo: level };
    if (tab === 'comando') {
      Object.assign(parameters, {
        servico, recurso, metodo, params, corpo, argumentos, paginas,
        limite_paginas: limitePaginas, atraso_pagina: atrasoPagina, simular, upload, sanitizar,
      });
    }
    if (tab === 'receita') Object.assign(parameters, { receita, entradas, simular });
    if (tab === 'paginas') {
      Object.assign(parameters, {
        paginas: pages, chave_itens: chaveItens, campo_id: campoId,
        comando_base: comandoBase, params_base: paramsBase,
      });
    }
    if (tab === 'lote') Object.assign(parameters, { operacao, itens, parametros, limite, simular });
    if (tab === 'escopos') Object.assign(parameters, { operacoes, concedidos });
    if (tab === 'erros') Object.assign(parameters, { codigo, mensagem, tentativas, idempotente });
    setBusy(true);
    setError('');
    setExecution(null);
    try {
      const response = await executeSkill(skill, parameters);
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

  const copyReport = async () => {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      pushToast('Relatório copiado.', 'success');
    } catch {
      pushToast('Não foi possível copiar; selecione o texto do relatório.', 'error');
    }
  };

  const loadSample = () => {
    setServico('drive');
    setRecurso('files');
    setMetodo('list');
    setParams(sampleParams);
    setCorpo('');
    setArgumentos('');
    setPaginas(false);
    setLimitePaginas(10);
    setAtrasoPagina(100);
    setSimular(true);
    setUpload('');
    setSanitizar('');
    setReceita('subir-arquivo');
    setEntradas(sampleInputs);
    setPages(samplePages);
    setChaveItens('');
    setCampoId('id');
    setComandoBase('gws drive files list');
    setParamsBase('{"q":"trashed = false"}');
    setOperacao('sheets.valores');
    setItens(sampleItems);
    setParametros('{"valueInputOption":"USER_ENTERED"}');
    setLimite(0);
    setOperacoes(sampleOps);
    setConcedidos(sampleGrants);
    setCodigo(1);
    setMensagem(sampleError);
    setTentativas(0);
    setIdempotente(true);
  };

  const heading = tab === 'comando' ? 'Comando da descoberta'
    : tab === 'receita' ? 'Receita em passos'
      : tab === 'paginas' ? 'Leitura paginada'
        : tab === 'lote' ? 'Lotes de escrita'
          : tab === 'escopos' ? 'Escopos e consentimento'
            : tab === 'erros' ? 'Triagem de erro' : 'Catálogo do escritório';
  const description = tab === 'comando' ? 'Serviço, recurso e método viram um comando com params, corpo e ensaio.'
    : tab === 'receita' ? 'Uma receita do catálogo vira passos com ensaio, verificação e escopos.'
      : tab === 'paginas' ? 'Tokens, duplicatas e a próxima chamada — sem baixar nada.'
        : tab === 'lote' ? 'Cada item é validado e dividido no teto da operação.'
          : tab === 'escopos' ? 'Cada operação aponta o escopo mínimo; o que sobra é dívida de consentimento.'
            : tab === 'erros' ? 'Código, status e reason viram causa, ação e política de repetição.'
              : 'Serviços, flags, códigos, escopos, receitas, lotes e erros.';

  return (
    <div className="office-page">
      <section className="office-intro panel">
        <span className="office-intro-icon"><Briefcase size={20} /></span>
        <div>
          <span className="eyebrow">TRABALHO · GOOGLE WORKSPACE</span>
          <h2>Escritório</h2>
          <p>
            Monta o comando `gws`, planeja receitas, lê páginas, divide lotes, compara escopos e
            tria erros — a partir do texto que você cola. Nada é autenticado, enviado ou executado aqui.
          </p>
          <ul className="office-laws">
            {laws.map(([title, body]) => (
              <li key={title}><strong>{title}</strong><span>{body}</span></li>
            ))}
          </ul>
        </div>
      </section>

      <nav className="office-tabs">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => openTab(id)}>
            <Icon size={15} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="office-layout">
        <section className="office-form panel">
          <header className="office-form-head">
            <div>
              <span className="eyebrow">ENTRADA</span>
              <h2>{heading}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="office-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          <p className="office-level-note">{description}</p>

          {tab === 'regras' && (
            <div className="office-about">
              <p>O catálogo é lido da skill <code>escritorio.regras</code>. Ele descreve o vocabulário usado pelas outras seis: 18 serviços, 10 flags, 6 códigos de saída, 31 escopos e 15 receitas.</p>
              <p><b>Escopo:</b> o JARVIS não instala o CLI, não lê credenciais e não chama o Google. Ele prepara e audita o texto que você vai rodar.</p>
            </div>
          )}

          {tab === 'comando' && (
            <>
              <div className="office-inline">
                <label className="field">
                  <span>Serviço</span>
                  <select value={servico} onChange={(event) => setServico(event.target.value)}>
                    {servicos.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Método</span>
                  <input value={metodo} onChange={(event) => setMetodo(event.target.value)} spellCheck={false} placeholder="list, get, create, +send" />
                </label>
              </div>
              <label className="field">
                <span>Recurso <em>vazio em ajudantes</em></span>
                <input value={recurso} onChange={(event) => setRecurso(event.target.value)} spellCheck={false} placeholder="files, users.messages, spreadsheets.values" />
              </label>
              <label className="field">
                <span>Parâmetros <em>--params</em></span>
                <textarea className="office-mono" rows={5} value={params} onChange={(event) => setParams(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Corpo <em>--json</em></span>
                <textarea className="office-mono" rows={4} value={corpo} onChange={(event) => setCorpo(event.target.value)} spellCheck={false} placeholder='{"name":"relatorio.pdf"}' />
              </label>
              <label className="field">
                <span>Argumentos do ajudante</span>
                <input value={argumentos} onChange={(event) => setArgumentos(event.target.value)} spellCheck={false} placeholder="--to ana@exemplo.com --subject Oi" />
              </label>
              <div className="office-inline">
                <label className="field">
                  <span>Upload</span>
                  <input value={upload} onChange={(event) => setUpload(event.target.value)} spellCheck={false} placeholder="/caminho/arquivo.pdf" />
                </label>
                <label className="field">
                  <span>Sanitizar</span>
                  <input value={sanitizar} onChange={(event) => setSanitizar(event.target.value)} spellCheck={false} placeholder="projects/P/locations/L/templates/T" />
                </label>
              </div>
              <div className="office-inline">
                <label className="field">
                  <span>Limite de páginas</span>
                  <input type="number" min={1} max={5000} value={limitePaginas} onChange={(event) => setLimitePaginas(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Atraso (ms)</span>
                  <input type="number" min={0} max={60000} step={50} value={atrasoPagina} onChange={(event) => setAtrasoPagina(Number(event.target.value))} />
                </label>
              </div>
              <div className="office-inline">
                <label className="field">
                  <span>Paginar <em>--page-all</em></span>
                  <select value={paginas ? 'sim' : 'nao'} onChange={(event) => setPaginas(event.target.value === 'sim')}>
                    <option value="nao">não</option>
                    <option value="sim">sim</option>
                  </select>
                </label>
                <label className="field">
                  <span>Ensaiar <em>--dry-run</em></span>
                  <select value={simular ? 'sim' : 'nao'} onChange={(event) => setSimular(event.target.value === 'sim')}>
                    <option value="sim">sim</option>
                    <option value="nao">não</option>
                  </select>
                </label>
              </div>
            </>
          )}

          {tab === 'receita' && (
            <>
              <label className="field">
                <span>Receita</span>
                <select value={receita} onChange={(event) => setReceita(event.target.value)}>
                  {recipes.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Entradas <em>JSON</em></span>
                <textarea className="office-mono" rows={8} value={entradas} onChange={(event) => setEntradas(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Ensaiar escritas</span>
                <select value={simular ? 'sim' : 'nao'} onChange={(event) => setSimular(event.target.value === 'sim')}>
                  <option value="sim">sim</option>
                  <option value="nao">não</option>
                </select>
              </label>
            </>
          )}

          {tab === 'paginas' && (
            <>
              <label className="field">
                <span>Páginas <b>*</b> <em>JSON, NDJSON ou array</em></span>
                <textarea className="office-mono" rows={10} value={pages} onChange={(event) => setPages(event.target.value)} spellCheck={false} />
              </label>
              <div className="office-inline">
                <label className="field">
                  <span>Chave dos itens</span>
                  <input value={chaveItens} onChange={(event) => setChaveItens(event.target.value)} placeholder="detectar" spellCheck={false} />
                </label>
                <label className="field">
                  <span>Campo de ID</span>
                  <input value={campoId} onChange={(event) => setCampoId(event.target.value)} spellCheck={false} />
                </label>
              </div>
              <label className="field">
                <span>Comando base</span>
                <input value={comandoBase} onChange={(event) => setComandoBase(event.target.value)} spellCheck={false} placeholder="gws drive files list" />
              </label>
              <label className="field">
                <span>Parâmetros base</span>
                <textarea className="office-mono" rows={3} value={paramsBase} onChange={(event) => setParamsBase(event.target.value)} spellCheck={false} />
              </label>
            </>
          )}

          {tab === 'lote' && (
            <>
              <label className="field">
                <span>Operação</span>
                <select value={operacao} onChange={(event) => setOperacao(event.target.value)}>
                  {operacoesLote.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Itens <b>*</b> <em>array JSON</em></span>
                <textarea className="office-mono" rows={10} value={itens} onChange={(event) => setItens(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Parâmetros do envelope</span>
                <textarea className="office-mono" rows={3} value={parametros} onChange={(event) => setParametros(event.target.value)} spellCheck={false} />
              </label>
              <div className="office-inline">
                <label className="field">
                  <span>Itens por chamada <em>0 = teto</em></span>
                  <input type="number" min={0} max={1000} value={limite} onChange={(event) => setLimite(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Ensaiar</span>
                  <select value={simular ? 'sim' : 'nao'} onChange={(event) => setSimular(event.target.value === 'sim')}>
                    <option value="sim">sim</option>
                    <option value="nao">não</option>
                  </select>
                </label>
              </div>
            </>
          )}

          {tab === 'escopos' && (
            <>
              <label className="field">
                <span>Operações <b>*</b> <em>uma por linha</em></span>
                <textarea className="office-mono" rows={7} value={operacoes} onChange={(event) => setOperacoes(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Escopos concedidos</span>
                <textarea className="office-mono" rows={3} value={concedidos} onChange={(event) => setConcedidos(event.target.value)} spellCheck={false} placeholder="drive, gmail.modify, tasks" />
              </label>
            </>
          )}

          {tab === 'erros' && (
            <>
              <div className="office-inline">
                <label className="field">
                  <span>Código de saída</span>
                  <select value={codigo} onChange={(event) => setCodigo(Number(event.target.value))}>
                    {[0, 1, 2, 3, 4, 5].map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Tentativas</span>
                  <input type="number" min={0} max={10} value={tentativas} onChange={(event) => setTentativas(Number(event.target.value))} />
                </label>
              </div>
              <label className="field">
                <span>Mensagem de erro <b>*</b></span>
                <textarea className="office-mono" rows={8} value={mensagem} onChange={(event) => setMensagem(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Operação idempotente</span>
                <select value={idempotente ? 'sim' : 'nao'} onChange={(event) => setIdempotente(event.target.value === 'sim')}>
                  <option value="sim">sim — leitura ou escrita repetível</option>
                  <option value="nao">não — escrita que pode duplicar</option>
                </select>
              </label>
            </>
          )}

          {tab !== 'regras' && (
            <div className="office-form-actions">
              <button type="button" className="office-sample" onClick={loadSample}><Clipboard size={12} />Carregar exemplo</button>
              <button type="button" className="button-primary" onClick={() => void run()} disabled={busy || !backendOnline}>
                {busy ? <LoaderCircle size={13} className="spin" /> : <ArrowRight size={13} />}
                {busy ? 'Lendo…' : 'Executar'}
              </button>
            </div>
          )}
          {!backendOnline && <p className="office-note">A API Python está offline; nada será calculado até ela voltar.</p>}
          {error && <div className="office-error"><AlertTriangle size={14} /><span>{error}</span></div>}
        </section>

        <section className="office-result panel">
          <header className="office-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h2>{tab === 'regras' ? 'Catálogo do escritório' : result ? heading : 'Aguardando execução'}</h2>
            </div>
            <div className="office-result-actions">
              {markdown && <button type="button" className="office-ghost" onClick={() => void copyReport()}><Clipboard size={12} />Copiar</button>}
            </div>
          </header>

          {!result && tab !== 'regras' && (
            <div className="office-placeholder">
              <MousePointerClick size={22} />
              <strong>Cole o texto e rode a skill.</strong>
              <p>O resultado é determinístico: mesmas entradas, mesmos achados. Nada é autenticado nem enviado.</p>
              <button type="button" className="office-sample" onClick={() => void run()} disabled={!backendOnline || busy}><ArrowRight size={12} />Preencher com o exemplo</button>
            </div>
          )}

          {tab === 'regras' && <ReferenceView reference={reference} />}

          {result && tab === 'comando' && <CommandView result={result} />}
          {result && tab === 'receita' && <RecipeView result={result} />}
          {result && tab === 'paginas' && <PagesView result={result} />}
          {result && tab === 'lote' && <BatchView result={result} />}
          {result && tab === 'escopos' && <ScopesView result={result} />}
          {result && tab === 'erros' && <ErrorsView result={result} />}
          {result && <Report markdown={markdown} />}
        </section>
      </div>
    </div>
  );
}
