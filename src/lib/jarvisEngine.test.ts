import { describe, expect, it } from 'vitest';
import { helpText, parseCommand } from './jarvisEngine';

/**
 * Estes são os exemplos que o próprio `helpText` promete ao usuário.
 * Se um deles parar de casar, o JARVIS passa a responder "não configurada"
 * sem chave de IA — e o usuário perde o comando sem entender por quê.
 */
describe('parseCommand — exemplos prometidos no helpText', () => {
  const casos: Array<[string, string]> = [
    ['ajuda', 'help'],
    ['oi', 'greeting'],
    ['obrigado', 'thanks'],
    ['que horas são?', 'time'],
    ['que dia é hoje?', 'date'],
    ['status do sistema', 'status'],
    ['calcular (1250 * 0,18) + 40', 'calculate'],
    ['criar tarefa revisar o projeto', 'task:add'],
    ['mostrar notas', 'note:list'],
    ['iniciar foco de 25 minutos', 'focus:start'],
    ['pesquisar por automação pessoal', 'web:search'],
    ['abrir GitHub', 'web:open'],
    ['analisar texto JARVIS organiza minha rotina', 'python:analyze'],
    ['python status', 'python:status'],
    ['artigo 49 do CDC', 'legal:article'],
    ['pesquisar na legislação sobre proteção de dados', 'legal:search'],
    ['listar documentos', 'document:list'],
    ['analisar reunião: Ana: revisar proposta', 'meeting:analyze'],
    ['gerar changelog: feat: nova skill', 'changelog:generate'],
    ['sortear 2 entre Ana, Bruno, Carla', 'random:pick'],
    ['organizar arquivos', 'files:organize'],
    ['listar planos', 'planning:list'],
    ['inspecionar artefato app/main.js', 'reverse:inspect'],
    ['abrir lean', 'lean:workspace'],
    ['abrir agentes', 'agency:workspace'],
    ['executar resumo do dia', 'automation:summary'],
  ];

  it.each(casos)('“%s” vira %s', (entrada, tipo) => {
    expect(parseCommand(entrada).type).toBe(tipo);
  });
});

describe('parseCommand — o que precisa da IA', () => {
  const perguntasAbertas = [
    'me explique a diferença entre inflação e deflação',
    'quem foi Machado de Assis',
    'escreva um poema sobre o mar',
  ];

  it.each(perguntasAbertas)('“%s” cai em unknown (depende da chave)', (entrada) => {
    expect(parseCommand(entrada).type).toBe('unknown');
  });

  it('entrada vazia não vira comando', () => {
    expect(parseCommand('   ').type).toBe('unknown');
  });
});

describe('parseCommand — detalhes do comando', () => {
  it('guarda a expressão do cálculo sem o ponto de interrogação', () => {
    const intent = parseCommand('calcular 2 + 2?');
    expect(intent).toMatchObject({ type: 'calculate', expression: '2 + 2' });
  });

  it('resolve o apelido do documento de lei', () => {
    expect(parseCommand('artigo 49 do CDC')).toMatchObject({ type: 'legal:article', documentId: 'cdc', article: '49' });
    expect(parseCommand('consultar artigo 5 da constituição')).toMatchObject({ documentId: 'constituicao' });
  });

  it('aceita cálculo digitado puro, sem a palavra calcular', () => {
    expect(parseCommand('(42 + 8) / 2').type).toBe('calculate');
  });

  it('não confunde texto solto com cálculo', () => {
    expect(parseCommand('me fale sobre 1984').type).not.toBe('calculate');
  });

  it('o pedido de foco carrega os minutos', () => {
    expect(parseCommand('iniciar foco de 25 minutos')).toMatchObject({ type: 'focus:start', minutes: 25 });
  });

  it('o sorteio carrega a quantidade', () => {
    expect(parseCommand('sortear 3 entre Ana, Bruno, Carla, Diego')).toMatchObject({ type: 'random:pick', count: 3 });
  });
});

describe('helpText', () => {
  it('cita as categorias locais principais', () => {
    for (const termo of ['Tarefas', 'Memória', 'Foco', 'Cálculos', 'Legislação', 'Documentos', 'Sistema']) {
      expect(helpText).toContain(termo);
    }
  });

  it('avisa o que exige confirmação', () => {
    expect(helpText.toLowerCase()).toContain('confirmação');
  });
});

describe('helpText — honestidade sobre a busca', () => {
  it('não promete leitura de resultados na busca do chat', () => {
    expect(helpText).toMatch(/aba nova/i);
    expect(helpText).toMatch(/não lê os resultados/i);
  });

  it('aponta a skill que faz a pesquisa real', () => {
    expect(helpText).toMatch(/Busca e leitura na web/i);
  });
});
