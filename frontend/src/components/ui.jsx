import React, { useEffect, useState } from 'react';
import { api } from '../api';

export function Badge({ map, value }) {
  const item = map[value] || { label: value, tone: 'gray' };
  return <span className={`badge ${item.tone}`}>{item.label}</span>;
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true">
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

/* Универсальная форма по описанию полей:
   { name, label, type: text|textarea|select|number|checkbox, options, required, full } */
export function EntityForm({ fields, initial = {}, onSubmit, onCancel, submitLabel = 'Сохранить' }) {
  const [values, setValues] = useState(() => {
    const v = {};
    fields.forEach((f) => {
      // Обязательный селект без default: браузер показывает первый пункт,
      // но в состоянии была бы пустая строка — синхронизируем с видимым.
      const selectFallback = (f.type === 'select' && f.required && f.options)
        ? Object.keys(f.options)[0] : '';
      v[f.name] = initial[f.name] ?? (f.type === 'checkbox' ? true : f.default ?? selectFallback);
    });
    return v;
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }));

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const payload = {};
      fields.forEach((f) => {
        let val = values[f.name];
        if (f.type === 'number') val = val === '' ? null : Number(val);
        if (val === '') val = null;
        payload[f.name] = val;
      });
      await onSubmit(payload);
    } catch (err) {
      setError(err.message || 'Не удалось сохранить');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      {error && <div className="error-box">{error}</div>}
      <div className="form-grid">
        {fields.map((f) => (
          <label key={f.name} className={`field ${f.full ? 'full' : ''}`}>
            <span>{f.label}{f.required ? ' *' : ''}</span>
            {f.type === 'textarea' ? (
              <textarea className={f.tall ? 'tall' : ''} value={values[f.name] ?? ''}
                onChange={(e) => set(f.name, e.target.value)} required={f.required} />
            ) : f.type === 'select' ? (
              <select value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)} required={f.required}>
                {!f.required && <option value="">—</option>}
                {Object.entries(f.options).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            ) : f.type === 'checkbox' ? (
              <input type="checkbox" style={{ width: 'auto' }} checked={!!values[f.name]}
                onChange={(e) => set(f.name, e.target.checked)} />
            ) : (
              <input type={f.type || 'text'} value={values[f.name] ?? ''}
                onChange={(e) => set(f.name, e.target.value)}
                required={f.required} minLength={f.minLength} />
            )}
          </label>
        ))}
      </div>
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>Отмена</button>
        <button type="submit" disabled={busy}>{busy ? 'Сохранение…' : submitLabel}</button>
      </div>
    </form>
  );
}

/* Универсальная CRUD-страница: таблица + модальные формы создания/редактирования. */
export function CrudPage({ title, endpoint, columns, fields, canEdit, canDelete,
                           emptyText = 'Пока пусто. Добавьте первую запись.',
                           renderFilters, rowActions, toolbar, filterRow }) {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null); // null | {} (создание) | row
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  const load = async (q = '') => {
    try {
      setRows(await api(endpoint + q));
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => { load(query); }, [query]);

  const save = async (payload) => {
    if (editing && editing.id) {
      await api(`${endpoint}/${editing.id}`, { method: 'PUT', body: payload });
    } else {
      await api(endpoint, { method: 'POST', body: payload });
    }
    setEditing(null);
    await load(query);
  };

  const remove = async (row) => {
    if (!window.confirm('Удалить запись без возможности восстановления?')) return;
    try {
      await api(`${endpoint}/${row.id}`, { method: 'DELETE' });
      await load(query);
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>{title}</h1>
        {canEdit && <button onClick={() => setEditing({})}>Добавить</button>}
      </div>
      {toolbar && <div className="filters">{toolbar}</div>}
      {renderFilters && renderFilters(setQuery)}
      {error && <div className="error-box">{error}</div>}
      <div className="table-wrap">
        {rows === null ? (
          <div className="empty">Загрузка…</div>
        ) : (filterRow ? rows.filter(filterRow) : rows).length === 0 ? (
          <div className="empty">{emptyText}</div>
        ) : (
          <table>
            <thead>
              <tr>
                {columns.map((c) => <th key={c.key}>{c.label}</th>)}
                {(canEdit || canDelete || rowActions) && <th>Действия</th>}
              </tr>
            </thead>
            <tbody>
              {(filterRow ? rows.filter(filterRow) : rows).map((row) => (
                <tr key={row.id}>
                  {columns.map((c) => <td key={c.key}>{c.render ? c.render(row) : row[c.key] ?? '—'}</td>)}
                  {(canEdit || canDelete || rowActions) && (
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {rowActions && rowActions(row, () => load(query))}{' '}
                      {canEdit && <button className="secondary small" onClick={() => setEditing(row)}>Изменить</button>}{' '}
                      {canDelete && <button className="danger small" onClick={() => remove(row)}>Удалить</button>}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing !== null && (
        <Modal title={editing.id ? 'Редактирование' : 'Новая запись'} onClose={() => setEditing(null)}>
          <EntityForm fields={fields} initial={editing} onSubmit={save} onCancel={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}


/* Вкладки (11.14.2: вкладки для версий статьи). */
export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" type="button"
          className={`tab ${active === t.key ? 'active' : ''}`}
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}>
          {t.label}{t.badge != null && <span className="tab-badge">{t.badge}</span>}
        </button>
      ))}
    </div>
  );
}
