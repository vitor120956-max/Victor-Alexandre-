import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  FileDiff,
  GitCompareArrows,
  Layers,
  ListChecks,
  LoaderCircle,
  LocateFixed,
  Play,
  ScrollText,
  ShieldCheck,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';

type RevisaoTab = 'escopo' | 'lotes' | 'achados' | 'posicao' | 'duplicatas' | 'cobertura' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: RevisaoTab; label: string; hint: string; icon: typeof Layers }> = [
  { id: 'escopo', label: 'Escopo', hint: 'O que revisar', icon: FileDiff },
  { id: 'lotes', label: 'Lotes', hint: 'Unidades de leitura', icon: Layers },
  { id: 'achados', label: 'Achados', hint: 'Triagem e ordem', icon: ListChecks },
  { id: 'posicao', label: 'Posição', hint: 'A âncora do comentário', icon: LocateFixed },
  { id: 'duplicatas', label: 'Duplicatas', hint: 'Regra contra agente', icon: GitCompareArrows },
  { id: 'cobertura', label: 'Cobertura', hint: 'Lido contra pedido', icon: ShieldCheck },
  { id: 'regras', label: 'Regras', hint: 'rule.json por caminho', icon: ScrollText },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const severidades = ['nit', 'minor', 'major', 'blocker'] as const;

const DIFF = `diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,6 @@
 import os
+import sys
+TOKEN = os.environ["TOKEN"]
 def main():
-    print("oi")
+    print("olá")
     return 0
diff --git a/src/test_app.py b/src/test_app.py
new file mode 100644
--- /dev/null
+++ b/src/test_app.py
@@ -0,0 +1,3 @@
+def test_main():
+    assert main() == 0
+
diff --git a/web/i18n/messages_pt.properties b/web/i18n/messages_pt.properties
--- a/web/i18n/messages_pt.properties
+++ b/web/i18n/messages_pt.properties
@@ -1 +1,2 @@
 hello=Oi
+bye=Tchau
diff --git a/web/i18n/messages_en.properties b/web/i18n/messages_en.properties
--- a/web/i18n/messages_en.properties
+++ b/web/i18n/messages_en.properties
@@ -1 +1,2 @@
 hello=Hi
+bye=Bye
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1 +1,2 @@
 {}
+{"lockfileVersion": 3}
diff --git a/migrations/001_add_email.sql b/migrations/001_add_email.sql
--- a/migrations/001_add_email.sql
+++ b/migrations/001_add_email.sql
@@ -1 +1,2 @@
 CREATE TABLE usuario (id INT);
+ALTER TABLE usuario ADD COLUMN email TEXT;
`;

const ACHADOS = JSON.stringify(
  [
    { file: 'src/app.py', line: 2, severity: 'critical', source: 'rule', rule: 'W0611', message: 'import sys não é usado neste módulo' },
    { file: 'src/app.py', line: 3, severity: 'warning', source: 'agent', message: 'Import sys nao esta sendo usado neste modulo' },
    { file: 'src/app.py', line: 5, severity: 'warning', source: 'agent', message: 'Função longa demais: considere dividir em partes menores' },
    { file: 'src/app.py', line: 5, severity: 'warning', source: 'agent', message: 'Função longa demais: considere dividir em partes menores' },
    { file: 'migrations/001_add_email.sql', line: 2, severity: 'critical', source: 'rule', rule: 'SQL001', message: 'ALTER TABLE sem caminho de rollback na migration' },
    { file: 'src/app.py', line: 99, severity: 'info', source: 'agent', message: 'Sugestão fora do hunk, provavelmente linha inventada pelo agente' },
  ],
  null,
  2,
);

const REVISADOS = `src/app.py
src/test_app.py
web/i18n/messages_pt.properties`;

const CONVENCOES = `Erro sempre com contexto: mensagem, operação e id do pedido.
Log estruturado em JSON, nunca concatenado.
Teste novo precisa falhar antes da correção.
Migration sempre com down escrito e testado.`;

const asObj = (valor: unknown): Row => (typeof valor === 'object' && valor !== null && !Array.isArray(valor) ? valor as Row : {});
const asRows = (valor: unknown): Row[] => (Array.isArray(valor) ? valor.filter((item): item is Row => typeof item === 'object' && item !== null && !Array.isArray(item)) : []);
const asList = (valor: unknown): string[] => (Array.isArray(valor) ? valor.map((item) => String(item)) : []);
const txt = (valor: unknown): string => (valor === null || valor === undefined ? '' : String(valor));
const num = (valor: unknown): number => (typeof valor === 'number' ? valor : Number(valor ?? 0));
const inteiro = (valor: string, padrao = 0): number => {
  const n = Number(valor.replace(',', '.'));
  return Number.isFinite(n) ? Math.trunc(n) : padrao;
};
const decimal = (valor: string, padrao = 0): number => {
  const n = Number(valor.replace(',', '.'));
  return Number.isFinite(n) ? n : padrao;
};

const grupos: Record<string, string> = { must: 'obrigatório', should: 'corrigir', nice: 'opcional' };

const tomDoGrupo = (valor: string): string => {
  if (['obrigatório', 'blocker', 'must', 'não revisado', 'linha-inexistente', 'linha-removida', 'arquivo-fora-do-diff'].includes(valor)) return 'is-danger';
  if (['corrigir', 'major', 'should', 'deslocado', 'proximo'].includes(valor)) return 'is-warning';
  if (['opcional', 'minor', 'nit', 'nice', 'revisado', 'exato', 'contexto', 'filtrado'].includes(valor)) return 'is-ok';
  return '';
};

type Coluna = { chave: string; titulo: string; tipo?: 'code' | 'pill'; largura?: string };

const colunas: Record<Exclude<RevisaoTab, 'regras'>, Coluna[]> = {
  escopo: [
    { chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' },
    { chave: 'classe', titulo: 'Classe' },
    { chave: 'status', titulo: 'Status' },
    { chave: 'adicionadas', titulo: '+', largura: '44px' },
    { chave: 'removidas', titulo: '−', largura: '44px' },
    { chave: 'risco', titulo: 'Risco', largura: '52px' },
    { chave: 'decisao', titulo: 'Decisão', tipo: 'pill' },
  ],
  lotes: [
    { chave: 'lote', titulo: '#', largura: '40px' },
    { chave: 'arquivos', titulo: 'Arquivos', largura: '64px' },
    { chave: 'principal', titulo: 'Principal', tipo: 'code' },
    { chave: 'outros', titulo: 'Junto com', tipo: 'code' },
    { chave: 'classe', titulo: 'Classe' },
    { chave: 'tokens', titulo: 'Tokens' },
  ],
  achados: [
    { chave: 'ordem', titulo: '#', largura: '40px' },
    { chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' },
    { chave: 'linha', titulo: 'Linha', largura: '54px' },
    { chave: 'severidade', titulo: 'Severidade', tipo: 'pill' },
    { chave: 'fonte', titulo: 'Fonte' },
    { chave: 'ocorrencias', titulo: 'Ocorr.', largura: '58px' },
    { chave: 'resumo', titulo: 'Resumo' },
  ],
  posicao: [
    { chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' },
    { chave: 'linha', titulo: 'Linha', largura: '54px' },
    { chave: 'situacao', titulo: 'Situação', tipo: 'pill' },
    { chave: 'sugestao', titulo: 'Âncora sugerida' },
  ],
  duplicatas: [
    { chave: 'grupo', titulo: '#', largura: '40px' },
    { chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' },
    { chave: 'linhas', titulo: 'Linhas', largura: '70px' },
    { chave: 'achados', titulo: 'Achados', largura: '64px' },
    { chave: 'fontes', titulo: 'Fontes' },
    { chave: 'severidades', titulo: 'Severidades', tipo: 'pill' },
    { chave: 'acao', titulo: 'Ação' },
  ],
  cobertura: [
    { chave: 'arquivo', titulo: 'Arquivo', tipo: 'code' },
    { chave: 'classe', titulo: 'Classe' },
    { chave: 'risco', titulo: 'Risco', largura: '52px' },
    { chave: 'linhas', titulo: 'Linhas', largura: '60px' },
    { chave: 'status', titulo: 'Status', tipo: 'pill' },
  ],
};

const titulos: Record<RevisaoTab, string> = {
  escopo: 'Escopo do diff',
  lotes: 'Lotes de revisão',
  achados: 'Achados normalizados',
  posicao: 'Posição dos comentários',
  duplicatas: 'Duplicatas entre camadas',
  cobertura: 'Cobertura da revisão',
  regras: 'Regras por caminho',
};

type Formato = 'int' | 'dec' | 'pct';

const formatar = (valor: number, formato: Formato = 'int'): string => {
  if (formato === 'pct') return `${valor.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 1 })}%`;
  if (formato === 'dec') return valor.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
  return valor.toLocaleString('pt-BR');
};

const metricasDoTab: Record<Exclude<RevisaoTab, 'regras'>, Array<{ label: string; chave: string; formato?: Formato }>> = {
  escopo: [
    { label: 'ARQUIVOS', chave: 'arquivos' },
    { label: 'REVISAR', chave: 'revisar' },
    { label: 'FILTRAR', chave: 'filtrar' },
    { label: 'LINHAS', chave: 'linhas' },
    { label: 'TESTES', chave: 'testes' },
    { label: 'SEGREDOS', chave: 'segredos' },
  ],
  lotes: [
    { label: 'LOTES', chave: 'lotes' },
    { label: 'ARQUIVOS', chave: 'arquivos' },
    { label: 'MAIOR LOTE', chave: 'maior_lote' },
    { label: 'TOKENS', chave: 'tokens' },
    { label: 'MAIOR EM TOKENS', chave: 'maior_tokens' },
    { label: 'MÉDIA POR LOTE', chave: 'media_arquivos', formato: 'dec' },
  ],
  achados: [
    { label: 'BRUTOS', chave: 'brutos' },
    { label: 'ÚNICOS', chave: 'normalizados' },
    { label: 'DUPLICADOS', chave: 'duplicados' },
    { label: 'BLOCKERS', chave: 'blockers' },
    { label: 'DE REGRA', chave: 'regra' },
    { label: 'INFLADOS', chave: 'inflados', formato: 'pct' },
  ],
  posicao: [
    { label: 'COMENTÁRIOS', chave: 'achados' },
    { label: 'EXATOS', chave: 'exatos' },
    { label: 'CONTEXTO', chave: 'contexto' },
    { label: 'DESLOCADOS', chave: 'deslocados' },
    { label: 'INVÁLIDOS', chave: 'invalidos' },
    { label: 'PRECISÃO', chave: 'precisao', formato: 'pct' },
  ],
  duplicatas: [
    { label: 'ACHADOS', chave: 'achados' },
    { label: 'PARES', chave: 'pares_entre_fontes' },
    { label: 'DUPLICATAS', chave: 'duplicatas' },
    { label: 'GRUPOS', chave: 'grupos' },
    { label: 'CONFLITOS', chave: 'conflitos' },
    { label: 'TAXA', chave: 'taxa', formato: 'pct' },
  ],
  cobertura: [
    { label: 'REVISÁVEIS', chave: 'revisaveis' },
    { label: 'REVISADOS', chave: 'revisados' },
    { label: 'FALTANDO', chave: 'faltando' },
    { label: 'COBERTURA', chave: 'cobertura', formato: 'pct' },
    { label: 'RISCO ALTO', chave: 'risco_alto' },
    { label: 'DESCONHECIDOS', chave: 'desconhecidos' },
  ],
};

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
                  const valor = txt(linha[coluna.chave]) || '—';
                  if (coluna.tipo === 'code') return <td key={coluna.chave}><code>{valor}</code></td>;
                  if (coluna.tipo === 'pill') return <td key={coluna.chave}><span className={['diagram-state', tomDoGrupo(valor)].filter(Boolean).join(' ')}>{valor}</span></td>;
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

export function RevisaoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<RevisaoTab>('escopo');
  const [nivel, setNivel] = useState('full');
  const [diff, setDiff] = useState(DIFF);
  const [achados, setAchados] = useState(ACHADOS);
  const [revisados, setRevisados] = useState(REVISADOS);
  const [convencoes, setConvencoes] = useState(CONVENCOES);
  const [limite, setLimite] = useState('50');
  const [severidade, setSeveridade] = useState('nit');
  const [tolerancia, setTolerancia] = useState('2');
  const [similaridade, setSimilaridade] = useState('0.5');
  const [maxArquivos, setMaxArquivos] = useState('12');
  const [maxRegras, setMaxRegras] = useState('20');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);
  const regraJson = useMemo(() => {
    if (tab !== 'regras') return '';
    const inicio = markdown.indexOf('```json');
    if (inicio < 0) return '';
    const fim = markdown.indexOf('```', inicio + 7);
    return fim < 0 ? '' : markdown.slice(inicio + 7, fim).trim();
  }, [markdown, tab]);
  const usaDiff = tab === 'escopo' || tab === 'lotes' || tab === 'posicao' || tab === 'cobertura' || tab === 'regras';
  const usaAchados = tab === 'achados' || tab === 'posicao' || tab === 'duplicatas';

  const trocarTab = (destino: RevisaoTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    const comum = { modo: nivel };
    if (tab === 'escopo') return { diff, ...comum };
    if (tab === 'lotes') return { diff, max_arquivos: inteiro(maxArquivos, 12), ...comum };
    if (tab === 'achados') return { achados, limite: inteiro(limite, 50), severidade_minima: severidade, ...comum };
    if (tab === 'posicao') return { diff, achados, tolerancia: inteiro(tolerancia, 2), ...comum };
    if (tab === 'duplicatas') return { achados, tolerancia: inteiro(tolerancia, 2), similaridade: decimal(similaridade, 0.5), ...comum };
    if (tab === 'cobertura') return { diff, revisados, ...comum };
    return { diff, convencoes, max_regras: inteiro(maxRegras, 20), ...comum };
  };

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi calculado.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`revisao.${tab}`, parametros());
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

  const copiar = async (texto: string, titulo: string) => {
    if (!texto) return;
    try {
      await navigator.clipboard.writeText(texto);
      pushToast(titulo, 'O texto está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const rotuloBotao: Record<RevisaoTab, string> = {
    escopo: 'Ler o diff',
    lotes: 'Agrupar em lotes',
    achados: 'Normalizar achados',
    posicao: 'Conferir as âncoras',
    duplicatas: 'Comparar as fontes',
    cobertura: 'Medir a cobertura',
    regras: 'Montar o rule.json',
  };

  const bloqueado = num(asObj(resultado?.counts).must) > 0;

  return (
    <div className="diagram-section selecao-page revisao-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><GitCompareArrows size={22} /></span>
        <div>
          <span className="eyebrow">REVISÃO HÍBRIDA, COM A PARTE CHATA RESOLVIDA</span>
          <h2>Revisão é cobertura e âncora</h2>
          <p>O open-code-review existe porque revisão feita só por agente tem três falhas conhecidas: cobre pouco em diff grande, erra a linha do comentário e varia com o prompt. Aqui a parte determinística é conta explícita — escopo por classe de arquivo, lote por assunto, severidade normalizada, âncora conferida contra o hunk, duplicata entre regra e agente e cobertura contra o que o diff pedia.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Arquivo gerado não é revisão</strong><span>Lockfile e vendor saem da conta.</span></li>
          <li><strong>Lote é assunto</strong><span>Código vai com o seu teste.</span></li>
          <li><strong>Comentário precisa de linha</strong><span>Fora do hunk é deriva de posição.</span></li>
          <li><strong>Duplicata custa confiança</strong><span>O mesmo problema se publica uma vez.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Modos de revisão">
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
            <label className="diagram-level">
              <span>NÍVEL</span>
              <select value={nivel} onChange={(event) => setNivel(event.target.value)}>
                {niveis.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
          </header>

          <form className="form-stack" onSubmit={executar}>
            {usaDiff && (
              <label className="field">
                <span>Diff unificado — <code>git diff</code>, <code>git show</code> ou <code>gh pr diff</code></span>
                <textarea value={diff} onChange={(event) => setDiff(event.target.value)} rows={12} spellCheck={false} className="revisao-diff" />
                <small className="selecao-contador">{diff.length.toLocaleString('pt-BR')} caracteres</small>
              </label>
            )}

            {usaAchados && (
              <label className="field">
                <span>Achados — JSON com <code>file</code>, <code>line</code>, <code>severity</code>, <code>source</code> e <code>message</code></span>
                <textarea value={achados} onChange={(event) => setAchados(event.target.value)} rows={10} spellCheck={false} />
                <small className="selecao-contador">{achados.length.toLocaleString('pt-BR')} caracteres</small>
              </label>
            )}

            {tab === 'cobertura' && (
              <label className="field">
                <span>Arquivos revisados — um caminho por linha</span>
                <textarea value={revisados} onChange={(event) => setRevisados(event.target.value)} rows={5} spellCheck={false} />
              </label>
            )}

            {tab === 'regras' && (
              <label className="field">
                <span>Convenções do projeto — o que não está no código</span>
                <textarea value={convencoes} onChange={(event) => setConvencoes(event.target.value)} rows={6} spellCheck={false} />
              </label>
            )}

            {tab === 'achados' && (
              <div className="selecao-filtros">
                <label>
                  <span>Severidade mínima</span>
                  <select value={severidade} onChange={(event) => setSeveridade(event.target.value)}>
                    {severidades.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label><span>Por página</span><input type="number" min={1} max={500} value={limite} onChange={(event) => setLimite(event.target.value)} /></label>
              </div>
            )}

            {(tab === 'lotes' || tab === 'regras') && (
              <div className="selecao-filtros">
                {tab === 'lotes' && (
                  <label><span>Arquivos por lote</span><input type="number" min={2} max={50} value={maxArquivos} onChange={(event) => setMaxArquivos(event.target.value)} /></label>
                )}
                {tab === 'regras' && (
                  <label><span>Regras</span><input type="number" min={1} max={200} value={maxRegras} onChange={(event) => setMaxRegras(event.target.value)} /></label>
                )}
              </div>
            )}

            {(tab === 'posicao' || tab === 'duplicatas') && (
              <div className="selecao-filtros">
                <label><span>Tolerância (linhas)</span><input type="number" min={0} max={50} value={tolerancia} onChange={(event) => setTolerancia(event.target.value)} /></label>
                {tab === 'duplicatas' && (
                  <label><span>Similaridade (0–1)</span><input type="number" min={0.1} max={1} step={0.05} value={similaridade} onChange={(event) => setSimilaridade(event.target.value)} /></label>
                )}
              </div>
            )}

            <div className="selecao-acoes">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="diagram-spin" /> : <Play size={16} />}
                {busy ? 'Calculando…' : rotuloBotao[tab]}
              </button>
              <button type="button" className="button ghost" onClick={() => { setDiff(DIFF); setAchados(ACHADOS); setRevisados(REVISADOS); setConvencoes(CONVENCOES); }}>
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
              {busy ? <LoaderCircle size={14} className="diagram-spin" /> : <FileDiff size={14} />}
              {busy ? 'Lendo o diff…' : 'A amostra já traz um diff com segredo, teste, locales, lockfile e migration: rode para ver cada achado.'}
            </p>
          )}

          {resultado && tab !== 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                {metricasDoTab[tab].map((metrica) => (
                  <Metric key={metrica.chave} label={metrica.label} value={formatar(num(asObj(resultado.metrics)[metrica.chave]), metrica.formato)} />
                ))}
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>
              <Tabela titulo="Evidência" colunas={colunas[tab]} linhas={asRows(resultado.rows)} />
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}

          {resultado && tab === 'regras' && (
            <div className="diagram-view">
              <div className="diagram-metrics">
                <Metric label="REGRAS" value={formatar(num(asObj(resultado.metrics).regras))} />
                <Metric label="CANDIDATOS" value={formatar(num(asObj(resultado.metrics).candidatos))} />
                <Metric label="OMITIDOS" value={formatar(num(asObj(resultado.metrics).omitidos))} />
                <Metric label="TOKENS" value={formatar(num(asObj(resultado.metrics).tokens))} />
                <Metric label="REPETIDAS" value={formatar(num(asObj(resultado.metrics).repetidas))} />
                <Metric label="CONVENÇÕES" value={num(asObj(resultado.metrics).com_convencoes) ? 'sim' : 'não'} />
              </div>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>
              <Tabela
                titulo="Regras propostas"
                colunas={[
                  { chave: 'caminho', titulo: 'Caminho', tipo: 'code' },
                  { chave: 'classe', titulo: 'Classe' },
                  { chave: 'caracteristica', titulo: 'Característica' },
                  { chave: 'linhas', titulo: 'Linhas', largura: '58px' },
                  { chave: 'tokens', titulo: 'Tokens', largura: '62px' },
                  { chave: 'merge', titulo: 'Merge', largura: '56px' },
                ]}
                linhas={asRows(resultado.rows)}
              />
              {regraJson && (
                <div className="revisao-json">
                  <header>
                    <h4>rule.json proposto</h4>
                    <button type="button" className="button ghost" onClick={() => void copiar(regraJson, 'rule.json copiado')}><Copy size={14} />Copiar</button>
                  </header>
                  <pre>{regraJson}</pre>
                </div>
              )}
              <Findings items={asRows(resultado.findings)} />
              <Limitations items={resultado.limitations} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
