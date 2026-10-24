import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  Dna,
  FileSearch,
  FlaskConical,
  FolderGit2,
  LoaderCircle,
  Microscope,
  Sigma,
  TestTubes,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../ciencia.css';

type CienciaTab = 'amostra' | 'estatistica' | 'desenho' | 'reprodutibilidade' | 'validacao' | 'manuscrito' | 'regras';
type Row = Record<string, unknown>;
type Level = 'lite' | 'full' | 'ultra';
type Teste = 'proporcoes' | 'medias';
type TipoDesenho = 'ensaio' | 'observacional' | 'diagnostico' | 'animal';
type TipoModalidade = 'cromatografico' | 'lba';
type TipoEstudo = 'ensaio' | 'observacional' | 'diagnostico' | 'revisao' | 'animal';

const tabs: Array<{ id: CienciaTab; label: string; hint: string; icon: typeof Sigma }> = [
  { id: 'amostra', label: 'Amostra', hint: 'Poder e n', icon: Sigma },
  { id: 'estatistica', label: 'Estatística', hint: 'O que o relato mostra', icon: ClipboardList },
  { id: 'desenho', label: 'Desenho', hint: 'O que decide validade', icon: FlaskConical },
  { id: 'reprodutibilidade', label: 'Reprodutibilidade', hint: 'Dado, código e ambiente', icon: FolderGit2 },
  { id: 'validacao', label: 'Validação', hint: 'Método analítico', icon: TestTubes },
  { id: 'manuscrito', label: 'Manuscrito', hint: 'Seções e diretriz', icon: FileSearch },
  { id: 'regras', label: 'Regras', hint: 'Critérios e fórmulas', icon: BookOpen },
];

const levels: Array<{ id: Level; label: string }> = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const tiposDesenho: Array<{ id: TipoDesenho; label: string }> = [
  { id: 'ensaio', label: 'Ensaio clínico' },
  { id: 'observacional', label: 'Observacional' },
  { id: 'diagnostico', label: 'Acurácia diagnóstica' },
  { id: 'animal', label: 'Estudo animal' },
];

const tiposEstudo: Array<{ id: TipoEstudo; label: string }> = [
  { id: 'ensaio', label: 'Ensaio — CONSORT 2025' },
  { id: 'observacional', label: 'Observacional — STROBE' },
  { id: 'diagnostico', label: 'Diagnóstico — STARD' },
  { id: 'revisao', label: 'Revisão — PRISMA 2020' },
  { id: 'animal', label: 'Animal — ARRIVE 2.0' },
];

const modalidades: Array<{ id: TipoModalidade; label: string }> = [
  { id: 'cromatografico', label: 'Cromatográfico — ICH M10' },
  { id: 'lba', label: 'Ligante (LBA) — ICH M10' },
];

const RESULTADOS = `Houve diferença significativa entre os grupos (t = 3,82; p < 0,05), com média de 75,2 e desvio de 8,5 no grupo A. A correlação entre dose e resposta foi forte. Não houve diferença entre B e C, portanto os tratamentos são equivalentes. O intervalo foi IC 95% [1,18; 2,42] e n = 48.`;

const METODOS = `Ensaio randomizado com alocação oculta em envelopes opacos. A randomização foi feita em blocos de quatro por sorteio. O cegamento foi duplo: participante, quem aplicou e quem mediu não sabiam o grupo. Havia grupo controle concorrente com placebo. A unidade experimental foi cada paciente. O desfecho primário foi dor aos 30 dias. O tamanho amostral foi calculado com poder de 80%, alfa 0,05 e efeito de 0,5. O protocolo foi pré-registrado no ClinicalTrials.gov (NCT01234567). Critérios de inclusão: adultos; exclusão: gestantes. Perdidos: 2 por desistência. A análise primária foi pré-especificada.`;

const REPRO = `Os dados estão disponíveis no Zenodo (doi 10.5281/zenodo.1234567) e o código em https://github.com/exemplo/analise, commit 4f2a1c. As versões foram Python 3.11.4, numpy 2.1.0 e statsmodels 0.14.2. A semente foi fixada em 42. O ambiente está em Docker (imagem exemplo/analise:1.0). O protocolo foi pré-registrado no OSF. Os dados brutos têm accession GSE123456. Licença CC BY 4.0.`;

const DADOS = `1,9.8,10,1
1,10.2,10,1
1,10.0,10,2
1,10.1,10,2
1,9.9,10,2
10,49.0,50,1
10,51.0,50,1
10,50.0,50,2
10,49.5,50,2
10,50.5,50,2`;

const CURVA = `0,0.02
5,5.1
10,10.1
20,19.9
40,40.2`;

const MANUSCRITO = `Resumo
Ensaio randomizado, duplo-cego, com 80 participantes.

Introdução
O tratamento é tema de interesse clínico.

Métodos
Randomização por sorteio em blocos, alocação oculta em envelopes, cegamento duplo, grupo controle com placebo, fluxo de participantes: 88 triados, 80 alocados. Desfecho primário: dor aos 30 dias. Tamanho amostral calculado com poder de 80%.

Resultados
A diferença foi significativa (t(78) = 3,1; p = 0,003), d = 0,7, IC 95% [0,2; 1,2], n = 80.

Discussão
O achado é compatível com a literatura e limitações incluem seguimento curto.

Conclusão
O tratamento é promissor.

Financiamento
FAPESP 2024/12345-6.

Conflito de interesse
Nenhum declarado.

Ética
Aprovado pelo CEP 1234, com consentimento livre e esclarecido.

Disponibilidade de dados
Dados no Zenodo (doi 10.5281/zenodo.1).

Contribuições
Concepção e desenho por A; análise por B.

Referências
1. Silva et al., 2024.`;

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));

const fmt = (value: unknown, casas = 2): string => {
  const numero = Number(value);
  if (!Number.isFinite(numero)) return '—';
  return numero.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
};
const groupLabel: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };
const pesoLabel: Record<string, string> = { must: 'exigido', should: 'esperado', nice: 'desejável' };

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
    <div className="ciencia-table-block">
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

function AmostraView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="n POR GRUPO" value={`${fmt(metrics.n1, 0)} · ${fmt(metrics.n2, 0)}`} />
        <Metric label="TOTAL ANALISADO" value={fmt(metrics.total, 0)} />
        <Metric label="PODER" value={`${fmt(count(metrics.poder_calculado) * 100)}%`} tone={count(metrics.poder_calculado) < 0.8 ? 'danger' : 'ok'} />
        <Metric label="A RECRUTAR" value={fmt(metrics.matricula, 0)} tone={count(metrics.matricula) > count(metrics.total) ? 'warning' : 'ok'} />
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

function EstatisticaView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="p CITADOS" value={count(metrics.p_citados)} />
        <Metric label="EFEITO" value={count(metrics.com_efeito) ? 'presente' : 'ausente'} tone={count(metrics.com_efeito) ? 'ok' : 'warning'} />
        <Metric label="INTERVALO" value={count(metrics.com_intervalo) ? 'presente' : 'ausente'} tone={count(metrics.com_intervalo) ? 'ok' : 'warning'} />
        <Metric label="n" value={count(metrics.n_declarado) || '—'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Números citados" colunas={['Tipo', 'Valor', 'Situação', 'Evidência']}>
        {asRows(result.rows).map((row, indice) => (
          <tr key={`${text(row.tipo)}-${indice}`}>
            <td><strong>{text(row.tipo)}</strong></td>
            <td><code>{text(row.valor)}</code></td>
            <td><span className={`diagram-state ${text(row.status) === 'ok' ? 'is-ok' : 'is-danger'}`}>{text(row.status)}</span></td>
            <td>{text(row.evidencia)}</td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function ChecklistView({ result, titulo }: { result: Row; titulo: string }) {
  const linhas = asRows(result.rows);
  const total = linhas.length;
  const presentes = linhas.filter((linha) => text(linha.status) === 'presente').length;
  const peso = linhas.filter((linha) => text(linha.peso) === 'must').length;
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="ITENS" value={total} />
        <Metric label="DECLARADOS" value={presentes} tone="ok" />
        <Metric label="AUSENTES" value={total - presentes} tone={total - presentes ? 'warning' : 'ok'} />
        <Metric label="OBRIGATÓRIOS" value={peso} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo={titulo} colunas={['Item', 'Peso', 'Situação', 'Evidência']}>
        {linhas.map((linha) => (
          <tr key={text(linha.item)}>
            <td><strong>{text(linha.item)}</strong></td>
            <td>{pesoLabel[text(linha.peso)] ?? text(linha.peso)}</td>
            <td><span className={`diagram-state ${text(linha.status) === 'presente' ? 'is-ok' : 'is-danger'}`}>{text(linha.status)}</span></td>
            <td>{text(linha.evidencia)}</td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function ValidacaoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="NÍVEIS" value={count(metrics.niveis)} />
        <Metric label="R²" value={count(metrics.r2) ? fmt(metrics.r2, 4) : '—'} tone={count(metrics.r2) >= 0.99 ? 'ok' : 'danger'} />
        <Metric label="LOD" value={count(metrics.lod) ? fmt(metrics.lod, 3) : '—'} />
        <Metric label="LOQ" value={count(metrics.loq) ? fmt(metrics.loq, 3) : '—'} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Medições por nível" colunas={['Nível', 'n', 'Recuperação', 'RSD', 'Limite', 'Situação']}>
        {asRows(result.rows).map((row, indice) => (
          <tr key={`${text(row.nivel)}-${indice}`}>
            <td><strong>{text(row.nivel)}</strong></td>
            <td>{text(row.n)}</td>
            <td>{text(row.recuperacao)}</td>
            <td>{text(row.rsd)}</td>
            <td><code>{text(row.limite)}</code></td>
            <td><span className={`diagram-state ${text(row.situacao) !== 'fora' ? 'is-ok' : 'is-danger'}`}>{text(row.situacao)}</span></td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function ManuscritoView({ result }: { result: Row }) {
  const metrics = asRow(result.metrics);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="DIRETRIZ" value={text(metrics.diretriz)} />
        <Metric label="SEÇÕES" value={`${count(metrics.secoes_presentes)} / ${count(metrics.secoes_total)}`} />
        <Metric label="ITENS" value={`${count(metrics.itens_presentes)} / ${count(metrics.itens_total)}`} tone={count(metrics.cobertura_diretriz) >= 80 ? 'ok' : 'warning'} />
        <Metric label="PALAVRAS" value={fmt(metrics.palavras, 0)} />
      </div>
      <Verdict blocked={blocked(result)}>{text(result.verdict)}</Verdict>
      <Tabela titulo="Seções e itens da diretriz" colunas={['Item', 'Escopo', 'Situação', 'Evidência']}>
        {asRows(result.rows).map((row, indice) => (
          <tr key={`${text(row.item)}-${indice}`}>
            <td><strong>{text(row.item)}</strong></td>
            <td>{text(row.tipo)}</td>
            <td><span className={`diagram-state ${text(row.status) === 'presente' ? 'is-ok' : 'is-danger'}`}>{text(row.status)}</span></td>
            <td>{text(row.evidencia)}</td>
          </tr>
        ))}
      </Tabela>
      <Findings items={asRows(result.findings)} />
      <Limitations items={result.limitations} />
    </div>
  );
}

function RegrasView({ regras }: { regras: Row | null }) {
  if (!regras) return <p className="diagram-empty">O catálogo ainda não chegou da API.</p>;
  const criterios = asRow(regras.criterios);
  const benchmarks = asRow(regras.benchmarks);
  return (
    <div className="diagram-view">
      <div className="diagram-metrics">
        <Metric label="DIRETRIZES" value={asRows(regras.diretrizes).length || Object.keys(regras.diretrizes ?? {}).length} />
        <Metric label="FÓRMULAS" value={asRows(regras.formulas).length} />
        <Metric label="ITENS DE DESENHO" value={asRows(asRow(regras.desenho).ensaio).length} />
        <Metric label="REPRODUTIBILIDADE" value={asRows(regras.reprodutibilidade).length} />
      </div>
      <p className="diagram-verdict"><Microscope size={14} />{text(regras.principio)}</p>
      <Tabela titulo="Benchmarks de efeito — pequeno · médio · grande" colunas={['Métrica', 'Pequeno', 'Médio', 'Grande']}>
        {Object.entries(benchmarks).map(([chave, valores]) => {
          const lista = Array.isArray(valores) ? valores.map((item) => fmt(item, 2)) : [];
          return (
            <tr key={chave}>
              <td><strong>{chave}</strong></td>
              <td>{lista[0] ?? '—'}</td>
              <td>{lista[1] ?? '—'}</td>
              <td>{lista[2] ?? '—'}</td>
            </tr>
          );
        })}
      </Tabela>
      <div className="ciencia-formulas">
        {asRows(regras.formulas).map((row) => (
          <article key={text(row.id)}><span>{text(row.id)}</span><p><code>{text(row.formula)}</code></p></article>
        ))}
      </div>
      <div className="ciencia-card">
        <h4>Critérios</h4>
        <ul>
          <li>R² mínimo: <code>{fmt(criterios.r2_minimo, 2)}</code></li>
          <li>Alfa: <code>{fmt(criterios.alfa, 2)}</code> · poder: <code>{fmt(criterios.poder, 2)}</code> (confirmatório <code>{fmt(criterios.poder_confirmatorio, 2)}</code>)</li>
          <li>Cromatográfico: recuperação ±<code>{fmt(asRow(criterios.cromatografico).recuperacao, 0)}%</code> · RSD <code>{fmt(asRow(criterios.cromatografico).rsd, 0)}%</code> · LLOQ <code>{fmt(asRow(criterios.cromatografico).lloq, 0)}%</code></li>
          <li>Ligante (LBA): recuperação ±<code>{fmt(asRow(criterios.lba).recuperacao, 0)}%</code> · RSD <code>{fmt(asRow(criterios.lba).rsd, 0)}%</code> · LLOQ <code>{fmt(asRow(criterios.lba).lloq, 0)}%</code></li>
        </ul>
      </div>
      <div className="ciencia-diretrizes">
        {Object.entries(asRow(regras.diretrizes)).map(([tipo, valor]) => {
          const diretriz = asRow(valor);
          return (
            <article key={tipo}>
              <header><strong>{text(diretriz.nome)}</strong><span>{tipo}</span></header>
              <ul>{asList(diretriz.itens).map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
          );
        })}
      </div>
      <div className="diagram-note-card">
        <h4>Itens obrigatórios por tipo de desenho</h4>
        <ul className="diagram-traps">
          {Object.entries(asRow(regras.desenho)).map(([tipo, valor]) => {
            const obrigatorios = asRows(valor).filter((item) => text(item.peso) === 'must').map((item) => text(item.rotulo));
            return <li key={tipo}><strong>{tipo}</strong> — {obrigatorios.join(' · ') || '—'}</li>;
          })}
        </ul>
      </div>
      <div className="ciencia-card">
        <h4>Afirmações que a conferência recusa</h4>
        <ul>{asRows(regras.claims).map((row) => <li key={text(row.id)}><strong>{text(row.rotulo)}</strong> — {groupLabel[text(row.grupo)] ?? text(row.grupo)}</li>)}</ul>
      </div>
      <div className="diagram-limitations">
        <strong>DEIXADO DE FORA</strong>
        <ul>{asList(regras.deixado_de_fora).map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </div>
  );
}

export function CienciaPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<CienciaTab>('amostra');
  const [level, setLevel] = useState<Level>('full');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [regras, setRegras] = useState<Row | null>(null);

  const [teste, setTeste] = useState<Teste>('proporcoes');
  const [alfa, setAlfa] = useState('0.05');
  const [poder, setPoder] = useState('0.8');
  const [alocacao, setAlocacao] = useState('1');
  const [perda, setPerda] = useState('0');
  const [comparacoes, setComparacoes] = useState('1');
  const [baseline, setBaseline] = useState('3');
  const [efeito, setEfeito] = useState('20');
  const [cohenD, setCohenD] = useState('0.5');
  const [nFixo, setNFixo] = useState('');
  const [cluster, setCluster] = useState('');
  const [icc, setIcc] = useState('');

  const [textoEstatistica, setTextoEstatistica] = useState(RESULTADOS);
  const [textoDesenho, setTextoDesenho] = useState(METODOS);
  const [tipoDesenho, setTipoDesenho] = useState<TipoDesenho>('ensaio');
  const [textoRepro, setTextoRepro] = useState(REPRO);
  const [dados, setDados] = useState(DADOS);
  const [curva, setCurva] = useState(CURVA);
  const [modalidade, setModalidade] = useState<TipoModalidade>('cromatografico');
  const [limiteRec, setLimiteRec] = useState('');
  const [limiteRsd, setLimiteRsd] = useState('');
  const [textoManuscrito, setTextoManuscrito] = useState(MANUSCRITO);
  const [tipoEstudo, setTipoEstudo] = useState<TipoEstudo>('ensaio');

  useEffect(() => {
    if (!backendOnline) return;
    let active = true;
    void (async () => {
      try {
        const response = await executeSkill('ciencia.regras', {});
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
      setError('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi conferido.');
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

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (tab === 'amostra') {
      void run('ciencia.amostra', {
        teste,
        alfa: Number(alfa) || 0,
        poder: Number(poder) || 0,
        alocacao: Number(alocacao) || 1,
        perda: Number(perda) || 0,
        comparacoes: Number(comparacoes) || 1,
        baseline: Number(baseline) || 0,
        efeito: Number(efeito) || 0,
        cohen_d: Number(cohenD) || 0,
        n_por_grupo: Number(nFixo) || 0,
        tamanho_cluster: Number(cluster) || 0,
        icc: Number(icc) || 0,
        modo: level,
      });
      return;
    }
    if (tab === 'estatistica') {
      void run('ciencia.estatistica', { texto: textoEstatistica, modo: level });
      return;
    }
    if (tab === 'desenho') {
      void run('ciencia.desenho', { texto: textoDesenho, tipo: tipoDesenho, modo: level });
      return;
    }
    if (tab === 'reprodutibilidade') {
      void run('ciencia.reprodutibilidade', { texto: textoRepro, modo: level });
      return;
    }
    if (tab === 'validacao') {
      void run('ciencia.validacao', {
        dados, curva, tipo: modalidade,
        limite_recuperacao: Number(limiteRec) || 0,
        limite_rsd: Number(limiteRsd) || 0,
        modo: level,
      });
      return;
    }
    if (tab === 'manuscrito') {
      void run('ciencia.manuscrito', { texto: textoManuscrito, tipo: tipoEstudo, modo: level });
      return;
    }
    setError('O catálogo é lido ao abrir a página.');
  };

  const activeTab = tabs.find((item) => item.id === tab) ?? tabs[0];
  const buttonLabel: Record<CienciaTab, string> = {
    amostra: 'Calcular a amostra', estatistica: 'Conferir o relato', desenho: 'Conferir os métodos',
    reprodutibilidade: 'Conferir o material', validacao: 'Validar o método', manuscrito: 'Conferir o manuscrito',
    regras: 'Ler regras',
  };
  const titulo: Record<CienciaTab, string> = {
    amostra: 'Amostra e poder', estatistica: 'Relato estatístico', desenho: 'Desenho do estudo',
    reprodutibilidade: 'Reprodutibilidade', validacao: 'Validação de método', manuscrito: 'Manuscrito',
    regras: 'Limites e fórmulas',
  };

  return (
    <div className="diagram-section ciencia-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Microscope size={22} /></span>
        <div>
          <span className="eyebrow">O QUE O TEXTO CONSEGUE MOSTRAR</span>
          <h2>Rigor é o que se pode verificar</h2>
          <p>Esta camada confere o que um estudo declara e faz a conta de planejamento. Ela calcula amostra e poder, lê o parágrafo de resultados, cobra os itens de desenho que decidem validade, confere a disponibilidade de dado e código, valida a tabela de um método analítico e mede a completude do manuscrito contra a diretriz do tipo de estudo. Não executa análise, não acessa base bibliográfica e não julga mérito.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Presença não é prova</strong><span>A palavra no texto não garante o procedimento; a ausência não prova que não foi feito.</span></li>
          <li><strong>p não é tamanho</strong><span>Efeito e intervalo antes do adjetivo “significativo”.</span></li>
          <li><strong>Completude não é qualidade</strong><span>A lista diz o que deveria estar escrito, não se está certo.</span></li>
          <li><strong>Critério antes do dado</strong><span>Limite escolhido depois de ver o resultado não é critério de aceitação.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos da ciência">
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
            {tab === 'amostra' && (
              <>
                <div className="field-row">
                  <label className="field"><span>Teste</span>
                    <select value={teste} onChange={(event) => setTeste(event.target.value as Teste)}>
                      <option value="proporcoes">Duas proporções</option>
                      <option value="medias">Duas médias</option>
                    </select>
                  </label>
                  <label className="field"><span>Comparações</span><input value={comparacoes} onChange={(event) => setComparacoes(event.target.value)} inputMode="numeric" /></label>
                </div>
                {teste === 'proporcoes' ? (
                  <div className="field-row">
                    <label className="field"><span>Linha de base (%)</span><input value={baseline} onChange={(event) => setBaseline(event.target.value)} inputMode="decimal" /></label>
                    <label className="field"><span>Efeito relativo (%)</span><input value={efeito} onChange={(event) => setEfeito(event.target.value)} inputMode="decimal" /></label>
                  </div>
                ) : (
                  <div className="field-row">
                    <label className="field"><span>d de Cohen</span><input value={cohenD} onChange={(event) => setCohenD(event.target.value)} inputMode="decimal" /></label>
                    <label className="field"><span>n por grupo</span><input value={nFixo} onChange={(event) => setNFixo(event.target.value)} inputMode="numeric" placeholder="opcional" /></label>
                  </div>
                )}
                <div className="field-row">
                  <label className="field"><span>Alfa</span><input value={alfa} onChange={(event) => setAlfa(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Poder</span><input value={poder} onChange={(event) => setPoder(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Perda (fração)</span><input value={perda} onChange={(event) => setPerda(event.target.value)} inputMode="decimal" /></label>
                </div>
                <div className="field-row">
                  <label className="field"><span>Alocação (n2/n1)</span><input value={alocacao} onChange={(event) => setAlocacao(event.target.value)} inputMode="decimal" /></label>
                  <label className="field"><span>Unidades por cluster</span><input value={cluster} onChange={(event) => setCluster(event.target.value)} inputMode="numeric" placeholder="opcional" /></label>
                  <label className="field"><span>ICC</span><input value={icc} onChange={(event) => setIcc(event.target.value)} inputMode="decimal" placeholder="opcional" /></label>
                </div>
              </>
            )}
            {tab === 'estatistica' && (
              <label className="field"><span>Parágrafo de resultados</span><textarea value={textoEstatistica} onChange={(event) => setTextoEstatistica(event.target.value)} rows={12} /></label>
            )}
            {tab === 'desenho' && (
              <>
                <label className="field"><span>Tipo de estudo</span>
                  <select value={tipoDesenho} onChange={(event) => setTipoDesenho(event.target.value as TipoDesenho)}>
                    {tiposDesenho.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
                <label className="field"><span>Métodos</span><textarea value={textoDesenho} onChange={(event) => setTextoDesenho(event.target.value)} rows={12} /></label>
              </>
            )}
            {tab === 'reprodutibilidade' && (
              <label className="field"><span>Métodos e disponibilidade</span><textarea value={textoRepro} onChange={(event) => setTextoRepro(event.target.value)} rows={12} /></label>
            )}
            {tab === 'validacao' && (
              <>
                <label className="field"><span>Modalidade</span>
                  <select value={modalidade} onChange={(event) => setModalidade(event.target.value as TipoModalidade)}>
                    {modalidades.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
                <label className="field"><span>Medições — nivel,medido,alvo[,grupo]</span><textarea value={dados} onChange={(event) => setDados(event.target.value)} rows={9} spellCheck={false} /></label>
                <label className="field"><span>Curva — concentracao,resposta</span><textarea value={curva} onChange={(event) => setCurva(event.target.value)} rows={5} spellCheck={false} /></label>
                <div className="field-row">
                  <label className="field"><span>Limite de recuperação (%)</span><input value={limiteRec} onChange={(event) => setLimiteRec(event.target.value)} inputMode="decimal" placeholder="ICH M10" /></label>
                  <label className="field"><span>Limite de RSD (%)</span><input value={limiteRsd} onChange={(event) => setLimiteRsd(event.target.value)} inputMode="decimal" placeholder="ICH M10" /></label>
                </div>
              </>
            )}
            {tab === 'manuscrito' && (
              <>
                <label className="field"><span>Tipo de estudo</span>
                  <select value={tipoEstudo} onChange={(event) => setTipoEstudo(event.target.value as TipoEstudo)}>
                    {tiposEstudo.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                  </select>
                </label>
                <label className="field"><span>Manuscrito</span><textarea value={textoManuscrito} onChange={(event) => setTextoManuscrito(event.target.value)} rows={14} /></label>
              </>
            )}
            {tab === 'regras' && (
              <p className="diagram-empty"><Dna size={14} />As regras vêm do servidor: benchmarks de efeito, critérios do ICH M10, fórmulas de poder, LOD e LOQ, diretrizes por tipo de estudo e o que ficou de fora.</p>
            )}

            <button className="button primary" type="submit" disabled={busy || (tab === 'regras' && !regras)}>
              {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Microscope size={16} />}
              {busy ? 'Conferindo…' : buttonLabel[tab]}
            </button>
            {error && <p className="diagram-error" role="alert"><AlertTriangle size={14} />{error}</p>}
          </form>
        </section>

        <section className="panel diagram-result">
          <header className="diagram-result-head">
            <div>
              <span className="eyebrow">RESULTADO</span>
              <h3>{titulo[tab]}</h3>
            </div>
            {result && (
              <div className="diagram-result-actions">
                {resultMarkdown && (
                  <button type="button" className="button ghost" onClick={() => void copiar(resultMarkdown)}>
                    Copiar parecer
                  </button>
                )}
              </div>
            )}
          </header>

          {!result && tab === 'regras' && <RegrasView regras={regras} />}
          {!result && tab !== 'regras' && (
            <p className="diagram-empty">
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <Microscope size={14} />}
              {busy ? 'Rodando a conferência…' : 'Preencha à esquerda. Cada resultado mostra a conta e a evidência.'}
            </p>
          )}
          {result && tab === 'amostra' && <AmostraView result={result} />}
          {result && tab === 'estatistica' && <EstatisticaView result={result} />}
          {result && tab === 'desenho' && <ChecklistView result={result} titulo="Itens de desenho" />}
          {result && tab === 'reprodutibilidade' && <ChecklistView result={result} titulo="Itens de reprodutibilidade" />}
          {result && tab === 'validacao' && <ValidacaoView result={result} />}
          {result && tab === 'manuscrito' && <ManuscritoView result={result} />}
        </section>
      </div>
    </div>
  );
}
