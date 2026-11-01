/**
 * Quanto tempo o JARVIS está trabalhando — e se ele travou.
 *
 * O pedido: *“o JARVIS só aparece com três pontinhos, mas como saber se ele está
 * trabalhando? não aparece tempo, nem o que ele está fazendo, nem se deu erro ou
 * travou”*.
 *
 * Três pontinhos animados não dizem nada: uma animação continua igual esteja a
 * skill rodando em 2 s ou travada há 4 min. Aqui ficam as três coisas que faltam
 * — rótulo do que está rodando, tempo decorrido e o limite que o servidor impõe
 * (`timeout_seconds` da skill) — sem inventar progresso que ninguém mede.
 */

export type Situacao = 'trabalhando' | 'demorando' | 'estourou';

export type Etapa = {
  /** O que está rodando, em português: “Arrumando a máquina (limpeza)”. */
  rotulo: string;
  /** Limite em segundos, igual ao `timeout_seconds` da skill no servidor. */
  limiteSegundos: number;
  /** `Date.now()` de quando o pedido saiu. */
  desde: number;
};

/** Limite padrão do agente local quando a skill não é conhecida antes. */
export const LIMITE_PADRAO_S = 120;

/**
 * Rótulo e limite deduzidos do pedido, antes de a API responder qual skill é.
 *
 * É dedução por palavra-chave, não entendimento: quando erra, o pior que
 * acontece é o rótulo dizer “Procurando a skill certa” em vez do nome exato. O
 * número do limite **não** é inventado para efeito visual — ele é o mesmo que o
 * servidor usa em `asyncio.wait_for`.
 */
export function rotuloDoPedido(texto: string): { rotulo: string; limiteSegundos: number } {
  const t = (texto || '').toLowerCase();
  if (/\bdesfaz|\bdesfazer|reverte|volta tudo/.test(t)) {
    return { rotulo: 'Desfazendo a última limpeza', limiteSegundos: 180 };
  }
  if (/arrum|limpa|faxina|sobra/.test(t)) {
    return { rotulo: 'Arrumando a máquina (limpeza)', limiteSegundos: 300 };
  }
  if (/analisa|analisar|resum|texto/.test(t)) {
    return { rotulo: 'Lendo o texto', limiteSegundos: 30 };
  }
  return { rotulo: 'Procurando a skill certa', limiteSegundos: LIMITE_PADRAO_S };
}

/** `00:07`, `01:23`, `12:05` — tempo decorrido, não previsão. */
export function formatarDecorrido(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutos = Math.floor(total / 60);
  const segundos = total % 60;
  return `${String(minutos).padStart(2, '0')}:${String(segundos).padStart(2, '0')}`;
}

/**
 * `demorando` entra em 40% do limite: tempo de o usuário ver que ainda anda. Não
 * é erro — só deixa de parecer travado.
 */
export function situacao(ms: number, limiteSegundos: number): Situacao {
  const limite = Math.max(1, limiteSegundos) * 1000;
  if (ms >= limite) return 'estourou';
  if (ms >= limite * 0.4) return 'demorando';
  return 'trabalhando';
}

/** A frase abaixo do rótulo. Curta, e sem prometer o que não se sabe. */
export function avisoDaSituacao(ms: number, limiteSegundos: number): string {
  const limite = Math.max(1, limiteSegundos);
  const caso = situacao(ms, limite);
  if (caso === 'estourou') {
    return `Passou do limite de ${limite} s: o servidor pode estar travado. Confira se a janela da API ainda está aberta.`;
  }
  if (caso === 'demorando') {
    return `Ainda rodando — o limite desta skill é ${limite} s. Pode cancelar sem estragar nada.`;
  }
  return `Limite desta skill: ${limite} s.`;
}
