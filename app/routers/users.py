from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing_extensions import TypeAlias

# from db.models import models
import app.db.models as models
from app.core.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.db.database import get_db
from app.schemas.schemas import (
    Follow,
    Follower,
    Following,
    PaginatedFollower,
    PaginatedFollowing,
    PaginatedTagView,
    TagView,
    Token,
    UserCreate,
    UserMe,
    UserPublic,
    UserUpdate,
)

CurrentUser: TypeAlias = Annotated[models.User, Depends(get_current_user)]


router = APIRouter(prefix="/api/users")


# login and get a token
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == form_data.username.lower()
        )
    )

    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    return Token(access_token=access_token, token_type="bearer")


# craete a new user
@router.post("", response_model=UserMe, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):

    result_user = await db.execute(
        select(models.User).where(
            func.lower(models.User.username) == user.username.lower()
        )
    )

    existing_user = result_user.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    result_email = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_email = result_email.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists"
        )

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.get("/me", response_model=UserMe)
async def get_current_user(current_user: CurrentUser):
    return current_user


# get a user by user_id


@router.get("/{user_id}", response_model=UserPublic)
async def get_user_by_id(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    result_user = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result_user.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found !"
        )

    return user


@router.get("", response_model=list[UserPublic])
async def get_all_users(db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(select(models.User))
    users = result.scalars().all()

    return users


@router.patch("/{user_id}", response_model=UserMe)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    if user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this user"
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updated = False

    if user_data.username:
        new_username = user_data.username.lower()

        if new_username != user.username.lower():
            exists = await db.scalar(
                select(func.count())
                .select_from(models.User)
                .where(func.lower(models.User.username) == new_username)
            )

            if exists:
                raise HTTPException(400, "Username already exists")

            user.username = new_username
            updated = True

    if user_data.email:
        new_email = user_data.email.lower()

        if new_email != user.email.lower():
            exists = await db.scalar(
                select(func.count())
                .select_from(models.User)
                .where(func.lower(models.User.email) == new_email)
            )

            if exists:
                raise HTTPException(400, "Email already exists")

            user.email = new_email
            updated = True

    if user_data.bio:

        if user_data.bio != current_user.bio:

            user.bio = user_data.bio
            updated = True

    if not updated:
        raise HTTPException(400, "No changes provided")

    await db.commit()
    await db.refresh(user)

    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not Authorized to delete the User",
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    await db.delete(user)
    await db.commit()


@router.post(
    "/{user_id}/follow", status_code=status.HTTP_201_CREATED, response_model=Follow
)
async def follow(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    existing_follow = await db.execute(
        select(models.Follow).where(
            models.Follow.follower_id == current_user.id,
            models.Follow.following_id == user_id,
        )
    )

    if existing_follow.scalar():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Follow already exists"
        )

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself"
        )

    new_follow = models.Follow(follower_id=current_user.id, following_id=user_id)

    db.add(new_follow)
    await db.commit()
    await db.refresh(new_follow, attribute_names=["following_user"])

    return Follow(
        follower_user=current_user,
        following_user=new_follow.following_user,
        created_at=new_follow.created_at,
        is_following=True,
    )


@router.delete("/{user_id}/follow", response_model=Follow)
async def unfollow(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    result = await db.execute(
        select(models.Follow)
        .options(selectinload(models.Follow.following_user))
        .where(
            models.Follow.follower_id == current_user.id,
            models.Follow.following_id == user_id,
        )
    )

    existing_follow = result.scalars().first()

    if not existing_follow:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Follow Dosent Exists"
        )

    await db.delete(existing_follow)
    await db.commit()

    return Follow(
        follower_user=current_user,
        following_user=existing_follow.following_user,
        is_following=False,
    )


@router.get("/{user_id}/followers", response_model=PaginatedFollower)
async def get_followers_for_a_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    count_result = await db.execute(
        select(func.count(models.Follow.following_id)).where(
            models.Follow.following_id == user_id
        )
    )

    total_followers = count_result.scalar() or 0

    result = await db.execute(
        select(models.Follow)
        .options(selectinload(models.Follow.follower_user))
        .where(models.Follow.following_id == user_id)
        .order_by(models.Follow.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    followers = result.scalars().all()

    has_more = skip + len(followers) < total_followers

    return PaginatedFollower(
        follower=[Follower.model_validate(follower) for follower in followers],
        total=total_followers,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{user_id}/following", response_model=PaginatedFollowing)
async def get_following_for_a_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    count_result = await db.execute(
        select(func.count(models.Follow.follower_id)).where(
            models.Follow.follower_id == user_id
        )
    )

    total_following = count_result.scalar() or 0

    result = await db.execute(
        select(models.Follow)
        .options(selectinload(models.Follow.following_user))
        .where(models.Follow.follower_id == user_id)
        .order_by(models.Follow.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    following = result.scalars().all()

    has_more = skip + len(following) < total_following

    return PaginatedFollowing(
        following=[
            Following.model_validate(following_user) for following_user in following
        ],
        total=total_following,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{user_id}/tags")
async def get_tags_of_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user dosen't exists"
        )

    count_result = await db.execute(
        select(func.count(models.Tag.id)).where(models.Tag.creator_id == user_id)
    )
    tags_count = count_result.scalar() or 0

    if tags_count == 0:

        return PaginatedTagView(
            tags=[], total=0, skip=skip, limit=limit, has_more=False
        )

    tags_result = await db.execute(
        select(models.Tag)
        .where(models.Tag.creator_id == user_id)
        .offset(skip)
        .limit(limit)
    )

    tags = tags_result.scalars().all()

    has_more = skip + len(tags) < tags_count

    return PaginatedTagView(
        tags=[TagView.model_validate(tag) for tag in tags],
        total=tags_count,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
