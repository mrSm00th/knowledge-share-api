from datetime import UTC, datetime
from typing import Annotated

import models
from auth import CurrentUser
from config import settings
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status
from schemas.schemas import (
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/items")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PostOwnerView)
async def create_post(
    item_data: PostCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    result = await db.execute(
        select(models.Post).where(
            func.lower(models.Post.title) == item_data.title.lower(),
            models.Post.user_id == current_user.id,
        )
    )

    existing_item = result.scalars().first()

    if existing_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item with same title already exists",
        )

    new_item = models.Post(
        title=item_data.title,
        content=item_data.content,
        is_public=item_data.is_public,
        user_id=current_user.id,
    )

    if item_data.tag_ids:

        result = await db.execute(
            select(models.Tag).where(models.Tag.id.in_(item_data.tag_ids))
        )

        tags = result.scalars().all()

        if len(tags) != len(item_data.tag_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="some tags are invalid"
            )

        new_item.tags = tags

    db.add(new_item)
    await db.commit()

    # adding the frist version

    version = models.Version(
        item_id=new_item.id,
        version_number=1,
        title=new_item.title,
        content=new_item.content,
    )

    db.add(version)
    await db.commit()

    # pre-loading the tags for return object
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags), selectinload(models.Post.author))
        .where(models.Post.id == new_item.id)
    )

    new_item = result.scalars().first()

    return PostOwnerView(
        id=new_item.id,
        author=new_item.author,
        title=new_item.title,
        content=new_item.content,
        created_at=new_item.created_at,
        tags=new_item.tags,
        likes_count=0,
        comments_count=0,
        bookmarks_count=0,
        version_count=1,
        is_public=new_item.is_public,
    )


@router.get("/{item_id}", response_model=PostOwnerView)
async def get_post(item_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags), selectinload(models.Post.author))
        .where(models.Post.id == item_id)
    )

    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item dosent exists"
        )

    if item.is_public == False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the post",
        )

    # the counts

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == item_id)
    )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.item_id == item_id)
    )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.item_id)).where(
            models.Bookmark.item_id == item_id
        )
    )

    versions_count = await db.scalar(
        select(func.count(models.Version.id)).where(models.Version.item_id == item_id)
    )

    return PostOwnerView(
        id=item_id,
        author=item.author,
        title=item.title,
        content=item.content,
        is_public=item.is_public,
        created_at=item.created_at,
        tags=item.tags,
        likes_count=likes_count,
        comments_count=comments_count,
        bookmarks_count=bookmarks_count,
        version_count=versions_count,
    )


@router.patch(
    "/{item_id}", status_code=status.HTTP_200_OK, response_model=PostUpdatedView
)
async def update_item(
    item_id: int,
    data: PostUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags))
        .where(models.Post.id == item_id)
    )

    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Item",
        )

    latest_version = await db.scalar(
        select(func.max(models.Version.version_number)).where(
            models.Version.item_id == item_id
        )
    )

    latest_version = latest_version or 0

    if data.content == item.content and data.title == item.title and not data.tag_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't update the item with same content or title",
        )

    updated = False

    if data.tag_ids:

        existing_tag_ids = {tag.id for tag in item.tags}
        incoming_tag_ids = set(data.tag_ids)

        new_tag_ids = incoming_tag_ids - existing_tag_ids

        if new_tag_ids:
            tag_result = await db.execute(
                select(models.Tag).where(models.Tag.id.in_(new_tag_ids))
            )
            new_tags = tag_result.scalars().all()

            # append only once
            item.tags.extend(new_tags)
            updated = True

    if data.title and data.title != item.title:
        item.title = data.title
        updated = True

    if data.content and data.content != item.content:
        item.content = data.content
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No changes detected")

    new_version = models.Version(
        item_id=item_id,
        version_number=latest_version + 1,
        title=item.title,
        content=item.content,
    )

    db.add(new_version)
    await db.commit()

    await db.refresh(item)
    await db.refresh(new_version)

    return PostUpdatedView(
        id=item_id,
        title=item.title,
        content=item.content,
        tags=item.tags,
        version_number=new_version.version_number,
        created_at=item.created_at,
        updated_at=new_version.updated_at,
    )


@router.patch("/{item_id}/Visibility", response_model=VisibilityUpdatedView)
async def update_item_visibility(
    item_id: int,
    data: VisibilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.tags))
        .where(models.Post.id == item_id)
    )

    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Item",
        )

    if data.is_public == item.is_public:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item Visibility already set to {item.is_public}",
        )

    item.is_public = data.is_public

    await db.commit()
    await db.refresh(item)

    return VisibilityUpdatedView(id=item_id, is_public=item.is_public)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(models.Post).where(models.Post.id == item_id))

    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access the Item",
        )

    await db.delete(item)
    await db.commit()


# -----------------------------
# GETTING LIKES FOR AN ITEM
# -----------------------------


@router.get("/{item_id}/likes", response_model=PaginatedLike)
async def get_likes_by_id(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    like_result = await db.execute(
        select(func.count()).where(models.Like.post_id == item_id)
    )

    total_likes = like_result.scalar() or 0

    result = await db.execute(
        select(models.Like)
        .where(models.Like.post_id == item_id)
        .options(selectinload(models.Like.user))
        .order_by(models.Like.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    likes = result.scalars().all()

    has_more = skip + len(likes) < total_likes

    return PaginatedLike(
        item_id=item_id,
        likes=[LikeView.model_validate(like) for like in likes],
        total=total_likes,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# -----------------------------
# CREATING A LIKE FOR AN ITEM
# -----------------------------
@router.post(
    "/{item_id}/like", status_code=status.HTTP_201_CREATED, response_model=LikedPostView
)
async def like_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    like_result = await db.execute(
        select(models.Like).where(
            models.Like.user_id == current_user.id, models.Like.post_id == item_id
        )
    )

    existing_like = like_result.scalars().first()

    if existing_like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item already liked"
        )
    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == item_id)
    )

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == item_id)
    )

    like = models.Like(user_id=current_user.id, item_id=item_id)

    db.add(like)
    await db.commit()
    db.refresh(like)

    return LikedPostView(
        user=current_user,
        post_id=item_id,
        is_liked=True,
        created_at=like.created_at,
        likes_count=likes_count + 1,
    )


# -----------------------------
# REMOVING LIKE FROM AN ITEM
# -----------------------------
@router.delete("/{item_id}/like", response_model=LikedPostView)
async def unlike_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    existing_like = await db.execute(
        select(models.Like).where(
            models.Like.user_id == current_user.id, models.Like.post_id == item_id
        )
    )

    like = existing_like.scalars().first()

    if not like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item is not Liked"
        )

    likes_count = await db.scalar(
        select(func.count(models.Like.post_id)).where(models.Like.post_id == item_id)
    )

    await db.delete(like)
    await db.commit()

    return LikedPostView(
        post_id=item_id,
        user=current_user,
        is_liked=False,
        created_at=datetime.now(UTC),
        likes_count=likes_count - 1,
    )


# -----------------------------
# GETTING COMMENTS FOR AN ITEM
# -----------------------------
@router.get("/{item_id}/comments", response_model=PaginatedComment)
async def get_comments_for_post(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.comment_per_page,
):

    result = await db.execute(select(models.Post).where(models.Post.id == item_id))

    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Comment)
        .where(models.Comment.item_id == item_id)
    )

    total_comments = count_result.scalar() or 0

    result = await db.execute(
        select(models.Comment)
        .where(models.Comment.item_id == item_id)
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
# COMMENTING ON AN ITEM
# ----------------------


@router.post(
    "/{item_id}/comment",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentedPostView,
)
async def comment_item(
    item_id: int,
    data: CommentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    result = await db.execute(
        select(models.Comment).where(
            models.Comment.user_id == current_user.id, models.Comment.item_id == item_id
        )
    )

    existing_comment = result.scalars().first()

    if existing_comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item already Commented"
        )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.item_id == item_id)
    )

    comment = models.Comment(
        user_id=current_user.id, content=data.content, item_id=item_id
    )

    db.add(comment)
    await db.commit()
    db.refresh(comment)

    return CommentedPostView(
        id=comment.id,
        user=current_user,
        post_id=item_id,
        is_commented=True,
        content=comment.content,
        created_at=comment.created_at,
        comments_count=comments_count + 1,
    )


# ----------------------
# UNCOMMENTING ON AN ITEM - deleting a comment
# ----------------------


@router.delete("/{item_id}/comment/{comment_id}", response_model=CommentedPostView)
async def uncomment_item(
    item_id: int,
    comment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    existing_comment = await db.execute(
        select(models.Comment).where(
            models.Comment.id == comment_id,
            models.Comment.user_id == current_user.id,
            models.Comment.item_id == item_id,
        )
    )

    comment = existing_comment.scalars().first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Comment dosent Exists"
        )

    comments_count = await db.scalar(
        select(func.count(models.Comment.id)).where(models.Comment.item_id == item_id)
    )

    await db.delete(comment)
    await db.commit()

    return CommentedPostView(
        post_id=item_id,
        user=current_user,
        is_commented=False,
        comments_count=comments_count - 1,
    )


# -----------------------------
# GETTING BOOKMARKS FOR AN ITEM
# -----------------------------
@router.get("/{item_id}/bookmarks", response_model=PaginatedBookmark)
async def get_bookmarks_by_id(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.likes_per_page,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    bookmark_result = await db.execute(
        select(func.count(models.Bookmark.item_id)).where(
            models.Bookmark.item_id == item_id
        )
    )

    total_bookmarks = bookmark_result.scalar() or 0

    result = await db.execute(
        select(models.Bookmark)
        .where(models.Bookmark.item_id == item_id)
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
# BOOKMARKING AN ITEM - creating bookmark
# -----------------------------
@router.post(
    "/{item_id}/bookmark",
    status_code=status.HTTP_201_CREATED,
    response_model=BookmarkedPostView,
)
async def bookmark_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    result = await db.execute(
        select(models.Bookmark).where(
            models.Bookmark.user_id == current_user.id,
            models.Bookmark.item_id == item_id,
        )
    )

    existing_bookmark = result.scalars().first()

    if existing_bookmark:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item already bookmarked"
        )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.item_id)).where(
            models.Bookmark.item_id == item_id
        )
    )

    bookmark = models.Bookmark(user_id=current_user.id, item_id=item_id)

    db.add(bookmark)
    await db.commit()
    db.refresh(bookmark)

    return BookmarkedPostView(
        post_id=item_id,
        user=current_user,
        is_bookmarked=True,
        created_at=bookmark.created_at,
        bookmarks_count=bookmarks_count + 1,
    )


# -----------------------------
# DELETING BOOKMARK FROM AN ITEM
# -----------------------------
@router.delete("/{item_id}/bookmark", response_model=BookmarkedPostView)
async def unbookmark_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    item_result = await db.execute(
        select(models.Post.id).where(models.Post.id == item_id)
    )

    item = item_result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    existing_bookmark = await db.execute(
        select(models.Bookmark).where(
            models.Bookmark.user_id == current_user.id,
            models.Bookmark.item_id == item_id,
        )
    )

    bookmark = existing_bookmark.scalars().first()

    if not bookmark:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Item Not Bookmarked"
        )

    bookmarks_count = await db.scalar(
        select(func.count(models.Bookmark.item_id)).where(
            models.Bookmark.item_id == item_id
        )
    )

    await db.delete(bookmark)
    await db.commit()

    return BookmarkedPostView(
        post_id=item_id,
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
        raise HTTPException(status_code=404, detail="Post not found")

    # count
    count_result = await db.execute(
        select(func.count(models.Version.id)).where(models.Version.item_id == post_id)
    )
    total = count_result.scalar() or 0

    # fetch versions
    result = await db.execute(
        select(models.Version)
        .where(models.Version.item_id == post_id)
        .order_by(models.Version.version_number.desc())
        .offset(skip)
        .limit(limit)
    )

    versions = result.scalars().all()

    has_more = skip + len(versions) < total

    return PaginatedVersionResponse(
        posts=[VersionResponse.model_validate(v) for v in versions],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
