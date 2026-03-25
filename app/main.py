from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.auth import get_current_user_optional
from app.core.config import settings
from app.db import models
from app.db.database import Base, engine, get_db
from app.routers import me, post, search, tags, users
from app.schemas.schemas import PaginatedFeed, PostDetailed


@asynccontextmanager
async def lifespan(_app: FastAPI):

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(search.router, tags=["Search"])

app.include_router(users.router, tags=["Users"])

app.include_router(post.router, tags=["Posts"])

app.include_router(tags.router, tags=["Tags"])

app.include_router(me.router, tags=["Current User"])


@app.get("/", response_model=PaginatedFeed)
@app.get("/feed", response_model=PaginatedFeed)
async def get_feed(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Post)
        .where(models.Post.is_public == True)
    )
    total = count_result.scalar() or 0

    if current_user:

        followed_results = await db.execute(
            select(models.Follow.following_id).where(
                models.Follow.follower_id == current_user.id
            )
        )

        followed_user_ids = [row[0] for row in followed_results.all()]

        ranking_case = case(
            (models.Post.user_id.in_(followed_user_ids), 1),
            (models.Post.user_id == current_user.id, 2),
            else_=3,
        )

        query = (
            select(models.Post)
            .options(selectinload(models.Post.tags), selectinload(models.Post.author))
            .where(models.Post.is_public == True)
            .order_by(ranking_case, models.Post.created_at.desc())
        )

    else:

        query = (
            select(models.Post)
            .options(selectinload(models.Post.tags), selectinload(models.Post.author))
            .where(models.Post.is_public == True)
            .order_by(models.Post.created_at.desc())
        )

    result = await db.execute(query.offset(skip).limit(limit))

    posts = result.scalars().all()

    if not posts:

        return PaginatedFeed(
            posts=[], total=total, skip=skip, limit=limit, has_more=False
        )

    post_its = [post.id for post in posts]

    likes_result = await db.execute(
        select(models.Like.post_id, func.count())
        .where(models.Like.post_id.in_(post_its))
        .group_by(models.Like.post_id)
    )

    likes_count = dict(likes_result.all())

    comments_result = await db.execute(
        select(models.Comment.post_id, func.count(models.Comment.id))
        .where(models.Comment.post_id.in_(post_its))
        .group_by(models.Comment.post_id)
    )

    comments_count = dict(comments_result.all())

    bookmarks_result = await db.execute(
        select(models.Bookmark.post_id, func.count(models.Bookmark.post_id))
        .where(models.Bookmark.post_id.in_(post_its))
        .group_by(models.Bookmark.post_id)
    )

    bookmarks_count = dict(bookmarks_result.all())

    feed = []

    for post in posts:

        feed.append(
            {
                "id": post.id,
                "author": post.author,
                "title": post.title,
                "content": post.content,
                "created_at": post.created_at,
                "tags": post.tags,
                "likes_count": likes_count.get(post.id, 0),
                "comments_count": comments_count.get(post.id, 0),
                "bookmarks_count": bookmarks_count.get(post.id, 0),
            }
        )

    has_more = skip + len(posts) < total

    return PaginatedFeed(
        posts=[PostDetailed.model_validate(post) for post in feed],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handdler(
    request: Request, exception: StarletteHTTPException
):

    return await http_exception_handler(request, exception)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exception: RequestValidationError):

    return await request_validation_exception_handler(request, exception)
