import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from backend.services.recipe_service import RecipeService
from backend.utils.helpers import parse_recipe_from_llm, sanitize_input, generate_recipe_id
from backend.database.db import DatabaseManager

@pytest.fixture
def recipe_service():
    """Create a RecipeService instance with mocked Gemini client"""
    with patch('google.generativeai.GenerativeModel') as mock_model, \
         patch('google.generativeai.configure'):
        
        mock_model.return_value.generate_content.return_value.text = """
        Title: Test Recipe
        Ingredients:
        - Ingredient 1
        - Ingredient 2
        Instructions:
        1. Step one
        2. Step two
        Cooking Time: 30 minutes
        Difficulty: Easy
        """
        
        service = RecipeService()
        service.model = mock_model.return_value
        return service

@pytest.fixture
def mock_db():
    """Create a mock database instance"""
    with patch('backend.services.recipe_service.db_instance') as mock:
        mock.save_recipe.return_value = True
        yield mock

def test_sanitize_input():
    """Test input sanitization"""
    # Test normal input
    assert sanitize_input("normal text") == "normal text"
    
    # Test with harmful characters
    assert sanitize_input("text <script>") == "text script"
    assert sanitize_input("text [bad]") == "text bad"
    
    # Test length limitation
    long_text = "a" * 600
    assert len(sanitize_input(long_text)) == 500

def test_generate_recipe_id():
    """Test recipe ID generation"""
    recipe_id = generate_recipe_id()
    assert recipe_id.startswith("recipe_")
    assert len(recipe_id) == len("recipe_") + 8  # 8 hex characters

def test_parse_recipe_from_llm():
    """Test parsing recipe from LLM response"""
    llm_response = """
    Title: Test Pasta
    Ingredients:
    - Pasta 200g
    - Tomato sauce
    Instructions:
    1. Cook pasta
    2. Add sauce
    Cooking Time: 20 minutes
    Difficulty: Easy
    """
    
    recipe_data = parse_recipe_from_llm(llm_response)
    
    assert recipe_data["title"] == "Test Pasta"
    assert "Pasta 200g" in recipe_data["ingredients"]
    assert "Cook pasta" in recipe_data["instructions"]
    assert recipe_data["cooking_time"] == 20
    assert recipe_data["difficulty"] == "Easy"

def test_parse_recipe_from_llm_invalid():
    """Test parsing invalid LLM response"""
    with pytest.raises(ValueError):
        parse_recipe_from_llm("Invalid format")

def test_generate_recipe_prompt(recipe_service):
    """Test recipe prompt generation"""
    prompt = recipe_service.generate_recipe_prompt(
        ingredients=["chicken", "rice"],
        cuisine="Italian",
        dietary_restrictions=["gluten-free"],
        cooking_time=30
    )
    
    assert "chicken, rice" in prompt
    assert "Italian" in prompt
    assert "gluten-free" in prompt
    assert "30" in prompt

def test_generate_recipe_success(recipe_service, mock_db):
    """Test successful recipe generation"""
    recipe_request = {
        "ingredients": ["chicken", "rice"],
        "cuisine": "Italian",
        "dietary_restrictions": ["gluten-free"],
        "cooking_time": 30
    }
    
    # Mock the generate_content method
    recipe_service.model.generate_content.return_value.text = """
    Title: Chicken Rice
    Ingredients:
    - Chicken 500g
    - Rice 200g
    Instructions:
    1. Cook chicken
    2. Cook rice
    Cooking Time: 30 minutes
    Difficulty: Medium
    """
    
    recipe = recipe_service.generate_recipe(recipe_request)
    
    assert recipe["title"] == "Chicken Rice"
    assert recipe["cooking_time"] == 30
    assert mock_db.save_recipe.called

def test_generate_recipe_api_error(recipe_service):
    """Test recipe generation with API error"""
    recipe_service.model.generate_content.side_effect = Exception("API error")
    
    recipe_request = {
        "ingredients": ["chicken", "rice"],
        "cuisine": "Italian",
        "dietary_restrictions": [],
        "cooking_time": 30
    }
    
    with pytest.raises(Exception):
        recipe_service.generate_recipe(recipe_request)

def test_database_operations():
    """Test database operations"""
    with patch('sqlite3.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        db = DatabaseManager(":memory:")
        
        # Test save recipe
        recipe_data = {
            "recipe_id": "test_123",
            "title": "Test Recipe",
            "ingredients": ["ing1", "ing2"],
            "instructions": ["step1", "step2"],
            "cooking_time": 30,
            "difficulty": "Easy",
            "user_query": "test query"
        }
        
        result = db.save_recipe(recipe_data)
        assert result is True
        
        # Test get recipe
        mock_cursor.fetchone.return_value = {
            "recipe_id": "test_123",
            "title": "Test Recipe",
            "ingredients": '["ing1", "ing2"]',
            "instructions": '["step1", "step2"]',
            "cooking_time": 30,
            "difficulty": "Easy",
            "user_query": "test query",
            "created_at": "2023-01-01T00:00:00"
        }
        
        recipe = db.get_recipe("test_123")
        assert recipe["title"] == "Test Recipe"
        
        # Test get recent recipes
        mock_cursor.fetchall.return_value = [mock_cursor.fetchone.return_value]
        recipes = db.get_recent_recipes(5)
        assert len(recipes) == 1