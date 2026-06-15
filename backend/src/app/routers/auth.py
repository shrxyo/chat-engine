from fastapi import APIRouter

from app.config import get_settings
from app.dependencies import SessionDep
from app.schemas.auth import AuthSyncRequest, AuthSyncResponse
from app.services.auth import create_access_token, upsert_oauth_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sync", response_model=AuthSyncResponse)
async def sync_user(
    body: AuthSyncRequest,
    session: SessionDep,
) -> AuthSyncResponse:
    """Upsert a user from an OAuth sign-in and return a backend JWT."""
    settings = get_settings()
    user = await upsert_oauth_user(session, body)
    token = create_access_token(user, settings)
    return AuthSyncResponse(user_id=user.id, access_token=token)
