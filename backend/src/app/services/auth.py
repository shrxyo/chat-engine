from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.user import User
from app.schemas.auth import AuthSyncRequest


def create_access_token(user: User, settings: Settings) -> str:
    """Mint a signed JWT with sub, email, and name for API/WebSocket auth."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def upsert_oauth_user(session: AsyncSession, body: AuthSyncRequest) -> User:
    """Find or create a user by OAuth provider identity, updating profile fields."""
    result = await session.execute(
        select(User).where(
            User.provider == body.provider,
            User.provider_id == body.provider_id,
        )
    )
    user = result.scalars().first()

    if user is None:
        result = await session.execute(select(User).where(User.email == body.email))
        user = result.scalars().first()

    now = datetime.now(UTC).replace(tzinfo=None)

    if user is None:
        user = User(
            email=body.email,
            name=body.name,
            avatar_url=body.avatar_url,
            provider=body.provider,
            provider_id=body.provider_id,
        )
        session.add(user)
    else:
        user.email = body.email
        user.name = body.name
        user.avatar_url = body.avatar_url
        user.provider = body.provider
        user.provider_id = body.provider_id
        user.updated_at = now
        session.add(user)

    await session.commit()
    await session.refresh(user)
    return user
