import { describe, expect, it, vi } from 'vitest';
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
    // Guarda contra a regressão da 0.74.0: a confirmação mandava "sim, pode".
    const texto = 'sim, pode';
    expect(autorizacaoParaConfirmar(true, texto)).toBe('');
    expect(autorizacaoParaConfirmar(false, texto)).toBe(texto);
    // sem modo dono o valor é o campo do token, nunca a mensagem do chat
    expect(autorizacaoParaConfirmar(false, '') === '').toBe(true);
  });
});

// --- 0.77.0: chaves de IA pela tela -------------------------------------
// O teste que importa não é "o cartão aparece": é que nada da chave fique
// guardado no navegador. A chave vai uma vez para a API local e é esquecida.

describe('chaves de IA', () => {
  it('a lista de mascaradas não contém chave utilizável', async () => {
    const { __mascararParaTeste } = await import('./api');
    const chave = 'gsk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
    const mascarada = __mascararParaTeste(chave);
    expect(mascarada).not.toBe(chave);
    expect(mascarada).not.toContain(chave);
    expect(mascarada.length).toBeLessThan(chave.length);
  });

  it('as funções de chave nunca gravam em localStorage', async () => {
    // O ambiente do vitest é node: não existe `Storage`. Um localStorage falso
    // serve para provar que ninguém chama `setItem` com a chave.
    const gravar = vi.fn();
    vi.stubGlobal('localStorage', { setItem: gravar, getItem: vi.fn(), removeItem: vi.fn() });
    const { getChavesIA } = await import('./api');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ok: true, quantidade: 1, mascaradas: ['gsk_a…BkXV'], provedor: 'Groq',
      base: 'https://api.groq.com/openai/v1', modelo: 'llama-3.3-70b-versatile',
      local: false, arquivo: 'D:/JARVIS/.env', maximo: 10, podeEditar: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));
    const estado = await getChavesIA();
    expect(estado.quantidade).toBe(1);
    expect(gravar).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
