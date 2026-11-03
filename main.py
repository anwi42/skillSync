"""
main.py
-------
FastAPI application entry point for SkillSync — a resume vs. job
description skill-gap analyzer powered by Groq's llama-3.3-70b-versatile.

Run locally with:
    uvicorn main:app --reload
"""

from __future__ import annotations

import io
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from analyzer import AnalyzerError, analyze_skill_gap
from parser import ParsingError, parse_jd_file, parse_resume
from report import generate_pdf

app = FastAPI(title="SkillSync", description="Resume Skill Gap Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------
# Pydantic models for the /download-report request body
# ---------------------------------------------------------------------------

class ResourceModel(BaseModel):
    title: str = ""
    platform: str = ""
    url: Optional[str] = ""


class MatchedSkillModel(BaseModel):
    name: str
    category: str = "technical"


class MissingSkillModel(BaseModel):
    name: str
    category: str = "technical"
    priority: str = "Medium"
    resources: List[ResourceModel] = []


class AnalysisReportRequest(BaseModel):
    match_score: int = 0
    matched_skills: List[MatchedSkillModel] = []
    missing_skills: List[MissingSkillModel] = []
    suggestions: List[str] = []
    resume_skills: Optional[dict] = None
    jd_skills: Optional[dict] = None


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def analyze(
    resume: UploadFile = File(...),
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
):
    # --- Parse resume ---
    try:
        resume_bytes = await resume.read()
        resume_text = parse_resume(resume.filename, resume_bytes)
    except ParsingError as exc:
        raise HTTPException(status_code=400, detail=f"Resume error: {exc}")
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read the resume file: {exc}"
        )

    # --- Resolve job description text (file takes precedence if both given, but
    #     we only use the file if it actually has content) ---
    jd_final_text: Optional[str] = None

    if jd_file is not None and jd_file.filename:
        try:
            jd_bytes = await jd_file.read()
            jd_final_text = parse_jd_file(jd_file.filename, jd_bytes)
        except ParsingError as exc:
            raise HTTPException(status_code=400, detail=f"Job description file error: {exc}")
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Could not read the job description file: {exc}"
            )
    elif jd_text and jd_text.strip():
        jd_final_text = jd_text.strip()

    if not jd_final_text:
        raise HTTPException(
            status_code=400,
            detail="Please provide a job description — either paste the text or upload a PDF, DOCX, or PPTX file.",
        )

    # --- Run AI analysis ---
    try:
        result = analyze_skill_gap(resume_text, jd_final_text)
    except AnalyzerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error during analysis: {exc}")

    return result


# ---------------------------------------------------------------------------
# /download-report
# ---------------------------------------------------------------------------

@app.post("/download-report")
async def download_report(payload: AnalysisReportRequest):
    try:
        analysis_dict = payload.model_dump()
        pdf_bytes = generate_pdf(analysis_dict)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate PDF report: {exc}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=skillsync_report.pdf"},
    )


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "SkillSync"}
