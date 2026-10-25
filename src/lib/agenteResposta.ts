import type { AgenteResultado } from './api';

/**
 * Monta o texto que vai para o chat a partir da resposta do agente local.
 *
 * O aviso que já aparece dentro da resposta não é repetido no fim — era o que
 * fazia a mesma frase sair duas vezes na tela.
 */
export function montarRespostaAgente(resultado: AgenteResultado): string {
  const corpo = resultado.resposta.trim();
  const avisos = resultado.avisos
    .map((aviso) => aviso.trim())
    .filter((aviso) => aviso && !corpo.includes(aviso));
  return [corpo, ...avisos].filter(Boolean).join('\n\n');
}
