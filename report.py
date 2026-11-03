"""
report.py
---------
Generates a clean PDF report from a skill-gap analysis result using fpdf2.
"""

from __future__ import annotations

from datetime import datetime

from fpdf import FPDF

NAVY = (17, 24, 57)
ACCENT = (56, 189, 248)  # light blue accent
DARK_TEXT = (30, 33, 48)
GRAY_TEXT = (100, 105, 120)
GREEN = (22, 163, 74)
ORANGE = (234, 88, 12)
RED = (220, 38, 38)
GRAY_BADGE = (120, 124, 138)
LIGHT_LINE = (225, 228, 235)


def _s(text) -> str:
    """Sanitize text for fpdf2's default latin-1 fonts (prevents crashes on unicode)."""
    if text is None:
        return ""
    text = str(text)
    # Normalize a few common unicode punctuation marks before falling back
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", "•": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _priority_color(priority: str):
    return {"High": RED, "Medium": ORANGE, "Low": GRAY_BADGE}.get(priority, GRAY_BADGE)


def _score_color(score: int):
    if score < 40:
        return RED
    if score <= 70:
        return ORANGE
    return GREEN


class SkillSyncPDF(FPDF):
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 22, style="F")
        self.set_xy(10, 6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "SkillSync", ln=0)
        self.set_font("Helvetica", "", 10)
        self.set_xy(0, 12)
        self.set_text_color(200, 210, 230)
        self.cell(self.w - 10, 6, "Resume Skill Gap Analysis Report", align="R")
        self.set_y(26)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _section_title(pdf: SkillSyncPDF, text: str):
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _s(text), ln=1)
    pdf.set_draw_color(*LIGHT_LINE)
    y = pdf.get_y()
    pdf.line(10, y, pdf.w - 10, y)
    pdf.ln(3)


def _skill_chip_line(pdf: SkillSyncPDF, skills: list, empty_message: str):
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK_TEXT)
    if not skills:
        pdf.set_text_color(*GRAY_TEXT)
        pdf.cell(0, 6, _s(empty_message), ln=1)
        return
    text = ", ".join(skills)
    pdf.multi_cell(0, 6, _s(text))
    pdf.ln(1)


def generate_pdf(analysis: dict) -> bytes:
    pdf = SkillSyncPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    match_score = analysis.get("match_score", 0)
    matched_skills = analysis.get("matched_skills", []) or []
    missing_skills = analysis.get("missing_skills", []) or []
    suggestions = analysis.get("suggestions", []) or []

    # Generated timestamp
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRAY_TEXT)
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    pdf.cell(0, 6, _s(f"Generated on {generated_at}"), ln=1)
    pdf.ln(2)

    # ---- Match score ----
    _section_title(pdf, "Overall Match Score")
    color = _score_color(match_score)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*color)
    pdf.cell(0, 14, _s(f"{match_score}%"), ln=1)

    # score bar
    bar_x, bar_y, bar_w, bar_h = 10, pdf.get_y() + 2, pdf.w - 20, 6
    pdf.set_fill_color(*LIGHT_LINE)
    pdf.rect(bar_x, bar_y, bar_w, bar_h, style="F")
    fill_w = bar_w * max(0, min(100, match_score)) / 100
    pdf.set_fill_color(*color)
    pdf.rect(bar_x, bar_y, fill_w, bar_h, style="F")
    pdf.ln(bar_h + 6)

    # ---- Matched skills ----
    _section_title(pdf, f"Matched Skills ({len(matched_skills)})")
    matched_names = [m.get("name", "") for m in matched_skills if m.get("name")]
    _skill_chip_line(pdf, matched_names, "No directly matched skills were found.")

    # ---- Missing skills + learning path ----
    _section_title(pdf, f"Missing Skills & Learning Path ({len(missing_skills)})")
    if not missing_skills:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GRAY_TEXT)
        pdf.cell(0, 6, _s("No significant skill gaps were found. Great match!"), ln=1)
    else:
        for skill in missing_skills:
            name = skill.get("name", "")
            priority = skill.get("priority", "Medium")
            category = skill.get("category", "technical")
            resources = skill.get("resources", []) or []

            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*DARK_TEXT)
            pdf.cell(0, 7, _s(f"- {name}"), ln=1)

            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_priority_color(priority))
            pdf.cell(0, 5, _s(f"  Priority: {priority}   |   Category: {category.capitalize()}"), ln=1)

            if resources:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*GRAY_TEXT)
                for res in resources:
                    title = res.get("title", "")
                    platform = res.get("platform", "")
                    url = res.get("url", "")
                pdf.set_x(pdf.l_margin + 4)
                pdf.multi_cell(0, 5, _s(f"> {title} ({platform}) - {url}"))
            pdf.ln(2)

    # ---- Suggestions ----
    _section_title(pdf, "Resume Improvement Suggestions")
    if not suggestions:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GRAY_TEXT)
        pdf.cell(0, 6, _s("No suggestions were generated."), ln=1)
    else:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*DARK_TEXT)
        for i, suggestion in enumerate(suggestions, start=1):
            pdf.multi_cell(0, 6, _s(f"{i}. {suggestion}"))
            pdf.ln(1)

    output = pdf.output()
    return bytes(output)
