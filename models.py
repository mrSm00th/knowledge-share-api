from __future__ import annotations
from datetime import datetime, UTC
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from database import Base


class User(Base):

    __tablename__ = "users"

    id : Mapped[int] = mapped_column(Integer, primary_key= True, index = True )
    username : Mapped[str] = mapped_column(String(50), unique=True, nullable=False )
    email : Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash : Mapped[str] = mapped_column(String(255), nullable=False)
    bio : Mapped[str] = mapped_column(Text)
    image_file : Mapped[str] = mapped_column(String(200),nullable=True, default=None)
    created_at : Mapped[DateTime] = mapped_column(DateTime(timezone=True), default = lambda: datetime.now(UTC), nullable=False)

    items :Mapped[list[Item]] = relationship(back_populates = "author", cascade = "all, delete-orphan")

    # people who followed this user
    followers : Mapped[list[Follow]] = relationship(
        foreign_keys= "Follow.follows_id",
        back_populates= "following_user",
        cascade = "all, delete-orphan"
        )
    
    # people who this user follows
    following : Mapped[list[Follow]] = relationship(
        foreign_keys= "Follow.user_id",
        back_populates= "follower_user",
        cascade = "all, delete-orphan")
    
    #saved posts 
    bookmarks : Mapped[list[Bookmark]] = relationship(
        back_populates= "user",
        cascade="all, delete-orphan"
    )

    likes : Mapped[list[Like]] = relationship(
        back_populates= "user",
        cascade = "all, delete-orphan"
    ) 

    comments : Mapped[list[Comment]] = relationship(
        
        back_populates= "user",
        cascade = "all, delete-orphan"
    )

    tags_created : Mapped[list[Tag]] = relationship(
        back_populates= "creator",
        foreign_keys="Tag.created_by")


    @property
    def image_path(self) -> str:
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        
        return "static/profile_pics/default.jpg"


class Item(Base):

    __tablename__  = "items"

    id : Mapped[int] = mapped_column(Integer, primary_key=True, index = True)
    user_id : Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable= True,
        index = True)
    title : Mapped[str] = mapped_column(String(100), nullable= False,index = True)
    content : Mapped[str] = mapped_column(Text, nullable = False)
    is_public : Mapped[bool] = mapped_column(Boolean, nullable = False, default = True)
    date_posted : Mapped[datetime] = mapped_column(DateTime(timezone=True), default = lambda: datetime.now(UTC))
    updated_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False, onupdate= lambda : datetime.now(UTC))


    author : Mapped[User] = relationship(
        back_populates="items"
    )

    tags : Mapped[list[Tag]] = relationship(
        secondary= "itemtags", 
        back_populates= "items"
    )

    comments : Mapped[list[Comment]] = relationship( 
        back_populates="item",
        cascade= "all, delete-orphan"
    )
    
    likes: Mapped[list[Like]] = relationship(
        back_populates="item",
        cascade= "all,delete-orphan"
    )
    
    bookmarked_by : Mapped[list[Bookmark]] = relationship(
        back_populates="item", 
        cascade= "all, delete-orphan"
    )

    versions : Mapped[list[Version]] = relationship(
        back_populates= "item", 
        cascade= "all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "title"),
    )

class Tag(Base):
    __tablename__ = "tags"

    id :  Mapped[int] = mapped_column(Integer, primary_key= True, index = True)
    name : Mapped[str] = mapped_column(String(120), nullable =False, index = True, unique = True)
    created_by : Mapped[int] = mapped_column(ForeignKey("users.id", ondelete= "SET NULL"), nullable = True, index = True ) 
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)

    items : Mapped[list[Item]] = relationship(
        secondary = "itemtags", 
        back_populates= "tags"
        
    )

    creator : Mapped[User] = relationship(
        back_populates="tags_created",
        foreign_keys=[created_by]
    )

class Itemtag(Base):

    __tablename__ = "itemtags"

    item_id : Mapped[int] = mapped_column(ForeignKey("items.id"), nullable= False, index = True, primary_key = True)
    tag_id : Mapped[int] = mapped_column(ForeignKey("tags.id"),nullable = False, index = True, primary_key = True)
    


    

class Follow(Base):

    __tablename__ = "follows"
    
    #follower_id
    user_id : Mapped[int] = mapped_column (ForeignKey("users.id"), primary_key = True, nullable=False, index = True)
    
    #following_id
    follows_id : Mapped[int] = mapped_column (ForeignKey("users.id"), primary_key = True, nullable= False, index = True)

    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)


    # the user doing the following
    follower_user : Mapped[User] = relationship(

        foreign_keys=[user_id],
        back_populates= "following"
    )

    # the user being followed
    following_user : Mapped[User] = relationship(

        foreign_keys=[follows_id],
        back_populates="followers"
    )


  
class Like(Base):
    __tablename__ = "likes"

    user_id : Mapped[int] = mapped_column (ForeignKey("users.id"), primary_key = True, nullable=False, index = True)
    item_id : Mapped[int] = mapped_column (ForeignKey("items.id"), primary_key = True, nullable=False, index = True)
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)

    user : Mapped[User] = relationship(

        back_populates= "likes")
    
    item : Mapped[Item] = relationship(

        back_populates="likes")
    
    


class Bookmark(Base): # saving some else's item

    __tablename__ = "bookmarks"

    user_id : Mapped[int] = mapped_column (ForeignKey("users.id"), primary_key = True, nullable=False, index = True)
    item_id : Mapped[int] = mapped_column (ForeignKey("items.id"), primary_key = True, nullable=False, index = True)
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)

    user : Mapped[User] = relationship(back_populates="bookmarks")
    item : Mapped[Item] = relationship(back_populates="bookmarked_by")

    
    


class Comment(Base):
    __tablename__ = "comments"

    id : Mapped[int] = mapped_column(Integer, primary_key = True)
    user_id : Mapped[int] = mapped_column(ForeignKey("users.id"), nullable= False, index =True)
    item_id : Mapped[int] = mapped_column (ForeignKey("items.id"), nullable=False, index = True)
    content : Mapped[str] = mapped_column(Text, nullable=False)
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)

    user : Mapped[User] = relationship(
        back_populates= "comments"
    )

    item : Mapped[Item] = relationship(
        back_populates="comments"
    )

   


class Version(Base):
    __tablename__ = "versions"

    id : Mapped[int] = mapped_column(Integer, primary_key = True)
    item_id : Mapped[int] = mapped_column (ForeignKey("items.id"), nullable=False, index = True)
    version_number : Mapped[int] = mapped_column(Integer, nullable =False)
    title : Mapped[str] = mapped_column(Text, nullable= False,index = True)
    content : Mapped[str] = mapped_column(Text, nullable = False)
    edited_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default= lambda : datetime.now(UTC), nullable= False)

    item : Mapped[Item] = relationship(back_populates="versions")
    __table_args__ = (
            UniqueConstraint("item_id", "version_number"),
        )


