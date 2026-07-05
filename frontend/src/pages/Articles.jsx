import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Badge, EntityForm, Modal, Tabs } from '../components/ui';
import AIPanel from '../components/AIPanel';
import { ARTICLE_STATUS, CHANNELS, fmtDate, fromLocalInput, toLocalInput,
         VERSION_CHANNELS, VERSION_STATUS } from '../dicts';
import Hint from '../components/Hint';

const canWrite = (user) => ['admin', 'editor'].includes(user.role);
const canCheck = (user) => ['admin', 'editor', 'expert'].includes(user.role);
const canVersion = (user) => ['admin', 'editor', 'content_manager'].includes(user.role);
const canSchedule = (user) => ['admin', 'editor', 'content_manager'].includes(user.role);
// Отметить «Опубликована» может только контент-менеджер или администратор
const canMarkPublished = (user) => ['admin', 'content_manager'].includes(user.role);

/* ------------------------------------------------------- Список статей */
export function ArticlesPage({ user }) {
  const [rows, setRows] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const status = params.get('status') || '';

  const load = async () => {
    try {
      setRows(await api('/api/articles' + (status ? `?status=${status}` : '')));
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, [status]);

  const create = async (payload) => {
    const article = await api('/api/articles', { method: 'POST', body: payload });
    setCreating(false);
    navigate(`/articles/${article.id}`);
  };

  return (
    <>
      <div className="page-head">
        <h1>Статьи<Hint id="articles" /></h1>
        {canWrite(user) && <button onClick={() => setCreating(true)}>Создать черновик</button>}
      </div>
      <div className="filters">
        <select value={status} onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}>
          <option value="">Все статусы</option>
          {Object.entries(ARTICLE_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="table-wrap">
        {rows === null ? <div className="empty">Загрузка…</div>
        : rows.length === 0 ? <div className="empty">Статей нет. Создайте черновик из темы или с нуля.</div>
        : (
          <table>
            <thead>
              <tr><th>Заголовок</th><th>Канал</th><th>Статус</th><th>Чек-лист</th><th>План</th><th>Обновлена</th></tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/articles/${a.id}`}>{a.title}</Link></td>
                  <td>{CHANNELS[a.channel] || a.channel}</td>
                  <td><Badge map={ARTICLE_STATUS} value={a.status} /></td>
                  <td>{a.checklist_total ? `${a.checklist_done}/${a.checklist_total}` : '—'}</td>
                  <td>{a.planned_at ? fmtDate(a.planned_at) : '—'}</td>
                  <td>{fmtDate(a.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {creating && (
        <Modal title="Новый черновик статьи" onClose={() => setCreating(false)}>
          <EntityForm
            onCancel={() => setCreating(false)}
            onSubmit={create}
            submitLabel="Создать"
            fields={[
              { name: 'title', label: 'Заголовок', required: true, full: true },
              { name: 'channel', label: 'Основной канал', type: 'select', options: CHANNELS, default: 'site', required: true },
              { name: 'topic_id', label: 'ID темы (если есть)', type: 'number' },
            ]}
          />
        </Modal>
      )}
    </>
  );
}

/* --------------------------------------- Карточка статьи (11.7 ТЗ, Этап 2)
   Компоновка: сверху вкладки «Статья» + версии по каналам; по центру редактор;
   справа процесс, публикация, чек-лист, комментарии; снизу история. */
const EDITABLE = ['draft', 'needs_revision', 'editing'];

export function ArticlePage({ user }) {
  const { id } = useParams();
  const [article, setArticle] = useState(null);
  const [versions, setVersions] = useState([]);
  const [tab, setTab] = useState('article');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [sideRefresh, setSideRefresh] = useState(0);

  const flash = (msg) => { setNotice(msg); setError(''); };
  const fail = (e) => { setError(e.message); setNotice(''); };

  const load = async () => {
    try {
      setArticle(await api(`/api/articles/${id}`));
      setVersions(await api(`/api/articles/${id}/versions`));
    } catch (e) { fail(e); }
  };
  useEffect(() => { load(); }, [id]);

  if (error && !article) return <div className="error-box">{error}</div>;
  if (!article) return <div className="empty">Загрузка…</div>;

  const editable = canWrite(user) && (EDITABLE.includes(article.status) || user.role === 'admin');

  const save = async (payload) => {
    try {
      setArticle(await api(`/api/articles/${id}`, { method: 'PUT', body: payload }));
      flash('Изменения сохранены');
    } catch (e) { fail(e); }
  };

  const changeStatus = async (status) => {
    try {
      setArticle(await api(`/api/articles/${id}/status`, { method: 'POST', body: { status } }));
      flash(`Статус: ${ARTICLE_STATUS[status].label}`);
    } catch (e) { fail(e); }
  };

  const initVersions = async () => {
    try {
      setVersions(await api(`/api/articles/${id}/versions/init`, { method: 'POST' }));
      flash('Версии по каналам созданы — заполните их во вкладках выше');
    } catch (e) { fail(e); }
  };

  const versionByChannel = Object.fromEntries(versions.map((v) => [v.channel, v]));
  const tabs = [
    { key: 'article', label: 'Статья' },
    ...Object.entries(VERSION_CHANNELS).map(([k, label]) => ({
      key: k, label, badge: versionByChannel[k] ? (VERSION_STATUS[versionByChannel[k].status]?.label[0] ?? '') : null,
    })),
  ];

  return (
    <>
      <div className="page-head">
        <h1>{article.title}</h1>
        <Badge map={ARTICLE_STATUS} value={article.status} />
      </div>
      {error && <div className="error-box">{error}</div>}
      {notice && <div className="panel notice">{notice}</div>}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      <div className="article-grid">
        <div className="panel">
          {tab === 'article' ? (
            <>
              <h2>Редактор</h2>
              {!editable && (
                <p className="muted-text">
                  Статья в статусе «{ARTICLE_STATUS[article.status].label}» — правки закрыты.
                  Чтобы редактировать, верните её на доработку.
                </p>
              )}
              <ArticleEditor key={article.updated_at} article={article} onSave={save} disabled={!editable} />
            </>
          ) : (
            <VersionEditor key={tab + (versionByChannel[tab]?.updated_at || '')}
              articleId={id} channel={tab} version={versionByChannel[tab]}
              canEdit={canVersion(user)}
              onSaved={(v) => {
                setVersions((list) => {
                  const rest = list.filter((x) => x.channel !== v.channel);
                  return [...rest, v].sort((a, b) => a.id - b.id);
                });
                flash('Версия сохранена');
              }}
              onInit={initVersions}
            />
          )}
        </div>

        <div className="side-rail">
          <div className="panel">
            <h2>Редакционный процесс<Hint id="articles.workflow" /></h2>
            <div className="status-actions">
              {article.allowed_transitions.length === 0 && (
                <span className="muted-text">Для вашей роли переходы из текущего статуса недоступны.</span>
              )}
              {article.allowed_transitions
                .filter((s) => !(s === 'scheduled' || s === 'published')) // публикация — блоком ниже
                .map((s) => (
                  <button key={s} className="secondary" onClick={() => changeStatus(s)}>
                    → {ARTICLE_STATUS[s].label}
                  </button>
                ))}
            </div>
            {canVersion(user) && (
              <button className="secondary" style={{ marginTop: 10, width: '100%' }} onClick={initVersions}>
                Создать версии для каналов
              </button>
            )}
          </div>

          <PublishPanel user={user} article={article}
            onChanged={(a) => { setArticle(a); flash('Публикация обновлена'); }}
            onError={fail} />

          <AIPanel articleId={id} visible={canWrite(user)}
            onDone={() => { load(); setSideRefresh((n) => n + 1); }}
            onError={fail} onNotice={flash} />

          <ChecklistPanel articleId={id} canEdit={canCheck(user)}
            onError={fail} onProgress={load} refresh={sideRefresh} />

          <CommentsPanel articleId={id} user={user} onError={fail} refresh={sideRefresh} />

          <div className="panel">
            <h2>Сведения</h2>
            <p className="info-line">Основной канал: {CHANNELS[article.channel] || article.channel}</p>
            <p className="info-line">Тема: {article.topic_id ? <Link to="/topics">№{article.topic_id}</Link> : '—'}</p>
            <p className="info-line">Создана: {fmtDate(article.created_at)}</p>
            <p className="info-line">Обновлена: {fmtDate(article.updated_at)}</p>
          </div>
        </div>
      </div>

      <HistoryPanel articleId={id} refreshKey={article.updated_at + article.status} />
    </>
  );
}

/* --------------------------------------------------- Основной редактор */
function ArticleEditor({ article, onSave, disabled }) {
  const FIELDS = [
    ['title', 'Заголовок (H1) *'], ['slug', 'Slug'],
    ['seo_title', 'SEO Title'], ['seo_description', 'SEO Description'],
    ['brief', 'SEO-бриф (структура H2/H3, вопросы FAQ, CTA, источники)'],
    ['draft_text', 'Черновик'], ['final_text', 'Финальный текст'],
    ['faq', 'FAQ'], ['cta', 'CTA'],
    ['internal_links', 'Внутренние ссылки на курсы EFFEСOM'],
    ['sources_list', 'Источники'],
    ['effecom_block', 'Блок «Как EFFEСOM может помочь»'],
  ];
  const [v, setV] = useState(() =>
    Object.fromEntries(FIELDS.map(([k]) => [k, article[k] || ''])));
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }));
  const submit = (e) => {
    e.preventDefault();
    const payload = {};
    Object.entries(v).forEach(([k, val]) => { payload[k] = val === '' ? null : val; });
    onSave(payload);
  };

  const area = (k, label, tall) => (
    <label className="field full" key={k}><span>{label}</span>
      <textarea className={tall ? 'tall' : ''} value={v[k]} onChange={set(k)} /></label>
  );

  return (
    <form onSubmit={submit}>
      <fieldset disabled={disabled} style={{ border: 'none', padding: 0, margin: 0 }}>
        <div className="form-grid">
          <label className="field full"><span>Заголовок (H1) *</span>
            <input value={v.title} onChange={set('title')} required /></label>
          <label className="field"><span>Slug</span>
            <input value={v.slug} onChange={set('slug')} /></label>
          <label className="field"><span>SEO Title</span>
            <input value={v.seo_title} onChange={set('seo_title')} /></label>
          <label className="field full"><span>SEO Description</span>
            <textarea value={v.seo_description} onChange={set('seo_description')} /></label>
          {area('brief', 'SEO-бриф (структура H2/H3, вопросы FAQ, CTA, источники)')}
          {area('draft_text', 'Черновик', true)}
          {area('final_text', 'Финальный текст', true)}
          {area('faq', 'FAQ (вопрос — ответ)')}
          <label className="field full"><span>CTA</span>
            <input value={v.cta} onChange={set('cta')} /></label>
          {area('internal_links', 'Внутренние ссылки на курсы EFFEСOM (по одной на строку)')}
          {area('sources_list', 'Источники (по одному на строку)')}
          {area('effecom_block', 'Блок «Как EFFEСOM может помочь»')}
        </div>
        {!disabled && <div className="actions"><button type="submit">Сохранить изменения</button></div>}
      </fieldset>
    </form>
  );
}

/* --------------------------------------------- Редактор версии канала (6.8) */
function VersionEditor({ articleId, channel, version, canEdit, onSaved, onInit }) {
  const [title, setTitle] = useState(version?.title || '');
  const [body, setBody] = useState(version?.body || '');
  const [status, setStatus] = useState(version?.status || 'draft');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  if (!version) {
    return (
      <div className="empty">
        Версии для канала «{VERSION_CHANNELS[channel]}» ещё нет.
        {canEdit
          ? <> Нажмите <button className="secondary small" onClick={onInit}>Создать версии для каналов</button> — заготовки появятся сразу для всех каналов.</>
          : ' Создание версий доступно редактору и контент-менеджеру.'}
      </div>
    );
  }

  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try {
      const v = await api(`/api/articles/${articleId}/versions/${channel}`, {
        method: 'PUT',
        body: { title: title || null, body: body || null, status },
      });
      onSaved(v);
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={save}>
      <h2>Версия: {VERSION_CHANNELS[channel]} <Badge map={VERSION_STATUS} value={version.status} /><Hint id="articles.versions" /></h2>
      {err && <div className="error-box">{err}</div>}
      <fieldset disabled={!canEdit} style={{ border: 'none', padding: 0, margin: 0 }}>
        <div className="form-grid">
          <label className="field full"><span>Заголовок версии</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label className="field full"><span>Текст версии</span>
            <textarea className="tall" value={body} onChange={(e) => setBody(e.target.value)} /></label>
          <label className="field"><span>Статус версии</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(VERSION_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select></label>
        </div>
        {version.published_at && <p className="muted-text">Опубликована: {fmtDate(version.published_at)}</p>}
        {canEdit && <div className="actions"><button type="submit" disabled={busy}>{busy ? 'Сохранение…' : 'Сохранить версию'}</button></div>}
      </fieldset>
    </form>
  );
}

/* ----------------------------------------------- Публикация и календарь (11.8) */
function PublishPanel({ user, article, onChanged, onError }) {
  const [planned, setPlanned] = useState(toLocalInput(article.planned_at));
  const [deadline, setDeadline] = useState(toLocalInput(article.review_deadline));
  const [busy, setBusy] = useState(false);

  const allowed = article.allowed_transitions || [];
  const scheduleOk = canSchedule(user) && (allowed.includes('scheduled') || article.status === 'scheduled');
  const markOk = canMarkPublished(user) && allowed.includes('published');

  const call = async (path, body) => {
    setBusy(true);
    try { onChanged(await api(`/api/articles/${article.id}/${path}`, { method: 'POST', body })); }
    catch (e) { onError(e); } finally { setBusy(false); }
  };

  return (
    <div className="panel">
      <h2>Публикация<Hint id="articles.publish" /></h2>
      {article.planned_at && <p className="info-line">План: {fmtDate(article.planned_at)}</p>}
      {article.review_deadline && <p className="info-line">Дедлайн проверки: {fmtDate(article.review_deadline)}</p>}
      {article.published_at && <p className="info-line">Опубликована: {fmtDate(article.published_at)}</p>}

      {scheduleOk ? (
        <>
          <label className="field"><span>Дата и время публикации</span>
            <input type="datetime-local" value={planned} onChange={(e) => setPlanned(e.target.value)} /></label>
          <label className="field"><span>Дедлайн проверки (необязательно)</span>
            <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          <button className="secondary" style={{ width: '100%' }} disabled={busy || !planned}
            onClick={() => call('schedule', {
              planned_at: fromLocalInput(planned),
              review_deadline: fromLocalInput(deadline),
            })}>
            {article.status === 'scheduled' ? 'Перенести публикацию' : 'Запланировать'}
          </button>
        </>
      ) : (
        !markOk && <p className="muted-text">
          Планирование откроется в статусе «Готова к публикации» (редактор,
          контент-менеджер или администратор). Отметить «Опубликована» может
          только контент-менеджер или администратор.
        </p>
      )}

      {markOk && (
        <button style={{ width: '100%', marginTop: 8 }} disabled={busy}
          onClick={() => call('mark-published', {})}>
          Отметить опубликованной вручную
        </button>
      )}
    </div>
  );
}

/* --------------------------------------------- Чек-лист качества (6.9, 11.7) */
function ChecklistPanel({ articleId, canEdit, onError, onProgress, refresh = 0 }) {
  const [items, setItems] = useState(null);

  useEffect(() => {
    api(`/api/articles/${articleId}/checklist`).then(setItems).catch(onError);
  }, [articleId, refresh]);

  const toggle = async (item) => {
    try {
      const updated = await api(`/api/articles/${articleId}/checklist/${item.key}`, {
        method: 'PUT', body: { is_done: !item.is_done },
      });
      setItems((list) => list.map((i) => (i.key === item.key ? updated : i)));
      onProgress();
    } catch (e) { onError(e); }
  };

  if (items === null) return <div className="panel"><h2>Чек-лист качества</h2><p className="muted-text">Загрузка…</p></div>;
  const done = items.filter((i) => i.is_done).length;

  return (
    <div className="panel">
      <h2>Чек-лист качества <span className="muted-text">{done}/{items.length}</span><Hint id="articles.checklist" /></h2>
      <div className="progress"><div className="progress-bar" style={{ width: `${(done / items.length) * 100}%` }} /></div>
      <ul className="checklist">
        {items.map((i) => (
          <li key={i.key}>
            <label>
              <input type="checkbox" checked={i.is_done} disabled={!canEdit} onChange={() => toggle(i)} />
              <span className={i.is_done ? 'done' : ''}>{i.label}</span>
            </label>
            {i.is_done && i.updated_by && <small className="muted-text">— {i.updated_by}</small>}
          </li>
        ))}
      </ul>
      {done < items.length && (
        <p className="muted-text" style={{ marginBottom: 0 }}>
          Пока чек-лист не закрыт, статья не перейдёт в «Готова к публикации».
        </p>
      )}
    </div>
  );
}

/* ----------------------------------------------------- Комментарии (11.7.5) */
function CommentsPanel({ articleId, user, onError, refresh = 0 }) {
  const [comments, setComments] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => api(`/api/articles/${articleId}/comments`).then(setComments).catch(onError);
  useEffect(() => { load(); }, [articleId, refresh]);

  const add = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api(`/api/articles/${articleId}/comments`, { method: 'POST', body: { text: text.trim() } });
      setText('');
      await load();
    } catch (e2) { onError(e2); } finally { setBusy(false); }
  };

  const remove = async (c) => {
    if (!window.confirm('Удалить комментарий?')) return;
    try {
      await api(`/api/articles/${articleId}/comments/${c.id}`, { method: 'DELETE' });
      await load();
    } catch (e2) { onError(e2); }
  };

  return (
    <div className="panel">
      <h2>Комментарии<Hint id="articles.comments" /></h2>
      {comments === null ? <p className="muted-text">Загрузка…</p>
        : comments.length === 0 ? <p className="muted-text">Комментариев нет. Эксперт и редактор оставляют замечания здесь.</p>
        : (
          <div className="comments">
            {comments.map((c) => (
              <div key={c.id} className="comment">
                <div className="comment-head">
                  <b>{c.author_name}</b>
                  <span className="muted-text">{fmtDate(c.created_at)}</span>
                </div>
                <p>{c.text}</p>
                {(user.role === 'admin' || c.author_id === user.id) && (
                  <button className="danger small" onClick={() => remove(c)}>Удалить</button>
                )}
              </div>
            ))}
          </div>
        )}
      <form onSubmit={add}>
        <textarea placeholder="Новый комментарий…" value={text}
          onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="secondary" style={{ width: '100%', marginTop: 6 }}
          disabled={busy || !text.trim()}>Добавить комментарий</button>
      </form>
    </div>
  );
}

/* --------------------------------------- История изменений и публикаций */
function HistoryPanel({ articleId, refreshKey }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    api(`/api/articles/${articleId}/history`).then(setRows).catch(() => setRows([]));
  }, [articleId, refreshKey]);

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <h2>История изменений и публикаций</h2>
      {rows === null ? <p className="muted-text">Загрузка…</p>
        : rows.length === 0 ? <p className="muted-text">Записей пока нет.</p>
        : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Детали</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDate(r.created_at)}</td>
                    <td>{r.user_email || '—'}</td>
                    <td>{r.action}</td>
                    <td>{r.detail || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}
