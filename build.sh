#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create database tables first (handles the empty first migration)
python -c "
from src.models.database import create_db_engine, Base
engine = create_db_engine()
Base.metadata.create_all(engine)
print('Database tables created successfully')
"

# Run any additional migrations (for schema changes)
alembic stamp head  # Mark all migrations as applied since we created tables directly

# Create initial user if needed
python -c "
from src.models.database import get_session, User
session = get_session()
if session.query(User).count() == 0:
    user = User(email='user@example.com', timezone='America/Los_Angeles')
    session.add(user)
    session.commit()
    print('Created initial user')
else:
    print('User already exists')
session.close()
"
