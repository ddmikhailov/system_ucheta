"""«Мой день» (этап 6): сводка внимания для куратора. Любой вошедший пользователь видит
только своё — группы берутся из его назначений (`get_curator_group_ids`), поэтому ролевой проверки нет."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.my_day import MyDay
from app.services import my_day_service

router = APIRouter(prefix="/my-day", tags=["my-day"])


@router.get("", response_model=MyDay)
def my_day(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return my_day_service.build_my_day(db, user)


@router.get("/counters")
def nav_counters(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    """Числа на пунктах меню — запрашиваются при каждом переходе, поэтому только подсчёт без списков."""
    return my_day_service.nav_counters(db, user)
