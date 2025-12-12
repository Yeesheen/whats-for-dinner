"""
Ingredient parser for recipe recommendations.

Parses ingredient strings to extract base ingredients and
calculate total unique ingredients across multiple recipes.
"""

import re
from typing import List, Set, Dict
import json

# Common pantry staples that don't count toward ingredient budget
# Keep this conservative - only items truly everyone has on hand
PANTRY_STAPLES = {
    'salt', 'kosher salt', 'sea salt',
    # Only include "ground black pepper" not generic "pepper" or "black pepper"
    'ground black pepper', 'ground white pepper',
    'olive oil', 'vegetable oil', 'canola oil', 'cooking oil', 'oil',
    'butter', 'unsalted butter', 'salted butter',
    'water', 'ice', 'ice water',
    'sugar', 'brown sugar', 'white sugar', 'granulated sugar', 'powdered sugar',
    'flour', 'all-purpose flour', 'bread flour',
    'baking powder', 'baking soda',
    'vanilla', 'vanilla extract',
    # Common dried spices only (not fresh herbs)
    'garlic powder', 'onion powder',
}


def normalize_ingredient_name(ingredient_string: str) -> str:
    """
    Extract and normalize the base ingredient name from an ingredient string.

    Examples:
        "2 cups diced red onions" -> "onion"
        "1 (15oz) can black beans, drained" -> "black bean"
        "3 cloves garlic, minced" -> "garlic"
        "1/2 cup fresh basil leaves" -> "basil"

    Args:
        ingredient_string: Raw ingredient string from recipe

    Returns:
        Normalized base ingredient name
    """
    # Convert to lowercase
    text = ingredient_string.lower().strip()

    # Remove parentheses and their contents first
    text = re.sub(r'\([^)]*\)', '', text)

    # Remove quantities and measurements
    # Pattern matches: numbers, fractions, measurements
    measurements = [
        r'\d+[\s-]?\d*\/?\d*',  # Numbers and fractions (1, 1/2, 1-1/2, etc.)
        r'\b(cup|cups|tablespoon|tablespoons|teaspoon|teaspoons|tbsp|tsp|oz|ounce|ounces|pound|pounds|lb|lbs|gram|grams|g|kg|ml|l|litre|liter)\b',
        r'\b(can|cans|jar|jars|package|packages|bunch|bunches|clove|cloves|head|heads|pinch|dash|handful)\b',
        r'\b(to)\b',  # Remove "to" as in "1 to 2 cups"
    ]

    for pattern in measurements:
        text = re.sub(pattern, '', text)

    # Remove common preparation methods and descriptors
    prep_words = [
        r'\b(fresh|frozen|dried|canned|jarred|organic|raw|cooked)\b',
        r'\b(chopped|diced|minced|sliced|grated|shredded|crushed|whole|halved|quartered)\b',
        r'\b(finely|coarsely|roughly|thinly|thickly)\b',
        r'\b(optional|or to taste|to taste|as needed|for serving|for garnish)\b',
        r'\b(plus more|and|or)\b',
        r'[,;].*$',  # Remove everything after comma or semicolon
    ]

    for pattern in prep_words:
        text = re.sub(pattern, '', text)

    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Handle plurals - convert to singular
    # This is a simple approach; a more sophisticated version would use a lemmatizer
    if text.endswith('ies'):
        text = text[:-3] + 'y'  # berries -> berry
    elif text.endswith('oes'):
        text = text[:-2]  # tomatoes -> tomato
    elif text.endswith('ses'):
        text = text[:-2]  # lentils -> lentil (handles most cases)
    elif text.endswith('s') and len(text) > 3:
        text = text[:-1]  # onions -> onion

    # Remove articles
    text = re.sub(r'\b(a|an|the)\b', '', text).strip()

    return text


def is_pantry_staple(ingredient: str) -> bool:
    """
    Check if an ingredient is a pantry staple.

    Args:
        ingredient: Normalized ingredient name

    Returns:
        True if ingredient is a pantry staple
    """
    ingredient_lower = ingredient.lower().strip()

    # Direct match
    if ingredient_lower in PANTRY_STAPLES:
        return True

    # Word-boundary match for multi-word staples (e.g., "extra virgin olive oil" contains "olive oil")
    # But avoid matching "pepper" in "peppercorn" or "red pepper flake"
    for staple in PANTRY_STAPLES:
        # Only do substring matching if the staple has multiple words
        if ' ' in staple:
            if staple in ingredient_lower:
                return True
        else:
            # For single-word staples, require word boundaries
            pattern = r'\b' + re.escape(staple) + r'\b'
            if re.search(pattern, ingredient_lower):
                return True

    return False


def extract_quantity_from_ingredient(ingredient_string: str) -> str:
    """
    Extract the quantity portion from an ingredient string.

    Args:
        ingredient_string: Raw ingredient string

    Returns:
        Quantity string (e.g., "2 cups", "250g", "1 packet")
    """
    text = ingredient_string.strip()

    # Pattern to match quantity at the start: number + optional fraction + optional unit
    # Examples: "2", "1/2", "2 cups", "250g", "1 (15oz) can"
    quantity_pattern = r'^[\d\s\/\-\(\)\.]+(?:cup|cups|tablespoon|tablespoons|teaspoon|teaspoons|tbsp|tsp|oz|ounce|ounces|pound|pounds|lb|lbs|gram|grams|g|kg|ml|l|litre|liter|can|cans|jar|jars|package|packages|packet|packets|bunch|bunches|clove|cloves|head|heads)?'

    match = re.match(quantity_pattern, text, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    return ""


def extract_unique_ingredients(recipes: List[Dict]) -> Set[str]:
    """
    Extract unique ingredients from a list of recipes, excluding pantry staples.

    Args:
        recipes: List of recipe dictionaries with 'ingredients' field

    Returns:
        Set of unique ingredient names
    """
    unique_ingredients = set()

    for recipe in recipes:
        # Parse ingredients JSON if it's a string
        ingredients = recipe.get('ingredients', [])
        if isinstance(ingredients, str):
            try:
                ingredients = json.loads(ingredients)
            except:
                ingredients = []

        for ingredient in ingredients:
            # Get the original text
            if isinstance(ingredient, dict):
                original = ingredient.get('original', '')
            else:
                original = str(ingredient)

            # Normalize the ingredient name
            normalized = normalize_ingredient_name(original)

            # Skip if empty or pantry staple
            if normalized and not is_pantry_staple(normalized):
                unique_ingredients.add(normalized)

    return unique_ingredients


def extract_ingredients_with_details(recipes: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Extract ingredients with their quantities and source recipes.

    Args:
        recipes: List of recipe dictionaries with 'ingredients' and 'title' fields

    Returns:
        Dictionary mapping ingredient name to list of usage details:
        {
            'tomato': [
                {'recipe': 'Recipe 1', 'quantity': '2 cups', 'original': '2 cups diced tomatoes'},
                {'recipe': 'Recipe 2', 'quantity': '1 lb', 'original': '1 lb cherry tomatoes'}
            ]
        }
    """
    ingredients_map = {}

    for recipe in recipes:
        recipe_title = recipe.get('title', 'Unknown Recipe')

        # Parse ingredients JSON if it's a string
        ingredients = recipe.get('ingredients', [])
        if isinstance(ingredients, str):
            try:
                ingredients = json.loads(ingredients)
            except:
                ingredients = []

        for ingredient in ingredients:
            # Get the original text
            if isinstance(ingredient, dict):
                original = ingredient.get('original', '')
            else:
                original = str(ingredient)

            # Normalize the ingredient name
            normalized = normalize_ingredient_name(original)

            # Skip if empty or pantry staple
            if not normalized or is_pantry_staple(normalized):
                continue

            # Extract quantity
            quantity = extract_quantity_from_ingredient(original)

            # Add to map
            if normalized not in ingredients_map:
                ingredients_map[normalized] = []

            ingredients_map[normalized].append({
                'recipe': recipe_title,
                'quantity': quantity if quantity else 'as needed',
                'original': original
            })

    return ingredients_map


def count_ingredients_for_recipes(recipes: List[Dict]) -> int:
    """
    Count total unique ingredients needed for a list of recipes.

    Args:
        recipes: List of recipe dictionaries

    Returns:
        Count of unique ingredients (excluding pantry staples)
    """
    return len(extract_unique_ingredients(recipes))


def get_ingredient_overlap(recipe1: Dict, recipe2: Dict) -> Set[str]:
    """
    Find ingredients that appear in both recipes.

    Args:
        recipe1: First recipe dictionary
        recipe2: Second recipe dictionary

    Returns:
        Set of overlapping ingredients
    """
    ingredients1 = extract_unique_ingredients([recipe1])
    ingredients2 = extract_unique_ingredients([recipe2])

    return ingredients1.intersection(ingredients2)


def calculate_ingredient_savings(recipes: List[Dict]) -> Dict:
    """
    Calculate how many ingredients are saved by selecting these recipes together.

    Args:
        recipes: List of recipe dictionaries

    Returns:
        Dictionary with:
            - total_ingredients: Total unique ingredients
            - ingredients_if_separate: Sum of ingredients if recipes were separate
            - savings: Number of ingredients saved through overlap
            - overlap_percentage: Percentage of ingredients that overlap
    """
    total_ingredients = count_ingredients_for_recipes(recipes)

    # Calculate total if each recipe was made separately
    ingredients_if_separate = sum(
        count_ingredients_for_recipes([recipe]) for recipe in recipes
    )

    savings = ingredients_if_separate - total_ingredients
    overlap_percentage = (savings / ingredients_if_separate * 100) if ingredients_if_separate > 0 else 0

    return {
        'total_ingredients': total_ingredients,
        'ingredients_if_separate': ingredients_if_separate,
        'savings': savings,
        'overlap_percentage': round(overlap_percentage, 1)
    }


if __name__ == "__main__":
    # Test the ingredient parser
    test_ingredients = [
        "2 cups diced red onions",
        "1 (15oz) can black beans, drained",
        "3 cloves garlic, minced",
        "1/2 cup fresh basil leaves",
        "Salt and pepper to taste",
        "2 tablespoons olive oil",
        "1 pound cherry tomatoes, halved",
    ]

    print("Ingredient Parser Test")
    print("=" * 50)

    for ing in test_ingredients:
        normalized = normalize_ingredient_name(ing)
        is_staple = is_pantry_staple(normalized)
        print(f"{ing}")
        print(f"  → {normalized} {'(pantry staple)' if is_staple else ''}")

    print("\nUnique ingredients (excluding staples):")
    test_recipe = {'ingredients': [{'original': ing} for ing in test_ingredients]}
    unique = extract_unique_ingredients([test_recipe])
    for ing in sorted(unique):
        print(f"  - {ing}")

    print(f"\nTotal count: {len(unique)}")
