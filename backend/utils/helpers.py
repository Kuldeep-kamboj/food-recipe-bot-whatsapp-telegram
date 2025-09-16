import re
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent injection attacks
    and remove potentially harmful characters.
    """
    if not text:
        return ""
    
    # Remove potentially harmful characters
    sanitized = re.sub(r'[<>{}[\]\\]', '', text.strip())
    # Limit length to prevent abuse
    return sanitized[:500]

def format_ingredients_list(ingredients: List[str]) -> str:
    """Convert list of ingredients to a formatted string"""
    if not ingredients:
        return "No ingredients specified"
    
    return ", ".join([ingredient.capitalize() for ingredient in ingredients if ingredient.strip()])

def validate_cooking_time(minutes: int) -> bool:
    """Validate that cooking time is reasonable"""
    return 1 <= minutes <= 480  # 1 minute to 8 hours

def parse_recipe_from_llm(response_text: str) -> Dict[str, Any]:
    """
    Parse structured recipe data from LLM response text.
    This function expects the LLM to return a specific format.
    """
    try:
        # This is a simplified parser - you might need to adjust based on your LLM's output format
        lines = response_text.split('\n')
        recipe_data = {
            'title': '',
            'ingredients': [],
            'instructions': [],
            'cooking_time': 0,
            'difficulty': 'Medium'
        }
        
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if 'title:' in line.lower():
                recipe_data['title'] = line.split(':', 1)[1].strip()
            elif 'ingredients:' in line.lower():
                current_section = 'ingredients'
            elif 'instructions:' in line.lower() or 'steps:' in line.lower():
                current_section = 'instructions'
            elif 'cooking time:' in line.lower():
                time_str = line.split(':', 1)[1].strip()
                recipe_data['cooking_time'] = int(re.findall(r'\d+', time_str)[0])
            elif 'difficulty:' in line.lower():
                recipe_data['difficulty'] = line.split(':', 1)[1].strip()
            elif current_section == 'ingredients' and line.startswith('-'):
                recipe_data['ingredients'].append(line[1:].strip())
            elif current_section == 'instructions' and re.match(r'^\d+\.', line):
                recipe_data['instructions'].append(re.sub(r'^\d+\.\s*', '', line))
        
        return recipe_data
        
    except Exception as e:
        logger.error(f"Error parsing recipe from LLM: {e}")
        raise ValueError("Failed to parse recipe from LLM response")

def generate_recipe_id() -> str:
    """Generate a unique recipe ID"""
    import uuid
    return f"recipe_{uuid.uuid4().hex[:8]}"