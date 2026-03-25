from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseSchema):

    username: Annotated[str, Field(min_length=1, max_length=20)]
    email: EmailStr
    bio: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]
    password: Annotated[str, Field(min_length=8)]


class UserPublic(BaseSchema):

    id: int
    username: str
    image_path: str


class UserMe(UserPublic):

    email: str
    bio: str | None
    created_at: datetime


class UserUpdate(BaseSchema):

    username: Annotated[str | None, Field(default=None, min_length=5, max_length=20)]
    email: EmailStr | None = None
    bio: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]


class PaginatedUsernameSearch(BaseSchema):

    users: list[UserPublic]
    total: int
    skip: int
    limit: int
    has_more: bool


class PaginatedPostSearch(BaseSchema):

    posts: list[PostMini]
    total: int
    skip: int
    limit: int
    has_more: bool


class ProfileStatus(BaseSchema):

    post_count: int
    followers_count: int
    followings_count: int


class PostCreate(BaseSchema):

    title: Annotated[str, Field(min_length=1, max_length=100)]
    content: Annotated[str, Field(min_length=1, max_length=1000)]
    is_public: bool = True
    tag_ids: Annotated[list[int], Field(max_length=10)] = []


class PostUpdate(BaseSchema):

    title: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]
    content: Annotated[str | None, Field(default=None, min_length=1, max_length=1000)]
    tag_ids: Annotated[list[int] | None, Field(default=None, max_length=10)]


class PostUpdatedView(BaseSchema):

    id: int
    title: str
    content: str
    tags: list[Tag]
    version_number: int
    created_at: datetime
    updated_at: datetime


class VisibilityUpdate(BaseSchema):

    is_public: bool


class VisibilityUpdatedView(BaseSchema):

    id: int
    is_public: bool


class PostMini(BaseSchema):

    id: int  # Post id
    author: UserPublic
    title: str
    content: str
    created_at: datetime


class PostMinimal(BaseSchema):
    id: int
    user_id: int
    title: str
    content: str
    created_at: datetime


class PostDetailed(PostMini):
    tags: list[Tag]
    likes_count: int
    comments_count: int
    bookmarks_count: int
    # version_number - update post, fetching post for current user


class PostOwnerView(PostDetailed):
    is_public: bool
    version_count: int


class PaginatedFeed(BaseSchema):

    posts: list[PostDetailed]
    total: int
    skip: int
    limit: int
    has_more: bool


class LikeView(BaseSchema):

    post_id: int
    user: UserPublic
    is_liked: bool = True
    created_at: datetime


class LikedPostView(LikeView):
    likes_count: int


class PaginatedLike(BaseSchema):

    likes: list[LikeView]
    total: int
    skip: int
    limit: int
    has_more: bool


class CommentCreate(BaseSchema):
    content: Annotated[str, Field(min_length=1, max_lenght=500)]


class CommentView(BaseSchema):

    id: int
    post_id: int
    user: UserPublic
    content: str
    created_at: datetime


class CommentedPostView(BaseSchema):

    id: Optional[int] = None
    post_id: int
    user: UserPublic
    is_commented: bool
    content: Optional[str] = None
    created_at: Annotated[datetime, Field(default=datetime.now(UTC))]
    comments_count: int


class PaginatedComment(BaseSchema):

    comments: list[CommentView]
    total: int
    skip: int
    limit: int
    has_more: bool


class OwnerCommentView(BaseSchema):

    id: int
    post: PostMinimal
    content: str
    created_at: datetime


class PaginatedOwnerComment(BaseSchema):

    comments: list[OwnerCommentView]
    total: int
    skip: int
    limit: int
    has_more: bool


class OwnerBookmarkView(BaseSchema):

    post: PostMinimal
    created_at: datetime


class PaginatedOwnerBookmark(BaseSchema):

    bookmarks: list[OwnerBookmarkView]
    total: int
    skip: int
    limit: int
    has_more: bool


class OwnerLikeView(BaseSchema):

    post: PostMinimal
    created_at: datetime


class PaginatedOwnerLike(BaseSchema):

    likes: list[OwnerLikeView]
    total: int
    skip: int
    limit: int
    has_more: bool


class BookmarkView(BaseSchema):

    post_id: int
    user: UserPublic
    created_at: datetime


class BookmarkedPostView(BaseSchema):

    post_id: int
    user: UserPublic
    is_bookmarked: bool
    created_at: Annotated[datetime, Field(default=datetime.now(UTC))]
    bookmarks_count: int


class PaginatedBookmark(BaseSchema):

    bookmarks: list[BookmarkView]
    total: int
    skip: int
    limit: int
    has_more: bool


class PaginatedTagView(BaseSchema):

    tags: list[TagView]
    total: int
    skip: int
    limit: int
    has_more: bool


class Follow(BaseSchema):

    follower_user: UserPublic
    following_user: UserPublic
    created_at: Annotated[datetime, Field(default=datetime.now(UTC))]
    is_following: bool


class Follower(BaseSchema):

    follower_user: UserPublic
    created_at: datetime


class PaginatedFollower(BaseSchema):

    follower: list[Follower]
    total: int
    skip: int
    limit: int
    has_more: bool


class Following(BaseSchema):

    following_user: UserPublic
    created_at: datetime


class PaginatedFollowing(BaseSchema):

    following: list[Following]
    total: int
    skip: int
    limit: int
    has_more: bool


class VersionResponse(BaseSchema):
    id: int
    version_number: int
    title: str
    content: str
    updated_at: datetime


class PaginatedVersionResponse(BaseSchema):
    versions: list[VersionResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class Tag(BaseSchema):

    id: int
    name: str


class TagView(BaseSchema):
    id: int
    name: str
    created_at: datetime


class TagCreate(BaseSchema):

    name: str = Field(min_length=1, max_length=120)


class TagCreateResponse(TagCreate):

    id: int
    creator_id: int
    created_at: datetime


class TagMini(BaseSchema):

    id: int
    name: str
