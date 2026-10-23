import { describe, expect, it } from 'vitest';
import { parseCommand } from '../src/lib/jarvisEngine';

describe('roteador de comandos do JARVIS', () => {
  it('reconhece tarefas com prioridade e amanhã', () => {
    const result = parseCommand('Criar tarefa revisar proposta para amanhã com prioridade alta');
    expect(result.type).toBe('task:add');
    if (result.type === 'task:add') {
      expect(result.title).toBe('revisar proposta');
      expect(result.priority).toBe('alta');
    }
  });

  it('diferencia notas, foco e cálculo', () => {
    expect(parseCommand('Anotar que a reunião mudou').type).toBe('note:add');
    expect(parseCommand('iniciar foco de 50 minutos')).toEqual({ type: 'focus:start', minutes: 50 });
    expect(parseCommand('quanto é 8 * 7?')).toEqual({ type: 'calculate', expression: '8 * 7' });
  });

  it('limita a duração do foco e entende destinos conhecidos', () => {
    expect(parseCommand('iniciar foco de 900 minutos')).toEqual({ type: 'focus:start', minutes: 180 });
    expect(parseCommand('abrir github')).toMatchObject({ type: 'web:open', destination: 'GitHub' });
  });

  it('abre o governo de agentes sem executar agentes', () => {
    expect(parseCommand('abrir agentes')).toEqual({ type: 'agency:workspace' });
    expect(parseCommand('governo de agentes')).toEqual({ type: 'agency:workspace' });
    expect(parseCommand('watchdog de tarefas')).toEqual({ type: 'agency:workspace' });
  });

  it('abre o estúdio de design sem compilar ou publicar', () => {
    expect(parseCommand('abrir estúdio')).toEqual({ type: 'studio:workspace' });
    expect(parseCommand('design system')).toEqual({ type: 'studio:workspace' });
    expect(parseCommand('revisar contraste')).toEqual({ type: 'studio:workspace' });
    expect(parseCommand('criticar design')).toEqual({ type: 'studio:workspace' });
  });

  it('abre a direção de arte sem executar o upstream', () => {
    expect(parseCommand('abrir direção')).toEqual({ type: 'taste:workspace' });
    expect(parseCommand('direção de arte')).toEqual({ type: 'taste:workspace' });
    expect(parseCommand('revisar copy')).toEqual({ type: 'taste:workspace' });
    expect(parseCommand('registro de tells')).toEqual({ type: 'taste:workspace' });
    expect(parseCommand('júri de design')).toEqual({ type: 'taste:workspace' });
  });

  it('abre os diagramas sem executar o upstream', () => {
    expect(parseCommand('abrir diagramas')).toEqual({ type: 'diagram:workspace' });
    expect(parseCommand('diagrama de arquitetura')).toEqual({ type: 'diagram:workspace' });
    expect(parseCommand('diagrama de sequência')).toEqual({ type: 'diagram:workspace' });
    expect(parseCommand('validar IR')).toEqual({ type: 'diagram:workspace' });
    expect(parseCommand('exportar mermaid')).toEqual({ type: 'diagram:workspace' });
  });

  it('abre a carreira sem enviar candidatura', () => {
    expect(parseCommand('abrir carreira')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('triagem de vaga')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('checar ats')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('auditar bullets')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('carta de apresentação')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('funil de candidaturas')).toEqual({ type: 'career:workspace' });
    expect(parseCommand('abrir navegador')).toEqual({ type: 'browser:workspace' });
    expect(parseCommand('ler snapshot')).toEqual({ type: 'browser:workspace' });
    expect(parseCommand('resolver alvo')).toEqual({ type: 'browser:workspace' });
    expect(parseCommand('roteiro de navegação')).toEqual({ type: 'browser:workspace' });
    expect(parseCommand('limites do navegador')).toEqual({ type: 'browser:workspace' });
  });

  it('direciona análise de texto e status para as skills Python', () => {
    expect(parseCommand('analisar texto O núcleo executa ações')).toEqual({ type: 'python:analyze', text: 'O núcleo executa ações' });
    expect(parseCommand('python status').type).toBe('python:status');
  });

  it('reconhece artigos exatos, inclusive milhares e sufixos', () => {
    expect(parseCommand('artigo 49 do CDC')).toEqual({ type: 'legal:article', documentId: 'cdc', article: '49' });
    expect(parseCommand('consultar art. 1.046 do Código Civil')).toEqual({ type: 'legal:article', documentId: 'codigo-civil', article: '1.046' });
    expect(parseCommand('leia artigo 54-f do CDC')).toEqual({ type: 'legal:article', documentId: 'cdc', article: '54-F' });
  });

  it('direciona pesquisas jurídicas ao corpus com filtro opcional', () => {
    expect(parseCommand('pesquisar no CDC sobre direito de arrependimento')).toEqual({
      type: 'legal:search', documentId: 'cdc', query: 'direito de arrependimento',
    });
    expect(parseCommand('pesquisar na legislação sobre proteção de dados')).toEqual({
      type: 'legal:search', documentId: '', query: 'proteção de dados',
    });
    expect(parseCommand('fontes da legislação')).toEqual({ type: 'legal:sources' });
  });

  it('mantém pesquisa web separada da pesquisa de legislação', () => {
    expect(parseCommand('pesquisar na internet sobre automação pessoal')).toEqual({ type: 'web:search', query: 'automação pessoal' });
  });

  it('roteia leitura, biblioteca e criação confirmada de documentos', () => {
    expect(parseCommand('listar documentos')).toEqual({ type: 'document:list' });
    expect(parseCommand('ler PDF "documentos/relatorio.pdf"')).toEqual({ type: 'document:read', path: 'documentos/relatorio.pdf' });
    expect(parseCommand('criar planilha')).toEqual({ type: 'document:workspace' });
    expect(parseCommand('organizar arquivos')).toEqual({ type: 'files:organize' });
  });

  it('preserva atas e changelogs multilinha para as skills determinísticas', () => {
    expect(parseCommand('analisar reunião:\nAna: Podemos revisar?\nBruno: Eu fico responsável.')).toEqual({
      type: 'meeting:analyze', transcript: 'Ana: Podemos revisar?\nBruno: Eu fico responsável.',
    });
    expect(parseCommand('gerar changelog versão 0.4.0:\nfeat: documentos\ntest: API')).toEqual({
      type: 'changelog:generate', version: '0.4.0', commits: 'feat: documentos\ntest: API',
    });
    expect(parseCommand('sortear 2 entre Ana, Bruno, Carla')).toEqual({ type: 'random:pick', entries: 'Ana, Bruno, Carla', count: 2 });
  });

  it('roteia revisão de código e Web Vitals para workflows locais', () => {
    expect(parseCommand('revisar código python:\ndefinicao = 1\neval(definicao)')).toEqual({
      type: 'engineering:review', language: 'python', code: 'definicao = 1\neval(definicao)',
    });
    expect(parseCommand('avaliar web vitals LCP 2600 INP 180 CLS 0,05')).toEqual({
      type: 'engineering:webvitals', lcpMs: 2600, inpMs: 180, cls: 0.05,
    });
    expect(parseCommand('avaliar web vitals LCP 2600')).toEqual({ type: 'engineering:workspace' });
    expect(parseCommand('criar ADR')).toEqual({ type: 'engineering:workspace' });
  });

  it('retoma planos somente por ID e separa leitura do workspace confirmado', () => {
    expect(parseCommand('listar planos')).toEqual({ type: 'planning:list' });
    expect(parseCommand('retomar plano 2026-10-22-entrega')).toEqual({ type: 'planning:resume', planId: '2026-10-22-entrega' });
    expect(parseCommand('gate do plano plano-api')).toEqual({ type: 'planning:gate', planId: 'plano-api' });
    expect(parseCommand('retomar plano')).toEqual({ type: 'planning:workspace' });
    expect(parseCommand('criar plano')).toEqual({ type: 'planning:workspace' });
  });

  it('direciona a engenharia enxuta para as skills lean', () => {
    const diff = '--- a/app.js\n+++ b/app.js\n@@ -1,1 +1,1 @@\n-a\n+b';
    expect(parseCommand(`revisar mudança: ${diff}`)).toEqual({ type: 'lean:review', diff });
    expect(parseCommand('auditar código app')).toEqual({ type: 'lean:audit', path: 'app' });
    expect(parseCommand('dívida de atalhos em app')).toEqual({ type: 'lean:debt', path: 'app' });
    expect(parseCommand('abrir lean')).toEqual({ type: 'lean:workspace' });
    expect(parseCommand('dívida de atalhos')).toEqual({ type: 'lean:workspace' });
    expect(parseCommand('revisar código python: eval(x)')).toMatchObject({ type: 'engineering:review', language: 'python' });
  });

  it('roteia a análise reversa sem executar o artefato', () => {
    expect(parseCommand('inspecionar artefato app/main.js')).toEqual({ type: 'reverse:inspect', path: 'app/main.js' });
    expect(parseCommand('strings de app.asar')).toEqual({ type: 'reverse:strings', path: 'app.asar' });
    expect(parseCommand('entropia de firmware.bin')).toEqual({ type: 'reverse:entropy', path: 'firmware.bin' });
    expect(parseCommand('analisar javascript app')).toEqual({ type: 'reverse:analyze', path: 'app' });
    expect(parseCommand('comparar artefatos antes.bin e depois.bin')).toEqual({ type: 'reverse:compare', left: 'antes.bin', right: 'depois.bin' });
    expect(parseCommand('engenharia reversa')).toEqual({ type: 'reverse:workspace' });
    expect(parseCommand('analisar artefato')).toEqual({ type: 'reverse:workspace' });
  });

  it('não inventa uma intenção para comandos desconhecidos', () => {
    expect(parseCommand('explique computação quântica').type).toBe('unknown');
    expect(parseCommand('apagar sistema operacional').type).toBe('unknown');
  });
});
