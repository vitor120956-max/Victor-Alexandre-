import { describe, expect, it } from 'vitest';
import {
  classificarArquivos,
  extensao,
  explicarRecusa,
  resumoDaTriagem,
  type Triagem,
} from './artefatos';

/**
 * 0.91.43 — a triagem da Reversa, que antes falhava calada.
 *
 * Dois defeitos reais, encontrados ao responder “o engenharia reversa tá
 * funcionando?”:
 *
 * 1. escolher um APK de 90 MB deixava o botão morto, sem explicação;
 * 2. arrastar uma pasta descartava arquivos grandes/formato estranho em
 *    silêncio — e a tela ainda dizia “pasta enviada”.
 */

const EXTENSOES = new Set(['.apk', '.js', '.elf', '.png', '.zip']);

function fake(nome: string, bytes: number, pasta = ''): File {
  const arquivo = new File([new Uint8Array(1)], nome);
  Object.defineProperty(arquivo, 'size', { value: bytes });
  if (pasta) {
    Object.defineProperty(arquivo, 'webkitRelativePath', { value: `${pasta}/${nome}` });
  }
  return arquivo;
}

describe('extensão', () => {
  it('devolve com ponto e em minúsculas', () => {
    expect(extensao('Jogo.APK')).toBe('.apk');
    expect(extensao('dados.tar.gz')).toBe('.gz');
  });

  it('nome sem ponto não inventa extensão', () => {
    expect(extensao('README')).toBe('');
    expect(extensao('.env')).toBe('');
  });
});

describe('classificarArquivos', () => {
  const limite = 25_000_000;

  it('aceita o que cabe e tem formato conhecido', () => {
    const triagem = classificarArquivos([fake('app.js', 1000), fake('lib.elf', 5000)], {
      limiteBytes: limite,
      extensoes: EXTENSOES,
    });
    expect(triagem.aceitos.map((arquivo) => arquivo.name)).toEqual(['app.js', 'lib.elf']);
    expect(triagem.recusados).toEqual([]);
    expect(triagem.totalBytes).toBe(6000);
  });

  it('recusa o grande COM motivo, em vez de sumir com ele', () => {
    // o caso do dono: APK de 90 MB na Reversa (teto 25 MB)
    const triagem = classificarArquivos([fake('meu-jogo.apk', 90_000_000)], {
      limiteBytes: limite,
      extensoes: EXTENSOES,
    });
    expect(triagem.aceitos).toHaveLength(0);
    expect(triagem.recusados).toEqual([
      { nome: 'meu-jogo.apk', motivo: 'grande', bytes: 90_000_000 },
    ]);
  });

  it('separa cada motivo: formato, oculto, vazio', () => {
    const triagem = classificarArquivos(
      [
        fake('nota.exe', 100), // extensão fora da lista
        fake('.escondido.js', 100, 'app'), // pasta/arquivo oculto
        fake('vazio.js', 0),
        fake('ok.js', 10),
      ],
      { limiteBytes: limite, extensoes: EXTENSOES },
    );
    expect(triagem.aceitos.map((arquivo) => arquivo.name)).toEqual(['ok.js']);
    expect(triagem.recusados.map((item) => item.motivo)).toEqual(['formato', 'oculto', 'vazio']);
  });

  it('olha o caminho relativo quando vem de pasta (o oculto pode estar no meio)', () => {
    const triagem = classificarArquivos([fake('app.js', 10, 'projeto/.git')], {
      limiteBytes: limite,
      extensoes: EXTENSOES,
    });
    expect(triagem.aceitos).toHaveLength(0);
    expect(triagem.recusados[0]).toMatchObject({ motivo: 'oculto', nome: 'projeto/.git/app.js' });
  });

  it('acusa o lote acima do total e acima da quantidade', () => {
    // cada um cabe sozinho (20 MB < 25 MB), mas três somam 60 MB > 50 MB
    const triagem = classificarArquivos(
      [fake('a.js', 20_000_000), fake('b.js', 20_000_000), fake('c.js', 20_000_000)],
      { limiteBytes: limite, extensoes: EXTENSOES, limiteTotalBytes: 50_000_000, limiteArquivos: 2 },
    );
    expect(triagem.aceitos).toHaveLength(3);
    expect(triagem.recusados).toEqual([]);
    expect(triagem.excedeTotal).toBe(true);
    expect(triagem.excedeQuantidade).toBe(true);
  });

  it('sem teto de lote, não inventa problema', () => {
    const triagem = classificarArquivos([fake('a.js', 10)], { limiteBytes: limite, extensoes: EXTENSOES });
    expect(triagem.excedeTotal).toBe(false);
    expect(triagem.excedeQuantidade).toBe(false);
  });
});

describe('explicarRecusa', () => {
  it('APK grande manda para a aba Meu jogo — foi o caso do dono', () => {
    const frase = explicarRecusa(
      { nome: 'meu-jogo.apk', motivo: 'grande', bytes: 90_000_000 },
      25_000_000,
    );
    expect(frase).toContain('Meu jogo');
    expect(frase).toContain('2 GB');
    expect(frase).toContain('90,0 MB');
    expect(frase).toContain('25,0 MB');
  });

  it('arquivo grande que não é APK não manda para a aba errada', () => {
    const frase = explicarRecusa({ nome: 'filme.zip', motivo: 'grande', bytes: 40_000_000 }, 25_000_000);
    expect(frase).not.toContain('Meu jogo');
    expect(frase).toContain('40,0 MB');
  });

  it('cada motivo tem a sua frase', () => {
    expect(explicarRecusa({ nome: 'x.exe', motivo: 'formato', bytes: 1 }, 25_000_000)).toContain('formato');
    expect(explicarRecusa({ nome: '.a/b.js', motivo: 'oculto', bytes: 1 }, 25_000_000)).toContain('oculta');
    expect(explicarRecusa({ nome: 'v.js', motivo: 'vazio', bytes: 0 }, 25_000_000)).toContain('vazio');
  });
});

describe('resumoDaTriagem', () => {
  const base = { limiteBytes: 25_000_000, limiteTotalBytes: 100_000_000, limiteArquivos: 30 };

  it('tudo entrou: resumo vazio', () => {
    const triagem: Triagem = {
      aceitos: [fake('a.js', 10)],
      recusados: [],
      totalBytes: 10,
      excedeTotal: false,
      excedeQuantidade: false,
    };
    expect(resumoDaTriagem(triagem, base)).toBe('');
  });

  it('cita os três primeiros e conta o resto', () => {
    const recusados = Array.from({ length: 5 }, (_, indice) => ({
      nome: `grande-${indice}.apk`,
      motivo: 'grande' as const,
      bytes: 90_000_000,
    }));
    const resumo = resumoDaTriagem(
      { aceitos: [], recusados, totalBytes: 0, excedeTotal: false, excedeQuantidade: false },
      base,
    );
    expect(resumo).toContain('grande-0.apk');
    expect(resumo).toContain('grande-2.apk');
    expect(resumo).not.toContain('grande-4.apk');
    expect(resumo).toContain('E mais 2 arquivos');
  });

  it('avisa o lote acima do total', () => {
    const resumo = resumoDaTriagem(
      { aceitos: [], recusados: [], totalBytes: 120_000_000, excedeTotal: true, excedeQuantidade: false },
      base,
    );
    expect(resumo).toContain('100,0 MB');
    expect(resumo).toContain('menos por vez');
  });
});
