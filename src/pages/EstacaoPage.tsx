import { useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  Clipboard,
  FileText,
  Gauge,
  KeyRound,
  ListChecks,
  LoaderCircle,
  MousePointerClick,
  Receipt,
  RefreshCw,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../estacao.css';

type EstacaoTab = 'tarefa' | 'permissoes' | 'recibos' | 'agenda' | 'limites' | 'memoria' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: EstacaoTab; label: string; hint: string; icon: typeof ListChecks }> = [
  { id: 'tarefa', label: 'Tarefa', hint: 'Objetivo → passos', icon: ListChecks },
  { id: 'permissoes', label: 'Permissões', hint: 'allow / ask / deny', icon: ShieldCheck },
  { id: 'recibos', label: 'Execução', hint: 'Chamada → recibo', icon: Receipt },
  { id: 'agenda', label: 'Agenda', hint: 'Cron → disparos', icon: CalendarClock },
  { id: 'limites', label: 'Limites', hint: 'Ação → consentimento', icon: Ban },
  { id: 'memoria', label: 'Memória', hint: 'Notas e skills', icon: FileText },
  { id: 'regras', label: 'Regras', hint: 'O vocabulário', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite' },
  { id: 'full', label: 'Full' },
  { id: 'ultra', label: 'Ultra' },
];

const laws = [
  ['Permissão declarada', 'Nenhuma ferramenta é oferecida sem uma permissão que a pessoa escreveu. Nome desconhecido é `deny`.'],
  ['Aprovação que vale uma vez', '`ask` para a rodada, guarda os argumentos e executa uma única vez. A decisão fica registrada.'],
  ['Chamada no máximo uma vez', 'Uma queda no meio deixa o resultado desconhecido. O agente relê o estado antes de repetir.'],
  ['Limite não se contorna', 'Evasão de detecção, CAPTCHA, rotação de conta e desrespeito a termos ficam fora do que este núcleo prepara.'],
];

const samplePolitica = `computer.exec=ask
files.read=allow
files.write=ask
browser.read=allow
browser.act=ask
automations=ask`;
const sampleFerramentas = 'read_file, write_file, browser_navigate, browser_click';
const sampleRecibos = `id=c1 tool=read_file status=ok result=extrato-lido
id=c2 tool=write_file status=interrompido
id=c2 tool=write_file status=ok result=gravado verificado=sim
id=c3 tool=browser_click status=erro result=timeout`;
const sampleAgenda = `relatorio-semanal | 0 9 * * 1-5 | 30 | sim
registrar-ponto | 55 8 * * 1-5 | 5 | nao
limpeza-mensal | 0 3 1 * * | 40 | nao`;
const sampleAcoes = `ler o extrato do banco
responder a mensagem da cliente
resolver o captcha do login
apagar os comprovantes antigos`;
const sampleNotas = `Ana prefere relatórios em PDF (2026-10-20).
A conta do cartão fecha dia 25 (2026-09-30).
Sempre mandar cópia para o financeiro.`;
const sampleSkills = `nome: fechar-planilha
gatilho: quando pedirem o fechamento do mês
passos: abrir a planilha; conferir totais; salvar PDF
verificacao: o PDF existe e os totais batem
permissoes: files.read, files.write
---
nome: cobranca-semanal
gatilho: quando pedirem a cobrança da semana
passos: listar faturas em aberto; montar lista de devedores
verificacao: toda fatura tem estado`;
const memoryHygiene = [
  'Todo fato carrega o dia em que foi aprendido.',
  'Segredo fica no cofre do host; a nota cita só o nome da variável.',
  'Skill sem gatilho não é lembrada; skill sem verificação não prova nada.',
  'Nota que deixou de valer é corrigida ou apagada, nunca empilhada.',
];

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const num = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const decisionLabel: Record<string, string> = { allow: 'allow', ask: 'ask', deny: 'deny' };
const riskLabel: Record<string, string> = { baixo: 'baixo', 'médio': 'médio', alto: 'alto' };
const levelLabel: Record<string, string> = { liberado: 'liberado', confirmar: 'confirmar', bloqueado: 'bloqueado' };

function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`estacao-badge is-${kind}`}>{children}</span>;
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="estacao-empty"><CheckCircle2 size={14} />Nada bloqueando pelas regras estáticas.</p>;
  return (
    <div className="estacao-findings">
      {findings.map((item) => {
        const group = text(item.group);
        return (
          <article className={`estacao-finding is-${group}`} key={`${text(item.id)}-${text(item.kind)}-${text(item.location)}`}>
            <header>
              <span className="estacao-group">{groupLabel[group] ?? group}</span>
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
  const counts = asRow(result.counts);
  const danger = num(counts.must) > 0;
  const warning = !danger && num(counts.should) > 0;
  const tone = danger ? 'is-danger' : warning ? 'is-warning' : 'is-ok';
  return (
    <div className={`estacao-verdict ${tone}`}>
      {danger ? <AlertTriangle size={15} /> : warning ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
      <div>
        <strong>{text(result.verdict)}</strong>
        <p>{danger
          ? 'Há item obrigatório: resolva antes de deixar o agente agir.'
          : warning
            ? 'Nada obrigatório, mas há ajuste recomendado antes de liberar.'
            : 'O plano está coerente com as regras estáticas.'}</p>
      </div>
    </div>
  );
}

function Metrics({ items }: { items: Array<{ label: string; value: ReactNode; tone?: 'ok' | 'warning' | 'danger' }> }) {
  return <div className="estacao-metrics">{items.map((item) => <Metric key={item.label} {...item} />)}</div>;
}

function Limitations({ items }: { items: unknown }) {
  const list = asList(items);
  if (!list.length) return null;
  return (
    <div className="estacao-limits">
      <strong>NÃO VERIFICADO</strong>
      <ul>{list.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Report({ markdown }: { markdown: string }) {
  if (!markdown) return null;
  return (
    <details className="estacao-report">
      <summary><Clipboard size={12} />Relatório em Markdown</summary>
      <pre>{markdown}</pre>
    </details>
  );
}

function TaskView({ result }: { result: Row }) {
  const passos = asRows(result.passos);
  const metrics = asRow(result.metrics);
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'PASSOS', value: num(metrics.passos) },
        { label: 'FERRAMENTAS', value: num(metrics.ferramentas) },
        { label: 'COM APROVAÇÃO', value: num(metrics.aprovacoes), tone: num(metrics.aprovacoes) ? 'warning' : 'ok' },
        { label: 'ORÇAMENTO', value: `${num(metrics.passos_max)} passos` },
      ]} />
      <div className="estacao-callout">
        <strong>Objetivo observável</strong>
        <p>{text(result.objetivo)}</p>
      </div>
      <section>
        <h3><ListChecks size={13} />Passos</h3>
        <div className="estacao-steps">
          {passos.map((passo) => (
            <article className="estacao-step" key={text(passo.ordem)}>
              <header>
                <strong>{text(passo.ordem)}. {text(passo.acao)}</strong>
                <Badge kind={text(passo.tipo)}>{text(passo.tipo)}</Badge>
                {Boolean(passo.aprovacao) && <Badge kind="ask">aprovação</Badge>}
                <em>{text(passo.ferramenta)}</em>
              </header>
              <dl>
                <div><dt>Permissão</dt><dd><code>{text(passo.permissao)}</code></dd></div>
                <div><dt>Deu certo se</dt><dd>{text(passo.prova)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h3><Ban size={13} />Parada</h3>
        <div className="estacao-chip-row">
          {asList(result.parada).map((item) => <span key={item}>{item}</span>)}
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

function PermissionsView({ result }: { result: Row }) {
  const matriz = asRows(result.matriz);
  const metrics = asRow(result.metrics);
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'ALLOW', value: num(metrics.allow), tone: 'ok' },
        { label: 'ASK', value: num(metrics.ask), tone: 'warning' },
        { label: 'DENY', value: num(metrics.deny), tone: 'danger' },
        { label: 'RISCO ALTO LIVRE', value: num(metrics.risco_alto_livre), tone: num(metrics.risco_alto_livre) ? 'danger' : 'ok' },
      ]} />
      <section>
        <h3><ShieldCheck size={13} />Matriz</h3>
        <div className="estacao-matrix">
          {matriz.map((linha) => (
            <article className={`estacao-perm is-${text(linha.decisao)}`} key={text(linha.permissao)}>
              <header>
                <code>{text(linha.permissao)}</code>
                <Badge kind={text(linha.decisao)}>{decisionLabel[text(linha.decisao)] ?? text(linha.decisao)}</Badge>
              </header>
              <small>{text(linha.rotulo)} · risco {riskLabel[text(linha.risco)] ?? text(linha.risco)} · padrão {text(linha.padrao)}</small>
            </article>
          ))}
        </div>
      </section>
      <div className="estacao-callout">
        <strong>O que `ask` faz</strong>
        <p>Para a rodada, guarda a chamada com os argumentos e espera a pessoa. A decisão vale uma vez e não sobrevive como carta branca.</p>
      </div>
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function ReceiptsView({ result }: { result: Row }) {
  const linhas = asRows(result.recibos);
  const interrompidas = asList(result.interrompidas);
  const metrics = asRow(result.metrics);
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'LINHAS', value: num(metrics.linhas) },
        { label: 'CHAMADAS', value: num(metrics.chamadas) },
        { label: 'INTERROMPIDAS', value: num(metrics.interrompidas), tone: num(metrics.interrompidas) ? 'danger' : 'ok' },
        { label: 'ERROS', value: num(metrics.erros), tone: num(metrics.erros) ? 'warning' : 'ok' },
      ]} />
      {interrompidas.length > 0 && (
        <div className="estacao-callout is-block">
          <strong>Não repita sem ler</strong>
          <p>Estas chamadas podem ter sido aplicadas e podem ainda estar rodando: {interrompidas.join(', ')}. Leia o estado atual antes de chamar de novo.</p>
        </div>
      )}
      <section>
        <h3><Receipt size={13} />Recibos</h3>
        <div className="estacao-table-wrap">
          <table className="estacao-table">
            <thead><tr><th>#</th><th>Chamada</th><th>Ferramenta</th><th>Status</th><th>Aprovação</th><th>Conferido</th></tr></thead>
            <tbody>
              {linhas.map((linha) => (
                <tr key={`${text(linha.ordem)}-${text(linha.chamada)}`}>
                  <td>{text(linha.ordem)}</td>
                  <td><code>{text(linha.chamada)}</code></td>
                  <td>{text(linha.ferramenta) || '—'}</td>
                  <td><Badge kind={text(linha.status)}>{text(linha.status)}</Badge></td>
                  <td>{text(linha.aprovacao) || '—'}</td>
                  <td>{linha.verificado ? 'sim' : 'não'}</td>
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

function AgendaView({ result }: { result: Row }) {
  const agenda = asRows(result.agenda);
  const conflitos = asRows(result.conflitos);
  const metrics = asRow(result.metrics);
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'AUTOMAÇÕES', value: num(metrics.automacoes) },
        { label: 'DISPAROS / SEMANA', value: num(metrics.disparos_semana) },
        { label: 'CHOQUES', value: num(metrics.conflitos), tone: num(metrics.conflitos) ? 'danger' : 'ok' },
        { label: 'COM PRESENÇA', value: num(metrics.com_presenca) },
      ]} />
      <section>
        <h3><CalendarClock size={13} />Agenda</h3>
        <div className="estacao-table-wrap">
          <table className="estacao-table">
            <thead><tr><th>Nome</th><th>Cron</th><th>Minutos</th><th>Presença</th><th>Disparos</th></tr></thead>
            <tbody>
              {agenda.map((linha) => (
                <tr key={text(linha.nome)}>
                  <td>{text(linha.nome)}</td>
                  <td className="is-mono">{text(linha.cron)}</td>
                  <td>{text(linha.duracao)}</td>
                  <td>{linha.presenca ? 'sim' : 'não'}</td>
                  <td>{text(linha.disparos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {conflitos.length > 0 && (
        <section>
          <h3><AlertTriangle size={13} />Choques de horário</h3>
          <div className="estacao-chip-row">
            {conflitos.map((item) => (
              <span key={`${text(item.dia)}-${text(item.minuto)}-${text(item.a)}`}>
                {text(item.dia)} · {String(Math.floor(num(item.minuto) / 60)).padStart(2, '0')}:{String(num(item.minuto) % 60).padStart(2, '0')}
                <code>{text(item.a)} × {text(item.b)}</code>
              </span>
            ))}
          </div>
        </section>
      )}
      <div className="estacao-callout">
        <strong>Atraso e queda</strong>
        <p>Automação perdida enquanto a máquina dormia roda uma vez no próximo acordar. Três falhas seguidas param a automação e avisam.</p>
      </div>
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function LimitsView({ result }: { result: Row }) {
  const acoes = asRows(result.acoes);
  const metrics = asRow(result.metrics);
  const bloqueadas = acoes.filter((item) => text(item.nivel) === 'bloqueado');
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'LIBERADAS', value: num(metrics.liberadas), tone: 'ok' },
        { label: 'CONFIRMAR', value: num(metrics.confirmar), tone: 'warning' },
        { label: 'BLOQUEADAS', value: num(metrics.bloqueadas), tone: num(metrics.bloqueadas) ? 'danger' : 'ok' },
        { label: 'AÇÕES', value: num(metrics.acoes) },
      ]} />
      <section>
        <h3><Ban size={13} />Uma por uma</h3>
        <div className="estacao-steps">
          {acoes.map((item) => (
            <article className="estacao-step" key={`${text(item.acao)}-${text(item.regra)}`}>
              <header>
                <strong>{text(item.acao)}</strong>
                <Badge kind={text(item.nivel)}>{levelLabel[text(item.nivel)] ?? text(item.nivel)}</Badge>
                {Boolean(item.regra) && <em>{text(item.regra)}</em>}
              </header>
              <dl>
                <div><dt>Por quê</dt><dd>{text(item.motivo)}</dd></div>
                <div><dt>Alternativa</dt><dd>{text(item.alternativa)}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>
      {bloqueadas.length > 0 && (
        <div className="estacao-callout is-block">
          <strong>O que fica de fora</strong>
          <p>O upstream se anuncia como indetectável por anti-bots. Este núcleo não adapta essa parte: esconder automação, vencer CAPTCHA, rotacionar contas e ignorar termos continuam bloqueados, com a via oficial indicada em cada linha.</p>
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

function MemoryView({ result }: { result: Row }) {
  const skills = asRows(result.skills);
  const metrics = asRow(result.metrics);
  return (
    <div className="estacao-view">
      <Verdict result={result} />
      <Metrics items={[
        { label: 'CARACTERES', value: num(metrics.notas) },
        { label: 'LINHAS DE NOTA', value: num(metrics.linhas) },
        { label: 'SKILLS', value: num(metrics.skills) },
        { label: 'SEGREDOS', value: num(metrics.segredos), tone: num(metrics.segredos) ? 'danger' : 'ok' },
      ]} />
      <section>
        <h3><FileText size={13} />Skills do agente</h3>
        {skills.length ? (
          <div className="estacao-table-wrap">
            <table className="estacao-table">
              <thead><tr><th>Nome</th><th>Gatilho</th><th>Passos</th><th>Verificação</th></tr></thead>
              <tbody>
                {skills.map((linha) => (
                  <tr key={text(linha.nome)}>
                    <td><code>{text(linha.nome)}</code></td>
                    <td>{text(linha.gatilho)}</td>
                    <td>{text(linha.passos)}</td>
                    <td>{text(linha.verificacao)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="estacao-empty"><FileText size={14} />Nenhuma skill declarada.</p>}
      </section>
      <section>
        <h3><KeyRound size={13} />Higiene</h3>
        <div className="estacao-chip-row">{memoryHygiene.map((item) => <span key={item}>{item}</span>)}</div>
      </section>
      <section>
        <h3><Gauge size={13} />Achados</h3>
        <FindingList findings={asRows(result.findings)} />
      </section>
      <Limitations items={result.limitations} />
    </div>
  );
}

function ReferenceView({ reference }: { reference: Row | null }) {
  if (!reference) {
    return <div className="estacao-placeholder"><LoaderCircle size={22} className="is-spinning" /><strong>Lendo o catálogo…</strong><p>A biblioteca vem da skill `estacao.regras`.</p></div>;
  }
  const ferramentas = asRows(reference.ferramentas);
  const permissoes = asRows(reference.permissoes);
  const estados = asRows(reference.estados);
  const evasao = asRows(reference.evasao);
  const limites = asRows(reference.limites);
  const orcamento = asRows(reference.orcamento);
  return (
    <div className="estacao-reference">
      <div className="estacao-callout">
        <strong>{text(reference.fonte)} · v{text(reference.versao)}</strong>
        <p>{text(reference.principio)}</p>
      </div>
      <section>
        <h3><Terminal size={13} />Ferramentas ({ferramentas.length})</h3>
        <div className="estacao-chip-row">
          {ferramentas.map((item) => (
            <span key={text(item.id)}><code>{text(item.id)}</code> {text(item.permissao)} · {text(item.risco)}</span>
          ))}
        </div>
      </section>
      <section>
        <h3><ShieldCheck size={13} />Permissões ({permissoes.length})</h3>
        <div className="estacao-matrix">
          {permissoes.map((item) => (
            <article className={`estacao-perm is-${text(item.padrao)}`} key={text(item.nome)}>
              <header><code>{text(item.nome)}</code><Badge kind={text(item.padrao)}>{text(item.padrao)}</Badge></header>
              <small>{text(item.rotulo)} · risco {riskLabel[text(item.risco)] ?? text(item.risco)}</small>
            </article>
          ))}
        </div>
      </section>
      <div className="estacao-columns">
        <section>
          <h3><RefreshCw size={13} />Estados</h3>
          {estados.map((item) => (
            <div className="estacao-ref-row" key={text(item.estado)}><code>{text(item.estado)}</code><span>{text(item.nota)}</span></div>
          ))}
        </section>
        <section>
          <h3><Gauge size={13} />Orçamento</h3>
          {orcamento.map((item) => (
            <div className="estacao-ref-row" key={text(item.regra)}><code>{text(item.regra)}</code><span>{text(item.valor)}</span></div>
          ))}
          {limites.map((item) => (
            <div className="estacao-ref-row" key={text(item.regra)}><code>{text(item.regra)}</code><span>{text(item.nivel)} · {text(item.porque)}</span></div>
          ))}
        </section>
      </div>
      <section>
        <h3><Ban size={13} />Evasão — fora do escopo ({evasao.length})</h3>
        {evasao.map((item) => (
          <div className="estacao-rule" key={text(item.regra)}>
            <code>{text(item.titulo)}</code>
            <span>{text(item.porque)} <b>Alternativa:</b> {text(item.alternativa)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

export function EstacaoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<EstacaoTab>('tarefa');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);

  const [objetivo, setObjetivo] = useState('baixar o comprovante do mês e salvar em ~/docs');
  const [ferramentas, setFerramentas] = useState(sampleFerramentas);
  const [politica, setPolitica] = useState(samplePolitica);
  const [passosMax, setPassosMax] = useState(60);
  const [orcamento, setOrcamento] = useState(1);

  const [politicaPerm, setPoliticaPerm] = useState(samplePolitica);
  const [ferramentasPerm, setFerramentasPerm] = useState('read_file, write_file');
  const [servidores, setServidores] = useState('planilhas');
  const [limitePassos, setLimitePassos] = useState(60);
  const [limiteCusto, setLimiteCusto] = useState(1);
  const [ocio, setOcio] = useState(15);

  const [log, setLog] = useState(sampleRecibos);

  const [automacoes, setAutomacoes] = useState(sampleAgenda);
  const [acordadas, setAcordadas] = useState(8);
  const [presenca, setPresenca] = useState('9-18');

  const [acoes, setAcoes] = useState(sampleAcoes);

  const [notas, setNotas] = useState(sampleNotas);
  const [skills, setSkills] = useState(sampleSkills);

  const result = execution?.ok ? asRow(execution.result) : null;
  const markdown = useMemo(() => text(result?.markdown), [result]);

  const loadReference = async () => {
    if (!backendOnline) return;
    try {
      const response = await executeSkill('estacao.regras', {});
      if (response.ok) setReference(asRow(response.result));
    } catch {
      setReference(null);
    }
  };

  const openTab = (next: EstacaoTab) => {
    setTab(next);
    setError('');
    setExecution(null);
    if (next === 'regras' && !reference) void loadReference();
  };

  const run = async () => {
    if (!backendOnline) {
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi calculado.');
      return;
    }
    const skill = `estacao.${tab}`;
    const parameters: Record<string, unknown> = { modo: level };
    if (tab === 'tarefa') Object.assign(parameters, { objetivo, ferramentas, politica, passos_max: passosMax, orcamento });
    if (tab === 'permissoes') Object.assign(parameters, {
      politica: politicaPerm, ferramentas: ferramentasPerm, servidores_mcp: servidores,
      limite_passos: limitePassos, limite_custo: limiteCusto, ocio_minutos: ocio,
    });
    if (tab === 'recibos') Object.assign(parameters, { log });
    if (tab === 'agenda') Object.assign(parameters, { automacoes, orcamento_diario: acordadas, presenca });
    if (tab === 'limites') Object.assign(parameters, { acoes });
    if (tab === 'memoria') Object.assign(parameters, { notas, skills });
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
    setObjetivo('baixar o comprovante do mês e salvar em ~/docs');
    setFerramentas(sampleFerramentas);
    setPolitica(samplePolitica);
    setPassosMax(60);
    setOrcamento(1);
    setPoliticaPerm(samplePolitica);
    setFerramentasPerm('read_file, write_file');
    setServidores('planilhas');
    setLimitePassos(60);
    setLimiteCusto(1);
    setOcio(15);
    setLog(sampleRecibos);
    setAutomacoes(sampleAgenda);
    setAcordadas(8);
    setPresenca('9-18');
    setAcoes(sampleAcoes);
    setNotas(sampleNotas);
    setSkills(sampleSkills);
  };

  const heading = tab === 'tarefa' ? 'Plano da tarefa'
    : tab === 'permissoes' ? 'Matriz de permissões'
      : tab === 'recibos' ? 'Execução e recuperação'
        : tab === 'agenda' ? 'Agenda de automações'
          : tab === 'limites' ? 'Limites e consentimento'
            : tab === 'memoria' ? 'Notas e skills' : 'Catálogo da estação';
  const description = tab === 'tarefa' ? 'O objetivo vira passos com ferramenta, permissão e prova; a parada é a prova, não o recibo.'
    : tab === 'permissoes' ? 'Cada permissão recebe allow, ask ou deny; risco alto liberado sem revisão é bloqueio.'
      : tab === 'recibos' ? 'Chamada sem resultado, execução dupla, aprovação reaproveitada e retomada sem conferir.'
        : tab === 'agenda' ? 'Cron, sobreposição, presença e orçamento de acordadas por dia.'
          : tab === 'limites' ? 'O que é leitura, o que precisa de confirmação e o que este núcleo não prepara.'
            : tab === 'memoria' ? 'Segredo em nota, fato sem dia, skill sem gatilho ou sem verificação.'
              : 'Ferramentas, permissões, estados, evasão e orçamentos do vocabulário.';

  return (
    <div className="estacao-page">
      <section className="estacao-intro panel">
        <span className="estacao-intro-icon"><ShieldCheck size={20} /></span>
        <div>
          <span className="eyebrow">AGENTE · COMPUTADOR PRÓPRIO</span>
          <h2>Estação</h2>
          <p>
            Permissões, aprovação, recuperação depois de queda, agenda e memória de um agente que
            trabalha num computador próprio. O contrato é texto: nada é instalado, autenticado ou executado aqui.
          </p>
          <ul className="estacao-laws">
            {laws.map(([title, body]) => (
              <li key={title}><strong>{title}</strong><span>{body}</span></li>
            ))}
          </ul>
        </div>
      </section>

      <nav className="estacao-tabs">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => openTab(id)}>
            <Icon size={15} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="estacao-layout">
        <section className="estacao-form panel">
          <header className="estacao-form-head">
            <div>
              <span className="eyebrow">ENTRADA</span>
              <h2>{heading}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="estacao-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>
          <p className="estacao-level-note">{description}</p>

          {tab === 'regras' && (
            <div className="estacao-about">
              <p>O catálogo vem da skill <code>estacao.regras</code>: 30 ferramentas, 14 permissões, 6 estados e 8 regras de evasão.</p>
              <p><b>Escopo:</b> inspirado em <code>feder-cr/invisible_dots</code> (MIT). Sem VM, sem QEMU, sem navegador e sem rede — só o contrato de governança.</p>
            </div>
          )}

          {tab === 'tarefa' && (
            <>
              <label className="field">
                <span>Objetivo <em>observável</em></span>
                <textarea rows={3} value={objetivo} onChange={(event) => setObjetivo(event.target.value)} />
              </label>
              <label className="field">
                <span>Ferramentas oferecidas</span>
                <input value={ferramentas} onChange={(event) => setFerramentas(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Política <em>uma por linha</em></span>
                <textarea className="estacao-mono" rows={6} value={politica} onChange={(event) => setPolitica(event.target.value)} spellCheck={false} />
              </label>
              <div className="estacao-inline">
                <label className="field">
                  <span>Passos máximos</span>
                  <input type="number" min={3} max={500} value={passosMax} onChange={(event) => setPassosMax(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Custo máximo (US$)</span>
                  <input type="number" min={0.01} max={100} step={0.5} value={orcamento} onChange={(event) => setOrcamento(Number(event.target.value))} />
                </label>
              </div>
            </>
          )}

          {tab === 'permissoes' && (
            <>
              <label className="field">
                <span>Política</span>
                <textarea className="estacao-mono" rows={7} value={politicaPerm} onChange={(event) => setPoliticaPerm(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Ferramentas em uso</span>
                <input value={ferramentasPerm} onChange={(event) => setFerramentasPerm(event.target.value)} spellCheck={false} />
              </label>
              <label className="field">
                <span>Servidores MCP <em>separados por vírgula</em></span>
                <input value={servidores} onChange={(event) => setServidores(event.target.value)} spellCheck={false} placeholder="planilhas, busca" />
              </label>
              <div className="estacao-inline">
                <label className="field">
                  <span>Passos máximos</span>
                  <input type="number" min={1} max={500} value={limitePassos} onChange={(event) => setLimitePassos(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Custo por tarefa</span>
                  <input type="number" min={0.01} max={100} step={0.5} value={limiteCusto} onChange={(event) => setLimiteCusto(Number(event.target.value))} />
                </label>
              </div>
              <label className="field">
                <span>Ócio até dormir <em>minutos</em></span>
                <input type="number" min={0} max={1440} value={ocio} onChange={(event) => setOcio(Number(event.target.value))} />
              </label>
            </>
          )}

          {tab === 'recibos' && (
            <label className="field">
              <span>Recibos <em>id=… tool=… status=…</em></span>
              <textarea className="estacao-mono" rows={10} value={log} onChange={(event) => setLog(event.target.value)} spellCheck={false} />
            </label>
          )}

          {tab === 'agenda' && (
            <>
              <label className="field">
                <span>Automações <em>nome | cron | minutos | presença</em></span>
                <textarea className="estacao-mono" rows={8} value={automacoes} onChange={(event) => setAutomacoes(event.target.value)} spellCheck={false} />
              </label>
              <div className="estacao-inline">
                <label className="field">
                  <span>Acordadas por dia</span>
                  <input type="number" min={1} max={96} value={acordadas} onChange={(event) => setAcordadas(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Janela de presença</span>
                  <input value={presenca} onChange={(event) => setPresenca(event.target.value)} placeholder="9-18" />
                </label>
              </div>
            </>
          )}

          {tab === 'limites' && (
            <label className="field">
              <span>Ações pretendidas <em>uma por linha</em></span>
              <textarea rows={9} value={acoes} onChange={(event) => setAcoes(event.target.value)} />
            </label>
          )}

          {tab === 'memoria' && (
            <>
              <label className="field">
                <span>Notas do agente <em>MEMORY.md</em></span>
                <textarea rows={7} value={notas} onChange={(event) => setNotas(event.target.value)} />
              </label>
              <label className="field">
                <span>Skills <em>blocos separados por ---</em></span>
                <textarea className="estacao-mono" rows={9} value={skills} onChange={(event) => setSkills(event.target.value)} spellCheck={false} />
              </label>
            </>
          )}

          <div className="estacao-form-actions">
            {tab !== 'regras' && (
              <>
                <button type="button" className="estacao-sample" onClick={loadSample}><RefreshCw size={11} />Preencher com o exemplo</button>
                <button type="button" className="button-primary" onClick={() => void run()} disabled={!backendOnline || busy}>
                  {busy ? <LoaderCircle size={13} className="is-spinning" /> : <ArrowRight size={13} />}
                  {busy ? 'Calculando…' : 'Executar'}
                </button>
              </>
            )}
            {tab === 'regras' && (
              <button type="button" className="estacao-sample" onClick={() => void loadReference()}><RefreshCw size={11} />Recarregar catálogo</button>
            )}
          </div>

          {error && <div className="estacao-error"><AlertTriangle size={13} /><span>{error}</span></div>}
        </section>

        <section className="estacao-result panel">
          <header className="estacao-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h2>{tab === 'regras' ? 'Catálogo da estação' : result ? heading : 'Aguardando execução'}</h2>
            </div>
            <div className="estacao-result-actions">
              {markdown && <button type="button" className="estacao-ghost" onClick={() => void copyReport()}><Clipboard size={12} />Copiar</button>}
            </div>
          </header>

          {!result && tab !== 'regras' && (
            <div className="estacao-placeholder">
              <MousePointerClick size={22} />
              <strong>Preencha e rode a skill.</strong>
              <p>O resultado é determinístico: mesmas entradas, mesmos achados. Nada é executado de verdade.</p>
              <button type="button" className="estacao-sample" onClick={() => void run()} disabled={!backendOnline || busy}><ArrowRight size={12} />Rodar o exemplo</button>
            </div>
          )}

          {tab === 'regras' && <ReferenceView reference={reference} />}
          {result && tab === 'tarefa' && <TaskView result={result} />}
          {result && tab === 'permissoes' && <PermissionsView result={result} />}
          {result && tab === 'recibos' && <ReceiptsView result={result} />}
          {result && tab === 'agenda' && <AgendaView result={result} />}
          {result && tab === 'limites' && <LimitsView result={result} />}
          {result && tab === 'memoria' && <MemoryView result={result} />}
          {result && <Report markdown={markdown} />}
        </section>
      </div>
    </div>
  );
}
