import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserCreate, UserUpdate


async def create_user(db: AsyncSession, data: UserCreate, is_superuser: bool = False) -> User:
    existing = await db.execute(
        select(User).where((User.email == data.email)
                           | (User.username == data.username))
    )
    if existing.scalar_one_or_none():
        raise ConflictException(
            "A user with this email or username already exists")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        is_superuser=is_superuser,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("User not found")
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.username and data.username != user.username:
        existing = await db.execute(select(User).where(User.username == data.username))
        if existing.scalar_one_or_none():
            raise ConflictException("Username already taken")
        user.username = data.username

    if data.full_name is not None:
        user.full_name = data.full_name

    await db.flush()
    await db.refresh(user)
    return user


async def admin_update_user(db: AsyncSession, user: User, data: UserAdminUpdate) -> User:
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_verified is not None:
        user.is_verified = data.is_verified
    if data.is_superuser is not None:
        user.is_superuser = data.is_superuser
    if data.full_name is not None:
        user.full_name = data.full_name
    await db.flush()
    await db.refresh(user)
    return user
