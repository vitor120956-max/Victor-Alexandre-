import { describe, expect, it } from 'vitest';
import { autorizacaoParaConfirmar } from './confirmacao';

describe('autorizacaoParaConfirmar', () => {
  it('no modo dono manda vazio, para o servidor preencher na própria máquina', () => {
    expect(autorizacaoParaConfirmar(true, 'token-da-tela')).toBe('');
    expect(autorizacaoParaConfirmar(true, '')).toBe('');
    expect(autorizacaoParaConfirmar(true, null)).toBe('');
  });

  it('sem modo dono manda o token que está na tela', () => {
    expect(autorizacaoParaConfirmar(false, 'abc123')).toBe('abc123');
    expect(autorizacaoParaConfirmar(false, '  abc123  ')).toBe('abc123');
    expect(autorizacaoParaConfirmar(false, undefined)).toBe('');
  });

  it('não existe caminho que devolva texto de conversa como token', () => {
    // Guarda contra a regressão da 0.61.8: a confirmação mandava "sim, pode".
    const texto = 'sim, pode';
    expect(autorizacaoParaConfirmar(true, texto)).toBe('');
    expect(autorizacaoParaConfirmar(false, texto)).toBe(texto);
    // sem modo dono o valor é o campo do token, nunca a mensagem do chat
    expect(autorizacaoParaConfirmar(false, '') === '').toBe(true);
  });
});
