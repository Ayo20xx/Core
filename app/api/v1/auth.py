from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.core.exceptions import EmailException
from app.schemas.user import UsersCreate, UsersRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UsersRead, status_code=201)
async def register(session: SessionDep, body: UsersCreate) -> UsersRead:
    service = AuthService()
    try:
        user = await service.register(session, body)
    except EmailException as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc

    return UsersRead.model_validate(user)
