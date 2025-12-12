"""
Recipe recommendation engine.

This module implements the core recommendation algorithm that selects
recipes based on user preferences and ratings.

Algorithm phases:
1. Cold start (0 ratings): Random with diversity
2. Learning (1-20 ratings): Preference-weighted with exploration
3. Personalized (20+ ratings): Strong preference matching
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy import func, and_, or_
from loguru import logger

from src.models.database import get_session, Recipe, Recommendation, UserPreference, User


class RecommendationEngine:
    """Main recommendation engine for selecting recipes."""

    def __init__(self, user_id: int):
        """
        Initialize recommendation engine for a specific user.

        Args:
            user_id: User ID to generate recommendations for
        """
        self.user_id = user_id
        self.session = get_session()

    def __del__(self):
        """Clean up database session."""
        if hasattr(self, "session"):
            self.session.close()

    def get_rating_count(self) -> int:
        """
        Get the total number of ratings the user has provided.

        Returns:
            Number of rated recipes
        """
        count = (
            self.session.query(Recommendation)
            .filter(
                and_(
                    Recommendation.user_id == self.user_id, Recommendation.rated == True
                )
            )
            .count()
        )
        return count

    def get_recently_sent_recipe_ids(self, days: int = 60) -> List[int]:
        """
        Get recipe IDs that were recently sent to avoid repeats.

        Args:
            days: Number of days to look back

        Returns:
            List of recipe IDs
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        recent_recommendations = (
            self.session.query(Recommendation.recipe_id)
            .filter(
                and_(
                    Recommendation.user_id == self.user_id,
                    Recommendation.sent_at >= cutoff_date,
                )
            )
            .all()
        )

        return [r.recipe_id for r in recent_recommendations]

    def get_low_rated_recipe_ids(self) -> List[int]:
        """
        Get recipe IDs that were rated poorly (1-2 stars) to avoid.

        Returns:
            List of recipe IDs
        """
        low_rated = (
            self.session.query(Recommendation.recipe_id)
            .filter(
                and_(
                    Recommendation.user_id == self.user_id,
                    Recommendation.rated == True,
                    Recommendation.rating <= 2,
                )
            )
            .all()
        )

        return [r.recipe_id for r in low_rated]

    def select_random_diverse_recipes(self, count: int = 2) -> List[Recipe]:
        """
        Select random recipes with cuisine diversity.
        Used for cold start phase.

        Args:
            count: Number of recipes to select

        Returns:
            List of Recipe instances
        """
        # Get recipes to exclude
        exclude_ids = self.get_recently_sent_recipe_ids(days=60)
        exclude_ids.extend(self.get_low_rated_recipe_ids())

        # Get all available recipes
        query = self.session.query(Recipe)
        if exclude_ids:
            query = query.filter(~Recipe.id.in_(exclude_ids))

        all_recipes = query.all()

        if len(all_recipes) <= count:
            logger.warning(f"Only {len(all_recipes)} recipes available")
            return all_recipes

        # Select recipes trying to maximize cuisine diversity
        selected = []
        used_cuisines = set()

        # Shuffle recipes
        import random
        shuffled = random.sample(all_recipes, len(all_recipes))

        # First pass: select recipes with different cuisines
        for recipe in shuffled:
            if len(selected) >= count:
                break

            cuisine = recipe.cuisine_type or "Unknown"
            if cuisine not in used_cuisines:
                selected.append(recipe)
                used_cuisines.add(cuisine)

        # Second pass: fill remaining slots if needed
        while len(selected) < count and len(shuffled) > len(selected):
            for recipe in shuffled:
                if recipe not in selected:
                    selected.append(recipe)
                    if len(selected) >= count:
                        break

        logger.info(
            f"Selected {len(selected)} random diverse recipes: "
            f"{[r.title for r in selected]}"
        )
        return selected

    def get_user_preferences(self) -> Dict[str, Dict[str, float]]:
        """
        Get user's preference scores organized by type.

        Returns:
            Dictionary mapping preference_type to {value: score}
        """
        preferences = (
            self.session.query(UserPreference)
            .filter(UserPreference.user_id == self.user_id)
            .all()
        )

        organized = {}
        for pref in preferences:
            if pref.preference_type not in organized:
                organized[pref.preference_type] = {}
            organized[pref.preference_type][pref.preference_value] = pref.score

        return organized

    def select_preference_based_recipes(
        self, count: int = 2, exploitation_ratio: float = 0.7
    ) -> List[Recipe]:
        """
        Select recipes based on learned preferences with exploration.
        Used for learning and personalized phases.

        Args:
            count: Number of recipes to select
            exploitation_ratio: Ratio of preference-based vs random (0.7 = 70% pref, 30% random)

        Returns:
            List of Recipe instances
        """
        exploitation_count = int(count * exploitation_ratio)
        exploration_count = count - exploitation_count

        # Get exclusion lists
        exclude_ids = self.get_recently_sent_recipe_ids(days=60)
        exclude_ids.extend(self.get_low_rated_recipe_ids())

        # Get user preferences
        preferences = self.get_user_preferences()

        selected = []

        # Exploitation: Select recipes matching preferences
        if exploitation_count > 0 and preferences:
            cuisine_prefs = preferences.get("cuisine_type", {})
            dish_prefs = preferences.get("dish_type", {})

            # Get preferred cuisines (positive scores)
            preferred_cuisines = [
                cuisine for cuisine, score in cuisine_prefs.items() if score > 0
            ]
            preferred_dishes = [
                dish for dish, score in dish_prefs.items() if score > 0
            ]

            # Query recipes matching preferences
            query = self.session.query(Recipe)
            if exclude_ids:
                query = query.filter(~Recipe.id.in_(exclude_ids))

            if preferred_cuisines or preferred_dishes:
                filters = []
                if preferred_cuisines:
                    filters.append(Recipe.cuisine_type.in_(preferred_cuisines))
                if preferred_dishes:
                    filters.append(Recipe.dish_type.in_(preferred_dishes))

                query = query.filter(or_(*filters))

            matching_recipes = query.all()

            if matching_recipes:
                import random
                selected = random.sample(
                    matching_recipes, min(exploitation_count, len(matching_recipes))
                )
                logger.info(
                    f"Selected {len(selected)} preference-based recipes: "
                    f"{[r.title for r in selected]}"
                )

        # Update exclusions with already selected recipes
        exclude_ids.extend([r.id for r in selected])

        # Exploration: Add random recipes for diversity
        if exploration_count > 0:
            query = self.session.query(Recipe)
            if exclude_ids:
                query = query.filter(~Recipe.id.in_(exclude_ids))

            available_recipes = query.all()

            if available_recipes:
                import random
                random_picks = random.sample(
                    available_recipes, min(exploration_count, len(available_recipes))
                )
                selected.extend(random_picks)
                logger.info(
                    f"Added {len(random_picks)} exploration recipes: "
                    f"{[r.title for r in random_picks]}"
                )

        return selected

    def select_recipes(self, count: int = 2) -> List[Recipe]:
        """
        Main method to select recipes using the appropriate algorithm phase.

        Args:
            count: Number of recipes to select

        Returns:
            List of Recipe instances
        """
        rating_count = self.get_rating_count()

        logger.info(
            f"Selecting {count} recipes for user {self.user_id} "
            f"(ratings: {rating_count})"
        )

        if rating_count == 0:
            # Phase 1: Cold start
            logger.info("Using cold start algorithm (random diverse)")
            return self.select_random_diverse_recipes(count)

        elif rating_count < 20:
            # Phase 2: Learning
            logger.info("Using learning algorithm (70% preference, 30% exploration)")
            return self.select_preference_based_recipes(
                count, exploitation_ratio=0.7
            )

        else:
            # Phase 3: Personalized
            logger.info(
                "Using personalized algorithm (80% preference, 20% exploration)"
            )
            return self.select_preference_based_recipes(
                count, exploitation_ratio=0.8
            )


def get_or_create_user(email: str) -> User:
    """
    Get existing user or create a new one.

    Args:
        email: User's email address

    Returns:
        User instance
    """
    session = get_session()
    try:
        user = session.query(User).filter(User.email == email).first()

        if not user:
            user = User(email=email, active=True)
            session.add(user)
            session.commit()
            session.refresh(user)  # Refresh to load the ID
            logger.info(f"Created new user: {email}")

        # Store user_id before closing session
        user_id = user.id
        user_email = user.email

        # Close session
        session.close()

        # Return fresh user object from new session
        new_session = get_session()
        return new_session.query(User).filter(User.id == user_id).first()
    except:
        session.close()
        raise


def recommend_recipes_for_user(email: str, count: int = 2) -> List[Recipe]:
    """
    High-level function to recommend recipes for a user by email.

    Args:
        email: User's email address
        count: Number of recipes to recommend

    Returns:
        List of Recipe instances
    """
    user = get_or_create_user(email)
    engine = RecommendationEngine(user.id)

    try:
        recipes = engine.select_recipes(count)
        logger.info(
            f"Recommended {len(recipes)} recipes for {email}: "
            f"{[r.title for r in recipes]}"
        )
        return recipes
    finally:
        del engine


if __name__ == "__main__":
    # Test the recommendation engine
    logger.add("logs/recommender_test.log", rotation="1 day")

    print("Testing Recommendation Engine...")
    print("-" * 50)

    import os
    from dotenv import load_dotenv

    load_dotenv()
    user_email = os.getenv("USER_EMAIL", "test@example.com")

    print(f"\nUser: {user_email}")

    # Get or create user
    user = get_or_create_user(user_email)
    print(f"User ID: {user.id}")

    # Create engine
    engine = RecommendationEngine(user.id)

    # Check rating count
    rating_count = engine.get_rating_count()
    print(f"Ratings provided: {rating_count}")

    # Select recipes
    print(f"\nSelecting 2 recipes...")
    recipes = engine.select_recipes(2)

    print(f"\nRecommended recipes:")
    for idx, recipe in enumerate(recipes, 1):
        print(f"  {idx}. {recipe.title}")
        print(f"     Cuisine: {recipe.cuisine_type}")
        print(f"     Ready in: {recipe.ready_in_minutes} min")

    print("\n" + "-" * 50)
    print("Recommendation engine test complete!")
