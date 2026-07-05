import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { Badge, Modal } from '../components/ui';
import Hint from '../components/Hint';
import { fmtDate } from '../dicts';

/* Этап 4a/4b: лента найденных материалов (6.2.8, 11.4 ТЗ).
   4b: фильтры (источник/дата/релевантность/статус), чекбоксы и массовые
   действия, тема из выбранных, ручной AI-анализ группы с ПРЕДПРОСМОТРОМ —
   сохранение только отдельным кликом «Создать инфоповод с анализом». */

export const ITEM_STATUS = {
  new: { label: 'Новый', tone: 'blue' },
  reviewed: { label: 'Просмотрен', tone: 'gray' },
  info_event_created: { label: 'Инфоповод создан', tone: 'green' },
  hidden: { label: 'Скрыт', tone: 'gray' },
};

const IMPORTANCE = { high: 'Высокая', medium: 'Средняя', low: 'Низкая' };

const canManage = (user) => ['admin', 'editor'].includes(user.role);

export default function MaterialsPage({ user }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [sources, setSources] = useState([]);
  const [f, setF] = useState({ status: 'new', source_id: '', date_from: '', date_to: '', min_relevance: '' });
  const [picked, setPicked] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null); // результат анализа группы

  const load = () => {
    const qs = Object.entries(f)
      .filter(([, v]) => v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(k.startsWith('date') ? `${v}T${k === 'date_to' ? '23:59:59' : '00:00:00'}` : v)}`)
      .join('&');
    api(`/api/source-items${qs ? `?${qs}` : ''}`)
      .then((r) => { setRows(r); setPicked([]); })
      .catch((e) => setError(e.message));
  };
  useEffect(() => { load(); }, [f]);
  useEffect(() => { api('/api/sources').then(setSources).catch(() => {}); }, []);

  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const flash = (msg) => { setNotice(msg); setError(''); };
  const fail = (e) => { setError(e.message); setNotice(''); };

  const bulk = async (action, label) => {
    if (!picked.length || busy) return;
    setBusy(true);
    try {
      const r = await api('/api/source-items/bulk', { method: 'POST', body: { item_ids: picked, action } });
      flash(`${label}: изменено ${r.changed} из ${r.total}`);
      load();
    } catch (e) { fail(e); }
    setBusy(false);
  };

  const makeInfoEvent = async (analysis) => {
    if (!picked.length || busy) return;
    setBusy(true);
    try {
      const body = { item_ids: picked, ...(analysis || {}) };
      const ev = await api('/api/info-events/from-items', { method: 'POST', body });
      flash(`Инфоповод №${ev.id} создан${analysis ? ' с AI-анализом' : ''} — раздел «Инфоповоды»`);
      setPreview(null);
      load();
    } catch (e) { fail(e); }
    setBusy(false);
  };

  const makeTopic = async () => {
    if (!picked.length || busy) return;
    setBusy(true);
    try {
      const topic = await api('/api/topics/from-items', { method: 'POST', body: { item_ids: picked } });
      flash(`Тема №${topic.id} создана — открываю`);
      navigate('/topics');
    } catch (e) { fail(e); setBusy(false); }
  };

  const analyzeGroup = async () => {
    if (!picked.length || busy) return;
    setBusy(true); setError('');
    try {
      const r = await api('/api/source-items/analyze-group', { method: 'POST', body: { item_ids: picked } });
      setPreview(r);
    } catch (e) { fail(e); }
    setBusy(false);
  };

  if (!rows) return <div className="empty">Загрузка…</div>;

  return (
    <div>
      <div className="page-head"><h1>Найденные материалы<Hint id="materials" /></h1></div>
      {error && <div className="error-box">{error}</div>}
      {notice && <div className="panel notice">{notice}</div>}

      <div className="filters materials-filters">
        <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
          <option value="new">Новые</option>
          <option value="reviewed">Просмотренные</option>
          <option value="info_event_created">С инфоповодом</option>
          <option value="hidden">Скрытые</option>
          <option value="">Все статусы</option>
        </select>
        <select value={f.source_id} onChange={(e) => setF({ ...f, source_id: e.target.value })}>
          <option value="">Все источники</option>
          {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label className="filter-inline">с
          <input type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} />
        </label>
        <label className="filter-inline">по
          <input type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} />
        </label>
        <label className="filter-inline">релевантность ≥
          <input type="number" min="0" style={{ width: 64 }} value={f.min_relevance}
            onChange={(e) => setF({ ...f, min_relevance: e.target.value })} />
        </label>
      </div>

      {canManage(user) && rows.length > 0 && (
        <div className="bulk-bar panel">
          <label className="filter-inline">
            <input type="checkbox"
              checked={picked.length > 0 && picked.length === rows.filter((r) => r.status !== 'info_event_created').length}
              onChange={(e) => setPicked(e.target.checked
                ? rows.filter((r) => r.status !== 'info_event_created').map((r) => r.id) : [])} />
            Выбрано: {picked.length}
          </label>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={() => makeInfoEvent(null)}>Инфоповод из выбранных</button>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={makeTopic}>Тема из выбранных</button>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={analyzeGroup}>{busy ? 'Выполняется…' : 'Анализ группы (AI)'}</button>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={() => bulk('reviewed', 'Просмотрено')}>Отметить просмотренными</button>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={() => bulk('hide', 'Скрыто')}>Скрыть</button>
          <button className="secondary small" disabled={!picked.length || busy}
            onClick={() => bulk('restore', 'Восстановлено')}>Восстановить</button>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="empty">
          Материалов по фильтру нет. Их находит мониторинг: откройте источник и
          нажмите «Проверить сейчас», либо включите MONITOR_ENABLED в .env.
        </div>
      ) : (
        <div className="materials-list">
          {rows.map((m) => (
            <div key={m.id} className="panel material-card">
              <div className="material-head">
                <span>
                  {canManage(user) && (
                    <input type="checkbox" checked={picked.includes(m.id)}
                      disabled={m.status === 'info_event_created'}
                      title={m.status === 'info_event_created'
                        ? 'Инфоповод уже создан — материал нельзя выбрать повторно' : undefined}
                      onChange={() => toggle(m.id)} style={{ marginRight: 8 }} />
                  )}
                  <a href={m.url} target="_blank" rel="noreferrer">{m.title}</a>
                </span>
                <Badge map={ITEM_STATUS} value={m.status} />
              </div>
              <div className="muted-text">
                Собран: {fmtDate(m.collected_at)}
                {m.published_at && <> · Опубликован источником: {fmtDate(m.published_at)}</>}
                {' · '}Релевантность: {m.relevance_score}
                {m.importance && <> · Важность (AI): {IMPORTANCE[m.importance] || m.importance}</>}
              </div>
              {m.excerpt && <p className="material-excerpt">{m.excerpt}</p>}
              {m.summary && <p className="material-summary"><b>AI-анализ:</b> {m.summary}</p>}
              {m.info_event_id && (
                <div className="muted-text">→ <Link to="/info-events">Инфоповод №{m.info_event_id}</Link></div>
              )}
            </div>
          ))}
        </div>
      )}

      {preview && (
        <Modal title={`AI-анализ группы (${preview.items_count} материалов) — предпросмотр`}
          onClose={() => setPreview(null)}>
          <p className="muted-text">{preview.detail}</p>
          {preview.summary && (<><h3>Выжимка</h3><p>{preview.summary}</p></>)}
          {preview.why_important && (<><h3>Почему важно клиентам EFFEСOM</h3><p>{preview.why_important}</p></>)}
          {preview.importance && (<p><b>Важность:</b> {IMPORTANCE[preview.importance] || preview.importance}</p>)}
          {preview.suggested_titles && (
            <><h3>Возможные темы</h3><pre className="prompt-view">{preview.suggested_titles}</pre></>
          )}
          <div className="modal-actions">
            <button className="secondary" type="button" onClick={() => setPreview(null)}>
              Закрыть без сохранения
            </button>
            <button type="button" disabled={busy} onClick={() => makeInfoEvent({
              summary: preview.summary || undefined,
              why_important: preview.why_important || undefined,
              importance: preview.importance || undefined,
              suggested_titles: preview.suggested_titles || undefined,
            })}>
              Создать инфоповод с анализом
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
