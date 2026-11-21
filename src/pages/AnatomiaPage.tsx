import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Cpu,
  HardDrive,
  LoaderCircle,
  Monitor,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Stethoscope,
  Tv,
  Wifi,
} from 'lucide-react';
import { escanearCelular, getAnatomiaFontes, getControleCelular, getSintomasCelular, lerAnatomia, varrerCelular } from '../lib/api';
import type {
  AnatomiaFontes,
  AnatomiaResultado,
  CelularControle,
  CelularVarredura,
  CelularDiagnostico,
  CelularSintoma,
  CelularSintomas,
} from '../lib/api';
import '../anatomia.css';

/**
 * Anatomia — ler o aparelho sem mudar nada nele.
 *
 * O pedido do dono: *“conectar no USB e ver todos os componentes, igual anatomia
 * humana”*, e depois a TV TCL Roku pela rede. A tela é uma só para os três
 * alvos, porque a pergunta é a mesma (“o que é isso por dentro?”) e a resposta
 * tem o mesmo formato: seções de rótulo/valor, limitações e o que o JARVIS não
 * faz.
 *
 * Quando um alvo está desligado, o cartão mostra **o que ligar** — não um
 * “indisponível” seco. O motivo vem do servidor justamente para não haver duas
 * versões da mesma instrução.
 */

const ICONES = {
  local: Monitor,
  android: Smartphone,
  roku: Tv,
} as const;

const DICAS = {
  local: 'CPU, memória, discos, vídeo e temperatura da máquina que executa a API.',
  android: 'Identidade, bateria, memória, partições e apps de um aparelho na USB.',
  roku: 'Modelo, canais e o que está na tela — pela porta 8060 da TV, só leitura.',
} as const;

function quando(iso: string): string {
  if (!iso) return '';
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return data.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const GRAVIDADE: Record<string, { rotulo: string; classe: string }> = {
  alta: { rotulo: 'Resolver primeiro', classe: 'is-alta' },
  media: { rotulo: 'Vale resolver', classe: 'is-media' },
  baixa: { rotulo: 'Só para saber', classe: 'is-baixa' },
};

/**
 * O resultado do scanner: cada achado com a medida que o sustenta.
 *
 * A ordem é a da gravidade, e o cartão abre pelo veredito — a frase de uma
 * linha que a pessoa lê se não ler mais nada. O passo a passo fica em sanfona
 * porque são muitos; o número medido nunca fica escondido.
 */
/**
 * “100% de acesso”: a resposta em degraus.
 *
 * O dono pediu acesso total. O cartão mostra onde ele está hoje, até onde o
 * JARVIS vai e — no mesmo lugar — o que cada degrau a mais custa. Não existe
 * degrau 6: o 5 é uma falha de segurança, e o cartão diz que não é feito.
 */
function CartaoControle({ dados }: { dados: CelularControle }) {
  return (
    <section className="panel anatomia-controle">
      <div className="anatomia-resultado-topo">
        <div>
          <span className="eyebrow">ACESSO AO APARELHO</span>
          <h2>Até onde o JARVIS chega</h2>
          <p className="anatomia-veredito">{dados.resumo}</p>
        </div>
        <span className="local-badge">degrau {dados.degrau_atual} de 5</span>
      </div>

      <div className="anatomia-controle-lista">
        {dados.degraus.map((degrau) => (
          <article
            key={degrau.degrau}
            className={`anatomia-controle-item ${degrau.alcancado ? 'is-ativo' : ''} ${degrau.jarvis_faz ? '' : 'is-fora'}`}
          >
            <div className="anatomia-controle-topo">
              <span className="anatomia-controle-num">{degrau.degrau}</span>
              <strong>{degrau.nome}</strong>
              <span className={degrau.jarvis_faz ? 'anatomia-suspeita-sim' : 'anatomia-suspeita-nao'}>
                {degrau.jarvis_faz ? 'o JARVIS faz' : 'o JARVIS não faz'}
              </span>
            </div>
            <dl>
              <div><dt>Ganha</dt><dd>{degrau.ganha}</dd></div>
              <div><dt>Falta</dt><dd>{degrau.falta}</dd></div>
              <div><dt>Custa</dt><dd>{degrau.custa}</dd></div>
            </dl>
            {degrau.recusa && <p className="anatomia-limite"><AlertTriangle size={12} /> {degrau.recusa}</p>}
          </article>
        ))}
      </div>

      {dados.root_temporario && (
        <div className={`anatomia-root-temporario ${dados.root_temporario.possivel ? 'is-sim' : 'is-nao'}`}>
          <h3>
            <AlertTriangle size={13} /> “Podemos usar root temporário?”
          </h3>
          <p className="anatomia-veredito">{dados.root_temporario.resumo}</p>
          <dl>
            <div>
              <dt>Situação neste aparelho</dt>
              <dd>{dados.root_temporario.qual}</dd>
            </div>
            <div>
              <dt>Precisa destravar o bootloader?</dt>
              <dd>{dados.root_temporario.precisa_destravar ? 'sim' : 'não'}</dd>
            </div>
            <div>
              <dt>Apaga o aparelho?</dt>
              <dd>{dados.root_temporario.apaga_o_aparelho ? 'sim' : 'não'}</dd>
            </div>
          </dl>
        </div>
      )}

      <div className="anatomia-nao-faz">
        <h3><ShieldCheck size={13} /> Por que o JARVIS para no degrau {dados.degrau_maximo_jarvis}</h3>
        <ul>{dados.o_que_nao_faz_e_por_que.map((frase) => <li key={frase}>{frase}</li>)}</ul>
      </div>
    </section>
  );
}

function CartaoDiagnostico({ dados }: { dados: CelularDiagnostico & { sintomas?: CelularSintomas } }) {
  const [aberto, setAberto] = useState<string>(dados.problemas[0]?.id ?? '');
  return (
    <section className="panel anatomia-scan">
      <div className="anatomia-resultado-topo">
        <div>
          <span className="eyebrow">SCANNER · {quando(dados.lido_em)}</span>
          <h2>{dados.titulo}</h2>
          <p className="anatomia-veredito">{dados.veredito}</p>
        </div>
        <span className="local-badge"><ShieldCheck size={12} /> NADA FOI ALTERADO</span>
      </div>

      {dados.sintomas && (
        <div className="anatomia-suspeitas">
          <h3><Stethoscope size={13} /> Pelo que você relatou, a ordem é esta</h3>
          <p className="anatomia-veredito">{dados.sintomas.veredito}</p>
          <ol>
            {dados.sintomas.fila.slice(0, 4).map((suspeita, indice) => (
              <li key={suspeita.id}>
                <div className="anatomia-suspeita-topo">
                  <span className="anatomia-suspeita-ordem">{indice + 1}</span>
                  <strong>{suspeita.titulo}</strong>
                  <span className={suspeita.medido_no_aparelho.length ? 'anatomia-suspeita-sim' : 'anatomia-suspeita-nao'}>
                    {suspeita.medido_no_aparelho.length ? 'medido no aparelho' : 'sem medida no aparelho'}
                  </span>
                </div>
                <p>{suspeita.porque}</p>
                <div className="anatomia-suspeita-testes">
                  <span>Teste mais barato</span>
                  <ul>{suspeita.teste.map((passo) => <li key={passo}>{passo}</li>)}</ul>
                </div>
                <p className="anatomia-limite"><AlertTriangle size={12} /> se confirmar: {suspeita.o_que_confirma}</p>
              </li>
            ))}
          </ol>
          <p className="anatomia-como-ler">{dados.sintomas.como_ler}</p>
        </div>
      )}

      {dados.problemas.length === 0 && (
        <p className="anatomia-scan-limpo">
          <ShieldCheck size={14} /> Nenhum problema nas áreas que o Android publica sem root — o
          aparelho está saudável no que dá para medir.
        </p>
      )}

      {dados.problemas.map((problema) => {
        const grau = GRAVIDADE[problema.gravidade] ?? GRAVIDADE.baixa;
        const expandido = aberto === problema.id;
        return (
          <article className={`anatomia-achado ${grau.classe} ${expandido ? 'is-open' : ''}`} key={problema.id}>
            <button
              className="anatomia-achado-topo"
              onClick={() => setAberto(expandido ? '' : problema.id)}
              aria-expanded={expandido}
            >
              <span className={`anatomia-grau ${grau.classe}`}>{grau.rotulo}</span>
              <strong>{problema.titulo}</strong>
              <small>{problema.medido}</small>
            </button>
            {expandido && (
              <div className="anatomia-achado-corpo">
                <p><b>Causa provável.</b> {problema.causa}</p>
                <ol>{problema.o_que_fazer.map((passo) => <li key={passo}>{passo}</li>)}</ol>
                <p className="anatomia-limite"><AlertTriangle size={12} /> {problema.limite}</p>
              </div>
            )}
          </article>
        );
      })}

      {dados.otimizacoes.length > 0 && (
        <div className="anatomia-otimizacoes">
          <h3>O que dá para melhorar</h3>
          {dados.otimizacoes.map((otimizacao) => (
            <article key={otimizacao.id}>
              <div>
                <strong>{otimizacao.titulo}</strong>
                <small>{otimizacao.ganho}</small>
              </div>
              {!otimizacao.medido && <span className="anatomia-nao-medido">sensação, não número medido</span>}
              <ol>{otimizacao.como.map((passo) => <li key={passo}>{passo}</li>)}</ol>
              <p className="anatomia-risco"><AlertTriangle size={12} /> {otimizacao.risco}</p>
            </article>
          ))}
        </div>
      )}

      <div className="anatomia-secoes">
        {dados.secoes.map((secao) => (
          <article className="anatomia-secao" key={secao.id}>
            <h3>{secao.titulo}</h3>
            <dl>
              {secao.itens.map((item) => (
                <div key={`${secao.id}-${item.rotulo}`}>
                  <dt>{item.rotulo}</dt>
                  <dd>{item.valor}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>

      {dados.limitacoes.length > 0 && (
        <div className="anatomia-limites">
          <h3><HardDrive size={13} /> O que o scanner não alcança</h3>
          <ul>{dados.limitacoes.map((limite) => <li key={limite}>{limite}</li>)}</ul>
        </div>
      )}

      <div className="anatomia-nao-faz">
        <h3><ShieldCheck size={13} /> O que o scanner não faz</h3>
        <ul>{dados.nao_faz.map((frase) => <li key={frase}>{frase}</li>)}</ul>
      </div>
    </section>
  );
}

/**
 * A varredura completa: o mesmo que o `ver-tudo-no-celular.bat` faz no console.
 *
 * Mostra **o mapa** (pastas, partições, memória, processos, apps, aparelho) e,
 * logo no topo, o que o scanner achou. Na 0.92.5 esta tela não existia: a
 * varredura só saía em texto, e um relatório com “nenhum problema” sem as
 * leituras de saúde passava despercebido.
 */
function CartaoVarredura({ dados }: { dados: CelularVarredura }) {
  return (
    <section className="panel anatomia-varredura">
      <div className="anatomia-resultado-topo">
        <div>
          <span className="eyebrow">VARREDURA COMPLETA · {quando(dados.lido_em)}</span>
          <h2>{dados.titulo}</h2>
          <p className="anatomia-veredito">{dados.veredito}</p>
        </div>
        <span className="local-badge"><ShieldCheck size={12} /> NADA FOI ALTERADO</span>
      </div>

      {dados.problemas.length > 0 && (
        <div className="anatomia-suspeitas">
          <h3><AlertTriangle size={13} /> O que o scanner achou</h3>
          <ol>
            {dados.problemas.slice(0, 5).map((problema) => {
              const grau = GRAVIDADE[problema.gravidade] ?? GRAVIDADE.baixa;
              return (
                <li key={problema.id}>
                  <div className="anatomia-suspeita-topo">
                    <strong>{problema.titulo}</strong>
                    <span className={grau.classe}>{problema.gravidade}</span>
                  </div>
                  <p>{problema.medido}</p>
                  <div className="anatomia-suspeita-testes">
                    <span>O que fazer</span>
                    <ul>{problema.o_que_fazer.slice(0, 3).map((passo) => <li key={passo}>{passo}</li>)}</ul>
                  </div>
                  {problema.limite && <p className="anatomia-limite"><AlertTriangle size={12} /> {problema.limite}</p>}
                </li>
              );
            })}
          </ol>
        </div>
      )}

      <div className="anatomia-secoes">
        {dados.secoes.map((secao) => (
          <article className="anatomia-secao" key={secao.id}>
            <h3>{secao.titulo}</h3>
            <dl>
              {secao.itens.map((item) => (
                <div key={`${secao.id}-${item.rotulo}`}>
                  <dt>{item.rotulo}</dt>
                  <dd>{item.valor}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>

      {dados.limitacoes.length > 0 && (
        <div className="anatomia-limites">
          <h3><HardDrive size={13} /> Leituras que não responderam</h3>
          <ul>{dados.limitacoes.map((limite) => <li key={limite}>{limite}</li>)}</ul>
        </div>
      )}

      <div className="anatomia-limites">
        <h3><ShieldCheck size={13} /> O que não dá sem root</h3>
        <ul>{dados.sem_root.map((frase) => <li key={frase}>{frase}</li>)}</ul>
      </div>

      <div className="anatomia-nao-faz">
        <h3><ShieldCheck size={13} /> O que esta varredura não faz</h3>
        <ul>{dados.nao_faz.map((frase) => <li key={frase}>{frase}</li>)}</ul>
      </div>
    </section>
  );
}

export function AnatomiaPage() {
  const [fontes, setFontes] = useState<AnatomiaFontes | null>(null);
  const [resultado, setResultado] = useState<AnatomiaResultado | null>(null);
  const [lendo, setLendo] = useState<string>('');
  const [erro, setErro] = useState('');
  const [ip, setIp] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [diagnostico, setDiagnostico] = useState<(CelularDiagnostico & { sintomas?: CelularSintomas }) | null>(null);
  const [escaneando, setEscaneando] = useState(false);
  const [perguntas, setPerguntas] = useState<CelularSintoma[]>([]);
  const [marcados, setMarcados] = useState<string[]>([]);
  const [controle, setControle] = useState<CelularControle | null>(null);
  const [varredura, setVarredura] = useState<CelularVarredura | null>(null);
  const [varrendo, setVarrendo] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setFontes(await getAnatomiaFontes());
      setErro('');
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui listar os alvos.');
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // As perguntas vêm do servidor para existir uma versão só delas: se o módulo
  // ganhar um sintoma novo, a tela ganha sem ninguém editar dois lugares.
  useEffect(() => {
    void getSintomasCelular()
      .then(setPerguntas)
      .catch(() => setPerguntas([]));
    void getControleCelular()
      .then(setControle)
      .catch(() => setControle(null));
  }, []);

  const ler = async (alvo: 'local' | 'android' | 'roku', parametros: { ip?: string; serial?: string } = {}) => {
    setLendo(alvo);
    setErro('');
    try {
      setResultado(await lerAnatomia(alvo, parametros));
    } catch (falha) {
      setResultado(null);
      setErro(falha instanceof Error ? falha.message : 'A leitura não respondeu.');
    } finally {
      setLendo('');
    }
  };

  const escanear = async (serial = '') => {
    setEscaneando(true);
    setErro('');
    try {
      setDiagnostico(await escanearCelular(serial, marcados));
    } catch (falha) {
      setDiagnostico(null);
      setErro(falha instanceof Error ? falha.message : 'O scanner não respondeu.');
    } finally {
      setEscaneando(false);
    }
  };

  const varrer = async (serial = '') => {
    setVarrendo(true);
    setErro('');
    try {
      setVarredura(await varrerCelular(serial));
    } catch (falha) {
      setVarredura(null);
      setErro(falha instanceof Error ? falha.message : 'A varredura não respondeu.');
    } finally {
      setVarrendo(false);
    }
  };

  const alternarSintoma = (id: string) =>
    setMarcados((atuais) => (atuais.includes(id) ? atuais.filter((item) => item !== id) : [...atuais, id]));

  const alvoDe = (id: 'local' | 'android' | 'roku') => fontes?.alvos.find((alvo) => alvo.id === id);

  return (
    <div className="anatomia-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">LEITURA DE APARELHO</span>
          <h1>Anatomia<span>.</span></h1>
          <p>
            O que o aparelho é por dentro — CPU, memória, discos, sensores e apps — sem instalar,
            alterar ou reiniciar nada. Como uma anatomia: olhar, nomear e explicar.
          </p>
        </div>
        <span className="local-badge"><ShieldCheck size={12} /> NADA É ALTERADO</span>
      </header>

      <div className="anatomia-alvos">
        {(['local', 'android', 'roku'] as const).map((id) => {
          const alvo = alvoDe(id);
          const Icone = ICONES[id];
          const disponivel = alvo?.disponivel ?? id === 'local';
          const aparelhos = alvo?.aparelhos ?? [];
          return (
            <section className={`panel anatomia-alvo ${disponivel ? '' : 'is-off'}`} key={id}>
              <div className="anatomia-alvo-topo">
                <span className="anatomia-icone"><Icone size={18} /></span>
                <div>
                  <h2>{alvo?.titulo ?? DICAS[id]}</h2>
                  <p>{DICAS[id]}</p>
                </div>
              </div>

              {id === 'android' && aparelhos.length > 0 && (
                <ul className="anatomia-aparelhos">
                  {aparelhos.map((aparelho) => (
                    <li key={aparelho.serial}>
                      <code>{aparelho.model || aparelho.serial}</code>
                      <span className={`anatomia-estado is-${aparelho.estado}`}>{aparelho.estado}</span>
                    </li>
                  ))}
                </ul>
              )}

              {id === 'roku' && (
                <label className="anatomia-ip">
                  <Wifi size={14} />
                  <input
                    value={ip}
                    onChange={(evento) => setIp(evento.target.value)}
                    placeholder="IP da TV, ex.: 192.168.0.23"
                    maxLength={64}
                    inputMode="decimal"
                  />
                </label>
              )}

              {id === 'android' && perguntas.length > 0 && (
                <div className="anatomia-sintomas">
                  <span>O que você vê no aparelho?</span>
                  {perguntas.map((pergunta) => (
                    <label key={pergunta.id} className={marcados.includes(pergunta.id) ? 'is-marcado' : ''}>
                      <input
                        type="checkbox"
                        checked={marcados.includes(pergunta.id)}
                        onChange={() => alternarSintoma(pergunta.id)}
                      />
                      <span>{pergunta.pergunta}</span>
                    </label>
                  ))}
                  <small>Marcar o que você vê muda a ordem das suspeitas — o scanner continua só lendo.</small>
                </div>
              )}

              {!disponivel && alvo?.motivo && <p className="anatomia-motivo"><AlertTriangle size={13} /> {alvo.motivo}</p>}
              {disponivel && alvo?.motivo && id !== 'roku' && <p className="anatomia-motivo">{alvo.motivo}</p>}

              <button
                className="button button-secondary"
                onClick={() => void ler(id, id === 'roku' ? { ip: ip.trim() } : {})}
                disabled={Boolean(lendo) || (id === 'roku' && !ip.trim()) || (id === 'android' && !disponivel)}
              >
                {lendo === id ? <LoaderCircle className="anatomia-girar" size={15} /> : <Icone size={15} />}
                {id === 'local' ? 'Ler este computador' : id === 'android' ? 'Ler o aparelho' : 'Ler a TV'}
              </button>
              {id === 'android' && (
                <button
                  className="button button-primary anatomia-escanear"
                  onClick={() => void escanear()}
                  disabled={escaneando || !disponivel}
                >
                  {escaneando ? <LoaderCircle className="anatomia-girar" size={15} /> : <Stethoscope size={15} />}
                  {escaneando ? 'Passando o scanner...' : 'Passar o scanner'}
                </button>
              )}
              {id === 'android' && (
                <button
                  className="button button-secondary anatomia-escanear"
                  onClick={() => void varrer()}
                  disabled={varrendo || !disponivel}
                  title="Passa por todo o aparelho numa leitura só: pastas, partições, memória, processos e apps."
                >
                  {varrendo ? <LoaderCircle className="anatomia-girar" size={15} /> : <Cpu size={15} />}
                  {varrendo ? 'Varrendo o aparelho...' : 'Ver tudo no aparelho'}
                </button>
              )}
            </section>
          );
        })}
      </div>

      {erro && <p className="anatomia-erro"><AlertTriangle size={14} /> {erro}</p>}

      {!resultado && !erro && (
        <section className="panel anatomia-vazio">
          {carregando ? <LoaderCircle className="anatomia-girar" size={22} /> : <Cpu size={22} />}
          <strong>Escolha um aparelho</strong>
          <p>
            A leitura da máquina local funciona sempre. O Android pede a Depuração USB ligada e o
            “Permitir” na tela; a TV Roku pede o IP dela na mesma rede.
          </p>
        </section>
      )}

      {controle && <CartaoControle dados={controle} />}

      {diagnostico && <CartaoDiagnostico dados={diagnostico} />}

      {varredura && <CartaoVarredura dados={varredura} />}

      {resultado && (
        <section className="panel anatomia-resultado">
          <div className="anatomia-resultado-topo">
            <div>
              <span className="eyebrow">LEITURA DE {quando(resultado.lido_em)}</span>
              <h2>{resultado.titulo}</h2>
            </div>
            <button className="icon-button small" onClick={() => void carregar()} aria-label="Atualizar alvos" disabled={carregando}>
              <RefreshCw size={14} className={carregando ? 'anatomia-girar' : ''} />
            </button>
          </div>

          <div className="anatomia-secoes">
            {resultado.secoes.map((secao) => (
              <article className="anatomia-secao" key={secao.id}>
                <h3>{secao.titulo}</h3>
                <dl>
                  {secao.itens.map((item) => (
                    <div key={`${secao.id}-${item.rotulo}`}>
                      <dt>{item.rotulo}</dt>
                      <dd>{item.valor}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>

          {resultado.limitacoes.length > 0 && (
            <div className="anatomia-limites">
              <h3><HardDrive size={13} /> O que a leitura não alcança</h3>
              <ul>{resultado.limitacoes.map((limite) => <li key={limite}>{limite}</li>)}</ul>
            </div>
          )}

          <div className="anatomia-nao-faz">
            <h3><ShieldCheck size={13} /> O que o JARVIS não faz</h3>
            <ul>{resultado.nao_faz.map((frase) => <li key={frase}>{frase}</li>)}</ul>
          </div>
        </section>
      )}
    </div>
  );
}
