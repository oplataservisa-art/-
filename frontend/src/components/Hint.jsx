import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { HINTS } from '../content/help';
import { useHints } from './hints';

/* Stage 3.2: значок «?» с короткой подсказкой (что это / зачем / когда).
   Рендерится только при включённом режиме «Подсказки» — с выключенным
   интерфейс не отличается от прежнего. Тексты — в content/help.js. */

export default function Hint({ id }) {
  const [enabled] = useHints();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const hint = HINTS[id];
  if (!enabled || !hint) return null;

  return (
    <span className="hint-wrap" ref={ref}>
      <button type="button" className="hint-btn" title="Подсказка"
        aria-label={`Подсказка: ${hint.title}`}
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>?</button>
      {open && (
        <span className="hint-pop" role="tooltip">
          <b>{hint.title}</b>
          <span>{hint.text}</span>
          <Link to="/help" onClick={() => setOpen(false)}>Подробнее — в «Помощи»</Link>
        </span>
      )}
    </span>
  );
}
