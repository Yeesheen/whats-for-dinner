"""
Weekly meal planner with ingredient optimization.

Selects 3 recipes for the week that minimize total unique ingredients
while respecting user preferences.
"""

from typing import List, Dict, Tuple
from itertools import combinations
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session
from loguru import logger

from src.models.database import Recipe, User, Recommendation, UserPreference
from src.recommender.ingredient_parser import count_ingredients_for_recipes, calculate_ingredient_savings, extract_unique_ingredients, extract_ingredients_with_details


def get_available_recipes(session: Session, user_id: int, days: int = 60) -> List[Recipe]:
    """
    Get recipes that haven't been sent recently and weren't rated poorly.

    Args:
        session: Database session
        user_id: User ID
        days: Number of days to look back for exclusion

    Returns:
        List of available Recipe instances
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get recently sent recipe IDs
    recent_recs = session.query(Recommendation.recipe_id).filter(
        and_(
            Recommendation.user_id == user_id,
            Recommendation.sent_at >= cutoff_date
        )
    ).all()
    recently_sent_ids = [r.recipe_id for r in recent_recs]

    # Get poorly rated recipe IDs (1-2 stars)
    low_rated = session.query(Recommendation.recipe_id).filter(
        and_(
            Recommendation.user_id == user_id,
            Recommendation.rated == True,
            Recommendation.rating <= 2
        )
    ).all()
    low_rated_ids = [r.recipe_id for r in low_rated]

    # Combine exclusion lists
    exclude_ids = list(set(recently_sent_ids + low_rated_ids))

    # Get available recipes
    query = session.query(Recipe)
    if exclude_ids:
        query = query.filter(~Recipe.id.in_(exclude_ids))

    return query.all()


def score_recipe_for_user(recipe: Recipe, user_preferences: List[UserPreference]) -> float:
    """
    Calculate a preference score for a recipe based on user preferences.

    Args:
        recipe: Recipe to score
        user_preferences: List of user preferences

    Returns:
        Preference score (higher is better)
    """
    score = 0.0

    # Create a lookup dict for faster access
    pref_lookup = {}
    for pref in user_preferences:
        key = (pref.preference_type, pref.preference_value)
        pref_lookup[key] = pref.score

    # Score based on cuisine
    if recipe.cuisine_type:
        score += pref_lookup.get(('cuisine_type', recipe.cuisine_type), 0.0)

    # Score based on dish type
    if recipe.dish_type:
        score += pref_lookup.get(('dish_type', recipe.dish_type), 0.0)

    # Score based on difficulty
    if recipe.difficulty:
        score += pref_lookup.get(('difficulty', recipe.difficulty), 0.0)

    # Score based on cooking time
    if recipe.ready_in_minutes:
        if recipe.ready_in_minutes < 30:
            time_bucket = "quick (<30min)"
        elif recipe.ready_in_minutes <= 60:
            time_bucket = "medium (30-60min)"
        else:
            time_bucket = "long (>60min)"
        score += pref_lookup.get(('cooking_time', time_bucket), 0.0)

    return score


def get_weekly_recommendations(
    session: Session,
    user_id: int,
    num_recipes: int = 3
) -> Tuple[List[Recipe], Dict]:
    """
    Get weekly recipe recommendations optimized for minimum ingredients.

    Algorithm:
    1. Get all available recipes (not sent recently)
    2. Score each recipe based on user preferences
    3. Consider all combinations of N recipes
    4. For each combination:
        - Calculate total unique ingredients
        - Calculate average preference score
        - Calculate combined score (preference weighted against ingredients)
    5. Return the combination with best combined score

    Args:
        session: Database session
        user_id: User ID
        num_recipes: Number of recipes to recommend (default 3)

    Returns:
        Tuple of (recipes, stats dict)
    """
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Get user preferences
    user_prefs = session.query(UserPreference).filter(
        UserPreference.user_id == user_id
    ).all()

    # Get available recipes
    available_recipes = get_available_recipes(session, user_id)

    if len(available_recipes) < num_recipes:
        raise ValueError(
            f"Not enough recipes available. Need {num_recipes}, have {len(available_recipes)}"
        )

    logger.info(f"Evaluating combinations from {len(available_recipes)} available recipes")

    # Convert Recipe objects to dicts for ingredient parser
    def recipe_to_dict(recipe: Recipe) -> Dict:
        return {
            'id': recipe.id,
            'title': recipe.title,
            'ingredients': recipe.ingredients,
            'cuisine_type': recipe.cuisine_type,
            'dish_type': recipe.dish_type,
            'difficulty': recipe.difficulty,
            'ready_in_minutes': recipe.ready_in_minutes,
        }

    # Score all recipes individually
    recipe_scores = {}
    for recipe in available_recipes:
        pref_score = score_recipe_for_user(recipe, user_prefs)
        recipe_scores[recipe.id] = pref_score

    # Evaluate all combinations of num_recipes
    best_combination = None
    best_score = float('-inf')
    best_stats = None

    # Limit combinations to evaluate (for performance)
    max_combinations = 10000
    total_combinations = len(list(combinations(range(len(available_recipes)), num_recipes)))

    if total_combinations > max_combinations:
        logger.warning(
            f"Too many combinations ({total_combinations}), will use greedy algorithm instead"
        )
        # Greedy algorithm: pick top recipes by preference, then optimize
        sorted_recipes = sorted(
            available_recipes,
            key=lambda r: recipe_scores[r.id],
            reverse=True
        )
        candidate_recipes = sorted_recipes[:min(50, len(sorted_recipes))]
    else:
        candidate_recipes = available_recipes

    for combo in combinations(candidate_recipes, num_recipes):
        # Calculate ingredient count
        combo_dicts = [recipe_to_dict(r) for r in combo]
        ingredient_count = count_ingredients_for_recipes(combo_dicts)

        # Calculate average preference score
        avg_pref_score = sum(recipe_scores[r.id] for r in combo) / num_recipes

        # Combined score:
        # - Prefer recipes with high preference scores
        # - Penalize combinations with many ingredients
        # Weight: preference score is more important, but ingredients matter too
        ingredient_penalty = (ingredient_count - user.max_ingredients_per_week) if ingredient_count > user.max_ingredients_per_week else 0
        combined_score = avg_pref_score - (ingredient_penalty * 0.5)

        if combined_score > best_score:
            best_score = combined_score
            best_combination = combo
            best_stats = {
                'ingredient_count': ingredient_count,
                'avg_preference_score': round(avg_pref_score, 2),
                'combined_score': round(combined_score, 2),
                'individual_scores': {r.id: recipe_scores[r.id] for r in combo}
            }

    if best_combination is None:
        # Fallback: just take top N by preference
        sorted_recipes = sorted(
            available_recipes,
            key=lambda r: recipe_scores[r.id],
            reverse=True
        )
        best_combination = sorted_recipes[:num_recipes]
        combo_dicts = [recipe_to_dict(r) for r in best_combination]
        ingredient_count = count_ingredients_for_recipes(combo_dicts)
        avg_pref_score = sum(recipe_scores[r.id] for r in best_combination) / num_recipes

        best_stats = {
            'ingredient_count': ingredient_count,
            'avg_preference_score': round(avg_pref_score, 2),
            'combined_score': round(avg_pref_score, 2),
            'individual_scores': {r.id: recipe_scores[r.id] for r in best_combination}
        }

    # Calculate detailed stats
    combo_dicts = [recipe_to_dict(r) for r in best_combination]
    savings_info = calculate_ingredient_savings(combo_dicts)
    unique_ingredients = extract_unique_ingredients(combo_dicts)
    detailed_ingredients = extract_ingredients_with_details(combo_dicts)

    best_stats.update({
        'savings': savings_info,
        'unique_ingredients': sorted(list(unique_ingredients)),
        'detailed_ingredients': detailed_ingredients,
        'max_ingredients_budget': user.max_ingredients_per_week,
        'within_budget': savings_info['total_ingredients'] <= user.max_ingredients_per_week
    })

    logger.info(
        f"Selected {num_recipes} recipes with {best_stats['ingredient_count']} ingredients "
        f"(budget: {user.max_ingredients_per_week})"
    )

    return list(best_combination), best_stats


if __name__ == "__main__":
    # Test the weekly planner
    from src.models.database import get_session

    logger.add("logs/weekly_planner_test.log", rotation="1 day")

    print("Testing Weekly Meal Planner")
    print("=" * 60)

    session = get_session()
    try:
        user_id = 1  # yeesheen@gmail.com

        # Get weekly recommendations
        recipes, stats = get_weekly_recommendations(session, user_id, num_recipes=3)

        print(f"\n✓ Generated weekly meal plan for user {user_id}")
        print(f"\nSelected Recipes:")
        for i, recipe in enumerate(recipes, 1):
            pref_score = stats['individual_scores'][recipe.id]
            print(f"  {i}. {recipe.title}")
            print(f"     Preference score: {pref_score:+.1f}")
            print(f"     Source: {recipe.source_website}")

        print(f"\nIngredient Analysis:")
        print(f"  Total unique ingredients: {stats['ingredient_count']}")
        print(f"  Budget: {stats['max_ingredients_budget']}")
        print(f"  Within budget: {'✓ Yes' if stats['within_budget'] else '✗ No'}")

        print(f"\n  If cooked separately: {stats['savings']['ingredients_if_separate']} ingredients")
        print(f"  Savings from overlap: {stats['savings']['savings']} ingredients ({stats['savings']['overlap_percentage']}%)")

        print(f"\nIngredient List ({len(stats['unique_ingredients'])} items):")
        for ing in stats['unique_ingredients'][:15]:  # Show first 15
            print(f"  - {ing}")
        if len(stats['unique_ingredients']) > 15:
            print(f"  ... and {len(stats['unique_ingredients']) - 15} more")

    finally:
        session.close()
