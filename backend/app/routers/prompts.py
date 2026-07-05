"""Редактируемые промпты (разделы 11.12 и 12 ТЗ; Этап 3).

- чтение: все авторизованные роли (промпты не содержат секретов);
- изменение и тестовый запуск: редактор и администратор;
- при каждом изменении версия увеличивается, прежний и новый тексты
  сохраняются в истории; удаления версий нет вообще — это строже,
  чем требование 11.12 («нельзя удалять без прав администратора»).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import AIError, ai_configured, generate
from ..audit import log_action
from ..database import get_db
from ..models import AIRequest, AIRequestStatus, Prompt, PromptVersion, Role, User
from ..prompts_seed import SYSTEM_PROMPT
from ..schemas import PromptOut, PromptTestIn, PromptUpdate, PromptVersionOut
from ..security import client_ip, get_current_user, require_roles
from .ai import _check_budget

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

can_edit = require_roles(Role.editor)


def _get(db: Session, key: str) -> Prompt:
    prompt = db.scalar(select(Prompt).where(Prompt.key == key))
    if prompt is None:
        raise HTTPException(404, "Промпт не найден")
    return prompt


@router.get("", response_model=list[PromptOut])
def list_prompts(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return db.scalars(select(Prompt).order_by(Prompt.key)).all()


@router.get("/{key}", response_model=PromptOut)
def get_prompt(key: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return _get(db, key)


@router.get("/{key}/versions", response_model=list[PromptVersionOut])
def prompt_versions(key: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    prompt = _get(db, key)
    return db.scalars(select(PromptVersion)
                      .where(PromptVersion.prompt_id == prompt.id)
                      .order_by(PromptVersion.version.desc())).all()


@router.put("/{key}", response_model=PromptOut)
def update_prompt(key: str, data: PromptUpdate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(can_edit)):
    prompt = _get(db, key)
    changed = False
    for field in ("name", "purpose", "variables"):
        value = getattr(data, field)
        if value is not None and value != getattr(prompt, field):
            setattr(prompt, field, value)
            changed = True
    if data.template is not None and data.template != prompt.template:
        prompt.template = data.template
        prompt.version += 1
        db.add(PromptVersion(prompt_id=prompt.id, version=prompt.version,
                             template=data.template, author=user.name))
        changed = True
    if not changed:
        return prompt
    prompt.updated_by = user.name
    db.commit()
    db.refresh(prompt)
    log_action(db, user=user, action="update", entity="prompt", entity_id=prompt.id,
               detail=f"Промпт «{prompt.key}» → версия {prompt.version}",
               ip=client_ip(request))
    return prompt


@router.post("/{key}/test")
def test_prompt(key: str, data: PromptTestIn, request: Request,
                db: Session = Depends(get_db),
                user: User = Depends(can_edit)):
    """Тестовый запуск (11.12.8): рендер шаблона на переданных переменных
    и один запрос к AI. Результат никуда не сохраняется."""
    prompt = _get(db, key)

    class _Safe(dict):
        def __missing__(self, k):
            return f"{{{k}}}"          # неподставленные переменные видны в рендере

    rendered = prompt.template.format_map(_Safe(dict(data.variables)))
    if not ai_configured():
        return {"rendered": rendered, "result": None,
                "detail": "AI не настроен — показан только рендер шаблона"}
    # Бюджетные лимиты (14.11.7) действуют и на тестовые запуски:
    # при превышении пишется запись budget_denied и возвращается 409.
    _check_budget(db, user, "prompt_test", None, None)
    record = AIRequest(kind="prompt_test", prompt_key=prompt.key,
                       prompt_version=prompt.version, created_by_email=user.email)
    try:
        result = generate(SYSTEM_PROMPT, rendered, max_tokens=1500)
    except AIError as exc:
        record.status = AIRequestStatus.error
        record.error = str(exc)
        db.add(record)
        db.commit()
        raise HTTPException(502, str(exc))
    record.provider = result.provider
    record.model = result.model
    record.input_tokens = result.input_tokens
    record.output_tokens = result.output_tokens
    record.cost_usd = result.cost_usd
    db.add(record)
    db.commit()
    log_action(db, user=user, action="ai_test", entity="prompt", entity_id=prompt.id,
               detail=f"Тестовый запуск «{prompt.key}»", ip=client_ip(request))
    return {"rendered": rendered, "result": result.text,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens}
