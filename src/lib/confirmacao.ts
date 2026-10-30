/**
 * Qual valor vai no campo `autorizacao` de uma skill de host.
 *
 * Regra única para toda a interface (era o bug da 0.62.9): o texto que a pessoa
 * digitou no chat **nunca** é token. Antes, o "sim, pode" que liberava a
 * confirmação ia junto como autorização e a skill recusava com "token inválido",
 * mesmo a pessoa estando na própria máquina.
 *
 * - modo dono ligado (JARVIS_HOST_CONFIAR_LOCAL=1): manda vazio. Quem decide é o
 *   servidor, que preenche o token sozinho quando a requisição vem do próprio PC —
 *   e continua exigindo token de qualquer outra máquina da rede.
 * - modo dono desligado: manda o token que está na tela.
 */
export function autorizacaoParaConfirmar(modoDono: boolean, hostToken: string | null | undefined): string {
  if (modoDono) return '';
  return (hostToken ?? '').trim();
}
