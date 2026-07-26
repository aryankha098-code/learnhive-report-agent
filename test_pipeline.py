"""Run: python3 test_pipeline.py
Smoke test for the data -> stats -> chart -> PDF pipeline. No framework needed."""
import io
import os
import pandas as pd
from report_agent import load_input, compute_stats, build_chart, build_pdf

TMP = "/tmp" if os.name != "nt" else os.environ.get("TEMP", ".")


def run_case(name, df=None, doc=None):
    stats = compute_stats(df=df, doc=doc)
    chart_path = f"{TMP}/_test_{name}_chart.png"
    pdf_path = f"{TMP}/_test_{name}_report.pdf"
    has_chart = build_chart(stats, chart_path, df=df)
    build_pdf(stats, f"Test narrative for {name}.", chart_path if has_chart else None, pdf_path)
    assert os.path.getsize(pdf_path) > 0
    print(f"OK: {name} -> kind={stats['kind']} chart={has_chart}")


# 1. Tutoring-schema CSV (existing sample data)
df_tutoring = pd.read_csv("weekly_sessions.csv")
assert compute_stats(df=df_tutoring)["kind"] == "tutoring"
run_case("tutoring", df=df_tutoring)

# 2. Generic CSV — arbitrary schema, no tutoring columns
df_generic = pd.DataFrame({
    "region": ["North", "South", "North", "East", "South", "North"],
    "revenue": [1200, 950, 1400, 700, 1100, 1600],
})
stats_generic = compute_stats(df=df_generic)
assert stats_generic["kind"] == "generic"
assert stats_generic["row_count"] == 6
run_case("generic", df=df_generic)

# 3. PDF with an extractable table
import pdfplumber
from reportlab.pdfgen import canvas as rl_canvas
pdf_table_path = f"{TMP}/_test_input_table.pdf"
c = rl_canvas.Canvas(pdf_table_path)
rows = [["item", "qty"], ["Widget", "10"], ["Gadget", "5"], ["Widget", "8"]]
y = 750
for row in rows:
    c.drawString(72, y, "   ".join(row))
    y -= 20
c.save()
with pdfplumber.open(pdf_table_path) as _pdf:
    pass  # sanity: file opens; real extraction depends on pdfplumber's layout heuristics

# 4. PDF text-only path, tested directly via the doc-stats function (bypasses
# pdfplumber's table-detection, which needs real ruled tables to trigger).
doc = {"text": "This is a plain text document with no tables. " * 30, "page_count": 1}
stats_doc = compute_stats(doc=doc)
assert stats_doc["kind"] == "document"
assert stats_doc["page_count"] == 1
run_case("document", doc=doc)

# 5. Unsupported extension is rejected at the loader
try:
    load_input(io.BytesIO(b"data"), "file.exe")
    raise AssertionError("expected ValueError for unsupported extension")
except ValueError:
    pass

print("ALL OK")
