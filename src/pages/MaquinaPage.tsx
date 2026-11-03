import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  ChevronDown,
  Cpu,
  HardDriveDownload,
  ListTree,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
  Undo2,
  Zap,
  Trash2,
  Usb,
  Wrench,
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

type ItemLimpeza = {
  id?: string;
  pacote?: string;
  nome: string;
  servico?: string;
  tarefa?: string;
  veredito: 'sobra' | 'cuidado' | 'essencial';
  o_que_e: string;
  se_remover?: string;
  se_parar?: string;
  tamanho_estimado_mb?: number;
  tamanho_mb?: number | null;
  ganho?: string;
  estado?: string;
  comando: string;
  desfazer: string;
};

type Debloat = {
  lido?: boolean;
  motivo?: string;
  apps?: { apps?: ItemLimpeza[]; sobras?: number; estimado_sobra_mb?: number; nao_classificados?: string[]; nao_classificados_total?: number } | ItemLimpeza[];
  servicos?: ItemLimpeza[];
  tarefas?: ItemLimpeza[];
  espaco?: ItemLimpeza[];
  rotulos?: Record<string, string>;
  plano?: {
    script?: string;
    restaurar?: string;
    resumo?: string;
    linhas_comando?: number;
    aviso?: string;
    apps?: string[];
    tarefas?: string[];
    servicos?: string[];
    espaco?: string[];
  };
};

type Plano = {
  etapas?: Ferramenta & { acumulado_mb?: number; baixar_de?: string }[];
  tamanho_total_mb?: number;
  ja_tem?: string[];
  como_baixar?: string;
  aviso?: string;
  onde?: { caminho?: string; removivel?: boolean };
};

type AcaoFeita = {
  id?: string;
  tipo?: string;
  nome?: string;
  comando?: string;
  ok?: boolean;
  saida?: string;
  ganho?: string;
  desfazer?: string;
  /** 0.75.0: a causa curta (“admin”, “sumiu”…) e a frase pronta. */
  causa?: string;
  motivo?: string;
};

type ResultadoArrumar = {
  executado?: boolean;
  resumo?: string;
  feitas?: number;
  falhas?: number;
  diario?: string;
  acoes?: AcaoFeita[];
  lido?: boolean;
  motivo?: string;
  total?: number;
  desfeito?: boolean;
  numero?: number;
  instantaneo?: string;
  ponto_de_restauracao?: { criado?: boolean; motivo?: string };
  como_voltar_tudo?: string;
  sem_volta?: string[];
  // 0.75.0: o "por que falhou" vem nomeado, em vez de "o diário diz qual".
  falhas_por_causa?: Record<string, number>;
  nao_feitas?: { nome?: string; tipo?: string; comando?: string; motivo?: string; causa?: string; saida?: string }[];
  como_resolver?: string;
  elevado?: boolean | null;
  precisam_admin?: number;
  aviso_admin?: string;
  ousado?: boolean;
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
  const [painel, setPainel] = useState<'processos' | 'pendrive' | 'limpeza'>('processos');
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null);
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null);
  const [plano, setPlano] = useState<Plano | null>(null);
  const [limpeza, setLimpeza] = useState<Debloat | null>(null);
  const [arrumando, setArrumando] = useState(false);
  const [ousado, setOusado] = useState(false);
  const [arrumado, setArrumado] = useState<ResultadoArrumar | null>(null);
  const [aberto, setAberto] = useState<string>('');
  // Plano (sem executar) só para saber, antes do clique, se falta administrador.
  const [planoArrumar, setPlanoArrumar] = useState<ResultadoArrumar | null>(null);
  // Pedido de elevação: o JARVIS não pode virar administrador sozinho (o UAC é
  // seu), mas pode abrir o aviso do Windows em vez de te mandar achar o .bat.
  const [elevando, setElevando] = useState(false);
  const [resultadoElevar, setResultadoElevar] = useState<{ motivo?: string; aceito?: boolean } | null>(null);

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

  const carregarLimpeza = useCallback(async () => {
    const resposta: SkillExecution = await executeSkill('maquina.debloat', {});
    if (!resposta.ok) {
      setErro(resposta.error?.message ?? 'A leitura de limpeza falhou.');
      return;
    }
    setLimpeza((resposta.result ?? {}) as Debloat);
  }, [executeSkill]);

  /**
   * O plano dos braços, medido sem executar. É o que permite dizer **antes** do
   * clique: “esta janela não está elevada; 13 de 16 vão falhar” — o aviso que
   * faltou em 01/11/2026.
   */
  const carregarPlanoArrumar = useCallback(async () => {
    const resposta: SkillExecution = await executeSkill('maquina.arrumar', { planejar_apenas: true }, { dryRun: true });
    if (resposta.ok) setPlanoArrumar((resposta.result ?? {}) as ResultadoArrumar);
  }, [executeSkill]);

  const recarregar = useCallback(async () => {
    if (!backendOnline) return;
    setBusy(true);
    setErro('');
    try {
      if (painel === 'processos') await carregarProcessos();
      else if (painel === 'pendrive') await carregarPendrive();
      else {
        await carregarLimpeza();
        await carregarPlanoArrumar();
      }
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui falar com a API.');
    } finally {
      setBusy(false);
    }
  }, [backendOnline, carregarLimpeza, carregarPlanoArrumar, carregarPendrive, carregarProcessos, painel]);

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

  const pedirAdministrador = async () => {
    setElevando(true);
    setErro('');
    try {
      const resposta = await executeSkill('maquina.administrador', {}, { confirmed: true });
      const dados = (resposta.result ?? {}) as { motivo?: string; aceito?: boolean };
      setResultadoElevar(dados);
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'O Windows não abriu o pedido de permissão.');
        return;
      }
      pushToast(
        dados.aceito ? 'Pedido enviado ao Windows' : 'Não reabri como administrador',
        dados.motivo ?? '',
        dados.aceito ? 'info' : 'warning',
      );
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui falar com a API.');
    } finally {
      setElevando(false);
    }
  };

  const arrumar = async (desfazer = false) => {
    setArrumando(true);
    setErro('');
    try {
      const resposta = await executeSkill(
        desfazer ? 'maquina.desfazer' : 'maquina.arrumar',
        desfazer ? {} : { ousado, ponto_de_restauracao: true },
        { confirmed: true },
      );
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'O JARVIS recusou arrumar.');
        return;
      }
      const resultado = (resposta.result ?? {}) as ResultadoArrumar;
      setArrumado(resultado);
      pushToast(
        desfazer ? 'Desfazer' : 'Arrumado',
        resultado.resumo ?? 'Feito.',
        'success',
      );
      if (!desfazer) void carregarLimpeza();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não consegui falar com a API.');
    } finally {
      setArrumando(false);
    }
  };

  const salvar = (texto: string, arquivo: string) => {
    const blob = new Blob([texto], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = arquivo;
    link.click();
    URL.revokeObjectURL(url);
    pushToast('Arquivo salvo', arquivo, 'success');
  };

  const appsDebloat = Array.isArray(limpeza?.apps) ? limpeza.apps : (limpeza?.apps?.apps ?? []);
  const sobras = Array.isArray(limpeza?.apps) ? 0 : num(limpeza?.apps?.sobras);
  const mbSobra = Array.isArray(limpeza?.apps) ? 0 : num(limpeza?.apps?.estimado_sobra_mb);
  const naoClassificados = Array.isArray(limpeza?.apps) ? [] : lista<string>(limpeza?.apps?.nao_classificados);
  const servicosLimpeza = lista<ItemLimpeza>(limpeza?.servicos);
  const tarefasLimpeza = lista<ItemLimpeza>(limpeza?.tarefas);
  const espacoLimpeza = lista<ItemLimpeza>(limpeza?.espaco);
  const script = limpeza?.plano?.script ?? '';
  const restaurarScript = limpeza?.plano?.restaurar ?? '';

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
        <button className={painel === 'limpeza' ? 'ativo' : ''} onClick={() => setPainel('limpeza')}>
          <Trash2 size={16} /> Limpeza
          <small>o que sai do Windows sem quebrar nada</small>
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

      {painel === 'limpeza' && (
        <>
          {limpeza && limpeza.lido === false && (
            <div className="maquina-alerta">
              <AlertTriangle size={16} /> {limpeza.motivo ?? 'Esta leitura é do Windows.'}
            </div>
          )}

          <div className="metric-grid maquina-metricas">
            <div className="metric-card">
              <span className="metric-icon"><Trash2 size={18} /></span>
              <div><strong>{sobras}</strong><span>Apps de loja sem uso</span></div>
              <small>~{mbSobra} MB estimados</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><Wrench size={18} /></span>
              <div><strong>{tarefasLimpeza.filter((i) => i.veredito === 'sobra').length}</strong><span>Tarefas de telemetria</span></div>
              <small>{tarefasLimpeza.length} do catálogo nesta máquina</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><Cpu size={18} /></span>
              <div><strong>{servicosLimpeza.filter((i) => i.veredito === 'sobra').length}</strong><span>Serviços sem uso</span></div>
              <small>todos voltam com um comando</small>
            </div>
            <div className="metric-card">
              <span className="metric-icon"><HardDriveDownload size={18} /></span>
              <div><strong>{espacoLimpeza.filter((i) => i.veredito !== 'essencial').length}</strong><span>Caches a limpar</span></div>
              <small>{naoClassificados.length} app fora do catálogo</small>
            </div>
          </div>

          <section className="panel maquina-braco">
            <header>
              <div>
                <span className="maquina-selo">os braços</span>
                <h2>Não quero apertar nada</h2>
                <p>
                  Isto não gera script: o JARVIS executa a limpeza agora — fecha processo de sobra,
                  remove app de loja sem uso, desativa tarefa de telemetria e serviço inútil, limpa
                  cache e lixeira. Antes, ele grava a <b>foto do que existe</b> (apps, serviços e
                  tarefas) e tenta criar um <b>ponto de restauração</b> do Windows. Driver e
                  essencial nunca entram.
                </p>
                {planoArrumar?.aviso_admin && (
                  <div className="maquina-aviso-admin">
                    <p>{planoArrumar.aviso_admin}</p>
                    <button className="button" onClick={() => void pedirAdministrador()} disabled={elevando || !backendOnline}>
                      <ShieldCheck size={15} /> {elevando ? 'Pedindo ao Windows…' : 'Reabrir como administrador'}
                    </button>
                    {resultadoElevar?.motivo && <small>{resultadoElevar.motivo}</small>}
                  </div>
                )}
                <label className="maquina-ousado">
                  <input type="checkbox" checked={ousado} onChange={(evento) => setOusado(evento.target.checked)} />
                  <span>
                    <b>Modo ousado</b> — inclui o que tem volta: Xbox, Teams, Search, Superfetch e
                    hibernação. WinSxS, Windows.old, Installer e Prefetch continuam fora.
                  </span>
                </label>
              </div>
              <div className="maquina-braco-botoes">
                <button className="button button-primary" onClick={() => void arrumar(false)} disabled={arrumando || !backendOnline}>
                  <Zap size={16} /> {arrumando ? 'Arrumando…' : 'Arrumar agora'}
                </button>
                <button className="button" onClick={() => void arrumar(true)} disabled={arrumando || !backendOnline}>
                  <Undo2 size={16} /> Desfazer a última
                </button>
              </div>
            </header>

            {arrumado && (
              <div className="maquina-braco-resultado">
                <p className="maquina-braco-resumo">{arrumado.resumo}</p>
                {arrumado.instantaneo && (
                  <small className="maquina-nota">Foto de antes: <code>{arrumado.instantaneo}</code></small>
                )}
                <small className="maquina-nota">
                  {arrumado.ponto_de_restauracao?.criado
                    ? 'Ponto de restauração criado — Win+R, rstrui, escolha “JARVIS antes da limpeza”.'
                    : arrumado.ponto_de_restauracao?.motivo ?? ''}
                </small>
                {arrumado.diario && <small className="maquina-nota">Diário: <code>{arrumado.diario}</code></small>}
                {lista<AcaoFeita>(arrumado.acoes).length > 0 && (
                  <ul>
                    {lista<AcaoFeita>(arrumado.acoes).map((acao) => {
                      const falta = lista<NonNullable<ResultadoArrumar['nao_feitas']>[number]>(arrumado.nao_feitas)
                        .find((item) => item.nome === acao.nome && item.comando === acao.comando);
                      return (
                        <li key={acao.id ?? acao.nome} className={acao.ok ? 'ok' : 'falhou'}>
                          <b>{acao.ok ? '✓' : '✕'}</b>
                          <span>{acao.nome}</span>
                          <small>{acao.ok ? acao.ganho || acao.tipo : falta?.motivo ?? acao.saida}</small>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {arrumado.como_resolver && <p className="maquina-nota">{arrumado.como_resolver}</p>}
                {lista<string>(arrumado.sem_volta).length > 0 && (
                  <p className="maquina-nota">
                    Sem volta (não têm como voltar): {lista<string>(arrumado.sem_volta).join(', ')}.
                  </p>
                )}
              </div>
            )}
          </section>

          {limpeza?.plano?.resumo && <p className="maquina-resumo">{limpeza.plano.resumo}</p>}

          <section className="panel maquina-script">
            <header>
              <div>
                <h2>O script, para você ler antes</h2>
                <p>{limpeza?.plano?.aviso ?? 'Uma linha por comando. Nada roda daqui: você salva, lê e roda como administrador.'}</p>
              </div>
              <div className="maquina-script-botoes">
                <button className="button" onClick={() => void copiar(script, 'Script de limpeza')} disabled={!script}>
                  Copiar script
                </button>
                <button className="button button-primary" onClick={() => salvar(script, 'debloat.bat')} disabled={!script}>
                  Salvar debloat.bat
                </button>
                <button className="button" onClick={() => salvar(restaurarScript, 'restaurar-windows.bat')} disabled={!restaurarScript}>
                  Salvar restaurar.bat
                </button>
              </div>
            </header>
            <pre className="maquina-pre">{script || 'Sem script: nada do catálogo foi encontrado nesta máquina.'}</pre>
            <p className="maquina-nota">
              O que é <b>cuidado</b> já vem comentado com <code>rem</code>: descomente só o que você não usa.
              O <code>restaurar-windows.bat</code> religa serviço e tarefa e mostra o comando de volta de cada app.
            </p>
          </section>

          {[
            { titulo: 'Apps de loja', itens: appsDebloat, dica: 'Sai inteiro pelo próprio Windows; a loja reinstala.' },
            { titulo: 'Tarefas agendadas', itens: tarefasLimpeza, dica: 'Telemetria e manutenção que ninguém pediu.' },
            { titulo: 'Serviços', itens: servicosLimpeza, dica: 'Só os sem uso viram comando; o NVIDIA Container fica comentado.' },
            { titulo: 'Espaço em disco', itens: espacoLimpeza, dica: 'Mede o que existe; nunca promete número que não mediu.' },
          ].map(({ titulo, itens, dica }) => (
            itens.length === 0 ? null : (
              <section key={titulo} className="panel maquina-grupo">
                <header>
                  <div>
                    <h2>{titulo}</h2>
                    <p>{dica}</p>
                  </div>
                  <strong>{itens.length}</strong>
                </header>
                <ul>
                  {itens.map((item) => {
                    const id = `limpeza:${item.id ?? item.pacote ?? item.nome}`;
                    const expandido = aberto === id;
                    return (
                      <li key={id} className={expandido ? 'aberto' : ''}>
                        <button
                          className={`maquina-linha maquina-veredito-${item.veredito}`}
                          onClick={() => setAberto(expandido ? '' : id)}
                          aria-expanded={expandido}
                        >
                          <ChevronDown size={15} />
                          <span className="nome">{item.nome}</span>
                          <span className={`maquina-veredito maquina-veredito-${item.veredito}`}>{item.veredito}</span>
                          <span className="mem">
                            {item.tamanho_mb != null ? mb(item.tamanho_mb)
                              : item.tamanho_estimado_mb ? `~${item.tamanho_estimado_mb} MB`
                                : item.ganho ?? ''}
                          </span>
                        </button>
                        {expandido && (
                          <div className="maquina-detalhe">
                            <p>{item.o_que_e}</p>
                            {item.se_remover && <p><b>Se remover:</b> {item.se_remover}</p>}
                            {item.se_parar && <p><b>Se parar:</b> {item.se_parar}</p>}
                            {item.estado && <p className="maquina-volta"><b>Agora:</b> {item.estado}</p>}
                            {item.comando && (
                              <button className="maquina-codigo" onClick={() => void copiar(item.comando, item.nome)}>
                                <code>{item.comando}</code>
                              </button>
                            )}
                            {item.desfazer && <p className="maquina-volta"><b>Desfazer:</b> <code>{item.desfazer}</code></p>}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )
          ))}

          {naoClassificados.length > 0 && (
            <section className="panel maquina-grupo maquina-grupo-desconhecido">
              <header>
                <div>
                  <h2>Apps fora do catálogo</h2>
                  <p>Podem ser seus. Não classifico o que não conheço — e não mando remover.</p>
                </div>
                <strong>{naoClassificados.length}</strong>
              </header>
              <ul>
                {naoClassificados.slice(0, 40).map((nome) => (
                  <li key={nome}><div className="maquina-linha maquina-linha-estatica"><span className="nome">{nome}</span></div></li>
                ))}
              </ul>
            </section>
          )}

          <section className="panel maquina-regra">
            <header><Sparkles size={16} /> <h2>O que este plano nunca toca</h2></header>
            <p>
              Microsoft Store, instalador do <code>winget</code>, Segurança do Windows, runtime VCLibs/UI.Xaml,
              Calculadora, Fotos, Ferramenta de Captura, fila de impressão, Wi-Fi, áudio, horário e a pasta
              <code>C:\Windows\Installer</code>. Tirar qualquer um deles não libera espaço de verdade e quebra
              alguma coisa que você usa todo dia.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
