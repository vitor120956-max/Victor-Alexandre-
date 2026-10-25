import { useCallback, useEffect, useState } from 'react';
import { Bot, Brush, Clock3, Compass, RefreshCw, Search, Trash2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import {
  ensinarAgente,
  esquecerAgente,
  painelAgente,
  pesquisarAgente,
  removerFalhaAgente,
  removerSkillLocal,
} from '../lib/api';
import type { AgentePainel } from '../lib/api';
import '../agente.css';

const acoes: Record<string, string> = {
  executado: 'executou',
  criado: 'criou skill',
  guardado: 'respondeu da memória',
  faltando: 'pediu campo',
  sugerir: 'sugeriu',
  web: 'pesquisou na web',
  nada: 'não achou',
};

export function AgentePage() {
  const { backendOnline, hostToken, pushToast } = useApp();
  const [dados, setDados] = useState<AgentePainel | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [alvo, setAlvo] = useState<Record<string, string>>({});
  const [erro, setErro] = useState('');

  const carregar = useCallback(async () => {
    if (!backendOnline) return;
    setCarregando(true);
    try {
      setDados(await painelAgente());
      setErro('');
    } catch (problema) {
      setErro(problema instanceof Error ? problema.message : 'falha desconhecida');
    } finally {
      setCarregando(false);
    }
  }, [backendOnline]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const ensinar = async (pedido: string) => {
    const escolha = (alvo[pedido] ?? '').trim();
    if (!escolha) {
      pushToast('Diga a skill', 'Escreva o id ou o nome da skill que deveria responder.', 'info');
      return;
    }
    try {
      await ensinarAgente(pedido, escolha);
      pushToast('Correlação guardada', `“${pedido}” agora usa ${escolha}.`, 'success');
      await carregar();
    } catch (problema) {
      pushToast('Não ensinou', problema instanceof Error ? problema.message : 'falha desconhecida', 'warning');
    }
  };

  const procurar = async (pedido: string) => {
    if (!hostToken) {
      pushToast('Falta o token de host', 'Envie “token SEU_TOKEN” no chat uma vez e tente de novo.', 'info');
      return;
    }
    try {
      const resultado = await pesquisarAgente(pedido, hostToken);
      pushToast(
        resultado.acao === 'web' ? 'Resposta guardada' : 'A busca não trouxe nada',
        resultado.acao === 'web' ? 'O mesmo pedido agora responde da memória.' : resultado.resposta.slice(0, 120),
        resultado.acao === 'web' ? 'success' : 'warning',
      );
      await carregar();
    } catch (problema) {
      pushToast('Falha na busca', problema instanceof Error ? problema.message : 'falha desconhecida', 'warning');
    }
  };

  const remover = async (acao: () => Promise<void>, mensagem: string) => {
    try {
      await acao();
      pushToast(mensagem, undefined, 'success');
      await carregar();
    } catch (problema) {
      pushToast('Não deu para remover', problema instanceof Error ? problema.message : 'falha desconhecida', 'warning');
    }
  };

  const esquecer = async (pedido: string) => {
    try {
      const removidos = await esquecerAgente(pedido);
      pushToast('Esquecido', `${removidos} registro(s) removidos para “${pedido}”.`, 'success');
      await carregar();
    } catch (problema) {
      pushToast('Não deu para esquecer', problema instanceof Error ? problema.message : 'falha desconhecida', 'warning');
    }
  };

  return (
    <div className="agente-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">SEM MODELO NENHUM</span>
          <h1>Agente<span>.</span></h1>
          <p>O que ele executou, o que criou, o que não soube e o que você ensinou.</p>
        </div>
        <button className="backend-refresh" onClick={() => void carregar()}>
          <RefreshCw size={13} className={carregando ? 'girando' : undefined} />
          {backendOnline ? 'Atualizar' : 'API offline'}
        </button>
      </header>

      {erro && <div className="panel agente-erro">Não consegui ler o painel: {erro}</div>}
      {!backendOnline && (
        <div className="panel agente-erro">
          A API Python está offline. Suba com <code>iniciar.py</code> para o agente local aparecer aqui.
        </div>
      )}

      <section className="panel agente-secao">
        <div className="agente-titulo">
          <Compass size={18} />
          <div>
            <h2>Fila do “não sei fazer”</h2>
            <p>Todo pedido que ele não resolveu fica aqui — nada some. Ensine a skill certa ou peça uma busca na web.</p>
          </div>
          <span className="agente-contagem">{dados?.fila.length ?? 0}</span>
        </div>
        {!dados?.fila.length && <p className="agente-vazio">Nada na fila. Quando ele não souber, o pedido aparece aqui.</p>}
        <ul className="agente-lista">
          {dados?.fila.map((falha) => (
            <li key={falha.id}>
              <div className="agente-item-topo">
                <strong>{falha.pedido}</strong>
                <span className="agente-tentativas">{falha.tentativas}× · {falha.visto_em.slice(0, 10)}</span>
              </div>
              <p className="agente-motivo">{falha.motivo}</p>
              <div className="agente-acoes">
                <input
                  value={alvo[falha.pedido] ?? ''}
                  onChange={(evento) => setAlvo((atual) => ({ ...atual, [falha.pedido]: evento.target.value }))}
                  placeholder="id ou nome da skill que deveria responder"
                  aria-label={`Skill para ${falha.pedido}`}
                />
                <button onClick={() => void ensinar(falha.pedido)}><Brush size={13} /> Ensinar</button>
                <button onClick={() => void procurar(falha.pedido)}><Search size={13} /> Buscar na web</button>
                <button className="agente-remover" onClick={() => void remover(() => removerFalhaAgente(falha.id), 'Removido da fila')}>
                  <Trash2 size={13} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="agente-grade">
        <section className="panel agente-secao">
          <div className="agente-titulo">
            <Bot size={18} />
            <div>
              <h2>Skills locais</h2>
              <p>Criadas por ele a partir das receitas. O mesmo pedido passa a rodar na hora.</p>
            </div>
            <span className="agente-contagem">{dados?.locais.length ?? 0}</span>
          </div>
          {!dados?.locais.length && <p className="agente-vazio">Ainda não criou nenhuma. Peça “contar as palavras de: …”.</p>}
          <ul className="agente-lista">
            {dados?.locais.map((skill) => (
              <li key={skill.id}>
                <div className="agente-item-topo">
                  <strong>{skill.nome}</strong>
                  <code>{skill.id}</code>
                </div>
                <p className="agente-motivo">{skill.descricao}</p>
                <div className="agente-acoes">
                  <span className="agente-tentativas">criada em {skill.criado_em.slice(0, 10)}</span>
                  <button className="agente-remover" onClick={() => void remover(() => removerSkillLocal(skill.id), 'Skill local removida')}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel agente-secao">
          <div className="agente-titulo">
            <Brush size={18} />
            <div>
              <h2>Correlações ensinadas</h2>
              <p>Pedidos que você ligou a uma skill específica.</p>
            </div>
            <span className="agente-contagem">{dados?.apelidos.length ?? 0}</span>
          </div>
          {!dados?.apelidos.length && <p className="agente-vazio">Nenhuma. No chat, diga “não é essa, é a skill …”.</p>}
          <ul className="agente-lista">
            {dados?.apelidos.map((apelido) => (
              <li key={apelido.chave}>
                <div className="agente-item-topo">
                  <strong>{apelido.pedido}</strong>
                  <code>{apelido.skill_id}</code>
                </div>
                <div className="agente-acoes">
                  <span className="agente-tentativas">{apelido.criado_em.slice(0, 10)}</span>
                  <button className="agente-remover" onClick={() => void esquecer(apelido.pedido)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="panel agente-secao">
        <div className="agente-titulo">
          <Clock3 size={18} />
          <div>
            <h2>Histórico</h2>
            <p>As últimas execuções, com a ação e a confiança da escolha.</p>
          </div>
          <span className="agente-contagem">{dados?.historico.length ?? 0}</span>
        </div>
        {!dados?.historico.length && <p className="agente-vazio">Nada executado ainda.</p>}
        <ul className="agente-historico">
          {dados?.historico.map((linha, indice) => (
            <li key={`${linha.quando}-${indice}`}>
              <span className={`agente-etiqueta acao-${linha.acao}`}>{acoes[linha.acao] ?? linha.acao}</span>
              <strong>{linha.pedido}</strong>
              {linha.skill && <code>{linha.skill}</code>}
              <span className="agente-tentativas">{linha.quando.slice(11, 16)} · {Math.round(linha.confianca * 100)}%</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel agente-secao">
        <div className="agente-titulo">
          <Bot size={18} />
          <div>
            <h2>Receitas disponíveis</h2>
            <p>O catálogo fechado de onde saem as skills criadas. Nada aqui escreve código novo.</p>
          </div>
          <span className="agente-contagem">{dados?.receitas.length ?? 0}</span>
        </div>
        <div className="agente-receitas">
          {dados?.receitas.map((receita) => (
            <article key={receita.id}>
              <strong>{receita.nome}</strong>
              <p>{receita.descricao}</p>
              <code>{receita.exemplo}</code>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
