import { describe, expect, it } from 'vitest';
import { formatPythonChatResult } from './skillResults';

describe('formatPythonChatResult · celular', () => {
  it('mostra a resposta do status, que é o que a pessoa precisa ler', () => {
    const texto = formatPythonChatResult('celular.status', {
      situacao: 'autorizado',
      resposta: 'adb: D:\\JARVIS\\adb.exe · scrcpy: D:\\JARVIS\\scrcpy.exe\n\nPronto: R58M12 autorizado.',
      proximo_passo: 'Próximo passo é `celular.espelhar`.',
    });
    expect(texto).toContain('adb:');
    expect(texto).toContain('R58M12');
  });

  it('lista o SHA-256 de cada ferramenta baixada', () => {
    const texto = formatPythonChatResult('celular.preparar', {
      resposta: 'Baixei e extraí as duas ferramentas.',
      baixados: [
        { ferramenta: 'platform-tools', pasta: 'D:\\ferramentas\\platform-tools', sha256: 'abcdef0123456789abcdef' },
        { ferramenta: 'scrcpy', pasta: 'D:\\ferramentas\\scrcpy', sha256: 'fedcba9876543210fedcba' },
      ],
    });
    expect(texto).toContain('platform-tools');
    expect(texto).toContain('abcdef0123456789');
  });

  it('não repete o próximo passo quando ele já está no texto', () => {
    const texto = formatPythonChatResult('celular.status', {
      resposta: 'Sem cabo. Rode `celular.plano`.',
      proximo_passo: 'Rode `celular.plano`.',
    });
    expect(texto.match(/celular\.plano/g)).toHaveLength(1);
  });

  it('usa `resposta` como saída de qualquer skill que a traga', () => {
    expect(formatPythonChatResult('qualquer.skill', { resposta: 'Texto pronto da skill.' })).toBe('Texto pronto da skill.');
  });
});
