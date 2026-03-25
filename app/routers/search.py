from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing_extensions import TypeAlias

import app.db.models as models
from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.schemas.schemas import PaginatedPostSearch, PaginatedUsernameSearch, PostMini
from app.schemas.schemas import UserPublic as userpublic

CurrentUser: TypeAlias = Annotated[models.User, Depends(get_current_user)]

router = APIRouter(prefix="/api")


# --------------------------------
# SEARCH FOR A USER WITH USERNAME
# --------------------------------
@router.get("/user/search", response_model=PaginatedUsernameSearch)
async def search_user_by_username(
    username: Annotated[str, Query(min_length=1, max_length=20)],
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.users_per_page,
):

    count_result = await db.execute(
        select(func.count(models.User.id)).where(
            models.User.username.ilike(f"%{username}%")
        )
    )

    total_users = count_result.scalar() or 0

    if total_users == 0:

        return PaginatedUsernameSearch(
            users=[], total=0, skip=skip, limit=limit, has_more=False
        )

    result = await db.execute(
        select(models.User)
        .where(models.User.username.ilike(f"%{username}%"))
        .order_by(models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    users = result.scalars().all()

    has_more = skip + len(users) < total_users

    return PaginatedUsernameSearch(
        users=[userpublic.model_validate(user) for user in users],
        total=total_users,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get("/posts/search", response_model=PaginatedPostSearch)
async def search_posts(
    title: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    tags: str | None = None,
    current_user: CurrentUser = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.users_per_page,
):

    query = select(models.Post)

    if title:
        query = query.where(models.Post.title.ilike(f"%{title}%"))

    if tags:
        tag_list = tags.split(",")
        tag_list = [t.strip().lower() for t in tag_list]

        query = query.join(models.Post.tags)
        query = query.where(func.lower(models.Tag.name).in_(tag_list))
        query = query.group_by(models.Post.id)

    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_posts = count_result.scalar() or 0

    if total_posts == 0:
        return PaginatedPostSearch(
            posts=[], total=0, skip=skip, limit=limit, has_more=False
        )

    query = query.options(
        selectinload(models.Post.tags), selectinload(models.Post.author)
    )

    query = query.order_by(models.Post.created_at.desc())
    query = query.offset(skip)
    query = query.limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    has_more = skip + len(posts) < total_posts

    return PaginatedPostSearch(
        posts=[PostMini.model_validate(post) for post in posts],
        total=total_posts,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
