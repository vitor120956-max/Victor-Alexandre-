import { useCallback, useEffect, useRef, useState } from 'react';

interface RecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}

interface RecognitionEventLike {
  results: {
    length: number;
    [index: number]: RecognitionResultLike;
  };
}

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type RecognitionConstructor = new () => RecognitionLike;

function recognitionConstructor(): RecognitionConstructor | undefined {
  if (typeof window === 'undefined') return undefined;
  const target = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return target.SpeechRecognition ?? target.webkitSpeechRecognition;
}

export function useSpeechInput() {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const finalTextRef = useRef('');
  const onFinalRef = useRef<((text: string) => void) | undefined>(undefined);
  const supported = typeof window !== 'undefined' && Boolean(recognitionConstructor());

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const toggle = useCallback((onFinal?: (text: string) => void) => {
    if (listening) {
      stop();
      return;
    }
    const Constructor = recognitionConstructor();
    if (!Constructor) {
      setError('Reconhecimento de voz não é suportado neste navegador.');
      return;
    }

    const recognition = new Constructor();
    recognition.lang = 'pt-BR';
    recognition.continuous = false;
    recognition.interimResults = true;
    finalTextRef.current = '';
    onFinalRef.current = onFinal;
    setTranscript('');
    setError('');

    recognition.onresult = (event) => {
      let text = '';
      let finalText = '';
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        text += result[0].transcript;
        if (result.isFinal) finalText += result[0].transcript;
      }
      setTranscript(text.trim());
      if (finalText.trim()) finalTextRef.current = finalText.trim();
    };
    recognition.onerror = (event) => {
      const messages: Record<string, string> = {
        'not-allowed': 'Permita o uso do microfone para falar com o JARVIS.',
        'no-speech': 'Não consegui ouvir. Tente falar um pouco mais perto do microfone.',
        'audio-capture': 'Nenhum microfone disponível foi encontrado.',
      };
      setError(messages[event.error] ?? 'O reconhecimento de voz foi interrompido. Tente novamente.');
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      const finalText = finalTextRef.current.trim();
      if (finalText) onFinalRef.current?.(finalText);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      setError('Não foi possível iniciar o microfone agora.');
      setListening(false);
    }
  }, [listening, stop]);

  useEffect(() => () => {
    if (!recognitionRef.current) return;
    recognitionRef.current.onend = null;
    recognitionRef.current.onresult = null;
    recognitionRef.current.onerror = null;
    recognitionRef.current.abort();
  }, []);

  return { supported, listening, transcript, error, toggle, stop };
}
