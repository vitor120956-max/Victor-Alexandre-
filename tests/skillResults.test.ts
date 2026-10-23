import { describe, expect, it } from 'vitest';
import { formatPythonChatResult } from '../src/lib/skillResults';

describe('resultados das novas skills na conversa', () => {
  it('lista arquivos reais sem afirmar que houve gravação', () => {
    const result = formatPythonChatResult('files.list', { files: [{ path: 'documentos/relatorio.pdf', bytes: 1200 }] });
    expect(result).toContain('documentos/relatorio.pdf');
    expect(result).toContain('Abra Documentos');
  });

  it('limita extrações longas e mantém a origem do documento', () => {
    const result = formatPythonChatResult('document.read', { path: 'ata.docx', format: 'docx', bytes: 100, text: 'x'.repeat(6500) });
    expect(result).toContain('ata.docx · DOCX');
    expect(result).toContain('Exibição limitada');
    expect(result.length).toBeLessThan(6800);
  });

  it('apresenta métricas de reunião com o aviso de análise textual', () => {
    const result = formatPythonChatResult('meeting.analyze', {
      words: 20, speakerCount: 1, questions: 1,
      speakers: [{ name: 'Ana', words: 20, fillerWords: 1, hedges: 0 }],
      actionItems: ['Eu fico responsável pelo relatório.'], decisions: [], notice: 'Análise textual; não diagnóstico.',
    });
    expect(result).toContain('Ana: 20 palavras');
    expect(result).toContain('Possíveis ações');
    expect(result).toContain('não diagnóstico');
  });

  it('deixa explícito que organização no chat é somente simulação', () => {
    const result = formatPythonChatResult('files.organize', { dryRun: true, moves: [{ from: 'nota.txt', to: 'documentos/nota.txt' }] });
    expect(result).toContain('Nenhum arquivo foi movido ou excluído');
    expect(result).toContain('nota.txt → documentos/nota.txt');
    expect(result).toContain('revise e confirme');
  });

  it('resume a decisão da escada sem afirmar leitura do repositório', () => {
    const result = formatPythonChatResult('lean.ladder', {
      decision: { rung: 3, label: 'Biblioteca padrão ou recurso nativo?', evidence: 'input type=date' },
      rungs: [{ label: 'Cortar o que ninguém pediu', status: 'cut' }, { label: 'Já existe no projeto?', status: 'partial' }],
      testObligation: { required: true }, warnings: ['Declare a evidência de dependency.'],
    });
    expect(result).toContain('degrau 3');
    expect(result).toContain('input type=date');
    expect(result).toContain('Teste obrigatório: sim');
    expect(result).toContain('nenhum arquivo do repositório foi lido');
  });

  it('resume achados de revisão e auditoria com o veredito', () => {
    const result = formatPythonChatResult('lean.review', {
      verdict: 'Corrija 1 e 2 primeiro.', counts: { must: 2, should: 1, nice: 0 },
      findings: [{ title: 'Possível remoção de validação', location: 'src/api.js:2' }],
    });
    expect(result).toContain('Corrija 1 e 2 primeiro.');
    expect(result).toContain('2 obrigatório(s)');
    expect(result).toContain('src/api.js:2');
    expect(result).toContain('Abra Enxuto');
  });

  it('lista dívida de atalhos e destaca os marcadores sem gatilho', () => {
    const result = formatPythonChatResult('lean.debt', {
      totals: { markers: 2, noTrigger: 1, files: 1 },
      rows: [
        { file: 'src/cache.js', line: 2, ceiling: 'cache em memória', noTrigger: false },
        { file: 'src/cache.js', line: 5, ceiling: 'sem retry', noTrigger: true },
      ],
    });
    expect(result).toContain('2 marcador(es)');
    expect(result).toContain('1 sem gatilho');
    expect(result).toContain('sem retry (no-trigger)');
  });

  it('apresenta o Markdown do workflow de engenharia sem trocar sua origem', () => {
    const result = formatPythonChatResult('engineering.webvitals', { markdown: '# Avaliação\n\nResultado geral: **Bom**.' });
    expect(result).toBe('# Avaliação\n\nResultado geral: **Bom**.');
  });

  it('lista planos sem escolher um automaticamente', () => {
    const result = formatPythonChatResult('planning.list', { plans: [{ planId: 'plano-a', title: 'Entrega', gate: { completePhases: 1, phaseCount: 2 } }] });
    expect(result).toContain('Nenhum foi selecionado automaticamente');
    expect(result).toContain('plano-a');
    expect(result).toContain('1/2 fases');
  });

  it('limita a recuperação aos arquivos do ID e apresenta o gate sem executar comandos', () => {
    const resumed = formatPythonChatResult('planning.resume', { markdown: '# Entrega\n\nPróximo passo: validar' });
    expect(resumed).toContain('Próximo passo: validar');
    expect(resumed).toContain('nenhum histórico de sessão');
    const gate = formatPythonChatResult('planning.gate', { markdown: 'INCOMPLETE\n\nNenhum comando foi executado.' });
    expect(gate).toContain('Nenhum comando foi executado');
  });

  it('apresenta evidências reversas com hash, contagens e ausência de execução', () => {
    const inspected = formatPythonChatResult('reverse.inspect', {
      identity: { path: 'app.asar', bytes: 2048, sha256: 'a'.repeat(64) },
      format: 'Electron ASAR',
      counts: { sections: 0, segments: 0, entries: 12, imports: 0 },
      entropy: { fileEntropy: 7.91 },
      topFindings: [{ severity: 'attention', message: 'Entrada com caminho inseguro.' }],
    });
    expect(inspected).toContain('app.asar');
    expect(inspected).toContain('a'.repeat(64));
    expect(inspected).toContain('Nada foi executado');
    expect(inspected).toContain('caminho inseguro');

    const javascript = formatPythonChatResult('reverse.javascript', {
      mode: 'tree',
      target: { path: 'app', files: 3, bytesRead: 900 },
      modules: [{ path: 'main.js' }],
      relationships: [{ from: 'main.js', to: 'helper.js' }],
      unresolved: [{ file: 'main.js', reason: 'dynamic-require' }],
      facts: [{ file: 'main.js', line: 4, category: 'electron.node-integration', severity: 'attention' }],
      entryCandidates: [{ path: 'main.js', reason: 'package.json main' }],
      coverage: { bytesRead: 900 },
    });
    expect(javascript).toContain('3 arquivos');
    expect(javascript).toContain('main.js:4 electron.node-integration');
    expect(javascript).toContain('sem AST');

    const compared = formatPythonChatResult('reverse.compare', {
      left: { path: 'antes.bin' }, right: { path: 'depois.bin' },
      identical: false, sizeDelta: 4, comparable: true,
      strings: { addedCount: 2, removedCount: 1 },
    });
    expect(compared).toContain('antes.bin ↔ depois.bin');
    expect(compared).toContain('2 adicionadas');
    expect(compared).toContain('não provam mudança de comportamento');
  });

  it('mostra os sorteados e o método de aleatoriedade', () => {
    const result = formatPythonChatResult('random.pick', { winners: ['Ana', 'Bruno'], eligible: 3, method: 'secrets.SystemRandom' });
    expect(result).toContain('1. Ana');
    expect(result).toContain('2. Bruno');
    expect(result).toContain('secrets.SystemRandom');
  });
});
