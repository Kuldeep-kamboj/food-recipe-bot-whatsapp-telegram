import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator, List, Dict, Any
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    """SQLite database manager for recipe storage"""
    
    def __init__(self, db_path: str = "recipes.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database with required tables"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS recipes (
                        recipe_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        ingredients TEXT NOT NULL,
                        instructions TEXT NOT NULL,
                        cooking_time INTEGER NOT NULL,
                        difficulty TEXT NOT NULL,
                        user_query TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at ON recipes(created_at)
                """)
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def save_recipe(self, recipe_data: Dict[str, Any]) -> bool:
        """Save a recipe to the database"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO recipes 
                    (recipe_id, title, ingredients, instructions, cooking_time, difficulty, user_query)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    recipe_data['recipe_id'],
                    recipe_data['title'],
                    json.dumps(recipe_data['ingredients']),
                    json.dumps(recipe_data['instructions']),
                    recipe_data['cooking_time'],
                    recipe_data['difficulty'],
                    recipe_data['user_query']
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save recipe: {e}")
            return False
    
    def get_recipe(self, recipe_id: str) -> Dict[str, Any]:
        """Retrieve a recipe by ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM recipes WHERE recipe_id = ?", 
                    (recipe_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'recipe_id': row['recipe_id'],
                        'title': row['title'],
                        'ingredients': json.loads(row['ingredients']),
                        'instructions': json.loads(row['instructions']),
                        'cooking_time': row['cooking_time'],
                        'difficulty': row['difficulty'],
                        'user_query': row['user_query'],
                        'created_at': row['created_at']
                    }
                return {}
        except Exception as e:
            logger.error(f"Failed to retrieve recipe: {e}")
            return {}
    
    def get_recent_recipes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent recipes"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM recipes ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                return [
                    {
                        'recipe_id': row['recipe_id'],
                        'title': row['title'],
                        'ingredients': json.loads(row['ingredients']),
                        'instructions': json.loads(row['instructions']),
                        'cooking_time': row['cooking_time'],
                        'difficulty': row['difficulty'],
                        'created_at': row['created_at']
                    }
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to retrieve recent recipes: {e}")
            return []

# Global database instance
db_instance = DatabaseManager()