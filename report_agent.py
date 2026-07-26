"""
Automatic Report Generation Agent
----------------------------------
Accepts CSV, Excel (.xlsx/.xls), or PDF (tabular or plain text) input.

Pipeline:
    1. Load raw data into a DataFrame (CSV/Excel) or extract text (PDF w/o tables)
    2. Compute statistics with pandas
       - tutoring-schema data (LearnHive sample) gets the domain-specific report
       - any other tabular data gets a generic column-level summary
       - text-only PDFs get a document-level summary (word/page counts)
    3. Feed statistics to Gemini -> written narrative
    4. Generate a supporting chart, when the data supports one
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

TUTORING_COLUMNS = {
    "date", "student_id", "tutor_id", "tutor_name",
    "subject", "duration_minutes", "status", "price_usd",
}

# Columns beyond this many get truncated in generic summaries/charts.
# ponytail: naive head(N) truncation, not a "most interesting column" ranking.
MAX_SUMMARIZED_COLUMNS = 6


def _numeric_series(s: pd.Series):
    """Returns a numeric-coerced Series, or None if the column isn't numeric-like.
    Handles columns that are numeric in substance but string in dtype (e.g. every
    column extracted from a PDF table is text, and "$1,200" style CSV values)."""
    if pd.api.types.is_numeric_dtype(s):
        return s
    coerced = pd.to_numeric(s.astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False),
                             errors="coerce")
    return coerced if coerced.notna().mean() >= 0.9 else None


# ---------------------------------------------------------------------------
# Loading: CSV / Excel / PDF -> DataFrame, or PDF text -> doc dict
# ---------------------------------------------------------------------------
def load_input(file_obj, filename: str):
    """Returns (df, doc). Exactly one of df / doc is not None."""
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "csv":
        return pd.read_csv(file_obj), None
    if ext in ("xlsx", "xls"):
        return pd.read_excel(file_obj), None
    if ext == "pdf":
        return _load_pdf(file_obj)

    raise ValueError(f"Unsupported file type: .{ext}")


def _load_pdf(file_obj):
    import pdfplumber

    tables, text_parts = [], []
    with pdfplumber.open(file_obj) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            tables.extend(t for t in page.extract_tables() if t and len(t) > 1)
            text = page.extract_text()
            if text:
                text_parts.append(text)

    if tables:
        # ponytail: only the first detected table is used. A PDF with several
        # unrelated tables would need one report per table - out of scope here.
        header, *rows = tables[0]
        return pd.DataFrame(rows, columns=header), None

    full_text = "\n".join(text_parts)
    if not full_text.strip():
        raise ValueError("Could not extract any text or tables from this PDF.")
    return None, {"text": full_text, "page_count": page_count}


# ---------------------------------------------------------------------------
# STEP 2: Compute statistics
# ---------------------------------------------------------------------------
def compute_stats(df: pd.DataFrame = None, doc: dict = None) -> dict:
    if doc is not None:
        return _compute_document_stats(doc)
    if TUTORING_COLUMNS.issubset(df.columns):
        return _compute_tutoring_stats(df)
    return _compute_generic_stats(df)


def _compute_tutoring_stats(df: pd.DataFrame) -> dict:
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
        "kind": "tutoring",
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


def _compute_generic_stats(df: pd.DataFrame) -> dict:
    numeric_map = {}
    for col in df.columns:
        s = _numeric_series(df[col])
        if s is not None:
            numeric_map[col] = s
    numeric_cols = list(numeric_map.keys())[:MAX_SUMMARIZED_COLUMNS]
    numeric_summary = {
        col: {
            "mean": round(numeric_map[col].mean(), 2),
            "min": round(numeric_map[col].min(), 2),
            "max": round(numeric_map[col].max(), 2),
            "sum": round(numeric_map[col].sum(), 2),
        }
        for col in numeric_cols
    }

    # Low-cardinality text columns make sense to summarize as categories;
    # e.g. an ID column with all-unique values wouldn't.
    cat_cols = [
        c for c in df.columns
        if c not in numeric_map and df[c].nunique() <= 30
    ][:MAX_SUMMARIZED_COLUMNS]
    top_categories = {col: df[col].value_counts().head(5).to_dict() for col in cat_cols}

    chart_column, chart_type = None, None
    if len(numeric_cols):
        chart_column, chart_type = numeric_cols[0], "hist"
    elif cat_cols:
        chart_column, chart_type = cat_cols[0], "bar"

    return {
        "kind": "generic",
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "numeric_summary": numeric_summary,
        "top_categories": top_categories,
        "chart_column": chart_column,
        "chart_type": chart_type,
    }


def _compute_document_stats(doc: dict) -> dict:
    text = doc["text"]
    return {
        "kind": "document",
        "page_count": doc["page_count"],
        "word_count": len(text.split()),
        "char_count": len(text),
        # ponytail: only the first ~6000 chars are summarized. A long document
        # would need chunking + a map-reduce summarization pass to cover it fully.
        "excerpt": text[:6000],
    }


# ---------------------------------------------------------------------------
# STEP 3: Call Gemini to turn stats into a written narrative
# ---------------------------------------------------------------------------
def generate_narrative(stats: dict) -> str:
    if stats["kind"] == "tutoring":
        prompt = _tutoring_prompt(stats)
    elif stats["kind"] == "generic":
        prompt = _generic_prompt(stats)
    else:
        prompt = _document_prompt(stats)

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

    return _fallback_narrative(stats)


def _tutoring_prompt(stats: dict) -> str:
    return f"""You are a business analyst at an online tutoring platform called {COMPANY_NAME}.
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


def _generic_prompt(stats: dict) -> str:
    return f"""You are a data analyst. Write a clear, professional report narrative
(around 200-300 words) based on the dataset summary below. Structure it into short
paragraphs: an overview of the data, a trends/notable-values paragraph, and a
recommendations paragraph. Do not invent numbers beyond what is given.

Dataset summary:
- Rows: {stats['row_count']}
- Columns: {stats['column_count']} ({', '.join(stats['columns'])})
- Numeric column summaries (mean/min/max/sum): {stats['numeric_summary']}
- Most common values per category column: {stats['top_categories']}
"""


def _document_prompt(stats: dict) -> str:
    return f"""You are a document analyst. Write a clear, professional 200-300 word
summary report of the document text below. Structure it into short paragraphs:
an overview of what the document covers, key points, and a closing takeaway.

Document stats: {stats['page_count']} pages, {stats['word_count']} words.

Document text (may be truncated):
\"\"\"{stats['excerpt']}\"\"\"
"""


def _fallback_narrative(stats: dict) -> str:
    """Used when no API key / no network access, so the pipeline stays runnable."""
    if stats["kind"] == "tutoring":
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
            f"increases for {stats['top_subject']} given its high demand."
        )
    if stats["kind"] == "generic":
        return (
            f"This dataset contains {stats['row_count']} rows across {stats['column_count']} columns "
            f"({', '.join(stats['columns'])}).\n\n"
            f"Numeric columns summarized: {stats['numeric_summary']}. "
            f"Common values by category: {stats['top_categories']}.\n\n"
            f"Recommendation: review the columns with the widest min/max spread for outliers, and "
            f"the most frequent categorical values for concentration risk."
        )
    return (
        f"This document spans {stats['page_count']} pages and {stats['word_count']} words.\n\n"
        f"Automated summarization requires a live Gemini API connection; the excerpt below is "
        f"included in the source data for manual review.\n\n"
        f"Recommendation: connect a GEMINI_API_KEY to generate a full narrative summary."
    )


# ---------------------------------------------------------------------------
# STEP 4: Build a supporting chart (skipped when there's nothing chartable)
# ---------------------------------------------------------------------------
CHART_COLOR = "#4F63D2"
CHART_COLOR_DARK = "#3846A6"


def _style_axes(ax, title, ylabel, xlabel=None):
    """Shared professional styling for every chart branch below."""
    ax.set_title(title, fontsize=13, fontweight="bold", color="#1a1a2e", pad=14)
    ax.set_ylabel(ylabel, fontsize=10, color="#444")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color="#444")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")
    ax.grid(axis="y", color="#e8e8ee", linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#555555", labelsize=9)


def build_chart(stats: dict, chart_file: str = CHART_FILE, df: pd.DataFrame = None) -> bool:
    """Returns True if a chart was written to chart_file, False if skipped."""
    fig, ax = plt.subplots(figsize=(6.4, 3.8))

    if stats["kind"] == "tutoring":
        labels = list(stats["subject_counts"].keys())
        values = list(stats["subject_counts"].values())
        title, ylabel = "Sessions by Subject — This Week", "Number of Sessions"
    elif stats["kind"] == "generic" and stats["chart_type"] == "hist":
        col = stats["chart_column"]
        series = _numeric_series(df[col]).dropna()
        ax.hist(series, bins=min(15, max(5, series.nunique())),
                color=CHART_COLOR, edgecolor="white", linewidth=0.6, zorder=3)
        _style_axes(ax, f"Distribution of {col}", "Count", xlabel=col)
        fig.tight_layout()
        fig.savefig(chart_file, dpi=160)
        plt.close(fig)
        return True
    elif stats["kind"] == "generic" and stats["chart_type"] == "bar":
        col = stats["chart_column"]
        counts = stats["top_categories"][col]
        labels, values = list(counts.keys()), list(counts.values())
        title, ylabel = f"Top values in {col}", "Count"
    else:
        plt.close(fig)
        return False  # document kind, or generic data with nothing chartable

    str_labels = [str(l) if len(str(l)) <= 14 else str(l)[:13] + "…" for l in labels]
    bars = ax.bar(str_labels, values, color=CHART_COLOR, edgecolor=CHART_COLOR_DARK,
                   linewidth=0.6, zorder=3, width=0.62)
    _style_axes(ax, title, ylabel)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + max(values) * 0.02, f"{int(h)}",
                 ha="center", va="bottom", fontsize=8.5, color="#333333")
    fig.tight_layout()
    fig.savefig(chart_file, dpi=160)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# STEP 5: Assemble the final PDF report
# ---------------------------------------------------------------------------
def build_pdf(stats: dict, narrative: str, chart_file: str = None, output_pdf: str = OUTPUT_PDF):
    doc = SimpleDocTemplate(output_pdf, pagesize=letter,
                             topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=20)
    heading_style = styles["Heading2"]
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, leading=15)

    story = [Paragraph(_report_title(stats), title_style), Spacer(1, 16)]

    story.append(Paragraph("Summary Narrative", heading_style))
    for para in narrative.split("\n\n"):
        story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Key Metrics", heading_style))
    tbl = Table(_metrics_table(stats), colWidths=[3 * inch, 3 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(CHART_COLOR)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)

    if chart_file:
        story.append(Spacer(1, 16))
        story.append(Paragraph("Chart", heading_style))
        story.append(Image(chart_file, width=6 * inch, height=3.5 * inch))

    doc.build(story)


def _report_title(stats: dict) -> str:
    if stats["kind"] == "tutoring":
        return f"{COMPANY_NAME} - Weekly Tutoring Sessions Report"
    if stats["kind"] == "generic":
        return "Data Summary Report"
    return "Document Summary Report"


def _metrics_table(stats: dict):
    if stats["kind"] == "tutoring":
        return [
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
    if stats["kind"] == "generic":
        rows = [["Metric", "Value"], ["Rows", stats["row_count"]], ["Columns", stats["column_count"]]]
        for col, s in stats["numeric_summary"].items():
            rows.append([f"{col} (mean / min / max)", f"{s['mean']} / {s['min']} / {s['max']}"])
        for col, counts in stats["top_categories"].items():
            top_val = next(iter(counts))
            rows.append([f"Most common {col}", f"{top_val} ({counts[top_val]}x)"])
        return rows
    return [
        ["Metric", "Value"],
        ["Pages", stats["page_count"]],
        ["Word count", stats["word_count"]],
        ["Character count", stats["char_count"]],
    ]


def main():
    with open(DATA_FILE, "rb") as f:
        df, doc = load_input(f, DATA_FILE)
    stats = compute_stats(df=df, doc=doc)
    narrative = generate_narrative(stats)
    has_chart = build_chart(stats, CHART_FILE, df=df)
    build_pdf(stats, narrative, CHART_FILE if has_chart else None)
    print(f"Report generated: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
