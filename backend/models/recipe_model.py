from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class RecipeRequest(BaseModel):
    """Schema for recipe query requests"""
    ingredients: List[str] = Field(..., description="List of available ingredients")
    cuisine: Optional[str] = Field(None, description="Preferred cuisine type")
    dietary_restrictions: Optional[List[str]] = Field(
        default=[], description="Dietary restrictions or preferences"
    )
    cooking_time: Optional[int] = Field(
        None, description="Maximum cooking time in minutes"
    )

class RecipeResponse(BaseModel):
    """Schema for recipe responses"""
    recipe_id: str = Field(..., description="Unique identifier for the recipe")
    title: str = Field(..., description="Name of the recipe")
    ingredients: List[str] = Field(..., description="List of ingredients required")
    instructions: List[str] = Field(..., description="Step-by-step cooking instructions")
    cooking_time: int = Field(..., description="Estimated cooking time in minutes")
    difficulty: str = Field(..., description="Difficulty level (Easy/Medium/Hard)")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")

class RecipeInDB(RecipeResponse):
    """Schema for recipes stored in database"""
    user_query: str = Field(..., description="Original user query for this recipe")