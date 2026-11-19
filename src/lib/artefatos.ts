/**
 * Quais arquivos a Reversa aceita — decidido antes de mandar, e com motivo.
 *
 * 0.91.43. O pedido veio de uma pergunta simples (“o engenharia reversa tá
 * funcionando?”) e da conferência dela. Funcionava, mas em dois pontos
 * **falhava calado**:
 *
 * 1. escolher um APK de 90 MB deixava o botão “Confirmar upload” **morto**, sem
 *    uma linha de explicação — o aviso só existia dentro do envio, que nunca
 *    acontecia porque o botão estava desabilitado;
 * 2. arrastar uma pasta com arquivos grandes ou de extensão estranha
 *    **descartava esses arquivos em silêncio**, e a tela ainda dizia que a
 *    pasta tinha sido enviada.
 *
 * Silêncio é o pior resultado: a pessoa acha que o JARVIS não funciona. Aqui a
 * triagem é uma função pura (por isso é testável sem navegador) que devolve o
 * que entra, o que fica de fora e **por quê**.
 */

export type MotivoRecusa = 'grande' | 'formato' | 'oculto' | 'vazio';

export type Recusado = { nome: string; motivo: MotivoRecusa; bytes: number };

export type Triagem = {
  aceitos: File[];
  recusados: Recusado[];
  totalBytes: number;
  /** O lote passou do teto total (o envio para até aqui, mas avisa). */
  excedeTotal: boolean;
  /** Passou do número máximo de arquivos por lote. */
  excedeQuantidade: boolean;
};

export type OpcoesTriagem = {
  limiteBytes: number;
  extensoes: ReadonlySet<string>;
  limiteTotalBytes?: number;
  limiteArquivos?: number;
};

/** O nome relativo do arquivo (a pasta, quando o navegador manda). */
export function caminhoDoArquivo(arquivo: File): string {
  const comPasta = arquivo as File & { webkitRelativePath?: string };
  return comPasta.webkitRelativePath || arquivo.name;
}

/** Extensão em minúsculas, com o ponto. Nome sem ponto devolve string vazia. */
export function extensao(nome: string): string {
  const corte = nome.lastIndexOf('.');
  return corte <= 0 ? '' : nome.slice(corte).toLowerCase();
}

export function classificarArquivos(arquivos: File[], opcoes: OpcoesTriagem): Triagem {
  const aceitos: File[] = [];
  const recusados: Recusado[] = [];

  for (const arquivo of arquivos) {
    const relativo = caminhoDoArquivo(arquivo);
    const partes = relativo.split('/');
    if (partes.some((parte) => parte.startsWith('.'))) {
      recusados.push({ nome: relativo, motivo: 'oculto', bytes: arquivo.size });
      continue;
    }
    if (arquivo.size <= 0) {
      recusados.push({ nome: relativo, motivo: 'vazio', bytes: arquivo.size });
      continue;
    }
    if (arquivo.size > opcoes.limiteBytes) {
      recusados.push({ nome: relativo, motivo: 'grande', bytes: arquivo.size });
      continue;
    }
    if (!opcoes.extensoes.has(extensao(arquivo.name))) {
      recusados.push({ nome: relativo, motivo: 'formato', bytes: arquivo.size });
      continue;
    }
    aceitos.push(arquivo);
  }

  const totalBytes = aceitos.reduce((soma, arquivo) => soma + arquivo.size, 0);
  return {
    aceitos,
    recusados,
    totalBytes,
    excedeTotal: Boolean(opcoes.limiteTotalBytes) && totalBytes > (opcoes.limiteTotalBytes ?? 0),
    excedeQuantidade:
      Boolean(opcoes.limiteArquivos) && aceitos.length > (opcoes.limiteArquivos ?? 0),
  };
}

/** “1,5 MB” — só para as mensagens. */
function tamanho(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1).replace('.', ',')} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(0)} KB`;
  return `${bytes} B`;
}

/**
 * A frase que a pessoa lê. Para APK grande, diz **onde** ele entra — foi o
 * caso do dono: o APK do jogo não cabe na Reversa (25 MB) e tem aba própria.
 */
export function explicarRecusa(recusado: Recusado, limiteBytes: number): string {
  const limite = tamanho(limiteBytes);
  switch (recusado.motivo) {
    case 'grande': {
      const eApk = /\.(apk|aab|apks|xapk)$/i.test(recusado.nome);
      if (eApk) {
        return (
          `“${recusado.nome}” tem ${tamanho(recusado.bytes)} e a Reversa aceita até ${limite}. `
          + 'Para o APK do seu jogo use a aba “Meu jogo” (até 600 MB): ela lê o manifesto, '
          + 'descobre o motor e diz o que melhorar.'
        );
      }
      return `“${recusado.nome}” tem ${tamanho(recusado.bytes)} e a Reversa aceita até ${limite} por arquivo.`;
    }
    case 'formato':
      return `“${recusado.nome}” não é um formato que a Reversa lê.`;
    case 'oculto':
      return `“${recusado.nome}” está em pasta oculta e não entra.`;
    case 'vazio':
      return `“${recusado.nome}” está vazio.`;
  }
}

/** O resumo de uma triagem, pronto para a tela. String vazia = tudo entrou. */
export function resumoDaTriagem(
  triagem: Triagem,
  opcoes: { limiteBytes: number; limiteTotalBytes?: number; limiteArquivos?: number },
): string {
  const linhas: string[] = [];
  if (triagem.recusados.length) {
    const motivos = triagem.recusados.map((item) => explicarRecusa(item, opcoes.limiteBytes));
    // Muitos arquivos recusados: cita os três primeiros e conta o resto.
    const mostrados = motivos.slice(0, 3);
    const resto = motivos.length - mostrados.length;
    linhas.push(mostrados.join(' '));
    if (resto > 0) linhas.push(`E mais ${resto} arquivo${resto > 1 ? 's' : ''} fora pelos mesmos motivos.`);
  }
  if (triagem.excedeQuantidade && opcoes.limiteArquivos) {
    linhas.push(`O lote passa de ${opcoes.limiteArquivos} arquivos; envie em partes.`);
  }
  if (triagem.excedeTotal && opcoes.limiteTotalBytes) {
    linhas.push(`O lote passa de ${tamanho(opcoes.limiteTotalBytes)} no total; envie menos por vez.`);
  }
  return linhas.join(' ');
}
