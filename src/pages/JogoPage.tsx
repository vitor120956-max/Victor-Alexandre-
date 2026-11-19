import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CircleAlert,
  Gamepad2,
  Info,
  LoaderCircle,
  Package,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import {
  requestJogoAnalisar,
  requestJogos,
  uploadJogo,
} from '../lib/api';
import type { JogoLista, JogoRelatorio } from '../lib/api';
import '../jogo.css';

const EXTENSOES = ['.apk', '.aab', '.apks', '.xapk'];
const LIMITE_MB = 600;

function mb(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1).replace('.', ',')} MB`;
}

function aceita(nome: string): boolean {
  const minusculo = nome.toLowerCase();
  return EXTENSOES.some((extensao) => minusculo.endsWith(extensao));
}

const SEVERIDADE = {
  critico: { rotulo: 'CRÍTICO', Icone: CircleAlert },
  atencao: { rotulo: 'ATENÇÃO', Icone: AlertTriangle },
  info: { rotulo: 'INFO', Icone: Info },
} as const;

function gravidade(item: { severidade: string }): keyof typeof SEVERIDADE {
  return item.severidade === 'critico' || item.severidade === 'atencao' ? item.severidade : 'info';
}

export function JogoPage() {
  const [lista, setLista] = useState<JogoLista | null>(null);
  const [relatorio, setRelatorio] = useState<JogoRelatorio | null>(null);
  const [selecionada, setSelecionada] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [enviando, setEnviando] = useState<string[]>([]);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [arrastando, setArrastando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro('');
    try {
      const resposta = await requestJogos();
      setLista(resposta);
      return resposta;
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui listar os jogos.');
      return null;
    } finally {
      setCarregando(false);
    }
  }, []);

  const analisar = useCallback(async (pasta: string, arquivo: string) => {
    setSelecionada(pasta);
    setCarregando(true);
    setErro('');
    try {
      const resposta = await requestJogoAnalisar(`${pasta}/${arquivo}`);
      setRelatorio(resposta);
    } catch (falha) {
      setRelatorio(null);
      setErro(falha instanceof Error ? falha.message : 'Não consegui analisar o APK.');
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /** Envia os arquivos um por um: cada APK entra na pasta dele. */
  const enviar = useCallback(
    async (arquivos: File[]) => {
      const validos = arquivos.filter((arquivo) => aceita(arquivo.name));
      const recusados = arquivos.filter((arquivo) => !aceita(arquivo.name));
      if (recusados.length) {
        setAviso(
          `${recusados.map((arquivo) => arquivo.name).join(', ')} não é APK (aceito ${EXTENSOES.join(', ')}).`,
        );
      } else {
        setAviso('');
      }
      const grandes = validos.filter((arquivo) => arquivo.size > LIMITE_MB * 1_000_000);
      if (grandes.length) {
        setErro(`${grandes.map((arquivo) => arquivo.name).join(', ')} passa de ${LIMITE_MB} MB.`);
        return;
      }
      if (!validos.length) return;

      setErro('');
      setEnviando(validos.map((arquivo) => arquivo.name));
      const enviados: Array<{ parte: string; arquivo: string }> = [];
      for (const arquivo of validos) {
        try {
          const resultado = await uploadJogo(arquivo);
          enviados.push({ parte: resultado.parte, arquivo: arquivo.name });
        } catch (falha) {
          setErro(`${arquivo.name}: ${falha instanceof Error ? falha.message : 'falha no envio'}`);
        } finally {
          setEnviando((atual) => atual.filter((nome) => nome !== arquivo.name));
        }
      }
      const atualizada = await carregar();
      if (enviados.length) {
        setAviso(
          `${enviados.length} APK${enviados.length > 1 ? 's' : ''} guardado${enviados.length > 1 ? 's' : ''} `
          + `em ${enviados.map((item) => `${item.parte}/`).join(', ')}.`,
        );
        void analisar(enviados[0].parte, enviados[0].arquivo);
      }
      if (!atualizada) return;
    },
    [analisar, carregar],
  );

  const partes = lista?.partes ?? [];
  const soltos = useMemo(() => (lista?.jogos ?? []).filter((item) => !item.parte), [lista]);

  return (
    <main className="jogo-page">
      <header className="jogo-header">
        <div>
          <span className="eyebrow">SEU JOGO — ANÁLISE DO PACOTE</span>
          <h1>Meu jogo<span>.</span></h1>
          <p>
            Arraste o APK aqui. Cada pacote fica na <strong>própria pasta</strong>, com o APK e a
            análise juntos — dois testes não se misturam. Nada é descompactado, descompilado ou
            enviado para fora do seu PC.
          </p>
        </div>
        <button className="button button-ghost" onClick={() => void carregar()} disabled={carregando}>
          <RefreshCw size={14} /> Atualizar
        </button>
      </header>

      <section
        className={`jogo-drop${arrastando ? ' is-over' : ''}`}
        onDragOver={(evento) => {
          evento.preventDefault();
          setArrastando(true);
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(evento) => {
          evento.preventDefault();
          setArrastando(false);
          void enviar(Array.from(evento.dataTransfer.files));
        }}
      >
        <Gamepad2 size={26} />
        <div>
          <strong>{arrastando ? 'Solte o APK aqui' : 'Jogue o APK (ou os dois) nesta área'}</strong>
          <span>
            ou <button type="button" onClick={() => entrada.current?.click()}>escolha o arquivo</button>
            {' '}— aceita {EXTENSOES.join(', ')} até {LIMITE_MB} MB, vários de uma vez
          </span>
        </div>
        <input
          ref={entrada}
          type="file"
          multiple
          accept={EXTENSOES.join(',')}
          onChange={(evento) => {
            void enviar(Array.from(evento.target.files ?? []));
            evento.target.value = '';
          }}
        />
      </section>

      {enviando.length > 0 && (
        <p className="jogo-status"><LoaderCircle className="jogo-spin" size={14} /> Enviando {enviando.join(', ')}…</p>
      )}
      {aviso && <p className="jogo-status is-ok"><Check size={14} /> {aviso}</p>}
      {erro && <p className="jogo-status is-error"><CircleAlert size={14} /> {erro}</p>}

      <div className="jogo-layout">
        <section className="jogo-lista">
          <h2>Pacotes guardados</h2>
          <p className="jogo-hint">
            {lista ? `${lista.pasta}` : 'carregando…'}
          </p>
          {!partes.length && !soltos.length && !carregando && (
            <p className="jogo-vazio">
              Nenhum APK ainda. Arraste o arquivo acima — ou, se preferir, use o
              <code> analisar-jogo.bat </code> no Windows.
            </p>
          )}
          {partes.map((parte) => (
            <button
              key={parte.nome}
              className={`jogo-item${selecionada === parte.nome ? ' is-selected' : ''}`}
              onClick={() => void analisar(parte.nome, parte.apks[0])}
            >
              <Package size={16} />
              <span>
                <strong>{parte.nome}/</strong>
                <small>{parte.apks.join(', ')} · {mb(parte.bytes)}</small>
              </span>
              <em className={parte.analisado ? 'is-ok' : ''}>
                {parte.analisado ? 'analisado' : 'novo'}
              </em>
            </button>
          ))}
          {soltos.map((item) => (
            <button
              key={item.nome}
              className={`jogo-item${selecionada === item.nome ? ' is-selected' : ''}`}
              onClick={() => void analisar('', item.nome)}
            >
              <Package size={16} />
              <span>
                <strong>{item.nome}</strong>
                <small>solto em jogos/ (formato antigo) · {mb(item.bytes)}</small>
              </span>
            </button>
          ))}
        </section>

        <section className="jogo-analise">
          {carregando && !relatorio && <p className="jogo-status"><LoaderCircle className="jogo-spin" size={14} /> lendo o pacote…</p>}
          {!relatorio && !carregando && (
            <p className="jogo-vazio">
              Escolha um pacote à esquerda para ver a análise — ou arraste um APK novo.
            </p>
          )}
          {relatorio && (
            <>
              <header className="jogo-analise-topo">
                <div>
                  <h2>{relatorio.arquivo}</h2>
                  <p>
                    {[relatorio.pacote, relatorio.versao && `versão ${relatorio.versao}`,
                      relatorio.motor && `${relatorio.motor}${relatorio.versaoDoMotor ? ` ${relatorio.versaoDoMotor}` : ''}`]
                      .filter(Boolean).join(' · ') || 'manifesto não lido'}
                  </p>
                </div>
                {relatorio.parte && <span className="jogo-parte">jogos/{relatorio.parte}/</span>}
              </header>

              <div className="jogo-metricas">
                <article><span>Tamanho</span><strong>{mb(relatorio.tamanhoDescompactado)}</strong><small>descompactado</small></article>
                <article><span>Arquivos</span><strong>{relatorio.entradas}</strong><small>dentro do pacote</small></article>
                <article><span>Android</span><strong>{relatorio.minSdk || '?'} → {relatorio.targetSdk || '?'}</strong><small>minSdk → targetSdk</small></article>
                <article>
                  <span>Assinatura</span>
                  <strong>
                    {[relatorio.assinatura.v2v3 && 'v2/v3', relatorio.assinatura.v1 && 'v1'].filter(Boolean).join(' + ') || 'nenhuma'}
                  </strong>
                  <small>{relatorio.assinatura.v2v3 ? 'conferida pelo Android' : 'sem bloco v2/v3'}</small>
                </article>
              </div>

              <p className="jogo-abis">
                <ShieldCheck size={13} /> ABIs: {relatorio.abis.join(', ') || 'nenhuma'} · DEX: {relatorio.dexes}
                {' '}· permissões: {relatorio.permissoes.length}
              </p>

              <h3 className="jogo-titulo-achados">
                {relatorio.achados.length
                  ? `${relatorio.achados.length} ponto${relatorio.achados.length > 1 ? 's' : ''} para melhorar`
                  : 'Nada errado no pacote'}
              </h3>

              {relatorio.achados.map((achado, indice) => {
                const nivel = gravidade(achado);
                const { rotulo, Icone } = SEVERIDADE[nivel];
                return (
                  <article key={`${indice}-${achado.titulo}`} className={`jogo-achado is-${nivel}`}>
                    <header><Icone size={14} /><em>{rotulo}</em><strong>{achado.titulo}</strong></header>
                    {achado.o_que_e && <p><b>O que é:</b> {achado.o_que_e}</p>}
                    {achado.por_que_importa && <p><b>Por que importa:</b> {achado.por_que_importa}</p>}
                    {achado.como_melhorar && <p><b>Como melhorar:</b> {achado.como_melhorar}</p>}
                    {achado.onde && <p className="jogo-onde"><b>Onde:</b> {achado.onde}</p>}
                  </article>
                );
              })}

              {relatorio.maiores.length > 0 && (
                <>
                  <h3 className="jogo-titulo-achados">Maiores arquivos</h3>
                  <ul className="jogo-maiores">
                    {relatorio.maiores.slice(0, 8).map((item) => (
                      <li key={item.nome}>
                        <span>{item.mb.toFixed(1).replace('.', ',')} MB</span>
                        <code>{item.nome}</code>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <p className="jogo-rodape">
                Análise feita no seu PC, sem enviar o APK para lugar nenhum. Isto é o que se vê do
                pacote pronto: equilíbrio, controles e ritmo só você decide — e o ajuste é feito no
                motor, antes de gerar o APK de novo.
              </p>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
