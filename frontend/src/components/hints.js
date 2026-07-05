import { useEffect, useState } from 'react';

/* Stage 3.2: режим «Подсказки». Состояние живёт только в localStorage
   браузера (ключ effecom_hints), backend и база не участвуют.
   Событие нужно, чтобы переключатель в сайдбаре мгновенно влиял
   на значки на открытой странице. */

const KEY = 'effecom_hints';
const EVENT = 'effecom-hints-changed';

export function hintsEnabled() {
  try { return localStorage.getItem(KEY) === 'on'; } catch { return false; }
}

export function setHintsEnabled(on) {
  try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch { /* приватный режим */ }
  window.dispatchEvent(new Event(EVENT));
}

export function useHints() {
  const [enabled, setEnabled] = useState(hintsEnabled);
  useEffect(() => {
    const sync = () => setEnabled(hintsEnabled());
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync); // синхронизация между вкладками
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  return [enabled, setHintsEnabled];
}
