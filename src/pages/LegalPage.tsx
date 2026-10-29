import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  ExternalLink,
  FileSearch,
  FileText,
  Info,
  Landmark,
  LoaderCircle,
  RefreshCw,
  Scale,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { Modal } from '../components/Modal';
import { useApp } from '../context/AppContext';
import type { LegalArticleResult, LegalSearchResult, LegalSourcesResult } from '../lib/api';
import { classNames } from '../lib/utils';

type LegalMode = 'search' | 'article';

const topicSuggestions = [
  'Direito de arrependimento',
  'Proteção de dados pessoais',
  'Liberdade de expressão',
  'Trabalho infantil',
];

function ArticleContent({ article }: { article: LegalArticleResult }) {
  return (
    <div className="legal-article-content">
      <div className="legal-article-provenance">
        <span><FileText size={14} /> Texto do corpus local</span>
        {article.truncated && <span className="legal-truncated">Trecho limitado · use a fonte oficial</span>}
      </div>
      <div className="legal-article-text">{article.text}</div>
      <footer className="legal-article-footer">
        <p><Info size={15} />{article.notice}</p>
        <a className="button button-secondary" href={article.source} target="_blank" rel="noreferrer noopener">
          Conferir fonte oficial <ExternalLink size={14} />
        </a>
      </footer>
    </div>
  );
}

export function LegalPage() {
  const { backendOnline, executeSkill } = useApp();
  const [mode, setMode] = useState<LegalMode>('search');
  const [sources, setSources] = useState<LegalSourcesResult | null>(null);
  const [sourcesError, setSourcesError] = useState('');
  const [loadingSources, setLoadingSources] = useState(false);
  const sourcesRequested = useRef(false);

  const [query, setQuery] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [searchResult, setSearchResult] = useState<LegalSearchResult | null>(null);
  const [searchError, setSearchError] = useState('');
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const [articleDocument, setArticleDocument] = useState('constituicao');
  const [articleNumber, setArticleNumber] = useState('5');
  const [articleResult, setArticleResult] = useState<LegalArticleResult | null>(null);
  const [articleError, setArticleError] = useState('');
  const [loadingArticle, setLoadingArticle] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<LegalArticleResult | null>(null);

  const loadSources = useCallback(async () => {
    if (!backendOnline || sourcesRequested.current) return;
    sourcesRequested.current = true;
    setLoadingSources(true);
    setSourcesError('');
    try {
      const response = await executeSkill('legal.sources', {});
      if (response.ok && response.result) {
        setSources(response.result as unknown as LegalSourcesResult);
      } else {
        setSourcesError(response.error?.message ?? 'Não foi possível carregar as fontes.');
        sourcesRequested.current = false;
      }
    } catch (error) {
      setSourcesError(error instanceof Error ? error.message : 'Falha ao carregar as fontes.');
      sourcesRequested.current = false;
    } finally {
      setLoadingSources(false);
    }
  }, [backendOnline, executeSkill]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const retrySources = () => {
    sourcesRequested.current = false;
    void loadSources();
  };

  const runSearch = async (requestedQuery = query) => {
    const cleanQuery = requestedQuery.trim();
    if (cleanQuery.length < 2 || searching || loadingArticle || !backendOnline) return;
    setMode('search');
    setQuery(cleanQuery);
    setSearching(true);
    setHasSearched(true);
    setSearchResult(null);
    setSearchError('');
    try {
      const response = await executeSkill('legal.search', { query: cleanQuery, documentId, limit: 8 });
      if (response.ok && response.result) {
        setSearchResult(response.result as unknown as LegalSearchResult);
      } else {
        setSearchError(response.error?.message ?? 'A pesquisa não pôde ser concluída.');
      }
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : 'Falha ao pesquisar o corpus.');
    } finally {
      setSearching(false);
    }
  };

  const runArticle = async (requestedDocument = articleDocument, requestedArticle = articleNumber) => {
    const cleanArticle = requestedArticle.trim();
    if (!cleanArticle || searching || loadingArticle || !backendOnline) return;
    setMode('article');
    setArticleDocument(requestedDocument);
    setArticleNumber(cleanArticle);
    setLoadingArticle(true);
    setArticleResult(null);
    setArticleError('');
    try {
      const response = await executeSkill('legal.article', { documentId: requestedDocument, article: cleanArticle });
      if (response.ok && response.result) {
        setArticleResult(response.result as unknown as LegalArticleResult);
      } else {
        setArticleError(response.error?.message ?? 'O artigo não pôde ser consultado.');
      }
    } catch (error) {
      setArticleError(error instanceof Error ? error.message : 'Falha ao consultar o artigo.');
    } finally {
      setLoadingArticle(false);
    }
  };

  const openArticleExample = (document: string, article: string) => {
    setMode('article');
    setArticleDocument(document);
    setArticleNumber(article);
  };

  const busy = searching || loadingArticle;

  return (
    <div className="legal-page">
      <header className="page-heading">
        <div><span className="eyebrow">CONHECIMENTO VERIFICÁVEL</span><h1>Legislação<span>.</span></h1><p>Consulte normas brasileiras pelo texto, com origem e fonte oficial.</p></div>
        <span className="local-badge"><Scale size={12} /> {sources ? `${sources.documentCount} NORMAS · ${sources.articleCount.toLocaleString('pt-BR')} ARTIGOS` : 'CORPUS LOCAL'}</span>
      </header>

      <section className="panel legal-search-panel">
        <div className="legal-search-intro">
          <span className="legal-hero-icon"><Landmark size={25} /></span>
          <div><span className="eyebrow">RECORTE INSPIRADO EM CTRESB/LEIS</span><h2>Encontre o dispositivo. Leia a fonte.</h2><p>Busca lexical nos textos locais, sem IA criando artigos ou referências.</p></div>
        </div>
        <div className="legal-mode-tabs" role="tablist" aria-label="Modo de consulta jurídica">
          <button type="button" role="tab" aria-selected={mode === 'search'} className={classNames(mode === 'search' && 'active')} onClick={() => setMode('search')}><Search size={15} /> Buscar por tema</button>
          <button type="button" role="tab" aria-selected={mode === 'article'} className={classNames(mode === 'article' && 'active')} onClick={() => setMode('article')}><BookOpen size={15} /> Consultar artigo</button>
        </div>
        {mode === 'search' ? (
          <form className="legal-search-form" onSubmit={(event) => { event.preventDefault(); void runSearch(); }}>
            <label className="legal-query-field"><Search size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ex.: direito de arrependimento" minLength={2} maxLength={240} required aria-label="Tema jurídico" /></label>
            <select value={documentId} onChange={(event) => setDocumentId(event.target.value)} aria-label="Filtrar documento da pesquisa">
              <option value="">Todos os documentos</option>
              {sources?.documents.map((document) => <option key={document.id} value={document.id}>{document.shortTitle}</option>)}
            </select>
            <button className="button button-primary" disabled={!backendOnline || busy || query.trim().length < 2}>{searching ? <LoaderCircle className="legal-spinner" size={16} /> : <Search size={16} />}{searching ? 'Pesquisando...' : 'Pesquisar'}</button>
          </form>
        ) : (
          <form className="legal-article-form" onSubmit={(event) => { event.preventDefault(); void runArticle(); }}>
            <label><span>Documento</span><select value={articleDocument} onChange={(event) => setArticleDocument(event.target.value)} disabled={!sources} required>
              {sources?.documents.map((document) => <option key={document.id} value={document.id}>{document.shortTitle}</option>)}
              {!sources && <option value="constituicao">Constituição Federal</option>}
            </select></label>
            <label><span>Número do artigo</span><input value={articleNumber} onChange={(event) => setArticleNumber(event.target.value)} placeholder="Ex.: 5, 49 ou 1.046" maxLength={24} required /></label>
            <button className="button button-primary" disabled={!backendOnline || busy || !articleNumber.trim()}>{loadingArticle ? <LoaderCircle className="legal-spinner" size={16} /> : <BookOpen size={16} />}{loadingArticle ? 'Consultando...' : 'Ler artigo'}</button>
          </form>
        )}
        {mode === 'search' && <div className="legal-topic-suggestions"><span>SUGESTÕES</span>{topicSuggestions.map((topic) => <button type="button" key={topic} disabled={!backendOnline || busy} onClick={() => void runSearch(topic)}>{topic}</button>)}</div>}
        {mode === 'article' && <div className="legal-topic-suggestions"><span>EXEMPLOS</span><button type="button" onClick={() => openArticleExample('constituicao', '5')}>Art. 5º · Constituição</button><button type="button" onClick={() => openArticleExample('cdc', '49')}>Art. 49 · CDC</button><button type="button" onClick={() => openArticleExample('lgpd', '18')}>Art. 18 · LGPD</button></div>}
      </section>

      {!backendOnline ? (
        <div className="legal-offline panel"><span><Scale size={25} /></span><div><h2>Corpus jurídico indisponível offline</h2><p>A página não usa dados simulados. Inicie a API Python com <code>.venv\Scripts\python iniciar.py</code> para consultar os textos locais.</p></div></div>
      ) : (
        <div className="legal-workspace">
          <main className="legal-results" aria-live="polite" aria-busy={busy}>
            {mode === 'search' && (
              <>
                {searching && <div className="legal-loading panel"><LoaderCircle className="legal-spinner" size={23} /><span>Pesquisando os artigos do recorte...</span></div>}
                {searchError && <div className="legal-error panel"><Info size={19} /><div><strong>Consulta não concluída</strong><p>{searchError}</p></div></div>}
                {!searching && !searchError && searchResult && (
                  <>
                    <div className="legal-results-heading"><div><span className="eyebrow">RESULTADO DA BUSCA LEXICAL</span><h2>{searchResult.resultCount} {searchResult.resultCount === 1 ? 'trecho encontrado' : 'trechos encontrados'}</h2><p>“{searchResult.query}” · {searchResult.searchedDocuments} {searchResult.searchedDocuments === 1 ? 'documento consultado' : 'documentos consultados'}</p></div><span>{searchResult.returned} exibidos</span></div>
                    {searchResult.results.length > 0 ? <div className="legal-result-list">{searchResult.results.map((item, index) => (
                      <article className="panel legal-result-card" key={`${item.documentId}-${item.articleNumber}-${index}`}>
                        <div className="legal-result-top"><span>{item.documentShortTitle}</span><strong>{item.article}</strong></div>
                        <p>{item.snippet}</p>
                        <footer><a href={item.source} target="_blank" rel="noreferrer noopener">Fonte oficial <ExternalLink size={13} /></a><button className="text-link" onClick={() => setSelectedArticle(item)}>Ler artigo <ArrowRight size={14} /></button></footer>
                      </article>
                    ))}</div> : <div className="empty-state panel legal-empty"><span><FileSearch size={25} /></span><h3>Nenhum trecho encontrado</h3><p>Tente menos palavras, outro termo ou remova o filtro de documento.</p></div>}
                  </>
                )}
                {!hasSearched && !searching && <div className="empty-state panel legal-empty legal-initial"><span><FileSearch size={27} /></span><h3>O que você quer encontrar?</h3><p>Pesquise um tema ou escolha uma sugestão acima. Os resultados vêm diretamente dos artigos do corpus.</p></div>}
              </>
            )}
            {mode === 'article' && (
              <>
                {loadingArticle && <div className="legal-loading panel"><LoaderCircle className="legal-spinner" size={23} /><span>Localizando o artigo exato...</span></div>}
                {articleError && <div className="legal-error panel"><Info size={19} /><div><strong>Artigo não localizado</strong><p>{articleError}</p></div></div>}
                {!loadingArticle && !articleError && articleResult && <section className="panel legal-exact-result"><div className="legal-results-heading"><div><span className="eyebrow">CONSULTA EXATA</span><h2>{articleResult.article}</h2><p>{articleResult.documentShortTitle}</p></div><Scale size={20} /></div><ArticleContent article={articleResult} /></section>}
                {!loadingArticle && !articleError && !articleResult && <div className="empty-state panel legal-empty legal-initial"><span><BookOpen size={27} /></span><h3>Consulte um artigo pelo número</h3><p>Selecione o documento e informe o número. Você também pode usar “artigo 49 do CDC” na conversa.</p></div>}
              </>
            )}
          </main>

          <aside className="legal-aside">
            <section className="panel legal-sources-card">
              <div className="section-heading compact-heading"><div><span className="eyebrow">ACERVO DESTE RECORTE</span><h2>Documentos e fontes</h2></div>{loadingSources && <LoaderCircle className="legal-spinner" size={15} />}</div>
              {sourcesError && <div className="legal-sources-error"><p>{sourcesError}</p><button className="text-link" onClick={retrySources}><RefreshCw size={13} /> Tentar novamente</button></div>}
              {sources && <><div className="legal-source-list">{sources.documents.map((document) => <div className="legal-source-item" key={document.id}><div><strong>{document.shortTitle}</strong><span>{document.articleCount.toLocaleString('pt-BR')} artigos</span></div><a href={document.source} target="_blank" rel="noreferrer noopener" aria-label={`Abrir fonte oficial: ${document.shortTitle}`} title="Fonte oficial"><ExternalLink size={14} /></a></div>)}</div><a className="legal-upstream" href={`${sources.upstream.url}/tree/${sources.upstream.commit}`} target="_blank" rel="noreferrer noopener"><span>Origem: {sources.upstream.repository}</span><small>commit {sources.upstream.commit.slice(0, 8)}</small><ExternalLink size={12} /></a></>}
              {!sources && !sourcesError && !loadingSources && <p className="muted">Carregando catálogo...</p>}
            </section>
            <section className="panel legal-method-card"><span className="eyebrow">COMO FUNCIONA</span><div><ShieldCheck size={17} /><p><strong>Referências sem IA</strong>O texto e os links vêm do corpus, não de uma resposta generativa.</p></div><div><Search size={17} /><p><strong>Busca lexical</strong>Termos próximos e sinônimos pontuais ajudam no ranking; não há interpretação jurídica.</p></div><div><Info size={17} /><p><strong>Confira a vigência</strong>Conversões podem conter falhas. Use a fonte oficial antes de tomar decisões.</p></div></section>
          </aside>
        </div>
      )}

      <Modal open={Boolean(selectedArticle)} onClose={() => setSelectedArticle(null)} title={selectedArticle ? `${selectedArticle.documentShortTitle} — ${selectedArticle.article}` : ''} eyebrow="LEITURA DO ARTIGO" className="legal-reader-modal">
        {selectedArticle && <ArticleContent article={selectedArticle} />}
      </Modal>
    </div>
  );
}
