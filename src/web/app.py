"""
Flask web application for Recipe Recommender.

Provides a web interface for:
- Viewing recipe history and ratings
- Browsing all recipes in the database
- Rating recipes through a web form
- Viewing learned preferences
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from sqlalchemy.orm import joinedload
import json
import os
import sys
import secrets

# Add parent directory to path to import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.models.database import (
    get_session,
    User,
    Recipe,
    Recommendation,
    UserPreference,
    ShoppingList,
)
from src.recommender.preference_updater import update_preferences_from_rating
from src.recommender.weekly_planner import get_weekly_recommendations

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Helper function to get the default user (single-user system)
def get_default_user():
    session = get_session()
    user = session.query(User).first()
    session.close()
    return user


@app.route('/')
def home():
    """Dashboard with overview stats."""
    session = get_session()

    try:
        user = session.query(User).first()

        # Get stats
        total_recipes = session.query(Recipe).count()
        total_sent = session.query(Recommendation).filter(
            Recommendation.user_id == user.id
        ).count()
        total_rated = session.query(Recommendation).filter(
            Recommendation.user_id == user.id,
            Recommendation.rated == True
        ).count()

        # Get recent recommendations
        recent_recs = session.query(Recommendation).filter(
            Recommendation.user_id == user.id
        ).options(
            joinedload(Recommendation.recipe)
        ).order_by(
            desc(Recommendation.sent_at)
        ).limit(5).all()

        # Calculate average rating
        avg_rating_result = session.query(func.avg(Recommendation.rating)).filter(
            Recommendation.user_id == user.id,
            Recommendation.rated == True
        ).scalar()
        avg_rating = round(avg_rating_result, 1) if avg_rating_result else 0

        # Get top preferences
        top_prefs = session.query(UserPreference).filter(
            UserPreference.user_id == user.id
        ).order_by(
            desc(UserPreference.score)
        ).limit(5).all()

        stats = {
            'total_recipes': total_recipes,
            'total_sent': total_sent,
            'total_rated': total_rated,
            'avg_rating': avg_rating,
            'unrated_count': total_sent - total_rated,
        }

        return render_template(
            'home.html',
            stats=stats,
            recent_recs=recent_recs,
            top_prefs=top_prefs,
            user=user
        )
    finally:
        session.close()


@app.route('/recipes')
def recipes():
    """Browse all recipes in the database."""
    session = get_session()

    try:
        # Get filter parameters
        cuisine = request.args.get('cuisine')
        source = request.args.get('source')
        sort_by = request.args.get('sort', 'recent')  # recent, title, time

        # Build query
        query = session.query(Recipe)

        if cuisine:
            query = query.filter(Recipe.cuisine_type == cuisine)
        if source:
            query = query.filter(Recipe.source_website == source)

        # Sort
        if sort_by == 'title':
            query = query.order_by(Recipe.title)
        elif sort_by == 'time':
            query = query.order_by(Recipe.ready_in_minutes)
        else:  # recent
            query = query.order_by(desc(Recipe.cached_at))

        all_recipes = query.all()

        # Get unique cuisines and sources for filters
        cuisines = session.query(Recipe.cuisine_type).distinct().filter(
            Recipe.cuisine_type.isnot(None)
        ).all()
        cuisines = [c[0] for c in cuisines]

        sources = session.query(Recipe.source_website).distinct().filter(
            Recipe.source_website.isnot(None)
        ).all()
        sources = [s[0] for s in sources]

        return render_template(
            'recipes.html',
            recipes=all_recipes,
            cuisines=cuisines,
            sources=sources,
            current_cuisine=cuisine,
            current_source=source,
            current_sort=sort_by
        )
    finally:
        session.close()


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    """View detailed recipe information."""
    session = get_session()

    try:
        recipe = session.query(Recipe).filter(Recipe.id == recipe_id).first()

        if not recipe:
            flash('Recipe not found', 'error')
            return redirect(url_for('recipes'))

        # Parse JSON fields
        ingredients = json.loads(recipe.ingredients) if recipe.ingredients else []
        instructions = json.loads(recipe.instructions) if recipe.instructions else []

        # Get user's rating if exists
        user = session.query(User).first()
        recommendation = session.query(Recommendation).filter(
            Recommendation.user_id == user.id,
            Recommendation.recipe_id == recipe_id,
            Recommendation.rated == True
        ).first()

        user_rating = recommendation.rating if recommendation else None

        return render_template(
            'recipe_detail.html',
            recipe=recipe,
            ingredients=ingredients,
            instructions=instructions,
            user_rating=user_rating
        )
    finally:
        session.close()


@app.route('/history')
def history():
    """View recommendation history and ratings."""
    session = get_session()

    try:
        user = session.query(User).first()

        # Get filter parameters
        rated_filter = request.args.get('rated')  # 'all', 'rated', 'unrated'

        # Build query
        query = session.query(Recommendation).filter(
            Recommendation.user_id == user.id
        ).options(joinedload(Recommendation.recipe))

        if rated_filter == 'rated':
            query = query.filter(Recommendation.rated == True)
        elif rated_filter == 'unrated':
            query = query.filter(Recommendation.rated == False)

        recommendations = query.order_by(desc(Recommendation.sent_at)).all()

        return render_template(
            'history.html',
            recommendations=recommendations,
            rated_filter=rated_filter or 'all'
        )
    finally:
        session.close()


@app.route('/rate/<int:recommendation_id>', methods=['GET', 'POST'])
def rate(recommendation_id):
    """Rate a recipe from a recommendation."""
    session = get_session()

    try:
        recommendation = session.query(Recommendation).filter(
            Recommendation.id == recommendation_id
        ).options(joinedload(Recommendation.recipe)).first()

        if not recommendation:
            flash('Recommendation not found', 'error')
            return redirect(url_for('history'))

        if request.method == 'POST':
            rating = int(request.form.get('rating'))

            if rating < 1 or rating > 5:
                flash('Rating must be between 1 and 5 stars', 'error')
                return redirect(url_for('rate', recommendation_id=recommendation_id))

            # Update recommendation
            recommendation.rating = rating
            recommendation.rated = True
            recommendation.rated_at = datetime.utcnow()

            # Update preferences
            user = session.query(User).first()
            recipe = recommendation.recipe

            session.commit()

            # Update preferences (uses separate session internally)
            update_preferences_from_rating(user.id, recipe.id, rating)

            flash(f'Rated "{recipe.title}" with {rating} stars!', 'success')
            return redirect(url_for('history'))

        # GET request - show rating form
        return render_template(
            'rate.html',
            recommendation=recommendation
        )
    except Exception as e:
        session.rollback()
        flash(f'Error saving rating: {str(e)}', 'error')
        return redirect(url_for('history'))
    finally:
        session.close()


@app.route('/preferences')
def preferences():
    """View learned preferences."""
    session = get_session()

    try:
        user = session.query(User).first()

        # Get preferences grouped by type
        all_prefs = session.query(UserPreference).filter(
            UserPreference.user_id == user.id
        ).order_by(
            UserPreference.preference_type,
            desc(UserPreference.score)
        ).all()

        # Group by type
        prefs_by_type = {}
        for pref in all_prefs:
            if pref.preference_type not in prefs_by_type:
                prefs_by_type[pref.preference_type] = []
            prefs_by_type[pref.preference_type].append(pref)

        # Get rating phase info
        rated_count = session.query(Recommendation).filter(
            Recommendation.user_id == user.id,
            Recommendation.rated == True
        ).count()

        if rated_count == 0:
            phase = "Cold Start"
            phase_desc = "Random diverse recipes to learn your taste"
        elif rated_count < 20:
            phase = "Learning"
            phase_desc = f"{rated_count}/20 ratings - Building your preference profile"
        else:
            phase = "Personalized"
            phase_desc = f"{rated_count} ratings - Strong personalization active"

        return render_template(
            'preferences.html',
            prefs_by_type=prefs_by_type,
            phase=phase,
            phase_desc=phase_desc,
            rated_count=rated_count
        )
    finally:
        session.close()


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """User settings page."""
    session = get_session()

    try:
        user = session.query(User).first()

        if request.method == 'POST':
            # Update max ingredients setting
            max_ingredients = request.form.get('max_ingredients_per_week', type=int)

            if max_ingredients and max_ingredients > 0:
                user.max_ingredients_per_week = max_ingredients
                session.commit()
                flash(f'Settings saved! Max ingredients set to {max_ingredients}', 'success')
                return redirect(url_for('settings'))
            else:
                flash('Please enter a valid number greater than 0', 'error')

        return render_template('settings.html', user=user)
    except Exception as e:
        session.rollback()
        flash(f'Error saving settings: {str(e)}', 'error')
        return redirect(url_for('settings'))
    finally:
        session.close()


@app.route('/weekly-planner')
def weekly_planner():
    """Weekly meal planner with ingredient optimization."""
    session = get_session()

    try:
        user = session.query(User).first()

        # Get weekly recommendations
        try:
            recipes, stats = get_weekly_recommendations(session, user.id, num_recipes=3)

            # Convert recipes to list of dicts for easier template access
            recipe_list = []
            recipe_ids = []
            recipe_titles = []

            for recipe in recipes:
                ingredients = json.loads(recipe.ingredients) if recipe.ingredients else []
                instructions = json.loads(recipe.instructions) if recipe.instructions else []

                recipe_ids.append(recipe.id)
                recipe_titles.append(recipe.title)

                recipe_list.append({
                    'id': recipe.id,
                    'title': recipe.title,
                    'image_url': recipe.image_url,
                    'source_url': recipe.source_url,
                    'source_website': recipe.source_website,
                    'ready_in_minutes': recipe.ready_in_minutes,
                    'servings': recipe.servings,
                    'cuisine_type': recipe.cuisine_type,
                    'ingredients': ingredients,
                    'instructions': instructions,
                    'preference_score': stats['individual_scores'][recipe.id]
                })

            # Create or update shopping list
            # Deactivate old shopping lists
            session.query(ShoppingList).filter(
                ShoppingList.user_id == user.id,
                ShoppingList.is_active == True
            ).update({'is_active': False})

            # Prepare ingredients list with checkbox state
            ingredients_list = []
            for ing_name in sorted(stats['unique_ingredients']):
                details = stats['detailed_ingredients'].get(ing_name, [])
                quantities = [d['quantity'] for d in details]
                ingredients_list.append({
                    'name': ing_name,
                    'quantities': quantities,
                    'checked': False
                })

            # Create new shopping list
            share_token = secrets.token_urlsafe(16)
            shopping_list = ShoppingList(
                user_id=user.id,
                share_token=share_token,
                ingredients=json.dumps(ingredients_list),
                recipe_ids=json.dumps(recipe_ids),
                recipe_titles=json.dumps(recipe_titles),
                total_ingredients=stats['ingredient_count'],
                ingredient_budget=stats['max_ingredients_budget'],
                is_active=True
            )
            session.add(shopping_list)
            session.commit()

            # Generate shareable URL
            share_url = url_for('shopping_list', token=share_token, _external=True)

            return render_template(
                'weekly_planner.html',
                recipes=recipe_list,
                stats=stats,
                user=user,
                share_url=share_url
            )
        except ValueError as e:
            flash(str(e), 'error')
            return render_template('weekly_planner.html', recipes=[], stats=None, user=user, share_url=None)

    finally:
        session.close()


@app.route('/shopping/<token>')
def shopping_list(token):
    """Display shareable shopping list."""
    session = get_session()

    try:
        shopping_list = session.query(ShoppingList).filter(
            ShoppingList.share_token == token
        ).first()

        if not shopping_list:
            flash('Shopping list not found', 'error')
            return redirect(url_for('home'))

        # Parse JSON fields
        ingredients = json.loads(shopping_list.ingredients) if shopping_list.ingredients else []
        recipe_ids = json.loads(shopping_list.recipe_ids) if shopping_list.recipe_ids else []
        recipe_titles = json.loads(shopping_list.recipe_titles) if shopping_list.recipe_titles else []

        # Get user for context
        user = session.query(User).filter(User.id == shopping_list.user_id).first()

        return render_template(
            'shopping_list.html',
            shopping_list=shopping_list,
            ingredients=ingredients,
            recipe_titles=recipe_titles,
            token=token,
            user=user
        )
    finally:
        session.close()


@app.route('/api/shopping/<token>/update', methods=['POST'])
def update_shopping_list(token):
    """API endpoint to update checkbox states."""
    session = get_session()

    try:
        shopping_list = session.query(ShoppingList).filter(
            ShoppingList.share_token == token
        ).first()

        if not shopping_list:
            return jsonify({'error': 'Shopping list not found'}), 404

        # Get the updated ingredients from request
        data = request.get_json()
        if not data or 'ingredients' not in data:
            return jsonify({'error': 'Invalid request'}), 400

        # Update the ingredients
        shopping_list.ingredients = json.dumps(data['ingredients'])
        session.commit()

        return jsonify({'success': True})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.template_filter('parse_json')
def parse_json_filter(value):
    """Template filter to parse JSON strings."""
    try:
        return json.loads(value) if value else []
    except:
        return []


if __name__ == '__main__':
    app.run(debug=True, port=5000)
