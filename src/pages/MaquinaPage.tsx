import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  ChevronDown,
  Cpu,
  HardDriveDownload,
  ListTree,
  RefreshCw,
  ShieldQuestion,
  Usb,
} from 'lucide-react';
import type { SkillExecution } from '../lib/api';
import { useApp } from '../context/AppContext';
import '../maquina.css';

type Veredito = 'essencial' | 'driver' | 'sobra' | 'cuidado' | 'proprio';

type Linha = {
  nome: string;
  processo?: string;
  memoria_mb: number;
  pid?: number;
  o_que_e?: string;
  se_parar?: string;
  como_parar?: string;
  como_desfazer?: string;
  inicio?: string;
  ganho?: string;
  risco?: string;
};

type Relatorio = {
  sistema?: string;
  lido?: boolean;
  motivo?: string;
  processos_lidos?: number;
  memoria_total_mb?: number;
  grupos?: Partial<Record<Veredito, Linha[]>>;
  rotulos?: Partial<Record<Veredito, string>>;
  desconhecidos?: { nome: string; memoria_mb: number }[];
  desconhecidos_total?: number;
  ganho_sobra_mb?: number;
  ganho_driver_mb?: number;
  resumo?: string;
  aviso?: string;
  inicio?: { nome: string; comando: string; local?: string }[];
  nvidia?: {
    pergunta?: string;
    resposta?: string;
    como_parar?: string;
    como_voltar?: string;
    para_nao_voltar?: string;
  };
};

type Ferramenta = {
  id: string;
  nome: string;
  tamanho_mb: number;
  licenca: string;
  url: string;
  para_que: string;
  libera_skill?: string;
  admin?: boolean;
  nota?: string;
  presente?: boolean;
};

type Catalogo = {
  ferramentas?: Ferramenta[];
  total?: number;
  presentes?: number;
  tamanho_total_mb?: number;
  nao_portatil?: { nome: string; por_que: string }[];
  onde?: { caminho?: string; unidade?: string; removivel?: boolean };
  regra?: string;
};

type Plano = {
  etapas?: Ferramenta & { acumulado_mb?: number; baixar_de?: string }[];
  tamanho_total_mb?: number;
  ja_tem?: string[];
  como_baixar?: string;
  aviso?: string;
  onde?: { caminho?: string; removivel?: boolean };
};

const ORDEM: Veredito[] = ['sobra', 'driver', 'cuidado', 'essencial', 'proprio'];

const EXPLICACAO: Record<Veredito, string> = {
  sobra: 'Pode fechar. Devolve RAM e não tira função que você usa.',
  driver: 'Peça do driver. Fechar não muda imagem nem FPS — tira o painel e o ShadowPlay.',
  cuidado: 'Funciona, mas fechar atrapalha: aba aberta, índice de busca, proteção.',
  essencial: 'Não feche. O Windows cai ou a sessão termina.',
  proprio: 'Do próprio JARVIS. Fechar derruba esta interface.',
};

const num = (valor: unknown, padrao = 0) => (typeof valor === 'number' && Number.isFinite(valor) ? valor : padrao);
const lista = <T,>(valor: unknown): T[] => (Array.isArray(valor) ? (valor as T[]) : []);
const mb = (valor: unknown) => {
  const n = num(valor);
  return n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${Math.round(n)} MB`;
};

export function MaquinaPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [painel, setPainel] = useState<'processos' | 'pendrive'>('processos');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null);
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null);
  const [plano, setPlano] = useState<Plano | null>(null);
  const [aberto, setAberto] = useState<string>('');

  const carregarProcessos = useCallback(async () => {
    const resposta: SkillExecution = await executeSkill('maquina.processos', {});
    if (!resposta.ok) {
      setErro(resposta.error?.message ?? 'A leitura dos processos falhou.');
      return null;
    }
    const dados = (resposta.result ?? {}) as Relatorio;
    setRelatorio(dados);
    return dados;
  }, [executeSkill]);

  const carregarPendrive = useCallback(async () => {
    const [lista, ordem] = await Promise.all([
      executeSkill('maquina.portatil', {}),
      executeSkill('maquina.plano', {}),
    ]);
    if (lista.ok && lista.result) setCatalogo(lista.result as Catalogo);
    if (ordem.ok && ordem.result) setPlano(ordem.result as Plano);
    if (!lista.ok) setErro(lista.error?.message ?? 'O catálogo do pendrive falhou.');
  }, [executeSkill]);

  const recarregar = useCallback(async () => {
    if (!backendOnline) return;
    setBusy(true);
    setErro('');
    try {
      if (painel === 'processos') await carregarProcessos();
      else await carregarPendrive();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui falar com a API.');
    } finally {
      setBusy(false);
    }
  }, [backendOnline, carregarPendrive, carregarProcessos, painel]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const copiar = async (texto: string, rotulo: string) => {
    try {
      await navigator.clipboard.writeText(texto);
      pushToast('Copiado', rotulo, 'success');
    } catch {
      pushToast('Copie à mão', texto, 'info');
    }
  };

  const nvidia = relatorio?.nvidia;
  const grupos = relatorio?.grupos ?? {};
  const presentes = num(catalogo?.presentes);
  const totalFerramentas = num(catalogo?.total);
  const removivel = Boolean(plano?.onde?.removivel ?? catalogo?.onde?.removivel);

  return (
    <div className="maquina-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">O QUE RODA E O QUE VAI NO PENDRIVE</span>
          <h1>Máquina<span>.</span></h1>
          <p>Nada é fechado nem baixado aqui: a página lê, explica e devolve o comando.</p>
        </div>
        <button className="button" onClick={() => void recarregar()} disabled={busy || !backendOnline}>
          <RefreshCw size={16} /> {busy ? 'Lendo…' : 'Atualizar'}
        </button>
      </header>

      <div className="maquina-abas">
        <button className={painel === 'processos' ? 'ativo' : ''} onClick={() => setPainel('processos')}>
          <ListTree size={16} /> Processos
          <small>o que está aberto e o que não precisa</small>
        </button>
        <button className={painel === 'pendrive' ? 'ativo' : ''} onClick={() => setPainel('pendrive')}>
          <Usb size={16} /> Pendrive
          <small>portátil de verdade × o que é do PC</small>
        </button>
      </div>

      {!backendOnline && (
        <div className="maquina-alerta">
          <AlertTriangle size={16} /> A API está offline: nada foi lido. Suba com{' '}
          <code>.venv\Scripts\python iniciar.py</code>.
        </div>
      )}
      {erro && (
        <div className="maquina-alerta maquina-alerta-erro">
          <AlertTriangle size={16} /> {erro}
          <button className="maquina-link" onClick={() => setErro('')}>fechar</button>
        </div>
      )}

      {painel === 'processos' && (
        <>
          {relatorio && relatorio.lido === false && (
            <div className="maquina-alerta">
              <AlertTriangle size={16} /> {relatorio.motivo ?? 'Esta leitura é do Windows.'}
            </div>
          )}

          <div className="metric-grid maquina-metricas">
            <div className="metric-card">
              <span className="metric-icon"><Cpu size={18} /></span>
              <div><strong>{num(relatorio?.processos_lidos)}</strong><span>Processos lidos</span></div>
              <small>{mb(relatorio?.memoria_total_mb)} em uso</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><HardDriveDownload size={18} /></span>
              <div><strong>{mb(relatorio?.ganho_sobra_mb)}</strong><span>Sobras recuperáveis</span></div>
              <small>fechando as sobras</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><Cpu size={18} /></span>
              <div><strong>{mb(relatorio?.ganho_driver_mb)}</strong><span>Driver NVIDIA</span></div>
              <small>seguro, mas tira o painel</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><ShieldQuestion size={18} /></span>
              <div><strong>{num(relatorio?.desconhecidos_total)}</strong><span>Não classificados</span></div>
              <small>ficam em paz</small>
            </div>
          </div>

          {nvidia && (
            <section className="panel maquina-nvidia">
              <header>
                <div>
                  <span className="maquina-selo">a sua pergunta</span>
                  <h2>{nvidia.pergunta ?? 'O NVIDIA Container precisa estar aberto?'}</h2>
                </div>
              </header>
              <p>{nvidia.resposta}</p>
              <div className="maquina-comandos">
                <button onClick={() => void copiar(nvidia.como_parar ?? '', 'Comando para parar o NVIDIA Container')}>
                  <span>parar agora</span>
                  <code>{nvidia.como_parar || '—'}</code>
                </button>
                <button onClick={() => void copiar(nvidia.como_voltar ?? '', 'Comando para religar o NVIDIA Container')}>
                  <span>voltar a funcionar</span>
                  <code>{nvidia.como_voltar || '—'}</code>
                </button>
                <button onClick={() => void copiar(nvidia.para_nao_voltar ?? '', 'Como impedir de voltar no boot')}>
                  <span>não voltar no boot</span>
                  <code>{nvidia.para_nao_voltar || 'Serviços > NvContainerLocalSystem > Manual'}</code>
                </button>
              </div>
            </section>
          )}

          {relatorio?.resumo && <p className="maquina-resumo">{relatorio.resumo}</p>}

          <div className="maquina-grupos">
            {ORDEM.map((chave) => {
              const itens = grupos[chave] ?? [];
              if (!itens.length) return null;
              return (
                <section key={chave} className={`panel maquina-grupo maquina-grupo-${chave}`}>
                  <header>
                    <div>
                      <h2>{relatorio?.rotulos?.[chave] ?? chave}</h2>
                      <p>{EXPLICACAO[chave]}</p>
                    </div>
                    <strong>{mb(itens.reduce((soma, item) => soma + num(item.memoria_mb), 0))}</strong>
                  </header>
                  <ul>
                    {itens.map((item) => {
                      const id = `${chave}:${item.nome}`;
                      const expandido = aberto === id;
                      return (
                        <li key={id} className={expandido ? 'aberto' : ''}>
                          <button
                            className="maquina-linha"
                            onClick={() => setAberto(expandido ? '' : id)}
                            aria-expanded={expandido}
                          >
                            <ChevronDown size={15} />
                            <span className="nome">{item.nome}</span>
                            <span className="mem">{mb(item.memoria_mb)}</span>
                          </button>
                          {expandido && (
                            <div className="maquina-detalhe">
                              {item.o_que_e && <p>{item.o_que_e}</p>}
                              {item.se_parar && (
                                <p><b>Se parar:</b> {item.se_parar}</p>
                              )}
                              {item.como_parar && (
                                <button className="maquina-codigo" onClick={() => void copiar(item.como_parar ?? '', item.nome)}>
                                  <code>{item.como_parar}</code>
                                </button>
                              )}
                              {item.como_desfazer && (
                                <p className="maquina-volta"><b>Desfazer:</b> <code>{item.como_desfazer}</code></p>
                              )}
                              {item.inicio && <p className="maquina-volta"><b>No boot:</b> {item.inicio}</p>}
                              {item.ganho && <p className="maquina-volta"><b>Ganho:</b> {item.ganho} · risco {item.risco ?? '—'}</p>}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>

          {(relatorio?.desconhecidos?.length ?? 0) > 0 && (
            <section className="panel maquina-grupo maquina-grupo-desconhecido">
              <header>
                <div>
                  <h2>Não classificados</h2>
                  <p>Não sei o que fazem, então não digo para fechar. Se um deles for seu, me diga o nome.</p>
                </div>
                <strong>{num(relatorio?.desconhecidos_total)}</strong>
              </header>
              <ul>
                {lista<{ nome: string; memoria_mb: number }>(relatorio?.desconhecidos).map((item) => (
                  <li key={item.nome}>
                    <div className="maquina-linha maquina-linha-estatica">
                      <span className="nome">{item.nome}</span>
                      <span className="mem">{mb(item.memoria_mb)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {lista<{ nome: string; comando: string; local?: string }>(relatorio?.inicio).length > 0 && (
            <section className="panel maquina-inicio">
              <header><h2>O que abre sozinho no boot</h2><p>É aqui que se ganha RAM de forma permanente, sem fechar nada na mão.</p></header>
              <ul>
                {lista<{ nome: string; comando: string; local?: string }>(relatorio?.inicio).slice(0, 40).map((item) => (
                  <li key={`${item.nome}-${item.comando}`}>
                    <strong>{item.nome}</strong>
                    <code>{item.comando}</code>
                    {item.local && <small>{item.local}</small>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {relatorio?.aviso && <p className="maquina-resumo maquina-resumo-fraco">{relatorio.aviso}</p>}
        </>
      )}

      {painel === 'pendrive' && (
        <>
          <div className="metric-grid maquina-metricas">
            <div className="metric-card">
              <span className="metric-icon"><Usb size={18} /></span>
              <div><strong>{presentes}/{totalFerramentas}</strong><span>Já no pendrive</span></div>
              <small>{mb(catalogo?.tamanho_total_mb)} para o catálogo inteiro</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><HardDriveDownload size={18} /></span>
              <div><strong>{mb(plano?.tamanho_total_mb)}</strong><span>Falta baixar</span></div>
              <small>{lista(plano?.etapas).length} itens</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><Ban size={18} /></span>
              <div><strong>{lista(catalogo?.nao_portatil).length}</strong><span>Não dá para levar</span></div>
              <small>driver e runtime</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><Cpu size={18} /></span>
              <div><strong>{removivel ? 'removível' : 'no PC'}</strong><span>Onde está o JARVIS</span></div>
              <small>{plano?.onde?.caminho ?? catalogo?.onde?.caminho ?? '—'}</small>
            </div>
          </div>

          {catalogo?.regra && <p className="maquina-resumo">{catalogo.regra}</p>}

          <section className="panel maquina-plano">
            <header>
              <div>
                <h2>Ordem para baixar</h2>
                <p>{plano?.como_baixar ?? 'Nada é baixado por esta página.'}</p>
              </div>
              {plano?.aviso && <small className="maquina-selo">{plano.aviso}</small>}
            </header>
            {lista<{ id: string; nome: string; tamanho_mb: number; acumulado_mb?: number; para_que: string; libera?: string; baixar_de?: string }>(plano?.etapas).length === 0 ? (
              <div className="maquina-vazio">
                <Usb size={26} />
                <p>Todas as ferramentas do catálogo já estão na pasta.</p>
              </div>
            ) : (
              <ol className="maquina-etapas">
                {lista<{ id: string; nome: string; tamanho_mb: number; acumulado_mb?: number; para_que: string; libera?: string; baixar_de?: string }>(plano?.etapas).map((etapa, indice) => (
                  <li key={etapa.id}>
                    <span className="indice">{indice + 1}</span>
                    <div>
                      <strong>{etapa.nome}</strong>
                      <p>{etapa.para_que}</p>
                      {etapa.libera && <small>libera: {etapa.libera}</small>}
                    </div>
                    <div className="maquina-etapa-numeros">
                      <span>{etapa.tamanho_mb} MB</span>
                      <small>{etapa.acumulado_mb} MB acumulados</small>
                      <a href={etapa.baixar_de} target="_blank" rel="noreferrer">site oficial</a>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="panel maquina-catalogo">
            <header>
              <div>
                <h2>Os {totalFerramentas} portáteis</h2>
                <p>Roda do pendrive, sem instalador e sem reiniciar.</p>
              </div>
            </header>
            <div className="maquina-cartoes">
              {lista<Ferramenta>(catalogo?.ferramentas).map((item) => (
                <article key={item.id} className={item.presente ? 'maquina-cartao presente' : 'maquina-cartao'}>
                  <header>
                    <strong>{item.nome}</strong>
                    <span>{item.presente ? 'no pendrive' : `${item.tamanho_mb} MB`}</span>
                  </header>
                  <p>{item.para_que}</p>
                  <footer>
                    <span>{item.licenca}</span>
                    {item.admin && <span className="maquina-tag">pede admin</span>}
                    <a href={item.url} target="_blank" rel="noreferrer">baixar</a>
                  </footer>
                  {item.libera_skill && <small>libera {item.libera_skill}</small>}
                </article>
              ))}
            </div>
          </section>

          <section className="panel maquina-nao">
            <header>
              <div>
                <h2>Do PC, não do pendrive</h2>
                <p>Isto não é ferramenta solta: instala no Windows, vira serviço e pede reinício. Prometer portátil aqui seria mentira.</p>
              </div>
            </header>
            <ul>
              {lista<{ nome: string; por_que: string }>(catalogo?.nao_portatil).map((item) => (
                <li key={item.nome}>
                  <Ban size={15} />
                  <div><strong>{item.nome}</strong><p>{item.por_que}</p></div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
