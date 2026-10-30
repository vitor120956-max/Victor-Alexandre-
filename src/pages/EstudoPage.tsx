import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BookOpenCheck,
  Brain,
  CalendarClock,
  Check,
  Flame,
  Layers,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-react';
import type { SkillExecution } from '../lib/api';
import { useApp } from '../context/AppContext';
import '../estudo.css';

type Cartao = {
  id: string;
  baralho: string;
  frente: string;
  verso: string;
  tipo?: string;
  vencido_ha?: number;
  erros?: number;
  reps?: number;
};

type Baralho = {
  baralho: string;
  nome: string;
  cartoes: number;
  vencidos: number;
  novos?: number;
  retencao?: number;
};

type Boletim = {
  cartoes?: number;
  vencidos?: number;
  novos?: number;
  respostas?: number;
  acertos?: number;
  erros?: number;
  retencao?: number;
  sequencia_dias?: number;
  dias_estudados?: number;
  baralhos?: Baralho[];
  fracos?: { id: string; baralho: string; frente: string; erros: number }[];
  resumo?: string;
  aviso?: string;
};

const NOTAS = [
  { nota: 'errei', rotulo: 'Errei', hint: 'volta amanhã', tone: 'errei' },
  { nota: 'dificil', rotulo: 'Difícil', hint: 'volta em dias', tone: 'dificil' },
  { nota: 'bom', rotulo: 'Bom', hint: 'segue o intervalo', tone: 'bom' },
  { nota: 'facil', rotulo: 'Fácil', hint: 'some por semanas', tone: 'facil' },
] as const;

const num = (valor: unknown, padrao = 0) => (typeof valor === 'number' && Number.isFinite(valor) ? valor : padrao);

function lista<T>(valor: unknown): T[] {
  return Array.isArray(valor) ? (valor as T[]) : [];
}

export function EstudoPage() {
  const { backendOnline, executeSkill, pushToast } = useApp();
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [execucao, setExecucao] = useState<SkillExecution | null>(null);
  const [boletim, setBoletim] = useState<Boletim | null>(null);
  const [baralhos, setBaralhos] = useState<Baralho[]>([]);
  const [fila, setFila] = useState<Cartao[]>([]);
  const [indice, setIndice] = useState(0);
  const [revelado, setRevelado] = useState(false);
  const [respondidos, setRespondidos] = useState(0);
  const [ultimo, setUltimo] = useState<{ rotulo: string; volta: string } | null>(null);

  const [material, setMaterial] = useState('');
  const [baralho, setBaralho] = useState('');

  const cartaoAtual = fila[indice] ?? null;
  const restantes = Math.max(fila.length - respondidos, 0);
  const total = fila.length;

  const recarregar = useCallback(async () => {
    if (!backendOnline) return;
    const [progresso, listaBaralhos, revisao] = await Promise.all([
      executeSkill('estudo.progresso', {}),
      executeSkill('estudo.baralhos', {}),
      executeSkill('estudo.revisar', {}),
    ]);
    if (progresso.ok && progresso.result) setBoletim(progresso.result as Boletim);
    if (listaBaralhos.ok && listaBaralhos.result) {
      setBaralhos(listaBiblioteca(listaBaralhos.result));
    }
    if (revisao.ok && revisao.result) {
      const dados = revisao.result as { cartoes?: Cartao[] };
      setFila(lista<Cartao>(dados.cartoes));
      setIndice(0);
      setRevelado(false);
      setRespondidos(0);
    }
  }, [backendOnline, executeSkill]);

  useEffect(() => {
    void recarregar().catch(() => setErro('Não consegui falar com a API. Suba com .venv\\Scripts\\python iniciar.py.'));
  }, [recarregar]);

  const responder = async (nota: string) => {
    if (!cartaoAtual) return;
    setBusy(true);
    setErro('');
    try {
      const resposta = await executeSkill('estudo.responder', { cartao: cartaoAtual.id, nota, baralho: cartaoAtual.baralho });
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou a resposta.');
        return;
      }
      const resultado = (resposta.result ?? {}) as { rotulo?: string; volta_em?: string; intervalo_dias?: number };
      setUltimo({
        rotulo: resultado.rotulo ?? nota,
        volta: resultado.intervalo_dias === 1 ? 'amanhã' : `em ${resultado.intervalo_dias ?? '?'} dias`,
      });
      setRespondidos((n) => n + 1);
      setRevelado(false);
      setIndice((i) => i + 1);
      if (resultado.volta_em) pushToast('Resposta registrada', `O cartão volta ${resultado.intervalo_dias === 1 ? 'amanhã' : `em ${resultado.intervalo_dias} dias`}.`, 'success');
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao registrar a resposta.');
    } finally {
      setBusy(false);
    }
  };

  const adicionar = async () => {
    if (!material.trim()) {
      setErro('Cole um resumo ou escreva um cartão: frente e verso separados por linha.');
      return;
    }
    if (!baralho.trim()) {
      setErro('Diga o nome do baralho: “civil”, “inglês”, “anatomia”.');
      return;
    }
    setBusy(true);
    setErro('');
    try {
      const resposta = await executeSkill('estudo.adicionar', { baralho: baralho.trim(), texto: material }, { confirmed: true });
      if (!resposta.ok) {
        setErro(resposta.error?.message ?? 'A skill recusou o material.');
        return;
      }
      setExecucao(resposta);
      const r = (resposta.result ?? {}) as { adicionados?: number; pulados?: number; ignoradas?: number };
      pushToast(`${num(r.adicionados)} cartão(ões)`, `Baralho ${baralho} · ${num(r.pulados)} repetidos · ${num(r.ignoradas)} linhas ignoradas`, 'success');
      setMaterial('');
      await recarregar();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao adicionar o material.');
    } finally {
      setBusy(false);
    }
  };

  const resumo = useMemo(() => {
    if (!boletim) return '';
    return boletim.resumo || '';
  }, [boletim]);

  const desde = ultimo ? `${ultimo.rotulo} · volta ${ultimo.volta}` : '';

  return (
    <div className="estudo-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">APRENDIZADO</span>
          <h1>Estudo<span>.</span></h1>
          <p>Repetição espaçada: o cartão volta antes de ser esquecido.</p>
        </div>
        <button className="button" onClick={() => void recarregar()} disabled={busy || !backendOnline}>
          <RefreshCw size={16} /> Atualizar
        </button>
      </header>

      {!backendOnline && (
        <div className="estudo-alerta">
          <TriangleAlert size={16} /> A API está offline. Nada aparece porque nada foi lido — suba com <code>.venv\Scripts\python iniciar.py</code>.
        </div>
      )}
      {erro && (
        <div className="estudo-alerta estudo-alerta-erro">
          <TriangleAlert size={16} /> {erro}
          <button className="estudo-link" onClick={() => setErro('')}>fechar</button>
        </div>
      )}

      <div className="metric-grid estudo-metricas">
        <div className="metric-card"><span className="metric-icon"><CalendarClock size={18} /></span><div><strong>{num(boletim?.vencidos)}</strong><span>Vencidos hoje</span></div><small>{num(boletim?.cartoes)} cartões</small></div>
        <div className="metric-card"><span className="metric-icon"><Brain size={18} /></span><div><strong>{num(boletim?.retencao)}%</strong><span>Retenção</span></div><small>{num(boletim?.respostas)} respostas</small></div>
        <div className="metric-card"><span className="metric-icon"><Flame size={18} /></span><div><strong>{num(boletim?.sequencia_dias)}</strong><span>Dias seguidos</span></div><small>{num(boletim?.dias_estudados)} dias estudados</small></div>
        <div className="metric-card"><span className="metric-icon"><Layers size={18} /></span><div><strong>{baralhos.length}</strong><span>Baralhos</span></div><small>{num(boletim?.novos)} cartões novos</small></div>
      </div>

      <div className="estudo-grade">
        <section className="panel estudo-sessao">
          <header className="estudo-cabecalho">
            <div>
              <h2>Sessão de hoje</h2>
              <p>{total ? `${respondidos} de ${total} nesta rodada · ${restantes} na fila` : 'Nada vencido agora.'}</p>
            </div>
            {desde && <span className="estudo-selo"><Check size={14} /> {desde}</span>}
          </header>

          {cartaoAtual ? (
            <div className="estudo-cartao">
              <span className="estudo-tag">{cartaoAtual.baralho}</span>
              <p className="estudo-pergunta">{cartaoAtual.frente}</p>
              {revelado ? (
                <div className="estudo-resposta">
                  <span>Resposta</span>
                  <p>{cartaoAtual.verso}</p>
                </div>
              ) : (
                <button className="button button-primary" onClick={() => setRevelado(true)}>
                  Mostrar resposta <ArrowRight size={16} />
                </button>
              )}
              {revelado && (
                <div className="estudo-notas">
                  {NOTAS.map(({ nota, rotulo, hint, tone }) => (
                    <button
                      key={nota}
                      className={`estudo-nota estudo-nota-${tone}`}
                      onClick={() => void responder(nota)}
                      disabled={busy}
                    >
                      <strong>{rotulo}</strong>
                      <small>{hint}</small>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="estudo-vazio">
              <BookOpenCheck size={28} />
              <p>{total ? 'Rodada concluída. Os cartões voltam nas datas certas.' : 'Nenhum cartão vencido. Cole material novo ao lado para começar.'}</p>
              {resumo && <small>{resumo}</small>}
            </div>
          )}
        </section>

        <section className="panel estudo-material">
          <header className="estudo-cabecalho">
            <div>
              <h2>Material novo</h2>
              <p>Vira cartão por padrão de frase — sem modelo.</p>
            </div>
            <Sparkles size={18} />
          </header>
          <label className="estudo-campo">
            <span>Baralho</span>
            <input
              value={baralho}
              onChange={(evento) => setBaralho(evento.target.value)}
              placeholder="civil, inglês, anatomia…"
              maxLength={120}
            />
          </label>
          <label className="estudo-campo">
            <span>Material ou cartão à mão</span>
            <textarea
              value={material}
              onChange={(evento) => setMaterial(evento.target.value)}
              rows={8}
              placeholder={'Direito civil é o ramo que regula as relações entre particulares.\n\n**Posse**: é o exercício de fato de um dos poderes da propriedade.'}
            />
          </label>
          <button className="button button-primary" onClick={() => void adicionar()} disabled={busy || !backendOnline}>
            {busy ? 'Lendo…' : 'Virar em cartões'}
          </button>
          {execucao?.result && (
            <p className="estudo-nota-tecnica">
              {num((execucao.result as { adicionados?: number }).adicionados)} adicionados ·{' '}
              {num((execucao.result as { pulados?: number }).pulados)} repetidos ·{' '}
              {num((execucao.result as { ignoradas?: number }).ignoradas)} linhas ignoradas
            </p>
          )}
        </section>
      </div>

      <section className="panel estudo-baralhos">
        <header className="estudo-cabecalho">
          <div><h2>Seus baralhos</h2><p>O que está vencido, por baralho.</p></div>
        </header>
        {baralhos.length ? (
          <div className="estudo-lista">
            {baralhos.map((item) => (
              <article key={item.baralho} className="estudo-linha">
                <div>
                  <strong>{item.nome}</strong>
                  <small>{item.cartoes} cartões · {item.novos ?? 0} novos</small>
                </div>
                <div className="estudo-linha-fim">
                  <span className={item.vencidos ? 'estudo-pill estudo-pill-alerta' : 'estudo-pill'}>
                    {item.vencidos ? `${item.vencidos} vencidos` : 'em dia'}
                  </span>
                  <button className="estudo-link" onClick={() => setBaralho(item.nome)}>usar</button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="estudo-vazio-texto">Nenhum baralho ainda. O primeiro nasce quando você cola material.</p>
        )}
        {!!boletim?.fracos?.length && (
          <div className="estudo-fracos">
            <h3><X size={15} /> O que mais erra</h3>
            <ul>
              {boletim.fracos.slice(0, 5).map((item) => (
                <li key={item.id}><span>{item.frente}</span><small>{item.erros}× · {item.baralho}</small></li>
              ))}
            </ul>
            <p>Cartão que erra sempre quase nunca é memória ruim: é material ruim. Reescreva a pergunta.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function listaBiblioteca(resultado: unknown): Baralho[] {
  const dados = resultado as { baralhos?: Baralho[] };
  return lista<Baralho>(dados.baralhos);
}
