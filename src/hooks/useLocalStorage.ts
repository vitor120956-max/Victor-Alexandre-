import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

export function useLocalStorage<T>(key: string, initialValue: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored !== null) return JSON.parse(stored) as T;
    } catch {
      // Um valor local corrompido não deve impedir o núcleo de iniciar.
    }
    return typeof initialValue === 'function' ? (initialValue as () => T)() : initialValue;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // O app continua em memória se o armazenamento estiver indisponível.
    }
  }, [key, value]);

  return [value, setValue];
}
