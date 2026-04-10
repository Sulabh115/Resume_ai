"""
screening/utils.py

Public entry point for the screening pipeline.
All job data is pulled directly from the database — no hardcoding.

    job.description         → compared with full resume text (cosine similarity)
    job.skills (M2M)        → compared with resume skills (fuzzy match)
    job.experience_required → compared with resume experience (date parsing)
    job.qualification_required → compared with resume qualifications (level match)

FIX #2:
    required_qualification is a CharField value like "" | "bachelor" | "master" etc.
    calculate_qualification_score() expects job_qual_list: List[str], not a bare string.
    Passing a bare string caused iteration over individual characters ("b","a","c",...)
    so the qualification score was always 0.
    Fix: wrap in a list — [required_qualification] if non-empty, else [].

FIX #9:
    compute_match_score now returns individual component scores alongside the
    overall score so they can be stored in ScreeningResult and displayed as
    sub-bars in the view_applicants and screening_dashboard templates.
    All component values are scaled to 0-100 for consistency with similarity_score.
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
            score               (float, 0–100)  — final weighted composite
            skill_score         (float, 0–100)  — #9: skill match component
            experience_score    (float, 0–100)  — #9: experience component
            qualification_score (float, 0–100)  — #9: qualification component
            cosine_score        (float, 0–100)  — #9: semantic similarity component
            extracted_skills    (comma-separated string — found in resume)
            matched_skills      (comma-separated string — matched to job)
            missing_skills      (comma-separated string — in job but not resume)
            summary             (human-readable string)
    """

    # ── 1. Extract raw text from resume PDF ───────────────────────────────
    raw_resume_text = extract_text_from_resume(resume_file)

    # ── 2. Build job text from DB fields ──────────────────────────────────
    raw_job_text = _build_job_text(job)

    # ── 3. Clean both texts ────────────────────────────────────────────────
    cleaned_resume = clean_text(raw_resume_text)
    cleaned_job    = clean_text(raw_job_text)

    # ── 4. Vectorise ───────────────────────────────────────────────────────
    resume_vector = text_to_vector(cleaned_resume)
    job_vector    = text_to_vector(cleaned_job)

    # ── 5. Cosine similarity (job description vs resume) ──────────────────
    cosine_sc = cosine_similarity_score(resume_vector, job_vector)

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
    #
    #    FIX #2: wrap qualification string in a list.
    #
    candidate_quals        = extract_candidate_qualifications(raw_resume_text)
    required_qualification = job.qualification_required or ""
    job_qual_list = [required_qualification] if required_qualification else []
    qual_sc = calculate_qualification_score(candidate_quals, job_qual_list)

    # ── 9. Final weighted score → 0–100 ───────────────────────────────────
    raw_score = final_score(cosine_sc, skill_sc, adj_exp_sc, qual_sc)
    score_pct = round(min(raw_score * 100, 100.0), 1)

    # ── 10. Scale component scores to 0–100 for storage (#9) ──────────────
    # cosine_sc and skill_sc are already in [0,1]; clamp to [0,100].
    # adj_exp_sc may reach 1.15 (bonus); cap at 100.
    # qual_sc may reach 1.10 (over-qualified bonus); cap at 100.
    skill_score_pct  = round(min(skill_sc   * 100, 100.0), 1)
    exp_score_pct    = round(min(adj_exp_sc * 100, 100.0), 1)
    qual_score_pct   = round(min(qual_sc    * 100, 100.0), 1)
    cosine_score_pct = round(min(cosine_sc  * 100, 100.0), 1)

    # ── 11. Human-readable summary ─────────────────────────────────────────
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
        "score":               score_pct,
        # ── #9: individual component scores ──
        "skill_score":         skill_score_pct,
        "experience_score":    exp_score_pct,
        "qualification_score": qual_score_pct,
        "cosine_score":        cosine_score_pct,
        # ── skill lists ──
        "extracted_skills":    ", ".join(extracted),
        "matched_skills":      ", ".join(extracted),
        "missing_skills":      ", ".join(missing),
        "summary":             summary,
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
                f"Experience requirement met "
                f"({candidate_exp} yrs vs {required_exp} required)."
            )
        else:
            parts.append(
                f"Experience below requirement "
                f"({candidate_exp} yrs vs {required_exp} required)."
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
                f"No qualification detected in resume. "
                f"Required: {required_qualification}."
            )

    return " ".join(parts)