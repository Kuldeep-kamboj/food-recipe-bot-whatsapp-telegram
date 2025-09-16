from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import logging

from ..models.recipe_model import RecipeRequest, RecipeResponse
from ..services.recipe_service import recipe_service
from ..database.db import db_instance
from ..utils.helpers import sanitize_input

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/recipes/generate", response_model=RecipeResponse)
async def generate_recipe(recipe_request: RecipeRequest):
    """
    Generate a recipe based on provided ingredients and preferences.
    
    Args:
        recipe_request: Contains ingredients, cuisine preferences, 
                       dietary restrictions, and cooking time constraints
    
    Returns:
        RecipeResponse: Generated recipe with detailed instructions
    """
    try:
        # Convert Pydantic model to dict for service
        request_data = {
            'ingredients': [sanitize_input(ing) for ing in recipe_request.ingredients],
            'cuisine': sanitize_input(recipe_request.cuisine) if recipe_request.cuisine else None,
            'dietary_restrictions': [sanitize_input(restr) for restr in recipe_request.dietary_restrictions],
            'cooking_time': recipe_request.cooking_time
        }
        
        # Generate recipe
        recipe = await recipe_service.generate_recipe(request_data)
        
        return RecipeResponse(**recipe)
        
    except ValueError as e:
        logger.warning(f"Validation error in recipe generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating recipe: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate recipe")

@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: str):
    """
    Retrieve a previously generated recipe by its ID.
    
    Args:
        recipe_id: Unique identifier of the recipe
    
    Returns:
        RecipeResponse: The requested recipe details
    """
    try:
        recipe = db_instance.get_recipe(recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        return RecipeResponse(**recipe)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving recipe {recipe_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recipe")

@router.get("/recipes")
async def get_recent_recipes(limit: int = 10):
    """
    Retrieve recently generated recipes.
    
    Args:
        limit: Maximum number of recipes to return (default: 10)
    
    Returns:
        List of recent recipes
    """
    try:
        recipes = db_instance.get_recent_recipes(limit)
        return {"recipes": recipes, "count": len(recipes)}
        
    except Exception as e:
        logger.error(f"Error retrieving recent recipes: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recipes")