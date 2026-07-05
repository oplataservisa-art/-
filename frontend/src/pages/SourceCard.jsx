import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { Badge } from '../components/ui';
import Hint from '../components/Hint';
import { fmtDate, SOURCE_STATUS, SOURCE_TYPE } from '../dicts';
import { ITEM_STATUS } from './Materials';

/* Этап 4a: карточка источника (11.4 ТЗ) — настройки доступа, история
   проверок, найденные материалы с чекбоксами, ошибки, «Проверить сейчас»,
   «Создать инфоповод из выбранных» (дальше тема — в 1 клик из инфоповода). */

const CHECK_STATUS = {
  ok: { label: 'Успешно', tone: 'green' },
  error: { label: 'Ошибка', tone: 'red' },
  blocked: { label: 'Доступ закрыт', tone: 'red' },
};
const FREQ = { hourly: 'Каждый час', daily: 'Ежедневно', weekly: 'Еженедельно', manual: 'Вручную' };

const canManage = (user) => ['admin', 'editor'].includes(user.role);

export default function SourceCardPage({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [source, setSource] = useState(null);
  const [items, setItems] = useState([]);
  const [checks, setChecks] = useState([]);
  const [picked, setPicked] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const sources = await api('/api/sources');
      const found = sources.find((s) => String(s.id) === String(id));
      if (!found) { setError('Источник не найден'); return; }
      setSource(found);
      setItems(await api(`/api/sources/${id}/items`));
      setChecks(await api(`/api/sources/${id}/checks`));
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, [id]);

  const checkNow = async () => {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const res = await api(`/api/sources/${id}/check-now`, { method: 'POST', body: {} });
      setNotice(res.status === 'ok'
        ? `Проверка завершена: новых материалов — ${res.found_new}`
        : `Проверка завершилась со статусом «${CHECK_STATUS[res.status]?.label || res.status}»: ${res.error || ''}`);
      await load();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const makeInfoEvent = async () => {
    if (!picked.length || busy) return;
    setBusy(true); setError('');
    try {
      const event = await api('/api/info-events/from-items',
        { method: 'POST', body: { item_ids: picked } });
      setNotice(`Инфоповод №${event.id} создан из ${picked.length} материалов`);
      setPicked([]);
      await load();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const makeTopic = async () => {
    if (!picked.length || busy) return;
    setBusy(true); setError('');
    try {
      const topic = await api('/api/topics/from-items',
        { method: 'POST', body: { item_ids: picked } });
      setNotice(`Тема №${topic.id} создана из ${picked.length} материалов — раздел «Темы»`);
      setPicked([]);
      await load();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const toggle = (itemId) => setPicked((p) =>
    p.includes(itemId) ? p.filter((x) => x !== itemId) : [...p, itemId]);

  if (error && !source) return <div className="error-box">{error}</div>;
  if (!source) return <div className="empty">Загрузка…</div>;

  return (
    <div>
      <div className="page-head">
        <h1>{source.name}<Hint id="sourceCard" /></h1>
        {canManage(user) && (
          <button onClick={checkNow} disabled={busy}>
            {busy ? 'Проверяю…' : 'Проверить сейчас'}
          </button>
        )}
      </div>
      {error && <div className="error-box">{error}</div>}
      {notice && <div className="panel notice">{notice}</div>}

      <div className="panel">
        <h2>Настройки</h2>
        <p className="info-line">
          Тип: {SOURCE_TYPE[source.type] || source.type}
          {' · '}Статус: <Badge map={SOURCE_STATUS} value={source.status} />
          {' · '}Частота: {FREQ[source.check_frequency] || source.check_frequency}
          {' · '}Последняя проверка: {source.last_checked_at ? fmtDate(source.last_checked_at) : '—'}
        </p>
        {source.url && <p className="info-line">URL: <a href={source.url} target="_blank" rel="noreferrer">{source.url}</a></p>}
        <p className="info-line muted-text">
          Правила доступа: {source.access_rules || 'не заполнены — сервис в любом случае уважает robots.txt и не заходит в закрытые разделы'}
        </p>
        <p className="info-line"><Link to="/sources">← ко всем источникам</Link></p>
      </div>

      <div className="panel">
        <h2>Найденные материалы ({items.length})</h2>
        {items.length === 0 && (
          <p className="muted-text">Пока пусто — нажмите «Проверить сейчас».</p>
        )}
        {items.map((m) => (
          <div key={m.id} className="source-item-row">
            {canManage(user) && m.status !== 'info_event_created' && (
              <input type="checkbox" checked={picked.includes(m.id)}
                onChange={() => toggle(m.id)} />
            )}
            <div>
              <a href={m.url} target="_blank" rel="noreferrer">{m.title}</a>
              <div className="muted-text">
                {fmtDate(m.published_at || m.collected_at)} · релевантность {m.relevance_score}
                {' · '}<Badge map={ITEM_STATUS} value={m.status} />
              </div>
            </div>
          </div>
        ))}
        {canManage(user) && items.length > 0 && (
          <div className="row-actions" style={{ marginTop: 10 }}>
            <button className="secondary" disabled={!picked.length || busy}
              onClick={makeInfoEvent}>
              Создать инфоповод из выбранных ({picked.length})
            </button>
            <button className="secondary" disabled={!picked.length || busy}
              onClick={makeTopic}>
              Создать тему из выбранных
            </button>
            <button className="secondary" onClick={() => navigate('/materials')}>
              Все материалы →
            </button>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>История проверок</h2>
        {checks.length === 0
          ? <p className="muted-text">Проверок ещё не было.</p>
          : (
            <table>
              <thead>
                <tr><th>Когда</th><th>Запуск</th><th>Статус</th><th>Новых</th><th>Ошибка</th></tr>
              </thead>
              <tbody>
                {checks.map((c) => (
                  <tr key={c.id}>
                    <td>{fmtDate(c.started_at)}</td>
                    <td>{c.triggered_by === 'manual' ? 'вручную' : 'воркер'}</td>
                    <td><Badge map={CHECK_STATUS} value={c.status} /></td>
                    <td>{c.found_new}</td>
                    <td className="muted-text">{c.error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </div>
  );
}
