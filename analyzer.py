"""
analyzer.py
-----------
AI-powered skill gap analysis using the Groq API (openai/gpt-oss-20b).

This module sends the full resume text and job description text to the
model in a single, carefully structured prompt and asks for a strict JSON
response so it can be parsed reliably. It also post-processes the result
(building real, clickable "search" links for learning resources and
defensively normalising the shape of the response) so the rest of the
app never has to guard against missing fields.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL_NAME = "openai/gpt-oss-20b"
MAX_TEXT_CHARS = 20000  # safety cap so we never send an unreasonably huge prompt

VALID_CATEGORIES = {"technical", "tools", "soft"}
VALID_PRIORITIES = {"High", "Medium", "Low"}


class AnalyzerError(Exception):
    """Raised when the AI analysis cannot be completed."""


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise AnalyzerError(
            "GROQ_API_KEY is not set. Please add it to a .env file "
            "(see .env.example) and restart the server."
        )
    return Groq(api_key=api_key)


def _truncate(text: str) -> str:
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS] + "\n...[truncated]"
    return text


SYSTEM_PROMPT = """You are SkillSync, an expert technical recruiter and career coach AI.
You compare a candidate's resume against a job description and produce a precise,
structured skill-gap analysis. You read the ENTIRE resume text (experience bullets,
projects, education, certifications, and any skills sections) to infer skills the
candidate actually has, not just skills explicitly listed under a "Skills" heading.

You must respond with ONLY a single valid JSON object, with no markdown fences,
no commentary, and no text before or after it. If a category genuinely has no
relevant items, return an empty array for it instead of omitting the key or
guessing. Never fabricate experience the resume does not support.

The JSON object must exactly follow this schema:

{
  "resume_skills": {
    "technical": [string],
    "tools": [string],
    "soft": [string]
  },
  "jd_skills": {
    "technical": [string],
    "tools": [string],
    "soft": [string]
  },
  "match_score": integer (0-100, overall percentage fit of resume to JD),
  "matched_skills": [
    { "name": string, "category": "technical"|"tools"|"soft" }
  ],
  "missing_skills": [
    {
      "name": string,
      "category": "technical"|"tools"|"soft",
      "priority": "High"|"Medium"|"Low",
      "resources": [
        { "title": string, "platform": string }
      ]
    }
  ],
  "suggestions": [string]
}

Rules:
- "technical" = programming languages, frameworks, concepts, domains (e.g. Python, Machine Learning, REST APIs)
- "tools" = named software/platforms (e.g. Docker, Git, Jira, AWS, Figma)
- "soft" = soft/interpersonal/professional skills (e.g. Communication, Leadership, Teamwork)
- matched_skills = skills that appear in BOTH the resume and the JD (dedupe, use the JD's wording when reasonable)
- missing_skills = skills required by the JD that are NOT evidenced anywhere in the resume
- priority: "High" if the JD emphasizes it or repeats it / lists it as a core requirement,
  "Medium" if it's listed but secondary, "Low" if it's a nice-to-have
- For each missing skill, suggest 1-2 real, well-known learning resources as
  { "title": "<specific course or resource name>", "platform": "<e.g. Coursera, Udemy, YouTube, freeCodeCamp, official docs>" }
  Do not invent URLs.
- suggestions = 3 to 4 concrete, specific resume improvement suggestions tailored to
  closing the gap with THIS job description (not generic advice)
- match_score should realistically reflect the overlap between resume and JD skills,
  weighted toward technical/tool requirements
- Output valid JSON only. Use double quotes. No trailing commas."""


def _build_user_prompt(resume_text: str, jd_text: str) -> str:
    return (
        "=== RESUME TEXT ===\n"
        f"{_truncate(resume_text)}\n\n"
        "=== JOB DESCRIPTION TEXT ===\n"
        f"{_truncate(jd_text)}\n\n"
        "Analyze the resume against the job description and return the JSON object "
        "described in the system instructions."
    )


def _extract_json(raw: str) -> dict:
    """Best-effort extraction of a JSON object from the model's raw response."""
    raw = raw.strip()
    # Strip markdown code fences if the model added them despite instructions
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: grab the largest {...} block in the text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AnalyzerError(
                "The AI returned a response that could not be parsed as JSON."
            ) from exc

    raise AnalyzerError("The AI returned a response that could not be parsed as JSON.")


def _clean_skill_list(items) -> list:
    if not isinstance(items, list):
        return []
    cleaned = []
    seen = set()
    for item in items:
        if not isinstance(item, str):
            continue
        name = item.strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            cleaned.append(name)
    return cleaned


def _clean_skill_bucket(bucket) -> dict:
    if not isinstance(bucket, dict):
        bucket = {}
    return {
        "technical": _clean_skill_list(bucket.get("technical")),
        "tools": _clean_skill_list(bucket.get("tools")),
        "soft": _clean_skill_list(bucket.get("soft")),
    }


def _normalize_category(category) -> str:
    if isinstance(category, str) and category.strip().lower() in VALID_CATEGORIES:
        return category.strip().lower()
    return "technical"


def _normalize_priority(priority) -> str:
    if isinstance(priority, str):
        p = priority.strip().capitalize()
        if p in VALID_PRIORITIES:
            return p
    return "Medium"


def _build_resource_link(title: str, platform: str) -> str:
    """Build a reliable, always-valid search link instead of trusting a model-generated URL."""
    query = urllib.parse.quote_plus(f"{title} {platform} course")
    return f"https://www.google.com/search?q={query}"


def _clean_resources(resources) -> list:
    if not isinstance(resources, list):
        return []
    cleaned = []
    for res in resources[:2]:  # cap at 2 resources per skill
        if not isinstance(res, dict):
            continue
        title = str(res.get("title", "")).strip()
        platform = str(res.get("platform", "")).strip()
        if not title:
            continue
        if not platform:
            platform = "Online"
        cleaned.append(
            {
                "title": title,
                "platform": platform,
                "url": _build_resource_link(title, platform),
            }
        )
    return cleaned


def _normalize_response(data: dict) -> dict:
    """Guarantee every expected field exists with the correct type, no matter what the model returned."""
    if not isinstance(data, dict):
        raise AnalyzerError("The AI response was not a valid JSON object.")

    resume_skills = _clean_skill_bucket(data.get("resume_skills"))
    jd_skills = _clean_skill_bucket(data.get("jd_skills"))

    raw_score = data.get("match_score", 0)
    try:
        match_score = int(round(float(raw_score)))
    except (TypeError, ValueError):
        match_score = 0
    match_score = max(0, min(100, match_score))

    matched_skills = []
    seen_matched = set()
    for item in data.get("matched_skills", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_matched:
            continue
        seen_matched.add(key)
        matched_skills.append({"name": name, "category": _normalize_category(item.get("category"))})

    missing_skills = []
    seen_missing = set()
    for item in data.get("missing_skills", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_missing:
            continue
        seen_missing.add(key)
        missing_skills.append(
            {
                "name": name,
                "category": _normalize_category(item.get("category")),
                "priority": _normalize_priority(item.get("priority")),
                "resources": _clean_resources(item.get("resources")),
            }
        )

    # Sort missing skills: High -> Medium -> Low
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    missing_skills.sort(key=lambda s: priority_order.get(s["priority"], 1))

    suggestions = [
        str(s).strip() for s in (data.get("suggestions") or []) if isinstance(s, str) and s.strip()
    ]
    if not suggestions:
        suggestions = [
            "Add quantifiable achievements (metrics, percentages, outcomes) to your experience bullets.",
            "Mirror key terminology from the job description in your resume where it genuinely applies.",
            "Highlight projects or coursework that demonstrate the missing skills listed above.",
        ]

    return {
        "resume_skills": resume_skills,
        "jd_skills": jd_skills,
        "match_score": match_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "suggestions": suggestions[:4],
    }


def analyze_skill_gap(resume_text: str, jd_text: str) -> dict:
    """
    Run the full AI skill-gap analysis.

    Returns a normalized dict (see _normalize_response) ready to be
    serialized to the frontend and later converted to a PDF report.
    """
    if not resume_text or not resume_text.strip():
        raise AnalyzerError("Resume text is empty — nothing to analyze.")
    if not jd_text or not jd_text.strip():
        raise AnalyzerError("Job description text is empty — nothing to analyze.")

    client = _get_client()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(resume_text, jd_text)},
            ],
            temperature=0.3,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise AnalyzerError(
            "Could not reach the Groq AI service. Please check your GROQ_API_KEY "
            "and internet connection, then try again."
        ) from exc

    try:
        raw_content = completion.choices[0].message.content
    except (IndexError, AttributeError) as exc:
        raise AnalyzerError("The AI service returned an unexpected response.") from exc

    if not raw_content:
        raise AnalyzerError("The AI service returned an empty response.")

    data = _extract_json(raw_content)
    return _normalize_response(data)
