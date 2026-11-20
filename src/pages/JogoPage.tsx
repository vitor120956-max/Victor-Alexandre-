import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CircleAlert,
  FileArchive,
  Gamepad2,
  Info,
  LoaderCircle,
  Package,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Upload,
} from 'lucide-react';
import {
  requestJogoAnalisar,
  requestJogosWeb,
  requestJogos,
  uploadJogo,
  uploadJogoWeb,
} from '../lib/api';
import type { JogoIphone, JogoLista, JogoRelatorio, JogoWebLista } from '../lib/api';
import '../jogo.css';

// 0.91.45 — o OBB entrou na lista: é onde mora quase todo o peso do jogo, e o
// dono perguntou por que ele não era analisado. O nome, o tamanho, o conteúdo
// (quando abre como ZIP) e a conferência com o APK agora são lidos.
const EXTENSOES = ['.apk', '.aab', '.apks', '.xapk', '.obb'];

/** `main`/`patch` + versão, do nome do OBB — só para o rótulo. */
function tipoDoObb(nome: string): string {
  const achado = /^(main|patch)\.(\d+)\./i.exec(nome);
  return achado ? `${achado[1].toLowerCase()} · versão ${achado[2]}` : 'nome fora do padrão';
}

function conferencia(obb: { conferencia: { pacote: string; versaoCodigo: string } }): {
  texto: string;
  nivel: 'ok' | 'erro' | 'neutro';
} {
  const { pacote, versaoCodigo } = obb.conferencia;
  if (pacote === 'diferente' || versaoCodigo === 'diferente') return { texto: 'NÃO confere', nivel: 'erro' };
  if (pacote === 'igual' && versaoCodigo === 'igual') return { texto: 'confere', nivel: 'ok' };
  return { texto: 'sem APK para conferir', nivel: 'neutro' };
}

// 0.91.44 — o dono perguntou “e se o jogo tiver 1 GB?”. O teto era 600 MB.
// O envio sempre foi em pedaços (a memória do servidor não cresce com o
// arquivo), então o teto novo é 2 GB; o número da tela tem de ser o mesmo que
// o servidor cobra em `server/jogo.py` (`MAXIMO_BYTES`).
const LIMITE_BYTES = 2_000_000_000;
const LIMITE_TEXTO = '2 GB';

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

/**
 * O veredito do iPhone para o pacote aberto (0.92.1).
 *
 * O dono arrastou dois APKs e pediu “passar para o iPhone de graça”. A resposta
 * depende do pacote — jogo com projeto no motor tem export web; cliente
 * alternativo do YouTube e microG não têm nada. O texto vem do servidor, não é
 * escrito na tela: assim a tela e o relatório não divergem.
 */
function CartaoIphone({ iphone }: { iphone: JogoIphone }) {
  const [aberto, setAberto] = useState(false);
  const tom = iphone.possivel ? 'ok' : iphone.tipo === 'dados' || iphone.tipo === 'desconhecido' ? 'neutro' : 'nao';
  return (
    <section className={`jogo-iphone is-${tom}`}>
      <header>
        <Smartphone size={15} />
        <div>
          <span className="jogo-iphone-rotulo">NO IPHONE, DE GRAÇA</span>
          <strong>{iphone.veredito}</strong>
        </div>
        <em>{iphone.possivel ? 'dá' : iphone.gratis ? 'pago' : 'não dá'}</em>
      </header>
      <p>{iphone.porque}</p>
      <button type="button" className="jogo-iphone-toggle" onClick={() => setAberto((valor) => !valor)}>
        {aberto ? 'Esconder o passo a passo' : `Ver o passo a passo (${iphone.passos.length})`}
      </button>
      {aberto && (
        <>
          <ol className="jogo-iphone-passos">
            {iphone.passos.map((passo, indice) => <li key={indice}>{passo}</li>)}
          </ol>
          <p className="jogo-iphone-custo"><b>Custo:</b> {iphone.custo}</p>
        </>
      )}
      <p className="jogo-iphone-limite"><b>Limite:</b> {iphone.limite}</p>
      <p className="jogo-iphone-fonte">lido de: {iphone.fonte}</p>
    </section>
  );
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
  const [web, setWeb] = useState<JogoWebLista | null>(null);
  const [enviandoWeb, setEnviandoWeb] = useState(false);
  const [avisoWeb, setAvisoWeb] = useState('');
  const [erroWeb, setErroWeb] = useState('');
  const entrada = useRef<HTMLInputElement>(null);
  const entradaWeb = useRef<HTMLInputElement>(null);

  const carregarWeb = useCallback(async () => {
    try {
      setWeb(await requestJogosWeb());
    } catch {
      setWeb(null); // a área do iPhone é um extra: falhar aqui não derruba a análise
    }
  }, []);

  useEffect(() => { void carregarWeb(); }, [carregarWeb]);

  const enviarWeb = useCallback(async (arquivo: File) => {
    setErroWeb('');
    setAvisoWeb('');
    setEnviandoWeb(true);
    try {
      const resultado = await uploadJogoWeb(arquivo);
      setAvisoWeb(`${resultado.nome}: ${resultado.arquivos} arquivo(s), pronto para servir no iPhone.`);
      await carregarWeb();
    } catch (falha) {
      setErroWeb(falha instanceof Error ? falha.message : 'Não consegui guardar o export.');
    } finally {
      setEnviandoWeb(false);
    }
  }, [carregarWeb]);

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
          `${recusados.map((arquivo) => arquivo.name).join(', ')} não é APK nem OBB `
          + `(aceito ${EXTENSOES.join(', ')}).`,
        );
      } else {
        setAviso('');
      }
      const grandes = validos.filter((arquivo) => arquivo.size > LIMITE_BYTES);
      if (grandes.length) {
        // Dizer o número **e** o caminho: um arquivo de 3 GB não fica menor por
        // insistir. Desde a 0.91.45 o OBB é analisado, então a saída é dividir
        // em main + patch ou usar Play Asset Delivery — não “tirar o OBB”.
        setErro(
          `${grandes.map((arquivo) => `${arquivo.name} (${mb(arquivo.size)})`).join(', ')} `
          + `passa de ${LIMITE_TEXTO}. Acima disso, divida os dados em main + patch `
          + '(até 2 GB cada) ou use Play Asset Delivery com o AAB.',
        );
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
          `${enviados.length} arquivo${enviados.length > 1 ? 's' : ''} guardado${enviados.length > 1 ? 's' : ''} `
          + `em ${enviados.map((item) => `${item.parte}/`).join(', ')}.`,
        );
        // Depois do envio, abrir a análise do APK da pasta (ou do OBB, quando
        // é o primeiro arquivo que chegou): o relatório do APK já traz o OBB.
        const parteNova = atualizada?.partes.find((parte) => parte.nome === enviados[0].parte);
        const alvo = parteNova?.apks[0] ?? enviados[0].arquivo;
        void analisar(enviados[0].parte, alvo);
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
            Arraste o APK aqui — e o <strong>OBB</strong> junto, se o jogo tiver um. Cada pacote fica
            na <strong>própria pasta</strong>, com o APK, o OBB e a análise juntos. O OBB é lido de
            verdade: nome, tamanho, conteúdo (quando abre como ZIP) e a conferência de pacote e
            versão contra o APK. Nada é descompactado, descompilado ou enviado para fora do seu PC.
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
          <strong>{arrastando ? 'Solte o APK (ou o OBB) aqui' : 'Jogue o APK e o OBB nesta área'}</strong>
          <span>
            ou <button type="button" onClick={() => entrada.current?.click()}>escolha o arquivo</button>
            {' '}— aceita {EXTENSOES.join(', ')} até {LIMITE_TEXTO}, vários de uma vez
            {' '}(o OBB vai para a pasta do APK do mesmo jogo)
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
          {partes.map((parte) => {
            const alvo = parte.apks[0] ?? parte.obbs[0];
            return (
              <button
                key={parte.nome}
                className={`jogo-item${selecionada === parte.nome ? ' is-selected' : ''}`}
                onClick={() => alvo && void analisar(parte.nome, alvo)}
                disabled={!alvo}
              >
                {parte.apks.length ? <Package size={16} /> : <FileArchive size={16} />}
                <span>
                  <strong>{parte.nome}/</strong>
                  <small>
                    {[
                      parte.apks.join(', '),
                      parte.obbs.length ? `OBB: ${parte.obbs.join(', ')}` : '',
                    ].filter(Boolean).join(' · ')} · {mb(parte.bytes)}
                  </small>
                </span>
                <em className={parte.analisado ? 'is-ok' : ''}>
                  {parte.analisado ? 'analisado' : 'novo'}
                </em>
              </button>
            );
          })}
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
                    {relatorio.somenteObb
                      ? [
                        tipoDoObb(relatorio.arquivo),
                        relatorio.pacote || 'pacote não lido do nome',
                      ].join(' · ')
                      : ([relatorio.pacote, relatorio.versao && `versão ${relatorio.versao}`,
                        relatorio.motor && `${relatorio.motor}${relatorio.versaoDoMotor ? ` ${relatorio.versaoDoMotor}` : ''}`]
                        .filter(Boolean).join(' · ') || 'manifesto não lido')}
                  </p>
                </div>
                {relatorio.parte && <span className="jogo-parte">jogos/{relatorio.parte}/</span>}
              </header>

              {relatorio.iphone && <CartaoIphone iphone={relatorio.iphone} />}

              {relatorio.somenteObb && (
                <p className="jogo-hint">
                  Só o OBB chegou até agora. Envie o APK do mesmo jogo nesta área — ele entra nesta
                  mesma pasta e eu confiro pacote e versão dos dois.
                </p>
              )}

              {!relatorio.somenteObb && (
                <>
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
                      <h3 className="jogo-titulo-achados">Maiores arquivos do APK</h3>
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
                </>
              )}

              {(relatorio.obbs ?? []).map((obb) => {
                const selo = conferencia(obb);
                return (
                  <section key={obb.arquivo} className="jogo-obb">
                    <h3 className="jogo-titulo-achados">
                      <FileArchive size={14} /> OBB — os dados fora do APK
                    </h3>
                    <p className="jogo-hint">
                      <code>{obb.arquivo}</code> · {tipoDoObb(obb.arquivo)} · {obb.formato}
                    </p>

                    <div className="jogo-metricas">
                      <article><span>OBB</span><strong>{mb(obb.bytes)}</strong><small>no disco</small></article>
                      <article>
                        <span>Arquivos</span>
                        <strong>{obb.zip ? obb.entradas : '—'}</strong>
                        <small>{obb.zip ? 'dentro do OBB' : 'conteúdo não listável'}</small>
                      </article>
                      <article>
                        <span>Descompactado</span>
                        <strong>{obb.zip ? mb(obb.tamanhoDescompactado) : '—'}</strong>
                        <small>{obb.zip ? 'quanto ocupa aberto' : 'sem ZIP, sem lista'}</small>
                      </article>
                      <article>
                        <span>Conferência</span>
                        <strong className={`jogo-selo is-${selo.nivel}`}>{selo.texto}</strong>
                        <small>pacote e versão vs. APK</small>
                      </article>
                    </div>

                    {obb.achados.map((achado, indice) => {
                      const nivel = gravidade(achado);
                      const { rotulo, Icone } = SEVERIDADE[nivel];
                      return (
                        <article key={`obb-${indice}-${achado.titulo}`} className={`jogo-achado is-${nivel}`}>
                          <header><Icone size={14} /><em>{rotulo}</em><strong>{achado.titulo}</strong></header>
                          {achado.o_que_e && <p><b>O que é:</b> {achado.o_que_e}</p>}
                          {achado.por_que_importa && <p><b>Por que importa:</b> {achado.por_que_importa}</p>}
                          {achado.como_melhorar && <p><b>Como melhorar:</b> {achado.como_melhorar}</p>}
                          {achado.onde && <p className="jogo-onde"><b>Onde:</b> {achado.onde}</p>}
                        </article>
                      );
                    })}

                    {obb.maiores.length > 0 && (
                      <>
                        <h4 className="jogo-titulo-achados">Maiores arquivos do OBB</h4>
                        <ul className="jogo-maiores">
                          {obb.maiores.slice(0, 8).map((item) => (
                            <li key={item.nome}>
                              <span>{item.mb.toFixed(1).replace('.', ',')} MB</span>
                              <code>{item.nome}</code>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}

                    <p className="jogo-hint">{obb.limitacoes.join(' ')}</p>
                  </section>
                );
              })}

              <p className="jogo-rodape">
                Análise feita no seu PC, sem enviar o APK para lugar nenhum. Isto é o que se vê do
                pacote pronto: equilíbrio, controles e ritmo só você decide — e o ajuste é feito no
                motor, antes de gerar o APK de novo.
              </p>
            </>
          )}
        </section>
      </div>

      <section className="jogo-web">
        <header>
          <Smartphone size={16} />
          <div>
            <h2>Testar no iPhone</h2>
            <p>
              O <code>.apk</code> não roda no iOS. O que roda é o <b>export web</b> do jogo
              (a pasta com <code>index.html</code>) — aqui você manda o <code>.zip</code> dela.
              O servidor do jogo é outro processo: abra o <code>testar-no-iphone.bat</code> e
              deixe a janela aberta.
            </p>
          </div>
        </header>

        <div className="jogo-web-acoes">
          <button
            type="button"
            className="jogo-web-enviar"
            onClick={() => entradaWeb.current?.click()}
            disabled={enviandoWeb}
          >
            {enviandoWeb ? <LoaderCircle className="jogo-spin" size={15} /> : <Upload size={15} />}
            Enviar o .zip do export
          </button>
          <input
            ref={entradaWeb}
            type="file"
            accept=".zip"
            hidden
            onChange={(evento) => {
              const arquivo = evento.target.files?.[0];
              if (arquivo) void enviarWeb(arquivo);
              evento.target.value = '';
            }}
          />
          {web && (
            <span className="jogo-web-endereco">
              No iPhone, no Safari: <code>{web.endereco}</code>
            </span>
          )}
        </div>

        {avisoWeb && <p className="jogo-status is-ok"><Check size={14} /> {avisoWeb}</p>}
        {erroWeb && <p className="jogo-status is-error"><CircleAlert size={14} /> {erroWeb}</p>}

        {web && web.jogos.length > 0 ? (
          <ul className="jogo-web-lista">
            {web.jogos.map((item) => (
              <li key={item.nome}>
                <Gamepad2 size={14} />
                <span>
                  <strong>{item.nome}</strong>
                  <small>{item.arquivos} arquivo(s) · {mb(item.bytes)}</small>
                </span>
                <em className={item.temIndex ? 'is-ok' : 'is-error'}>
                  {item.temIndex ? 'pronto' : 'sem index.html'}
                </em>
              </li>
            ))}
          </ul>
        ) : (
          <p className="jogo-hint">
            Nenhum export guardado ainda. No motor do jogo, gere o destino <b>WebGL</b> (Unity)
            ou <b>Web</b> (Godot) e compacte a pasta que tem o <code>index.html</code>.
          </p>
        )}

        <p className="jogo-hint">
          Depois de abrir no Safari: <b>Compartilhar → Adicionar à Tela de Início</b>. Vira ícone
          em tela cheia, sem App Store e sem conta paga. Não é app assinado — e o celular precisa
          estar no mesmo Wi-Fi do PC.
        </p>
      </section>
    </main>
  );
}
