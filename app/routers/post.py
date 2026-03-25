from datetime import UTC, datetime
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
    BookmarkedPostView,
    BookmarkView,
    CommentCreate,
    CommentedPostView,
    CommentView,
    LikedPostView,
    LikeView,
    PaginatedBookmark,
    PaginatedComment,
    PaginatedLike,
    PaginatedVersionResponse,
    PostCreate,
    PostOwnerView,
    PostUpdate,
    PostUpdatedView,
    VersionResponse,
    VisibilityUpdate,
    VisibilityUpdatedView,
)

CurrentUser: TypeAlias = Annotated[models.User, Depends(get_current_user)]

router = APIRouter(prefix="/api/posts")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PostOwnerView)
async def create_post(
    post_data: PostCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    result = await db.execute(
        select(models.Post).where(
            func.lower(models.Post.title) == post_data.title.lower(),
            models.Post.user_id == current_user.id,
        )
    )

    existing_post = result.scalars().first()

    if existing_post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post with same title already exists",
        )

    new_post = models.Post(
        title=post_data.title,
        content=post_data.content,
        is_public=post_data.is_public,
        user_id=current_user.id,
    )

    if post_data.tag_ids:

        result = await db.execute(
            select(models.Tag).where(models.Tag.id.in_(post_data.tag_ids))
        )

        tags = result.scalars().all()

        if len(tags) != len(post_data.tag_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="some tags are invalid"
            )

        new_post.tags = tags

    db.add(new_post)
    await db.commit()

    version = models.Version(
        post_id=new_post.id,
        version_number=1,
        title=new_post.title,
        content=new_post.content,
    )

    db.add(version)
    await db.commit()

    # pre-loading the tags for return object
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags), selectinload(models.Post.author))
        .where(models.Post.id == new_post.id)
    )

    new_post = result.scalars().first()

    return PostOwnerView(
        id=new_post.id,
        author=new_post.author,
        title=new_post.title,
        content=new_post.content,
        created_at=new_post.created_at,
        tags=new_post.tags,
        likes_count=0,
        comments_count=0,
        bookmarks_count=0,
        version_count=1,
        is_public=new_post.is_public,
    )


@router.get("/{post_id}", response_model=PostOwnerView)
async def get_post_by_id(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags), selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )

    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Post dosent exists"
        )

    if post.is_public == False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the post",
        )

    # the counts

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == post_id)
    )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.post_id == post_id)
    )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.post_id)).where(
            models.Bookmark.post_id == post_id
        )
    )

    versions_count = await db.scalar(
        select(func.count(models.Version.id)).where(models.Version.post_id == post_id)
    )

    return PostOwnerView(
        id=post_id,
        author=post.author,
        title=post.title,
        content=post.content,
        is_public=post.is_public,
        created_at=post.created_at,
        tags=post.tags,
        likes_count=likes_count,
        comments_count=comments_count,
        bookmarks_count=bookmarks_count,
        version_count=versions_count,
    )


@router.patch(
    "/{post_id}", status_code=status.HTTP_200_OK, response_model=PostUpdatedView
)
async def update_post(
    post_id: int,
    data: PostUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags))
        .where(models.Post.id == post_id)
    )

    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Post",
        )

    latest_version = await db.scalar(
        select(func.max(models.Version.version_number)).where(
            models.Version.post_id == post_id
        )
    )

    latest_version = latest_version or 0

    if data.content == post.content and data.title == post.title and not data.tag_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't update the post with same content or title",
        )

    updated = False

    if data.tag_ids:

        existing_tag_ids = {tag.id for tag in post.tags}
        incoming_tag_ids = set(data.tag_ids)

        new_tag_ids = incoming_tag_ids - existing_tag_ids

        if new_tag_ids:
            tag_result = await db.execute(
                select(models.Tag).where(models.Tag.id.in_(new_tag_ids))
            )
            new_tags = tag_result.scalars().all()

            # append only once
            post.tags.extend(new_tags)
            updated = True

    if data.title and data.title != post.title:
        post.title = data.title
        updated = True

    if data.content and data.content != post.content:
        post.content = data.content
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No changes detected")

    new_version = models.Version(
        post_id=post_id,
        version_number=latest_version + 1,
        title=post.title,
        content=post.content,
    )

    db.add(new_version)
    await db.commit()

    await db.refresh(post)
    await db.refresh(new_version)

    return PostUpdatedView(
        id=post_id,
        title=post.title,
        content=post.content,
        tags=post.tags,
        version_number=new_version.version_number,
        created_at=post.created_at,
        updated_at=new_version.updated_at,
    )


@router.patch("/{post_id}/visibility", response_model=VisibilityUpdatedView)
async def update_post_visibility(
    post_id: int,
    data: VisibilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags))
        .where(models.Post.id == post_id)
    )

    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Post",
        )

    if data.is_public == post.is_public:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Post Visibility already set to {post.is_public}",
        )

    post.is_public = data.is_public

    await db.commit()
    await db.refresh(post)

    return VisibilityUpdatedView(id=post_id, is_public=post.is_public)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Post",
        )

    await db.delete(post)
    await db.commit()


# -----------------------------
# GETTING LIKES FOR AN post
# -----------------------------


@router.get("/{post_id}/likes", response_model=PaginatedLike)
async def get_post_likes(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    like_result = await db.execute(
        select(func.count()).where(models.Like.post_id == post_id)
    )

    total_likes = like_result.scalar() or 0

    result = await db.execute(
        select(models.Like)
        .where(models.Like.post_id == post_id)
        .options(selectinload(models.Like.user))
        .order_by(models.Like.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    likes = result.scalars().all()

    has_more = skip + len(likes) < total_likes

    return PaginatedLike(
        post_id=post_id,
        likes=[LikeView.model_validate(like) for like in likes],
        total=total_likes,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# CREATING A LIKE FOR AN post
# -----------------------------
@router.post(
    "/{post_id}/likes",
    status_code=status.HTTP_201_CREATED,
    response_model=LikedPostView,
)
async def add_post_like(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    like_result = await db.execute(
        select(models.Like).where(
            models.Like.user_id == current_user.id, models.Like.post_id == post_id
        )
    )

    existing_like = like_result.scalars().first()

    if existing_like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Post already liked"
        )

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == post_id)
    )

    like = models.Like(user_id=current_user.id, post_id=post_id)

    db.add(like)
    await db.commit()
    db.refresh(like)

    return LikedPostView(
        user=current_user,
        post_id=post_id,
        is_liked=True,
        created_at=like.created_at,
        likes_count=likes_count + 1,
    )


# -----------------------------
# REMOVING LIKE FROM AN post
# -----------------------------
@router.delete("/{post_id}/likes", response_model=LikedPostView)
async def remove_post_like(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    existing_like = await db.execute(
        select(models.Like).where(
            models.Like.user_id == current_user.id, models.Like.post_id == post_id
        )
    )

    like = existing_like.scalars().first()

    if not like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Post is not Liked"
        )

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == post_id)
    )

    await db.delete(like)
    await db.commit()

    return LikedPostView(
        post_id=post_id,
        user=current_user,
        is_liked=False,
        created_at=datetime.now(UTC),
        likes_count=likes_count - 1,
    )


# -----------------------------
# GETTING COMMENTS FOR AN post
# -----------------------------
@router.get("/{post_id}/comments", response_model=PaginatedComment)
async def get_comments_for_post(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.comment_per_page,
):

    result = await db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Comment)
        .where(models.Comment.post_id == post_id)
    )

    total_comments = count_result.scalar() or 0

    result = await db.execute(
        select(models.Comment)
        .where(models.Comment.post_id == post_id)
        .options(selectinload(models.Comment.user))
        .order_by(models.Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    comments = result.scalars().all()

    has_more = skip + len(comments) < total_comments

    return PaginatedComment(
        comments=[CommentView.model_validate(comment) for comment in comments],
        total=total_comments,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# ----------------------
# COMMENTING ON AN post
# ----------------------


@router.post(
    "/{post_id}/comments",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentedPostView,
)
async def add_post_comment(
    post_id: int,
    data: CommentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.post_id == post_id)
    )

    comment = models.Comment(
        user_id=current_user.id, content=data.content, post_id=post_id
    )

    db.add(comment)
    await db.commit()
    db.refresh(comment)

    return CommentedPostView(
        id=comment.id,
        user=current_user,
        post_id=post_id,
        is_commented=True,
        content=comment.content,
        created_at=comment.created_at,
        comments_count=comments_count + 1,
    )


# ----------------------
# UNCOMMENTING ON AN post - deleting a comment
# ----------------------


@router.delete("/{post_id}/comments/{comment_id}", response_model=CommentedPostView)
async def delete_post_comment(
    post_id: int,
    comment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    existing_comment = await db.execute(
        select(models.Comment).where(
            models.Comment.id == comment_id,
            models.Comment.user_id == current_user.id,
            models.Comment.post_id == post_id,
        )
    )

    comment = existing_comment.scalars().first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Comment Dosent Exists"
        )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.post_id == post_id)
    )

    await db.delete(comment)
    await db.commit()

    return CommentedPostView(
        post_id=post_id,
        user=current_user,
        is_commented=False,
        comments_count=comments_count - 1,
    )


# -----------------------------
# GETTING BOOKMARKS FOR AN post
# -----------------------------
@router.get("/{post_id}/bookmarks", response_model=PaginatedBookmark)
async def get_post_bookmarks(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post Not Found",
        )

    bookmark_result = await db.execute(
        select(func.count(models.Bookmark.post_id)).where(
            models.Bookmark.post_id == post_id
        )
    )

    total_bookmarks = bookmark_result.scalar() or 0

    result = await db.execute(
        select(models.Bookmark)
        .where(models.Bookmark.post_id == post_id)
        .options(selectinload(models.Bookmark.user))
        .order_by(models.Bookmark.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    bookmarks = result.scalars().all()

    has_more = skip + len(bookmarks) < total_bookmarks

    return PaginatedBookmark(
        bookmarks=[BookmarkView.model_validate(bookmark) for bookmark in bookmarks],
        total=total_bookmarks,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# BOOKMARKING AN post - creating bookmark
# -----------------------------
@router.post(
    "/{post_id}/bookmarks",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkedPostView,
)
async def add_post_bookmark(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    result = await db.execute(
        select(models.Bookmark).where(
            models.Bookmark.user_id == current_user.id,
            models.Bookmark.post_id == post_id,
        )
    )

    existing_bookmark = result.scalars().first()

    if existing_bookmark:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Post Already Bookmarked"
        )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.post_id)).where(
            models.Bookmark.post_id == post_id
        )
    )

    bookmark = models.Bookmark(user_id=current_user.id, post_id=post_id)

    db.add(bookmark)
    await db.commit()
    db.refresh(bookmark)

    return BookmarkedPostView(
        post_id=post_id,
        user=current_user,
        is_bookmarked=True,
        created_at=bookmark.created_at,
        bookmarks_count=bookmarks_count + 1,
    )


# -----------------------------
# DELETING BOOKMARK FROM AN post
# -----------------------------
@router.delete("/{post_id}/bookmarks", response_model=BookmarkedPostView)
async def remove_post_bookmark(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    post_result = await db.execute(
        select(models.Post.id).where(models.Post.id == post_id)
    )

    post = post_result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post Not Found",
        )

    existing_bookmark = await db.execute(
        select(models.Bookmark).where(
            models.Bookmark.user_id == current_user.id,
            models.Bookmark.post_id == post_id,
        )
    )

    bookmark = existing_bookmark.scalars().first()

    if not bookmark:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Post Not Bookmarked"
        )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.post_id)).where(
            models.Bookmark.post_id == post_id
        )
    )

    await db.delete(bookmark)
    await db.commit()

    return BookmarkedPostView(
        post_id=post_id,
        user=current_user,
        is_bookmarked=False,
        bookmarks_count=bookmarks_count - 1,
    )


@router.get("/{post_id}/versions", response_model=PaginatedVersionResponse)
async def get_post_versions(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 10,
):

    # check post exists
    result = await db.execute(select(models.Post.id).where(models.Post.id == post_id))
    if not result.scalar():
        raise HTTPException(status_code=404, detail="Post Not Found")

    # count
    count_result = await db.execute(
        select(func.count(models.Version.id)).where(models.Version.post_id == post_id)
    )
    total = count_result.scalar() or 0

    # fetch versions
    result = await db.execute(
        select(models.Version)
        .where(models.Version.post_id == post_id)
        .order_by(models.Version.version_number.desc())
        .offset(skip)
        .limit(limit)
    )

    versions = result.scalars().all()

    has_more = skip + len(versions) < total

    return PaginatedVersionResponse(
        versions=[VersionResponse.model_validate(v) for v in versions],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
