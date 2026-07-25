# LearnHive Report Agent

An AI agent that turns raw business data into a written report automatically.

Upload a weekly tutoring sessions CSV and the agent computes the key metrics, generates a written narrative summary using Google's Gemini API, builds a chart, and returns a formatted PDF report — all in one request.

## What it does

1. Reads uploaded session data (CSV)
2. Computes stats with pandas — total sessions, completion/cancellation/no-show rates, revenue, top subject, top tutor, busiest day
3. Sends those stats to Gemini, which writes a natural-language summary
4. Builds a bar chart with matplotlib
5. Assembles narrative + metrics table + chart into a PDF with ReportLab

## Tech stack

- Python, Flask
- pandas for data analysis
- Google Gemini API for narrative generation
- matplotlib for charts
- ReportLab for PDF generation
- Vanilla HTML/CSS/JS frontend (no framework, no build step)

## Project structure

```
report_agent/
├── app.py                  # Flask app — routes and upload handling
├── report_agent.py         # Core pipeline: stats, narrative, chart, PDF
├── generate_data.py        # Generates the sample dataset
├── weekly_sessions.csv     # Sample input dataset
├── templates/index.html    # Frontend
├── test_pipeline.py        # Smoke test for the pipeline
├── requirements.txt
├── Procfile                # Render deploy config
├── vercel.json              # Vercel deploy config
└── .env.example
```

## Setup

```bash
git clone https://github.com/<your-username>/learnhive-report-agent.git
cd learnhive-report-agent
pip install -r requirements.txt
cp .env.example .env   # add your GEMINI_API_KEY
python3 app.py
```

Open `http://127.0.0.1:5000`, upload a CSV, download the generated report.

## Testing

```bash
python3 test_pipeline.py
```

## Deployment

**Render**: connect the repo, it auto-detects `requirements.txt` and `Procfile`. Add `GEMINI_API_KEY` as an environment variable in the dashboard.

**Vercel**: import the repo, it reads `vercel.json`. Add `GEMINI_API_KEY` in project environment variables.

## Sample CSV columns

```
session_id, date, student_id, tutor_id, tutor_name, subject, duration_minutes, status, price_usd
```

## License

MIT
