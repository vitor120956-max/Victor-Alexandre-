import { useEffect } from 'react';
import { ArrowUpRight, AudioLines, CheckSquare2, Clock3, Mic, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { useSpeechInput } from '../hooks/useSpeechInput';
import { skills } from '../data/skills';
import { classNames } from '../lib/utils';

export function CommandCenter() {
  const { sendMessage, openTaskModal, startFocus, automations, pushToast, pythonSkills, backendOnline } = useApp();
  const voice = useSpeechInput();
  const navigate = useNavigate();

  useEffect(() => {
    if (voice.error) pushToast('Comando de voz indisponível', voice.error, 'warning');
  }, [pushToast, voice.error]);

  const listeningCopy = voice.transcript || 'Pode falar. Estou ouvindo...';

  return (
    <section className={classNames('command-center', voice.listening && 'is-listening')}>
      <div className="console-grid" aria-hidden="true" />
      <header className="console-header">
        <span><i /> JARVIS / NÚCLEO 01</span>
        <button onClick={() => navigate('/conversa')}>ABRIR CANAL <ArrowUpRight size={13} /></button>
      </header>
      <div className="console-body">
        <div className="console-copy">
          <span className="eyebrow">ASSISTENTE PESSOAL</span>
          <h2>{voice.listening ? 'Estou ouvindo.' : 'Como posso ajudar?'}</h2>
          <p>{voice.listening ? listeningCopy : 'Fale ou escolha uma ação para começar.'}</p>
        </div>
        <button
          className="orb-button"
          onClick={() => voice.toggle((text) => sendMessage(text))}
          aria-label={voice.listening ? 'Parar reconhecimento de voz' : 'Ativar comando de voz'}
        >
          <span className="orb-halo" />
          <span className="orb-ring orb-ring-one"><i /></span>
          <span className="orb-ring orb-ring-two"><i /></span>
          <span className="orb-ring orb-ring-three" />
          <span className="orb-core">{voice.listening ? <AudioLines size={31} /> : <Mic size={29} />}</span>
        </button>
        <div className="console-readout">
          <div><span>SKILLS LOCAIS</span><strong>{String(skills.filter((skill) => skill.active).length + pythonSkills.length).padStart(2, '0')}</strong></div>
          <div><span>AUTOMAÇÕES</span><strong>{String(automations.filter((automation) => automation.enabled).length).padStart(2, '0')}</strong></div>
          <div><span>CONEXÃO</span><strong className="readout-local">{backendOnline ? 'API + LOCAL' : 'LOCAL'}</strong></div>
        </div>
      </div>
      <div className="voice-wave" aria-hidden="true">
        {Array.from({ length: 32 }, (_, index) => <i key={index} style={{ animationDelay: `${index * -0.07}s` }} />)}
      </div>
      <footer className="console-actions">
        <button onClick={() => sendMessage('Resumo do dia')}><Sparkles size={15} /><span>Resumo do dia</span></button>
        <button onClick={openTaskModal}><CheckSquare2 size={15} /><span>Nova tarefa</span></button>
        <button onClick={() => startFocus(25)}><Clock3 size={15} /><span>Iniciar foco</span></button>
      </footer>
    </section>
  );
}
