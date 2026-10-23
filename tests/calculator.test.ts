import { describe, expect, it } from 'vitest';
import { evaluateExpression } from '../src/lib/calculator';

describe('calculadora segura', () => {
  it('respeita precedência e parênteses', () => {
    expect(evaluateExpression('(42 + 8) / 2')).toBe(25);
    expect(evaluateExpression('2 + 3 * 4')).toBe(14);
    expect(evaluateExpression('2 ^ 3 ^ 2')).toBe(512);
  });

  it('aceita decimal brasileiro e operadores visuais', () => {
    expect(evaluateExpression('1250 * 0,18')).toBe(225);
    expect(evaluateExpression('10 × 3')).toBe(30);
    expect(evaluateExpression('10 ÷ 4')).toBe(2.5);
  });

  it('recusa código e divisões inválidas', () => {
    expect(() => evaluateExpression('alert(1)')).toThrow();
    expect(() => evaluateExpression('10 / 0')).toThrow('zero');
    expect(() => evaluateExpression('(2 + 3')).toThrow('parêntese');
  });
});
