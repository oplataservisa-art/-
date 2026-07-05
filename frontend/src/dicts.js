// Русские подписи и цветовая логика статусов (11.14 ТЗ):
// серый — черновик/архив, синий — в работе, жёлтый — внимание,
// зелёный — готово/опубликовано, красный — ошибка/риск.

export const ROLES = {
  admin: 'Администратор',
  editor: 'Редактор',
  expert: 'Эксперт',
  content_manager: 'Контент-менеджер',
  manager: 'Руководитель',
};

export const ARTICLE_STATUS = {
  draft: { label: 'Черновик', tone: 'gray' },
  needs_revision: { label: 'Требует доработки', tone: 'yellow' },
  editing: { label: 'На редактуре', tone: 'blue' },
  expert_review: { label: 'На экспертной проверке', tone: 'blue' },
  ready: { label: 'Готова к публикации', tone: 'green' },
  scheduled: { label: 'Запланирована', tone: 'blue' },
  published: { label: 'Опубликована', tone: 'green' },
  publish_error: { label: 'Ошибка публикации', tone: 'red' },
  archived: { label: 'Архив', tone: 'gray' },
};

export const TOPIC_STATUS = {
  idea: { label: 'Идея', tone: 'gray' },
  needs_brief: { label: 'Нужен бриф', tone: 'yellow' },
  brief_ready: { label: 'Бриф готов', tone: 'blue' },
  writing: { label: 'Пишется статья', tone: 'blue' },
  article_created: { label: 'Статья создана', tone: 'green' },
  rejected: { label: 'Отклонена', tone: 'red' },
  archived: { label: 'Архив', tone: 'gray' },
};

export const SOURCE_STATUS = {
  active: { label: 'Активен', tone: 'green' },
  paused: { label: 'Выключен', tone: 'gray' },
  error: { label: 'Ошибка', tone: 'red' },
};

export const SOURCE_TYPE = {
  official: 'Министерства и ведомства',
  legal_acts: 'Нормативные акты',
  news: 'Новости законодательства',
  legal_system: 'КонсультантПлюс / Гарант',
  effecom: 'Сайт EFFEСOM',
  forum: 'Форумы и сообщества',
  rss: 'RSS-лента',
  manual: 'Ручная загрузка',
  competitor: 'Конкуренты',
};

export const KNOWLEDGE_TYPE = {
  course: 'Курс',
  direction: 'Направление обучения',
  pricing: 'Цены',
  documents: 'Документы и лицензии',
  faq: 'FAQ',
  advantages: 'Преимущества',
  forbidden_phrases: 'Запрещённые формулировки',
  brand_style: 'Стиль бренда',
  legal_limits: 'Юридические ограничения',
  other: 'Прочее',
};

export const CHANNELS = {
  site: 'Сайт',
  dzen: 'Дзен',
  vk: 'VK',
  telegram: 'Telegram',
  export: 'Ручной экспорт',
};

export const PRIORITY = { 1: 'Высокий', 2: 'Средний', 3: 'Низкий' };

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString('ru-RU') : '—');

/* ------------------------------ Этап 2 ------------------------------ */

export const INFOEVENT_STATUS = {
  new: { label: 'Новый', tone: 'blue' },
  in_progress: { label: 'В работе', tone: 'blue' },
  topic_created: { label: 'Создана тема', tone: 'green' },
  rejected: { label: 'Отклонён', tone: 'red' },
  archived: { label: 'Архив', tone: 'gray' },
};

export const IMPORTANCE = {
  high: { label: 'Высокая', tone: 'red' },
  medium: { label: 'Средняя', tone: 'yellow' },
  low: { label: 'Низкая', tone: 'gray' },
};

export const VERSION_CHANNELS = {
  site: 'Сайт',
  dzen: 'Дзен',
  vk: 'VK',
  telegram: 'Telegram',
  markdown: 'HTML/Markdown',
};

export const VERSION_STATUS = {
  draft: { label: 'Черновик', tone: 'gray' },
  ready: { label: 'Готова', tone: 'green' },
  published: { label: 'Опубликована', tone: 'green' },
};

export const fmtDay = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU') : '—');

// datetime-local <-> ISO
export const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
export const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);
