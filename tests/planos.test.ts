import { describe, expect, it } from 'vitest';
import { parametrosDeExecucao, planoDoResultado, resumoDoPlano } from '../src/lib/planos';

const resultadoDoPlano = {
  confirmacao: '6d622c63',
  rows: [
    { campo: 'alvo', valor: 'setup.exe' },
    { campo: 'tipo', valor: 'exe' },
    { campo: 'comando', valor: 'C:/JARVIS/storage/host-downloads/setup.exe /S' },
    { campo: 'risco', valor: 'alto' },
    { campo: 'sha256', valor: 'dcb8daf9f7b51b4b6b1e63bb86347ec9bb8b08198e03c4c890b6e3ac7144f8ea' },
    { campo: 'confirmação', valor: '6d622c63' },
  ],
};

describe('plano de instalação na tela', () => {
  it('lê o código e os campos da lista rows', () => {
    const plano = planoDoResultado(resultadoDoPlano);
    expect(plano).not.toBeNull();
    expect(plano?.confirmacao).toBe('6d622c63');
    expect(plano?.alvo).toBe('setup.exe');
    expect(plano?.tipo).toBe('exe');
    expect(plano?.risco).toBe('alto');
    expect(plano?.comando).toContain('setup.exe /S');
    expect(plano?.sha256).toHaveLength(64);
  });

  it('sem código de uso único não há botão de executar', () => {
    expect(planoDoResultado({ rows: [{ campo: 'alvo', valor: 'x.exe' }] })).toBeNull();
    expect(planoDoResultado({ confirmacao: '' })).toBeNull();
    expect(planoDoResultado(null)).toBeNull();
    expect(planoDoResultado(undefined)).toBeNull();
  });

  it('aguenta resultado sem rows e campo com valor estranho', () => {
    const plano = planoDoResultado({ confirmacao: 'abcd1234', rows: [{ campo: 'alvo', valor: 42 }] });
    expect(plano?.confirmacao).toBe('abcd1234');
    expect(plano?.alvo).toBe('');
  });

  it('modo dono não manda token — quem preenche é o servidor', () => {
    const plano = planoDoResultado(resultadoDoPlano)!;
    expect(parametrosDeExecucao(plano, { hostToken: 'segredo', modoDono: true })).toEqual({ confirmacao: '6d622c63' });
  });

  it('sem modo dono, o token digitado vai junto', () => {
    const plano = planoDoResultado(resultadoDoPlano)!;
    expect(parametrosDeExecucao(plano, { hostToken: ' abc123 ', modoDono: false })).toEqual({
      confirmacao: '6d622c63',
      autorizacao: 'abc123',
    });
  });

  it('sem token e sem modo dono, só o código vai — e o servidor vai recusar', () => {
    const plano = planoDoResultado(resultadoDoPlano)!;
    expect(parametrosDeExecucao(plano, { hostToken: '   ', modoDono: false })).toEqual({ confirmacao: '6d622c63' });
  });

  it('resume o plano para o cabeçalho', () => {
    const plano = planoDoResultado(resultadoDoPlano)!;
    expect(resumoDoPlano(plano)).toBe('setup.exe · exe · risco alto');
    expect(resumoDoPlano({ ...plano, alvo: '', tipo: '', risco: '' })).toBe('plano');
  });
});
