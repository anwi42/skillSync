# SkillSync

**SkillSync** is a resume ↔ job description skill-gap analyzer. Upload your resume
and a job description, and SkillSync uses AI (Groq's `llama-3.3-70b-versatile`)
to calculate a match score, show which skills you have, which ones are missing,
their priority, suggested learning resources, and resume improvement tips — then
lets you download the whole analysis as a PDF report.

## Features

- Upload resume as **PDF** or **DOCX**
- Provide the job description by **pasting text** or uploading a **PDF/PPTX**
- AI reads the entire resume (experience, projects, education, skills) — not just a skills section
- Match score gauge (red / yellow / green)
- Matched skills, missing skills (with High/Medium/Low priority), and learning resources
- Resume improvement suggestions tailored to the job description
- Downloadable PDF report
- Single-page app, no database, fully stateless per request

## Tech Stack

| Layer          | Technology                              |
|----------------|------------------------------------------|
| Backend        | FastAPI (Python)                        |
| AI             | Groq API — `llama-3.3-70b-versatile`    |
| PDF parsing    | PyMuPDF (`fitz`)                        |
| DOCX parsing   | `python-docx`                           |
| PPTX parsing   | `python-pptx`                           |
| PDF report     | `fpdf2`                                 |
| Frontend       | Single static HTML/CSS/JS file          |

## Project Structure

```
SkillSync/
├── main.py              # FastAPI app & API endpoints
├── parser.py             # Resume/JD text extraction (PDF, DOCX, PPTX)
├── analyzer.py            # Groq API call + JSON parsing/normalization
├── report.py              # PDF report generation (fpdf2)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── static/
    └── index.html         # Frontend UI
```

## Setup

### 1. Clone / open the project folder

```bash
cd SkillSync
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a Groq API key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up / log in
3. Navigate to **API Keys** and create a new key
4. Copy the key

### 5. Configure your environment

Copy `.env.example` to `.env` and paste in your key:

```bash
cp .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=your_actual_key_here
```

> `.env` is already included in `.gitignore` — it will never be committed.

### 6. Run the app

```bash
uvicorn main:app --reload
```

Open your browser at **http://127.0.0.1:8000**

## How to Use

1. **Step 1** — Upload your resume (PDF or DOCX, max 10MB)
2. **Step 2** — Either paste the job description text, or toggle to "Upload File" and upload a PDF/PPTX
3. **Step 3** — Click **Analyze Skill Gap**
4. Review your match score, matched/missing skills, learning resources, and suggestions
5. Click **Download Report (PDF)** to save the full analysis

## API Endpoints

### `POST /analyze`

Multipart form data:
- `resume` (file, required) — PDF or DOCX
- `jd_text` (string, optional) — plain text job description
- `jd_file` (file, optional) — PDF or PPTX job description

> Provide either `jd_text` or `jd_file`.

Returns JSON:

```json
{
  "resume_skills": { "technical": [...], "tools": [...], "soft": [...] },
  "jd_skills": { "technical": [...], "tools": [...], "soft": [...] },
  "match_score": 72,
  "matched_skills": [{ "name": "Python", "category": "technical" }],
  "missing_skills": [
    {
      "name": "Kubernetes",
      "category": "tools",
      "priority": "High",
      "resources": [{ "title": "Kubernetes for Beginners", "platform": "Udemy", "url": "..." }]
    }
  ],
  "suggestions": ["...", "...", "..."]
}
```

### `POST /download-report`

Accepts the JSON object returned by `/analyze` in the request body and returns a
`application/pdf` file (`skillsync_report.pdf`).

## Limits & Error Handling

- Max file size: **10MB** per file
- Supported resume formats: **PDF, DOCX**
- Supported JD formats: **PDF, PPTX, or plain text**
- Clear error messages are returned for unreadable files, missing JD input, or Groq API failures (bad key, network issues, etc.)

## Notes

- No database is used — every request is analyzed independently (stateless).
- The Groq API key must be supplied by you via `.env`; it is never hardcoded.
