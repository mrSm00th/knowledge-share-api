from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# from db.models import models
import app.db.models as models
from app.core.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.schemas.schemas import TagCreate, TagCreateResponse, TagMini

router = APIRouter(prefix="/api/tags")
from typing_extensions import TypeAlias

CurrentUser: TypeAlias = Annotated[models.User, Depends(get_current_user)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TagCreateResponse)
async def create_tag(
    data: TagCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):

    result = await db.execute(
        select(models.Tag).where(func.lower(models.Tag.name) == data.name.lower())
    )
    existing_tag = result.scalars().first()

    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag already exists with id: {existing_tag.id}",
        )

    new_tag = models.Tag(name=data.name, creator_id=current_user.id)

    db.add(new_tag)
    await db.commit()
    await db.refresh(new_tag)

    return new_tag


# get all the tags
@router.get("", response_model=list[TagMini])
async def get_all_tags(db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(select(models.Tag))

    tags = result.scalars().all()

    return tags
