import streamlit as st
import requests
import json
import os

from typing import List, Optional

# Configure page
st.set_page_config(
    page_title="Food Recipe Bot",
    page_icon="🍳",
    layout="wide"
)

# Get backend URL from environment variable with default
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# API configuration
API_BASE_URL = BACKEND_URL + "/api/v1"
API_HEALTH_URL = BACKEND_URL

def test_api_connection():
    """Test connection to the backend API"""
    try:
        response = requests.get(f"{API_HEALTH_URL}/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def generate_recipe(ingredients: List[str], cuisine: Optional[str] = None, 
                   dietary_restrictions: Optional[List[str]] = None,
                   cooking_time: Optional[int] = None):
    """Send recipe generation request to backend API"""
    payload = {
        "ingredients": ingredients,
        "cuisine": cuisine,
        "dietary_restrictions": dietary_restrictions or [],
        "cooking_time": cooking_time
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/recipes/generate",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error generating recipe: {e}")
        return None

def get_recent_recipes(limit: int = 5):
    """Fetch recent recipes from backend"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/recipes?limit={limit}",
            timeout=10
        )
        response.raise_for_status()
        return response.json().get('recipes', [])
    except requests.exceptions.RequestException:
        return []

def display_recipe(recipe):
    """Display recipe in a formatted way"""
    if not recipe:
        return
    
    st.header(recipe['title'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Ingredients")
        for ingredient in recipe['ingredients']:
            st.write(f"• {ingredient}")
        
        st.subheader("📊 Details")
        st.write(f"**Cooking Time:** {recipe['cooking_time']} minutes")
        st.write(f"**Difficulty:** {recipe['difficulty']}")
        st.write(f"**Recipe ID:** `{recipe['recipe_id']}`")
    
    with col2:
        st.subheader("👩‍🍳 Instructions")
        for i, instruction in enumerate(recipe['instructions'], 1):
            st.write(f"{i}. {instruction}")

def main():
    """Main Streamlit application"""
    st.title("🍳 Food Recipe Bot")
    st.markdown("Generate delicious recipes from your available ingredients!")
    
    # Check API connection
    if not test_api_connection():
        st.error("⚠️ Backend API is not available. Please make sure the backend server is running.")
        st.info("Run the backend with: `uvicorn app:app --reload` from the backend directory")
        return
    
    # Sidebar for recent recipes
    with st.sidebar:
        st.header("📖 Recent Recipes")
        recent_recipes = get_recent_recipes(5)
        
        if recent_recipes:
            for recipe in recent_recipes:
                if st.button(recipe['title'], key=f"recent_{recipe['recipe_id']}"):
                    st.session_state.selected_recipe = recipe
        else:
            st.write("No recent recipes yet.")
    
    # Main content area
    tab1, tab2 = st.tabs(["Generate Recipe", "Get Recipe by ID"])
    
    with tab1:
        st.header("Create New Recipe")
        
        # Ingredient input
        ingredients_input = st.text_area(
            "Enter ingredients (comma-separated):",
            placeholder="e.g., chicken, rice, tomatoes, onions",
            help="List all ingredients you have available"
        )
        
        # Additional options
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cuisine = st.selectbox(
                "Cuisine Style (optional):",
                ["", "Italian", "Mexican", "Chinese", "Indian", "Thai", 
                 "American", "Mediterranean", "Japanese", "French"]
            )
            cuisine = cuisine if cuisine else None
        
        with col2:
            dietary_options = st.multiselect(
                "Dietary Restrictions (optional):",
                ["Vegetarian", "Vegan", "Gluten-free", "Dairy-free", 
                 "Nut-free", "Keto", "Paleo", "Low-carb"]
            )
        
        with col3:
            cooking_time = st.slider(
                "Max Cooking Time (minutes):",
                min_value=10,
                max_value=240,
                value=60,
                step=5
            )
        
        # Generate button
        if st.button("Generate Recipe 🍳", type="primary"):
            if not ingredients_input.strip():
                st.warning("Please enter at least one ingredient.")
                return
            
            ingredients = [ing.strip() for ing in ingredients_input.split(',') if ing.strip()]
            
            with st.spinner("Generating your recipe... This may take a moment."):
                recipe = generate_recipe(
                    ingredients=ingredients,
                    cuisine=cuisine,
                    dietary_restrictions=dietary_options,
                    cooking_time=cooking_time
                )
                
                if recipe:
                    st.session_state.selected_recipe = recipe
                    st.success("Recipe generated successfully!")
    
    with tab2:
        st.header("Retrieve Existing Recipe")
        recipe_id = st.text_input("Enter Recipe ID:")
        
        if st.button("Get Recipe", key="get_recipe_btn"):
            if not recipe_id.strip():
                st.warning("Please enter a recipe ID.")
                return
            
            try:
                response = requests.get(f"{API_BASE_URL}/recipes/{recipe_id.strip()}")
                if response.status_code == 200:
                    st.session_state.selected_recipe = response.json()
                    st.success("Recipe found!")
                else:
                    st.error("Recipe not found. Please check the ID.")
            except requests.exceptions.RequestException:
                st.error("Error connecting to the API.")
    
    # Display selected recipe
    if 'selected_recipe' in st.session_state and st.session_state.selected_recipe:
        st.divider()
        display_recipe(st.session_state.selected_recipe)
        
        # Add download option
        recipe_json = json.dumps(st.session_state.selected_recipe, indent=2)
        st.download_button(
            label="Download Recipe as JSON",
            data=recipe_json,
            file_name=f"{st.session_state.selected_recipe['title'].replace(' ', '_')}.json",
            mime="application/json"
        )

if __name__ == "__main__":
    main()