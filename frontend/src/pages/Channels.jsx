import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { fmtDate } from '../dicts';
import Hint from '../components/Hint';

/* Экран каналов публикации (11.10). MVP: интеграций нет, статус — «ручной»/
   «экспорт». Показывает шаблон, UTM-заготовку, последнюю публикацию и ошибки.
   Ключи/токены не отображаются (в MVP их и нет). */
const CONNECTION = { manual: 'Ручной', export: 'Экспорт' };

export default function ChannelsPage() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/channels').then(setRows).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <div className="page-head"><h1>Каналы публикации<Hint id="channels" /></h1></div>
      {error && <div className="error-box">{error}</div>}
      <p className="muted-text">
        Интеграции с API площадок в MVP отключены (см. ограничения ТЗ). Публикация
        выполняется вручную: экспорт материала и фиксация ссылки на карточке статьи.
      </p>
      <div className="cards-grid">
        {rows.map((c) => (
          <div className="panel" key={c.key}>
            <h2>{c.name}</h2>
            <p className="info-line">Подключение: <b>{CONNECTION[c.connection] || c.connection}</b></p>
            <p className="info-line">Шаблон: {c.template}</p>
            <p className="info-line">UTM: <code>{c.utm}</code></p>
            <p className="info-line">
              Последняя публикация: {c.last_publication
                ? <>{c.last_publication.status === 'error' ? '⚠ ошибка' : 'опубликовано'}
                    {c.last_publication.published_at && <> · {fmtDate(c.last_publication.published_at)}</>}
                    {c.last_publication.url && <> · <a href={c.last_publication.url} target="_blank" rel="noreferrer">ссылка</a></>}</>
                : '—'}
            </p>
            {c.last_error && <p className="info-line" style={{ color: 'var(--danger, #b00)' }}>Ошибка: {c.last_error}</p>}
          </div>
        ))}
      </div>
    </>
  );
}
