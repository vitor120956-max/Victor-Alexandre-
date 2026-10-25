import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bluetooth,
  CheckCircle2,
  Cpu,
  Download,
  FileCheck2,
  FolderTree,
  Gauge,
  Globe,
  HardDrive,
  LoaderCircle,
  Package,
  PackageMinus,
  Play,
  ShieldAlert,
  Terminal,
  Wrench,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import type { SkillExecution } from '../lib/api';
import '../diagramas.css';
import '../selecao.css';
import '../revisao.css';
import '../continuidade.css';
import '../sistema.css';

type SistemaTab = 'ambiente' | 'disco' | 'pastas' | 'drivers' | 'bluetooth' | 'rede' | 'baixar' | 'assinatura' | 'instalar' | 'desinstalar' | 'executar' | 'regras';
type Row = Record<string, unknown>;

const tabs: Array<{ id: SistemaTab; label: string; hint: string; icon: typeof Cpu }> = [
  { id: 'ambiente', label: 'Ambiente', hint: 'Que máquina é esta', icon: Cpu },
  { id: 'disco', label: 'Disco', hint: 'Espaço livre real', icon: HardDrive },
  { id: 'pastas', label: 'Pastas', hint: 'Inventário sem abrir', icon: FolderTree },
  { id: 'drivers', label: 'Drivers', hint: 'Módulos e assinatura', icon: Wrench },
  { id: 'bluetooth', label: 'Bluetooth', hint: 'Rádio e pareados', icon: Bluetooth },
  { id: 'rede', label: 'Rede', hint: 'Buscar e ler', icon: Globe },
  { id: 'baixar', label: 'Baixar', hint: 'Quarentena e hash', icon: Download },
  { id: 'assinatura', label: 'Assinatura', hint: 'Origem e integridade', icon: FileCheck2 },
  { id: 'instalar', label: 'Instalar', hint: 'Plano e risco', icon: Package },
  { id: 'desinstalar', label: 'Desinstalar', hint: 'Remoção simétrica', icon: PackageMinus },
  { id: 'executar', label: 'Executar', hint: 'O efeito real', icon: Play },
  { id: 'regras', label: 'Regras', hint: 'Guardas e limites', icon: ShieldAlert },
];

const niveis = [
  { id: 'lite', label: 'Lite — só o que bloqueia' },
  { id: 'full', label: 'Full — bloqueios e correções' },
  { id: 'ultra', label: 'Ultra — inclui perguntas' },
];

const semToken = 'sem token de host';

export function SistemaPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [tab, setTab] = useState<SistemaTab>('ambiente');
  const [nivel, setNivel] = useState('full');
  const [token, setToken] = useState('');
  const [caminhos, setCaminhos] = useState('');
  const [minimo, setMinimo] = useState('0');
  const [raiz, setRaiz] = useState('.');
  const [profundidade, setProfundidade] = useState('2');
  const [limite, setLimite] = useState('120');
  const [ocultos, setOcultos] = useState(false);
  const [filtro, setFiltro] = useState('');
  const [acaoRede, setAcaoRede] = useState<'buscar' | 'olhar'>('buscar');
  const [consulta, setConsulta] = useState('driver bluetooth windows 11');
  const [urlRede, setUrlRede] = useState('');
  const [urlDownload, setUrlDownload] = useState('');
  const [arquivoAssinatura, setArquivoAssinatura] = useState('');
  const [hashEsperado, setHashEsperado] = useState('');
  const [assinaturaDestacada, setAssinaturaDestacada] = useState('');
  const [exigirAssinatura, setExigirAssinatura] = useState(false);
  const [pacoteRemover, setPacoteRemover] = useState('');
  const [arquivo, setArquivo] = useState('');
  const [pacote, setPacote] = useState('');
  const [silencioso, setSilencioso] = useState(true);
  const [confirmacao, setConfirmacao] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execution, setExecution] = useState<SkillExecution | null>(null);

  const resultado = execution?.ok ? asObj(execution.result) : null;
  const markdown = useMemo(() => txt(resultado?.markdown), [resultado]);

  const trocarTab = (destino: SistemaTab) => {
    setTab(destino);
    setErro('');
    setExecution(null);
  };

  const parametros = (): Record<string, unknown> => {
    const base = { autorizacao: token, modo: nivel };
    if (tab === 'regras') return {};
    if (tab === 'ambiente') return { autorizacao: token, modo: nivel, detalhe: 'full' };
    if (tab === 'disco') return { ...base, caminhos, minimo: Number(minimo) || 0 };
    if (tab === 'pastas') return { ...base, raiz, profundidade: Number(profundidade) || 2, limite: Number(limite) || 120, incluir_ocultos: ocultos };
    if (tab === 'drivers') return { ...base, filtro, limite: 120 };
    if (tab === 'bluetooth') return { ...base, filtro };
    if (tab === 'rede') return { ...base, acao: acaoRede, consulta, url: urlRede, limite: 8 };
    if (tab === 'baixar') return { ...base, url: urlDownload };
    if (tab === 'assinatura') return { ...base, arquivo: arquivoAssinatura, hash_esperado: hashEsperado, assinatura_arquivo: assinaturaDestacada };
    if (tab === 'instalar') return { ...base, arquivo, pacote, silencioso, exigir_assinatura: exigirAssinatura };
    if (tab === 'desinstalar') return { ...base, arquivo, pacote: pacoteRemover };
    return { ...base, confirmacao };
  };

  const opcoes = () => (tab === 'baixar' || tab === 'executar' ? { confirmed: confirmado } : tab === 'instalar' ? { dryRun: true } : undefined);

  const executar = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!backendOnline) {
      setErro('A API Python está offline. Inicie o núcleo com “npm run dev”; nada foi lido da máquina.');
      return;
    }
    if (tab !== 'regras' && !token.trim()) {
      setErro('Cole o token de storage/host-token.txt. Ele aparece no terminal onde a API subiu.');
      return;
    }
    if ((tab === 'baixar' || tab === 'executar') && !confirmado) {
      setErro('Marque a confirmação: estas duas abas escrevem no disco de verdade.');
      return;
    }
    setBusy(true);
    setErro('');
    setExecution(null);
    try {
      const resposta = await executeSkill(`sistema.${tab}`, parametros(), opcoes());
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou o pedido.');
        return;
      }
      setExecution(resposta);
      const plano = asObj(resposta.result);
      if ((tab === 'instalar' || tab === 'desinstalar') && txt(plano.confirmacao)) setConfirmacao(txt(plano.confirmacao));
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao executar a skill.');
    } finally {
      setBusy(false);
    }
  };

  const copiar = async (valor: string, titulo: string) => {
    if (!valor) return;
    try {
      await navigator.clipboard.writeText(valor);
      pushToast(titulo, 'O texto está na área de transferência.');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto manualmente.', 'warning');
    }
  };

  const bloqueado = num(asObj(resultado?.counts).must) > 0;
  const catalogo = tab === 'regras' ? resultado : null;
  const guardas = asRows(catalogo?.guardas);
  const operacoes = asRows(catalogo?.operacoes);
  const naoFaz = asList(catalogo?.nao_faz);
  const instaladores = asList(catalogo?.instaladores);
  const limites = asObj(catalogo?.limites);
  const download = asObj(resultado?.download);
  const execucao = asObj(resultado?.execucao);

  return (
    <div className="diagram-section selecao-page revisao-page continuidade-page sistema-page">
      <section className="panel diagram-intro">
        <span className="diagram-intro-icon"><Terminal size={22} /></span>
        <div>
          <span className="eyebrow">A PRIMEIRA CAMADA QUE TOCA A MÁQUINA DE VERDADE</span>
          <h2>Diagnóstico local, busca na web e instalador com trava</h2>
          <p>As camadas anteriores liam texto colado. Esta lê o host: espaço em disco, inventário de pastas, drivers e Bluetooth. Depois, com a rede ligada, busca, baixa para a quarentena e — só com a trava ligada e um token de uso único — executa o instalador. Tudo passa por um token de host que só existe em <code>storage/host-token.txt</code>, no terminal de quem subiu a API.</p>
        </div>
        <ul className="diagram-laws">
          <li><strong>Token primeiro</strong><span>Sem ele, nada responde.</span></li>
          <li><strong>Rede desligada</strong><span>Opt-in por variável de ambiente.</span></li>
          <li><strong>Sem shell livre</strong><span>Allowlist fechada de instaladores.</span></li>
          <li><strong>Aviso de origem</strong><span>Num contêiner, é o contêiner.</span></li>
        </ul>
      </section>

      <nav className="diagram-tabs" aria-label="Operações de sistema">
        {tabs.map(({ id, label, hint, icon: Icon }) => (
          <button key={id} type="button" className={tab === id ? 'is-active' : undefined} onClick={() => trocarTab(id)} aria-pressed={tab === id}>
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="diagram-layout">
        <section className="panel diagram-form">
          <header className="diagram-form-head">
            <div>
              <span className="eyebrow">{tabs.find((item) => item.id === tab)?.label.toUpperCase()}</span>
              <h2>{tabs.find((item) => item.id === tab)?.hint}</h2>
            </div>
            {tab !== 'regras' && (
              <label className="diagram-level">
                <span>NÍVEL</span>
                <select value={nivel} onChange={(event) => setNivel(event.target.value)}>
                  {niveis.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
          </header>

          <form className="form-stack" onSubmit={executar}>
            {tab !== 'regras' && (
              <label className="field">
                <span>Token de host — <code>storage/host-token.txt</code>, impresso no terminal da API</span>
                <input
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder={semToken}
                  autoComplete="off"
                  spellCheck={false}
                />
                <small className="selecao-contador">Fica só na memória desta aba; não é salvo no navegador.</small>
              </label>
            )}

            {tab === 'disco' && (
              <div className="sistema-dupla">
                <label className="field">
                  <span>Unidades — vazio mede todas as montagens</span>
                  <input value={caminhos} onChange={(event) => setCaminhos(event.target.value)} placeholder="/ , /home" />
                </label>
                <label className="field">
                  <span>Mínimo livre (%)</span>
                  <input value={minimo} onChange={(event) => setMinimo(event.target.value)} inputMode="numeric" />
                </label>
              </div>
            )}

            {tab === 'pastas' && (
              <>
                <label className="field">
                  <span>Raiz</span>
                  <input value={raiz} onChange={(event) => setRaiz(event.target.value)} placeholder="." spellCheck={false} />
                </label>
                <div className="sistema-dupla">
                  <label className="field">
                    <span>Profundidade (0–6)</span>
                    <input value={profundidade} onChange={(event) => setProfundidade(event.target.value)} inputMode="numeric" />
                  </label>
                  <label className="field">
                    <span>Limite de entradas</span>
                    <input value={limite} onChange={(event) => setLimite(event.target.value)} inputMode="numeric" />
                  </label>
                </div>
                <label className="continuidade-check">
                  <input type="checkbox" checked={ocultos} onChange={(event) => setOcultos(event.target.checked)} />
                  <span>Incluir arquivos e pastas ocultos — cofre e chave aparecem só pelo nome</span>
                </label>
              </>
            )}

            {(tab === 'drivers' || tab === 'bluetooth') && (
              <label className="field">
                <span>Filtro por nome — vazio lista tudo</span>
                <input value={filtro} onChange={(event) => setFiltro(event.target.value)} placeholder={tab === 'bluetooth' ? 'fone' : 'btusb'} />
              </label>
            )}

            {tab === 'rede' && (
              <>
                <div className="sistema-dupla">
                  <label className="field">
                    <span>Ação</span>
                    <select value={acaoRede} onChange={(event) => setAcaoRede(event.target.value as 'buscar' | 'olhar')}>
                      <option value="buscar">buscar</option>
                      <option value="olhar">olhar</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>{acaoRede === 'buscar' ? 'Consulta' : 'URL'}</span>
                    {acaoRede === 'buscar' ? (
                      <input value={consulta} onChange={(event) => setConsulta(event.target.value)} />
                    ) : (
                      <input value={urlRede} onChange={(event) => setUrlRede(event.target.value)} placeholder="https://" spellCheck={false} />
                    )}
                  </label>
                </div>
              </>
            )}

            {tab === 'baixar' && (
              <label className="field">
                <span>URL do arquivo — vai para <code>storage/host-downloads</code></span>
                <input value={urlDownload} onChange={(event) => setUrlDownload(event.target.value)} placeholder="https://fabricante.com/driver.msi" spellCheck={false} />
              </label>
            )}

            {tab === 'assinatura' && (
              <>
                <label className="field">
                  <span>Arquivo da quarentena</span>
                  <input value={arquivoAssinatura} onChange={(event) => setArquivoAssinatura(event.target.value)} placeholder="storage/host-downloads/…-driver.msi" spellCheck={false} />
                </label>
                <label className="field">
                  <span>SHA-256 esperado — o hash publicado pelo projeto</span>
                  <input value={hashEsperado} onChange={(event) => setHashEsperado(event.target.value)} placeholder="64 caracteres hexadecimais" spellCheck={false} />
                </label>
                <label className="field">
                  <span>Assinatura destacada (opcional) — <code>.sig</code> ou <code>.asc</code> na quarentena</span>
                  <input value={assinaturaDestacada} onChange={(event) => setAssinaturaDestacada(event.target.value)} placeholder="storage/host-downloads/…-driver.msi.asc" spellCheck={false} />
                </label>
              </>
            )}

            {tab === 'instalar' && (
              <>
                <label className="field">
                  <span>Arquivo da quarentena — o caminho devolvido por <code>Baixar</code></span>
                  <input value={arquivo} onChange={(event) => setArquivo(event.target.value)} placeholder="storage/host-downloads/…-driver.msi" spellCheck={false} />
                </label>
                <label className="field">
                  <span>ou pacote — <code>pip:nome</code> ou <code>npm:nome</code></span>
                  <input value={pacote} onChange={(event) => setPacote(event.target.value)} placeholder="pip:playsound" spellCheck={false} />
                </label>
                <label className="continuidade-check">
                  <input type="checkbox" checked={silencioso} onChange={(event) => setSilencioso(event.target.checked)} />
                  <span>Instalação silenciosa (<code>/S</code>, <code>/qb</code>) — reduz clique, não reduz risco</span>
                </label>
                <label className="continuidade-check is-warning">
                  <input type="checkbox" checked={exigirAssinatura} onChange={(event) => setExigirAssinatura(event.target.checked)} />
                  <span>Exigir assinatura válida — o plano bloqueia e a execução recusa quando não confirmar</span>
                </label>
              </>
            )}

            {tab === 'desinstalar' && (
              <>
                <label className="field">
                  <span>Alvo — <code>dpkg:</code>, <code>rpm:</code>, <code>pip:</code>, <code>npm:</code> ou <code>msi:&#123;GUID&#125;</code></span>
                  <input value={pacoteRemover} onChange={(event) => setPacoteRemover(event.target.value)} placeholder="dpkg:curl" spellCheck={false} />
                </label>
                <label className="field">
                  <span>ou um <code>.msi</code> da quarentena</span>
                  <input value={arquivo} onChange={(event) => setArquivo(event.target.value)} placeholder="storage/host-downloads/…-driver.msi" spellCheck={false} />
                </label>
              </>
            )}

            {tab === 'executar' && (
              <label className="field">
                <span>Confirmação — o token de 8 caracteres devolvido pelo plano</span>
                <input value={confirmacao} onChange={(event) => setConfirmacao(event.target.value)} placeholder="a1b2c3d4" spellCheck={false} />
                <small className="selecao-contador">Vale 10 minutos, serve uma vez e só para o arquivo do plano.</small>
              </label>
            )}

            {(tab === 'baixar' || tab === 'executar') && (
              <label className="continuidade-check is-warning">
                <input type="checkbox" checked={confirmado} onChange={(event) => setConfirmado(event.target.checked)} />
                <span>Confirmo que esta operação {tab === 'baixar' ? 'grava um arquivo no disco' : 'executa um instalador de terceiro'}</span>
              </label>
            )}

            <div className="diagram-actions">
              <button type="submit" className="primary" disabled={busy}>
                {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
                {busy ? 'Executando' : tab === 'regras' ? 'Abrir catálogo' : 'Ler a máquina'}
              </button>
              {markdown && (
                <button type="button" className="ghost" onClick={() => copiar(markdown, 'Parecer copiado')}>
                  Copiar parecer
                </button>
              )}
            </div>

            {erro && <p className="diagram-error"><AlertTriangle size={14} />{erro}</p>}

            <p className="sistema-aviso">
              <ShieldAlert size={14} />
              Os dados são da máquina que executa a API. Num contêiner, é o contêiner — não o seu PC.
            </p>
          </form>
        </section>

        <section className="panel diagram-output">
          {!resultado ? (
            <p className="diagram-empty"><Gauge size={14} />Rode uma operação para ver o parecer.</p>
          ) : (
            <>
              <Verdict blocked={bloqueado}>{txt(resultado.verdict)}</Verdict>

              {tbMetrics(tab).length > 0 && (
                <div className="diagram-metrics">
                  {tbMetrics(tab).map(({ label, chave }) => (
                    <Metric key={chave} label={label} value={formatar(num(asObj(resultado.metrics)[chave]))} />
                  ))}
                </div>
              )}

              {tab === 'ambiente' && <Tabela titulo="Máquina" colunas={[{ titulo: 'Chave', chave: 'chave' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'disco' && <Tabela titulo="Unidades" colunas={[{ titulo: 'Unidade', chave: 'unidade', tipo: 'code' }, { titulo: 'Tipo', chave: 'tipo' }, { titulo: 'Total', chave: 'total' }, { titulo: 'Livre', chave: 'livre' }, { titulo: 'Livre %', chave: 'livrePct', tipo: 'pill' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'pastas' && <Tabela titulo="Entradas" colunas={[{ titulo: 'Nome', chave: 'nome' }, { titulo: 'Tipo', chave: 'tipo', tipo: 'pill' }, { titulo: 'Bytes', chave: 'bytes' }, { titulo: 'Modificado', chave: 'modificado' }, { titulo: 'Protegido', chave: 'protegido', tipo: 'pill' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'drivers' && <Tabela titulo="Drivers" colunas={[{ titulo: 'Nome', chave: 'nome' }, { titulo: 'Versão', chave: 'versao' }, { titulo: 'Assinado', chave: 'assinado', tipo: 'pill' }, { titulo: 'Fonte', chave: 'fonte' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'bluetooth' && <Tabela titulo="Dispositivos" colunas={[{ titulo: 'Nome', chave: 'nome' }, { titulo: 'Tipo', chave: 'tipo', tipo: 'pill' }, { titulo: 'MAC', chave: 'mac', tipo: 'code' }, { titulo: 'Estado', chave: 'estado' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'rede' && <Tabela titulo="Resultados" colunas={[{ titulo: '#', chave: 'posicao' }, { titulo: 'Título', chave: 'titulo' }, { titulo: 'URL', chave: 'url', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'baixar' && <Tabela titulo="Arquivo" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'assinatura' && <Tabela titulo="Verificação" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'instalar' && <Tabela titulo="Plano" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'desinstalar' && <Tabela titulo="Plano de remoção" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}
              {tab === 'executar' && <Tabela titulo="Execução" colunas={[{ titulo: 'Campo', chave: 'campo' }, { titulo: 'Valor', chave: 'valor', tipo: 'code' }]} linhas={asRows(resultado.rows)} />}

              {txt(download.sha256) && (
                <div className="sistema-hash">
                  <span>SHA-256</span>
                  <code>{txt(download.sha256)}</code>
                  <button type="button" onClick={() => copiar(txt(download.sha256), 'Hash copiado')}>Copiar</button>
                </div>
              )}

              {txt(execucao.comando) && (
                <pre className="sistema-shell">{txt(execucao.comando)}
                  {txt(execucao.saida) ? `\n\n${txt(execucao.saida)}` : ''}
                  {txt(execucao.erro) ? `\n\n${txt(execucao.erro)}` : ''}
                </pre>
              )}

              <Findings items={asRows(resultado.findings)} />

              {tab === 'regras' && (
                <>
                  <Tabela titulo="Guardas" colunas={[{ titulo: 'Ordem', chave: 'ordem' }, { titulo: 'Guarda', chave: 'guarda' }, { titulo: 'Padrão', chave: 'padrao', tipo: 'pill' }]} linhas={guardas} />
                  <Tabela titulo="Operações" colunas={[{ titulo: 'Skill', chave: 'id', tipo: 'code' }, { titulo: 'Entrada', chave: 'entrada' }, { titulo: 'Saída', chave: 'saida' }]} linhas={operacoes} />
                  <div className="sistema-listas">
                    <div>
                      <h4>Instaladores aceitos</h4>
                      <ul>{instaladores.map((item) => <li key={item}><code>{item}</code></li>)}</ul>
                    </div>
                    <div>
                      <h4>Recusa declarada</h4>
                      <ul>{naoFaz.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                  </div>
                  <p className="selecao-contador">
                    Texto {formatar(num(limites.texto))} · entradas {formatar(num(limites.entradas))} · profundidade {formatar(num(limites.profundidade))} · download {formatar(num(limites.download))} bytes
                  </p>
                </>
              )}

              <Limitations items={resultado.limitations} />

              {markdown && (
                <details className="diagram-markdown">
                  <summary>Parecer em Markdown</summary>
                  <pre>{markdown}</pre>
                </details>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function Verdict({ children, blocked }: { children: React.ReactNode; blocked: boolean }) {
  return (
    <p className="diagram-verdict">
      {blocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
      {children}
    </p>
  );
}

function Findings({ items }: { items: Row[] }) {
  if (!items.length) return <p className="diagram-empty"><CheckCircle2 size={14} />Nada contra as regras deste nível.</p>;
  return (
    <div className="diagram-findings">
      {items.map((item) => {
        const grupo = txt(item.group);
        return (
          <article className={`diagram-finding is-${grupo}`} key={`${txt(item.id)}-${txt(item.kind)}`}>
            <header>
              <span className="diagram-group">{grupos[grupo] ?? grupo}</span>
              <strong>{txt(item.title)}</strong>
              <code>{txt(item.location)}</code>
            </header>
            <dl>
              <div><dt>O que é</dt><dd>{txt(item.what)}</dd></div>
              <div><dt>Problema</dt><dd>{txt(item.problem)}</dd></div>
              <div><dt>Correção</dt><dd>{txt(item.fix)}</dd></div>
              <div><dt>Se ignorar</dt><dd>{txt(item.ifSkipped)}</dd></div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function Limitations({ items }: { items: unknown }) {
  const linhas = asList(items);
  if (!linhas.length) return null;
  return (
    <div className="diagram-limitations">
      <strong>LIMITES DECLARADOS</strong>
      <ul>{linhas.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function Tabela({ titulo, colunas: cols, linhas }: { titulo: string; colunas: Coluna[]; linhas: Row[] }) {
  if (!linhas.length) return null;
  return (
    <div className="selecao-table-block">
      <h4>{titulo}</h4>
      <div className="diagram-scroll">
        <table className="diagram-table">
          <thead><tr>{cols.map((coluna) => <th key={coluna.chave}>{coluna.titulo}</th>)}</tr></thead>
          <tbody>
            {linhas.map((linha, indice) => (
              <tr key={indice}>
                {cols.map((coluna) => {
                  const bruto = linha[coluna.chave];
                  const valor = typeof bruto === 'boolean' ? (bruto ? 'sim' : 'não') : (typeof bruto === 'number' ? formatar(bruto) : txt(bruto) || '—');
                  if (coluna.tipo === 'code') return <td key={coluna.chave}><code>{valor}</code></td>;
                  if (coluna.tipo === 'pill') return <td key={coluna.chave}><span className={['diagram-state', tom(valor)].filter(Boolean).join(' ')}>{valor}</span></td>;
                  return <td key={coluna.chave}>{valor}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type Coluna = { titulo: string; chave: string; largura?: string; tipo?: 'code' | 'pill' };

const grupos: Record<string, string> = { must: 'Corrigir obrigatoriamente', should: 'Corrigir', nice: 'Opcional' };

const formatar = (valor: number): string => valor.toLocaleString('pt-BR');

const tom = (valor: string): string => {
  const baixo = valor.toLowerCase();
  if (['must', 'alto', 'não', 'protegido', 'arquivo'].includes(baixo)) return 'is-alert';
  if (['should', 'médio', 'pasta'].includes(baixo)) return 'is-warn';
  if (['nice', 'baixo', 'sim'].includes(baixo)) return 'is-ok';
  return '';
};

const tbMetrics = (tab: SistemaTab): Array<{ label: string; chave: string }> => {
  if (tab === 'ambiente') return [{ label: 'NÚCLEOS', chave: 'nucleos' }, { label: 'MEMÓRIA LIVRE (GB)', chave: 'memoriaLivre' }, { label: 'CONTÊINER', chave: 'container' }];
  if (tab === 'disco') return [{ label: 'UNIDADES', chave: 'unidades' }, { label: 'LIVRE (GB)', chave: 'livre' }, { label: 'MENOR LIVRE %', chave: 'menorLivrePct' }];
  if (tab === 'pastas') return [{ label: 'ENTRADAS', chave: 'entradas' }, { label: 'PASTAS', chave: 'pastas' }, { label: 'ARQUIVOS', chave: 'arquivos' }, { label: 'NEGADOS', chave: 'negados' }];
  if (tab === 'drivers') return [{ label: 'ITENS', chave: 'itens' }, { label: 'SEM VERSÃO', chave: 'semVersao' }, { label: 'NÃO ASSINADOS', chave: 'naoAssinados' }];
  if (tab === 'bluetooth') return [{ label: 'ADAPTADORES', chave: 'adaptadores' }, { label: 'PAREA DOS', chave: 'emparelhados' }];
  if (tab === 'rede') return [{ label: 'RESULTADOS', chave: 'resultados' }];
  if (tab === 'baixar') return [{ label: 'BYTES', chave: 'bytes' }];
  if (tab === 'assinatura') return [{ label: 'BYTES', chave: 'bytes' }, { label: 'HASH CONFERE', chave: 'hashConfere' }, { label: 'ASSINATURA', chave: 'assinatura' }];
  if (tab === 'desinstalar') return [{ label: 'PASSOS', chave: 'passos' }];
  if (tab === 'instalar') return [{ label: 'PASSOS', chave: 'passos' }];
  if (tab === 'executar') return [{ label: 'CÓDIGO', chave: 'codigo' }];
  return [];
};

function asObj(valor: unknown): Row {
  return valor && typeof valor === 'object' && !Array.isArray(valor) ? (valor as Row) : {};
}

function asRows(valor: unknown): Row[] {
  return Array.isArray(valor) ? valor.filter((item): item is Row => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function asList(valor: unknown): string[] {
  return Array.isArray(valor) ? valor.filter((item): item is string => typeof item === 'string') : [];
}

function txt(valor: unknown): string {
  if (typeof valor === 'string') return valor;
  if (typeof valor === 'number' || typeof valor === 'boolean') return String(valor);
  return '';
}

function num(valor: unknown): number {
  return typeof valor === 'number' ? valor : Number(valor) || 0;
}
