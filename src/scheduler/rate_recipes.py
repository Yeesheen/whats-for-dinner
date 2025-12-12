"""
Manual recipe rating script.

This script allows users to manually rate recipes they've received,
which is useful for testing the preference learning system.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.database import get_session, Recommendation, Recipe, UserPreference
from src.recommender.preference_updater import process_ratings
from src.recommender.engine import get_or_create_user
from sqlalchemy import and_

# Load environment variables
load_dotenv()

USER_EMAIL = os.getenv("USER_EMAIL")


def get_unrated_recipes(user_id: int):
    """
    Get the most recent unrated recipe recommendations.

    Args:
        user_id: User ID

    Returns:
        List of (recommendation, recipe) tuples
    """
    session = get_session()
    try:
        # Get unrated recommendations with their recipes
        results = (
            session.query(Recommendation, Recipe)
            .join(Recipe, Recommendation.recipe_id == Recipe.id)
            .filter(
                and_(
                    Recommendation.user_id == user_id,
                    Recommendation.rated == False,
                )
            )
            .order_by(Recommendation.sent_at.desc(), Recommendation.id)
            .all()
        )

        # Group by sent_at to get the most recent batch
        if not results:
            return []

        most_recent_sent_at = results[0][0].sent_at
        batch = [
            (rec, recipe)
            for rec, recipe in results
            if rec.sent_at == most_recent_sent_at
        ]

        return batch

    finally:
        session.close()


def display_recipe(recipe: Recipe, number: int):
    """
    Display recipe information for rating.

    Args:
        recipe: Recipe instance
        number: Recipe number (1, 2, etc.)
    """
    print(f"\n{'=' * 60}")
    print(f"RECIPE {number}: {recipe.title}")
    print(f"{'=' * 60}")
    print(f"Cuisine: {recipe.cuisine_type or 'N/A'}")
    print(f"Dish Type: {recipe.dish_type or 'N/A'}")
    print(f"Ready in: {recipe.ready_in_minutes} minutes")
    print(f"Difficulty: {recipe.difficulty or 'N/A'}")


def get_rating_input(recipe_number: int, recipe_title: str) -> int:
    """
    Get rating input from user with validation.

    Args:
        recipe_number: Recipe number
        recipe_title: Recipe title for display

    Returns:
        Rating value (1-5)
    """
    while True:
        try:
            rating = input(f"\nRate Recipe {recipe_number} (1-5 stars): ")
            rating = int(rating)

            if 1 <= rating <= 5:
                return rating
            else:
                print("❌ Please enter a number between 1 and 5")

        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\n⚠️  Rating cancelled")
            sys.exit(0)


def show_preferences(user_id: int):
    """
    Display current user preferences.

    Args:
        user_id: User ID
    """
    session = get_session()
    try:
        preferences = (
            session.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .order_by(
                UserPreference.preference_type,
                UserPreference.score.desc()
            )
            .all()
        )

        if not preferences:
            print("\n📊 No preferences learned yet")
            return

        print("\n" + "=" * 60)
        print("YOUR CURRENT PREFERENCES")
        print("=" * 60)

        current_type = None
        for pref in preferences:
            if pref.preference_type != current_type:
                print(f"\n{pref.preference_type.replace('_', ' ').title()}:")
                current_type = pref.preference_type

            # Visual score indicator
            score_indicator = "+" * int(abs(pref.score)) if pref.score > 0 else "-" * int(abs(pref.score))
            print(f"  {pref.preference_value:.<30} {pref.score:+.1f} {score_indicator}")

    finally:
        session.close()


def main():
    """Main entry point for the rating script."""
    # Set up logging
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "rating.log",
        rotation="1 week",
        retention="1 month",
        level="INFO",
    )

    print("\n" + "=" * 60)
    print("RATE YOUR RECIPES")
    print("=" * 60)
    print(f"User: {USER_EMAIL}")
    print("=" * 60)

    if not USER_EMAIL:
        print("\n❌ Error: USER_EMAIL not set in .env file")
        sys.exit(1)

    # Get or create user
    user = get_or_create_user(USER_EMAIL)
    logger.info(f"Rating recipes for user: {user.email} (ID: {user.id})")

    # Get unrated recipes
    print("\nFetching unrated recipes...")
    unrated = get_unrated_recipes(user.id)

    if not unrated:
        print("\n✨ No unrated recipes found!")
        print("\nYou can send yourself new recipes with:")
        print("  python -m src.scheduler.send_daily")
        show_preferences(user.id)
        sys.exit(0)

    print(f"\nFound {len(unrated)} unrated recipe(s) from your last email")

    # Display recipes and collect ratings
    ratings = []
    for idx, (recommendation, recipe) in enumerate(unrated, 1):
        display_recipe(recipe, idx)
        rating = get_rating_input(idx, recipe.title)
        ratings.append((idx, rating))
        logger.info(f"User rated recipe {idx} ({recipe.title}): {rating}/5")

    # Confirm ratings
    print("\n" + "=" * 60)
    print("YOUR RATINGS:")
    print("=" * 60)
    for idx, (_, recipe) in enumerate(unrated, 1):
        rating = ratings[idx - 1][1]
        stars = "⭐" * rating
        print(f"  Recipe {idx}: {rating}/5 {stars}")
        print(f"    → {recipe.title}")

    # Process ratings
    print("\n" + "=" * 60)
    print("Processing ratings and updating preferences...")
    print("=" * 60)

    processed = process_ratings(user.id, ratings)

    if processed > 0:
        print(f"\n✅ Successfully processed {processed} rating(s)!")
        print("\n🧠 Learning from your feedback...")

        # Show updated preferences
        show_preferences(user.id)

        print("\n" + "=" * 60)
        print("Your preferences have been updated!")
        print("Future recommendations will adapt to your taste.")
        print("=" * 60)
    else:
        print("\n❌ Failed to process ratings")
        sys.exit(1)


if __name__ == "__main__":
    main()
