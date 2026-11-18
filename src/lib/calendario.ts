/**
 * O dia de hoje, em português, sem passar pelo modelo (0.91.37).
 *
 * A pergunta do dono, em 18/11:
 *
 *     e se eu perguntar para o javis q dia e hj proximos feriados quantos dias
 *     faltam para final de semana hj e quarta quinta...?
 *
 * “Que dia é hoje” já funcionava. As outras três não: “quantos dias faltam para
 * o fim de semana”, “hoje é quarta?” e os feriados caíam em `unknown` e iam para
 * o modelo — que não tem relógio. Ele acerta o dia da semana por sorte e chuta o
 * Carnaval com a mesma confiança com que acerta o Natal.
 *
 * Aqui a conta é local e pura: dia da semana, quanto falta para o sábado e a
 * conferência de um palpite (“hoje é quinta?”). Não depende da API, então
 * funciona com o servidor fora do ar — e a resposta diz isso. As datas de
 * **feriado** ficam no `server/calendario.py`, porque dependem de lei e de
 * Páscoa, e uma segunda cópia aqui só criaria duas verdades.
 */

export const DIAS_SEMANA = [
  'domingo',
  'segunda-feira',
  'terça-feira',
  'quarta-feira',
  'quinta-feira',
  'sexta-feira',
  'sábado',
] as const;

export type DiaSemana = (typeof DIAS_SEMANA)[number];

/** “quarta”, “quarta-feira”, “qua” → 3. Palpite que não é dia volta -1. */
export function numeroDoDia(palpite: string): number {
  const limpo = palpite
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s*-?\s*feira/g, '')
    .replace(/[^a-z]/g, '')
    .trim();
  const nomes: Record<string, number> = {
    domingo: 0,
    dom: 0,
    segunda: 1,
    seg: 1,
    terca: 2,
    ter: 2,
    quarta: 3,
    qua: 3,
    quinta: 4,
    qui: 4,
    sexta: 5,
    sex: 5,
    sabado: 6,
    sab: 6,
  };
  return nomes[limpo] ?? -1;
}

export function diaDaSemana(quando: Date): DiaSemana {
  return DIAS_SEMANA[quando.getDay()];
}

/** Dias até o próximo sábado: 0 = hoje é sábado, 6 = domingo. */
export function diasAteSabado(quando: Date): number {
  return (6 - quando.getDay()) % 7;
}

function dataBR(quando: Date): string {
  return quando.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function comDia(quando: Date): string {
  return `${diaDaSemana(quando)}, ${dataBR(quando)}`;
}

function fraseDoFimDeSemana(quando: Date): string {
  const faltam = diasAteSabado(quando);
  const sabado = new Date(quando.getTime());
  sabado.setDate(sabado.getDate() + faltam);
  if (faltam === 0) return `Hoje é sábado: o fim de semana é agora.`;
  if (quando.getDay() === 0) {
    return `É domingo — o fim de semana está acabando. O próximo sábado é ${dataBR(sabado)}, em ${faltam} dias.`;
  }
  if (faltam === 1) return `Falta 1 dia para o sábado (${dataBR(sabado)}).`;
  return `Faltam ${faltam} dias para o sábado (${dataBR(sabado)}).`;
}

/** O texto de “que dia é hoje”, com o que falta para o fim de semana. */
export function resumoDoDia(base: Date = new Date()): string {
  return `Hoje é ${comDia(base)}. ${fraseDoFimDeSemana(base)}`;
}

/** O texto de “e amanhã?”. */
export function resumoDeAmanha(base: Date = new Date()): string {
  const amanha = new Date(base.getTime());
  amanha.setDate(amanha.getDate() + 1);
  return `Amanhã é ${comDia(amanha)}. ${fraseDoFimDeSemana(amanha)}`;
}

/**
 * Confere um palpite: “hoje é quarta?”.
 *
 * Acertar o dia é fácil; o difícil é dizer **que dia é** quando a pessoa erra —
 * por isso a resposta traz o dia certo e, se fizer sentido, o “é amanhã”.
 */
export function conferirDia(palpite: string, base: Date = new Date()): string {
  const alvo = numeroDoDia(palpite);
  const hoje = base.getDay();
  const certo = comDia(base);
  if (alvo < 0) return `Não entendi “${palpite}” como dia da semana. Hoje é ${certo}.`;
  if (alvo === hoje) return `Sim: hoje é ${certo}.`;
  const amanha = (hoje + 1) % 7;
  const ontem = (hoje + 6) % 7;
  if (alvo === amanha) return `Não — hoje é ${certo}. ${DIAS_SEMANA[alvo]} é amanhã.`;
  if (alvo === ontem) return `Não — hoje é ${certo}. ${DIAS_SEMANA[alvo]} foi ontem.`;
  const faltam = (alvo - hoje + 7) % 7;
  return `Não — hoje é ${certo}. ${DIAS_SEMANA[alvo]} é em ${faltam} dias.`;
}

/** Nomes de dia que o parser reconhece numa frase (“hoje é quinta?”). */
export const NOMES_DE_DIA = Object.keys({
  domingo: 0,
  segunda: 1,
  terça: 2,
  terca: 2,
  quarta: 3,
  quinta: 4,
  sexta: 5,
  sábado: 6,
  sabado: 6,
});

/**
 * “Quantos dias faltam para sexta?” — a resposta é a data, não uma estimativa.
 * `alvo` pode ser qualquer dia; “fim de semana” é resolvido para sábado antes.
 */
export function contagemPara(alvo: string, base: Date = new Date()): string {
  const numero = numeroDoDia(alvo);
  if (numero < 0) return `Não entendi “${alvo}” como dia da semana. Hoje é ${comDia(base)}.`;
  const faltam = (numero - base.getDay() + 7) % 7;
  const quando = new Date(base.getTime());
  quando.setDate(quando.getDate() + faltam);
  if (faltam === 0) return `${DIAS_SEMANA[numero]} é hoje (${dataBR(base)}).`;
  if (faltam === 1) return `Falta 1 dia para ${DIAS_SEMANA[numero]} (${dataBR(quando)}).`;
  return `Faltam ${faltam} dias para ${DIAS_SEMANA[numero]} (${dataBR(quando)}).`;
}
