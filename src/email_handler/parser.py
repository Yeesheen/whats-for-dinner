"""
Email rating parser.

This module parses rating information from email replies.
Supports multiple rating formats to make it easy for users.
"""

import re
from typing import List, Tuple, Optional
from loguru import logger


def clean_email_body(body: str) -> str:
    """
    Clean email body by removing quoted text and signatures.

    Args:
        body: Raw email body

    Returns:
        Cleaned email body
    """
    if not body:
        return ""

    # Split into lines
    lines = body.split('\n')

    # Remove lines starting with > (quoted text)
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip quoted lines
        if stripped.startswith('>'):
            continue
        # Skip common reply markers
        if 'wrote:' in stripped.lower() or 'on ' in stripped.lower() and ' wrote:' in stripped.lower():
            break
        cleaned.append(line)

    body = '\n'.join(cleaned)

    # Cut at common signature markers
    for marker in ['--', '___', 'Sent from', 'Best regards', 'Thanks', 'Regards']:
        if marker in body:
            body = body.split(marker)[0]

    # Cut at original message marker
    if '-----Original Message-----' in body:
        body = body.split('-----Original Message-----')[0]

    return body.strip()


def parse_ratings(email_body: str) -> List[Tuple[int, int]]:
    """
    Parse ratings from email body text.

    Supports multiple formats:
    - "Recipe 1: 4, Recipe 2: 5"
    - "1: 4, 2: 5"
    - "Recipe 1: 4/5, Recipe 2: 5/5"
    - "4/5 for recipe 1, 5/5 for recipe 2"
    - "Recipe 1: ⭐⭐⭐⭐"
    - "First recipe 4 stars, second recipe 5 stars"

    Args:
        email_body: Email body text

    Returns:
        List of (recipe_number, rating) tuples
    """
    if not email_body:
        return []

    # Clean the email body
    body = clean_email_body(email_body)
    body_lower = body.lower()

    ratings = []

    # Pattern 1: "Recipe 1: 4" or "1: 4" or "Recipe 1 : 4"
    pattern1 = r'(?:recipe\s*)?(\d+)\s*[:：]\s*(\d+)'
    matches = re.findall(pattern1, body_lower, re.IGNORECASE)
    for recipe_num, rating in matches:
        recipe_num = int(recipe_num)
        rating = int(rating)
        if 1 <= recipe_num <= 10 and 1 <= rating <= 5:
            ratings.append((recipe_num, rating))

    # Pattern 2: Star emojis "Recipe 1: ⭐⭐⭐⭐"
    pattern2 = r'(?:recipe\s*)?(\d+)[\s:：]+([⭐★]{1,5})'
    star_matches = re.findall(pattern2, body, re.IGNORECASE)
    for recipe_num, stars in star_matches:
        recipe_num = int(recipe_num)
        rating = len(stars)
        if 1 <= recipe_num <= 10 and 1 <= rating <= 5:
            # Only add if not already added
            if (recipe_num, rating) not in ratings:
                ratings.append((recipe_num, rating))

    # Pattern 3: "4/5 for recipe 1" or "4/5 for the first recipe"
    pattern3 = r'(\d+)\s*/\s*5\s+(?:for\s+)?(?:the\s+)?(?:recipe\s*)?(\d+|first|second|third)'
    slash_matches = re.findall(pattern3, body_lower, re.IGNORECASE)
    for rating, recipe_word in slash_matches:
        rating = int(rating)
        # Convert word to number
        if recipe_word.isdigit():
            recipe_num = int(recipe_word)
        elif recipe_word == 'first':
            recipe_num = 1
        elif recipe_word == 'second':
            recipe_num = 2
        elif recipe_word == 'third':
            recipe_num = 3
        else:
            continue

        if 1 <= recipe_num <= 10 and 1 <= rating <= 5:
            # Only add if not already added
            if (recipe_num, rating) not in ratings:
                ratings.append((recipe_num, rating))

    # Pattern 4: "first recipe 4 stars" or "second recipe 5 stars"
    pattern4 = r'(first|second|third|1st|2nd|3rd|\d+)(?:st|nd|rd|th)?\s+recipe\s*[:\s]+(\d+)\s*(?:star|out)'
    word_matches = re.findall(pattern4, body_lower, re.IGNORECASE)
    for recipe_word, rating in word_matches:
        rating = int(rating)
        # Convert word to number
        if recipe_word.isdigit():
            recipe_num = int(recipe_word)
        elif recipe_word in ['first', '1st']:
            recipe_num = 1
        elif recipe_word in ['second', '2nd']:
            recipe_num = 2
        elif recipe_word in ['third', '3rd']:
            recipe_num = 3
        else:
            continue

        if 1 <= recipe_num <= 10 and 1 <= rating <= 5:
            # Only add if not already added
            if (recipe_num, rating) not in ratings:
                ratings.append((recipe_num, rating))

    # Remove duplicates and sort by recipe number
    ratings = list(set(ratings))
    ratings.sort(key=lambda x: x[0])

    logger.info(f"Parsed {len(ratings)} ratings from email: {ratings}")
    return ratings


def validate_ratings(ratings: List[Tuple[int, int]], expected_count: int = 2) -> bool:
    """
    Validate that ratings are complete and valid.

    Args:
        ratings: List of (recipe_number, rating) tuples
        expected_count: Expected number of recipes (usually 2)

    Returns:
        True if ratings are valid and complete
    """
    if len(ratings) != expected_count:
        logger.warning(
            f"Expected {expected_count} ratings but got {len(ratings)}: {ratings}"
        )
        return False

    # Check for correct recipe numbers (should be 1, 2, ... expected_count)
    expected_numbers = set(range(1, expected_count + 1))
    actual_numbers = set(r[0] for r in ratings)

    if expected_numbers != actual_numbers:
        logger.warning(
            f"Expected recipe numbers {expected_numbers} but got {actual_numbers}"
        )
        return False

    # Check all ratings are in valid range
    for recipe_num, rating in ratings:
        if not (1 <= rating <= 5):
            logger.warning(f"Invalid rating {rating} for recipe {recipe_num}")
            return False

    logger.info(f"Ratings validated successfully: {ratings}")
    return True


if __name__ == "__main__":
    # Test the rating parser
    logger.add("logs/parser_test.log", rotation="1 day")

    print("Testing Rating Parser...")
    print("-" * 50)

    test_cases = [
        ("Recipe 1: 4, Recipe 2: 5", [(1, 4), (2, 5)]),
        ("1: 4, 2: 5", [(1, 4), (2, 5)]),
        ("Recipe 1: 4/5, Recipe 2: 5/5", [(1, 4), (2, 5)]),
        ("4/5 for recipe 1, 5/5 for recipe 2", [(1, 4), (2, 5)]),
        ("Recipe 1: ⭐⭐⭐⭐\nRecipe 2: ⭐⭐⭐⭐⭐", [(1, 4), (2, 5)]),
        ("First recipe 4 stars, second recipe 5 stars", [(1, 4), (2, 5)]),
        ("Recipe 1 : 3\nRecipe 2 : 5", [(1, 3), (2, 5)]),
        (
            "Hi! Recipe 1: 4, Recipe 2: 5\n\nThanks!\n\n> On Dec 8, someone wrote:\n> Recipe 1...",
            [(1, 4), (2, 5)],
        ),
    ]

    print("\nTesting different rating formats:\n")
    for idx, (test_input, expected) in enumerate(test_cases, 1):
        print(f"Test {idx}:")
        print(f"  Input: {test_input[:60]}...")
        result = parse_ratings(test_input)
        print(f"  Expected: {expected}")
        print(f"  Got: {result}")
        print(f"  Valid: {validate_ratings(result)}")
        success = result == expected
        print(f"  ✅ PASS" if success else f"  ❌ FAIL")
        print()

    print("-" * 50)
    print("Rating parser test complete!")
