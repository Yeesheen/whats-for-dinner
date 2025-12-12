"""
Daily recipe recommendation sender.

This script is run daily (via launchd or manually) to:
1. Select 2 recipes using the recommendation engine
2. Compose an email with the recipes
3. Send the email to the user
4. Log the recommendations in the database for tracking
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.recommender.engine import recommend_recipes_for_user, get_or_create_user
from src.email_handler.composer import compose_recipe_email, create_plain_text_version
from src.email_handler.sender import send_email, EmailSendError
from src.models.database import get_session, Recommendation

# Load environment variables
load_dotenv()

USER_EMAIL = os.getenv("USER_EMAIL")


def log_recommendations(user_id: int, recipe_ids: list, message_id: str) -> None:
    """
    Log sent recommendations to the database.

    Args:
        user_id: User ID
        recipe_ids: List of recipe IDs that were sent
        message_id: Email Message-ID for tracking replies
    """
    session = get_session()
    try:
        for recipe_id in recipe_ids:
            recommendation = Recommendation(
                user_id=user_id,
                recipe_id=recipe_id,
                sent_at=datetime.utcnow(),
                email_message_id=message_id,
                rated=False,
            )
            session.add(recommendation)

        session.commit()
        logger.info(f"Logged {len(recipe_ids)} recommendations for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to log recommendations: {e}")
        session.rollback()
    finally:
        session.close()


def send_daily_recommendations(user_email: str = None) -> bool:
    """
    Send daily recipe recommendations to a user.

    Args:
        user_email: User's email address (defaults to USER_EMAIL from .env)

    Returns:
        True if successful, False otherwise
    """
    if user_email is None:
        user_email = USER_EMAIL

    if not user_email:
        logger.error("No user email provided")
        print("❌ Error: USER_EMAIL not set in .env file")
        return False

    try:
        logger.info(f"Starting daily recommendation send for {user_email}")
        print(f"Sending daily recommendations to {user_email}")
        print("-" * 50)

        # Step 1: Get or create user
        user = get_or_create_user(user_email)
        logger.info(f"User: {user.email} (ID: {user.id})")
        print(f"User: {user.email} (ID: {user.id})")

        # Step 2: Select recipes
        print("\nSelecting recipes...")
        recipes = recommend_recipes_for_user(user_email, count=2)

        if not recipes:
            logger.error("No recipes selected")
            print("❌ Error: No recipes available")
            return False

        print(f"Selected recipes:")
        for idx, recipe in enumerate(recipes, 1):
            print(f"  {idx}. {recipe.title}")
            logger.info(f"  Recipe {idx}: {recipe.title} (ID: {recipe.id})")

        # Step 3: Compose email
        print("\nComposing email...")
        subject, html_body = compose_recipe_email(recipes)
        plain_body = create_plain_text_version(recipes)
        logger.info(f"Email composed: {subject}")

        # Step 4: Send email
        print(f"\nSending email...")
        message_id = send_email(
            to_email=user_email,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
        )
        print(f"✅ Email sent successfully!")
        print(f"📧 Message-ID: {message_id}")
        logger.info(f"Email sent: Message-ID = {message_id}")

        # Step 5: Log recommendations
        print("\nLogging recommendations...")
        recipe_ids = [r.id for r in recipes]
        log_recommendations(user.id, recipe_ids, message_id)
        print("✅ Recommendations logged in database")

        print("\n" + "-" * 50)
        print("Daily recommendations sent successfully!")
        logger.info("Daily recommendation send completed successfully")
        return True

    except EmailSendError as e:
        logger.error(f"Email send failed: {e}")
        print(f"\n❌ Failed to send email: {e}")
        print("\nCheck your Gmail configuration in .env:")
        print("  - GMAIL_ADDRESS")
        print("  - GMAIL_APP_PASSWORD")
        return False

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return False


def main():
    """Main entry point for the daily send script."""
    # Set up logging
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "daily_send.log",
        rotation="1 week",
        retention="1 month",
        level="INFO",
    )

    print("\n" + "=" * 50)
    print("DAILY RECIPE RECOMMENDATIONS")
    print("=" * 50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50 + "\n")

    success = send_daily_recommendations()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
