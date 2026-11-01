import { describe, expect, it } from 'vitest';
import { avisoDaSituacao, formatarDecorrido, rotuloDoPedido, situacao } from './progresso';

describe('progresso do chat', () => {
  it('mostra tempo decorrido em mm:ss, nunca negativo', () => {
    expect(formatarDecorrido(0)).toBe('00:00');
    expect(formatarDecorrido(7_000)).toBe('00:07');
    expect(formatarDecorrido(83_000)).toBe('01:23');
    expect(formatarDecorrido(725_000)).toBe('12:05');
    expect(formatarDecorrido(-500)).toBe('00:00');
  });

  it('deduz o rótulo e o limite do pedido', () => {
    expect(rotuloDoPedido('arruma o pc').rotulo).toContain('Arrumando');
    expect(rotuloDoPedido('arruma o pc').limiteSegundos).toBe(300);
    expect(rotuloDoPedido('desfaz a última limpeza').rotulo).toContain('Desfazendo');
    expect(rotuloDoPedido('desfaz a última limpeza').limiteSegundos).toBe(180);
    expect(rotuloDoPedido('analisar texto: a vida é bela').rotulo).toContain('Lendo');
    expect(rotuloDoPedido('qualquer outra coisa').rotulo).toContain('Procurando');
    expect(rotuloDoPedido('').limiteSegundos).toBeGreaterThan(0);
  });

  it('marca demorando em 40% do limite e estourou no limite', () => {
    expect(situacao(1_000, 300)).toBe('trabalhando');
    expect(situacao(120_000, 300)).toBe('demorando');
    expect(situacao(300_000, 300)).toBe('estourou');
    // Limite zero ou negativo não pode virar divisão por zero.
    expect(situacao(1_000, 0)).toBe('estourou');
  });

  it('o aviso diz o limite real, sem inventar previsão', () => {
    expect(avisoDaSituacao(1_000, 300)).toBe('Limite desta skill: 300 s.');
    expect(avisoDaSituacao(200_000, 300)).toContain('Ainda rodando');
    expect(avisoDaSituacao(400_000, 300)).toContain('Passou do limite de 300 s');
    expect(avisoDaSituacao(400_000, 300)).toContain('API');
  });
});
