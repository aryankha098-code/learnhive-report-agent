"""
Automatic Weekly Report Generation Agent
-----------------------------------------
Target company : LearnHive (fictional online tutoring platform - substitution noted)
Report type    : Weekly Tutoring Sessions Summary Report

Pipeline:
    1. Load raw session data (CSV)
    2. Compute business statistics with pandas
    3. Feed statistics to Gemini (Google Generative AI) -> written narrative
    4. Generate a supporting chart (matplotlib)
    5. Assemble narrative + table + chart into a PDF report (reportlab)

Usage:
    export GEMINI_API_KEY="your_key_here"
    python3 report_agent.py
"""

import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DATA_FILE = "weekly_sessions.csv"
CHART_FILE = "sessions_by_subject.png"
OUTPUT_PDF = "LearnHive_Weekly_Report.pdf"
COMPANY_NAME = "LearnHive"  # substitution: fictional online tutoring platform


# ---------------------------------------------------------------------------
# STEP 1 & 2: Load data and compute statistics
# ---------------------------------------------------------------------------
def compute_stats(df: pd.DataFrame) -> dict:
    total_sessions = len(df)
    completed = df[df["status"] == "completed"]
    cancelled = df[df["status"] == "cancelled"]
    no_show = df[df["status"] == "no_show"]

    total_revenue = completed["price_usd"].sum()
    active_students = df["student_id"].nunique()
    active_tutors = df["tutor_id"].nunique()

    subject_counts = df["subject"].value_counts()
    top_subject = subject_counts.idxmax()

    tutor_completed = completed.groupby("tutor_name").size().sort_values(ascending=False)
    top_tutor = tutor_completed.idxmax() if len(tutor_completed) else "N/A"

    daily_counts = df.groupby("date").size()
    busiest_day = daily_counts.idxmax()

    cancellation_rate = (len(cancelled) / total_sessions) * 100
    no_show_rate = (len(no_show) / total_sessions) * 100
    completion_rate = (len(completed) / total_sessions) * 100

    avg_session_value = completed["price_usd"].mean() if len(completed) else 0

    return {
        "total_sessions": total_sessions,
        "completed_sessions": len(completed),
        "cancelled_sessions": len(cancelled),
        "no_show_sessions": len(no_show),
        "completion_rate": round(completion_rate, 1),
        "cancellation_rate": round(cancellation_rate, 1),
        "no_show_rate": round(no_show_rate, 1),
        "total_revenue": round(total_revenue, 2),
        "avg_session_value": round(avg_session_value, 2),
        "active_students": active_students,
        "active_tutors": active_tutors,
        "top_subject": top_subject,
        "subject_counts": subject_counts.to_dict(),
        "top_tutor": top_tutor,
        "busiest_day": busiest_day,
        "daily_counts": daily_counts.to_dict(),
    }


# ---------------------------------------------------------------------------
# STEP 3: Call Gemini to turn stats into a written narrative
# ---------------------------------------------------------------------------
def generate_narrative(stats: dict) -> str:
    prompt = f"""You are a business analyst at an online tutoring platform called {COMPANY_NAME}.
Write a clear, professional weekly report narrative (around 250-300 words) based on the
following statistics. Structure it into short paragraphs: an overview, a performance/trends
paragraph, and a recommendations paragraph. Do not invent numbers beyond what is given.

Statistics:
- Total sessions booked: {stats['total_sessions']}
- Completed: {stats['completed_sessions']} ({stats['completion_rate']}%)
- Cancelled: {stats['cancelled_sessions']} ({stats['cancellation_rate']}%)
- No-shows: {stats['no_show_sessions']} ({stats['no_show_rate']}%)
- Total revenue: ${stats['total_revenue']}
- Average revenue per completed session: ${stats['avg_session_value']}
- Active students: {stats['active_students']}
- Active tutors: {stats['active_tutors']}
- Most popular subject: {stats['top_subject']}
- Subject breakdown (session count): {stats['subject_counts']}
- Top performing tutor (by completed sessions): {stats['top_tutor']}
- Busiest day: {stats['busiest_day']}
"""

    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"[warning] Gemini call failed, falling back to local draft. Reason: {e}")

    # Fallback used when no API key / no network access (e.g. offline demo/testing).
    # Keeps the pipeline runnable end-to-end even without live API access.
    return (
        f"This week, {COMPANY_NAME} recorded {stats['total_sessions']} booked tutoring sessions, "
        f"of which {stats['completed_sessions']} ({stats['completion_rate']}%) were completed successfully. "
        f"Cancellations accounted for {stats['cancellation_rate']}% of bookings and no-shows for "
        f"{stats['no_show_rate']}%, both within a normal operating range.\n\n"
        f"Completed sessions generated ${stats['total_revenue']} in revenue, averaging "
        f"${stats['avg_session_value']} per session. {stats['active_students']} unique students engaged with "
        f"{stats['active_tutors']} active tutors across the week. {stats['top_subject']} was the most "
        f"requested subject, and {stats['top_tutor']} was the top-performing tutor by completed sessions. "
        f"{stats['busiest_day']} was the busiest day for bookings.\n\n"
        f"Recommendation: monitor cancellation trends closely and consider targeted tutor availability "
        f"increases for {stats['top_subject']} given its high demand, in order to sustain completion rates "
        f"and revenue growth into next week."
    )


# ---------------------------------------------------------------------------
# STEP 4: Build a supporting chart
# ---------------------------------------------------------------------------
def build_chart(stats: dict, chart_file: str = CHART_FILE):
    subjects = list(stats["subject_counts"].keys())
    counts = list(stats["subject_counts"].values())

    plt.figure(figsize=(6, 3.5))
    bars = plt.bar(subjects, counts, color="#4C72B0")
    plt.title("Sessions by Subject - This Week")
    plt.ylabel("Number of Sessions")
    plt.xticks(rotation=30, ha="right")
    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2, h + 0.3, str(int(h)),
                  ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(chart_file, dpi=150)
    plt.close()


# ---------------------------------------------------------------------------
# STEP 5: Assemble the final PDF report
# ---------------------------------------------------------------------------
def build_pdf(stats: dict, narrative: str, chart_file: str = CHART_FILE, output_pdf: str = OUTPUT_PDF):
    doc = SimpleDocTemplate(output_pdf, pagesize=letter,
                             topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=20)
    heading_style = styles["Heading2"]
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, leading=15)

    story = []

    story.append(Paragraph(f"{COMPANY_NAME} - Weekly Tutoring Sessions Report", title_style))
    story.append(Paragraph(f"Reporting period: {min(stats['daily_counts'].keys())} to "
                            f"{max(stats['daily_counts'].keys())}", body_style))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Summary Narrative", heading_style))
    for para in narrative.split("\n\n"):
        story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Key Metrics", heading_style))

    table_data = [
        ["Metric", "Value"],
        ["Total Sessions Booked", stats["total_sessions"]],
        ["Completed Sessions", f"{stats['completed_sessions']} ({stats['completion_rate']}%)"],
        ["Cancelled Sessions", f"{stats['cancelled_sessions']} ({stats['cancellation_rate']}%)"],
        ["No-Show Sessions", f"{stats['no_show_sessions']} ({stats['no_show_rate']}%)"],
        ["Total Revenue", f"${stats['total_revenue']}"],
        ["Avg. Revenue / Completed Session", f"${stats['avg_session_value']}"],
        ["Active Students", stats["active_students"]],
        ["Active Tutors", stats["active_tutors"]],
        ["Most Popular Subject", stats["top_subject"]],
        ["Top Tutor", stats["top_tutor"]],
        ["Busiest Day", stats["busiest_day"]],
    ]
    tbl = Table(table_data, colWidths=[3 * inch, 3 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C72B0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Sessions by Subject", heading_style))
    story.append(Image(chart_file, width=6 * inch, height=3.5 * inch))

    doc.build(story)


def main():
    df = pd.read_csv(DATA_FILE)
    stats = compute_stats(df)
    narrative = generate_narrative(stats)
    build_chart(stats)
    build_pdf(stats, narrative)
    print(f"Report generated: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
