import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Hint from '../components/Hint';

// 11.3 ТЗ: карточки отвечают на вопрос «что сегодня нужно сделать»
// и ведут в отфильтрованные списки.
const CARDS = [
  { key: 'new_info_events', label: 'Новые инфоповоды', to: '/info-events' },
  { key: 'topics_need_brief', label: 'Темы ждут брифа', to: '/topics' },
  { key: 'drafts_waiting', label: 'Черновики ждут редактора', to: '/articles?status=draft' },
  { key: 'expert_review', label: 'На экспертной проверке', to: '/articles?status=expert_review' },
  { key: 'ready_to_publish', label: 'Готово к публикации', to: '/articles?status=ready' },
  { key: 'needs_revision', label: 'Требует доработки', to: '/articles?status=needs_revision' },
  { key: 'scheduled', label: 'Запланированы', to: '/calendar' },
  { key: 'sources_error', label: 'Источники с ошибками', to: '/sources' },
  { key: 'new_materials', label: 'Новые материалы мониторинга', to: '/materials' },
];

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [ai, setAi] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/dashboard').then(setData).catch((e) => setError(e.message));
    // Расход AI (14.11.8): блок виден администратору; ошибки не критичны
    api('/api/ai/status').then(setAi).catch(() => {});
  }, []);

  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <div className="empty">Загрузка…</div>;

  return (
    <>
      <div className="page-head"><h1>Дашборд<Hint id="dashboard" /></h1></div>
      <div className="cards">
        {CARDS.map((c) => (
          <Link key={c.key} to={c.to} className="card">
            <div className="num">{data.cards[c.key] ?? 0}</div>
            <div className="cap">{c.label}</div>
          </Link>
        ))}
      </div>

      {ai && ai.spending && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h2>AI-расходы<Hint id="dashboard.ai" /></h2>
          <p className="info-line">
            Сегодня: ${ai.spending.today} из ${ai.budgets.daily_usd} ·
            За месяц: ${ai.spending.month} из ${ai.budgets.monthly_usd}
            {!ai.configured && ' · AI не настроен'}
          </p>
        </div>
      )}
      <div className="panel">
        <h2>Как начать работу</h2>
        <p style={{ margin: 0, color: 'var(--text-muted)' }}>
          Путь материала: инфоповод → тема → статья. Заведите инфоповод и создайте
          из него тему в один клик, из темы — черновик статьи. В карточке статьи
          заполните текст и версии по каналам, закройте чек-лист качества, отправьте
          эксперту, затем запланируйте публикацию в календаре. В карточке статьи
          можно использовать AI-помощник для брифа, черновика, версий и проверок.
          Если AI не настроен, материалы можно вести вручную.
        </p>
      </div>
    </>
  );
}
