import { describe, expect, it } from 'vitest';
import { formatLegalChatResult } from '../src/lib/legal';

const article = {
  documentId: 'cdc',
  documentTitle: 'Lei nº 8.078',
  documentShortTitle: 'Código de Defesa do Consumidor',
  article: 'Art. 49.',
  articleNumber: '49',
  text: 'Art. 49. O consumidor pode desistir do contrato, no prazo de 7 dias.',
  snippet: 'O consumidor pode desistir do contrato.',
  source: 'https://normas.leg.br/?urn=exemplo',
  truncated: false,
  notice: 'Conteúdo informativo. Confirme a fonte oficial.',
};

describe('respostas jurídicas na conversa', () => {
  it('usa o texto do artigo e inclui fonte e aviso', () => {
    const response = formatLegalChatResult('legal.article', article);
    expect(response).toContain('Art. 49. O consumidor pode desistir');
    expect(response).toContain(article.source);
    expect(response).toContain(article.notice);
  });

  it('sinaliza quando a exibição de um artigo longo é limitada', () => {
    const response = formatLegalChatResult('legal.article', { ...article, text: `Art. 49. ${'x'.repeat(6_100)}` });
    expect(response).toContain('Exibição da conversa limitada');
    expect(response).toContain('página Legislação');
  });

  it('não inventa resultado quando a busca é vazia', () => {
    const response = formatLegalChatResult('legal.search', {
      query: 'termo inexistente', results: [], resultCount: 0, returned: 0, searchedDocuments: 8,
      notice: article.notice,
    });
    expect(response).toContain('Não encontrei');
    expect(response).toContain('termo inexistente');
    expect(response).not.toContain('Art. 49.');
  });

  it('apresenta resultados lexicais com suas fontes', () => {
    const response = formatLegalChatResult('legal.search', {
      query: 'arrependimento', results: [{ ...article, score: 50 }], resultCount: 1, returned: 1,
      searchedDocuments: 1, notice: article.notice,
    });
    expect(response).toContain('busca lexical');
    expect(response).toContain('Código de Defesa do Consumidor — Art. 49.');
    expect(response).toContain(article.source);
  });
});
