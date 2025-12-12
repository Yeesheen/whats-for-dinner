#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Create initial user if needed (optional)
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
