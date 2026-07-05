import React, { useEffect, useState } from 'react';
import { api } from '../api';
import Hint from './Hint';

/* AI-помощник (Этап 3, 11.7 «Действия»).
   Правила: результаты — только черновики; перезапись существующего текста —
   только после подтверждения (backend отвечает 409 с просьбой подтвердить,
   мы показываем confirm и повторяем с overwrite=true); кнопка блокируется
   на время запроса — защита от двойного клика. */

const ACTIONS = [
  { key: 'brief', label: 'Сгенерировать бриф', path: 'brief' },
  { key: 'draft', label: 'Сгенерировать черновик', path: 'draft' },
  { key: 'improve', label: 'Улучшить текст', path: 'improve',
    alwaysConfirm: 'Улучшение заменит текущий черновик (финальный текст не трогается). Продолжить?' },
  { key: 'versions', label: 'Версии по каналам (AI)', path: 'versions' },
  { key: 'facts', label: 'Проверить факты', path: 'check-facts' },
  { key: 'legal', label: 'Проверить юр. риски', path: 'check-legal' },
  { key: 'quality', label: 'Автопроверка чек-листа', path: 'quality' },
];

export default function AIPanel({ articleId, visible, onDone, onError, onNotice }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState('');

  useEffect(() => {
    api('/api/ai/status').then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  if (!visible) return null;

  const run = async (action, overwrite = false) => {
    if (busy) return; // повторный клик игнорируется
    if (action.alwaysConfirm && !overwrite) {
      if (!window.confirm(action.alwaysConfirm)) return;
      overwrite = true;
    }
    setBusy(action.key);
    try {
      const res = await api(`/api/ai/articles/${articleId}/${action.path}`,
        { method: 'POST', body: { overwrite } });
      onNotice((res && res.detail) || 'Готово — результат сохранён как черновик');
      onDone(action.key, res);
    } catch (e) {
      if (!overwrite && /одтвердите/.test(e.message)) {
        setBusy('');
        if (window.confirm(`${e.message}\n\nПерезаписать?`)) return run(action, true);
        return;
      }
      onError(e);
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="panel">
      <h2>AI-помощник<Hint id="articles.ai" /></h2>
      {status === null && <span className="muted-text">Проверка настроек AI…</span>}
      {status && !status.configured && (
        <span className="muted-text">
          AI не настроен. Задайте AI_PROVIDER, AI_API_KEY и AI_MODEL в .env
          и перезапустите backend — кнопки включатся автоматически.
        </span>
      )}
      {status && status.configured && (
        <>
          <div className="muted-text" style={{ marginBottom: 8 }}>
            {status.provider} · {status.model}
            {status.spending && (
              <> · расход сегодня ${status.spending.today} / месяц ${status.spending.month}</>
            )}
          </div>
          <div className="status-actions">
            {ACTIONS.map((a) => (
              <button key={a.key} className="secondary" disabled={!!busy}
                onClick={() => run(a)}>
                {busy === a.key ? 'Выполняется…' : a.label}
              </button>
            ))}
          </div>
          <div className="muted-text" style={{ marginTop: 8 }}>
            Все результаты сохраняются как черновики; автопроверка только
            предлагает отметки чек-листа — их можно изменить.
          </div>
        </>
      )}
    </div>
  );
}
