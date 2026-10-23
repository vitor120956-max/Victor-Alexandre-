import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Expand, Mic, Sparkles, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { useSpeechInput } from '../hooks/useSpeechInput';
import { classNames } from '../lib/utils';

export function ChatPanel({ full = false }: { full?: boolean }) {
  const { messages, sendMessage, clearMessages, pushToast, processing, backendOnline, aiStatus, preferences } = useApp();
  const [input, setInput] = useState('');
  const messageEndRef = useRef<HTMLDivElement>(null);
  const voice = useSpeechInput();
  const navigate = useNavigate();

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, processing]);

  useEffect(() => {
    if (voice.transcript) setInput(voice.transcript);
  }, [voice.transcript]);

  useEffect(() => {
    if (voice.error) pushToast('Não foi possível usar o microfone', voice.error, 'warning');
  }, [pushToast, voice.error]);

  const submit = () => {
    const value = input.trim();
    if (!value || processing) return;
    sendMessage(value);
    setInput('');
  };

  const startVoice = () => {
    voice.toggle((text) => {
      setInput('');
      sendMessage(text);
    });
  };

  return (
    <section className={classNames('chat-panel', full && 'chat-panel-full')}>
      <header className="chat-header">
        <div className="chat-identity">
          <span className="assistant-avatar"><Sparkles size={17} /></span>
          <div><strong>Conversa</strong><span><i /> {!backendOnline ? 'Modo navegador' : aiStatus.configured && preferences.aiEnabled ? `${aiStatus.provider} + skills` : 'Skills locais + Python'}</span></div>
        </div>
        {full ? (
          <button className="icon-button" onClick={clearMessages} disabled={Boolean(processing)} aria-label="Limpar conversa" title="Limpar conversa"><Trash2 size={17} /></button>
        ) : (
          <button className="icon-button" onClick={() => navigate('/conversa')} aria-label="Expandir conversa"><Expand size={16} /></button>
        )}
      </header>

      <div className="chat-messages" aria-live="polite">
        {messages.map((message) => (
          <div className={`message message-${message.role}`} key={message.id}>
            {message.role === 'jarvis' && <span className="message-avatar"><Sparkles size={13} /></span>}
            <div className="message-wrap">
              <div className="message-bubble">{message.content}</div>
              <time>{new Date(message.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}{message.source === 'ai' ? ' · IA EXTERNA' : message.source === 'python' ? ' · SKILL PYTHON' : ''}</time>
            </div>
          </div>
        ))}
        {processing && (
          <div className="message message-jarvis processing-message">
            <span className="message-avatar"><Sparkles size={13} /></span>
            <div className="typing-bubble"><i /><i /><i /><span>{processing === 'ai' ? 'Consultando a IA externa...' : 'Executando skill Python...'}</span></div>
          </div>
        )}
        <div ref={messageEndRef} />
      </div>

      <div className="chat-bottom">
        <div className="suggestion-row">
          <button onClick={() => sendMessage('Resumo do dia')}>Resumo do dia</button>
          <button onClick={() => sendMessage('O que você pode fazer?')}>Explorar comandos</button>
        </div>
        <div className={classNames('chat-composer', voice.listening && 'is-listening')}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder={voice.listening ? 'Ouvindo...' : 'Digite um comando ou pergunta...'}
            rows={1}
            maxLength={1000}
            aria-label="Mensagem para o JARVIS"
          />
          <button className={classNames('mic-button', voice.listening && 'active')} onClick={startVoice} aria-label={voice.listening ? 'Parar de ouvir' : 'Falar com o JARVIS'} title="Comando por voz">
            <Mic size={17} />
          </button>
          <button className="send-button" onClick={submit} disabled={!input.trim() || Boolean(processing)} aria-label="Enviar mensagem"><ArrowUp size={18} /></button>
        </div>
        <div className="composer-hint"><span>Enter para enviar</span><span>•</span><span>Shift + Enter para nova linha</span></div>
      </div>
    </section>
  );
}
