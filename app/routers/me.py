from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing_extensions import TypeAlias

import app.db.models as models
from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.schemas.schemas import (
    Follower,
    Following,
    OwnerBookmarkView,
    OwnerCommentView,
    OwnerLikeView,
    PaginatedFollower,
    PaginatedFollowing,
    PaginatedOwnerBookmark,
    PaginatedOwnerComment,
    PaginatedOwnerLike,
    PaginatedTagView,
    TagView,
)

CurrentUser: TypeAlias = Annotated[models.User, Depends(get_current_user)]


router = APIRouter(prefix="/api")


@router.get("/me/followers", response_model=PaginatedFollower)
async def get_my_followers(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    count_result = await db.execute(
        select(func.count(models.Follow.following_id)).where(
            models.Follow.following_id == current_user.id
        )
    )

    total_followers = count_result.scalar() or 0

    result = await db.execute(
        select(models.Follow)
        .options(selectinload(models.Follow.follower_user))
        .where(models.Follow.following_id == current_user.id)
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


@router.get("/me/following", response_model=PaginatedFollowing)
async def get_my_following(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    count_result = await db.execute(
        select(func.count(models.Follow.follower_id)).where(
            models.Follow.follower_id == current_user.id
        )
    )

    total_following = count_result.scalar() or 0

    result = await db.execute(
        select(models.Follow)
        .options(selectinload(models.Follow.following_user))
        .where(models.Follow.follower_id == current_user.id)
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


# -----------------------------
# GETTING All COMMENTS DONE BY A USER
# -----------------------------
@router.get("/me/comments", response_model=PaginatedOwnerComment)
async def get_my_comments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.comment_per_page,
):

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Comment)
        .where(models.Comment.user_id == current_user.id)
    )

    total_comments = count_result.scalar() or 0

    if total_comments == 0:

        return PaginatedOwnerComment(
            comments=[], total=0, skip=skip, limit=limit, has_more=False
        )

    result = await db.execute(
        select(models.Comment)
        .where(models.Comment.user_id == current_user.id)
        .options(selectinload(models.Comment.post))
        .order_by(models.Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    comments = result.scalars().all()

    has_more = skip + len(comments) < total_comments

    return PaginatedOwnerComment(
        comments=[OwnerCommentView.model_validate(comment) for comment in comments],
        total=total_comments,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# GETTING ALL THE BOOKMARKS FOR AN USER
# -----------------------------
@router.get("/me/bookmarks", response_model=PaginatedOwnerBookmark)
async def get_my_bookmarks(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    bookmark_result = await db.execute(
        select(func.count(models.Bookmark.post_id)).where(
            models.Bookmark.user_id == current_user.id
        )
    )

    total_bookmarks = bookmark_result.scalar() or 0

    if total_bookmarks == 0:
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="No Bookmarks Found",
        # )

        return PaginatedOwnerBookmark(
            bookmarks=[], total=0, skip=skip, limit=limit, has_more=False
        )

    result = await db.execute(
        select(models.Bookmark)
        .where(models.Bookmark.user_id == current_user.id)
        .options(selectinload(models.Bookmark.post))
        .order_by(models.Bookmark.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    bookmarks = result.scalars().all()

    has_more = skip + len(bookmarks) < total_bookmarks

    return PaginatedOwnerBookmark(
        bookmarks=[
            OwnerBookmarkView.model_validate(bookmark) for bookmark in bookmarks
        ],
        total=total_bookmarks,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# GETTING LIKES FOR AN ITEM
# -----------------------------


@router.get("/me/likes", response_model=PaginatedOwnerLike)
async def get_my_likes(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    like_result = await db.execute(
        select(func.count()).where(models.Like.user_id == current_user.id)
    )

    total_likes = like_result.scalar() or 0

    if total_likes == 0:
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail="Item not found",
        # )

        return PaginatedOwnerLike(
            likes=[], total=0, skip=skip, limit=limit, has_more=False
        )

    result = await db.execute(
        select(models.Like)
        .where(models.Like.user_id == current_user.id)
        .options(selectinload(models.Like.post))
        .order_by(models.Like.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    likes = result.scalars().all()

    has_more = skip + len(likes) < total_likes

    return PaginatedOwnerLike(
        likes=[OwnerLikeView.model_validate(like) for like in likes],
        total=total_likes,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# GETTING ALL THE TAGS CREATED BY THE CURRENT USER
# -----------------------------
@router.get("/me/tags", response_model=PaginatedTagView)
async def get_my_tags(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.post_per_page,
):

    count_result = await db.execute(
        select(func.count(models.Tag.id)).where(
            models.Tag.creator_id == current_user.id
        )
    )
    tags_count = count_result.scalar() or 0

    if tags_count == 0:

        return PaginatedTagView(
            tags=[], total=0, skip=skip, limit=limit, has_more=False
        )

    tags_result = await db.execute(
        select(models.Tag)
        .where(models.Tag.creator_id == current_user.id)
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
