"""
Spoonacular API client for fetching recipe data.

This module provides functions to interact with the Spoonacular API,
including searching for recipes, fetching recipe details, and caching
results in the database.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv
from loguru import logger

from src.models.database import get_session, Recipe

# Load environment variables
load_dotenv()

# API Configuration
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")
SPOONACULAR_BASE_URL = "https://api.spoonacular.com/recipes"

# Rate limiting: 150 requests per day for free tier
# We'll cache aggressively to stay within limits


class SpoonacularAPIError(Exception):
    """Custom exception for Spoonacular API errors."""

    pass


def _make_api_request(endpoint: str, params: Dict) -> Dict:
    """
    Make a request to the Spoonacular API with error handling.

    Args:
        endpoint: API endpoint path
        params: Query parameters

    Returns:
        JSON response as dictionary

    Raises:
        SpoonacularAPIError: If API request fails
    """
    if not SPOONACULAR_API_KEY:
        raise SpoonacularAPIError(
            "SPOONACULAR_API_KEY not found in environment variables"
        )

    params["apiKey"] = SPOONACULAR_API_KEY
    url = f"{SPOONACULAR_BASE_URL}/{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error from Spoonacular API: {e}")
        logger.error(f"Response: {response.text}")
        raise SpoonacularAPIError(f"API request failed: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        raise SpoonacularAPIError(f"Network error: {e}")


def search_recipes(
    query: str = "",
    cuisine: Optional[str] = None,
    diet: Optional[str] = None,
    intolerances: Optional[List[str]] = None,
    type: Optional[str] = "main course",
    number: int = 10,
    add_recipe_information: bool = True,
) -> List[Dict]:
    """
    Search for recipes using various filters.

    Args:
        query: Search query (e.g., "pasta")
        cuisine: Cuisine type (e.g., "italian", "mexican")
        diet: Diet type (e.g., "vegetarian", "vegan")
        intolerances: List of intolerances (e.g., ["gluten", "dairy"])
        type: Meal type (e.g., "main course", "dessert")
        number: Number of recipes to return (max 100)
        add_recipe_information: Include detailed information

    Returns:
        List of recipe dictionaries
    """
    params = {
        "number": number,
        "addRecipeInformation": add_recipe_information,
        "fillIngredients": True,
    }

    if query:
        params["query"] = query
    if cuisine:
        params["cuisine"] = cuisine
    if diet:
        params["diet"] = diet
    if intolerances:
        params["intolerances"] = ",".join(intolerances)
    if type:
        params["type"] = type

    try:
        response = _make_api_request("complexSearch", params)
        recipes = response.get("results", [])
        logger.info(f"Found {len(recipes)} recipes matching criteria")
        return recipes
    except SpoonacularAPIError as e:
        logger.error(f"Failed to search recipes: {e}")
        return []


def get_recipe_details(recipe_id: int) -> Optional[Dict]:
    """
    Get detailed information about a specific recipe.

    Args:
        recipe_id: Spoonacular recipe ID

    Returns:
        Recipe details dictionary or None if not found
    """
    params = {
        "includeNutrition": True,
    }

    try:
        response = _make_api_request(f"{recipe_id}/information", params)
        logger.info(f"Fetched details for recipe {recipe_id}: {response.get('title')}")
        return response
    except SpoonacularAPIError as e:
        logger.error(f"Failed to fetch recipe {recipe_id}: {e}")
        return None


def _extract_recipe_data(recipe_data: Dict) -> Dict:
    """
    Extract and format recipe data for database storage.

    Args:
        recipe_data: Raw recipe data from API

    Returns:
        Formatted recipe dictionary
    """
    # Extract cuisine type
    cuisines = recipe_data.get("cuisines", [])
    cuisine_type = cuisines[0] if cuisines else None

    # Extract dish types
    dish_types = recipe_data.get("dishTypes", [])
    dish_type = dish_types[0] if dish_types else None

    # Estimate difficulty based on prep time and steps
    ready_in_minutes = recipe_data.get("readyInMinutes", 0)
    if ready_in_minutes < 30:
        difficulty = "easy"
    elif ready_in_minutes < 60:
        difficulty = "medium"
    else:
        difficulty = "hard"

    # Format instructions
    instructions = []
    analyzed_instructions = recipe_data.get("analyzedInstructions", [])
    if analyzed_instructions:
        for instruction_set in analyzed_instructions:
            for step in instruction_set.get("steps", []):
                instructions.append(
                    {"number": step.get("number"), "step": step.get("step")}
                )

    # Format ingredients
    ingredients = []
    for ingredient in recipe_data.get("extendedIngredients", []):
        ingredients.append(
            {
                "name": ingredient.get("name"),
                "amount": ingredient.get("amount"),
                "unit": ingredient.get("unit"),
                "original": ingredient.get("original"),
            }
        )

    return {
        "spoonacular_id": recipe_data.get("id"),
        "title": recipe_data.get("title"),
        "image_url": recipe_data.get("image"),
        "ready_in_minutes": ready_in_minutes,
        "servings": recipe_data.get("servings"),
        "cuisine_type": cuisine_type,
        "dish_type": dish_type,
        "difficulty": difficulty,
        "instructions": json.dumps(instructions),
        "ingredients": json.dumps(ingredients),
        "nutrition_data": json.dumps(recipe_data.get("nutrition", {})),
        "source_url": recipe_data.get("sourceUrl"),
    }


def cache_recipe(recipe_data: Dict) -> Optional[Recipe]:
    """
    Cache a recipe in the database.

    Args:
        recipe_data: Recipe data from API

    Returns:
        Recipe model instance or None if failed
    """
    session = get_session()

    try:
        # Check if recipe already exists
        spoonacular_id = recipe_data.get("id")
        existing_recipe = (
            session.query(Recipe)
            .filter(Recipe.spoonacular_id == spoonacular_id)
            .first()
        )

        if existing_recipe:
            logger.debug(f"Recipe {spoonacular_id} already cached")
            return existing_recipe

        # Extract and format recipe data
        formatted_data = _extract_recipe_data(recipe_data)

        # Create new recipe
        recipe = Recipe(**formatted_data)
        session.add(recipe)
        session.commit()

        logger.info(f"Cached recipe: {recipe.title} (ID: {spoonacular_id})")
        return recipe

    except Exception as e:
        logger.error(f"Failed to cache recipe: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_cached_recipe(spoonacular_id: int) -> Optional[Recipe]:
    """
    Get a recipe from the cache (database).

    Args:
        spoonacular_id: Spoonacular recipe ID

    Returns:
        Recipe model instance or None if not found
    """
    session = get_session()
    try:
        recipe = (
            session.query(Recipe)
            .filter(Recipe.spoonacular_id == spoonacular_id)
            .first()
        )
        return recipe
    finally:
        session.close()


def fetch_and_cache_recipes(
    count: int = 20,
    cuisine: Optional[str] = None,
    diet: Optional[str] = None,
) -> List[Recipe]:
    """
    Fetch recipes from API and cache them in database.

    Args:
        count: Number of recipes to fetch
        cuisine: Optional cuisine filter
        diet: Optional diet filter

    Returns:
        List of cached Recipe instances
    """
    # Search for recipes
    recipes = search_recipes(
        cuisine=cuisine, diet=diet, type="main course", number=count
    )

    if not recipes:
        logger.warning("No recipes found from API")
        return []

    cached_recipes = []
    for recipe_data in recipes:
        # If the search didn't include full details, fetch them
        if "analyzedInstructions" not in recipe_data:
            recipe_id = recipe_data.get("id")
            full_recipe = get_recipe_details(recipe_id)
            if full_recipe:
                recipe_data = full_recipe

        # Cache the recipe
        cached_recipe = cache_recipe(recipe_data)
        if cached_recipe:
            cached_recipes.append(cached_recipe)

    logger.info(f"Cached {len(cached_recipes)} new recipes")
    return cached_recipes


def get_random_cached_recipes(count: int = 2) -> List[Recipe]:
    """
    Get random recipes from the cache.

    Args:
        count: Number of recipes to retrieve

    Returns:
        List of Recipe instances
    """
    session = get_session()
    try:
        from sqlalchemy import func

        recipes = session.query(Recipe).order_by(func.random()).limit(count).all()
        return recipes
    finally:
        session.close()


if __name__ == "__main__":
    # Test the API client
    logger.add("logs/api_test.log", rotation="1 day")

    print("Testing Spoonacular API Client...")
    print("-" * 50)

    # Test 1: Search for recipes
    print("\n1. Searching for Italian recipes...")
    results = search_recipes(cuisine="italian", number=5)
    print(f"Found {len(results)} recipes")

    if results:
        # Test 2: Get recipe details
        recipe_id = results[0].get("id")
        print(f"\n2. Fetching details for recipe ID {recipe_id}...")
        details = get_recipe_details(recipe_id)
        if details:
            print(f"Recipe: {details.get('title')}")
            print(f"Ready in: {details.get('readyInMinutes')} minutes")

        # Test 3: Cache recipe
        print(f"\n3. Caching recipe...")
        cached = cache_recipe(details)
        if cached:
            print(f"Successfully cached: {cached.title}")

        # Test 4: Retrieve from cache
        print(f"\n4. Retrieving from cache...")
        from_cache = get_cached_recipe(recipe_id)
        if from_cache:
            print(f"Retrieved from cache: {from_cache.title}")

    # Test 5: Fetch and cache multiple recipes
    print(f"\n5. Fetching and caching 10 recipes...")
    cached_recipes = fetch_and_cache_recipes(count=10)
    print(f"Cached {len(cached_recipes)} recipes")

    # Test 6: Get random cached recipes
    print(f"\n6. Getting 2 random cached recipes...")
    random_recipes = get_random_cached_recipes(count=2)
    for recipe in random_recipes:
        print(f"  - {recipe.title} ({recipe.cuisine_type})")

    print("\n" + "-" * 50)
    print("API client test complete!")
