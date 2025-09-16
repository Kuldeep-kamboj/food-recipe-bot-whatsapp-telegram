import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from backend.app import app
from backend.models.recipe_model import RecipeRequest

client = TestClient(app)

@pytest.fixture
def mock_recipe_service():
    """Mock the recipe service for testing"""
    with patch('backend.routes.recipe_routes.recipe_service') as mock:
        yield mock

@pytest.fixture
def mock_db_instance():
    """Mock the database instance for testing"""
    with patch('backend.routes.recipe_routes.db_instance') as mock:
        yield mock

def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "food-recipe-bot"}

def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
    assert "endpoints" in response.json()

def test_generate_recipe_success(mock_recipe_service):
    """Test successful recipe generation"""
    mock_recipe = {
        "recipe_id": "test_123",
        "title": "Test Recipe",
        "ingredients": ["ing1", "ing2"],
        "instructions": ["step1", "step2"],
        "cooking_time": 30,
        "difficulty": "Easy"
    }
    mock_recipe_service.generate_recipe.return_value = mock_recipe
    
    recipe_request = {
        "ingredients": ["chicken", "rice"],
        "cuisine": "Italian",
        "dietary_restrictions": [],
        "cooking_time": 30
    }
    
    response = client.post("/api/v1/recipes/generate", json=recipe_request)
    
    assert response.status_code == 200
    assert response.json()["title"] == "Test Recipe"
    assert response.json()["recipe_id"] == "test_123"
    mock_recipe_service.generate_recipe.assert_called_once()

def test_generate_recipe_invalid_input():
    """Test recipe generation with invalid input"""
    recipe_request = {
        "ingredients": [],  # Empty ingredients
        "cuisine": "Italian",
        "dietary_restrictions": [],
        "cooking_time": 30
    }
    
    response = client.post("/api/v1/recipes/generate", json=recipe_request)
    assert response.status_code == 400  # Should be validation error

def test_get_recipe_success(mock_db_instance):
    """Test successful recipe retrieval"""
    mock_recipe = {
        "recipe_id": "test_123",
        "title": "Test Recipe",
        "ingredients": ["ing1", "ing2"],
        "instructions": ["step1", "step2"],
        "cooking_time": 30,
        "difficulty": "Easy",
        "user_query": "test query",
        "created_at": "2023-01-01T00:00:00"
    }
    mock_db_instance.get_recipe.return_value = mock_recipe
    
    response = client.get("/api/v1/recipes/test_123")
    
    assert response.status_code == 200
    assert response.json()["title"] == "Test Recipe"
    mock_db_instance.get_recipe.assert_called_once_with("test_123")

def test_get_recipe_not_found(mock_db_instance):
    """Test recipe retrieval for non-existent recipe"""
    mock_db_instance.get_recipe.return_value = {}
    
    response = client.get("/api/v1/recipes/nonexistent")
    
    assert response.status_code == 404
    mock_db_instance.get_recipe.assert_called_once_with("nonexistent")

def test_get_recent_recipes(mock_db_instance):
    """Test retrieval of recent recipes"""
    mock_recipes = [
        {
            "recipe_id": "test_1",
            "title": "Recipe 1",
            "ingredients": ["ing1"],
            "instructions": ["step1"],
            "cooking_time": 20,
            "difficulty": "Easy",
            "created_at": "2023-01-01T00:00:00"
        }
    ]
    mock_db_instance.get_recent_recipes.return_value = mock_recipes
    
    response = client.get("/api/v1/recipes?limit=5")
    
    assert response.status_code == 200
    assert "recipes" in response.json()
    assert len(response.json()["recipes"]) == 1
    mock_db_instance.get_recent_recipes.assert_called_once_with(5)

def test_whatsapp_webhook_missing_config():
    """Test WhatsApp webhook without Twilio configuration"""
    response = client.post("/api/v1/webhook/whatsapp", data={})
    # Should return error since Twilio is not configured in tests
    assert response.status_code in [500, 501]