import { ArrowRight, Calculator, CheckSquare2, Clock3, Code2, FileText, Gauge, Globe2, Mic2, Shuffle, Sparkles } from 'lucide-react';
import { ChatPanel } from '../components/ChatPanel';
import { useApp } from '../context/AppContext';

const examples = [
  { icon: CheckSquare2, label: 'Organizar uma tarefa', command: 'Criar tarefa revisar o próximo módulo com prioridade alta' },
  { icon: Calculator, label: 'Resolver um cálculo', command: 'Calcular (1250 * 0,18) + 40' },
  { icon: Clock3, label: 'Entrar em foco', command: 'Iniciar foco de 25 minutos' },
  { icon: Globe2, label: 'Pesquisar na web', command: 'Pesquisar por arquitetura de assistentes pessoais' },
  { icon: Code2, label: 'Executar Python', command: 'Analisar texto O JARVIS conecta inteligência e ações com segurança.' },
  { icon: FileText, label: 'Listar documentos', command: 'Listar documentos' },
  { icon: Shuffle, label: 'Fazer um sorteio', command: 'Sortear 2 entre Ana, Bruno, Carla' },
  { icon: Gauge, label: 'Avaliar Web Vitals', command: 'Avaliar web vitals LCP 2600 INP 180 CLS 0,05' },
];

export function ChatPage() {
  const { sendMessage, aiStatus, backendOnline, preferences } = useApp();
  return (
    <div className="chat-page">
      <header className="page-heading">
        <div><span className="eyebrow">CANAL DIRETO</span><h1>Conversa com o JARVIS<span>.</span></h1><p>Texto, voz e comandos locais no mesmo fluxo.</p></div>
        <span className="local-badge"><i /> {backendOnline && aiStatus.configured && preferences.aiEnabled ? 'IA EXTERNA + SKILLS' : 'SKILLS LOCAIS + PYTHON'}</span>
      </header>
      <div className="chat-page-layout">
        <ChatPanel full />
        <aside className="chat-aside">
          <section className="panel examples-panel">
            <span className="eyebrow">PONTO DE PARTIDA</span>
            <h2>O que posso fazer por você?</h2>
            <p>Experimente um comando real. O resultado aparece na conversa e no módulo correspondente.</p>
            <div className="example-list">
              {examples.map(({ icon: Icon, label, command }) => (
                <button key={label} onClick={() => sendMessage(command)}>
                  <span><Icon size={17} /></span>
                  <div><strong>{label}</strong><small>“{command}”</small></div>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          </section>
          <section className="voice-note">
            <span><Mic2 size={19} /></span>
            <div><strong>Prefere falar?</strong><p>Use o microfone no campo de mensagem. O suporte depende do navegador.</p></div>
          </section>
          <button className="help-command" onClick={() => sendMessage('ajuda')}><Sparkles size={16} /> Ver todos os comandos locais <ArrowRight size={15} /></button>
        </aside>
      </div>
    </div>
  );
}
