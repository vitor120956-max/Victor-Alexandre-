import { describe, expect, it } from 'vitest';
import { normalizeSkillParameters } from '../src/lib/api';
import type { PythonSkill } from '../src/lib/api';

const skill: PythonSkill = {
  id: 'test.numeric', name: 'Numéricos', description: '', category: 'Teste', runtime: 'python',
  sideEffects: false, dryRunSupported: false, requiresConfirmation: false,
  inputSchema: {
    type: 'object',
    properties: {
      decimal: { type: 'number', title: 'CLS' },
      count: { type: 'integer', title: 'Contagem', default: 1 },
      text: { type: 'string', title: 'Texto' },
    },
    required: ['decimal'],
  },
};

describe('normalização de parâmetros numéricos das skills', () => {
  it('preserva decimais durante a edição e converte somente no envio', () => {
    expect(normalizeSkillParameters(skill, { decimal: '0.05', count: '2', text: '0.05' })).toEqual({ decimal: 0.05, count: 2, text: '0.05' });
  });

  it('usa o default em opcionais vazios e rejeita obrigatórios vazios', () => {
    expect(normalizeSkillParameters(skill, { decimal: '0.1', count: '' })).toMatchObject({ decimal: 0.1, count: 1 });
    expect(() => normalizeSkillParameters(skill, { decimal: '', count: 1 })).toThrow('Preencha o campo numérico “CLS”');
  });

  it('rejeita números inválidos antes da chamada da API', () => {
    expect(() => normalizeSkillParameters(skill, { decimal: 'não-numérico', count: 1 })).toThrow('Use um número válido em “CLS”');
  });
});
