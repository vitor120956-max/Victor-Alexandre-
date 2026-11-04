import { MonitorSmartphone, X } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '../context/AppContext';

/**
 * Aviso de tela velha: o servidor é uma versão e a interface servida é outra.
 *
 * Nasceu de um print real: *“já atualizei mas ainda não tem a parte para botar
 * as APIs”*, com o rodapé dizendo `VERSÃO 0.5.0`. O Python estava novo; a tela
 * não. Sem este aviso, a pessoa não tem como saber qual das duas metades falhou
 * — e a conclusão natural é “o recurso não existe”.
 *
 * Limite honesto: se a tela servida for **antiga de verdade**, ela não tem este
 * componente e não consegue avisar nada. Ele existe para o caso de atualização
 * **pela metade** (Python novo, `web-dist` velho) — e aí a diferença aparece na
 * primeira tela nova que abrir. Para o caso antigo, o caminho é o
 * `conferir-versao.bat`, que roda fora do navegador.
 */
export function InterfaceBanner() {
  const { interfaceServida, backendVersion } = useApp();
  const [fechado, setFechado] = useState(false);
  if (fechado || !interfaceServida.velha) return null;
  return (
    <div className="update-banner interface-banner">
      <MonitorSmartphone size={15} />
      <span>
        <b>A tela é mais velha que o servidor.</b>{' '}
        A interface servida ({interfaceServida.pasta}) é a {interfaceServida.versao ?? 'sem carimbo'} e o servidor é{' '}
        {backendVersion ?? '?'}. A atualização não chegou nesta pasta: rode <code>atualizar.bat</code> e abra de novo.
        Para conferir, clique duas vezes em <code>conferir-versao.bat</code>.
      </span>
      <button className="icon-button" onClick={() => setFechado(true)} aria-label="Fechar aviso de interface">
        <X size={15} />
      </button>
    </div>
  );
}
