import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, X } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { testarChavesIA } from '../lib/api';

/**
 * Aviso de cota das chaves de IA — “está acabando” e “acabou”.
 *
 * O pedido: *“dá para o JARVIS avisar quando estiver acabando ou quando acabar
 * totalmente as APIs?”*. Sim, mas o aviso só vale se for **medido**. Quem sabe
 * é o processo Python, que viu o código HTTP de cada chave e os cabeçalhos
 * `x-ratelimit-*`; a tela recebe isso em `/api/ai/status` (campo `saude`) a cada
 * 30 s. Nada de estimativa: quando o provedor não manda o número, o aviso fala
 * do que aconteceu (429/401), não inventa porcentagem.
 *
 * Três estados aparecem:
 * - `apertando` (âmbar): alguma chave caiu ou o que resta no minuto é pouco;
 * - `esgotado` (vermelho): nenhuma chave responde — o modelo parou;
 * - `ok`/`local`/`sem_chave`: nada a avisar.
 *
 * O aviso é dispensável, mas volta sozinho quando a situação piora: a dispensa
 * é guardada por assinatura (situação + quantas chaves restam), não para sempre.
 */

const CHAVE = 'jarvis-cota-dispensada';

export function CotaBanner() {
  const { aiStatus, backendOnline, refreshBackend, pushToast } = useApp();
  const saude = aiStatus.saude;
  const [conferindo, setConferindo] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);
  const [dispensada, setDispensada] = useState<string | null>(() =>
    typeof window === 'undefined' ? null : window.sessionStorage.getItem(CHAVE),
  );
  const avisado = useRef<string>('');

  const assinatura = saude ? `${saude.situacao}:${saude.disponiveis}:${saude.total}` : '';
  const situacao = saude?.situacao ?? 'ok';
  const relevante =
    backendOnline && aiStatus.external && (situacao === 'apertando' || situacao === 'esgotado');
  const mostrar = relevante && dispensada !== assinatura;

  // O toque no ombro acontece uma vez por mudança de situação — o banner fica
  // na tela, mas quem está em outra página não veria nada.
  useEffect(() => {
    if (!mostrar || !saude) return;
    if (saude.situacao !== 'esgotado') return;
    if (avisado.current === assinatura) return;
    avisado.current = assinatura;
    pushToast('As chaves de IA acabaram', saude.resumo, 'warning');
  }, [mostrar, saude, assinatura, pushToast]);

  const conferir = useCallback(async () => {
    setConferindo(true);
    setResultado(null);
    try {
      const resposta = await testarChavesIA();
      setResultado(resposta.resumo);
      // O teste alimenta o diário do provedor; recarregar o status é o que
      // faz o banner sumir quando as três chaves voltaram a responder.
      await refreshBackend();
    } catch (error) {
      setResultado(error instanceof Error ? error.message : 'não consegui testar agora');
    } finally {
      setConferindo(false);
    }
  }, [refreshBackend]);

  const fechar = useCallback(() => {
    setDispensada(assinatura);
    window.sessionStorage.setItem(CHAVE, assinatura);
  }, [assinatura]);

  if (!mostrar || !saude) return null;

  const critico = saude.situacao === 'esgotado';
  return (
    <div className={`update-banner cota-banner ${critico ? 'cota-banner-critico' : 'cota-banner-atencao'}`}>
      <AlertTriangle size={15} />
      <span>
        <b>{critico ? 'As chaves de IA acabaram' : 'As chaves de IA estão acabando'}</b>{' '}
        {saude.aviso ?? saude.resumo}
        {resultado ? <> — {resultado}</> : null}
      </span>
      <button className="button" onClick={() => void conferir()} disabled={conferindo}>
        <RefreshCw size={13} /> {conferindo ? 'Testando…' : 'Conferir agora'}
      </button>
      <Link className="button" to="/configuracoes#chaves-de-ia">
        Chaves de IA
      </Link>
      <button className="icon-button" onClick={fechar} aria-label="Fechar aviso de cota">
        <X size={15} />
      </button>
    </div>
  );
}
