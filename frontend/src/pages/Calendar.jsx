import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Badge } from '../components/ui';
import { ARTICLE_STATUS, CHANNELS, fmtDate, fmtDay } from '../dicts';
import Hint from '../components/Hint';

/* -------------------------- Календарь публикаций (11.8 ТЗ, Этап 2) --------------------------
   Виды: месяц / неделя / список. События — статьи с плановой (planned_at)
   или фактической (published_at) датой. Клик по событию открывает статью. */

const pad = (n) => String(n).padStart(2, '0');
const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const startOfWeek = (d) => { const x = new Date(d); const wd = (x.getDay() + 6) % 7; return addDays(x, -wd); };

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

export default function CalendarPage() {
  const [view, setView] = useState('month'); // month | week | list
  const [anchor, setAnchor] = useState(() => new Date());
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');

  // Видимый период
  const range = useMemo(() => {
    if (view === 'week') {
      const from = startOfWeek(anchor);
      return { from, to: addDays(from, 6) };
    }
    // месяц (и список показывает тот же месяц)
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    return { from: startOfWeek(first), to: addDays(startOfWeek(last), 6) };
  }, [view, anchor]);

  useEffect(() => {
    setItems(null);
    api(`/api/calendar?date_from=${isoDay(range.from)}&date_to=${isoDay(range.to)}`)
      .then(setItems)
      .catch((e) => setError(e.message));
  }, [range.from.getTime(), range.to.getTime()]);

  const byDay = useMemo(() => {
    const m = {};
    (items || []).forEach((it) => {
      if (!it.day) return;
      (m[it.day] = m[it.day] || []).push(it);
    });
    return m;
  }, [items]);

  const shift = (dir) => {
    if (view === 'week') setAnchor((d) => addDays(d, dir * 7));
    else setAnchor((d) => new Date(d.getFullYear(), d.getMonth() + dir, 1));
  };

  const title = view === 'week'
    ? `${fmtDay(range.from)} — ${fmtDay(addDays(startOfWeek(anchor), 6))}`
    : `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`;

  return (
    <>
      <div className="page-head">
        <h1>Календарь публикаций<Hint id="calendar" /></h1>
        <div className="cal-controls">
          <button className="secondary small" onClick={() => shift(-1)}>←</button>
          <span className="cal-title">{title}</span>
          <button className="secondary small" onClick={() => shift(1)}>→</button>
          <button className="secondary small" onClick={() => setAnchor(new Date())}>Сегодня</button>
          <select value={view} onChange={(e) => setView(e.target.value)}>
            <option value="month">Месяц</option>
            <option value="week">Неделя</option>
            <option value="list">Список</option>
          </select>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      {items === null ? <div className="empty">Загрузка…</div>
        : view === 'list' ? <ListView items={items} />
        : <GridView view={view} anchor={anchor} range={range} byDay={byDay} />}
      <p className="muted-text" style={{ marginTop: 12 }}>
        Чтобы запланировать или перенести публикацию, откройте статью в статусе
        «Готова к публикации» и укажите дату в блоке «Публикация». Отметить
        опубликованной вручную можно там же — внешних интеграций на Этапе 2 нет.
      </p>
    </>
  );
}

function EventChip({ it }) {
  const tone = ARTICLE_STATUS[it.status]?.tone || 'gray';
  return (
    <Link to={`/articles/${it.id}`} className={`chip ${tone}`}
      title={`${it.title}\n${CHANNELS[it.channel] || it.channel} · ${ARTICLE_STATUS[it.status]?.label || it.status}${it.responsible ? `\nОтветственный: ${it.responsible}` : ''}`}>
      {it.title}
    </Link>
  );
}

function GridView({ view, anchor, range, byDay }) {
  const days = [];
  const total = view === 'week' ? 7
    : Math.round((range.to - range.from) / 86400000) + 1;
  for (let i = 0; i < total; i += 1) days.push(addDays(range.from, i));
  const today = isoDay(new Date());

  return (
    <div className="cal-grid-wrap">
      <div className="cal-grid">
        {WEEKDAYS.map((w) => <div key={w} className="cal-head">{w}</div>)}
        {days.map((d) => {
          const key = isoDay(d);
          const off = view === 'month' && d.getMonth() !== anchor.getMonth();
          return (
            <div key={key} className={`cal-cell ${off ? 'off' : ''} ${key === today ? 'today' : ''}`}>
              <div className="cal-date">{d.getDate()}</div>
              {(byDay[key] || []).map((it) => <EventChip key={it.id + it.status} it={it} />)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ListView({ items }) {
  if (items.length === 0) {
    return (
      <div className="empty">
        В этом периоде публикаций нет. Доведите статью до статуса
        «Готова к публикации» и запланируйте её из карточки статьи.
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Статья</th><th>Канал</th><th>Направление</th><th>Статус</th>
            <th>Ответственный</th><th>Дедлайн проверки</th><th>План</th><th>Факт</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id}>
              <td><Link to={`/articles/${it.id}`}>{it.title}</Link></td>
              <td>{CHANNELS[it.channel] || it.channel}</td>
              <td>{it.direction || '—'}</td>
              <td><Badge map={ARTICLE_STATUS} value={it.status} /></td>
              <td>{it.responsible || '—'}</td>
              <td>{fmtDate(it.review_deadline)}</td>
              <td>{fmtDate(it.planned_at)}</td>
              <td>{fmtDate(it.published_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
