import { useCallback, useEffect, useState } from 'react';
import { Download, RefreshCw, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

/**
 * Aviso de versão nova, no topo da tela.
 *
 * A checagem baixa **só o `manifest.json`** (~56 KB) uma vez por sessão (ou a
 * cada hora, com o `sessionStorage`), e compara sha256 arquivo por arquivo — em
 * vez de comparar número de versão. Baixar também é delta: só o que mudou.
 *
 * Aplicar **não** reinicia nada sozinho: o texto final manda fechar a API e
 * rodar `iniciar-jarvis.bat`, porque é o processo que está na memória que
 * precisa morrer. Fingir que dá para reiniciar daqui seria mentira.
 */

type Checagem = {
  checou?: boolean;
  disponivel?: boolean;
  local?: string;
  remota?: string;
  a_baixar?: number;
  bytes?: number;
  resumo?: string;
  motivo?: string;
  ligado?: boolean;
};

type Preparo = { preparado?: boolean; baixados?: number; resumo?: string; palco?: string; motivo?: string };

const CHAVE = 'jarvis-checagem-versao';
const UMA_HORA = 60 * 60 * 1000;

export function UpdateBanner() {
  const { backendOnline, executeSkill } = useApp();
  const [checagem, setChecagem] = useState<Checagem | null>(null);
  const [preparo, setPreparo] = useState<Preparo | null>(null);
  const [aplicado, setAplicado] = useState(false);
  const [trabalhando, setTrabalhando] = useState(false);
  const [fechado, setFechado] = useState(false);

  useEffect(() => {
    if (!backendOnline) return;
    const ultima = Number(window.sessionStorage.getItem(CHAVE) || 0);
    if (Date.now() - ultima < UMA_HORA) return;
    let vivo = true;
    void executeSkill('atualizacao.verificar', { forcar: true })
      .then((resposta) => {
        if (!vivo) return;
        window.sessionStorage.setItem(CHAVE, String(Date.now()));
        if (resposta.ok) setChecagem((resposta.result ?? {}) as Checagem);
      })
      .catch(() => {
        // Sem rede ou API antiga: o aviso simplesmente não aparece.
      });
    return () => {
      vivo = false;
    };
  }, [backendOnline, executeSkill]);

  const baixar = useCallback(async () => {
    setTrabalhando(true);
    try {
      const resposta = await executeSkill('atualizacao.preparar', {}, { confirmed: true });
      if (resposta.ok) setPreparo((resposta.result ?? {}) as Preparo);
    } finally {
      setTrabalhando(false);
    }
  }, [executeSkill]);

  const aplicar = useCallback(async () => {
    setTrabalhando(true);
    try {
      const resposta = await executeSkill('atualizacao.aplicar', {}, { confirmed: true });
      if (resposta.ok) {
        setAplicado(true);
        setChecagem(null);
      }
    } finally {
      setTrabalhando(false);
    }
  }, [executeSkill]);

  if (fechado) return null;
  if (aplicado) {
    return (
      <div className="update-banner update-banner-pronto">
        <RefreshCw size={15} />
        <span>
          Atualização aplicada no disco. <b>Feche a janela da API no X</b> e rode{' '}
          <code>iniciar-jarvis.bat</code> para o código novo valer.
        </span>
        <button className="icon-button" onClick={() => setFechado(true)} aria-label="Fechar aviso"><X size={15} /></button>
      </div>
    );
  }
  if (!checagem?.disponivel) return null;

  const kb = Math.max(1, Math.round(Number(checagem.bytes || 0) / 1024));
  return (
    <div className="update-banner">
      <Download size={15} />
      <span>
        <b>Versão {checagem.remota}</b> disponível (a sua é {checagem.local}): {checagem.a_baixar} arquivo(s),{' '}
        {kb} KB — só o que mudou, em vez do zip de 3,5 MB.
        {preparo?.preparado && ' Baixado e conferido. Falta aplicar e reiniciar.'}
      </span>
      {!preparo?.preparado ? (
        <button className="button" onClick={() => void baixar()} disabled={trabalhando}>
          {trabalhando ? 'Baixando…' : 'Baixar só o que mudou'}
        </button>
      ) : (
        <button className="button button-primary" onClick={() => void aplicar()} disabled={trabalhando}>
          {trabalhando ? 'Aplicando…' : 'Aplicar e reiniciar'}
        </button>
      )}
      <button className="icon-button" onClick={() => setFechado(true)} aria-label="Fechar aviso"><X size={15} /></button>
    </div>
  );
}
