import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Briefcase,
  CheckCircle2,
  Clipboard,
  FileText,
  Filter,
  Gauge,
  LoaderCircle,
  MessageSquare,
  PenLine,
  ShieldCheck,
  Target,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../carreira.css';

type CareerTab = 'triagem' | 'ats' | 'bullets' | 'carta' | 'entrevista' | 'funil' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';

const tabs: Array<{ id: CareerTab; label: string; hint: string; icon: typeof Briefcase }> = [
  { id: 'triagem', label: 'Triagem', hint: 'Nota 1–5 com evidência', icon: Target },
  { id: 'ats', label: 'ATS', hint: 'Placar de 100 pontos', icon: ShieldCheck },
  { id: 'bullets', label: 'Bullets', hint: 'Conquista por conquista', icon: PenLine },
  { id: 'carta', label: 'Carta', hint: 'Rascunho com fonte', icon: FileText },
  { id: 'entrevista', label: 'Entrevista', hint: 'Requisito → pergunta', icon: MessageSquare },
  { id: 'funil', label: 'Funil', hint: 'Conversão e paradas', icon: Filter },
  { id: 'regras', label: 'Regras', hint: 'O vocabulário usado', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite' },
  { id: 'full', label: 'Full' },
  { id: 'ultra', label: 'Ultra' },
];

const laws = [
  ['Nota é triagem', 'Cinco dimensões com peso declarado e teto nomeado. Não é média, não é probabilidade de contratação.'],
  ['Evidência antes do número', 'Cada requisito tem banda e nível de evidência. Inferência nunca vira obrigatório; sem dado, a confiança cai.'],
  ['Sinal, não acusação', 'Legitimidade do anúncio é observação sobre o texto. Nenhum sinal muda a nota 1–5 sozinho.'],
  ['Você envia', 'O JARVIS lê o que você cola. Não abre portal, não manda candidatura e não altera seu currículo.'],
];

const sampleJob = `Vaga: Engenheira de Dados Sênior
Empresa: Acme Analytics
Local: Remoto (Brasil)
Modelo: remoto
Publicada: 2026-10-12

Sobre a empresa
Somos uma consultoria de dados com clientes em varejo e saúde. O time tem oito pessoas e atende três frentes.

Responsabilidades
- Construir e manter pipelines de dados em Python e Spark
- Modelar dados em dbt e BigQuery
- Revisar código do time e mentorar pessoas júnior

Requisitos
- Experiência obrigatória com Python, SQL e Airflow
- Conhecimento em dbt e BigQuery
- Inglês avançado para reuniões com clientes

Diferenciais
- Terraform e Kubernetes

Benefícios
- Plano de saúde
- Vale-refeição
- Orçamento para cursos

Remuneração: R$ 14.000 - R$ 18.000 por mês`;

const sampleProfile = `nome: Ana Souza
titulo: Engenheira de Dados
alvos:
  - Engenharia de Dados
  - Analytics Engineering
dominios:
  - varejo
salario_minimo: R$ 15.000
alvo_salarial: R$ 20.000
moeda: BRL
periodo: mes
idiomas:
  Inglês: avançado
notice_period_days: 30
regras:
  - Não aceito modelo presencial`;

const sampleCv = `# Ana Souza
ana@example.com

## Experiência
- Construí pipelines em Python e SQL que reduziram o atraso de dados de 6h para 40min
- Modelei 30 tabelas em dbt no BigQuery
- Orquestrei 120 DAGs no Airflow
- Liderei 3 pessoas e reduzi o retrabalho em 25%
- Responsável por relatórios semanais para a diretoria

## Formação
- Bacharelado em Estatística, UFSC, 2020

## Habilidades
Python, SQL, Airflow, dbt, BigQuery, Spark`;

const sampleStories = `## Migração do pipeline
Situação: o time perdia seis horas de dados por dia. Tarefa: reduzir o atraso.
Ação: reconstruí 120 DAGs no Airflow. Resultado: o atraso caiu para 40 minutos.

## Mentoria
Situação: três pessoas júnior no time. Tarefa: acelerar a entrega.
Ação: pairing semanal e revisão de código. Resultado: retrabalho caiu 25%.

## Sem número
Contexto: fiz uma apresentação para a diretoria.`;

const sampleApps = `| Data | Empresa | Cargo | Status | Nota |
| --- | --- | --- | --- | --- |
| 2026-08-01 | Acme | Engenheira de Dados | aplicada | 4,5 |
| 2026-08-03 | Beta | Analytics Engineer | respondeu | 4,2 |
| 2026-08-10 | Gama | Data Engineer | entrevista | 4,0 |
| 2026-09-01 | Delta | Engenheira de Dados | recusada | 3,8 |
| 2026-09-05 | Acme | Engenheira de Dados | aplicada | 4,5 |
| 2026-09-10 | Epsilon | Data Analyst | entrevista | 4,8 |
| 2026-10-01 | Zeta | Engenheira de Dados | oferta | 4,9 |
| 2026-10-10 | Eta | BI Engineer | aguardando | 4,1 |`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));
const fixed = (value: unknown, digits = 1): string => count(value).toFixed(digits).replace('.', ',');
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const evidenceLabel: Record<string, string> = { supported: 'sustentada', partial: 'parcial', unknown: 'sem dado' };
const bandLabel: Record<string, string> = { critical: 'Obrigatório', high: 'Central', meaningful: 'Relevante', preferred: 'Diferencial', low_signal: 'Genérico' };
const matchLabel: Record<string, string> = { forte: 'Forte', parcial: 'Parcial', ausente: 'Ausente', indefinido: 'Indefinido' };
const legitimacyLabel: Record<string, string> = { alta: 'Alta confiança', cautela: 'Cautela', suspeita: 'Suspeito' };

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warning' | 'danger' }) {
  return <article className={tone ? `is-${tone}` : undefined}><span>{label}</span><strong>{value}</strong></article>;
}

function Meter({ value, max = 5, tone }: { value: number; max?: number; tone?: string }) {
  const width = Math.max(0, Math.min(100, (value / max) * 100));
  return <span className={`career-meter ${tone ? `is-${tone}` : ''}`}><i style={{ width: `${width}%` }} /></span>;
}

function FindingList({ findings }: { findings: Row[] }) {
  if (!findings.length) return <p className="career-empty"><CheckCircle2 size={14} />Nada bloqueando pelas regras estáticas.</p>;
  return (
    <div className="career-findings">
      {findings.map((finding) => {
        const group = text(finding.group);
        return (
          <article className={`career-finding is-${group}`} key={`${text(finding.id)}-${text(finding.kind)}-${text(finding.location)}`}>
            <header>
              <span className="career-group">{groupLabel[group] ?? group}</span>
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
    <div className="career-limits">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Questions({ items }: { items: unknown }) {
  const rows = asList(items);
  if (!rows.length) return null;
  return (
    <div className="career-questions">
      <strong>PERGUNTAS ANTES DE SEGUIR</strong>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Report({ markdown }: { markdown: string }) {
  if (!markdown) return null;
  return (
    <details className="career-report">
      <summary><FileText size={13} />Relatório completo em markdown</summary>
      <pre>{markdown}</pre>
    </details>
  );
}

function TriageView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const dims = asRow(metrics.dimensoes);
  const caps = asRows(metrics.ajustes);
  const signals = asRows(metrics.sinais);
  const comp = asRow(metrics.comp);
  const company = asRow(metrics.empresaTipo);
  const blocked = Boolean(metrics.bloqueada);
  const note = count(metrics.nota);
  return (
    <div className="career-view">
      {blocked && (
        <div className="career-banner">
          <AlertTriangle size={15} />
          <div><strong>Parada por regra dura.</strong><p>O anúncio contradiz algo que você mesmo escreveu. A nota está limitada a 2,0 e nada foi enviado.</p></div>
        </div>
      )}
      <div className="career-score">
        <div>
          <span className="career-score-label">NOTA DE TRIAGEM</span>
          <strong className={`career-score-value ${note >= 4 ? 'is-ok' : note >= 3.5 ? 'is-warning' : 'is-danger'}`}>{fixed(note)}<small>/5</small></strong>
          <span className="career-score-band">{text(metrics.faixa)}</span>
        </div>
        <div className="career-scale">
          <div className="career-scale-track">
            {[1, 2, 3, 4, 5].map((tick) => <span key={tick} />)}
            <i style={{ left: `${Math.max(0, Math.min(100, ((note - 1) / 4) * 100))}%` }} />
          </div>
          <div className="career-scale-marks">
            <span style={{ left: '0%' }}>1</span>
            <span className="is-line" style={{ left: '62.5%' }}>3,5</span>
            <span className="is-line" style={{ left: '75%' }}>4,0</span>
            <span style={{ left: '100%' }}>5</span>
          </div>
          <p>Base ponderada {fixed(metrics.base)} · cobertura {fixed(metrics.cobertura, 0)}% · confiança {text(metrics.confianca)}</p>
        </div>
      </div>
      <div className="career-metrics">
        <Metric label="CONFIANÇA" value={text(metrics.confianca).toUpperCase()} tone={text(metrics.confianca) === 'alta' ? 'ok' : text(metrics.confianca) === 'baixa' ? 'danger' : 'warning'} />
        <Metric label="LEGITIMIDADE" value={`${legitimacyLabel[text(metrics.legitimidade)] ?? text(metrics.legitimidade)} · ${count(metrics.legitimidadeNota)}`} tone={text(metrics.legitimidade) === 'alta' ? 'ok' : text(metrics.legitimidade) === 'suspeita' ? 'danger' : 'warning'} />
        <Metric label="REMUNERAÇÃO" value={comp.declarada ? `${text(comp.moeda) || '—'} ${text(comp.piso)}–${text(comp.teto)} / ${text(comp.periodo)}` : 'não declarada'} />
        <Metric label="EMPRESA" value={text(company.rotulo)} />
      </div>
      <div className="career-dims">
        {Object.keys(dims).map((key) => {
          const dim = asRow(dims[key]);
          return (
            <article key={key}>
              <div><strong>{key === 'aderencia' ? 'Aderência' : key === 'alvo' ? 'Alvo' : key === 'comp' ? 'Remuneração' : key === 'cultura' ? 'Cultura' : 'Risco'}</strong><code>{evidenceLabel[text(dim.evidencia)] ?? text(dim.evidencia)}</code></div>
              <Meter value={count(dim.nota)} tone={count(dim.nota) >= 4 ? 'ok' : count(dim.nota) >= 3 ? 'warning' : 'danger'} />
              <p><span>{fixed(dim.nota)}</span> {text(dim.nota_txt)}</p>
            </article>
          );
        })}
      </div>
      {caps.length > 0 && (
        <div className="career-caps">
          <strong>TETOS APLICADOS</strong>
          {caps.map((cap) => (
            <p key={`${text(cap.regra)}-${text(cap.porque)}`}><b>{text(cap.regra)}</b> — {text(cap.porque)} <em>limite {fixed(cap.nota)}</em></p>
          ))}
        </div>
      )}
      <div className="career-table-wrap">
        <table className="career-table">
          <thead><tr><th>Banda</th><th>Requisito</th><th>Casamento</th><th>Prova</th></tr></thead>
          <tbody>
            {asRows(result.rows).map((row, index) => (
              <tr key={`${index}-${text(row.requisito)}`}>
                <td><span className={`career-chip is-${text(row.banda)}`}>{bandLabel[text(row.banda)] ?? text(row.banda)}</span></td>
                <td>{text(row.requisito)}</td>
                <td className={`is-${text(row.casamento)}`}>{matchLabel[text(row.casamento)] ?? text(row.casamento)}</td>
                <td className="career-dim">{text(row.prova) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="career-signals">
        <strong>LEGITIMIDADE DO ANÚNCIO</strong>
        {signals.map((signal) => (
          <article key={text(signal.codigo)} className={`is-${text(signal.estado)}`}>
            <span>{text(signal.estado) === 'bom' ? '✓' : text(signal.estado) === 'ruim' ? '✗' : '!'}</span>
            <div><strong>{text(signal.titulo)}</strong><p>{text(signal.leitura)}</p>{text(signal.evidencia) && <code>{text(signal.evidencia)}</code>}</div>
          </article>
        ))}
      </div>
      <FindingList findings={asRows(result.findings)} />
      <Questions items={result.questions} />
      <Limitations items={result.limitations} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function AtsView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const checks = asRows(metrics.checklist);
  const lints = asRows(metrics.lints);
  const words = asRow(metrics.palavras);
  return (
    <div className="career-view">
      <div className="career-score">
        <div>
          <span className="career-score-label">PONTOS MEDIDOS</span>
          <strong className="career-score-value">{count(metrics.score)}<small>/{count(metrics.escala)}</small></strong>
          <span className="career-score-band">nota {text(metrics.nota)}</span>
        </div>
        <div className="career-scale">
          <Meter value={count(metrics.score)} max={Math.max(1, count(metrics.escala))} tone={!metrics.html ? 'warning' : count(metrics.score) / Math.max(1, count(metrics.escala)) >= 0.8 ? 'ok' : count(metrics.score) / Math.max(1, count(metrics.escala)) >= 0.6 ? 'warning' : 'danger'} />
          <p>{metrics.html ? 'HTML inspecionado: as oito checagens têm peso fixo.' : 'Sem HTML, cinco checagens ficam não verificadas — a nota final é parcial.'}</p>
          <p>{count(metrics.bullets)} bullets · {count(metrics.metricasCv)} com número</p>
        </div>
      </div>
      <div className="career-checks">
        {checks.map((check) => (
          <article key={text(check.codigo)} className={`is-${text(check.status)}`}>
            <header><strong>{text(check.titulo)}</strong><span>{count(check.peso)} pts</span></header>
            <p>{text(check.evidencia)}</p>
            <code>{text(check.status)}</code>
          </article>
        ))}
      </div>
      <div className="career-keywords">
        <strong>PALAVRAS DA VAGA</strong>
        <p>Cobertura de {count(words.cobertura)}% · {text(words.nota)}</p>
        <div>
          {asList(words.presentes).map((word) => <span className="is-present" key={word}>{word}</span>)}
          {asList(words.ausentes).map((word) => <span className="is-missing" key={word}>{word}</span>)}
        </div>
      </div>
      {lints.length > 0 && (
        <div className="career-lints">
          <strong>LINTS DE PAYLOAD</strong>
          {lints.map((lint, index) => (
            <p key={`${index}-${text(lint.codigo)}`}><b>{text(lint.codigo)}</b> <code>linha {text(lint.linha) || 'texto'}</code> {text(lint.problema)} → {text(lint.ajuste)}</p>
          ))}
        </div>
      )}
      <FindingList findings={asRows(result.findings)} />
      <Limitations items={result.limitations} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function BulletsView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const items = asRows(metrics.auditoria);
  return (
    <div className="career-view">
      <div className="career-metrics">
        <Metric label="COM NÚMERO" value={`${count(metrics.comMetrica)}/${count(metrics.bullets)}`} tone={count(metrics.cobertura) >= 60 ? 'ok' : 'warning'} />
        <Metric label="COBERTURA" value={`${count(metrics.cobertura)}%`} />
        <Metric label="MÉDIA" value={`${count(metrics.mediaCaracteres)} car.`} />
        <Metric label="ABERTURAS REPETIDAS" value={Object.keys(asRow(metrics.aberturasRepetidas)).length} tone={Object.keys(asRow(metrics.aberturasRepetidas)).length ? 'warning' : 'ok'} />
      </div>
      <div className="career-bullets">
        {items.map((item) => {
          const problems = asRows(item.problemas);
          return (
            <article key={text(item.linha)}>
              <header>
                <code>linha {text(item.linha)}</code>
                <span className={count(item.pontuacao) >= 80 ? 'is-ok' : count(item.pontuacao) >= 50 ? 'is-warning' : 'is-danger'}>{count(item.pontuacao)}</span>
              </header>
              <p>{text(item.texto)}</p>
              <Meter value={count(item.pontuacao)} max={100} tone={count(item.pontuacao) >= 80 ? 'ok' : count(item.pontuacao) >= 50 ? 'warning' : 'danger'} />
              {problems.length > 0 && <ul>{problems.map((problem) => <li key={text(problem.codigo)}><b>{text(problem.codigo)}</b> {text(problem.problema)} <em>{text(problem.ajuste)}</em></li>)}</ul>}
              <footer><span>modelo: {text(item.modelo)}</span><span>{text(item.pergunta)}</span></footer>
            </article>
          );
        })}
      </div>
      <FindingList findings={asRows(result.findings)} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function LetterView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const checks = asRows(metrics.checagens);
  const missing = asList(metrics.faltando);
  const achievements = asRows(metrics.conquistas);
  const gap = asRow(metrics.lacuna);
  return (
    <div className="career-view">
      <div className="career-metrics">
        <Metric label="STATUS" value={metrics.pronto ? 'pronta para revisão' : 'faltam insumos'} tone={metrics.pronto ? 'ok' : 'danger'} />
        <Metric label="CARACTERES" value={count(metrics.caracteres)} tone={count(metrics.caracteres) >= 600 && count(metrics.caracteres) <= 1600 ? 'ok' : 'warning'} />
        <Metric label="CHECAGENS" value={`${checks.filter((check) => check.ok).length}/${checks.length}`} />
        <Metric label="CONQUISTAS" value={achievements.length} />
      </div>
      {missing.length > 0 && <Questions items={missing} />}
      {text(metrics.rascunho) && (
        <div className="career-letter">
          <strong>RASCUNHO</strong>
          <div>{asList(metrics.paragrafos).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
          <small>Nada foi enviado. Revise em voz alta antes de gerar PDF.</small>
        </div>
      )}
      {checks.length > 0 && (
        <div className="career-checks is-compact">
          {checks.map((check) => (
            <article key={text(check.codigo)} className={check.ok ? 'is-ok' : 'is-falha'}>
              <header><strong>{text(check.codigo)}</strong><span>{check.ok ? '✓' : '✗'}</span></header>
              <p>{text(check.evidencia)}</p>
            </article>
          ))}
        </div>
      )}
      {achievements.length > 0 && (
        <div className="career-sources">
          <strong>FONTES USADAS</strong>
          {achievements.map((item) => <p key={text(item.linha)}><code>linha {text(item.linha)}</code> {text(item.texto)}</p>)}
        </div>
      )}
      {text(gap.requisito) && <p className="career-note">Lacuna assumida: <b>{text(gap.requisito)}</b> — {text(gap.plano)}</p>}
      <FindingList findings={asRows(result.findings)} />
      <Questions items={result.questions} />
      <Limitations items={result.limitations} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function InterviewView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const plan = asRows(metrics.plano);
  const signals = asRows(metrics.sinais);
  const blocks = asRows(metrics.blocos);
  return (
    <div className="career-view">
      <div className="career-metrics">
        <Metric label="REQUISITOS" value={plan.length} />
        <Metric label="HISTÓRIAS" value={asRows(metrics.historias).length} tone={asRows(metrics.historias).length ? 'ok' : 'danger'} />
        <Metric label="HISTÓRIAS COMPLETAS" value={`${count(metrics.confirmados)}/${asRows(metrics.historias).length}`} />
        <Metric label="SINAIS A ESCLARECER" value={signals.length} />
      </div>
      <div className="career-plan">
        {plan.map((item) => (
          <article key={text(item.ordem)}>
            <header>
              <span className="career-order">{text(item.ordem)}</span>
              <div><strong>{text(item.requisito)}</strong><small>{text(item.banda_rotulo)} · {matchLabel[text(item.casamento)] ?? text(item.casamento)}{text(item.historia) ? ` · história: ${text(item.historia)}` : ''}</small></div>
            </header>
            <ul>{asList(item.perguntas).map((question) => <li key={question}>{question}</li>)}</ul>
            <p className="career-note"><b>Prova:</b> {text(item.prova) || 'sem linha no currículo'}</p>
            <p className="career-note"><b>Risco:</b> {text(item.risco)}</p>
          </article>
        ))}
      </div>
      <div className="career-ask">
        <strong>PERGUNTAS PARA A EMPRESA</strong>
        <ul>{asList(metrics.perguntasEmpresa).map((question) => <li key={question}>{question}</li>)}</ul>
      </div>
      {signals.length > 0 && (
        <div className="career-signals">
          <strong>SINAIS A ESCLARECER</strong>
          {signals.map((signal) => <article key={text(signal.sinal)} className="is-atencao"><span>!</span><div><strong>{text(signal.sinal)}</strong><p>{text(signal.pergunta)}</p></div></article>)}
        </div>
      )}
      <div className="career-blocks">
        {blocks.map((block) => <article key={text(block.bloco)}><span>{text(block.tempo)}</span><strong>{text(block.bloco)}</strong><p>{text(block.tarefa)}</p></article>)}
      </div>
      <FindingList findings={asRows(result.findings)} />
      <Limitations items={result.limitations} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function FunnelView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  const status = asRow(metrics.porStatus);
  const rates = asRow(metrics.taxas);
  const months = asRow(metrics.meses);
  const total = Math.max(1, count(metrics.total));
  return (
    <div className="career-view">
      <div className="career-metrics">
        <Metric label="CANDIDATURAS" value={count(metrics.total)} />
        <Metric label="ATIVAS" value={count(metrics.ativas)} />
        <Metric label="PARADAS 14+ DIAS" value={count(metrics.paradas)} tone={count(metrics.paradas) ? 'warning' : 'ok'} />
        <Metric label="STATUS ILEGÍVEL" value={count(metrics.semStatus)} tone={count(metrics.semStatus) ? 'danger' : 'ok'} />
      </div>
      <div className="career-rates">
        {[['resposta', 'Resposta'], ['entrevista', 'Entrevista'], ['oferta', 'Oferta']].map(([key, label]) => {
          const rate = asRow(rates[key]);
          return (
            <article key={key}>
              <span>{label}</span>
              <strong>{rate.valor === null ? '—' : `${fixed(rate.valor)}%`}</strong>
              <small>{count(rate.numerador)}/{count(rate.denominador)}</small>
            </article>
          );
        })}
      </div>
      <div className="career-status">
        {Object.keys(status).map((key) => (
          <div key={key}>
            <span>{key}</span>
            <Meter value={count(status[key])} max={total} />
            <b>{count(status[key])}</b>
          </div>
        ))}
      </div>
      <div className="career-table-wrap">
        <table className="career-table">
          <thead><tr><th>Mês</th><th>Candidaturas</th><th>Entrevistas</th><th>Ofertas</th></tr></thead>
          <tbody>
            {Object.keys(months).sort().reverse().map((month) => {
              const row = asRow(months[month]);
              return <tr key={month}><td>{month}</td><td>{count(row.total)}</td><td>{count(row.entrevista)}</td><td>{count(row.oferta)}</td></tr>;
            })}
          </tbody>
        </table>
      </div>
      <div className="career-table-wrap">
        <table className="career-table">
          <thead><tr><th>Data</th><th>Empresa</th><th>Cargo</th><th>Status</th><th>Nota</th></tr></thead>
          <tbody>
            {asRows(result.rows).map((row, index) => (
              <tr key={`${index}-${text(row.empresa)}`}><td>{text(row.data)}</td><td>{text(row.empresa)}</td><td>{text(row.cargo)}</td><td>{text(row.status)}</td><td>{text(row.nota)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <FindingList findings={asRows(result.findings)} />
      <Limitations items={result.limitations} />
      <Report markdown={text(result.markdown)} />
    </div>
  );
}

function ReferenceView({ reference }: { reference: Row | null }) {
  if (!reference) return <p className="career-empty"><LoaderCircle size={14} />Carregue o catálogo com a API ligada.</p>;
  return (
    <div className="career-view">
      <div className="career-ref-grid">
        <section>
          <strong>BANDAS DE IMPORTÂNCIA</strong>
          {asRows(reference.bandas).map((band) => <p key={text(band.chave)}><code>{text(band.chave)}</code> <b>{text(band.rotulo)}</b> <span>peso {text(band.peso)}</span></p>)}
        </section>
        <section>
          <strong>DIMENSÕES DA NOTA</strong>
          {asRows(reference.dimensoes).map((dim) => <p key={text(dim.chave)}><b>{text(dim.rotulo)}</b> <span>{fixed(count(dim.peso) * 100, 0)}%</span><em>{text(dim.leitura)}</em></p>)}
        </section>
        <section>
          <strong>NÍVEIS DE EVIDÊNCIA</strong>
          {asRows(reference.evidencia).map((item) => <p key={text(item.chave)}><b>{text(item.rotulo)}</b><em>{text(item.leitura)}</em></p>)}
        </section>
        <section>
          <strong>FAIXAS DA NOTA</strong>
          {asRows(reference.faixasNota).map((band) => <p key={text(band.minimo)}><b>{count(band.minimo) === 0 ? '< 3,5' : `≥ ${fixed(band.minimo)}`}</b> <span>{text(band.acao)}</span><em>{text(band.leitura)}</em></p>)}
        </section>
        <section>
          <strong>ESTADOS DO FUNIL</strong>
          {asRows(reference.estados).map((state) => <p key={text(state.chave)}><code>{text(state.chave)}</code> <b>{text(state.rotulo)}</b>{state.ativa ? <span>ativa</span> : null}<em>{text(state.leitura)}</em></p>)}
        </section>
        <section>
          <strong>PESOS DO ATS</strong>
          {asRows(reference.ats).map((check) => <p key={text(check.chave)}><b>{text(check.titulo)}</b> <span>{count(check.peso)} pts</span><em>{text(check.regra)}</em></p>)}
        </section>
        <section>
          <strong>EMPRESA × CONFIABILIDADE</strong>
          {asRows(reference.tiposEmpresa).map((item) => <p key={text(item.chave)}><b>{text(item.rotulo)}</b> <span>{text(item.confiabilidade)}</span></p>)}
        </section>
        <section>
          <strong>SINAIS DE LEGITIMIDADE</strong>
          {asRows(reference.sinais).map((signal) => <p key={text(signal.codigo)}><b>{text(signal.titulo)}</b> <span>{text(signal.nivel)}</span><em>{text(signal.pergunta)}</em></p>)}
        </section>
      </div>
      <div className="career-chips">
        <strong>CLICHÊS QUE A CARTA NÃO PODE USAR</strong>
        <div>{asList(reference.cliches).map((item) => <span key={item}>{item}</span>)}</div>
      </div>
      <div className="career-chips is-good">
        <strong>VERBOS FORTES PARA BULLETS</strong>
        <div>{asList(reference.verbosFortes).map((item) => <span key={item}>{item}</span>)}</div>
      </div>
      <div className="career-rules">
        <strong>REGRAS DO MÓDULO</strong>
        <ul>{asList(reference.regras).map((rule) => <li key={rule}>{rule}</li>)}</ul>
      </div>
    </div>
  );
}

export function CareerPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<CareerTab>('triagem');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [reference, setReference] = useState<Row | null>(null);
  const [job, setJob] = useState(sampleJob);
  const [profile, setProfile] = useState(sampleProfile);
  const [cv, setCv] = useState(sampleCv);
  const [html, setHtml] = useState('');
  const [research, setResearch] = useState('A Acme atende varejo e saúde com times pequenos de dados.');
  const [reason, setReason] = useState('Quero trabalhar perto do cliente e do problema real de varejo.');
  const [stories, setStories] = useState(sampleStories);
  const [apps, setApps] = useState(sampleApps);
  const [windowDays, setWindowDays] = useState(90);
  const [force, setForce] = useState(false);

  const result = execution?.ok ? asRow(execution.result) : null;
  const markdown = useMemo(() => text(result?.markdown), [result]);

  const loadReference = async () => {
    if (!backendOnline) return;
    try {
      const response = await executeSkill('carreira.regras', {});
      if (response.ok) setReference(asRow(response.result));
    } catch {
      setReference(null);
    }
  };

  const openTab = (next: CareerTab) => {
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
    const skill = `carreira.${tab === 'bullets' ? 'bullets' : tab}`;
    const parameters: Record<string, unknown> = { modo: level };
    if (tab === 'triagem') Object.assign(parameters, { vaga: job, perfil: profile, curriculo: cv, forcar: force });
    if (tab === 'ats') Object.assign(parameters, { curriculo: cv, vaga: job, html });
    if (tab === 'bullets') Object.assign(parameters, { curriculo: cv });
    if (tab === 'carta') Object.assign(parameters, { vaga: job, curriculo: cv, perfil: profile, pesquisa: research, porque: reason });
    if (tab === 'entrevista') Object.assign(parameters, { vaga: job, curriculo: cv, perfil: profile, historias: stories });
    if (tab === 'funil') Object.assign(parameters, { aplicacoes: apps, janela: windowDays });
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
    setJob(sampleJob);
    setProfile(sampleProfile);
    setCv(sampleCv);
    setStories(sampleStories);
    setApps(sampleApps);
    setHtml('');
    setResearch('A Acme atende varejo e saúde com times pequenos de dados.');
    setReason('Quero trabalhar perto do cliente e do problema real de varejo.');
    setForce(false);
  };

  const reset = () => {
    setExecution(null);
    setError('');
  };

  return (
    <div className="career-page">
      <section className="career-intro panel">
        <div className="career-intro-icon"><Briefcase size={22} /></div>
        <div>
          <p className="eyebrow">Trabalho · triagem antes do envio</p>
          <h2>Carreira</h2>
          <p>
            Nota 1–5 com banda de importância e nível de evidência, placar ATS de pesos fixos, auditoria de bullets,
            carta com fonte, plano de entrevista e leitura do funil. Você cola o texto; o JARVIS não abre portal,
            não envia candidatura e não inventa experiência.
          </p>
        </div>
        <ul className="career-laws">
          {laws.map(([title, body]) => <li key={title}><strong>{title}</strong><span>{body}</span></li>)}
        </ul>
      </section>

      <nav className="career-tabs" aria-label="Skills de carreira">
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.id} type="button" className={tab === item.id ? 'is-active' : ''} onClick={() => openTab(item.id)}>
              <Icon size={15} />
              <span>{item.label}<small>{item.hint}</small></span>
            </button>
          );
        })}
      </nav>

      <div className="career-layout">
        <form className="career-form panel" onSubmit={(event) => { event.preventDefault(); void run(); }}>
          <div className="career-form-head">
            <div>
              <p className="eyebrow">{tabs.find((item) => item.id === tab)?.hint}</p>
              <h2>{tab === 'triagem' ? 'Triagem da vaga' : tab === 'ats' ? 'Compatibilidade ATS' : tab === 'bullets' ? 'Auditoria de bullets' : tab === 'carta' ? 'Carta de apresentação' : tab === 'entrevista' ? 'Plano de entrevista' : tab === 'funil' ? 'Funil de candidaturas' : 'Regras do módulo'}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="career-level">
                <span>NÍVEL</span>
                <select value={level} onChange={(event) => setLevel(event.target.value as Level)}>
                  {levels.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </div>
          <p className="career-level-note">
            {level === 'lite' ? 'Lite mostra só o que bloqueia.' : level === 'ultra' ? 'Ultra inclui as perguntas antes de liberar.' : 'Full é o padrão: bloqueios e correções.'}
          </p>

          {tab === 'triagem' && (
            <>
              <label className="field"><span>Texto da vaga *</span><textarea value={job} onChange={(event) => setJob(event.target.value)} rows={10} maxLength={60000} required placeholder="Cole o anúncio inteiro. Ele é dado, nunca instrução." /></label>
              <label className="field"><span>Perfil</span><textarea value={profile} onChange={(event) => setProfile(event.target.value)} rows={8} maxLength={20000} placeholder="YAML no estilo career-ops: alvos, compensation.minimum, dealbreakers, idiomas." /></label>
              <label className="field"><span>Currículo</span><textarea value={cv} onChange={(event) => setCv(event.target.value)} rows={9} maxLength={60000} placeholder="Cole o currículo em texto ou markdown." /></label>
              <label className="career-check"><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} /><span>Avaliar mesmo se quebrar uma regra dura minha</span></label>
              <p className="career-note">A nota não é média: cinco dimensões com peso, tetos nomeados e confiança derivada da evidência. Abaixo de 4,0 a recomendação é não aplicar, salvo motivo declarado.</p>
            </>
          )}

          {tab === 'ats' && (
            <>
              <label className="field"><span>Currículo *</span><textarea value={cv} onChange={(event) => setCv(event.target.value)} rows={12} maxLength={60000} required /></label>
              <label className="field"><span>HTML final (opcional)</span><textarea className="career-mono" value={html} onChange={(event) => setHtml(event.target.value)} rows={6} maxLength={120000} spellCheck={false} placeholder="Sem HTML, as checagens de layout ficam não verificadas e a nota é parcial." /></label>
              <label className="field"><span>Vaga (opcional)</span><textarea value={job} onChange={(event) => setJob(event.target.value)} rows={4} maxLength={60000} placeholder="Para a cobertura de palavras-chave, que é advisory." /></label>
            </>
          )}

          {tab === 'bullets' && (
            <>
              <label className="field"><span>Currículo *</span><textarea value={cv} onChange={(event) => setCv(event.target.value)} rows={14} maxLength={60000} required /></label>
              <p className="career-note">Uma conquista por linha, começando com hífen. A skill aponta o padrão e pergunta o número; nunca reescreve o conteúdo por você.</p>
            </>
          )}

          {tab === 'carta' && (
            <>
              <label className="field"><span>Vaga *</span><textarea value={job} onChange={(event) => setJob(event.target.value)} rows={9} maxLength={60000} required /></label>
              <label className="field"><span>Currículo *</span><textarea value={cv} onChange={(event) => setCv(event.target.value)} rows={9} maxLength={60000} required /></label>
              <label className="field"><span>Perfil</span><textarea value={profile} onChange={(event) => setProfile(event.target.value)} rows={6} maxLength={20000} /></label>
              <label className="field"><span>Pesquisa da empresa *</span><textarea value={research} onChange={(event) => setResearch(event.target.value)} rows={3} maxLength={4000} placeholder="Um fato concreto sobre o que a empresa faz e por que isso conversa com você." /></label>
              <label className="field"><span>Por que essa empresa</span><input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={600} /></label>
              <p className="career-note">Sem pesquisa e sem conquista com número, a skill para antes do rascunho. Carta genérica não é entregue.</p>
            </>
          )}

          {tab === 'entrevista' && (
            <>
              <label className="field"><span>Vaga *</span><textarea value={job} onChange={(event) => setJob(event.target.value)} rows={9} maxLength={60000} required /></label>
              <label className="field"><span>Currículo</span><textarea value={cv} onChange={(event) => setCv(event.target.value)} rows={7} maxLength={60000} /></label>
              <label className="field"><span>Banco de histórias</span><textarea value={stories} onChange={(event) => setStories(event.target.value)} rows={9} maxLength={40000} placeholder="## Título · Situação · Tarefa · Ação · Resultado" /></label>
              <label className="field"><span>Perfil</span><textarea value={profile} onChange={(event) => setProfile(event.target.value)} rows={5} maxLength={20000} /></label>
            </>
          )}

          {tab === 'funil' && (
            <>
              <label className="field"><span>Candidaturas *</span><textarea className="career-mono" value={apps} onChange={(event) => setApps(event.target.value)} rows={14} maxLength={60000} required /></label>
              <label className="field"><span>Janela em dias</span><input type="number" min={0} max={3650} value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value))} /></label>
              <p className="career-note">Aceita tabela markdown, TSV ou CSV com Data | Empresa | Cargo | Status | Nota. Status fora da lista vira achado, não é descartado em silêncio.</p>
            </>
          )}

          {tab === 'regras' && (
            <div className="career-about">
              <p>Este painel lê o catálogo de vocabulário usado pelas seis skills: bandas, dimensões, evidência, faixas, estados, pesos do ATS, tipos de empresa, sinais e listas de escrita.</p>
              <p>Nenhum dado sai da máquina. Nenhum arquivo do seu computador é alterado.</p>
            </div>
          )}

          {error && <div className="career-error"><AlertTriangle size={15} /><span>{error}</span></div>}

          <div className="career-form-actions">
            {tab === 'regras' ? (
              <button type="button" className="button" onClick={() => void loadReference()}><BookOpen size={14} />Carregar catálogo</button>
            ) : (
              <button type="button" className="career-sample" onClick={loadSample}><Clipboard size={14} />Carregar exemplo</button>
            )}
            {tab !== 'regras' && (
              <button type="submit" className="button button-primary" disabled={busy || !backendOnline}>
                {busy ? <LoaderCircle size={15} className="is-spinning" /> : <Gauge size={15} />}
                {busy ? 'Calculando…' : 'Executar'}
              </button>
            )}
          </div>
        </form>

        <section className="career-result panel">
          <div className="career-result-head">
            <div>
              <p className="eyebrow">Resultado</p>
              <h2>{result ? text(result.analysis) : tab === 'regras' ? 'Catálogo de regras' : 'Aguardando execução'}</h2>
            </div>
            <div className="career-result-actions">
              {markdown && <button type="button" className="career-ghost" onClick={() => void copyReport()}><Clipboard size={13} />Copiar</button>}
              {result && <button type="button" className="career-ghost" onClick={reset}>Limpar</button>}
            </div>
          </div>

          {!result && !busy && tab !== 'regras' && (
            <div className="career-placeholder">
              <Target size={26} />
              <strong>Cole o texto e rode a skill.</strong>
              <p>O resultado é determinístico: mesmas entradas, mesma saída. Nada é lido de portais nem de arquivos seus.</p>
              <button type="button" className="career-sample" onClick={loadSample}><ArrowRight size={14} />Preencher com o exemplo</button>
            </div>
          )}
          {busy && <div className="career-placeholder"><LoaderCircle size={24} className="is-spinning" /><strong>Lendo o que foi colado…</strong></div>}
          {result && tab === 'triagem' && <TriageView result={result} />}
          {result && tab === 'ats' && <AtsView result={result} />}
          {result && tab === 'bullets' && <BulletsView result={result} />}
          {result && tab === 'carta' && <LetterView result={result} />}
          {result && tab === 'entrevista' && <InterviewView result={result} />}
          {result && tab === 'funil' && <FunnelView result={result} />}
          {tab === 'regras' && <ReferenceView reference={reference} />}
        </section>
      </div>
    </div>
  );
}
