"""
screening/features.py

Extracts structured features from cleaned resume text:
    - Skills           (fuzzy keyword matching against a job's skill list)
    - Experience       (date-range parsing + "X years" fallback)
    - Qualifications   (degree-level detection)

All functions expect CLEANED text (output of cleaner.clean_text)
EXCEPT extract_candidate_qualifications, which works better on
the raw/original resume text because degree phrases contain
capitalised words that get lost after cleaning.
"""

import re
from datetime import datetime
from typing import List

from fuzzywuzzy import fuzz

from .cleaner import clean_text   # used internally for qualification scoring


# ── Constants ──────────────────────────────────────────────────────────────

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Level hierarchy: higher value = higher qualification
QUAL_LEVELS = {
    "phd":      3,
    "doctor":   3,
    "master":   2,
    "msc":      2,
    "mtech":    2,
    "bachelor": 1,
    "bsc":      1,
    "be":       1,
    "btech":    1,
    "ba":       1,
    "diploma":  0.5,
    "certificate": 0.2,
}


# ── Skills ─────────────────────────────────────────────────────────────────

def extract_skills(
    cleaned_resume_text: str,
    skill_list: List[str],
    fuzzy_threshold: int = 80,
) -> List[str]:
    """
    Fuzzy-match a job's required skills against a cleaned resume.

    Args:
        cleaned_resume_text: Output of cleaner.clean_text(resume_raw).
        skill_list:          Required skills defined on the Job model
                             (e.g. ['Python', 'Django', 'PostgreSQL']).
        fuzzy_threshold:     Minimum fuzz.partial_ratio score (0-100).

    Returns:
        List of skills from skill_list that were found in the resume.
    """
    text   = cleaned_resume_text.lower()
    words  = text.split()

    # Build unigrams, bigrams, trigrams for matching multi-word skills
    ngrams = (
        words
        + [" ".join(words[i:i+2]) for i in range(len(words) - 1)]
        + [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
    )

    found = set()
    for skill in skill_list:
        skill_lower = skill.lower()
        for chunk in ngrams:
            if fuzz.partial_ratio(skill_lower, chunk) >= fuzzy_threshold:
                found.add(skill)
                break

    return list(found)


def get_missing_skills(
    extracted_skills: List[str],
    job_skill_list: List[str],
) -> List[str]:
    """
    Return skills from job_skill_list NOT found in extracted_skills.
    Used to populate ScreeningResult.missing_skills.
    """
    found_lower  = {s.lower() for s in extracted_skills}
    return [s for s in job_skill_list if s.lower() not in found_lower]


# ── Experience ─────────────────────────────────────────────────────────────

def extract_experience(cleaned_resume_text: str) -> float:
    """
    Parse total years of experience from cleaned resume text.

    Strategy:
        1. Sum up all date ranges found (e.g. 'Jan 2020 – Dec 2021').
        2. Fallback: look for explicit "X years" phrases.

    Args:
        cleaned_resume_text: Output of cleaner.clean_text().

    Returns:
        Total experience in years, rounded to 1 decimal.
    """
    text  = cleaned_resume_text.lower()
    today = datetime.today()

    total_months = 0

    date_ranges = re.findall(
        r'(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\s*(\d{4}))'
        r'\s*[-–to]+\s*'
        r'(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\s*(\d{4}|present))',
        text,
    )

    for start_mon, start_yr, end_mon, end_yr in date_ranges:
        start_yr  = int(start_yr)
        start_mon = MONTH_MAP.get(start_mon, 1)

        if end_yr == "present":
            end_yr  = today.year
            end_mon = today.month
        else:
            end_yr  = int(end_yr)
            end_mon = MONTH_MAP.get(end_mon, 12)

        months = (end_yr - start_yr) * 12 + (end_mon - start_mon)
        if months > 0:
            total_months += months

    if total_months > 0:
        return round(total_months / 12, 1)

    # Fallback: "4+ years", "2 years experience"
    matches = re.findall(r'(\d+\.?\d*)\s*\+?\s*years?', text)
    return round(sum(float(v) for v in matches), 1)


# ── Qualifications ─────────────────────────────────────────────────────────

def extract_candidate_qualifications(raw_resume_text: str) -> List[str]:
    """
    Extract qualification phrases from the ORIGINAL (uncleaned) resume text.
    Use raw text here — capitalisation helps identify degree names correctly.

    Args:
        raw_resume_text: Direct output of extractor.extract_text_from_pdf().

    Returns:
        List of qualification phrases, e.g. ['Bachelor in Computer Science'].
    """
    pattern = re.compile(
        r'\b(' + '|'.join(QUAL_LEVELS.keys()) + r')\b(?:\s+\w+){0,5}',
        flags=re.IGNORECASE,
    )
    return [m.group().strip() for m in pattern.finditer(raw_resume_text)]


def calculate_qualification_score(
    candidate_quals: List[str],
    job_qual_list: List[str],
) -> float:
    """
    Score the candidate's qualifications against the job's requirements.

    Rules:
        - Exact match (after cleaning both sides) → 1.0
        - Candidate's highest level > job's required level → +0.10 bonus
        - No match → 0.0

    Returns:
        Float between 0.0 and 1.10.
    """
    score                   = 0.0
    highest_candidate_level = 0.0
    highest_job_level       = 0.0

    cleaned_job_quals = [clean_text(jq) for jq in job_qual_list]

    # Determine minimum required qualification level
    for jq in cleaned_job_quals:
        for level_name, level_val in QUAL_LEVELS.items():
            if level_name in jq:
                highest_job_level = max(highest_job_level, level_val)

    cleaned_candidate_quals = [clean_text(cq) for cq in candidate_quals]

    for cq in cleaned_candidate_quals:
        if cq in cleaned_job_quals:
            score = 1.0

        for level_name, level_val in QUAL_LEVELS.items():
            if level_name in cq:
                highest_candidate_level = max(highest_candidate_level, level_val)

    # Bonus: candidate is over-qualified
    if highest_candidate_level > highest_job_level:
        score += 0.10

    return min(score, 1.10)