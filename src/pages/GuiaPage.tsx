import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Compass,
  HeartHandshake,
  LoaderCircle,
  MessageCircle,
  MessagesSquare,
  Phone,
  ScanEye,
  Send,
  ShieldAlert,
  Sparkles,
  SpellCheck2,
} from 'lucide-react';
import { ApiError, getCatalogoGuia, guiaConversa, type GuiaCatalogo } from '../lib/api';
import '../guia.css';

type Aba = 'abrir' | 'manter' | 'convidar' | 'sinais' | 'revisar' | 'filosofia' | 'psicologia' | 'limites';

const abas: Array<{ id: Aba; label: string; hint: string; icon: typeof Compass }> = [
  { id: 'abrir', label: 'Começar', hint: 'A primeira frase', icon: MessageCircle },
  { id: 'manter', label: 'Manter', hint: 'A conversa não morre', icon: MessagesSquare },
  { id: 'convidar', label: 'Convidar', hint: 'Chamar para sair', icon: Send },
  { id: 'sinais', label: 'Sinais', hint: 'Interesse e desconforto', icon: ScanEye },
  { id: 'revisar', label: 'Revisar', hint: 'Antes de mandar', icon: SpellCheck2 },
  { id: 'filosofia', label: 'Filosofia', hint: 'Oito escolas', icon: Sparkles },
  { id: 'psicologia', label: 'Psicologia', hint: 'Com base, sem achismo', icon: HeartHandshake },
  { id: 'limites', label: 'Limites', hint: 'O que ele não escreve', icon: ShieldAlert },
];

const rotulos: Record<string, string> = {
  contexto: 'Contexto',
  aberturas: 'Aberturas',
  evite: 'Evite',
  principio: 'Princípio',
  principios: 'Princípios',
  exemplo_ruim: 'Exemplo ruim',
  exemplo_bom: 'Exemplo bom',
  estrutura: 'Estrutura',
  exemplos: 'Exemplos',
  plano: 'Plano',
  sinais_de_interesse: 'Sinais de interesse',
  sinais_de_desconforto: 'Sinais de desconforto',
  consentimento: 'Consentimento',
  o_que_fazer: 'O que fazer',
  caracteres: 'Caracteres',
  perguntas: 'Perguntas',
  problemas: 'Problemas',
  sugestoes: 'Sugestões',
  lembrete: 'Lembrete',
  aviso: 'Aviso',
  pergunta: 'Pergunta',
  escola: 'Escola',
  escolas: 'Escolas',
  ideia: 'Ideia central',
  pratica: 'Prática',
  limite: 'Limite',
  conceito: 'Conceito',
  conceitos: 'Conceitos',
  o_que_e: 'O que é',
  base: 'O que a pesquisa sustenta',
  cuidado: 'Cuidado',
  recusados: 'Recusados',
  porque: 'Por quê',
  no_lugar: 'No lugar disso',
  nao_e_terapia: 'Não é terapia',
  ajuda: 'Ajuda imediata',
  como_usar: 'Como usar',
  mensagem: 'Mensagem',
  tecnica: 'Técnica',
};

function humanizar(chave: string): string {
  return rotulos[chave] ?? chave.replace(/_/g, ' ').replace(/^./, (letra) => letra.toUpperCase());
}

/** O conteúdo vem em markdown mínimo (`**forte**`). Nada de HTML cru na tela. */
function Texto({ valor }: { valor: string }) {
  const partes = valor.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return (
    <>
      {partes.map((parte, indice) =>
        parte.startsWith('**') && parte.endsWith('**') && parte.length > 4
          ? <strong key={indice}>{parte.slice(2, -2)}</strong>
          : <span key={indice}>{parte}</span>,
      )}
    </>
  );
}

function Valor({ nome, valor }: { nome?: string; valor: unknown }) {
  if (valor === null || valor === undefined || valor === '') return null;
  if (typeof valor === 'string' || typeof valor === 'number') {
    return (
      <div className="guia-campo">
        {nome && <span className="guia-rotulo">{humanizar(nome)}</span>}
        <p><Texto valor={String(valor)} /></p>
      </div>
    );
  }
  if (typeof valor === 'boolean') return null;
  if (Array.isArray(valor)) {
    const textos = valor.filter((item) => typeof item === 'string') as string[];
    if (textos.length === valor.length) {
      return (
        <div className="guia-campo">
          {nome && <span className="guia-rotulo">{humanizar(nome)}</span>}
          <ul className="guia-lista">
            {textos.map((item, indice) => <li key={indice}><Texto valor={item} /></li>)}
          </ul>
        </div>
      );
    }
    const objetos = valor.filter((item) => typeof item === 'object' && item !== null) as Record<string, unknown>[];
    return (
      <div className="guia-campo">
        {nome && <span className="guia-rotulo">{humanizar(nome)}</span>}
        <div className="guia-cartoes">
          {objetos.map((item, indice) => (
            <article className="guia-cartao" key={indice}>
              {Object.entries(item).map(([chave, conteudo]) => (
                <Valor key={chave} nome={chave} valor={conteudo} />
              ))}
            </article>
          ))}
        </div>
      </div>
    );
  }
  if (typeof valor === 'object') {
    const objeto = valor as Record<string, unknown>;
    return (
      <section className="guia-secao">
        {nome && <h4>{humanizar(nome)}</h4>}
        {Object.entries(objeto).map(([chave, conteudo]) => (
          <Valor key={chave} nome={chave} valor={conteudo} />
        ))}
      </section>
    );
  }
  return null;
}

export function GuiaPage() {
  const [aba, setAba] = useState<Aba>('abrir');
  const [catalogo, setCatalogo] = useState<GuiaCatalogo | null>(null);
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(null);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(false);

  const [contexto, setContexto] = useState('app');
  const [interesse, setInteresse] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [objetivo, setObjetivo] = useState('conhecer');
  const [plano, setPlano] = useState('');
  const [tempo, setTempo] = useState('');
  const [pergunta, setPergunta] = useState('');
  const [escola, setEscola] = useState('');
  const [conceito, setConceito] = useState('');
  const [revisao, setRevisao] = useState('');

  useEffect(() => {
    let vivo = true;
    getCatalogoGuia()
      .then((dados) => { if (vivo) setCatalogo(dados); })
      .catch((falha: unknown) => {
        if (vivo) setErro(falha instanceof ApiError ? falha.message : 'Não foi possível carregar o catálogo.');
      });
    return () => { vivo = false; };
  }, []);

  const ativa = useMemo(() => abas.find((item) => item.id === aba) ?? abas[0], [aba]);

  async function rodar(rota: Parameters<typeof guiaConversa>[0], corpo: Record<string, unknown>) {
    setErro('');
    setCarregando(true);
    setResultado(null);
    try {
      setResultado(await guiaConversa(rota, corpo));
    } catch (falha) {
      setErro(falha instanceof ApiError ? falha.message : 'A API não respondeu. O servidor está ligado?');
    } finally {
      setCarregando(false);
    }
  }

  return (
    <main className="guia-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">CONVERSA · FILOSOFIA · PSICOLOGIA</span>
          <h1>Como conversar, <span>sem truque</span></h1>
          <p>
            Aberturas, ritmo, convite e leitura de sinais — mais oito escolas de filosofia e sete
            conceitos de psicologia com o que a pesquisa sustenta. O objetivo é ser claro sobre o
            que você quer; ninguém aqui ensina a fazer alguém se apaixonar.
          </p>
        </div>
      </header>

      <section className="panel guia-aviso" role="note">
        <AlertTriangle size={16} />
        <div>
          <strong>Não é terapia.</strong>
          <p>
            Isto é conversa e educação. Se a dor for grande, o caminho é um profissional — e em crise
            o CVV atende no <a href="tel:188">188</a>, de graça, 24 h. Violência: 180 (mulher) e 190.
          </p>
        </div>
      </section>

      <nav className="guia-tabs" aria-label="Seções do guia">
        {abas.map(({ id, label, hint, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={aba === id ? 'is-active' : undefined}
            aria-pressed={aba === id}
            onClick={() => { setAba(id); setErro(''); setResultado(null); }}
          >
            <Icon size={16} />
            <span>{label}<small>{hint}</small></span>
          </button>
        ))}
      </nav>

      <div className="guia-grid">
        <section className="panel guia-form">
          <header className="guia-form-head">
            <div>
              <span className="eyebrow">{ativa.label.toUpperCase()}</span>
              <h2>{ativa.hint}</h2>
            </div>
          </header>

          {aba === 'abrir' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('abrir', { contexto, interesse }); }}>
              <label className="field">
                <span>Onde vocês se viram *</span>
                <select value={contexto} onChange={(e) => setContexto(e.target.value)}>
                  {(catalogo?.contextos ?? [
                    { id: 'app', nome: 'aplicativo', aberturas: [] },
                    { id: 'festa', nome: 'festa', aberturas: [] },
                    { id: 'academia', nome: 'academia', aberturas: [] },
                    { id: 'trabalho', nome: 'trabalho', aberturas: [] },
                    { id: 'rua', nome: 'rua', aberturas: [] },
                    { id: 'curso', nome: 'curso', aberturas: [] },
                  ]).map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
                </select>
              </label>
              <label className="field">
                <span>O que vocês têm em comum</span>
                <input value={interesse} onChange={(e) => setInteresse(e.target.value)} maxLength={300}
                  placeholder="Ex.: o mesmo professor, o mesmo jogo, a mesma cidade" />
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <Compass size={15} />} Ver aberturas
              </button>
            </form>
          )}

          {aba === 'manter' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('manter', { mensagem, objetivo }); }}>
              <label className="field">
                <span>Onde a conversa está</span>
                <textarea value={mensagem} onChange={(e) => setMensagem(e.target.value)} rows={4} maxLength={4000}
                  placeholder="Cole a conversa ou escreva o que ela disse por último." />
              </label>
              <label className="field">
                <span>Objetivo *</span>
                <select value={objetivo} onChange={(e) => setObjetivo(e.target.value)}>
                  <option value="conhecer">conhecer melhor</option>
                  <option value="marcar">marcar de sair</option>
                  <option value="reativar">reativar depois de um tempo</option>
                </select>
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <MessagesSquare size={15} />} Ver o que fazer
              </button>
            </form>
          )}

          {aba === 'convidar' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('convidar', { plano, tempoConhecendo: tempo }); }}>
              <label className="field">
                <span>O programa que você pensou</span>
                <input value={plano} onChange={(e) => setPlano(e.target.value)} maxLength={300}
                  placeholder="Ex.: feira de vinil no sábado de manhã" />
              </label>
              <label className="field">
                <span>Há quanto tempo conversam</span>
                <input value={tempo} onChange={(e) => setTempo(e.target.value)} maxLength={60}
                  placeholder="Ex.: duas semanas, falando todo dia" />
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <Send size={15} />} Montar o convite
              </button>
            </form>
          )}

          {aba === 'sinais' && (
            <div className="guia-form-simples">
              <p className="guia-nota">
                Sinal é ambíguo; palavra não é. Se você precisa de um detector de sentimento, o
                caminho é perguntar — com abertura para ouvir “não”.
              </p>
              <button className="button" type="button" onClick={() => void rodar('ler', {})}>
                Ver o que observar
              </button>
            </div>
          )}

          {aba === 'revisar' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('revisar', { mensagem: revisao }); }}>
              <label className="field">
                <span>A mensagem que você ia mandar *</span>
                <textarea value={revisao} onChange={(e) => setRevisao(e.target.value)} rows={5} maxLength={4000} required
                  placeholder="Escreva exatamente como você mandaria." />
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <SpellCheck2 size={15} />} Revisar
              </button>
            </form>
          )}

          {aba === 'filosofia' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('filosofia', { pergunta, escola }); }}>
              <label className="field">
                <span>A sua pergunta</span>
                <textarea value={pergunta} onChange={(e) => setPergunta(e.target.value)} rows={3} maxLength={600}
                  placeholder="Ex.: vale a pena tentar de novo depois de um não?" />
              </label>
              <label className="field">
                <span>Escola (vazio = todas)</span>
                <select value={escola} onChange={(e) => setEscola(e.target.value)}>
                  <option value="">todas as oito</option>
                  {(catalogo?.escolas ?? []).map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
                </select>
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />} Ver as lentes
              </button>
            </form>
          )}

          {aba === 'psicologia' && (
            <form className="form-stack" onSubmit={(evento) => { evento.preventDefault(); void rodar('psicologia', { conceito }); }}>
              <label className="field">
                <span>Conceito (vazio = todos)</span>
                <select value={conceito} onChange={(e) => setConceito(e.target.value)}>
                  <option value="">todos os sete</option>
                  {(catalogo?.conceitos ?? []).map((item) => (
                    <option key={item.id} value={item.id}>{item.id.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </label>
              <button className="button" type="submit" disabled={carregando}>
                {carregando ? <LoaderCircle size={15} className="spin" /> : <HeartHandshake size={15} />} Explicar com base
              </button>
            </form>
          )}

          {aba === 'limites' && (
            <div className="guia-form-simples">
              <p className="guia-nota">
                O JARVIS não escreve neg, não insiste depois do “não”, não usa chantagem, não inventa
                personagem, não ensina a confundir e não ajuda a vigiar ninguém. A lista abaixo vem do
                próprio servidor — não é texto de marketing.
              </p>
              <ul className="guia-lista">
                {(catalogo?.recusados ?? []).map((item) => <li key={item}>{item}</li>)}
              </ul>
              <p className="guia-nota">{catalogo?.no_lugar}</p>
            </div>
          )}
        </section>

        <section className="panel guia-resultado" aria-live="polite">
          {erro && <div className="guia-erro" role="alert"><AlertTriangle size={15} /> {erro}</div>}
          {!erro && !resultado && (
            <div className="guia-vazio">
              <Phone size={18} />
              <p>
                Escolha uma seção e um formulário. O que voltar é texto — o JARVIS não manda mensagem
                por você, e não sabe o que a outra pessoa pensa.
              </p>
            </div>
          )}
          {resultado && Object.entries(resultado).map(([chave, valor]) => (
            <Valor key={chave} nome={chave} valor={valor} />
          ))}
          {catalogo && (aba === 'limites' || aba === 'sinais') && (
            <p className="guia-ajuda">{catalogo.ajuda}</p>
          )}
        </section>
      </div>
    </main>
  );
}
