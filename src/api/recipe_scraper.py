"""
Recipe scraper for extracting recipes from URLs.

This module uses the recipe-scrapers library to extract structured recipe data
from popular recipe websites including Smitten Kitchen, Food52, NYT Cooking,
and many others.
"""

import json
from typing import Optional, Dict
from urllib.parse import urlparse
from recipe_scrapers import scrape_me
from loguru import logger
import requests
from bs4 import BeautifulSoup
import json as json_lib

from src.models.database import get_session, Recipe


class RecipeScraperError(Exception):
    """Custom exception for recipe scraping errors."""
    pass


def _extract_website_name(url: str) -> str:
    """
    Extract the website name from a URL.

    Args:
        url: Recipe URL

    Returns:
        Website name (e.g., "smittenkitchen.com", "food52.com")
    """
    parsed = urlparse(url)
    domain = parsed.netloc

    # Remove 'www.' prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]

    return domain


def _scrape_with_schema(url: str) -> Optional[Dict]:
    """
    Fallback scraper that extracts recipe data from schema.org structured data.

    Many recipe sites use JSON-LD format with schema.org Recipe vocabulary.
    This works as a fallback when the site isn't directly supported.

    Args:
        url: Recipe URL

    Returns:
        Dictionary containing recipe data or None if not found
    """
    try:
        logger.info(f"Attempting schema.org extraction from: {url}")

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for JSON-LD script tags with Recipe schema
        scripts = soup.find_all('script', type='application/ld+json')

        for script in scripts:
            try:
                data = json_lib.loads(script.string)

                # Handle both single recipe and array of items
                recipes = []
                if isinstance(data, list):
                    recipes = [item for item in data if item.get('@type') == 'Recipe']
                elif isinstance(data, dict):
                    if data.get('@type') == 'Recipe':
                        recipes = [data]
                    elif '@graph' in data:
                        recipes = [item for item in data['@graph'] if item.get('@type') == 'Recipe']

                if recipes:
                    recipe = recipes[0]  # Use first recipe found

                    # Extract data from schema
                    title = recipe.get('name', 'Unknown Recipe')
                    image_url = recipe.get('image')
                    if isinstance(image_url, list):
                        image_url = image_url[0] if image_url else None
                    if isinstance(image_url, dict):
                        image_url = image_url.get('url')

                    # Parse time (ISO 8601 duration format like "PT30M")
                    def parse_duration(duration_str):
                        if not duration_str:
                            return None
                        import re
                        # Match PT followed by hours/minutes
                        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?', str(duration_str))
                        if match:
                            hours = int(match.group(1) or 0)
                            minutes = int(match.group(2) or 0)
                            return hours * 60 + minutes
                        return None

                    total_time = parse_duration(recipe.get('totalTime'))
                    cook_time = parse_duration(recipe.get('cookTime'))
                    prep_time = parse_duration(recipe.get('prepTime'))

                    ready_in_minutes = total_time or cook_time or prep_time

                    # Parse servings/yield
                    servings = None
                    recipe_yield = recipe.get('recipeYield')
                    if recipe_yield:
                        import re
                        if isinstance(recipe_yield, list):
                            recipe_yield = recipe_yield[0]
                        match = re.search(r'\d+', str(recipe_yield))
                        if match:
                            servings = int(match.group())

                    # Get ingredients
                    ingredients = recipe.get('recipeIngredient', [])
                    formatted_ingredients = []
                    for i, ingredient in enumerate(ingredients, 1):
                        formatted_ingredients.append({
                            "name": ingredient,
                            "original": ingredient,
                            "order": i
                        })

                    # Get instructions
                    instructions_raw = recipe.get('recipeInstructions', [])
                    formatted_instructions = []

                    if isinstance(instructions_raw, str):
                        # Single string of instructions
                        instruction_lines = [line.strip() for line in instructions_raw.split('\n') if line.strip()]
                        for i, instruction in enumerate(instruction_lines, 1):
                            formatted_instructions.append({
                                "number": i,
                                "step": instruction
                            })
                    elif isinstance(instructions_raw, list):
                        # List of instruction objects or strings
                        for i, instruction in enumerate(instructions_raw, 1):
                            if isinstance(instruction, dict):
                                text = instruction.get('text', instruction.get('name', ''))
                            else:
                                text = str(instruction)
                            if text.strip():
                                formatted_instructions.append({
                                    "number": i,
                                    "step": text.strip()
                                })

                    # Get category/cuisine
                    cuisine_type = recipe.get('recipeCuisine')
                    if isinstance(cuisine_type, list):
                        cuisine_type = cuisine_type[0] if cuisine_type else None

                    category = recipe.get('recipeCategory')
                    if isinstance(category, list):
                        category = category[0] if category else None

                    logger.info(f"Successfully extracted recipe from schema: {title}")

                    return {
                        'title': title,
                        'image_url': image_url,
                        'ready_in_minutes': ready_in_minutes,
                        'servings': servings,
                        'cuisine_type': cuisine_type,
                        'dish_type': category or 'main course',
                        'ingredients': formatted_ingredients,
                        'instructions': formatted_instructions,
                    }

            except (json_lib.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing JSON-LD: {e}")
                continue

        return None

    except Exception as e:
        logger.error(f"Schema extraction failed: {e}")
        return None


def _scrape_smitten_kitchen(url: str) -> Optional[Dict]:
    """
    Custom scraper for Smitten Kitchen recipes.

    Smitten Kitchen uses Jetpack Recipe plugin with specific CSS classes.

    Args:
        url: Smitten Kitchen recipe URL

    Returns:
        Dictionary containing recipe data or None if not found
    """
    try:
        logger.info(f"Attempting Smitten Kitchen extraction from: {url}")

        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract title
        title_elem = soup.find('h1', class_='entry-title') or soup.find('h1')
        if not title_elem:
            return None
        title = title_elem.get_text().strip()

        # Look for Jetpack Recipe container (hrecipe or jetpack-recipe)
        recipe_container = soup.find('div', class_='jetpack-recipe') or \
                          soup.find('div', class_='hrecipe') or \
                          soup.find('div', class_='h-recipe')

        if not recipe_container:
            logger.info("No Jetpack recipe container found")
            return None

        # Extract ingredients
        ingredients = []
        ingredients_container = recipe_container.find('div', class_='jetpack-recipe-ingredients')
        if ingredients_container:
            # Find all p tags or li tags within the ingredients container
            ingredient_elems = ingredients_container.find_all(['p', 'li'])
            for elem in ingredient_elems:
                ingredient_text = elem.get_text(strip=True)
                if ingredient_text:
                    ingredients.append({
                        "name": ingredient_text,
                        "original": ingredient_text,
                        "order": len(ingredients) + 1
                    })

        if not ingredients:
            logger.info("No ingredients found")
            return None

        # Extract instructions
        instructions = []
        directions_container = recipe_container.find('div', class_='jetpack-recipe-directions') or \
                              recipe_container.find('div', class_='e-instructions')
        if directions_container:
            # Try structured elements first (p, li, ol)
            instruction_elems = directions_container.find_all(['p', 'li', 'ol'])
            if instruction_elems:
                for elem in instruction_elems:
                    if elem.name == 'ol':
                        # If it's an ordered list, get its list items
                        for li in elem.find_all('li'):
                            instruction_text = li.get_text(strip=True)
                            if instruction_text:
                                instructions.append({
                                    "number": len(instructions) + 1,
                                    "step": instruction_text
                                })
                    else:
                        instruction_text = elem.get_text(strip=True)
                        if instruction_text:
                            instructions.append({
                                "number": len(instructions) + 1,
                                "step": instruction_text
                            })
            else:
                # Fallback: Try splitting by <strong> tags first
                html_str = str(directions_container)
                parts = html_str.split('<strong>')

                for part in parts[1:]:  # Skip first part (before any strong tag)
                    # Extract text from this part
                    if '</strong>' in part:
                        heading, rest = part.split('</strong>', 1)
                        # Clean heading
                        heading = BeautifulSoup(heading, 'html.parser').get_text(strip=True)
                        # Clean rest
                        rest = BeautifulSoup(rest, 'html.parser').get_text(strip=True)
                        # Combine
                        full_text = f"{heading} {rest}".strip()
                        if full_text:
                            instructions.append({
                                "number": len(instructions) + 1,
                                "step": full_text
                            })

                # If still no instructions, treat each text block/paragraph as a step
                if not instructions:
                    # Get all text and split by newlines
                    full_text = directions_container.get_text()
                    # Split into paragraphs (by double newlines or single newlines)
                    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]

                    for para in paragraphs:
                        if para and len(para) > 20:  # Filter out very short strings
                            instructions.append({
                                "number": len(instructions) + 1,
                                "step": para
                            })

        if not instructions:
            logger.info("No instructions found")
            return None

        # Extract metadata
        servings = None
        ready_in_minutes = None

        # Try to get servings (look for "Servings:" or "Yield:")
        content_text = recipe_container.get_text()
        import re
        servings_match = re.search(r'(?:Servings?|Yield):\s*(\d+)', content_text, re.IGNORECASE)
        if servings_match:
            servings = int(servings_match.group(1))

        # Try to get time
        time_match = re.search(r'(\d+)\s*(?:minutes?|mins?)', content_text, re.IGNORECASE)
        if time_match:
            ready_in_minutes = int(time_match.group(1))

        # Extract image
        image_url = None
        # Try to find image in recipe container first
        img_elem = recipe_container.find('img')
        if img_elem:
            image_url = img_elem.get('src') or img_elem.get('data-src')

        # If no recipe image, try featured image
        if not image_url:
            featured_img = soup.find('img', class_='wp-post-image')
            if featured_img:
                image_url = featured_img.get('src') or featured_img.get('data-src')

        logger.info(f"Successfully extracted Smitten Kitchen recipe: {title}")

        return {
            'title': title,
            'image_url': image_url,
            'ready_in_minutes': ready_in_minutes,
            'servings': servings,
            'cuisine_type': None,
            'dish_type': 'main course',
            'ingredients': ingredients,
            'instructions': instructions,
        }

    except Exception as e:
        logger.error(f"Smitten Kitchen extraction failed: {e}")
        return None


def _scrape_dinner_a_love_story(url: str) -> Optional[Dict]:
    """
    Custom scraper for Dinner A Love Story recipes.

    DALS uses plain HTML without structured recipe markup. This is a "best effort"
    scraper that extracts title and basic content from blog-style posts.

    Args:
        url: Dinner A Love Story recipe URL

    Returns:
        Dictionary containing recipe data or None if not found
    """
    try:
        logger.info(f"Attempting Dinner A Love Story extraction from: {url}")

        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract title
        title_elem = soup.find('h1', class_='entry-title')
        if not title_elem:
            return None
        title = title_elem.get_text().strip()

        # Find the main content area
        content_area = soup.find('div', class_='post-content') or soup.find('div', class_='entry-content')
        if not content_area:
            logger.info("No content area found")
            return None

        # Extract all paragraphs
        paragraphs = content_area.find_all('p')

        # Try to separate ingredients from instructions
        ingredients = []
        instructions = []

        # Heuristic: Look for ingredient patterns (measurements, food words)
        ingredient_keywords = ['cup', 'tablespoon', 'teaspoon', 'pound', 'ounce', 'clove', 'bunch', 'package', 'can', 'lb', 'oz', 'tsp', 'tbsp']
        instruction_keywords = ['heat', 'cook', 'add', 'mix', 'stir', 'combine', 'place', 'pour', 'serve', 'cut', 'chop', 'slice']

        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 10:
                continue

            # Check if it looks like an ingredient line
            lower_text = text.lower()
            has_ingredient_keyword = any(keyword in lower_text for keyword in ingredient_keywords)
            has_instruction_keyword = any(keyword in lower_text for keyword in instruction_keywords)

            # If it has measurements but not many action words, likely an ingredient
            if has_ingredient_keyword and not has_instruction_keyword and len(text) < 150:
                # Split multi-line ingredients
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                for line in lines:
                    if len(line) > 5:
                        ingredients.append({
                            "name": line,
                            "original": line,
                            "order": len(ingredients) + 1
                        })
            # If it has numbered steps or action words, likely instructions
            elif text[0].isdigit() or has_instruction_keyword:
                instructions.append({
                    "number": len(instructions) + 1,
                    "step": text
                })

        # If we didn't find clear ingredients/instructions, just take all text
        if not ingredients and not instructions:
            logger.info("No clear structure found, using all paragraph text")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    # Use as instruction
                    instructions.append({
                        "number": len(instructions) + 1,
                        "step": text
                    })

        # Need at least some content
        if not instructions:
            logger.info("No usable content found")
            return None

        # If we have no ingredients, add a placeholder
        if not ingredients:
            ingredients.append({
                "name": "See recipe text for ingredients",
                "original": "See recipe text for ingredients",
                "order": 1
            })

        # Extract image
        image_url = None
        img_elem = content_area.find('img')
        if img_elem:
            image_url = img_elem.get('src')

        logger.info(f"Successfully extracted Dinner A Love Story recipe: {title}")

        return {
            'title': title,
            'image_url': image_url,
            'ready_in_minutes': None,
            'servings': None,
            'cuisine_type': None,
            'dish_type': 'main course',
            'ingredients': ingredients,
            'instructions': instructions,
        }

    except Exception as e:
        logger.error(f"Dinner A Love Story extraction failed: {e}")
        return None


def _estimate_difficulty(total_time: int, num_instructions: int) -> str:
    """
    Estimate recipe difficulty based on time and complexity.

    Args:
        total_time: Total time in minutes
        num_instructions: Number of instruction steps

    Returns:
        Difficulty level: "easy", "medium", or "hard"
    """
    # Simple heuristic based on time and steps
    if total_time < 30 and num_instructions <= 5:
        return "easy"
    elif total_time < 60 and num_instructions <= 10:
        return "medium"
    else:
        return "hard"


def scrape_recipe_from_url(url: str) -> Dict:
    """
    Scrape recipe data from a URL using recipe-scrapers library.

    Args:
        url: Recipe URL from supported websites

    Returns:
        Dictionary containing structured recipe data

    Raises:
        RecipeScraperError: If scraping fails or URL is not supported
    """
    try:
        logger.info(f"Scraping recipe from: {url}")

        # Check if it's Smitten Kitchen or Dinner A Love Story and use custom scraper
        website = _extract_website_name(url)
        recipe_data_dict = None

        if 'smittenkitchen.com' in website:
            logger.info("Detected Smitten Kitchen, using custom scraper")
            recipe_data_dict = _scrape_smitten_kitchen(url)
            if not recipe_data_dict:
                raise RecipeScraperError(f"Failed to scrape Smitten Kitchen recipe from {url}")
        elif 'dinneralovestory.com' in website:
            logger.info("Detected Dinner A Love Story, using custom scraper")
            recipe_data_dict = _scrape_dinner_a_love_story(url)
            if not recipe_data_dict:
                raise RecipeScraperError(f"Failed to scrape Dinner A Love Story recipe from {url}")

        # Try recipe-scrapers library first (if not Smitten Kitchen)
        if not recipe_data_dict:
            try:
                scraper = scrape_me(url)
            except Exception as e:
                logger.info(f"recipe-scrapers failed, trying schema fallback: {e}")
                # Try schema.org fallback
                recipe_data_dict = _scrape_with_schema(url)
                if not recipe_data_dict:
                    raise RecipeScraperError(f"All scraping methods failed for {url}")

        # If we used the schema fallback, format and return
        if recipe_data_dict:
            website = _extract_website_name(url)
            difficulty = _estimate_difficulty(
                recipe_data_dict.get('ready_in_minutes') or 30,
                len(recipe_data_dict.get('instructions', []))
            )

            return {
                "title": recipe_data_dict['title'],
                "image_url": recipe_data_dict.get('image_url'),
                "ready_in_minutes": recipe_data_dict.get('ready_in_minutes'),
                "servings": recipe_data_dict.get('servings'),
                "cuisine_type": recipe_data_dict.get('cuisine_type'),
                "dish_type": recipe_data_dict.get('dish_type', 'main course'),
                "difficulty": difficulty,
                "instructions": json.dumps(recipe_data_dict['instructions']),
                "ingredients": json.dumps(recipe_data_dict['ingredients']),
                "source_url": url,
                "source_website": website,
                "nutrition_data": json.dumps({}),
                "spoonacular_id": None,
            }

        # Otherwise use the scraper object

        # Extract basic information
        title = scraper.title()
        image_url = scraper.image()

        # Get timing information
        try:
            total_time = scraper.total_time()
        except Exception:
            total_time = None

        try:
            cook_time = scraper.cook_time()
        except Exception:
            cook_time = total_time  # Fallback to total time

        # Get servings/yields
        try:
            yields = scraper.yields()
        except Exception:
            yields = None

        # Parse servings from yields string (e.g., "4 servings" -> 4)
        servings = None
        if yields:
            # Try to extract number from yields string
            import re
            match = re.search(r'\d+', str(yields))
            if match:
                servings = int(match.group())

        # Get ingredients
        ingredients = scraper.ingredients()

        # Format ingredients as list of dicts
        formatted_ingredients = []
        for i, ingredient in enumerate(ingredients, 1):
            formatted_ingredients.append({
                "name": ingredient,
                "original": ingredient,
                "order": i
            })

        # Get instructions
        instructions_text = scraper.instructions()

        # Split instructions into steps (if they're in one block)
        instruction_lines = [
            line.strip()
            for line in instructions_text.split('\n')
            if line.strip()
        ]

        # Format instructions as list of dicts
        formatted_instructions = []
        for i, instruction in enumerate(instruction_lines, 1):
            formatted_instructions.append({
                "number": i,
                "step": instruction
            })

        # Try to get cuisine/category (not all sites support this)
        cuisine_type = None
        try:
            cuisine = scraper.cuisine()
            if cuisine:
                cuisine_type = cuisine if isinstance(cuisine, str) else cuisine[0]
        except Exception:
            pass

        # Try to get category/dish type
        dish_type = None
        try:
            category = scraper.category()
            if category:
                dish_type = category if isinstance(category, str) else category[0]
        except Exception:
            pass

        # Estimate difficulty
        difficulty = _estimate_difficulty(
            cook_time or 30,  # Default to 30 if no time available
            len(formatted_instructions)
        )

        # Get website name
        website = _extract_website_name(url)

        recipe_data = {
            "title": title,
            "image_url": image_url,
            "ready_in_minutes": cook_time,
            "servings": servings,
            "cuisine_type": cuisine_type,
            "dish_type": dish_type or "main course",  # Default to main course
            "difficulty": difficulty,
            "instructions": json.dumps(formatted_instructions),
            "ingredients": json.dumps(formatted_ingredients),
            "source_url": url,
            "source_website": website,
            "nutrition_data": json.dumps({}),  # Not extracted from scraped recipes
            "spoonacular_id": None,  # No Spoonacular ID for scraped recipes
        }

        logger.info(f"Successfully scraped recipe: {title} from {website}")
        return recipe_data

    except Exception as e:
        logger.error(f"Failed to scrape recipe from {url}: {e}")
        raise RecipeScraperError(f"Could not scrape recipe from {url}: {str(e)}")


def add_recipe_from_url(url: str) -> Optional[Recipe]:
    """
    Scrape a recipe from a URL and add it to the database.

    Args:
        url: Recipe URL

    Returns:
        Recipe model instance or None if failed
    """
    session = get_session()

    try:
        # Check if recipe URL already exists
        existing_recipe = (
            session.query(Recipe)
            .filter(Recipe.source_url == url)
            .first()
        )

        if existing_recipe:
            logger.info(f"Recipe from {url} already exists in database")
            print(f"✓ Recipe already in database: {existing_recipe.title}")
            return existing_recipe

        # Scrape the recipe
        recipe_data = scrape_recipe_from_url(url)

        # Create new recipe
        recipe = Recipe(**recipe_data)
        session.add(recipe)
        session.commit()

        logger.info(f"Added recipe to database: {recipe.title} (ID: {recipe.id})")
        print(f"✓ Successfully added: {recipe.title}")
        print(f"  Source: {recipe.source_website}")
        print(f"  Ingredients: {len(json.loads(recipe.ingredients))}")
        print(f"  Steps: {len(json.loads(recipe.instructions))}")

        return recipe

    except RecipeScraperError as e:
        logger.error(f"Failed to add recipe from URL: {e}")
        print(f"✗ Error: {e}")
        session.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error adding recipe: {e}")
        print(f"✗ Unexpected error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def list_supported_websites():
    """
    Print information about supported recipe websites.
    """
    print("\nSupported Recipe Websites:")
    print("-" * 50)

    print("\n✓ Confirmed to work:")
    print("  - Food52 (food52.com)")
    print("  - NYT Cooking (cooking.nytimes.com)")
    print("  - Serious Eats (seriouseats.com)")
    print("  - Bon Appétit (bonappetit.com)")
    print("  - Epicurious (epicurious.com)")

    print("\n✓ Likely to work (use standard schema):")
    print("  - Smitten Kitchen (smittenkitchen.com)")
    print("  - David Lebovitz (davidlebovitz.com)")
    print("  - Dinner A Love Story (dinneralovestory.com)")
    print("  - Amateur Gourmet (amateurgourmet.com)")

    print("\n✓ The library supports 200+ sites!")
    print("  See: https://github.com/hhursev/recipe-scrapers")

    print("\nUsage:")
    print("  python -m src.api.recipe_scraper <recipe_url>")
    print("\nExample:")
    print("  python -m src.api.recipe_scraper 'https://smittenkitchen.com/2024/01/pasta-e-ceci/'")
    print()


if __name__ == "__main__":
    import sys

    logger.add("logs/recipe_scraper.log", rotation="1 day")

    if len(sys.argv) < 2:
        print("\nRecipe URL Scraper")
        print("=" * 50)
        list_supported_websites()
        sys.exit(0)

    url = sys.argv[1]

    print("\nRecipe URL Scraper")
    print("=" * 50)
    print(f"\nScraping: {url}\n")

    recipe = add_recipe_from_url(url)

    if recipe:
        print(f"\n✓ Recipe added successfully!")
        print(f"  Database ID: {recipe.id}")
        print(f"  Title: {recipe.title}")
        print(f"  URL: {recipe.source_url}")
    else:
        print("\n✗ Failed to add recipe")
        sys.exit(1)
