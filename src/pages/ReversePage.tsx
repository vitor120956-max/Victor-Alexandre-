import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Binary,
  Braces,
  Check,
  Download,
  FileSearch,
  Fingerprint,
  GitCompare,
  ListTree,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { listReverseArtifacts, uploadReverseArtifact } from '../lib/api';
import type { ReverseArtifact } from '../lib/api';
import '../reverse.css';

type Row = Record<string, unknown>;
type Columns = Array<{ key: string; label: string; render?: (row: Row) => React.ReactNode }>;

const MAX_ARTIFACT_BYTES = 25_000_000;
const MAX_BATCH_FILES = 30;
const MAX_BATCH_BYTES = 100_000_000;
const ALLOWED_EXTENSIONS = new Set(['.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.json', '.map', '.html', '.htm', '.css', '.wasm', '.elf', '.macho', '.o', '.obj', '.bin', '.so', '.dylib', '.dll', '.exe', '.apk', '.aar', '.jar', '.zip', '.asar', '.ipa', '.dmg', '.msix', '.har', '.pcap', '.py', '.pyc', '.beam', '.gguf', '.safetensors', '.onnx', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.txt', '.md', '.log', '.hbc', '.dex', '.class', '.pack', '.dat', '.img', '.rom']);
const ACCEPTED = Array.from(ALLOWED_EXTENSIONS).join(',');

const asRow = (value: unknown): Row => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Row : {});
const asRows = (value: unknown): Row[] => (Array.isArray(value) ? value.map(asRow) : []);
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: unknown): number => (typeof value === 'number' ? value : Number(value ?? 0));

function bytesLabel(value: unknown): string {
  const bytes = count(value);
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(2)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  return `${bytes} B`;
}

function Metric({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return <article><span>{label}</span><strong className={mono ? 'is-mono' : undefined}>{value}</strong></article>;
}

function Table({ columns, rows, empty, limit = 40 }: { columns: Columns; rows: Row[]; empty: string; limit?: number }) {
  if (!rows.length) return <p className="reverse-table-empty">{empty}</p>;
  const visible = rows.slice(0, limit);
  return (
    <div className="reverse-scroll">
      <table className="reverse-table">
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={`${index}-${text(row.name ?? row.path ?? row.library ?? row.offset ?? row.reason)}`}>
              {columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : text(row[column.key])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limit && <p className="reverse-table-note">Exibindo {limit} de {rows.length} linhas. O JSON completo permanece disponível abaixo.</p>}
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="reverse-json-block">
      <summary>{label}</summary>
      <pre className="reverse-json">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return null;
  return (
    <div className="reverse-findings">
      {items.map((item, index) => (
        <p key={index} className={text(item.severity) === 'attention' ? 'is-attention' : undefined}>
          <ShieldAlert size={13} />
          <span>{text(item.message)}</span>
        </p>
      ))}
    </div>
  );
}

function Limitations({ items }: { items: unknown }) {
  const values = Array.isArray(items) ? items.map(text).filter(Boolean) : [];
  if (!values.length) return null;
  return (
    <div className="reverse-limitations">
      <strong>Limites desta análise</strong>
      <ul>{values.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Chips({ title, values }: { title: string; values: unknown }) {
  const items = Array.isArray(values) ? values.map(text).filter(Boolean) : [];
  return (
    <div className="reverse-chips-block">
      <span>{title}</span>
      {items.length ? <div className="reverse-chips">{items.map((item) => <code key={item}>{item}</code>)}</div> : <p className="reverse-table-empty">Nenhum item nesta categoria.</p>}
    </div>
  );
}

function InspectView({ result }: { result: Row }) {
  const identity = asRow(result.identity);
  const entropy = asRow(result.entropy);
  const counts = asRow(result.counts);
  return (
    <div className="reverse-view">
      <div className="reverse-metrics">
        <Metric label="FORMATO" value={text(result.format)} />
        <Metric label="TAMANHO" value={bytesLabel(identity.bytes)} />
        <Metric label="ENTROPIA" value={count(entropy.fileEntropy).toFixed(3)} mono />
        <Metric label="EXECUTADO" value="NÃO" mono />
      </div>
      <div className="reverse-hash"><Fingerprint size={14} /><span>SHA-256</span><code>{text(identity.sha256)}</code></div>
      <div className="reverse-metrics reverse-metrics-compact">
        <Metric label="SEÇÕES" value={count(counts.sections)} />
        <Metric label="SEGMENTOS" value={count(counts.segments)} />
        <Metric label="ENTRADAS" value={count(counts.entries)} />
        <Metric label="IMPORTS" value={count(counts.imports)} />
      </div>
      <Findings items={asRows(result.topFindings)} />
      <JsonBlock label="Fatos estruturais (JSON)" value={result.facts} />
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

function LayoutView({ result }: { result: Row }) {
  const sections = asRows(result.sections).map((section) => ({
    ...section,
    size: section.size ?? section.virtualSize,
    address: section.addr ?? section.virtualAddress,
  }));
  const segments = asRows(result.segments).map((segment) => ({
    ...segment,
    size: segment.filesz ?? segment.fileSize,
    address: segment.vaddr ?? segment.vmaddr,
  }));
  return (
    <div className="reverse-view">
      <div className="reverse-metrics">
        <Metric label="FORMATO" value={text(result.format)} />
        <Metric label="SEÇÕES" value={sections.length} />
        <Metric label="SEGMENTOS" value={segments.length} />
        <Metric label="TRUNCADO" value={result.truncated ? 'SIM' : 'NÃO'} />
      </div>
      <Findings items={asRows(result.findings)} />
      <h3>Seções</h3>
      <Table
        empty="O formato não expõe seções nesta análise."
        rows={sections}
        columns={[
          { key: 'index', label: '#' },
          { key: 'name', label: 'Nome' },
          { key: 'type', label: 'Tipo' },
          { key: 'address', label: 'Endereço', render: (row) => <code>{text(row.address)}</code> },
          { key: 'size', label: 'Bytes', render: (row) => count(row.size).toLocaleString('pt-BR') },
        ]}
      />
      <h3>Segmentos</h3>
      <Table
        empty="O formato não expõe segmentos nesta análise."
        rows={segments}
        columns={[
          { key: 'name', label: 'Nome', render: (row) => text(row.name) || `tipo ${text(row.type)}` },
          { key: 'flags', label: 'Flags', render: (row) => <code>{text(row.flags)}</code> },
          { key: 'offset', label: 'Offset' },
          { key: 'address', label: 'Endereço', render: (row) => <code>{text(row.address)}</code> },
          { key: 'size', label: 'Arquivo', render: (row) => count(row.size).toLocaleString('pt-BR') },
        ]}
      />
      <h3>Entradas e recursos</h3>
      <Table
        empty="Nenhuma entrada de contêiner foi inventariada."
        rows={asRows(result.entries)}
        columns={[
          { key: 'name', label: 'Caminho' },
          { key: 'bytes', label: 'Bytes', render: (row) => count(row.bytes).toLocaleString('pt-BR') },
          { key: 'compressedBytes', label: 'Comprimido' },
          { key: 'crc32', label: 'CRC32', render: (row) => <code>{text(row.crc32)}</code> },
          { key: 'unsafeName', label: 'Caminho inseguro', render: (row) => (row.unsafeName ? 'sim' : 'não') },
        ]}
      />
      <h3>Imports e dependências</h3>
      <Table
        empty="Nenhuma biblioteca importada foi identificada."
        rows={asRows(result.imports)}
        columns={[
          { key: 'library', label: 'Biblioteca' },
          { key: 'functions', label: 'Funções', render: (row) => (row.functions === undefined ? '—' : count(row.functions)) },
          { key: 'kind', label: 'Tipo' },
        ]}
      />
      <JsonBlock label="Fatos do cabeçalho (JSON)" value={result.facts} />
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

function StringsView({ result }: { result: Row }) {
  const window = asRow(result.window);
  return (
    <div className="reverse-view">
      <div className="reverse-metrics">
        <Metric label="STRINGS" value={count(result.count)} />
        <Metric label="MÍNIMO" value={`${count(result.minLength)} bytes`} />
        <Metric label="JANELA" value={`${count(window.offset)} + ${count(window.length)}`} mono />
        <Metric label="LIMITADO" value={result.truncated ? 'SIM' : 'NÃO'} />
      </div>
      <Table
        empty="Nenhuma string imprimível foi encontrada com esse filtro."
        rows={asRows(result.items)}
        limit={80}
        columns={[
          { key: 'offset', label: 'Offset', render: (row) => <code>0x{count(row.offset).toString(16)}</code> },
          { key: 'encoding', label: 'Codificação' },
          { key: 'value', label: 'Valor', render: (row) => <span className="reverse-string-value">{text(row.value)}</span> },
        ]}
      />
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

function EntropyView({ result }: { result: Row }) {
  return (
    <div className="reverse-view">
      <div className="reverse-metrics">
        <Metric label="ENTROPIA" value={count(result.fileEntropy).toFixed(4)} mono />
        <Metric label="BLOCOS" value={count(result.blockCount)} />
        <Metric label="TAMANHO DO BLOCO" value={`${count(result.blockSize)} B`} />
        <Metric label="EXECUTADO" value="NÃO" mono />
      </div>
      <Table
        empty="Nenhuma região foi classificada."
        rows={asRows(result.runs)}
        columns={[
          { key: 'offset', label: 'Offset', render: (row) => <code>0x{count(row.offset).toString(16)}</code> },
          { key: 'length', label: 'Comprimento' },
          { key: 'classification', label: 'Classificação', render: (row) => <span className={`reverse-classification is-${text(row.classification)}`}>{text(row.classification)}</span> },
        ]}
      />
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

function JavaScriptView({ result }: { result: Row }) {
  const target = asRow(result.target);
  const coverage = asRow(result.coverage);
  const packageInfo = asRow(result.package);
  const modules = asRows(result.modules);
  const facts = asRows(result.facts);
  const attention = facts.filter((fact) => text(fact.severity) === 'attention');
  return (
    <div className="reverse-view">
      <div className="reverse-metrics">
        <Metric label="MODO" value={text(result.mode)} />
        <Metric label="ARQUIVOS" value={count(target.files)} />
        <Metric label="BYTES LIDOS" value={bytesLabel(target.bytesRead ?? coverage.bytesRead)} />
        <Metric label="EXECUTADO" value="NÃO" mono />
      </div>
      <div className="reverse-hash"><Fingerprint size={14} /><span>IDENTIDADE DA ÁRVORE</span><code>{text(target.sha256)}</code></div>
      {packageInfo.name !== undefined && packageInfo.name !== null && (
        <div className="reverse-package">
          <strong>{text(packageInfo.name)} {packageInfo.version ? `v${text(packageInfo.version)}` : ''}</strong>
          <span>main: {text(packageInfo.main) || 'não declarado'} · type: {text(packageInfo.type) || 'não declarado'}</span>
          {Array.isArray(packageInfo.dependencies) && packageInfo.dependencies.length > 0 && <small>Dependências: {packageInfo.dependencies.map(text).slice(0, 12).join(', ')}{packageInfo.dependencies.length > 12 ? '…' : ''}</small>}
        </div>
      )}
      <div className="reverse-metrics reverse-metrics-compact">
        <Metric label="MÓDULOS" value={modules.length} />
        <Metric label="RELAÇÕES" value={asRows(result.relationships).length} />
        <Metric label="NÃO RESOLVIDOS" value={asRows(result.unresolved).length} />
        <Metric label="LIMITE ATINGIDO" value={coverage.limitReached ? 'SIM' : 'NÃO'} />
      </div>
      <Findings items={attention} />
      <h3>Módulos</h3>
      <Table
        empty="Nenhum módulo JavaScript ou TypeScript foi analisado."
        rows={modules}
        columns={[
          { key: 'path', label: 'Caminho' },
          { key: 'language', label: 'Linguagem' },
          { key: 'lines', label: 'Linhas' },
          { key: 'imports', label: 'Imports', render: (row) => asRows(row.imports).length },
          { key: 'facts', label: 'Fatos', render: (row) => asRows(row.facts).length },
        ]}
      />
      <h3>Relações resolvidas</h3>
      <Table
        empty="Nenhuma relação relativa foi resolvida dentro da árvore."
        rows={asRows(result.relationships)}
        columns={[
          { key: 'from', label: 'De' },
          { key: 'to', label: 'Para' },
          { key: 'specifier', label: 'Especificador', render: (row) => <code>{text(row.specifier)}</code> },
          { key: 'kind', label: 'Tipo' },
        ]}
      />
      <h3>Pendências e imports dinâmicos</h3>
      <Table
        empty="Nenhuma importação ficou pendente."
        rows={asRows(result.unresolved)}
        columns={[
          { key: 'file', label: 'Arquivo' },
          { key: 'specifier', label: 'Especificador' },
          { key: 'reason', label: 'Motivo' },
          { key: 'line', label: 'Linha' },
        ]}
      />
      <h3>Fatos Electron e de risco</h3>
      <Table
        empty="Nenhum fato conhecido foi observado."
        limit={60}
        rows={facts}
        columns={[
          { key: 'category', label: 'Categoria', render: (row) => <code>{text(row.category)}</code> },
          { key: 'file', label: 'Arquivo' },
          { key: 'line', label: 'Linha' },
          { key: 'severity', label: 'Nível', render: (row) => <span className={`reverse-classification is-${text(row.severity)}`}>{text(row.severity)}</span> },
          { key: 'evidence', label: 'Evidência', render: (row) => <span className="reverse-evidence">{text(row.evidence)}</span> },
        ]}
      />
      <h3>Rotas e endpoints candidatos</h3>
      <Table
        empty="Nenhuma rota estática foi encontrada."
        rows={asRows(result.routes)}
        columns={[
          { key: 'method', label: 'Método' },
          { key: 'path', label: 'Caminho' },
          { key: 'file', label: 'Arquivo' },
          { key: 'line', label: 'Linha' },
        ]}
      />
      <Table
        empty="Nenhuma URL de fetch foi encontrada."
        rows={asRows(result.endpoints)}
        columns={[
          { key: 'url', label: 'URL observada' },
          { key: 'file', label: 'Arquivo' },
          { key: 'line', label: 'Linha' },
        ]}
      />
      <Chips title="Candidatos a entrada" values={asRows(result.entryCandidates).map((item) => `${text(item.path)} (${text(item.reason)})`)} />
      <JsonBlock label="Cobertura e arquivos ignorados (JSON)" value={{ coverage, htmlReferences: result.htmlReferences }} />
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

function CompareView({ result }: { result: Row }) {
  const left = asRow(result.left);
  const right = asRow(result.right);
  const sections = asRow(result.sections);
  const entries = asRow(result.entries);
  const imports = asRow(result.imports);
  const strings = asRow(result.strings);
  return (
    <div className="reverse-view">
      <div className="reverse-compare-head">
        <article><span>REFERÊNCIA</span><strong>{text(left.path)}</strong><small>{bytesLabel(left.bytes)} · {text(left.kind)}</small><code>{text(left.sha256).slice(0, 20)}…</code></article>
        <span className={`reverse-verdict ${result.identical ? 'is-identical' : ''}`}>{result.identical ? <><Check size={14} /> IDÊNTICOS</> : <><GitCompare size={14} /> DIFERENTES</>}</span>
        <article><span>COMPARADO</span><strong>{text(right.path)}</strong><small>{bytesLabel(right.bytes)} · {text(right.kind)}</small><code>{text(right.sha256).slice(0, 20)}…</code></article>
      </div>
      <div className="reverse-metrics">
        <Metric label="DELTA DE TAMANHO" value={`${count(result.sizeDelta) > 0 ? '+' : ''}${bytesLabel(Math.abs(count(result.sizeDelta)))}`} />
        <Metric label="MESMO FORMATO" value={result.comparable ? 'SIM' : 'NÃO'} />
        <Metric label="STRINGS ADICIONADAS" value={count(strings.addedCount)} />
        <Metric label="STRINGS REMOVIDAS" value={count(strings.removedCount)} />
      </div>
      {result.sections ? <Chips title="Seções adicionadas" values={sections.added} /> : null}
      {result.sections ? <Chips title="Seções removidas" values={sections.removed} /> : null}
      {result.sections ? <Chips title="Seções alteradas" values={sections.changed} /> : null}
      {result.entries ? <Chips title="Entradas adicionadas" values={entries.added} /> : null}
      {result.entries ? <Chips title="Entradas removidas" values={entries.removed} /> : null}
      {result.imports ? <Chips title="Imports adicionados" values={imports.added} /> : null}
      {result.imports ? <Chips title="Imports removidos" values={imports.removed} /> : null}
      {result.strings ? <Chips title="Strings adicionadas (amostra)" values={strings.added} /> : null}
      {result.strings ? <Chips title="Strings removidas (amostra)" values={strings.removed} /> : null}
      <Limitations items={result.limitations} />
      <JsonBlock label="Resposta completa (JSON)" value={result} />
    </div>
  );
}

export function ReversePage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [artifacts, setArtifacts] = useState<ReverseArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [selected, setSelected] = useState('');
  const [comparePath, setComparePath] = useState('');
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState<{ skillId: string; data: Row } | null>(null);
  const [requestError, setRequestError] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadDirectory, setUploadDirectory] = useState('');
  const [uploadOverwrite, setUploadOverwrite] = useState(false);
  const [uploadConfirmed, setUploadConfirmed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [inlineSource, setInlineSource] = useState('');
  const [treePath, setTreePath] = useState('');
  const [batch, setBatch] = useState<{ done: number; total: number } | null>(null);
  const [folderError, setFolderError] = useState('');
  const resultRef = useRef<HTMLElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const registerFolderInput = (node: HTMLInputElement | null) => {
    folderInputRef.current = node;
    if (node) {
      node.setAttribute('webkitdirectory', '');
      node.setAttribute('directory', '');
    }
  };

  const load = async () => {
    if (!backendOnline) return;
    setLoading(true);
    setListError('');
    try {
      const response = await listReverseArtifacts();
      setArtifacts(response.artifacts);
      setSelected((current) => (current && response.artifacts.some((item) => item.path === current) ? current : ''));
    } catch (error) {
      setListError(error instanceof Error ? error.message : 'Falha ao listar os artefatos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendOnline]);

  const selectedArtifact = useMemo(() => artifacts.find((artifact) => artifact.path === selected) ?? null, [artifacts, selected]);

  const run = async (skillId: string, parameters: Record<string, unknown>) => {
    if (busy) return;
    setBusy(skillId);
    setRequestError('');
    try {
      const response = await executeSkill(skillId, parameters);
      if (!response.ok || !response.result) {
        setRequestError(response.error?.message ?? 'A análise foi recusada.');
        return;
      }
      setResult({ skillId, data: response.result });
      pushToast('Análise concluída', 'Nenhum byte foi executado.');
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 40);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Falha ao executar a análise.');
    } finally {
      setBusy('');
    }
  };

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!uploadFile || uploading) return;
    setUploadError('');
    if (uploadFile.size > MAX_ARTIFACT_BYTES) {
      setUploadError('O artefato excede o limite de 25 MB.');
      return;
    }
    setUploading(true);
    try {
      const response = await uploadReverseArtifact({
        file: uploadFile,
        directory: uploadDirectory,
        overwrite: uploadOverwrite,
        confirmed: uploadConfirmed,
      });
      pushToast('Artefato enviado', response.path);
      setUploadFile(null);
      setUploadConfirmed(false);
      setUploadOverwrite(false);
      setSelected(response.path);
      await load();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Falha ao enviar o artefato.');
    } finally {
      setUploading(false);
    }
  };

  const uploadFolder = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    setFolderError('');
    if (!files.length) return;
    if (files.length > MAX_BATCH_FILES) {
      setFolderError(`Selecione no máximo ${MAX_BATCH_FILES} arquivos por lote para respeitar o limite da API.`);
      return;
    }
    const accepted = files.filter((file) => {
      const name = file.name;
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath || name;
      const suffix = name.slice(name.lastIndexOf('.')).toLowerCase();
      return !relative.split('/').some((part) => part.startsWith('.')) && file.size > 0 && file.size <= MAX_ARTIFACT_BYTES && ALLOWED_EXTENSIONS.has(suffix);
    });
    const totalBytes = accepted.reduce((sum, file) => sum + file.size, 0);
    if (!accepted.length) {
      setFolderError('Nenhum arquivo compatível foi encontrado nessa pasta.');
      return;
    }
    if (totalBytes > MAX_BATCH_BYTES) {
      setFolderError('O lote excede 100 MB no total. Envie menos arquivos por vez.');
      return;
    }
    setBatch({ done: 0, total: accepted.length });
    let failed = 0;
    for (const [index, file] of accepted.entries()) {
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      const parts = relative.split('/').filter(Boolean);
      parts.pop();
      const directory = parts.join('/');
      try {
        await uploadReverseArtifact({ file, directory, overwrite: false, confirmed: true });
      } catch {
        failed += 1;
      }
      setBatch({ done: index + 1, total: accepted.length });
    }
    const rootFolder = ((accepted[0] as File & { webkitRelativePath?: string }).webkitRelativePath || '').split('/')[0];
    if (rootFolder) setTreePath(rootFolder);
    await load();
    setBatch(null);
    if (failed) setFolderError(`${failed} de ${accepted.length} arquivos não puderam ser enviados.`);
    else pushToast('Pasta enviada', `${accepted.length} arquivos enviados. Use “Analisar árvore” para o conjunto.`);
  };

  const analyze = (skillId: string) => {
    if (!selected) return;
    void run(skillId, { path: selected });
  };

  const compare = () => {
    if (!selected || !comparePath) return;
    void run('reverse.compare', { left: comparePath, right: selected });
  };

  const analyzeInline = (event: React.FormEvent) => {
    event.preventDefault();
    if (!inlineSource.trim()) return;
    void run('reverse.javascript', { path: '', source: inlineSource });
  };

  const data = result?.data ?? null;

  return (
    <div className="reverse-page">
      <header className="page-heading">
        <div><span className="eyebrow">ANÁLISE ESTÁTICA DE ARTEFATOS</span><h1>Engenharia reversa<span>.</span></h1><p>Entenda binários, pacotes e aplicações sem executar o alvo.</p></div>
        <span className="local-badge"><ShieldCheck size={12} /> NENHUM ARTEFATO É EXECUTADO</span>
      </header>

      {!backendOnline ? (
        <div className="legal-offline panel"><span><Binary size={25} /></span><div><h2>Análise reversa indisponível offline</h2><p>Inicie a API Python com <code>.venv\Scripts\python iniciar.py</code>. Nenhum artefato será simulado, executado ou enviado à IA.</p></div></div>
      ) : (
        <>
          <div className="reverse-layout">
            <section className="panel reverse-library">
              <div className="section-heading compact-heading"><div><span className="eyebrow">ÁREA CONFINADA</span><h2>Artefatos</h2></div><button className="icon-button small" onClick={() => void load()} disabled={loading} aria-label="Atualizar artefatos"><RefreshCw size={14} className={loading ? 'legal-spinner' : ''} /></button></div>
              <form className="reverse-upload" onSubmit={upload}>
                <label className="document-file-picker"><Upload size={16} /><span>{uploadFile ? uploadFile.name : 'Escolher artefato para upload'}</span><input type="file" accept={ACCEPTED} onChange={(event) => { setUploadFile(event.target.files?.[0] ?? null); setUploadConfirmed(false); setUploadError(''); }} /></label>
                {uploadFile && <div className="reverse-upload-details"><span>{bytesLabel(uploadFile.size)}</span><label>Pasta de destino<input value={uploadDirectory} onChange={(event) => setUploadDirectory(event.target.value)} maxLength={120} placeholder="ex.: app" /></label></div>}
                {uploadFile && <><label className="document-check"><input type="checkbox" checked={uploadOverwrite} onChange={(event) => setUploadOverwrite(event.target.checked)} /><span>Permitir sobrescrever</span></label><label className="document-check confirmation"><input type="checkbox" checked={uploadConfirmed} onChange={(event) => setUploadConfirmed(event.target.checked)} /><span>Confirmo a gravação deste artefato na área isolada.</span></label></>}
                {uploadError && <p className="document-form-error">{uploadError}</p>}
                <button className="button button-secondary" disabled={!uploadFile || !uploadConfirmed || uploading || (uploadFile?.size ?? 0) > MAX_ARTIFACT_BYTES}>{uploading ? <LoaderCircle className="legal-spinner" size={15} /> : <Upload size={15} />}{uploading ? 'Enviando...' : 'Confirmar upload'}</button>
              </form>
              <div className="reverse-folder-upload">
                <label className="document-file-picker"><Upload size={15} /><span>{batch ? `Enviando ${batch.done}/${batch.total}...` : `Enviar pasta de aplicação (até ${MAX_BATCH_FILES} arquivos)`}</span><input ref={registerFolderInput} type="file" multiple onChange={(event) => void uploadFolder(event)} disabled={Boolean(batch)} /></label>
                <small>Uma confirmação cobre o lote. Nada é extraído; os arquivos vão para subpastas com o caminho relativo.</small>
                {folderError && <p className="document-form-error">{folderError}</p>}
              </div>
              {listError && <div className="document-form-error">{listError}</div>}
              <div className="reverse-list" aria-live="polite">
                {artifacts.map((artifact) => (
                  <article className={`reverse-item ${selected === artifact.path ? 'is-selected' : ''} ${comparePath === artifact.path ? 'is-compare' : ''}`} key={artifact.path}>
                    <button className="reverse-item-main" onClick={() => setSelected(artifact.path)} title="Selecionar para análise">
                      <span className="reverse-item-icon"><Binary size={15} /></span>
                      <span><strong>{artifact.path.split('/').pop()}</strong><small>{artifact.path} · {bytesLabel(artifact.bytes)}</small></span>
                      <em>{artifact.kind}</em>
                    </button>
                    <div className="reverse-item-actions">
                      <button className={`icon-button small ${comparePath === artifact.path ? 'is-active' : ''}`} onClick={() => setComparePath((current) => (current === artifact.path ? '' : artifact.path))} aria-label={`Marcar ${artifact.path} para comparação`} title="Marcar como referência de comparação"><GitCompare size={14} /></button>
                      <a className="icon-button small" href={artifact.downloadUrl} download aria-label={`Baixar ${artifact.path}`} title="Baixar artefato"><Download size={14} /></a>
                    </div>
                  </article>
                ))}
                {!artifacts.length && !loading && <div className="documents-empty"><Binary size={23} /><strong>Nenhum artefato por aqui</strong><p>Envie um binário, pacote ou árvore JavaScript para começar.</p></div>}
                {loading && !artifacts.length && <div className="documents-empty"><LoaderCircle className="legal-spinner" size={22} /><p>Carregando artefatos...</p></div>}
              </div>
              <div className="documents-library-note"><ShieldAlert size={14} /><span>Arquivos ficam em <code>storage/user-files/reverse</code>. Nada é descompactado, importado ou executado.</span></div>
            </section>

            <section className="panel reverse-console">
              <div className="document-create-heading"><span><FileSearch size={21} /></span><div><span className="eyebrow">EVIDÊNCIAS ESTÁTICAS</span><h2>{selectedArtifact ? selectedArtifact.path.split('/').pop() : 'Selecione um artefato'}</h2><p>{selectedArtifact ? `${selectedArtifact.format} · ${bytesLabel(selectedArtifact.bytes)}` : 'Escolha um arquivo na biblioteca ou cole um código-fonte.'}</p></div></div>
              {selectedArtifact && (
                <>
                  <div className="reverse-selected-path"><code>{selectedArtifact.path}</code><a href={selectedArtifact.downloadUrl} download>Baixar <Download size={12} /></a></div>
                  <div className="reverse-actions">
                    <button className="button button-primary" onClick={() => analyze('reverse.inspect')} disabled={Boolean(busy)}>{busy === 'reverse.inspect' ? <LoaderCircle className="legal-spinner" size={15} /> : <Fingerprint size={15} />}Inspecionar</button>
                    <button className="button button-secondary" onClick={() => analyze('reverse.layout')} disabled={Boolean(busy)}>{busy === 'reverse.layout' ? <LoaderCircle className="legal-spinner" size={15} /> : <ListTree size={15} />}Layout</button>
                    <button className="button button-secondary" onClick={() => analyze('reverse.strings')} disabled={Boolean(busy)}>{busy === 'reverse.strings' ? <LoaderCircle className="legal-spinner" size={15} /> : <Braces size={15} />}Strings</button>
                    <button className="button button-secondary" onClick={() => analyze('reverse.entropy')} disabled={Boolean(busy)}>{busy === 'reverse.entropy' ? <LoaderCircle className="legal-spinner" size={15} /> : <Binary size={15} />}Entropia</button>
                    <button className="button button-secondary" onClick={() => analyze('reverse.javascript')} disabled={Boolean(busy)}>{busy === 'reverse.javascript' ? <LoaderCircle className="legal-spinner" size={15} /> : <Braces size={15} />}JavaScript</button>
                  </div>
                  <div className="reverse-tree-row">
                    <label className="field"><span>Analisar uma pasta inteira</span><input value={treePath} onChange={(event) => setTreePath(event.target.value)} maxLength={160} placeholder="ex.: app" /><small className="field-description">Use o caminho da pasta criada pelo envio em lote.</small></label>
                    <button className="button button-secondary" onClick={() => void run('reverse.javascript', { path: treePath.trim(), source: '', includeNodeModules: false, maxFiles: 500 })} disabled={!treePath.trim() || Boolean(busy)}>{busy === 'reverse.javascript' ? <LoaderCircle className="legal-spinner" size={15} /> : <Braces size={15} />}Analisar árvore</button>
                  </div>
                  <div className="reverse-compare-row">
                    <div><span>Comparar com</span><code>{comparePath || 'marque outro artefato com o ícone de comparação'}</code></div>
                    <button className="button button-ghost" onClick={compare} disabled={!comparePath || comparePath === selected || Boolean(busy)}>{busy === 'reverse.compare' ? <LoaderCircle className="legal-spinner" size={14} /> : <GitCompare size={14} />}Comparar</button>
                  </div>
                </>
              )}
              {!selectedArtifact && <p className="reverse-selection-note">A inspeção, o layout, as strings, a entropia e a análise JavaScript usam somente leitura. A comparação exige dois artefatos marcados.</p>}
              <form className="reverse-inline" onSubmit={analyzeInline}>
                <div className="compact-heading"><div><span className="eyebrow">SEM UPLOAD</span><h3>Analisar código colado</h3></div></div>
                <label className="field"><span>JavaScript ou TypeScript</span><textarea value={inlineSource} onChange={(event) => setInlineSource(event.target.value)} rows={7} maxLength={500000} placeholder="Cole um módulo para mapear imports, IPC, rotas e fatos de risco. Nada é executado." /><small className="field-description">Até 500.000 caracteres e 1 MB em UTF-8. A resolução de caminhos fica desativada no modo inline.</small></label>
                <button className="button button-secondary" type="submit" disabled={!inlineSource.trim() || Boolean(busy)}>{busy === 'reverse.javascript' ? <LoaderCircle className="legal-spinner" size={15} /> : <Braces size={15} />}Analisar código</button>
              </form>
              {requestError && <div className="execution-error">{requestError}</div>}
              <div className="reverse-scope"><ShieldCheck size={14} /><span>Somente leitura: parsers próprios em Python, sem shell, sem rede, sem MCP e sem executar o artefato.</span></div>
            </section>
          </div>

          <section className="panel reverse-result" ref={resultRef}>
            <div className="section-heading compact-heading"><div><span className="eyebrow">RESULTADO</span><h2>{result ? result.skillId : 'Nenhuma análise executada'}</h2></div>{result && <span className="reverse-readonly"><ShieldCheck size={13} /> executado: não</span>}</div>
            {!data && <div className="documents-empty"><FileSearch size={23} /><strong>Selecione uma análise</strong><p>O resultado mostra identidade SHA-256, fatos estruturais e limites declarados, sem alterar o arquivo.</p></div>}
            {data && data.analysis === 'inspect' && <InspectView result={data} />}
            {data && data.analysis === 'layout' && <LayoutView result={data} />}
            {data && data.analysis === 'strings' && <StringsView result={data} />}
            {data && data.analysis === 'entropy' && <EntropyView result={data} />}
            {data && data.analysis === 'javascript' && <JavaScriptView result={data} />}
            {data && data.analysis === 'compare' && <CompareView result={data} />}
            {data && !['inspect', 'layout', 'strings', 'entropy', 'javascript', 'compare'].includes(text(data.analysis)) && <JsonBlock label="Resposta (JSON)" value={data} />}
          </section>

          <div className="documents-more"><span>Também disponíveis: workflows de engenharia, planos persistentes e documentos locais.</span><Link to="/engenharia">Abrir Engenharia <ArrowRight size={13} /></Link></div>
        </>
      )}
    </div>
  );
}
