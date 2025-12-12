"""
User preference updater.

This module updates user preferences based on recipe ratings.
Implements the scoring system that makes recommendations smarter over time.
"""

from datetime import datetime
from typing import List, Tuple
from sqlalchemy import and_
from loguru import logger

from src.models.database import (
    get_session,
    Recommendation,
    Recipe,
    UserPreference,
)


def calculate_score_delta(rating: int) -> float:
    """
    Calculate the preference score change based on rating.

    Rating impact:
    5 stars: +2.0
    4 stars: +1.0
    3 stars:  0.0 (neutral)
    2 stars: -1.0
    1 star:  -2.0

    Args:
        rating: Rating from 1-5

    Returns:
        Score delta to apply
    """
    return (rating - 3) * 1.0


def update_user_preference(
    user_id: int, preference_type: str, preference_value: str, score_delta: float
) -> None:
    """
    Update or create a user preference score.

    Args:
        user_id: User ID
        preference_type: Type of preference (e.g., 'cuisine_type', 'dish_type')
        preference_value: Value (e.g., 'Italian', 'main course')
        score_delta: Amount to adjust score by
    """
    if not preference_value:
        return  # Skip if value is None or empty

    session = get_session()
    try:
        # Find existing preference
        pref = (
            session.query(UserPreference)
            .filter(
                and_(
                    UserPreference.user_id == user_id,
                    UserPreference.preference_type == preference_type,
                    UserPreference.preference_value == preference_value,
                )
            )
            .first()
        )

        if pref:
            # Update existing preference
            pref.score += score_delta
            pref.last_updated = datetime.utcnow()
            logger.info(
                f"Updated {preference_type}='{preference_value}': "
                f"{pref.score - score_delta:.1f} → {pref.score:.1f} "
                f"(delta: {score_delta:+.1f})"
            )
        else:
            # Create new preference
            pref = UserPreference(
                user_id=user_id,
                preference_type=preference_type,
                preference_value=preference_value,
                score=score_delta,
            )
            session.add(pref)
            logger.info(
                f"Created {preference_type}='{preference_value}': "
                f"score = {score_delta:.1f}"
            )

        session.commit()

    except Exception as e:
        logger.error(f"Failed to update preference: {e}")
        session.rollback()
    finally:
        session.close()


def update_preferences_from_rating(
    user_id: int, recipe_id: int, rating: int
) -> None:
    """
    Update user preferences based on a single recipe rating.

    This extracts the recipe's attributes and updates preferences for:
    - Cuisine type
    - Dish type
    - Difficulty level
    - Cooking time bucket

    Args:
        user_id: User ID
        recipe_id: Recipe ID that was rated
        rating: Rating value (1-5)
    """
    session = get_session()
    try:
        # Get recipe details
        recipe = session.query(Recipe).filter(Recipe.id == recipe_id).first()

        if not recipe:
            logger.error(f"Recipe {recipe_id} not found")
            return

        logger.info(
            f"Updating preferences for user {user_id} based on "
            f"'{recipe.title}' (rating: {rating}/5)"
        )

        # Calculate score delta
        score_delta = calculate_score_delta(rating)

        # Update cuisine preference
        if recipe.cuisine_type:
            update_user_preference(
                user_id, "cuisine_type", recipe.cuisine_type, score_delta
            )

        # Update dish type preference
        if recipe.dish_type:
            update_user_preference(user_id, "dish_type", recipe.dish_type, score_delta)

        # Update difficulty preference
        if recipe.difficulty:
            update_user_preference(
                user_id, "difficulty", recipe.difficulty, score_delta
            )

        # Update cooking time preference
        if recipe.ready_in_minutes:
            if recipe.ready_in_minutes < 30:
                time_bucket = "quick (<30min)"
            elif recipe.ready_in_minutes <= 60:
                time_bucket = "medium (30-60min)"
            else:
                time_bucket = "long (>60min)"

            update_user_preference(
                user_id, "cooking_time", time_bucket, score_delta
            )

        logger.info(
            f"Preferences updated for user {user_id} based on recipe {recipe_id}"
        )

    finally:
        session.close()


def process_ratings(
    user_id: int, ratings: List[Tuple[int, int]], message_id: str = None
) -> int:
    """
    Process multiple ratings and update the database.

    Args:
        user_id: User ID
        ratings: List of (recipe_number, rating) tuples
        message_id: Optional email Message-ID to match recommendations

    Returns:
        Number of ratings successfully processed
    """
    session = get_session()
    processed_count = 0

    try:
        # Get all unrated recommendations for this user
        query = session.query(Recommendation).filter(
            and_(
                Recommendation.user_id == user_id,
                Recommendation.rated == False,
            )
        )

        if message_id:
            query = query.filter(Recommendation.email_message_id == message_id)

        # Get recommendations ordered by sent_at descending, then by id
        recommendations = query.order_by(
            Recommendation.sent_at.desc(), Recommendation.id
        ).all()

        if not recommendations:
            logger.warning(
                f"No unrated recommendations found for user {user_id}"
            )
            return 0

        # Group recommendations by sent_at to find the most recent batch
        from itertools import groupby
        grouped = []
        for sent_at, group in groupby(recommendations, key=lambda r: r.sent_at):
            grouped.append(list(group))

        # Get the most recent batch (first group after sorting by sent_at desc)
        most_recent_batch = grouped[0] if grouped else []

        logger.info(
            f"Found {len(most_recent_batch)} unrated recipes from most recent send"
        )

        # Process each rating
        for recipe_number, rating in ratings:
            logger.info(
                f"Processing rating: Recipe {recipe_number} = {rating}/5 stars"
            )

            # Match recipe by position (recipe_number)
            # recipe_number 1 = first recipe sent, 2 = second, etc.
            if recipe_number <= len(most_recent_batch):
                recommendation = most_recent_batch[recipe_number - 1]

                # Update recommendation with rating
                recommendation.rating = rating
                recommendation.rated = True
                recommendation.rated_at = datetime.utcnow()
                session.commit()

                logger.info(
                    f"Marked recommendation {recommendation.id} as rated "
                    f"(recipe: {recommendation.recipe_id}, rating: {rating})"
                )

                # Update user preferences based on this rating
                update_preferences_from_rating(
                    user_id, recommendation.recipe_id, rating
                )

                processed_count += 1
            else:
                logger.warning(
                    f"Recipe number {recipe_number} out of range "
                    f"(have {len(most_recent_batch)} recommendations)"
                )

        logger.info(f"Processed {processed_count}/{len(ratings)} ratings")
        return processed_count

    except Exception as e:
        logger.error(f"Error processing ratings: {e}")
        session.rollback()
        return processed_count
    finally:
        session.close()


if __name__ == "__main__":
    # Test the preference updater
    logger.add("logs/preference_test.log", rotation="1 day")

    print("Testing Preference Updater...")
    print("-" * 50)

    # Simulate rating the recipes we just sent
    print("\nSimulating ratings for most recent recommendations:")
    print("  Recipe 1: 5 stars (loved it!)")
    print("  Recipe 2: 3 stars (it was okay)")
    print()

    # Process the ratings
    user_id = 1  # yeesheen@gmail.com
    ratings = [(1, 5), (2, 3)]

    processed = process_ratings(user_id, ratings)
    print(f"\n✅ Processed {processed} ratings")

    # Show updated preferences
    session = get_session()
    preferences = (
        session.query(UserPreference)
        .filter(UserPreference.user_id == user_id)
        .order_by(UserPreference.preference_type, UserPreference.score.desc())
        .all()
    )

    print(f"\nUpdated preferences for user {user_id}:")
    current_type = None
    for pref in preferences:
        if pref.preference_type != current_type:
            print(f"\n{pref.preference_type.upper()}:")
            current_type = pref.preference_type
        print(f"  {pref.preference_value}: {pref.score:+.1f}")

    session.close()

    print("\n" + "-" * 50)
    print("Preference updater test complete!")
