# Recipe Recommender 🍽️

A personalized recipe recommendation system that emails you 2 dinner recipes daily, learns from your ratings, and adapts to your taste over time.

**NEW:** Now supports adding recipes from your favorite cooking blogs! Scrape recipes from Smitten Kitchen, Food52, NYT Cooking, and 200+ other sites.

## Features

- 🤖 **Smart Recommendations** - 3-phase algorithm that learns your preferences
- 📧 **Beautiful Emails** - HTML emails with photos, ingredients, and step-by-step instructions
- 🌐 **Web Dashboard** - Browse recipes, view history, and rate recipes in your browser
- ⭐ **Rating System** - Rate recipes 1-5 stars via simple email replies or manual entry
- 🧠 **Preference Learning** - System adapts based on your ratings
- 🔄 **No Repeats** - Avoids sending the same recipes within 60 days
- 🎯 **Cuisine Diversity** - Ensures variety in recommendations

## How It Works

### Recommendation Phases

1. **Cold Start (0 ratings)** - Random diverse recipes to learn your taste
2. **Learning (1-20 ratings)** - 70% match preferences, 30% explore new options
3. **Personalized (20+ ratings)** - 80% strong preference matching, 20% exploration

### Rating Impact

- ⭐⭐⭐⭐⭐ (5 stars): +2.0 preference score - Love it!
- ⭐⭐⭐⭐ (4 stars): +1.0 preference score - Like it
- ⭐⭐⭐ (3 stars): 0.0 preference score - Neutral
- ⭐⭐ (2 stars): -1.0 preference score - Dislike
- ⭐ (1 star): -2.0 preference score - Avoid

## Setup

### Prerequisites

- Python 3.9+
- Gmail account with 2FA enabled
- (Optional) Spoonacular API key if using Spoonacular integration

### Installation

1. **Clone and navigate to the project:**
   ```bash
   cd /Users/yeesheen/projects/recipe-recommender
   ```

2. **Create virtual environment and install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Set up configuration:**
   ```bash
   cp .env.example .env
   ```

4. **Edit `.env` with your credentials:**
   ```bash
   # Spoonacular API
   SPOONACULAR_API_KEY=your_api_key_here

   # Gmail Configuration
   GMAIL_ADDRESS=your.email@gmail.com
   GMAIL_APP_PASSWORD=your_16_char_app_password

   # User Configuration
   USER_EMAIL=your.email@gmail.com
   USER_TIMEZONE=America/Los_Angeles

   # Database
   DATABASE_URL=sqlite:///recipe_recommender.db
   ```

### Getting API Keys

#### Spoonacular API Key
1. Go to https://spoonacular.com/food-api
2. Click "Get Access" or "Start Now"
3. Sign up for a free account
4. Copy your API key from the dashboard

#### Gmail App Password
1. Enable 2FA on your Gmail account
2. Go to https://myaccount.google.com/apppasswords
3. Select "Mail" and your device
4. Click "Generate"
5. Copy the 16-character password (no spaces)

### Initialize Database

```bash
source venv/bin/activate
python -m src.models.database
```

### Add Recipes

You can add recipes in two ways:

#### Option 1: Add Recipes from URLs (Recommended)

Add recipes from your favorite cooking websites by URL:

```bash
source venv/bin/activate
python -m src.api.recipe_scraper 'https://smittenkitchen.com/2024/01/pasta-e-ceci/'
```

**Supported websites include:**
- Smitten Kitchen (smittenkitchen.com)
- Food52 (food52.com)
- NYT Cooking (cooking.nytimes.com)
- Dinner A Love Story (dinneralovestory.com)
- David Lebovitz (davidlebovitz.com)
- Amateur Gourmet (amateurgourmet.com)
- 200+ other recipe sites

To see all supported sites:
```bash
python -m src.api.recipe_scraper
```

#### Option 2: Fetch from Spoonacular API

```bash
source venv/bin/activate
python -m src.api.spoonacular_client
```

This fetches and caches 10 recipes from Spoonacular (requires API key).

## Usage

### Web Interface (NEW!)

Access the web dashboard to browse recipes, view history, and rate recipes:

```bash
source venv/bin/activate
python -m src.web.app
```

Then open your browser to: **http://localhost:5000**

**Features:**
- 📊 **Dashboard** - View stats, recent recommendations, and top preferences
- 📚 **Recipe Browser** - Browse all 26 recipes with filters for cuisine and source
- 📜 **History** - View all past recommendations and rate them
- ⭐ **Rate Recipes** - Easy web form to rate recipes 1-5 stars
- 🧠 **Preferences** - See what the system has learned about your taste

The web interface complements your daily emails - emails still arrive at 9 AM, but you can use the web app to browse, rate backlog, and understand the system better.

### Manual Usage

#### Send Daily Recipes

```bash
source venv/bin/activate
python -m src.scheduler.send_daily
```

This will:
1. Select 2 recipes based on your preferences
2. Compose a beautiful HTML email
3. Send it to your USER_EMAIL
4. Log the recommendations in the database

#### Rate Recipes

```bash
source venv/bin/activate
python -m src.scheduler.rate_recipes
```

This interactive script will:
1. Show your unrated recipes
2. Ask for ratings (1-5 stars)
3. Update your preference profile
4. Display your updated preferences

#### Check Your Preferences

```bash
source venv/bin/activate
python -c "
from src.models.database import get_session, UserPreference
session = get_session()
prefs = session.query(UserPreference).filter(UserPreference.user_id==1).all()
for p in prefs:
    print(f'{p.preference_type}: {p.preference_value} = {p.score:+.1f}')
session.close()
"
```

### Automated Daily Emails (macOS)

Set up launchd to automatically send recipes at 9 AM daily:

1. **Copy launchd plist files:**
   ```bash
   cp config/com.user.recipe-recommender.send.plist ~/Library/LaunchAgents/
   ```

2. **Load the service:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.user.recipe-recommender.send.plist
   ```

3. **Verify it's running:**
   ```bash
   launchctl list | grep recipe-recommender
   ```

4. **To stop:**
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.user.recipe-recommender.send.plist
   ```

## Project Structure

```
recipe-recommender/
├── src/
│   ├── models/
│   │   └── database.py          # SQLAlchemy models
│   ├── api/
│   │   ├── spoonacular_client.py # Recipe API integration (optional)
│   │   └── recipe_scraper.py    # URL-based recipe scraping
│   ├── email_handler/
│   │   ├── sender.py            # Gmail SMTP sender
│   │   ├── composer.py          # Email template rendering
│   │   └── parser.py            # Rating extraction
│   ├── recommender/
│   │   ├── engine.py            # Recommendation algorithm
│   │   └── preference_updater.py # Learning system
│   └── scheduler/
│       ├── send_daily.py        # Daily send script
│       └── rate_recipes.py      # Manual rating script
├── templates/
│   └── email_template.html      # Recipe email template
├── config/
│   └── *.plist                  # launchd configurations
├── alembic/                     # Database migrations
├── logs/                        # Application logs
├── .env                         # Configuration (not in git)
├── .env.example                 # Configuration template
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Database Schema

### Tables

- **users** - User accounts and settings
- **recipes** - Cached recipes from Spoonacular
- **recommendations** - Tracks sent recipes and ratings
- **user_preferences** - Learned taste preferences
- **email_log** - Email processing history (for debugging)

## Rating Formats

The rating parser supports multiple formats:

```
✅ Recipe 1: 4, Recipe 2: 5
✅ 1: 4, 2: 5
✅ Recipe 1: 4/5, Recipe 2: 5/5
✅ 4/5 for recipe 1, 5/5 for recipe 2
✅ Recipe 1: ⭐⭐⭐⭐
✅ First recipe 4 stars, second recipe 5 stars
```

## Troubleshooting

### Email Not Sending

**Error:** `Gmail authentication failed`
- Verify you're using an app-specific password, not your regular Gmail password
- Check that 2FA is enabled on your Gmail account
- Generate a new app password if needed

### No Recipes Available

**Error:** `No recipes available`
- Run `python -m src.api.spoonacular_client` to fetch more recipes
- Check your Spoonacular API key is valid
- Verify you haven't exceeded the 150 requests/day limit

### Database Errors

**Error:** `DetachedInstanceError` or session issues
- Stop all running scripts
- Restart your Python session
- Re-run the command

### Logs

Check logs for detailed error information:
```bash
tail -f logs/daily_send.log
tail -f logs/rating.log
tail -f logs/api_test.log
```

## Cost

### Free Tier
- **Recipe scraping:** Free (scrapes from public websites)
- **Gmail:** 500 emails/day
- **Storage:** SQLite (local, free)
- **Spoonacular** (optional): 150 API requests/day

**Total Cost:** $0/month for single user

### Scaling
If you exceed free tiers:
- **Spoonacular** (if using): $0.002 per request (~$0.60 for 300 requests)
- **Cloud hosting:** ~$15/month (AWS Lambda + RDS)

## Future Enhancements

### Planned Features

- [ ] IMAP email receiver for automatic rating processing
- [ ] Dietary restrictions and allergies support
- [ ] Ingredient exclusion preferences
- [ ] Recipe collections (favorites, avoid list)
- [ ] Web dashboard for viewing history
- [ ] Multi-user support

### Weekend Shopping List Feature (Detailed Plan)

**Goal:** Send 3 recipes on weekends with a smart shopping list that minimizes ingredients and optionally respects budget constraints.

#### Phase 1: Weekend Mode (Easy)
- [ ] Modify recommendation logic to detect weekends
- [ ] Send 3 recipes instead of 2 on Sat/Sun
- [ ] Generate basic shopping list (all ingredients from 3 recipes)
- [ ] Email shopping list along with recipes

#### Phase 2: Smart Shopping List (Moderate)
- [ ] Build ingredient parser (`src/recommender/ingredient_parser.py`)
  - Parse quantities and units from ingredient strings
  - Normalize measurements (convert to common units)
  - Extract base ingredient names
- [ ] Build shopping list generator (`src/recommender/shopping_list.py`)
  - Deduplicate ingredients across recipes
  - Combine quantities (e.g., "2 cups onions" + "1 cup onions" = "3 cups onions")
  - Group by category (produce, dairy, protein, etc.)
- [ ] Optimize recipe selection for ingredient overlap
  - Modify recommendation engine to favor recipes sharing ingredients
  - Add "ingredient_count" constraint (e.g., max 15 unique ingredients per week)
- [ ] Create weekend-specific scheduler (`src/scheduler/send_weekend.py`)

**Challenges:**
- Parsing varied ingredient formats ("1 onion, diced" vs "2 cups chopped onions")
- Normalizing units across recipes
- Determining when ingredients are "the same" (chicken breast vs chicken thighs)

**Implementation notes:**
- Consider using NLP library or regex patterns for parsing
- Store normalized ingredient data in database for learning
- May need manual ingredient mapping for edge cases

#### Phase 3: Budget Awareness (Complex - Optional)
- [ ] Add price estimation system
  - Options:
    1. Manual price database (user enters typical prices)
    2. Grocery API integration (Instacart, Kroger APIs)
    3. Simple tier system: $ (cheap), $$ (moderate), $$$ (expensive)
  - Add `IngredientPrice` table to database
  - Tag common ingredients with price estimates
- [ ] Budget-aware recipe selection
  - Calculate estimated recipe cost based on ingredient prices
  - Add budget constraint to recommendation engine (e.g., "< $150/week")
  - Prefer recipes within budget while maintaining variety

**Challenges:**
- Price variability by location, store, season, quality
- Keeping price data current
- Accounting for pantry staples vs. special purchases

**Simplest viable approach:**
- Start with manual price database for your most common ingredients
- Use broad categories rather than exact prices
- Refine over time based on actual shopping experience

### Other Ideas
- [ ] Meal planning (breakfast, lunch, dinner)
- [ ] Leftover tracking and recipe suggestions

## Technical Details

### Technologies Used

- **Python 3.9+**
- **SQLAlchemy 2.0** - Database ORM
- **Alembic** - Database migrations
- **Jinja2** - Email templating
- **Requests** - HTTP client
- **Loguru** - Logging
- **recipe-scrapers** - Web scraping for recipe sites
- **BeautifulSoup4** - HTML parsing
- **Spoonacular API** (optional) - Alternative recipe source
- **Gmail SMTP** - Email delivery

### Architecture

The system uses a 3-tier architecture:
1. **Data Layer** - SQLite database with SQLAlchemy ORM
2. **Business Logic** - Recommendation engine, preference learning
3. **Presentation** - Email templates, SMTP sender

### Algorithm Details

The recommendation engine uses a phased approach:
- **Phase 1:** Random selection with cuisine diversity
- **Phase 2:** Weighted preference matching with exploration/exploitation balance
- **Phase 3:** Strong personalization with limited exploration

Preferences are tracked across multiple dimensions:
- Cuisine type (Italian, Mexican, Asian, etc.)
- Dish type (main course, soup, dessert, etc.)
- Difficulty level (easy, medium, hard)
- Cooking time (<30min, 30-60min, >60min)

## Support

For issues or questions:
- Check the troubleshooting section above
- Review logs in the `logs/` directory
- Verify your `.env` configuration

## License

This project is for personal use.

---

**Built with ❤️ and powered by Spoonacular API**
