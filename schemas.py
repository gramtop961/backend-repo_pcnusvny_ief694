"""
Database Schemas for Interactive World Map & Lore Wiki

Each Pydantic model corresponds to a MongoDB collection with the collection
name equal to the lowercase class name (e.g., LoreArticle -> "lorearticle").
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class Category(BaseModel):
    name: str = Field(..., description="Category display name")
    slug: str = Field(..., description="URL-friendly unique slug")
    description: Optional[str] = Field(None, description="Short description of this category")


class LoreArticle(BaseModel):
    title: str = Field(..., description="Article title")
    short_description: str = Field(..., description="Short teaser/summary")
    main_image_url: Optional[str] = Field(None, description="Primary image URL")
    content_body: str = Field(..., description="HTML content for WYSIWYG output")
    category_ids: List[str] = Field(default_factory=list, description="List of linked Category IDs (as strings)")
    slug: Optional[str] = Field(default=None, description="Optional URL slug")


class POI(BaseModel):
    name: str = Field(..., description="Point of Interest name")
    x_coordinate: float = Field(..., ge=0, le=1, description="X position normalized 0..1 relative to map width")
    y_coordinate: float = Field(..., ge=0, le=1, description="Y position normalized 0..1 relative to map height")
    icon_type: str = Field("marker", description="Icon type (city, dungeon, quest, marker...)")
    lore_article_id: Optional[str] = Field(None, description="Linked LoreArticle ID")


class MapAsset(BaseModel):
    image_url: str = Field(..., description="Public URL to the map image")
    width: Optional[int] = Field(None, description="Original pixel width")
    height: Optional[int] = Field(None, description="Original pixel height")
    version: int = Field(1, description="Increment when image replaced")
