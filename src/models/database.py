"""
Database models for the Recipe Recommendation System.

This module defines the SQLAlchemy models for users, recipes, recommendations,
user preferences, and email logging.
"""

from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    Text,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

Base = declarative_base()


class User(Base):
    """
    User model for storing user information.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    timezone = Column(String(50), default="America/Los_Angeles")
    active = Column(Boolean, default=True)
    max_ingredients_per_week = Column(Integer, default=20)  # Max unique ingredients for weekly meal planning
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    recommendations = relationship("Recommendation", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user")
    email_logs = relationship("EmailLog", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', active={self.active})>"


class Recipe(Base):
    """
    Recipe model for storing recipes from Spoonacular API or scraped from URLs.
    """

    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    spoonacular_id = Column(Integer, unique=True, nullable=True)  # Nullable for scraped recipes
    title = Column(String(500), nullable=False)
    image_url = Column(Text)
    ready_in_minutes = Column(Integer)
    servings = Column(Integer)
    cuisine_type = Column(String(100))
    dish_type = Column(String(100))
    difficulty = Column(String(50))
    instructions = Column(Text)  # JSON array of steps
    ingredients = Column(Text)  # JSON array of ingredients
    nutrition_data = Column(Text)  # JSON object
    source_url = Column(Text)
    source_website = Column(String(255))  # e.g., "smittenkitchen.com", "food52.com"
    cached_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    recommendations = relationship("Recommendation", back_populates="recipe")

    # Indexes for faster queries
    __table_args__ = (
        Index("idx_cuisine", "cuisine_type"),
        Index("idx_dish_type", "dish_type"),
    )

    def __repr__(self):
        return f"<Recipe(id={self.id}, title='{self.title}', cuisine='{self.cuisine_type}')>"


class Recommendation(Base):
    """
    Recommendation model for tracking what recipes were sent to users.
    """

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    email_message_id = Column(String(255))  # For tracking replies
    rated = Column(Boolean, default=False)
    rating = Column(
        Integer, CheckConstraint("rating >= 1 AND rating <= 5"), nullable=True
    )
    rated_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="recommendations")
    recipe = relationship("Recipe", back_populates="recommendations")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_user_sent", "user_id", "sent_at"),
        Index("idx_rated", "rated"),
        UniqueConstraint("user_id", "recipe_id", "sent_at", name="uq_user_recipe_sent"),
    )

    def __repr__(self):
        return f"<Recommendation(id={self.id}, user_id={self.user_id}, recipe_id={self.recipe_id}, rated={self.rated})>"


class UserPreference(Base):
    """
    User preference model for storing learned preferences from ratings.
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    preference_type = Column(
        String(50), nullable=False
    )  # 'cuisine', 'dish_type', 'difficulty', etc.
    preference_value = Column(String(100), nullable=False)
    score = Column(Float, default=0.0)  # Weighted score based on ratings
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="preferences")

    # Unique constraint: one preference per type/value combination per user
    __table_args__ = (
        UniqueConstraint(
            "user_id", "preference_type", "preference_value", name="uq_user_preference"
        ),
    )

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id}, type='{self.preference_type}', value='{self.preference_value}', score={self.score})>"


class ShoppingList(Base):
    """
    Shareable shopping list model for weekly meal planning.
    Stores ingredients with a unique token for sharing.
    """

    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    share_token = Column(String(32), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)  # Only one active list per user

    # Shopping list data (JSON)
    ingredients = Column(Text, nullable=False)  # JSON: [{"name": "...", "quantity": "...", "checked": false}]
    recipe_ids = Column(Text)  # JSON: [1, 2, 3]
    recipe_titles = Column(Text)  # JSON: ["Recipe 1", "Recipe 2", "Recipe 3"]

    # Stats
    total_ingredients = Column(Integer)
    ingredient_budget = Column(Integer)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<ShoppingList(id={self.id}, token='{self.share_token}', active={self.is_active})>"


class EmailLog(Base):
    """
    Email log model for debugging and tracking email processing.
    """

    __tablename__ = "email_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    email_subject = Column(String(500))
    email_from = Column(String(255))
    processed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50))  # 'success', 'parse_error', 'invalid_rating', etc.
    raw_body = Column(Text)
    parsed_data = Column(Text)  # JSON

    # Relationships
    user = relationship("User", back_populates="email_logs")

    def __repr__(self):
        return f"<EmailLog(id={self.id}, status='{self.status}', processed_at={self.processed_at})>"


# Database connection and session management
def get_database_url():
    """Get database URL from environment or use default SQLite."""
    database_url = os.getenv("DATABASE_URL", "sqlite:///recipe_recommender.db")

    # Render/Heroku use postgres:// but SQLAlchemy requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def create_db_engine():
    """Create and return a database engine."""
    database_url = get_database_url()
    return create_engine(database_url, echo=False)


def create_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def get_session():
    """Create and return a database session."""
    engine = create_db_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_database():
    """Initialize the database by creating all tables."""
    engine = create_db_engine()
    create_tables(engine)
    print(f"Database initialized successfully at: {get_database_url()}")


if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
