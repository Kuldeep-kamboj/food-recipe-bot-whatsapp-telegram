import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator, List, Dict, Any, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    """SQLite database manager for recipe storage and payment tracking"""
    
    def __init__(self, db_path: str = "food_recipe_bot.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database with required tables"""
        try:
            with self._get_connection() as conn:
                # Recipes table (existing)
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
                
                # Payments table (new)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS payments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        payment_id TEXT UNIQUE NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        customer_phone TEXT NOT NULL,
                        status TEXT NOT NULL,
                        upi_reference TEXT,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_payment_id ON payments(payment_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_customer_phone ON payments(customer_phone)
                """)
                
                # Users table (new)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone_number TEXT UNIQUE NOT NULL,
                        name TEXT,
                        is_premium INTEGER DEFAULT 0,
                        premium_expiry TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_phone ON users(phone_number)
                """)
                
                # Sessions table (new)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone_number TEXT NOT NULL,
                        session_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_session_phone ON sessions(phone_number)
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
    
    # Recipe methods (existing)
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

    # Payment methods (new)
    def save_payment(self, payment_data: Dict[str, Any]) -> bool:
        """Save a payment to the database"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO payments 
                    (payment_id, amount, currency, customer_phone, status, upi_reference, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    payment_data['payment_id'],
                    payment_data['amount'],
                    payment_data['currency'],
                    payment_data['customer_phone'],
                    payment_data['status'],
                    payment_data.get('upi_reference'),
                    payment_data.get('description', '')
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save payment: {e}")
            return False
    
    def update_payment_status(self, payment_id: str, status: str, upi_reference: Optional[str] = None) -> bool:
        """Update payment status in database"""
        try:
            with self._get_connection() as conn:
                if upi_reference:
                    conn.execute(
                        "UPDATE payments SET status = ?, upi_reference = ?, updated_at = CURRENT_TIMESTAMP WHERE payment_id = ?",
                        (status, upi_reference, payment_id)
                    )
                else:
                    conn.execute(
                        "UPDATE payments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE payment_id = ?",
                        (status, payment_id)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update payment status: {e}")
            return False
    
    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """Retrieve a payment by ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM payments WHERE payment_id = ?", 
                    (payment_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'payment_id': row['payment_id'],
                        'amount': row['amount'],
                        'currency': row['currency'],
                        'customer_phone': row['customer_phone'],
                        'status': row['status'],
                        'upi_reference': row['upi_reference'],
                        'description': row['description'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return {}
        except Exception as e:
            logger.error(f"Failed to retrieve payment: {e}")
            return {}
    
    def get_user_payments(self, customer_phone: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve payments for a specific user"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM payments WHERE customer_phone = ? ORDER BY created_at DESC LIMIT ?",
                    (customer_phone, limit)
                )
                return [
                    {
                        'payment_id': row['payment_id'],
                        'amount': row['amount'],
                        'currency': row['currency'],
                        'status': row['status'],
                        'upi_reference': row['upi_reference'],
                        'created_at': row['created_at']
                    }
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to retrieve user payments: {e}")
            return []

    # User methods (new)
    def save_user(self, user_data: Dict[str, Any]) -> bool:
        """Save a user to the database"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO users 
                    (phone_number, name, is_premium, premium_expiry)
                    VALUES (?, ?, ?, ?)
                """, (
                    user_data['phone_number'],
                    user_data.get('name'),
                    user_data.get('is_premium', 0),
                    user_data.get('premium_expiry')
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save user: {e}")
            return False
    
    def get_user(self, phone_number: str) -> Dict[str, Any]:
        """Retrieve a user by phone number"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM users WHERE phone_number = ?", 
                    (phone_number,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'phone_number': row['phone_number'],
                        'name': row['name'],
                        'is_premium': bool(row['is_premium']),
                        'premium_expiry': row['premium_expiry'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return {}
        except Exception as e:
            logger.error(f"Failed to retrieve user: {e}")
            return {}
    
    def update_user_premium_status(self, phone_number: str, is_premium: bool, premium_expiry: Optional[datetime] = None) -> bool:
        """Update user premium status"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE users SET is_premium = ?, premium_expiry = ?, updated_at = CURRENT_TIMESTAMP WHERE phone_number = ?",
                    (int(is_premium), premium_expiry, phone_number)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update user premium status: {e}")
            return False

    # Session methods (new)
    def save_session(self, session_data: Dict[str, Any]) -> bool:
        """Save a session to the database"""
        try:
            with self._get_connection() as conn:
                # First try to update existing session
                conn.execute(
                    "UPDATE sessions SET session_data = ?, updated_at = CURRENT_TIMESTAMP WHERE phone_number = ?",
                    (json.dumps(session_data['session_data']), session_data['phone_number'])
                )
                
                # If no rows were updated, insert new session
                if conn.total_changes == 0:
                    conn.execute("""
                        INSERT INTO sessions 
                        (phone_number, session_data)
                        VALUES (?, ?)
                    """, (
                        session_data['phone_number'],
                        json.dumps(session_data['session_data'])
                    ))
                
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    def get_session(self, phone_number: str) -> Dict[str, Any]:
        """Retrieve a session by phone number"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE phone_number = ?", 
                    (phone_number,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'phone_number': row['phone_number'],
                        'session_data': json.loads(row['session_data']),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return {}
        except Exception as e:
            logger.error(f"Failed to retrieve session: {e}")
            return {}
    
    def delete_session(self, phone_number: str) -> bool:
        """Delete a session by phone number"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "DELETE FROM sessions WHERE phone_number = ?",
                    (phone_number,)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False

# Global database instance
db_instance = DatabaseManager()