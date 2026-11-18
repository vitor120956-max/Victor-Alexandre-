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
    ['testar ia', 'ai:testar'],
    ['conferir a ia', 'ai:testar'],
    ['a ia está funcionando?', 'ai:testar'],
    ['status da ia', 'ai:testar'],
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

describe('pedidos de abertura com cortesia', () => {
  it('reconhece o pedido coloquial de abrir o YouTube', () => {
    expect(parseCommand('quero q vc abra uma tela do youtube no meu pc')).toMatchObject({ type: 'web:open', destination: 'YouTube' });
  });

  it('reconhece "pode abrir o gmail pra mim"', () => {
    expect(parseCommand('pode abrir o gmail pra mim')).toMatchObject({ type: 'web:open', destination: 'Gmail' });
  });

  it('mantém o formato curto', () => {
    expect(parseCommand('abrir GitHub')).toMatchObject({ type: 'web:open', destination: 'GitHub' });
    expect(parseCommand('abra o drive')).toMatchObject({ type: 'web:open', destination: 'Google Drive' });
  });

  it('não transforma painel em aba', () => {
    expect(parseCommand('abrir estúdio').type).toBe('studio:workspace');
    expect(parseCommand('abrir lean').type).toBe('lean:workspace');
  });

  it('site fora da lista continua precisando de ajuda', () => {
    expect(parseCommand('abrir um site qualquer de receitas').type).toBe('unknown');
  });
});

describe('pesquisa com resposta e token de host', () => {
  it('reconhece "pesquisar e responder X"', () => {
    expect(parseCommand('pesquisar e responder quem foi Machado de Assis')).toMatchObject({
      type: 'pesquisa:responder',
      pergunta: 'quem foi Machado de Assis',
    });
  });

  it('reconhece a variante com "na web" e "me explique"', () => {
    expect(parseCommand('pesquise na web e me explique a diferença entre inflação e deflação')).toMatchObject({
      type: 'pesquisa:responder',
    });
  });

  it('reconhece "responder com fontes"', () => {
    expect(parseCommand('responder com fontes o que é inflação').type).toBe('pesquisa:responder');
  });

  it('a busca simples continua abrindo o navegador', () => {
    expect(parseCommand('pesquisar por automação pessoal').type).toBe('web:search');
  });

  it('reconhece o comando de token e não confunde com pergunta', () => {
    expect(parseCommand('token abc123def456')).toMatchObject({ type: 'host:token', token: 'abc123def456' });
    expect(parseCommand('token')).not.toMatchObject({ type: 'host:token' });
  });
});

describe('helpText — pesquisa com fonte', () => {
  it('ensina que buscar não pede token e avisa o que acontece sem IA', () => {
    expect(helpText).toMatch(/não pede token/i);
    expect(helpText).toMatch(/JARVIS_HOST_REDE=1/);
    expect(helpText).toMatch(/sem resumo/i);
    expect(helpText).toMatch(/DuckDuckGo/);
  });

  it('reconhece “no youtube” como fonte de verdade, não atalho do navegador', () => {
    expect(parseCommand('pesquisa no youtube sobre python')).toMatchObject({
      type: 'pesquisa:responder',
      pergunta: 'python',
      fonte: 'youtube',
    });
    expect(parseCommand('busca na wikipedia sobre café')).toMatchObject({
      type: 'pesquisa:responder',
      fonte: 'wikipedia',
    });
    expect(parseCommand('pesquisar no google sobre impostos')).toMatchObject({
      type: 'pesquisa:responder',
      fonte: 'auto',
    });
  });

  it('sem fonte dita, a busca simples continua abrindo o navegador', () => {
    expect(parseCommand('pesquisar por automação pessoal').type).toBe('web:search');
    expect(parseCommand('pesquisar na internet sobre automação pessoal')).toEqual({
      type: 'web:search',
      query: 'automação pessoal',
    });
  });
});

describe('agente local — comandos', () => {
  it('lista as skills locais', () => {
    expect(parseCommand('minhas skills locais').type).toBe('agente:skills');
    expect(parseCommand('skills locais').type).toBe('agente:skills');
    expect(parseCommand('ver skills criadas').type).toBe('agente:skills');
  });

  it('aceita o pedido explícito com o prefixo skill', () => {
    expect(parseCommand('skill somar 10 20 30')).toMatchObject({ type: 'agente:executar', pedido: 'somar 10 20 30' });
    expect(parseCommand('modo local contar as palavras de: um dois')).toMatchObject({
      type: 'agente:executar',
      pedido: 'contar as palavras de: um dois',
    });
  });

  it('não transforma pergunta comum em pedido de skill', () => {
    expect(parseCommand('quem foi Machado de Assis').type).toBe('unknown');
  });

  it('o help descreve o agente local sem prometer IA', () => {
    expect(helpText).toMatch(/Agente local/);
    expect(helpText).toMatch(/sem modelo nenhum/);
    expect(helpText).toMatch(/receitas prontas/);
  });
});

describe('agente local — correção', () => {
  it('reconhece a correção pelo nome da skill', () => {
    expect(parseCommand('não é essa, é a skill legal.article')).toMatchObject({ type: 'agente:corrigir', alvo: 'legal.article' });
    expect(parseCommand('corrigir: text.analyze')).toMatchObject({ type: 'agente:corrigir', alvo: 'text.analyze' });
    expect(parseCommand('use a skill Analisar texto')).toMatchObject({ type: 'agente:corrigir', alvo: 'Analisar texto' });
  });

  it('reconhece o pedido de buscar na web o que falhou', () => {
    expect(parseCommand('procure na web sobre isso').type).toBe('agente:pesquisar');
    expect(parseCommand('pesquise isso na web').type).toBe('agente:pesquisar');
    expect(parseCommand('não sabe? pesquisa isso').type).toBe('agente:pesquisar');
  });

  it('reconhece o esquecimento', () => {
    expect(parseCommand('esqueça como fazer pão')).toMatchObject({ type: 'agente:esquecer', pedido: 'como fazer pão' });
    expect(parseCommand('esquecer meu relatorio do mes').type).toBe('agente:esquecer');
  });

  it('não confunde pesquisa normal com correção', () => {
    expect(parseCommand('pesquisar por automação pessoal').type).toBe('web:search');
    expect(parseCommand('pesquisar e responder quem foi Machado de Assis').type).toBe('pesquisa:responder');
  });

  it('o help ensina a corrigir', () => {
    expect(helpText).toMatch(/Correção/);
    expect(helpText).toMatch(/procure na web sobre isso/);
    expect(helpText).toMatch(/esqueça/);
  });
});

describe('abertura com palavra de chamada na frente', () => {
  it('aceita "chat" antes do pedido', () => {
    expect(parseCommand('chat abra o youtube no meu pc')).toMatchObject({ type: 'web:open', destination: 'YouTube' });
    expect(parseCommand('chat: abre o gmail')).toMatchObject({ type: 'web:open', destination: 'Gmail' });
    expect(parseCommand('jarvis chat abra o github')).toMatchObject({ type: 'web:open', destination: 'GitHub' });
  });

  it('continua aceitando o pedido sem palavra de chamada', () => {
    expect(parseCommand('abra o youtube')).toMatchObject({ type: 'web:open', destination: 'YouTube' });
    expect(parseCommand('quero q vc abra uma tela do youtube no meu pc')).toMatchObject({ type: 'web:open', destination: 'YouTube' });
  });

  it('não transforma site desconhecido em abertura', () => {
    expect(parseCommand('chat abra um site de receitas')).not.toMatchObject({ type: 'web:open' });
  });
});


/**
 * 0.91.34 — “funcionou?” precisa de prova.
 *
 * O dono perguntou isso olhando um “oi” respondido na tela. Aquele texto é a
 * skill local de saudação (`case 'greeting'`): não passa pelo modelo e não diz
 * nada sobre ele. A resposta honesta é um comando que pede ao modelo de
 * verdade — e o parser tem de reconhecer as formas que uma pessoa digita.
 */
describe('parseCommand — testar a IA de verdade', () => {
  it.each([
    'testar ia',
    'testa a ia',
    'teste ia',
    'conferir ia',
    'conferir a ia externa',
    'confere a ia',
    'verificar ia',
    'ia está funcionando',
    'a ia está funcionando?',
    'a ia responde?',
    'ia online?',
    'status da ia',
    'estado da IA externa',
  ])('“%s” pede o teste da IA', (entrada) => {
    expect(parseCommand(entrada).type).toBe('ai:testar');
  });

  it('não rouba comandos vizinhos', () => {
    // `status do sistema` é do sistema; `python status` é das skills Python.
    expect(parseCommand('status do sistema').type).toBe('status');
    expect(parseCommand('python status').type).toBe('python:status');
    expect(parseCommand('que horas são?').type).toBe('time');
    expect(parseCommand('oi').type).toBe('greeting');
  });

  it('o texto de ajuda ensina o comando e diz que “oi” é local', () => {
    expect(helpText).toContain('testar ia');
    expect(helpText).toContain('locais');
  });
});

describe('parseCommand — previsão do tempo de verdade', () => {
  // 0.91.36 — “vai chover hoje?” ia para o modelo, que não vê o tempo e podia
  // inventar uma temperatura plausível. Agora a frase consulta o serviço de
  // previsão — que devolve a fonte e a hora da leitura.
  it.each([
    'vai chover hoje?',
    'vai chover',
    'chove hoje',
    'como está a previsão do tempo hoje?',
    'qual a previsão do tempo hoje',
    'que tempo faz hoje',
    'como está o tempo',
    'como está o clima hoje',
    'vai fazer sol hoje',
    'preciso de guarda-chuva?',
    'qual a temperatura agora',
  ])('“%s” vira uma consulta de previsão', (entrada) => {
    const intent = parseCommand(entrada);
    expect(intent.type).toBe('tempo:previsao');
    if (intent.type === 'tempo:previsao') {
      expect(intent.cidade).toBe('');
      expect(intent.quando).toBe('hoje');
    }
  });

  it.each([
    ['vai chover amanhã?', 'amanha'],
    ['previsão do tempo para amanhã', 'amanha'],
  ])('“%s” pergunta pelo dia seguinte', (entrada, quando) => {
    const intent = parseCommand(entrada);
    expect(intent.type).toBe('tempo:previsao');
    if (intent.type === 'tempo:previsao') expect(intent.quando).toBe(quando);
  });

  it.each([
    ['previsão do tempo em São José', 'São José'],
    ['como está o tempo em Curitiba hoje', 'Curitiba'],
    ['vai chover hoje no Rio de Janeiro', 'Rio de Janeiro'],
    ['previsão para o Rio de Janeiro', 'Rio de Janeiro'],
    ['qual a temperatura agora em Palhoça', 'Palhoça'],
    ['previsao em Palhoca, SC', 'Palhoca'],
  ])('“%s” pergunta pela cidade da frase (%s)', (entrada, cidade) => {
    const intent = parseCommand(entrada);
    expect(intent.type).toBe('tempo:previsao');
    if (intent.type === 'tempo:previsao') expect(intent.cidade).toBe(cidade);
  });

  it('não confunde “hoje”, “tempo” nem “guarda-chuva” com cidade', () => {
    for (const frase of ['vai chover hoje?', 'como esta a previsao de tempo hj', 'preciso de guarda-chuva?']) {
      const intent = parseCommand(frase);
      expect(intent.type).toBe('tempo:previsao');
      if (intent.type === 'tempo:previsao') expect(intent.cidade).toBe('');
    }
  });

  it('quem pediu busca na web continua indo para a web', () => {
    // A pessoa quer a página, não o número: não roubar o comando.
    expect(parseCommand('pesquise a previsão do tempo').type).toBe('web:search');
    expect(parseCommand('procure na web a previsão do tempo de hoje').type).toBe('web:search');
  });

  it('não rouba os vizinhos', () => {
    expect(parseCommand('que horas são?').type).toBe('time');
    expect(parseCommand('vai abrir o chrome').type).toBe('unknown');
    expect(parseCommand('testar ia').type).toBe('ai:testar');
    expect(parseCommand('que dia é hoje?').type).toBe('date');
  });

  it('o texto de ajuda diz que a previsão não passa pelo modelo', () => {
    expect(helpText).toContain('previsão do tempo');
    expect(helpText).toContain('Open-Meteo');
  });
});

describe('parseCommand — calendário: dia, fim de semana e feriados (0.91.37)', () => {
  // O dono perguntou, em 18/11: “q dia e hj, próximos feriados, quantos dias
  // faltam para final de semana?”. Só o “que dia é hoje” funcionava; o resto
  // caía no modelo, que não tem relógio.
  it.each([
    'que dia é hoje',
    'que dia é hoje?',
    'que dia da semana é hoje',
    'estamos em que dia da semana',
    'data de hoje',
  ])('“%s” é data local', (entrada) => {
    expect(parseCommand(entrada).type).toBe('date');
  });

  it.each([
    ['hoje é quarta?', 'quarta'],
    ['hoje é quinta', 'quinta'],
    ['hoje é quinta-feira?', 'quinta'],
    // `diaCitado` trabalha sobre o texto normalizado: o nome volta sem acento,
    // que é o que `numeroDoDia` entende.
    ['hoje é sábado', 'sabado'],
  ])('“%s” confere o dia (%s)', (entrada, dia) => {
    const intent = parseCommand(entrada);
    expect(intent.type).toBe('date');
    if (intent.type === 'date') expect(intent.conferir).toBe(dia);
  });

  it.each([
    'quantos dias faltam para o fim de semana',
    'quantos dias faltam para o final de semana',
    'falta quanto para o sábado',
    'quanto falta para o sábado',
  ])('“%s” conta até o sábado', (entrada) => {
    const intent = parseCommand(entrada);
    expect(intent.type).toBe('date');
    if (intent.type === 'date') expect(intent.alvo).toBe('sabado');
  });

  it('conta até outro dia da semana', () => {
    const intent = parseCommand('quantos dias faltam para sexta?');
    expect(intent.type).toBe('date');
    if (intent.type === 'date') expect(intent.alvo).toBe('sexta');
  });

  it('“que dia é amanhã?” pede o dia seguinte', () => {
    const intent = parseCommand('que dia é amanhã?');
    expect(intent.type).toBe('date');
    if (intent.type === 'date') expect(intent.amanha).toBe(true);
  });

  it.each([
    'próximos feriados',
    'quais os próximos feriados',
    'quais são os feriados',
    'quando é o próximo feriado',
  ])('“%s” consulta o calendário', (entrada) => {
    expect(parseCommand(entrada).type).toBe('calendario:feriados');
  });

  it('entende feriado pelo nome', () => {
    const natal = parseCommand('quanto falta para o natal?');
    expect(natal.type).toBe('calendario:feriados');
    if (natal.type === 'calendario:feriados') {
      expect(natal.nome).toBe('Natal');
      expect(natal.proximo).toBe(true);
    }

    const carnaval = parseCommand('quando é o carnaval');
    expect(carnaval.type).toBe('calendario:feriados');
    if (carnaval.type === 'calendario:feriados') expect(carnaval.nome).toBe('Carnaval');
  });

  it('entende o ano pedido', () => {
    const intent = parseCommand('feriados de 2027');
    expect(intent.type).toBe('calendario:feriados');
    if (intent.type === 'calendario:feriados') expect(intent.ano).toBe(2027);
  });

  it('a pergunta composta (dia + feriados) cai nos feriados, que já trazem o dia', () => {
    expect(parseCommand('que dia é hoje e os próximos feriados').type).toBe('calendario:feriados');
  });

  it('não rouba os vizinhos', () => {
    expect(parseCommand('que horas são?').type).toBe('time');
    expect(parseCommand('vai chover hoje?').type).toBe('tempo:previsao');
    expect(parseCommand('testar ia').type).toBe('ai:testar');
    expect(parseCommand('pesquise os feriados de 2027').type).toBe('web:search');
    expect(parseCommand('abrir o calendário do google').type).toBe('unknown');
  });

  it('o texto de ajuda ensina o calendário e diz que feriado móvel é calculado', () => {
    expect(helpText).toContain('quantos dias faltam para o fim de semana');
    expect(helpText).toContain('Páscoa');
  });
});

  // 0.91.38 — “analisar meu jogo”: o dono está criando um jogo em APK e quer o
  // diagnóstico do pacote. O pedido tem de chegar na análise do arquivo, e não
  // no modelo, que não vê o APK e inventaria um “problema de performance”.
  describe('análise do próprio jogo (APK)', () => {
    it('reconhece o pedido de análise', () => {
      for (const frase of [
        'analisar jogo',
        'analisa meu jogo',
        'analise o apk do jogo',
        'analisar o apk do jogo',
        'melhorar meu jogo',
        'como melhorar meu jogo?',
        'quero melhorar o jogo',
        'otimizar meu jogo',
      ]) {
        expect(parseCommand(frase).type).toBe('jogo:analisar');
      }
    });

    it('pega o nome do arquivo dito na frase', () => {
      const intent = parseCommand('analisar jogo meu-jogo.apk');
      expect(intent.type).toBe('jogo:analisar');
      if (intent.type === 'jogo:analisar') expect(intent.arquivo).toBe('meu-jogo.apk');

      const xapk = parseCommand('analisa o jogo corrida.XAPK');
      if (xapk.type === 'jogo:analisar') expect(xapk.arquivo).toBe('corrida.XAPK');
    });

    it('sem o nome do arquivo, deixa o servidor dizer o que tem lá', () => {
      const intent = parseCommand('analisar meu jogo');
      expect(intent.type).toBe('jogo:analisar');
      if (intent.type === 'jogo:analisar') expect(intent.arquivo).toBeUndefined();
    });

    it('não rouba os vizinhos', () => {
      expect(parseCommand('que horas são?').type).toBe('time');
      expect(parseCommand('vai chover hoje?').type).toBe('tempo:previsao');
      expect(parseCommand('pesquise jogos de corrida para android').type).toBe('web:search');
      expect(parseCommand('abrir o jogo').type).toBe('unknown');
      expect(parseCommand('não gostei do jogo do brasil').type).toBe('unknown');
    });

    it('a ajuda ensina o comando e onde arrastar o APK', () => {
      expect(helpText).toContain('analisar jogo');
      expect(helpText).toContain('analisar-jogo.bat');
    });
  });

  // 0.91.39 — “dps q esse apk estiver bom eu quero testar no meu iphone”.
  // APK não roda no iOS; o pedido tem de chegar na resposta certa, e não no
  // modelo (que responderia “sim, dá para instalar” com toda a confiança).
  describe('testar o jogo no iPhone', () => {
    it('reconhece o pedido', () => {
      for (const frase of [
        'quero testar no meu iphone',
        'testar no iphone',
        'testar meu jogo no iphone',
        'como rodo o jogo no iphone',
        'da para jogar no iphone',
        'meu jogo no iphone funciona?',
        'como instalar meu jogo no iphone',
      ]) {
        expect(parseCommand(frase).type).toBe('jogo:iphone');
      }
    });

    it('não rouba compra de iphone nem a busca na web', () => {
      expect(parseCommand('qual o preço do iphone 17?').type).not.toBe('jogo:iphone');
      expect(parseCommand('pesquise iphone 17 no mercado').type).toBe('web:search');
      expect(parseCommand('testar ia').type).toBe('ai:testar');
      expect(parseCommand('quero testar no meu iphone').type).toBe('jogo:iphone');
      expect(parseCommand('analisar meu jogo').type).toBe('jogo:analisar');
    });

    it('a ajuda explica o caminho do iPhone', () => {
      expect(helpText).toContain('iPhone');
      expect(helpText).toContain('testar-no-iphone.bat');
    });
  });
