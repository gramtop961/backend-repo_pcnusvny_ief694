import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId

from database import db, create_document, get_documents
from schemas import POI, LoreArticle, Category, MapAsset

app = FastAPI(title="Roblox World Map & Lore API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def oid_str(value) -> str:
    return str(value) if isinstance(value, ObjectId) else str(value)


def doc_to_public(d: dict) -> dict:
    if not d:
        return d
    d = {**d}
    if d.get("_id"):
        d["id"] = oid_str(d.pop("_id"))
    return d


# Simple admin auth using environment variables
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


# Naive in-memory token store for demo purposes only
TOKENS: set[str] = set()


def require_admin(token: Optional[str] = None):
    if token is None or token not in TOKENS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.get("/")
def root():
    return {"message": "Backend running"}


@app.get("/test")
def test_database():
    status = {
        "backend": "✅ Running",
        "database": "❌ Not Connected",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "collections": [],
    }
    try:
        cols = db.list_collection_names() if db else []
        status["collections"] = cols
        status["database"] = "✅ Connected" if db else "❌ Not Connected"
    except Exception as e:
        status["database"] = f"⚠️ {e}"[:120]
    return status


# --------------------- Public API for Roblox and Website ---------------------

@app.get("/api/pois")
def get_pois():
    pois = get_documents("poi")
    mapped = [
        {
            "id": oid_str(p.get("_id")),
            "name": p.get("name"),
            "x_coordinate": p.get("x_coordinate"),
            "y_coordinate": p.get("y_coordinate"),
            "lore_article_id": p.get("lore_article_id"),
            "icon_type": p.get("icon_type", "marker"),
        }
        for p in pois
    ]
    return mapped


@app.get("/api/lore/{article_id}")
def get_lore_article(article_id: str):
    try:
        obj_id = ObjectId(article_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid article id")

    doc = db["lorearticle"].find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Article not found")
    public = doc_to_public(doc)
    # Ensure required fields are present in response
    return {
        "id": public["id"],
        "title": public.get("title"),
        "short_description": public.get("short_description"),
        "main_image_url": public.get("main_image_url"),
        "content_body": public.get("content_body"),
    }


@app.get("/api/lore/search")
def search_lore(q: str):
    query = {"$or": [
        {"title": {"$regex": q, "$options": "i"}},
        {"short_description": {"$regex": q, "$options": "i"}},
    ]}
    results = db["lorearticle"].find(query).limit(20)
    return [
        {
            "id": oid_str(r.get("_id")),
            "title": r.get("title"),
            "short_description": r.get("short_description"),
        }
        for r in results
    ]


# Public map endpoint (no auth) so the website can load the current map image
@app.get("/api/map")
def public_get_map():
    doc = db["mapasset"].find_one(sort=[("version", -1)]) if db else None
    return doc_to_public(doc) if doc else None


# --------------------- Admin endpoints ---------------------

@app.post("/api/admin/login", response_model=AuthResponse)
def admin_login(payload: AuthRequest):
    if payload.username == ADMIN_USERNAME and payload.password == ADMIN_PASSWORD:
        token = os.urandom(16).hex()
        TOKENS.add(token)
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")


# Map image asset
@app.get("/api/admin/map", dependencies=[Depends(require_admin)])
def get_map(token: str):
    doc = db["mapasset"].find_one(sort=[("version", -1)]) if db else None
    return doc_to_public(doc) if doc else None


class MapAssetUpdate(BaseModel):
    image_url: str
    width: Optional[int] = None
    height: Optional[int] = None


@app.post("/api/admin/map", dependencies=[Depends(require_admin)])
def set_map(payload: MapAssetUpdate, token: str):
    current = db["mapasset"].find_one(sort=[("version", -1)])
    version = (current.get("version", 0) + 1) if current else 1
    new_doc = MapAsset(image_url=payload.image_url, width=payload.width, height=payload.height, version=version)
    new_id = create_document("mapasset", new_doc)
    created = db["mapasset"].find_one({"_id": ObjectId(new_id)})
    return doc_to_public(created)


# POI CRUD
class POICreate(POI):
    pass


@app.get("/api/admin/pois", dependencies=[Depends(require_admin)])
def admin_list_pois(token: str):
    docs = get_documents("poi")
    return [doc_to_public(d) for d in docs]


@app.post("/api/admin/pois", dependencies=[Depends(require_admin)])
def admin_create_poi(payload: POICreate, token: str):
    new_id = create_document("poi", payload)
    created = db["poi"].find_one({"_id": ObjectId(new_id)})
    return doc_to_public(created)


class POIUpdate(BaseModel):
    name: Optional[str] = None
    x_coordinate: Optional[float] = None
    y_coordinate: Optional[float] = None
    icon_type: Optional[str] = None
    lore_article_id: Optional[str] = None


@app.put("/api/admin/pois/{poi_id}", dependencies=[Depends(require_admin)])
def admin_update_poi(poi_id: str, payload: POIUpdate, token: str):
    try:
        obj_id = ObjectId(poi_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    update_doc = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_doc:
        return {"updated": False}
    db["poi"].update_one({"_id": obj_id}, {"$set": update_doc})
    updated = db["poi"].find_one({"_id": obj_id})
    return doc_to_public(updated)


@app.delete("/api/admin/pois/{poi_id}", dependencies=[Depends(require_admin)])
def admin_delete_poi(poi_id: str, token: str):
    try:
        obj_id = ObjectId(poi_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    db["poi"].delete_one({"_id": obj_id})
    return {"deleted": True}


# Lore CRUD
class LoreCreate(LoreArticle):
    pass


@app.get("/api/admin/lore", dependencies=[Depends(require_admin)])
def admin_list_lore(token: str):
    docs = get_documents("lorearticle")
    return [doc_to_public(d) for d in docs]


@app.post("/api/admin/lore", dependencies=[Depends(require_admin)])
def admin_create_lore(payload: LoreCreate, token: str):
    new_id = create_document("lorearticle", payload)
    created = db["lorearticle"].find_one({"_id": ObjectId(new_id)})
    return doc_to_public(created)


class LoreUpdate(BaseModel):
    title: Optional[str] = None
    short_description: Optional[str] = None
    main_image_url: Optional[str] = None
    content_body: Optional[str] = None
    category_ids: Optional[List[str]] = None
    slug: Optional[str] = None


@app.put("/api/admin/lore/{lore_id}", dependencies=[Depends(require_admin)])
def admin_update_lore(lore_id: str, payload: LoreUpdate, token: str):
    try:
        obj_id = ObjectId(lore_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    update_doc = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_doc:
        return {"updated": False}
    db["lorearticle"].update_one({"_id": obj_id}, {"$set": update_doc})
    updated = db["lorearticle"].find_one({"_id": obj_id})
    return doc_to_public(updated)


@app.delete("/api/admin/lore/{lore_id}", dependencies=[Depends(require_admin)])
def admin_delete_lore(lore_id: str, token: str):
    try:
        obj_id = ObjectId(lore_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    db["lorearticle"].delete_one({"_id": obj_id})
    return {"deleted": True}


# Categories
class CategoryCreate(Category):
    pass


@app.get("/api/admin/categories", dependencies=[Depends(require_admin)])
def admin_list_categories(token: str):
    docs = get_documents("category")
    return [doc_to_public(d) for d in docs]


@app.post("/api/admin/categories", dependencies=[Depends(require_admin)])
def admin_create_category(payload: CategoryCreate, token: str):
    new_id = create_document("category", payload)
    created = db["category"].find_one({"_id": ObjectId(new_id)})
    return doc_to_public(created)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None


@app.put("/api/admin/categories/{category_id}", dependencies=[Depends(require_admin)])
def admin_update_category(category_id: str, payload: CategoryUpdate, token: str):
    try:
        obj_id = ObjectId(category_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    update_doc = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_doc:
        return {"updated": False}
    db["category"].update_one({"_id": obj_id}, {"$set": update_doc})
    updated = db["category"].find_one({"_id": obj_id})
    return doc_to_public(updated)


@app.delete("/api/admin/categories/{category_id}", dependencies=[Depends(require_admin)])
def admin_delete_category(category_id: str, token: str):
    try:
        obj_id = ObjectId(category_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    db["category"].delete_one({"_id": obj_id})
    return {"deleted": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
