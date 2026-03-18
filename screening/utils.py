"""
screening/utils.py

Public entry point for the screening pipeline.
All job data is pulled directly from the database — no hardcoding.

    job.description         → compared with full resume text (cosine similarity)
    job.skills (M2M)        → compared with resume skills (fuzzy match)
    job.experience_required → compared with resume experience (date parsing)
    job.qualification_required → compared with resume qualifications (level match)
"""

from typing import Dict

from .extractor import extract_text_from_resume
from .cleaner   import clean_text
from .features  import (
    extract_skills,
    get_missing_skills,
    extract_experience,
    extract_candidate_qualifications,
    calculate_qualification_score,
)
from .scorer import (
    text_to_vector,
    cosine_similarity_score,
    skills_score,
    experience_score,
    adjusted_experience_score,
    final_score,
)


def compute_match_score(resume_file, job) -> Dict:
    """
    Full screening pipeline for one application.

    Pulls ALL comparison data from the Job model instance (database):
        - job.description + requirements + responsibilities → semantic similarity
        - job.skills (M2M queryset)                        → skill matching
        - job.experience_required (IntegerField)           → experience scoring
        - job.qualification_required (CharField)           → qualification scoring

    Args:
        resume_file : Django FileField  (application.resume.file)
        job         : jobs.Job model instance (passed from views.py)

    Returns:
        dict:
            score            (float, 0–100)
            extracted_skills (comma-separated string — found in resume)
            matched_skills   (comma-separated string — matched to job)
            missing_skills   (comma-separated string — in job but not resume)
            summary          (human-readable string)
    """

    # ── 1. Extract raw text from resume PDF ───────────────────────────────
    raw_resume_text = extract_text_from_resume(resume_file)

    # ── 2. Build job text from DB fields ──────────────────────────────────
    #    Combines description + requirements + responsibilities + skill names
    #    This is what gets compared semantically with the resume
    raw_job_text = _build_job_text(job)

    # ── 3. Clean both texts ────────────────────────────────────────────────
    cleaned_resume = clean_text(raw_resume_text)
    cleaned_job    = clean_text(raw_job_text)

    # ── 4. Vectorise ───────────────────────────────────────────────────────
    resume_vector = text_to_vector(cleaned_resume)
    job_vector    = text_to_vector(cleaned_job)

    # ── 5. Cosine similarity (job.description vs resume) ──────────────────
    cosine_score = cosine_similarity_score(resume_vector, job_vector)

    # ── 6. Skill matching (job.skills M2M from DB vs resume) ──────────────
    job_skill_names = list(job.skills.values_list("name", flat=True))
    extracted       = extract_skills(cleaned_resume, job_skill_names)
    missing         = get_missing_skills(extracted, job_skill_names)
    skill_sc        = skills_score(extracted, job_skill_names)

    # ── 7. Experience (job.experience_required from DB vs resume dates) ───
    candidate_exp = extract_experience(cleaned_resume)
    required_exp  = float(job.experience_required or 0)
    exp_sc        = experience_score(candidate_exp, required_exp)
    adj_exp_sc    = adjusted_experience_score(exp_sc, skill_sc)

    # ── 8. Qualification (job.qualification_required from DB vs resume) ───
    #    job.qualification_required is a CharField with choices:
    #    "" | "diploma" | "bachelor" | "master" | "phd"
    candidate_quals        = extract_candidate_qualifications(raw_resume_text)
    required_qualification = job.qualification_required or ""
    qual_sc                = calculate_qualification_score(
                               candidate_quals,
                               required_qualification   # ← direct DB value, no parsing
                             )

    # ── 9. Final weighted score → 0–100 ───────────────────────────────────
    raw_score = final_score(cosine_score, skill_sc, adj_exp_sc, qual_sc)
    score_pct = round(min(raw_score * 100, 100.0), 1)

    # ── 10. Human-readable summary ─────────────────────────────────────────
    summary = _build_summary(
        score_pct,
        extracted,
        missing,
        candidate_exp,
        required_exp,
        required_qualification,
        candidate_quals,
    )

    return {
        "score":            score_pct,
        "extracted_skills": ", ".join(extracted),
        "matched_skills":   ", ".join(extracted),
        "missing_skills":   ", ".join(missing),
        "summary":          summary,
    }


# ── Internal helpers ───────────────────────────────────────────────────────

def _build_job_text(job) -> str:
    """
    Concatenate all Job text fields into one block for vectorisation.
    Skill names are appended as plain text so the model sees them.
    """
    skill_names = " ".join(job.skills.values_list("name", flat=True))
    parts = [
        job.title,
        job.description,
        job.requirements     or "",
        job.responsibilities or "",
        skill_names,
    ]
    return "\n".join(p for p in parts if p.strip())


def _build_summary(
    score:                  float,
    matched:                list,
    missing:                list,
    candidate_exp:          float,
    required_exp:           float,
    required_qualification: str,
    candidate_quals:        list,
) -> str:
    """Generate a plain-English summary of the full screening result."""

    verdict = (
        "Strong match"   if score >= 75 else
        "Moderate match" if score >= 50 else
        "Weak match"
    )

    parts = [f"{verdict} — overall score {score:.1f}%."]

    # Skills
    if matched:
        parts.append(f"Matched skills: {', '.join(matched)}.")
    if missing:
        parts.append(f"Missing skills: {', '.join(missing)}.")

    # Experience
    if required_exp > 0:
        if candidate_exp >= required_exp:
            parts.append(
                f"Experience requirement met ({candidate_exp} yrs vs {required_exp} required)."
            )
        else:
            parts.append(
                f"Experience below requirement ({candidate_exp} yrs vs {required_exp} required)."
            )

    # Qualification
    if required_qualification:
        if candidate_quals:
            parts.append(
                f"Qualification found: {candidate_quals[0]}. "
                f"Required: {required_qualification}."
            )
        else:
            parts.append(
                f"No qualification detected in resume. Required: {required_qualification}."
            )

    return " ".join(parts)