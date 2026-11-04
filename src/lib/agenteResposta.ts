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

/**
 * A resposta veio de uma skill de verdade?
 *
 * Com o cérebro ligado, o chat tenta a skill antes do modelo (0.79.0). Só a
 * resposta da skill vale a pena mostrar; `nada` e `sugerir` são o sinal de que
 * o modelo deve responder.
 *
 * `faltando` só conta com confiança alta: no meio da faixa o agente apenas
 * suspeita ("parece a skill X, mas falta um campo") — e aí uma pergunta sobre
 * um formulário errado é pior do que a resposta do modelo.
 */
export function respostaVeioDeSkill(resultado: AgenteResultado): boolean {
  if (['executado', 'criado', 'guardado', 'biblioteca', 'confirmar'].includes(resultado.acao)) {
    return Boolean(resultado.resposta.trim()) || resultado.acao === 'confirmar';
  }
  return resultado.acao === 'faltando' && resultado.confianca >= 0.5;
}
