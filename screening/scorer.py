"""
screening/scorer.py

All scoring logic:
    - text_to_vector        — Sentence-Transformer embedding
    - cosine_similarity_score
    - skills_score
    - experience_score      (with optional adjustment)
    - final_score           — weighted combination of all components

The SentenceTransformer model is loaded ONCE at module level.
Django's auto-reloader will keep it in memory between requests.
"""

from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# ── Model — loaded once ────────────────────────────────────────────────────
# Change the model name here if you switch to a larger / domain-specific one.
# _MODEL_NAME = "all-MiniLM-L6-v2"
# _model      = SentenceTransformer(_MODEL_NAME)
_model = None

def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model



# ── Vectorisation ──────────────────────────────────────────────────────────

def text_to_vector(text: str) -> np.ndarray:
    """
    Convert cleaned text to a dense semantic vector (384-dim).

    Args:
        text: Output of cleaner.clean_text().

    Returns:
        numpy array of shape (384,).
    """
    return _get_model().encode(text)


# ── Cosine Similarity ──────────────────────────────────────────────────────

def cosine_similarity_score(resume_vector: np.ndarray, job_vector: np.ndarray) -> float:
    """
    Semantic similarity between resume and job description.

    Returns:
        Float in [0, 1]. Higher = more similar.
    """
    return float(cosine_similarity([resume_vector], [job_vector])[0][0])


# ── Component scores ───────────────────────────────────────────────────────

def skills_score(candidate_skills: List[str], job_skills: List[str]) -> float:
    """
    Fraction of required job skills present in the candidate's resume.

    Returns:
        Float in [0, 1].
    """
    if not job_skills:
        return 0.0

    candidate_set = {s.lower() for s in candidate_skills}
    job_set       = {s.lower() for s in job_skills}
    matched       = candidate_set & job_set

    return round(len(matched) / len(job_set), 2)


def experience_score(candidate_exp: float, required_exp: float) -> float:
    """
    How well the candidate's experience meets the job requirement.

    - Exceeding the requirement gives a max 15% bonus (capped at 1.15).
    - If required_exp == 0, returns 1.0 (no requirement).

    Returns:
        Float in [0, 1.15].
    """
    if required_exp == 0:
        return 1.0

    return round(min(candidate_exp / required_exp, 1.15), 2)


def adjusted_experience_score(exp_score: float, skill_score: float) -> float:
    """
    Penalty for candidates with irrelevant experience (low skill match).

    Rules:
        - skill_score < 0.3  → experience counts for nothing (0)
        - skill_score < 0.6  → experience value halved
        - otherwise          → full experience score

    Prevents a 10-year accountant from scoring well on a software-engineering job.
    """
    if skill_score < 0.3:
        return 0.0
    if skill_score < 0.6:
        return round(exp_score * 0.5, 2)
    return exp_score


# ── Final weighted score ───────────────────────────────────────────────────

def final_score(
    cosine_sim:           float,
    skill_score:          float,
    exp_score:            float,
    qualification_score:  float,
) -> float:
    """
    Weighted combination of all component scores.

    Weights (tuned from notebook experiments):
        60%  semantic similarity  (cosine)
        20%  skill match
        10%  experience
        10%  qualification

    Returns:
        Float in [0, ~1.05].  Multiply by 100 for a percentage.
    """
    total = (
        0.60 * cosine_sim           +
        0.20 * skill_score          +
        0.10 * exp_score            +
        0.10 * qualification_score
    )
    return round(float(total), 4)