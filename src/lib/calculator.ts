/**
 * Calculadora de precedência com parser recursivo.
 * Não usa eval nem executa qualquer texto fora da gramática matemática.
 */
export function evaluateExpression(source: string): number {
  const input = source
    .trim()
    .replace(/[×x]/gi, '*')
    .replace(/÷/g, '/')
    .replace(/[−–]/g, '-')
    .replace(/\^/g, '^');

  if (!input || input.length > 160) {
    throw new Error('Expressão vazia ou longa demais.');
  }

  let position = 0;

  function skipSpaces(): void {
    while (position < input.length && /\s/.test(input[position])) position += 1;
  }

  function parseExpression(): number {
    let value = parseTerm();
    while (true) {
      skipSpaces();
      const operator = input[position];
      if (operator !== '+' && operator !== '-') break;
      position += 1;
      const right = parseTerm();
      value = operator === '+' ? value + right : value - right;
    }
    return value;
  }

  function parseTerm(): number {
    let value = parsePower();
    while (true) {
      skipSpaces();
      const operator = input[position];
      if (operator !== '*' && operator !== '/' && operator !== '%') break;
      position += 1;
      const right = parsePower();
      if ((operator === '/' || operator === '%') && right === 0) {
        throw new Error('Não é possível dividir por zero.');
      }
      if (operator === '*') value *= right;
      else if (operator === '/') value /= right;
      else value %= right;
    }
    return value;
  }

  function parsePower(): number {
    let value = parseUnary();
    skipSpaces();
    if (input[position] === '^') {
      position += 1;
      value = value ** parsePower();
    }
    return value;
  }

  function parseUnary(): number {
    skipSpaces();
    const operator = input[position];
    if (operator === '+' || operator === '-') {
      position += 1;
      const value = parseUnary();
      return operator === '-' ? -value : value;
    }
    return parsePrimary();
  }

  function parsePrimary(): number {
    skipSpaces();
    if (input[position] === '(') {
      position += 1;
      const value = parseExpression();
      skipSpaces();
      if (input[position] !== ')') throw new Error('Há um parêntese sem fechamento.');
      position += 1;
      return value;
    }

    const rest = input.slice(position);
    const match = rest.match(/^(?:\d+(?:[.,]\d*)?|[.,]\d+)/);
    if (!match) throw new Error('Use apenas números e operadores matemáticos.');
    position += match[0].length;
    const value = Number(match[0].replace(',', '.'));
    if (!Number.isFinite(value)) throw new Error('Número inválido.');
    return value;
  }

  const result = parseExpression();
  skipSpaces();
  if (position !== input.length) throw new Error('Não reconheci parte dessa expressão.');
  if (!Number.isFinite(result)) throw new Error('O resultado ultrapassa o limite numérico.');
  return result;
}

export function formatCalculation(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    maximumFractionDigits: 8,
    useGrouping: true,
  }).format(value);
}
