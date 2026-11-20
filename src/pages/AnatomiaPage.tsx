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
  Tv,
  Wifi,
} from 'lucide-react';
import { getAnatomiaFontes, lerAnatomia } from '../lib/api';
import type { AnatomiaFontes, AnatomiaResultado } from '../lib/api';
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

export function AnatomiaPage() {
  const [fontes, setFontes] = useState<AnatomiaFontes | null>(null);
  const [resultado, setResultado] = useState<AnatomiaResultado | null>(null);
  const [lendo, setLendo] = useState<string>('');
  const [erro, setErro] = useState('');
  const [ip, setIp] = useState('');
  const [carregando, setCarregando] = useState(false);

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
