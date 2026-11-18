import { describe, expect, it } from 'vitest';
import {
  conferirDia,
  contagemPara,
  diaDaSemana,
  diasAteSabado,
  numeroDoDia,
  resumoDeAmanha,
  resumoDoDia,
} from './calendario';

// Quarta-feira, 18/11/2026 — o dia do print do dono. Os testes usam data fixa:
// relógio de máquina de teste não serve de régua.
const QUARTA = new Date(2026, 10, 18, 10, 1);
const SABADO = new Date(2026, 10, 21, 9, 0);
const DOMINGO = new Date(2026, 10, 22, 9, 0);
const SEXTA = new Date(2026, 10, 20, 9, 0);

describe('calendário local — o dia de hoje (0.91.37)', () => {
  it('sabe o dia da semana sem passar pelo modelo', () => {
    expect(diaDaSemana(QUARTA)).toBe('quarta-feira');
    expect(diaDaSemana(SABADO)).toBe('sábado');
    expect(diaDaSemana(DOMINGO)).toBe('domingo');
  });

  it('conta os dias até o sábado', () => {
    expect(diasAteSabado(QUARTA)).toBe(3);
    expect(diasAteSabado(SEXTA)).toBe(1);
    expect(diasAteSabado(SABADO)).toBe(0);
    // Domingo: o fim de semana está acabando, o próximo sábado é em 6 dias.
    expect(diasAteSabado(DOMINGO)).toBe(6);
  });

  it('responde “que dia é hoje” como o dono pediu', () => {
    expect(resumoDoDia(QUARTA)).toBe(
      'Hoje é quarta-feira, 18/11/2026. Faltam 3 dias para o sábado (21/11/2026).',
    );
  });

  it('no sábado diz que o fim de semana é agora', () => {
    expect(resumoDoDia(SABADO)).toContain('Hoje é sábado: o fim de semana é agora.');
  });

  it('na sexta fala “falta 1 dia”, no singular', () => {
    expect(resumoDoDia(SEXTA)).toContain('Falta 1 dia para o sábado (21/11/2026).');
  });

  it('no domingo diz quando é o próximo sábado', () => {
    expect(resumoDoDia(DOMINGO)).toContain('O próximo sábado é 28/11/2026, em 6 dias.');
  });

  it('responde “e amanhã?”', () => {
    expect(resumoDeAmanha(QUARTA)).toContain('Amanhã é quinta-feira, 19/11/2026.');
  });
});

describe('calendário local — “hoje é quinta?”', () => {
  it('entende o nome do dia com e sem “-feira”', () => {
    expect(numeroDoDia('quinta')).toBe(4);
    expect(numeroDoDia('quinta-feira')).toBe(4);
    expect(numeroDoDia('Qui')).toBe(4);
    expect(numeroDoDia('sábado')).toBe(6);
    expect(numeroDoDia('amanhã')).toBe(-1);
  });

  it('confirma quando a pessoa acerta', () => {
    expect(conferirDia('quarta', QUARTA)).toBe('Sim: hoje é quarta-feira, 18/11/2026.');
  });

  it('corrige quando a pessoa erra, e diz em quantos dias é', () => {
    expect(conferirDia('quinta', QUARTA)).toBe(
      'Não — hoje é quarta-feira, 18/11/2026. quinta-feira é amanhã.',
    );
    expect(conferirDia('sexta', QUARTA)).toContain('sexta-feira é em 2 dias.');
    expect(conferirDia('segunda', QUARTA)).toContain('segunda-feira é em 5 dias.');
  });

  it('reconhece ontem', () => {
    expect(conferirDia('terça', QUARTA)).toContain('terça-feira foi ontem.');
  });

  it('palpite que não é dia não vira “sim”', () => {
    expect(conferirDia('amanhã', QUARTA)).toContain('Hoje é quarta-feira, 18/11/2026.');
  });
});

describe('calendário local — quanto falta para o fim de semana', () => {
  it('responde a contagem para o sábado', () => {
    expect(contagemPara('sabado', QUARTA)).toBe('Faltam 3 dias para sábado (21/11/2026).');
  });

  it('fala “hoje” quando o dia é hoje', () => {
    expect(contagemPara('sábado', SABADO)).toBe('sábado é hoje (21/11/2026).');
  });

  it('conta qualquer dia da semana, não só o sábado', () => {
    expect(contagemPara('sexta', QUARTA)).toBe('Faltam 2 dias para sexta-feira (20/11/2026).');
    expect(contagemPara('quinta', QUARTA)).toBe('Falta 1 dia para quinta-feira (19/11/2026).');
    expect(contagemPara('terça', QUARTA)).toBe('Faltam 6 dias para terça-feira (24/11/2026).');
  });

  it('dia que não existe vira frase, não erro', () => {
    expect(contagemPara('feriado', QUARTA)).toContain('Não entendi “feriado” como dia da semana.');
  });
});
