"""Pure analysis tools — no Jira writes, no external services required.

These tools operate entirely on data passed to them and perform calculations,
scoring, and prioritisation locally.  They are safe to call without any
network access or approval gates.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

_PRIORITY_RANK: dict[str, int] = {
    "highest": 5,
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "lowest": 1,
    "trivial": 1,
}

# Words that indicate a description is meaningful vs. boilerplate
_QUALITY_NEGATIVE_PATTERNS = [
    re.compile(r"\btodo\b", re.IGNORECASE),
    re.compile(r"\bfixme\b", re.IGNORECASE),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bN/A\b"),
    re.compile(r"^\.+$"),  # only dots
]

_ACCEPTANCE_CRITERIA_KEYWORDS = [
    "given", "when", "then",    # Gherkin
    "acceptance", "criteria", "accept", "verify",
    "must", "should", "shall",
]


# ── Tools ─────────────────────────────────────────────────────────────


@tool
def analyze_sprint_capacity(
    team_size: int,
    sprint_days: int,
    focus_factor: float = 0.7,
) -> dict:
    """Estimate the recommended story point capacity for a sprint.

    Formula: team_size * sprint_days * focus_factor * 8 hours/day
             divided by 13 average hours per story point.

    Args:
        team_size: Number of developers on the team.
        sprint_days: Working days in the sprint (e.g. 10 for a 2-week sprint).
        focus_factor: Fraction of time spent on sprint work (default 0.7 = 70%).

    Returns:
        Dict with status="SUCCESS", recommended_story_points, and breakdown details.
    """
    if team_size <= 0:
        return {"status": "FAILED", "error": "team_size must be a positive integer."}
    if sprint_days <= 0:
        return {"status": "FAILED", "error": "sprint_days must be a positive integer."}
    if not (0.0 < focus_factor <= 1.0):
        return {
            "status": "FAILED",
            "error": "focus_factor must be between 0.0 (exclusive) and 1.0 (inclusive).",
        }

    avg_hours_per_point = 13.0  # industry heuristic
    hours_per_day = 8.0

    total_available_hours = team_size * sprint_days * hours_per_day * focus_factor
    recommended_points = round(total_available_hours / avg_hours_per_point, 1)

    # Also compute conservative (-20%) and stretch (+20%) targets
    conservative_points = round(recommended_points * 0.8, 1)
    stretch_points = round(recommended_points * 1.2, 1)

    logger.debug(
        "analyze_sprint_capacity: team=%d days=%d ff=%.2f → %.1f pts",
        team_size, sprint_days, focus_factor, recommended_points,
    )
    return {
        "status": "SUCCESS",
        "team_size": team_size,
        "sprint_days": sprint_days,
        "focus_factor": focus_factor,
        "hours_per_day": hours_per_day,
        "avg_hours_per_story_point": avg_hours_per_point,
        "total_available_hours": round(total_available_hours, 1),
        "recommended_story_points": recommended_points,
        "conservative_story_points": conservative_points,
        "stretch_story_points": stretch_points,
    }


@tool
def calculate_risk_score(
    total_tickets: int,
    blocked_count: int,
    overdue_count: int,
    critical_defects: int,
) -> dict:
    """Calculate a 0–100 sprint risk score from issue metrics.

    Scoring heuristics:
    - Blocked ratio (blocked / total): up to 40 points
    - Overdue ratio (overdue / total): up to 35 points
    - Critical defects (absolute, capped at 5): up to 25 points

    Risk levels:
    - 0–25   → LOW
    - 26–50  → MEDIUM
    - 51–75  → HIGH
    - 76–100 → CRITICAL

    Args:
        total_tickets: Total number of open sprint tickets.
        blocked_count: Number of blocked tickets.
        overdue_count: Number of overdue tickets.
        critical_defects: Number of unresolved Critical/High bugs.

    Returns:
        Dict with status="SUCCESS", score (0–100), risk_level, and breakdown.
    """
    if total_tickets < 0:
        return {"status": "FAILED", "error": "total_tickets must be >= 0."}
    for label, val in [
        ("blocked_count", blocked_count),
        ("overdue_count", overdue_count),
        ("critical_defects", critical_defects),
    ]:
        if val < 0:
            return {"status": "FAILED", "error": f"{label} must be >= 0."}

    if total_tickets == 0:
        # No tickets means no measurable sprint risk from ratios
        score = min(critical_defects * 5, 25)
        breakdown = {
            "blocked_score": 0,
            "overdue_score": 0,
            "defect_score": score,
            "note": "No sprint tickets — defect score only.",
        }
    else:
        blocked_ratio = min(blocked_count / total_tickets, 1.0)
        overdue_ratio = min(overdue_count / total_tickets, 1.0)
        capped_defects = min(critical_defects, 5)

        blocked_score = round(blocked_ratio * 40)
        overdue_score = round(overdue_ratio * 35)
        defect_score = round(capped_defects / 5 * 25)

        score = blocked_score + overdue_score + defect_score
        breakdown = {
            "blocked_ratio": round(blocked_ratio, 3),
            "overdue_ratio": round(overdue_ratio, 3),
            "blocked_score": blocked_score,
            "overdue_score": overdue_score,
            "defect_score": defect_score,
        }

    score = max(0, min(score, 100))

    if score <= 25:
        risk_level = "LOW"
    elif score <= 50:
        risk_level = "MEDIUM"
    elif score <= 75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    logger.debug(
        "calculate_risk_score: total=%d blocked=%d overdue=%d defects=%d → score=%d %s",
        total_tickets, blocked_count, overdue_count, critical_defects, score, risk_level,
    )
    return {
        "status": "SUCCESS",
        "score": score,
        "risk_level": risk_level,
        "inputs": {
            "total_tickets": total_tickets,
            "blocked_count": blocked_count,
            "overdue_count": overdue_count,
            "critical_defects": critical_defects,
        },
        "breakdown": breakdown,
    }


@tool
def prioritize_backlog(
    tickets: list[dict],
    weights: Optional[dict] = None,
) -> dict:
    """Compute a composite priority score for a list of backlog tickets.

    Each ticket dict should have: key, priority, story_points, age_days,
    has_blockers.  Missing fields default to safe values.

    Composite score formula (weighted sum, 0–100):
    - priority (0.4): rank 1–5 mapped to 0–100
    - age (0.2): capped at 180 days, older = higher score
    - size (0.2): smaller = higher score (inverse of story_points, capped at 13)
    - blockers (0.2): has_blockers=True → 100, False → 0

    Args:
        tickets: List of ticket dicts with key, priority, story_points,
                 age_days, has_blockers.
        weights: Optional weight overrides as dict with keys: priority, age,
                 size, blockers.  Values must sum to 1.0.

    Returns:
        Dict with status="SUCCESS" and sorted list of tickets with composite scores.
    """
    if not tickets:
        return {
            "status": "SUCCESS",
            "message": "No tickets to prioritise.",
            "prioritized": [],
        }

    default_weights = {"priority": 0.4, "age": 0.2, "size": 0.2, "blockers": 0.2}
    if weights:
        merged = {**default_weights, **weights}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.05:
            return {
                "status": "FAILED",
                "error": f"Weights must sum to 1.0 (got {total:.3f}).",
            }
        final_weights = merged
    else:
        final_weights = default_weights

    scored: list[dict] = []
    for ticket in tickets:
        key = str(ticket.get("key", "UNKNOWN"))
        priority_str = str(ticket.get("priority", "medium")).lower()
        story_points_raw = ticket.get("story_points")
        age_days_raw = ticket.get("age_days", 0)
        has_blockers = bool(ticket.get("has_blockers", False))

        # Priority score: 0–100
        priority_rank = _PRIORITY_RANK.get(priority_str, 3)
        priority_score = round((priority_rank - 1) / 4 * 100)

        # Age score: older tickets score higher (cap at 180 days)
        try:
            age_days = float(age_days_raw)
        except (TypeError, ValueError):
            age_days = 0.0
        age_score = round(min(age_days / 180.0, 1.0) * 100)

        # Size score: smaller = higher priority (cap at 13 SP)
        try:
            sp = float(story_points_raw) if story_points_raw is not None else 5.0
        except (TypeError, ValueError):
            sp = 5.0
        size_score = round((1.0 - min(sp, 13.0) / 13.0) * 100)

        # Blocker score
        blocker_score = 100 if has_blockers else 0

        composite = round(
            priority_score * final_weights["priority"]
            + age_score * final_weights["age"]
            + size_score * final_weights["size"]
            + blocker_score * final_weights["blockers"],
            1,
        )

        scored.append(
            {
                "key": key,
                "priority": ticket.get("priority", "medium"),
                "story_points": story_points_raw,
                "age_days": age_days_raw,
                "has_blockers": has_blockers,
                "composite_score": composite,
                "score_breakdown": {
                    "priority_score": priority_score,
                    "age_score": age_score,
                    "size_score": size_score,
                    "blocker_score": blocker_score,
                },
            }
        )

    scored.sort(key=lambda t: t["composite_score"], reverse=True)
    logger.debug("prioritize_backlog: scored %d tickets.", len(scored))
    return {
        "status": "SUCCESS",
        "total": len(scored),
        "weights_used": final_weights,
        "prioritized": scored,
    }


@tool
def check_ticket_quality(
    summary: str,
    description: str,
    acceptance_criteria: str = "",
) -> dict:
    """Score the quality of a Jira ticket's content on a 0–100 scale.

    Checks:
    - Summary length and specificity (no vague words)
    - Description length and substance
    - Presence of acceptance criteria
    - Absence of placeholder text (TODO, TBD, N/A)

    Args:
        summary: The ticket summary line.
        description: The full description text.
        acceptance_criteria: Optional acceptance criteria text.

    Returns:
        Dict with status="SUCCESS", quality_score (0–100), and improvement_hints.
    """
    hints: list[str] = []
    score = 100

    # ── Summary checks (max penalty: -40) ────────────────────────────
    summary_stripped = summary.strip()
    if len(summary_stripped) < 10:
        hints.append("Summary is too short — be more descriptive (at least 10 characters).")
        score -= 20
    elif len(summary_stripped) < 20:
        hints.append("Summary is brief — consider adding more context.")
        score -= 10

    if len(summary_stripped) > 200:
        hints.append("Summary is too long — keep it under 200 characters.")
        score -= 10

    vague_words = {"fix", "update", "change", "misc", "bug", "issue", "stuff", "thing"}
    summary_lower = summary_stripped.lower()
    matched_vague = [w for w in vague_words if re.search(rf"\b{w}\b", summary_lower)]
    if matched_vague:
        hints.append(
            f"Summary contains vague words ({', '.join(matched_vague)}) — be specific about what needs doing."
        )
        score -= 10

    # ── Description checks (max penalty: -30) ────────────────────────
    desc_stripped = description.strip()
    if not desc_stripped:
        hints.append("Description is empty — explain the problem/goal and context.")
        score -= 30
    elif len(desc_stripped) < 50:
        hints.append("Description is very short — add more context and detail.")
        score -= 20
    elif len(desc_stripped) < 150:
        hints.append("Description could be more detailed.")
        score -= 10

    for pattern in _QUALITY_NEGATIVE_PATTERNS:
        if pattern.search(desc_stripped):
            hints.append(
                "Description contains placeholder text (TODO/TBD/N/A) — replace with actual content."
            )
            score -= 10
            break

    # ── Acceptance criteria checks (max penalty: -20) ─────────────────
    ac_text = (acceptance_criteria or "").strip()
    if not ac_text:
        # Check whether description contains embedded acceptance criteria
        combined = desc_stripped.lower()
        has_ac_in_desc = any(kw in combined for kw in _ACCEPTANCE_CRITERIA_KEYWORDS)
        if not has_ac_in_desc:
            hints.append(
                "No acceptance criteria found — add Gherkin (Given/When/Then) or "
                "a bulleted 'Acceptance Criteria' section."
            )
            score -= 20
    else:
        ac_lower = ac_text.lower()
        has_ac_keywords = any(kw in ac_lower for kw in _ACCEPTANCE_CRITERIA_KEYWORDS)
        if not has_ac_keywords:
            hints.append(
                "Acceptance criteria section is present but lacks clear verifiable statements."
            )
            score -= 10

    score = max(0, score)

    if score >= 80:
        quality_label = "GOOD"
    elif score >= 60:
        quality_label = "ACCEPTABLE"
    elif score >= 40:
        quality_label = "NEEDS_IMPROVEMENT"
    else:
        quality_label = "POOR"

    logger.debug("check_ticket_quality: score=%d label=%s", score, quality_label)
    return {
        "status": "SUCCESS",
        "quality_score": score,
        "quality_label": quality_label,
        "improvement_hints": hints,
        "checks": {
            "summary_length": len(summary_stripped),
            "description_length": len(desc_stripped),
            "has_acceptance_criteria": bool(ac_text) or any(
                kw in desc_stripped.lower() for kw in _ACCEPTANCE_CRITERIA_KEYWORDS
            ),
        },
    }


@tool
def detect_duplicate_ticket(
    new_summary: str,
    existing_tickets: list[dict],
) -> dict:
    """Detect whether a proposed new ticket is a likely duplicate of existing ones.

    Uses word-overlap (Jaccard) similarity on ticket summaries.  A match with
    score >= 0.5 is flagged as a potential duplicate.

    Args:
        new_summary: The summary of the ticket being created.
        existing_tickets: List of existing ticket dicts with at least 'key'
                          and 'summary' fields.

    Returns:
        Dict with status="SUCCESS", is_duplicate (bool), and similar_tickets list.
    """
    if not new_summary.strip():
        return {
            "status": "FAILED",
            "error": "new_summary must not be empty.",
        }

    # Tokenise helper (inline to avoid importing memory module)
    _punct = re.compile(r"[^\w\s]")
    _stops = frozenset(
        {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was", "were",
            "be", "as", "it", "its", "this", "that", "not", "no", "do",
            "does", "did", "so", "if", "up", "i", "we", "you", "he", "she",
        }
    )

    def _tok(text: str) -> set[str]:
        cleaned = _punct.sub(" ", text.lower())
        return {t for t in cleaned.split() if t and t not in _stops and len(t) > 1}

    def _jaccard(a: set[str], b: set[str]) -> float:
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    new_tokens = _tok(new_summary)
    similar: list[dict] = []
    THRESHOLD = 0.5

    for ticket in existing_tickets:
        existing_key = str(ticket.get("key", ""))
        existing_summary = str(ticket.get("summary", ""))
        if not existing_summary:
            continue
        existing_tokens = _tok(existing_summary)
        score = _jaccard(new_tokens, existing_tokens)
        if score >= THRESHOLD:
            similar.append(
                {
                    "key": existing_key,
                    "summary": existing_summary,
                    "similarity_score": round(score, 3),
                }
            )

    similar.sort(key=lambda x: x["similarity_score"], reverse=True)
    is_duplicate = len(similar) > 0

    logger.debug(
        "detect_duplicate_ticket: new_summary='%s...' → %d similar found, is_duplicate=%s",
        new_summary[:50], len(similar), is_duplicate,
    )
    return {
        "status": "SUCCESS",
        "new_summary": new_summary,
        "is_duplicate": is_duplicate,
        "similar_count": len(similar),
        "similar_tickets": similar,
        "threshold_used": THRESHOLD,
    }
