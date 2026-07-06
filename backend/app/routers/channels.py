"""Каналы публикации — данные для экрана 11.10 (Этап 4).

MVP: интеграций нет, поэтому статус подключения у всех каналов — «ручной».
Экран показывает шаблон/подсказку канала, заготовку UTM, последнюю публикацию
и ошибки из лога. API-ключи/токены не хранятся и не отдаются (11.10 требование).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Publication, PublicationStatus, Role, User, VersionChannel
from ..security import require_roles

router = APIRouter(prefix="/api/channels", tags=["channels"])

can_view = require_roles(Role.content_manager, Role.manager)

# Подсказки/шаблоны каналов (6.8). UTM — заготовка source/medium под канал.
CHANNELS_META = {
    VersionChannel.site: {"name": "Сайт EFFEСOM", "connection": "manual",
                          "template": "Полная SEO-статья: H1/H2/H3, FAQ, ссылки, CTA.",
                          "utm": "utm_source=site&utm_medium=article"},
    VersionChannel.dzen: {"name": "Дзен", "connection": "manual",
                          "template": "Журнальный стиль, сильное начало, меньше SEO.",
                          "utm": "utm_source=dzen&utm_medium=social"},
    VersionChannel.vk: {"name": "VK", "connection": "manual",
                        "template": "Короткая версия: тезисы, CTA, ссылка на статью.",
                        "utm": "utm_source=vk&utm_medium=social"},
    VersionChannel.telegram: {"name": "Telegram", "connection": "manual",
                              "template": "Короткий пост: 3-5 тезисов, призыв к менеджеру.",
                              "utm": "utm_source=telegram&utm_medium=social"},
    VersionChannel.markdown: {"name": "Экспорт (MD/HTML)", "connection": "export",
                              "template": "Ручной экспорт Markdown/HTML для других площадок.",
                              "utm": "utm_source=export&utm_medium=file"},
}


@router.get("")
def list_channels(db: Session = Depends(get_db), user: User = Depends(can_view)):
    result = []
    for channel, meta in CHANNELS_META.items():
        last = db.scalar(select(Publication).where(
            Publication.channel == channel).order_by(Publication.id.desc()))
        last_error = db.scalar(select(Publication).where(
            Publication.channel == channel,
            Publication.status == PublicationStatus.error).order_by(Publication.id.desc()))
        result.append({
            "key": channel.value,
            "name": meta["name"],
            "connection": meta["connection"],   # manual | export — интеграций нет
            "template": meta["template"],
            "utm": meta["utm"],
            "last_publication": ({
                "url": last.publication_url,
                "status": last.status.value,
                "published_at": last.published_at,
            } if last else None),
            "last_error": last_error.error_log if last_error else None,
        })
    return result
