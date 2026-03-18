"""
screening/cleaner.py

Handles all text preprocessing:
    - Date normalisation  (fixes OCR artefacts like 't0')
    - Lowercasing
    - Special-character removal
    - SpaCy lemmatisation + stopword removal

Keep this layer separate so you can swap NLP models without
touching extraction or scoring logic.
"""

import re
import spacy

# ── Load once at module import time (avoid reloading on every call) ────────
# _nlp = spacy.load("en_core_web_sm")
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ── Public API ─────────────────────────────────────────────────────────────

def normalize_dates(text: str) -> str:
    """
    Fix common OCR date artefacts before cleaning.

    Examples fixed:
        '10 2011 t0 04 2013'  →  '2011-2013'
        'Jan 2020 to Dec 2021' stays as-is (handled by extract_experience)
    """
    # Common OCR error: 't0' instead of 'to'
    text = re.sub(r't0', 'to', text)

    # Compact numeric date ranges: '03 2020 to 08 2022' → '2020-2022'
    text = re.sub(r'(\d{1,2}) (\d{4}) to (\d{1,2}) (\d{4})', r'\2-\4', text)

    # Ensure consistent dash in year ranges already present
    text = re.sub(r'(\d{4})-(\d{4})', r'\1-\2', text)

    return text


def clean_text(text: str) -> str:
    """
    Full preprocessing pipeline for NLP / vectorisation.

    Steps:
        1. Normalise dates
        2. Lowercase
        3. Collapse newlines → spaces
        4. Remove special characters (keep letters + digits)
        5. SpaCy lemmatise + drop stopwords

    Args:
        text: Raw resume or job-description text.

    Returns:
        Clean, lemmatised string ready for vectorisation / skill matching.
    """
    text = normalize_dates(text)
    text = text.lower()
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)

    doc    = _get_nlp()(text)
    tokens = [token.lemma_ for token in doc if not token.is_stop]

    return " ".join(tokens)