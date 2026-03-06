# ---------------------------------------------------------
# Imports
# ---------------------------------------------------------

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import logging
from sqlalchemy.orm import selectinload


from database import get_db_session, init_db
from models import User, Recipe, Ingredient, Tag


# ---------------------------------------------------------
# App setup
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Recipe API (FastAPI ORM)")
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    password: str
    name: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None

class TokenCreate(BaseModel):
    email: str
    password: str

class RecipeCreate(BaseModel):
    title: str
    time_minutes: int
    price: str
    link: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[int]] = None
    ingredients: Optional[List[int]] = None


# ---------------------------------------------------------
# Startup: Create tables
# ---------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    await init_db()
    logger.info("Database initialized")


# ---------------------------------------------------------
# Home page (HTML)
# ---------------------------------------------------------

@app.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.tags),
            selectinload(Recipe.ingredients)
        )
    )

    recipes = result.scalars().unique().all()

    recipe_list = []
    for r in recipes:
        recipe_list.append({
            "id": r.id,
            "title": r.title,
            "time_minutes": r.time_minutes,
            "price": r.price,
            "link": r.link or "",
            "tags": [{"id": t.id, "name": t.name} for t in r.tags]
        })

    return templates.TemplateResponse(
        "home.html",
        {"request": request, "recipes": recipe_list}
    )


# ---------------------------------------------------------
# Recipe detail (HTML)
# ---------------------------------------------------------

@app.get("/recipes/{id}/")
async def recipe_detail(id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == id)
        .options(
            selectinload(Recipe.tags),
            selectinload(Recipe.ingredients)
        )
    )

    recipe = result.scalars().first()

    if not recipe:
        return templates.TemplateResponse(
            "recipe_not_found.html",
            {"request": request},
            status_code=404
        )

    recipe_data = {
        "id": recipe.id,
        "title": recipe.title,
        "time_minutes": recipe.time_minutes,
        "price": recipe.price,
        "link": recipe.link or "",
        "description": recipe.description or "",
        "ingredients": [{"id": ing.id, "name": ing.name} for ing in recipe.ingredients],
        "tags": [{"id": t.id, "name": t.name} for t in recipe.tags]
    }

    return templates.TemplateResponse(
        "recipe_detail.html",
        {"request": request, "recipe": recipe_data}
    )


# ---------------------------------------------------------
# API Overview
# ---------------------------------------------------------

@app.get("/api")
async def api_overview():
    return {
        "create_user_url": "/api/user/create/",
        "current_user_url": "/api/user/me/",
        "user_token_url": "/api/user/token/",
        "recipes_url": "/api/recipe/recipes/",
        "recipe_url": "/api/recipe/recipes/{id}/",
        "ingredients_url": "/api/recipe/ingredients/",
        "tags_url": "/api/recipe/tags/"
    }


# ---------------------------------------------------------
# User API (ORM)
# ---------------------------------------------------------

@app.post("/api/user/create/", status_code=201)
async def user_create(user: UserCreate, db: AsyncSession = Depends(get_db_session)):
    new_user = User(email=user.email, password=user.password, name=user.name)
    db.add(new_user)

    try:
        await db.commit()
        await db.refresh(new_user)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email already exists")

    return {"id": new_user.id, "email": new_user.email, "name": new_user.name}


@app.get("/api/user/me/")
async def user_me():
    return {"email": "user@example.com", "name": "Example User"}


@app.put("/api/user/me/")
async def user_me_update(user: UserUpdate):
    return {"email": user.email or "user@example.com", "name": user.name or "Example User"}


@app.patch("/api/user/me/")
async def user_me_partial_update(user: UserUpdate):
    return {
        "email": user.email or "user@example.com",
        "name": user.name or "Example User"
    }


@app.post("/api/user/token/")
async def user_token_create(token: TokenCreate, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.email == token.email))
    user = result.scalars().first()

    if not user or user.password != token.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"email": token.email, "token": "placeholder_jwt_token"}


# ---------------------------------------------------------
# Recipe API (ORM)
# ---------------------------------------------------------

@app.get("/api/recipe/recipes/")
async def recipe_list(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.tags),
            selectinload(Recipe.ingredients)
        )
    )

    recipes = result.scalars().unique().all()

    output = []
    for r in recipes:
        output.append({
            "id": r.id,
            "title": r.title,
            "time_minutes": r.time_minutes,
            "price": r.price,
            "link": r.link or "",
            "ingredients": [{"id": ing.id, "name": ing.name} for ing in r.ingredients],
            "tags": [{"id": t.id, "name": t.name} for t in r.tags]
        })

    return output


@app.post("/api/recipe/recipes/", status_code=201)
async def recipe_create(recipe: RecipeCreate, db: AsyncSession = Depends(get_db_session)):
    new_recipe = Recipe(
        title=recipe.title,
        time_minutes=recipe.time_minutes,
        price=recipe.price,
        link=recipe.link,
        description=recipe.description
    )

    # Attach tags
    if recipe.tags:
        tag_rows = await db.execute(select(Tag).where(Tag.id.in_(recipe.tags)))
        new_recipe.tags = tag_rows.scalars().all()

    # Attach ingredients
    if recipe.ingredients:
        ing_rows = await db.execute(select(Ingredient).where(Ingredient.id.in_(recipe.ingredients)))
        new_recipe.ingredients = ing_rows.scalars().all()

    db.add(new_recipe)
    await db.commit()
    await db.refresh(new_recipe)

    return {"id": new_recipe.id}


@app.get("/api/recipe/recipes/{id}/")
async def recipe_detail_api(id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Recipe).where(Recipe.id == id))
    recipe = result.scalars().first()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return {
        "id": recipe.id,
        "title": recipe.title,
        "time_minutes": recipe.time_minutes,
        "price": recipe.price,
        "link": recipe.link or "",
        "description": recipe.description or "",
        "ingredients": [{"id": ing.id, "name": ing.name} for ing in recipe.ingredients],
        "tags": [{"id": t.id, "name": t.name} for t in recipe.tags]
    }


import uvicorn
import asyncio

if __name__ == "__main__":
    asyncio.run(
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=5000,
            reload=False
        )
    )
