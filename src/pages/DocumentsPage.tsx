import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  Check,
  Download,
  Eye,
  FilePlus2,
  FileText,
  FolderLock,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { uploadUserFile } from '../lib/api';
import type { DocumentReadResult, UploadedFile, WorkspaceFile } from '../lib/api';

const ACCEPTED = '.txt,.md,.json,.csv,.log,.docx,.xlsx,.pptx,.pdf';
const DOCUMENT_EXTENSIONS = ['docx', 'xlsx', 'pptx', 'pdf'];
const MAX_FILE_BYTES = 25_000_000;

type DocumentFormat = 'docx' | 'xlsx' | 'pptx' | 'pdf';

interface ViewerState {
  path: string;
  format: string;
  text: string;
  bytes: number;
  downloadUrl: string;
  details: string[];
  truncated: boolean;
}

const placeholders: Record<DocumentFormat, string> = {
  docx: '# Resumo executivo\nEscreva o conteúdo aqui.\n- Primeiro ponto\n- Segundo ponto',
  xlsx: 'Nome;Quantidade;Situação\nAna;10;Ativo\nBruno;20;Pendente',
  pptx: 'Título do primeiro slide\n- Primeiro ponto\n- Segundo ponto\n---\nTítulo do segundo slide\n- Encerramento',
  pdf: '# Resumo executivo\nEscreva o conteúdo aqui.\n- Primeiro ponto\n- Segundo ponto',
};

function bytesLabel(bytes: number): string {
  if (bytes < 1_000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function extension(path: string): string {
  return path.split('.').pop()?.toLowerCase() ?? '';
}

export function DocumentsPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [filesError, setFilesError] = useState('');
  const [loadingFiles, setLoadingFiles] = useState(false);
  const filesRequest = useRef(false);

  const [selectedUpload, setSelectedUpload] = useState<File | null>(null);
  const [uploadDirectory, setUploadDirectory] = useState('uploads');
  const [uploadOverwrite, setUploadOverwrite] = useState(false);
  const [uploadConfirmed, setUploadConfirmed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const uploadInput = useRef<HTMLInputElement>(null);

  const [format, setFormat] = useState<DocumentFormat>('docx');
  const [path, setPath] = useState('documentos/relatorio.docx');
  const [title, setTitle] = useState('Relatório JARVIS');
  const [content, setContent] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [createConfirmed, setCreateConfirmed] = useState(false);
  const [createBusy, setCreateBusy] = useState<'dry' | 'write' | null>(null);
  const [createError, setCreateError] = useState('');
  const [createdDownload, setCreatedDownload] = useState<Record<string, unknown> | null>(null);

  const [viewer, setViewer] = useState<ViewerState | null>(null);
  const [readingPath, setReadingPath] = useState('');
  const [readError, setReadError] = useState('');

  const loadFiles = useCallback(async () => {
    if (!backendOnline || filesRequest.current) return;
    filesRequest.current = true;
    setLoadingFiles(true);
    setFilesError('');
    try {
      const response = await executeSkill('files.list', {});
      if (response.ok && response.result) {
        setFiles((response.result.files as unknown as WorkspaceFile[]) ?? []);
      } else {
        setFilesError(response.error?.message ?? 'Não foi possível listar os documentos.');
      }
    } catch (error) {
      setFilesError(error instanceof Error ? error.message : 'Falha ao listar documentos.');
    } finally {
      filesRequest.current = false;
      setLoadingFiles(false);
    }
  }, [backendOnline, executeSkill]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const invalidatePlan = () => {
    setPlan(null);
    setCreateConfirmed(false);
    setCreatedDownload(null);
  };

  const changeFormat = (next: DocumentFormat) => {
    setFormat(next);
    setPath((current) => current.replace(/\.(docx|xlsx|pptx|pdf)$/i, `.${next}`));
    invalidatePlan();
  };

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedUpload || uploading || !uploadConfirmed || !backendOnline) return;
    if (selectedUpload.size > MAX_FILE_BYTES) {
      setUploadError('O arquivo excede o limite de 25 MB.');
      return;
    }
    setUploading(true);
    setUploadError('');
    try {
      const result: UploadedFile = await uploadUserFile({ file: selectedUpload, directory: uploadDirectory, overwrite: uploadOverwrite, confirmed: true });
      pushToast('Upload concluído', `${result.path} · ${bytesLabel(result.bytes)}`);
      setSelectedUpload(null);
      setUploadConfirmed(false);
      if (uploadInput.current) uploadInput.current.value = '';
      await loadFiles();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Falha no upload.');
    } finally {
      setUploading(false);
    }
  };

  const validateCreation = async () => {
    if (createBusy || !backendOnline || !content.trim() || !title.trim() || !path.trim()) return;
    setCreateBusy('dry');
    setCreateError('');
    setPlan(null);
    setCreateConfirmed(false);
    setCreatedDownload(null);
    try {
      const response = await executeSkill('document.create', { format, path, title, content, overwrite }, { dryRun: true });
      if (response.ok && response.result) setPlan(response.result);
      else setCreateError(response.error?.message ?? 'A criação foi recusada.');
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Falha ao validar o documento.');
    } finally {
      setCreateBusy(null);
    }
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!plan || !createConfirmed || createBusy || !backendOnline) return;
    setCreateBusy('write');
    setCreateError('');
    try {
      const response = await executeSkill('document.create', { format, path, title, content, overwrite }, { confirmed: true });
      if (response.ok && response.result) {
        setCreatedDownload(response.result);
        pushToast('Documento criado', String(response.result.written ?? path));
        setPlan(null);
        setCreateConfirmed(false);
        await loadFiles();
      } else {
        setCreateError(response.error?.message ?? 'A criação foi recusada.');
      }
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Falha ao criar documento.');
    } finally {
      setCreateBusy(null);
    }
  };

  const read = async (file: WorkspaceFile) => {
    if (readingPath || !backendOnline) return;
    setReadingPath(file.path);
    setReadError('');
    setViewer(null);
    try {
      const isOffice = DOCUMENT_EXTENSIONS.includes(extension(file.path));
      const response = await executeSkill(isOffice ? 'document.read' : 'files.read', { path: file.path });
      if (!response.ok || !response.result) {
        setReadError(response.error?.message ?? 'Não foi possível ler o arquivo.');
        return;
      }
      const result = response.result as unknown as DocumentReadResult & { content?: string };
      setViewer({
        path: file.path,
        format: extension(file.path),
        text: String(isOffice ? result.text : result.content ?? ''),
        bytes: result.bytes,
        downloadUrl: isOffice ? result.downloadUrl : file.downloadUrl,
        details: [
          result.pages !== undefined ? `${result.pages} páginas` : '',
          result.slides !== undefined ? `${result.slides} slides` : '',
          result.sheets !== undefined ? `${result.sheets} planilhas` : '',
          result.tables !== undefined ? `${result.tables} tabelas` : '',
        ].filter(Boolean),
        truncated: Boolean(result.truncated),
      });
    } catch (error) {
      setReadError(error instanceof Error ? error.message : 'Falha ao ler o documento.');
    } finally {
      setReadingPath('');
    }
  };

  const busy = uploading || Boolean(createBusy) || Boolean(readingPath);

  return (
    <div className="documents-page">
      <header className="page-heading">
        <div><span className="eyebrow">ARQUIVOS LOCAIS E DOCUMENTOS</span><h1>Documentos<span>.</span></h1><p>Crie, leia e baixe arquivos em uma área isolada do JARVIS.</p></div>
        <span className="local-badge"><FolderLock size={12} /> {files.length} {files.length === 1 ? 'ARQUIVO' : 'ARQUIVOS'} · MÁX. 25 MB</span>
      </header>

      {!backendOnline ? (
        <div className="legal-offline panel"><span><FileText size={25} /></span><div><h2>Área de documentos indisponível offline</h2><p>Inicie a API Python com <code>.venv\Scripts\python iniciar.py</code>. Nenhum arquivo será simulado ou enviado à IA.</p></div></div>
      ) : (
        <>
          <div className="documents-layout">
            <section className="panel documents-library">
              <div className="section-heading compact-heading"><div><span className="eyebrow">ÁREA CONFINADA</span><h2>Biblioteca local</h2></div><button className="icon-button small" onClick={() => void loadFiles()} disabled={loadingFiles} aria-label="Atualizar biblioteca"><RefreshCw size={14} className={loadingFiles ? 'legal-spinner' : ''} /></button></div>
              <form className="document-upload" onSubmit={upload}>
                <label className="document-file-picker"><Upload size={16} /><span>{selectedUpload ? selectedUpload.name : 'Escolher arquivo para upload'}</span><input ref={uploadInput} type="file" accept={ACCEPTED} onChange={(event) => { setSelectedUpload(event.target.files?.[0] ?? null); setUploadConfirmed(false); setUploadError(''); }} /></label>
                {selectedUpload && <div className="document-upload-details"><span>{bytesLabel(selectedUpload.size)}</span><label>Destino<input value={uploadDirectory} onChange={(event) => setUploadDirectory(event.target.value)} maxLength={120} required /></label></div>}
                {selectedUpload && <><label className="document-check"><input type="checkbox" checked={uploadOverwrite} onChange={(event) => setUploadOverwrite(event.target.checked)} /><span>Permitir sobrescrever</span></label><label className="document-check confirmation"><input type="checkbox" checked={uploadConfirmed} onChange={(event) => setUploadConfirmed(event.target.checked)} /><span>Confirmo a gravação deste arquivo na área isolada.</span></label></>}
                {uploadError && <p className="document-form-error">{uploadError}</p>}
                <button className="button button-secondary" disabled={!selectedUpload || !uploadConfirmed || busy || selectedUpload.size > MAX_FILE_BYTES}>{uploading ? <LoaderCircle className="legal-spinner" size={15} /> : <Upload size={15} />}{uploading ? 'Enviando...' : 'Confirmar upload'}</button>
              </form>
              {filesError && <div className="document-form-error">{filesError}</div>}
              <div className="document-file-list" aria-live="polite">
                {files.map((file) => <article className="document-file-item" key={file.path}>
                  <button className="document-file-main" onClick={() => void read(file)} disabled={busy}><span className="document-extension">{extension(file.path)}</span><span><strong>{file.path.split('/').pop()}</strong><small>{file.path} · {bytesLabel(file.bytes)}</small></span></button>
                  <div className="document-file-actions"><button className="icon-button small" onClick={() => void read(file)} disabled={busy} aria-label={`Ler ${file.path}`} title="Ler arquivo">{readingPath === file.path ? <LoaderCircle className="legal-spinner" size={14} /> : <Eye size={14} />}</button><a className="icon-button small" href={file.downloadUrl} download aria-label={`Baixar ${file.path}`} title="Baixar arquivo"><Download size={14} /></a></div>
                </article>)}
                {!files.length && !loadingFiles && <div className="documents-empty"><HardDrive size={23} /><strong>Nenhum arquivo por aqui</strong><p>Envie um documento ou crie um novo ao lado.</p></div>}
                {loadingFiles && !files.length && <div className="documents-empty"><LoaderCircle className="legal-spinner" size={22} /><p>Carregando biblioteca...</p></div>}
              </div>
              <div className="documents-library-note"><ShieldCheck size={14} /><span>DOCX, XLSX, PPTX, PDF e textos permitidos. Sem shell ou execução de macros.</span></div>
            </section>

            <section className="panel document-create-panel">
              <div className="document-create-heading"><span><FilePlus2 size={21} /></span><div><span className="eyebrow">CRIAÇÃO CONFIRMADA</span><h2>Novo documento</h2><p>Conteúdo estruturado, gerado localmente sem IA.</p></div></div>
              <form onSubmit={create} className="document-create-form">
                <div className="document-form-row"><label className="field"><span>Formato</span><select value={format} onChange={(event) => changeFormat(event.target.value as DocumentFormat)}><option value="docx">Word (DOCX)</option><option value="xlsx">Planilha (XLSX)</option><option value="pptx">Apresentação (PPTX)</option><option value="pdf">PDF</option></select></label><label className="field document-title-field"><span>Título</span><input value={title} onChange={(event) => { setTitle(event.target.value); invalidatePlan(); }} maxLength={200} required /></label></div>
                <label className="field"><span>Destino na área isolada</span><input value={path} onChange={(event) => { setPath(event.target.value); invalidatePlan(); }} maxLength={160} required /><small className="field-description">A extensão precisa corresponder ao formato escolhido.</small></label>
                <label className="field"><span>Conteúdo</span><textarea value={content} onChange={(event) => { setContent(event.target.value); invalidatePlan(); }} placeholder={placeholders[format]} rows={11} maxLength={100000} required /><small className="field-description">{format === 'xlsx' ? 'Use CSV ou ponto e vírgula. Valores são gravados como texto, não fórmulas.' : format === 'pptx' ? 'Primeira linha: título do slide. Demais linhas: tópicos. Separe slides por ---.' : 'Use # para seções e - para listas. O texto não é interpretado como HTML.'}</small></label>
                <label className="document-check"><input type="checkbox" checked={overwrite} onChange={(event) => { setOverwrite(event.target.checked); invalidatePlan(); }} /><span>Permitir sobrescrever um arquivo existente</span></label>
                {createError && <p className="document-form-error">{createError}</p>}
                {plan && <div className="document-plan"><Check size={16} /><div><strong>Simulação aprovada. Nada foi gravado.</strong><p>Destino: {String(plan.wouldWrite ?? path)}{plan.overwrite ? ' · sobrescrita autorizada' : ''}</p></div></div>}
                {createdDownload && <div className="document-created"><Check size={16} /><span>Documento criado e disponível na biblioteca.</span><a href={String(createdDownload.downloadUrl)} download>Baixar <Download size={13} /></a></div>}
                {plan && <label className="document-check confirmation"><input type="checkbox" checked={createConfirmed} onChange={(event) => setCreateConfirmed(event.target.checked)} /><span>Revisei a simulação e confirmo a gravação.</span></label>}
                <div className="document-create-actions"><button type="button" className="button button-secondary" onClick={() => void validateCreation()} disabled={busy || !content.trim() || !title.trim() || !path.trim()}>{createBusy === 'dry' ? <LoaderCircle className="legal-spinner" size={15} /> : <ShieldCheck size={15} />}{createBusy === 'dry' ? 'Validando...' : 'Validar criação'}</button><button type="submit" className="button button-primary" disabled={!plan || !createConfirmed || busy}>{createBusy === 'write' ? <LoaderCircle className="legal-spinner" size={15} /> : <FilePlus2 size={15} />}{createBusy === 'write' ? 'Criando...' : 'Criar documento'}</button></div>
              </form>
            </section>
          </div>

          {(viewer || readError) && <section className="panel document-viewer">
            <div className="document-viewer-heading"><div><span className="eyebrow">LEITURA LOCAL</span><h2>{viewer?.path ?? 'Não foi possível ler o arquivo'}</h2>{viewer && <p>{viewer.format.toUpperCase()} · {bytesLabel(viewer.bytes)}{viewer.details.length ? ` · ${viewer.details.join(' · ')}` : ''}</p>}</div>{viewer && <a className="button button-secondary" href={viewer.downloadUrl} download><Download size={14} /> Baixar</a>}</div>
            {readError && <p className="document-form-error">{readError}</p>}
            {viewer && <>{viewer.truncated && <p className="document-truncated">Extração limitada a 100.000 caracteres. Baixe o arquivo para ler tudo.</p>}<div className="document-viewer-text">{viewer.text}</div><footer><BookOpen size={14} /><span>Texto extraído localmente. O arquivo original permanece disponível para download.</span><button className="text-link" onClick={() => setViewer(null)}>Fechar leitura <ArrowRight size={13} /></button></footer></>}
          </section>}
          <div className="documents-more"><span>Também disponíveis: mesclar PDFs, organizar arquivos, analisar reuniões, changelogs e sorteios.</span><Link to="/skills">Abrir todas as skills <ArrowRight size={13} /></Link></div>
        </>
      )}
    </div>
  );
}
