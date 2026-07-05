import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { Badge, EntityForm, Modal } from '../components/ui';
import { fmtDate, IMPORTANCE, INFOEVENT_STATUS } from '../dicts';
import Hint from '../components/Hint';

const canWrite = (user) => ['admin', 'editor'].includes(user.role);

const FORM_FIELDS = [
  { name: 'title', label: 'Заголовок', required: true, full: true },
  { name: 'direction', label: 'Направление' },
  { name: 'importance', label: 'Важность', type: 'select', default: 'medium', required: true,
    options: { high: 'Высокая', medium: 'Средняя', low: 'Низкая' } },
  { name: 'summary', label: 'Краткая выжимка', type: 'textarea', full: true },
  { name: 'links', label: 'Исходные ссылки (по одной на строку)', type: 'textarea', full: true },
  { name: 'why_important', label: 'Почему это важно для клиентов', type: 'textarea', full: true },
  { name: 'related_services', label: 'Какие услуги EFFEСOM связаны с темой', type: 'textarea', full: true },
  { name: 'suggested_titles', label: 'Предложенные заголовки статей (по одному на строку)', type: 'textarea', full: true },
  { name: 'source_id', label: 'ID источника (если есть)', type: 'number' },
];

/* -------------------------------------------- Инфоповоды (11.5 ТЗ, Этап 2) */
export default function InfoEventsPage({ user }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [importance, setImportance] = useState('');
  const [selected, setSelected] = useState(null); // карточка инфоповода
  const [editing, setEditing] = useState(null);   // null | {} | row

  const load = async () => {
    const q = new URLSearchParams();
    if (status) q.set('status', status);
    if (importance) q.set('importance', importance);
    try {
      setRows(await api('/api/info-events' + (q.toString() ? `?${q}` : '')));
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, [status, importance]);

  const save = async (payload) => {
    if (editing && editing.id) {
      await api(`/api/info-events/${editing.id}`, { method: 'PUT', body: payload });
    } else {
      await api('/api/info-events', { method: 'POST', body: payload });
    }
    setEditing(null);
    setSelected(null);
    await load();
  };

  return (
    <>
      <div className="page-head">
        <h1>Инфоповоды<Hint id="infoEvents" /></h1>
        {canWrite(user) && <button onClick={() => setEditing({})}>Добавить инфоповод</button>}
      </div>
      <div className="filters">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Все статусы</option>
          {Object.entries(INFOEVENT_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={importance} onChange={(e) => setImportance(e.target.value)}>
          <option value="">Любая важность</option>
          {Object.entries(IMPORTANCE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="table-wrap">
        {rows === null ? <div className="empty">Загрузка…</div>
        : rows.length === 0 ? (
          <div className="empty">
            Инфоповодов нет. Добавьте вручную найденное изменение, новость или вопрос —
            на Этапе 3 их начнёт предлагать мониторинг источников.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Заголовок</th><th>Направление</th><th>Важность</th>
                <th>Обнаружен</th><th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => setSelected(r)}>
                  <td>{r.title}</td>
                  <td>{r.direction || '—'}</td>
                  <td><Badge map={IMPORTANCE} value={r.importance} /></td>
                  <td>{fmtDate(r.detected_at)}</td>
                  <td><Badge map={INFOEVENT_STATUS} value={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <EventCard user={user} event={selected}
          onClose={() => setSelected(null)}
          onEdit={() => { setEditing(selected); }}
          onChanged={() => { setSelected(null); load(); }} />
      )}

      {editing !== null && (
        <Modal title={editing.id ? 'Редактирование инфоповода' : 'Новый инфоповод'}
               onClose={() => setEditing(null)}>
          <EntityForm fields={FORM_FIELDS} initial={editing}
                      onSubmit={save} onCancel={() => setEditing(null)} />
        </Modal>
      )}
    </>
  );
}

/* Карточка инфоповода (11.5): выжимка, ссылки, важность для клиентов,
   услуги EFFEСOM, заголовки + кнопки «Создать тему» и «Отклонить». */
function EventCard({ user, event, onClose, onEdit, onChanged }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const createTopic = async () => {
    setBusy(true); setError('');
    try {
      await api(`/api/info-events/${event.id}/create-topic`, { method: 'POST', body: {} });
      navigate('/topics');
    } catch (e) { setError(e.message); setBusy(false); }
  };

  const reject = async () => {
    if (!window.confirm('Отклонить инфоповод?')) return;
    setBusy(true); setError('');
    try {
      await api(`/api/info-events/${event.id}/reject`, { method: 'POST' });
      onChanged();
    } catch (e) { setError(e.message); setBusy(false); }
  };

  const block = (label, text) => text ? (
    <div className="detail-block">
      <h3>{label}</h3>
      <p>{text}</p>
    </div>
  ) : null;

  const editable = canWrite(user);

  return (
    <Modal title={event.title} onClose={onClose}>
      {error && <div className="error-box">{error}</div>}
      <p style={{ marginTop: 0 }}>
        <Badge map={INFOEVENT_STATUS} value={event.status} />{' '}
        <Badge map={IMPORTANCE} value={event.importance} />{' '}
        <span className="muted-text">
          {event.direction ? `· ${event.direction}` : ''} · обнаружен {fmtDate(event.detected_at)}
        </span>
      </p>
      {block('Краткая выжимка', event.summary)}
      {block('Исходные ссылки', event.links)}
      {block('Почему это важно для клиентов', event.why_important)}
      {block('Связанные услуги EFFEСOM', event.related_services)}
      {block('Предложенные заголовки', event.suggested_titles)}
      {!event.summary && !event.links && !event.why_important && (
        <p className="muted-text">Детали не заполнены — откройте редактирование.</p>
      )}
      <div className="actions" style={{ justifyContent: 'space-between' }}>
        <div>
          {editable && <button type="button" className="secondary" onClick={onEdit}>Изменить</button>}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {editable && event.status !== 'rejected' && (
            <button type="button" className="danger" disabled={busy} onClick={reject}>Отклонить</button>
          )}
          {editable && event.status !== 'rejected' && (
            <button type="button" disabled={busy} onClick={createTopic}>
              {busy ? '…' : 'Создать тему'}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
