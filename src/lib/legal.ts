import type { LegalArticleResult, LegalSearchResult, LegalSourcesResult } from './api';

function notice(value: unknown): string {
  return typeof value === 'string' ? value : 'Conteúdo informativo. Confirme o texto e a vigência na fonte oficial.';
}

export function formatLegalChatResult(skillId: string, result: Record<string, unknown>): string {
  const legalNotice = notice(result.notice);
  if (skillId === 'legal.sources') {
    const sources = result as unknown as LegalSourcesResult;
    const documents = sources.documents.map((document) => `• ${document.shortTitle} — ${document.articleCount} artigos`).join('\n');
    return [
      `O corpus local reúne ${sources.documentCount} normas e ${sources.articleCount.toLocaleString('pt-BR')} artigos:`,
      documents,
      'Abra a página Legislação para pesquisar e acessar os links oficiais.',
      legalNotice,
    ].join('\n\n');
  }
  if (skillId === 'legal.article') {
    const article = result as unknown as LegalArticleResult;
    const text = article.text.length > 6_000
      ? `${article.text.slice(0, 6_000)}\n\n[Exibição da conversa limitada. Abra a página Legislação para continuar a leitura.]`
      : article.text;
    return [
      `${article.documentShortTitle} — ${article.article}`,
      text,
      `Fonte oficial: ${article.source}`,
      legalNotice,
    ].join('\n\n');
  }
  const search = result as unknown as LegalSearchResult;
  if (!search.results.length) {
    return `Não encontrei “${search.query}” nos ${search.searchedDocuments} documentos consultados. Tente outras palavras ou pesquise sem filtrar o documento.\n\n${legalNotice}`;
  }
  const items = search.results.slice(0, 3).map((item, index) => [
    `${index + 1}. ${item.documentShortTitle} — ${item.article}`,
    item.snippet,
    `Fonte: ${item.source}`,
  ].join('\n')).join('\n\n');
  return [
    `Encontrei ${search.resultCount} ${search.resultCount === 1 ? 'trecho' : 'trechos'} para “${search.query}”. Estes são os primeiros resultados da busca lexical:`,
    items,
    'Abra a página Legislação para ler os artigos completos.',
    legalNotice,
  ].join('\n\n');
}
