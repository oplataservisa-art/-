import React from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { Badge, CrudPage } from '../components/ui';
import { fmtDate, KNOWLEDGE_TYPE, PRIORITY, SOURCE_STATUS, SOURCE_TYPE,
         TOPIC_STATUS, CHANNELS } from '../dicts';
import Hint from '../components/Hint';

const canWrite = (user) => ['admin', 'editor'].includes(user.role);
const isAdmin = (user) => user.role === 'admin';

/* -------------------------------------------------- Источники (11.4 ТЗ) */
export function SourcesPage({ user }) {
  const navigate = useNavigate();
  const [stats, setStats] = React.useState({});
  const [flt, setFlt] = React.useState('');
  React.useEffect(() => {
    api('/api/sources-stats').then(setStats).catch(() => {});
  }, []);
  const stat = (r) => stats[String(r.id)] || { new_items: 0, errors_7d: 0 };
  return (
    <CrudPage
      title={<>Источники<Hint id="sources" /></>}
      endpoint="/api/sources"
      filterRow={(r) => (flt === 'active' ? r.status === 'active'
        : flt === 'errors' ? r.status === 'error' || stat(r).errors_7d > 0 : true)}
      toolbar={(
        <select value={flt} onChange={(e) => setFlt(e.target.value)}>
          <option value="">Все источники</option>
          <option value="active">Только активные</option>
          <option value="errors">С ошибками</option>
        </select>
      )}
      canEdit={canWrite(user)}
      canDelete={isAdmin(user)}
      emptyText="Источников пока нет. Добавьте первый: сайт ведомства, RSS-ленту или страницу с нормативными актами."
      columns={[
        { key: 'name', label: 'Название' },
        { key: 'type', label: 'Тип', render: (r) => SOURCE_TYPE[r.type] || r.type },
        { key: 'url', label: 'URL', render: (r) => r.url ? <span className="muted">{r.url}</span> : '—' },
        { key: 'status', label: 'Статус', render: (r) => <Badge map={SOURCE_STATUS} value={r.status} /> },
        { key: 'check_frequency', label: 'Частота проверки', render: (r) => (
            ({ hourly: 'Каждый час', daily: 'Ежедневно', weekly: 'Еженедельно', manual: 'Вручную' })[r.check_frequency] || r.check_frequency) },
        { key: 'last_checked_at', label: 'Последняя проверка', render: (r) => fmtDate(r.last_checked_at) },
        { key: 'new_items', label: 'Найдено новых', render: (r) => stat(r).new_items },
        { key: 'errors_7d', label: 'Ошибок за 7 дней', render: (r) => (
            stat(r).errors_7d > 0 ? <span className="err-count">{stat(r).errors_7d}</span> : 0) },
      ]}
      rowActions={(row) => (
        <button className="secondary small" onClick={() => navigate(`/sources/${row.id}`)}>Открыть</button>
      )}
      fields={[
        { name: 'name', label: 'Название', required: true },
        { name: 'type', label: 'Тип источника', type: 'select', options: SOURCE_TYPE, required: true },
        { name: 'url', label: 'URL', full: true },
        { name: 'check_frequency', label: 'Частота проверки', type: 'select', default: 'daily',
          options: { hourly: 'Каждый час', daily: 'Ежедневно', weekly: 'Еженедельно', manual: 'Вручную' }, required: true },
        { name: 'status', label: 'Статус', type: 'select', options: Object.fromEntries(
            Object.entries(SOURCE_STATUS).map(([k, v]) => [k, v.label])), default: 'active', required: true },
        { name: 'access_rules', label: 'Правила доступа (лицензия, robots.txt, ограничения)', type: 'textarea', full: true },
      ]}
    />
  );
}

/* ------------------------------------------------ База знаний (11.9 ТЗ) */
export function KnowledgePage({ user }) {
  const canEdit = ['admin', 'editor', 'content_manager'].includes(user.role);
  return (
    <CrudPage
      title={<>База знаний EFFEСOM<Hint id="knowledge" /></>}
      endpoint="/api/knowledge"
      canEdit={canEdit}
      canDelete={isAdmin(user)}
      emptyText="База знаний пуста. Добавьте курсы, преимущества, FAQ и запрещённые формулировки — на Этапе 2 AI будет опираться на эти данные."
      columns={[
        { key: 'title', label: 'Название' },
        { key: 'type', label: 'Раздел', render: (r) => KNOWLEDGE_TYPE[r.type] || r.type },
        { key: 'tags', label: 'Теги', render: (r) => r.tags ? <span className="muted">{r.tags}</span> : '—' },
        { key: 'is_actual', label: 'Актуальность', render: (r) => (
            <Badge map={{ true: { label: 'Актуально', tone: 'green' }, false: { label: 'Устарело', tone: 'yellow' } }}
                   value={String(r.is_actual)} />) },
        { key: 'updated_at', label: 'Обновлено', render: (r) => fmtDate(r.updated_at) },
      ]}
      fields={[
        { name: 'title', label: 'Название', required: true },
        { name: 'type', label: 'Раздел', type: 'select', options: KNOWLEDGE_TYPE, required: true },
        { name: 'content', label: 'Содержание', type: 'textarea', tall: true, full: true },
        { name: 'tags', label: 'Теги (через запятую)' },
        { name: 'is_actual', label: 'Актуально', type: 'checkbox' },
      ]}
    />
  );
}

/* ---------------------------------------------------------- Темы (11.6 ТЗ) */
export function TopicsPage({ user }) {
  const navigate = useNavigate();

  // 11.15.3: создать статью из темы за 1 клик
  const createArticle = async (topic) => {
    try {
      const article = await api('/api/articles', {
        method: 'POST',
        body: { title: topic.title, topic_id: topic.id, channel: topic.channel || 'site' },
      });
      navigate(`/articles/${article.id}`);
    } catch (e) { alert(e.message); }
  };

  const aiBrief = async (topic) => {
    try {
      const article = await api(`/api/ai/topics/${topic.id}/brief`, { method: 'POST', body: {} });
      navigate(`/articles/${article.id}`);
    } catch (e) { alert(e.message); }
  };

  return (
    <CrudPage
      title={<>Темы<Hint id="topics" /></>}
      endpoint="/api/topics"
      canEdit={canWrite(user)}
      canDelete={isAdmin(user)}
      emptyText="Тем пока нет. Создайте первую тему вручную или из инфоповода: заголовок, направление, аудитория, ключевые слова и CTA."
      rowActions={canWrite(user) ? (row) => (
        !['article_created', 'rejected', 'archived'].includes(row.status) && (
          <>
            {['idea', 'needs_brief'].includes(row.status) && (
              <button className="secondary small" onClick={() => aiBrief(row)}>SEO-бриф (AI)</button>
            )}
            <button className="secondary small" onClick={() => createArticle(row)}>Создать статью</button>
          </>
        )
      ) : undefined}
      renderFilters={(setQuery) => (
        <div className="filters">
          <select onChange={(e) => setQuery(e.target.value ? `?status=${e.target.value}` : '')} defaultValue="">
            <option value="">Все статусы</option>
            {Object.entries(TOPIC_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
      )}
      columns={[
        { key: 'title', label: 'Тема' },
        { key: 'direction', label: 'Направление' },
        { key: 'audience', label: 'Аудитория' },
        { key: 'priority', label: 'Приоритет', render: (r) => PRIORITY[r.priority] || r.priority },
        { key: 'channel', label: 'Канал', render: (r) => CHANNELS[r.channel] || r.channel || '—' },
        { key: 'status', label: 'Статус', render: (r) => <Badge map={TOPIC_STATUS} value={r.status} /> },
        { key: 'created_at', label: 'Создана', render: (r) => fmtDate(r.created_at) },
      ]}
      fields={[
        { name: 'title', label: 'Заголовок темы', required: true, full: true },
        { name: 'direction', label: 'Направление обучения' },
        { name: 'audience', label: 'Целевая аудитория' },
        { name: 'intent', label: 'Поисковый интент' },
        { name: 'channel', label: 'Рекомендуемый канал', type: 'select', options: CHANNELS },
        { name: 'priority', label: 'Приоритет', type: 'select', default: '2',
          options: { 1: 'Высокий', 2: 'Средний', 3: 'Низкий' }, required: true },
        { name: 'status', label: 'Статус', type: 'select', default: 'idea', required: true,
          options: Object.fromEntries(Object.entries(TOPIC_STATUS).map(([k, v]) => [k, v.label])) },
        { name: 'keywords', label: 'Ключевые слова', type: 'textarea', full: true },
        { name: 'cta', label: 'Предполагаемый CTA', full: true },
      ]}
    />
  );
}
