import { describe, expect, it } from 'vitest';
import { montarRespostaAgente, respostaVeioDeSkill } from './agenteResposta';
import type { AgenteResultado } from './api';

function resultado(patch: Partial<AgenteResultado> = {}): AgenteResultado {
  return {
    ok: true,
    pedido: 'pedido',
    acao: 'nada',
    skill: null,
    confianca: 0,
    parametros: {},
    faltando: [],
    resposta: '',
    alternativas: [],
    fontes: [],
    avisos: [],
    limites: [],
    ...patch,
  };
}

describe('montarRespostaAgente', () => {
  it('junta resposta e avisos novos', () => {
    const texto = montarRespostaAgente(resultado({ resposta: 'Achei isto.', avisos: ['Fonte sem data.'] }));
    expect(texto).toBe('Achei isto.\n\nFonte sem data.');
  });

  it('não repete o aviso que já está dentro da resposta', () => {
    const aviso = 'Modo host exige o token de storage/host-token.txt.';
    const texto = montarRespostaAgente(
      resultado({ resposta: `Não achei skill nem receita, e a busca falhou: ${aviso}`, avisos: [aviso] }),
    );
    expect(texto.match(/Modo host exige/g)).toHaveLength(1);
  });

  it('ignora aviso vazio e resposta vazia', () => {
    expect(montarRespostaAgente(resultado({ resposta: '', avisos: ['', '  '] }))).toBe('');
  });

  it('mantém os dois avisos quando são diferentes da resposta', () => {
    const texto = montarRespostaAgente(resultado({ resposta: 'Ok.', avisos: ['Primeiro.', 'Segundo.'] }));
    expect(texto).toBe('Ok.\n\nPrimeiro.\n\nSegundo.');
  });
});

describe('respostaVeioDeSkill', () => {
  it('skill executada com texto responde pelo chat', () => {
    expect(respostaVeioDeSkill(resultado({ acao: 'executado', resposta: 'Feito.' }))).toBe(true);
    expect(respostaVeioDeSkill(resultado({ acao: 'criado', resposta: 'Criei.' }))).toBe(true);
    expect(respostaVeioDeSkill(resultado({ acao: 'guardado', resposta: 'Guardada.' }))).toBe(true);
    expect(respostaVeioDeSkill(resultado({ acao: 'biblioteca', resposta: 'Do livro.' }))).toBe(true);
  });

  it('confirmação vale mesmo sem texto: é o pedido de autorização', () => {
    expect(respostaVeioDeSkill(resultado({ acao: 'confirmar', resposta: '' }))).toBe(true);
  });

  it('sem skill, o modelo responde', () => {
    expect(respostaVeioDeSkill(resultado({ acao: 'nada' }))).toBe(false);
    expect(respostaVeioDeSkill(resultado({ acao: 'sugerir', confianca: 0.4 }))).toBe(false);
  });

  it('“falta um campo” só vale com confiança alta', () => {
    expect(respostaVeioDeSkill(resultado({ acao: 'faltando', confianca: 0.62 }))).toBe(true);
    expect(respostaVeioDeSkill(resultado({ acao: 'faltando', confianca: 0.31 }))).toBe(false);
  });
});
