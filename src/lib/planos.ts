/**
 * Leitura do plano de instalação devolvido por `sistema.instalar` /
 * `sistema.desinstalar`, e os parâmetros para executá-lo por `sistema.executar`.
 *
 * O plano chega no resultado da skill como `confirmacao` (código de uso único)
 * e uma lista `rows` de `{campo, valor}`. Este módulo transforma isso em algo
 * que a tela consegue mostrar sem adivinhar nada — se não houver código, não há
 * plano, e o botão "executar" não aparece.
 */

export interface PlanoDeInstalacao {
  confirmacao: string;
  alvo: string;
  tipo: string;
  comando: string;
  risco: string;
  sha256: string;
}

type Resultado = Record<string, unknown> | null | undefined;

function texto(valor: unknown): string {
  return typeof valor === 'string' ? valor : '';
}

export function planoDoResultado(resultado: Resultado): PlanoDeInstalacao | null {
  if (!resultado) return null;
  const confirmacao = texto(resultado.confirmacao);
  if (!confirmacao) return null;
  const rows = Array.isArray(resultado.rows) ? (resultado.rows as { campo?: unknown; valor?: unknown }[]) : [];
  const campo = (nome: string) => texto(rows.find((row) => row?.campo === nome)?.valor);
  return {
    confirmacao,
    alvo: campo('alvo'),
    tipo: campo('tipo'),
    comando: campo('comando'),
    risco: campo('risco'),
    sha256: campo('sha256'),
  };
}

/**
 * Parâmetros de `sistema.executar`.
 *
 * No modo dono o servidor preenche o token; sem ele, o token digitado no chat
 * (ou na tela) precisa ir junto, senão a execução é recusada.
 */
export function parametrosDeExecucao(
  plano: { confirmacao: string },
  opcoes: { hostToken?: string; modoDono?: boolean } = {},
): Record<string, unknown> {
  const parametros: Record<string, unknown> = { confirmacao: plano.confirmacao };
  const token = (opcoes.hostToken ?? '').trim();
  if (!opcoes.modoDono && token) parametros.autorizacao = token;
  return parametros;
}

/** Texto curto para o cabeçalho do cartão do plano. */
export function resumoDoPlano(plano: PlanoDeInstalacao): string {
  const partes = [plano.alvo || 'plano', plano.tipo, plano.risco ? `risco ${plano.risco}` : '']
    .filter((parte) => Boolean(parte))
    .join(' · ');
  return partes;
}
