"""
Email composer module for creating recipe recommendation emails.

This module takes recipe data and generates beautiful HTML emails
using Jinja2 templates.
"""

import os
import json
from datetime import datetime
from typing import List
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from src.models.database import Recipe

# Get project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PROJECT_ROOT / "templates"


def _parse_json_field(json_str: str) -> list:
    """
    Parse a JSON string field from the database.

    Args:
        json_str: JSON string

    Returns:
        Parsed list or empty list if parsing fails
    """
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {json_str[:50]}...")
        return []


def prepare_recipe_data(recipe: Recipe) -> dict:
    """
    Prepare recipe data for template rendering.

    Args:
        recipe: Recipe model instance

    Returns:
        Dictionary with formatted recipe data
    """
    return {
        "title": recipe.title,
        "image_url": recipe.image_url,
        "ready_in_minutes": recipe.ready_in_minutes,
        "servings": recipe.servings,
        "cuisine_type": recipe.cuisine_type,
        "difficulty": recipe.difficulty,
        "ingredients": _parse_json_field(recipe.ingredients),
        "instructions": _parse_json_field(recipe.instructions),
        "source_url": recipe.source_url,
    }


def compose_recipe_email(recipes: List[Recipe]) -> tuple[str, str]:
    """
    Compose an HTML email with recipe recommendations.

    Args:
        recipes: List of Recipe model instances (typically 2)

    Returns:
        Tuple of (subject, html_body)
    """
    if not recipes:
        raise ValueError("No recipes provided for email composition")

    # Prepare template data
    template_data = {
        "date": datetime.now().strftime("%A, %B %d, %Y"),
        "recipes": [prepare_recipe_data(recipe) for recipe in recipes],
    }

    # Load and render template
    try:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template("email_template.html")
        html_body = template.render(**template_data)

        # Create subject line
        if len(recipes) == 1:
            subject = f"Today's Dinner Recipe: {recipes[0].title}"
        else:
            recipe_names = " & ".join([r.title for r in recipes[:2]])
            subject = f"Your Daily Dinner Recipes - {datetime.now().strftime('%b %d')}"

        logger.info(f"Composed email with {len(recipes)} recipes")
        return subject, html_body

    except Exception as e:
        logger.error(f"Failed to compose email: {e}")
        raise


def create_plain_text_version(recipes: List[Recipe]) -> str:
    """
    Create a plain text version of the recipe email.

    Args:
        recipes: List of Recipe model instances

    Returns:
        Plain text email body
    """
    lines = [
        f"YOUR DAILY DINNER RECIPES - {datetime.now().strftime('%A, %B %d, %Y')}",
        "=" * 60,
        "",
    ]

    for idx, recipe in enumerate(recipes, 1):
        lines.append(f"RECIPE {idx}: {recipe.title.upper()}")
        lines.append("-" * 60)
        lines.append(f"Ready in: {recipe.ready_in_minutes} minutes")
        lines.append(f"Servings: {recipe.servings}")
        if recipe.cuisine_type:
            lines.append(f"Cuisine: {recipe.cuisine_type}")
        if recipe.difficulty:
            lines.append(f"Difficulty: {recipe.difficulty}")
        lines.append("")

        # Ingredients
        lines.append("INGREDIENTS:")
        ingredients = _parse_json_field(recipe.ingredients)
        for ing in ingredients:
            lines.append(f"  - {ing.get('original', 'N/A')}")
        lines.append("")

        # Instructions
        lines.append("INSTRUCTIONS:")
        instructions = _parse_json_field(recipe.instructions)
        for step in instructions:
            lines.append(f"  {step.get('number', '?')}. {step.get('step', 'N/A')}")
        lines.append("")

        if recipe.source_url:
            lines.append(f"Source: {recipe.source_url}")

        if idx < len(recipes):
            lines.append("")
            lines.append("=" * 60)
            lines.append("")

    # Rating instructions
    lines.extend(
        [
            "",
            "=" * 60,
            "RATE THESE RECIPES",
            "=" * 60,
            "",
            "Reply to this email with your ratings (1-5 stars):",
            f"Example: Recipe 1: 4, Recipe 2: 5",
            "",
        ]
    )

    return "\n".join(lines)


if __name__ == "__main__":
    # Test the email composer
    logger.add("logs/composer_test.log", rotation="1 day")

    from src.models.database import get_session
    from sqlalchemy import func

    print("Testing Email Composer...")
    print("-" * 50)

    # Get 2 random recipes from database
    session = get_session()
    recipes = session.query(Recipe).order_by(func.random()).limit(2).all()

    if not recipes:
        print("No recipes in database. Run the Spoonacular API client first.")
    else:
        print(f"\nComposing email with recipes:")
        for idx, recipe in enumerate(recipes, 1):
            print(f"  {idx}. {recipe.title}")

        # Compose email
        subject, html_body = compose_recipe_email(recipes)
        plain_body = create_plain_text_version(recipes)

        print(f"\nSubject: {subject}")
        print(f"\nHTML body length: {len(html_body)} characters")
        print(f"Plain text body length: {len(plain_body)} characters")

        # Save to files for inspection
        output_dir = PROJECT_ROOT / "logs"
        output_dir.mkdir(exist_ok=True)

        with open(output_dir / "sample_email.html", "w") as f:
            f.write(html_body)
        print(f"\n✅ HTML email saved to: {output_dir}/sample_email.html")

        with open(output_dir / "sample_email.txt", "w") as f:
            f.write(plain_body)
        print(f"✅ Plain text email saved to: {output_dir}/sample_email.txt")

    session.close()
    print("\n" + "-" * 50)
    print("Email composer test complete!")
