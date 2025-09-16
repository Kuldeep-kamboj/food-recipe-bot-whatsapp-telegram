import os
import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from ..utils.helpers import parse_recipe_from_llm, generate_recipe_id, sanitize_input
from ..database.db import db_instance

logger = logging.getLogger(__name__)

class RecipeService:
    """Service for interacting with Gemini LLM to generate recipes"""
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("GEMINI_API_KEY environment variable not set")
            raise ValueError("Gemini API key is required")
        
        try:
            genai.configure(api_key=self.api_key)
            #self.model = genai.GenerativeModel('gemini-pro')
            self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise
    
    def generate_recipe_prompt(self, ingredients: list, cuisine: Optional[str] = None, 
                             dietary_restrictions: Optional[list] = None,
                             cooking_time: Optional[int] = None) -> str:
        """Generate a structured prompt for the LLM"""
        prompt_parts = [
            "Generate a detailed recipe using the following ingredients:",
            f"Ingredients: {', '.join(ingredients)}",
        ]
        
        if cuisine:
            prompt_parts.append(f"Cuisine style: {cuisine}")
        
        if dietary_restrictions:
            prompt_parts.append(f"Dietary restrictions: {', '.join(dietary_restrictions)}")
        
        if cooking_time:
            prompt_parts.append(f"Maximum cooking time: {cooking_time} minutes")
        
        prompt_parts.extend([
            "Please provide the recipe in this exact format:",
            "Title: [Recipe Name]",
            "Ingredients:",
            "- [Ingredient 1]",
            "- [Ingredient 2]",
            "...",
            "Instructions:",
            "1. [Step 1]",
            "2. [Step 2]",
            "...",
            "Cooking Time: [X] minutes",
            "Difficulty: [Easy/Medium/Hard]",
            "Ensure the recipe is practical and quantities are specified."
        ])
        
        return "\n".join(prompt_parts)
    
    async def generate_recipe(self, recipe_request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a recipe using Gemini LLM"""
        try:
            # Sanitize inputs
            ingredients = [sanitize_input(ing) for ing in recipe_request['ingredients']]
            cuisine = sanitize_input(recipe_request.get('cuisine', ''))
            dietary_restrictions = [sanitize_input(restr) for restr in recipe_request.get('dietary_restrictions', [])]
            cooking_time = recipe_request.get('cooking_time')
            
            # Generate prompt
            prompt = self.generate_recipe_prompt(
                ingredients, cuisine, dietary_restrictions, cooking_time
            )
            
            # Call Gemini API
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini API")
            
            # Parse the response
            recipe_data = parse_recipe_from_llm(response.text)
            recipe_id = generate_recipe_id()
            
            # Prepare complete recipe data
            complete_recipe = {
                'recipe_id': recipe_id,
                'title': recipe_data['title'],
                'ingredients': recipe_data['ingredients'],
                'instructions': recipe_data['instructions'],
                'cooking_time': recipe_data['cooking_time'],
                'difficulty': recipe_data['difficulty'],
                'user_query': f"Ingredients: {', '.join(ingredients)}" +
                             (f", Cuisine: {cuisine}" if cuisine else "") +
                             (f", Restrictions: {', '.join(dietary_restrictions)}" if dietary_restrictions else "")
            }
            
            # Save to database
            db_instance.save_recipe(complete_recipe)
            
            return complete_recipe
            
        except Exception as e:
            logger.error(f"Failed to generate recipe: {e}")
            raise

# Global service instance
recipe_service = RecipeService()