import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { Modal } from '../components/ui';
import { fmtDate } from '../dicts';
import Hint from '../components/Hint';

/* Промпты (11.12 и 12 ТЗ; Этап 3).
   Редактирование создаёт новую версию; история версий не удаляется.
   Тестовый запуск (11.12.8) ничего не сохраняет в статьи. */

const canEdit = (user) => ['admin', 'editor'].includes(user.role);

export default function PromptsPage({ user }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(null);   // prompt | null
  const [history, setHistory] = useState(null);   // {prompt, versions} | null
  const [testing, setTesting] = useState(null);   // prompt | null

  const load = () => api('/api/prompts').then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const openHistory = async (prompt) => {
    try {
      setHistory({ prompt, versions: await api(`/api/prompts/${prompt.key}/versions`) });
    } catch (e) { setError(e.message); }
  };

  if (error && !rows) return <div className="error-box">{error}</div>;
  if (!rows) return <div className="empty">Загрузка…</div>;

  return (
    <div>
      <div className="page-head"><h1>Промпты<Hint id="prompts" /></h1></div>
      {error && <div className="error-box">{error}</div>}
      <p className="muted-text" style={{ marginBottom: 12 }}>
        Шаблоны AI-генерации (раздел 12 ТЗ). Каждое изменение текста шаблона
        создаёт новую версию; старые версии сохраняются и не удаляются.
      </p>
      <div className="panel" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Ключ</th><th>Название</th><th>Назначение</th>
              <th>Версия</th><th>Кем изменён</th><th>Когда</th><th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.key}>
                <td><code>{p.key}</code></td>
                <td>{p.name}</td>
                <td className="muted">{p.purpose || '—'}</td>
                <td>v{p.version}</td>
                <td>{p.updated_by || '—'}</td>
                <td>{fmtDate(p.updated_at)}</td>
                <td>
                  <div className="row-actions">
                    {canEdit(user) && (
                      <button className="secondary small" onClick={() => setEditing(p)}>Изменить</button>
                    )}
                    <button className="secondary small" onClick={() => openHistory(p)}>История</button>
                    {canEdit(user) && (
                      <button className="secondary small" onClick={() => setTesting(p)}>Тест</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <EditPromptModal prompt={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} onError={setError} />
      )}
      {history && (
        <Modal title={`История: ${history.prompt.name}`} onClose={() => setHistory(null)}>
          {history.versions.map((v) => (
            <details key={v.version} style={{ marginBottom: 10 }}>
              <summary>
                v{v.version} — {v.author || '—'} · {fmtDate(v.created_at)}
                {v.version === history.prompt.version ? ' (текущая)' : ''}
              </summary>
              <pre className="prompt-view">{v.template}</pre>
            </details>
          ))}
        </Modal>
      )}
      {testing && (
        <TestPromptModal prompt={testing} onClose={() => setTesting(null)} />
      )}
    </div>
  );
}

function EditPromptModal({ prompt, onClose, onSaved, onError }) {
  const [form, setForm] = useState({
    name: prompt.name, purpose: prompt.purpose || '',
    variables: prompt.variables || '', template: prompt.template,
  });
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await api(`/api/prompts/${prompt.key}`, { method: 'PUT', body: form });
      onSaved();
    } catch (e) { onError(e.message); setBusy(false); }
  };

  return (
    <Modal title={`Промпт: ${prompt.key} (v${prompt.version})`} onClose={onClose}>
      <label>Название
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <label>Назначение
        <input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
      </label>
      <label>Переменные (через запятую; в шаблоне — {'{имя}'})
        <input value={form.variables} onChange={(e) => setForm({ ...form, variables: e.target.value })} />
      </label>
      <label>Текст шаблона
        <textarea rows={14} value={form.template}
          onChange={(e) => setForm({ ...form, template: e.target.value })} />
      </label>
      <p className="muted-text">Изменение текста шаблона создаст версию v{prompt.version + 1}.</p>
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>Отмена</button>
        <button type="button" disabled={busy} onClick={save}>
          {busy ? 'Сохранение…' : 'Сохранить'}
        </button>
      </div>
    </Modal>
  );
}

function TestPromptModal({ prompt, onClose }) {
  const initial = Object.fromEntries(
    (prompt.variables || '').split(',').map((v) => v.trim()).filter(Boolean)
      .map((v) => [v, '']));
  const [vars, setVars] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const run = async () => {
    if (busy) return;
    setBusy(true); setError(''); setResult(null);
    try {
      setResult(await api(`/api/prompts/${prompt.key}/test`,
        { method: 'POST', body: { variables: vars } }));
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  return (
    <Modal title={`Тестовый запуск: ${prompt.name}`} onClose={onClose}>
      {Object.keys(vars).length === 0 && (
        <p className="muted-text">У шаблона нет переменных — можно запускать как есть.</p>
      )}
      {Object.keys(vars).map((k) => (
        <label key={k}>{`{${k}}`}
          <input value={vars[k]}
            onChange={(e) => setVars({ ...vars, [k]: e.target.value })} />
        </label>
      ))}
      {error && <div className="error-box">{error}</div>}
      {result && (
        <>
          <h3 style={{ marginTop: 12 }}>Рендер шаблона</h3>
          <pre className="prompt-view">{result.rendered}</pre>
          <h3>Ответ AI</h3>
          {result.result === null
            ? <p className="muted-text">{result.detail}</p>
            : <pre className="prompt-view">{result.result}</pre>}
        </>
      )}
      <div className="modal-actions">
        <button className="secondary" type="button" onClick={onClose}>Закрыть</button>
        <button type="button" disabled={busy} onClick={run}>
          {busy ? 'Выполняется…' : 'Запустить'}
        </button>
      </div>
    </Modal>
  );
}
