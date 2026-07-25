"""Run: python3 test_pipeline.py
Smoke test for the CSV -> stats -> chart -> PDF pipeline. No framework needed."""
import os
import pandas as pd
from report_agent import compute_stats, build_chart, build_pdf

df = pd.read_csv("weekly_sessions.csv")
stats = compute_stats(df)

assert stats["total_sessions"] == len(df)
assert stats["completed_sessions"] + stats["cancelled_sessions"] + stats["no_show_sessions"] == len(df)
assert 0 <= stats["completion_rate"] <= 100
assert stats["top_subject"] in df["subject"].unique()

build_chart(stats, "/tmp/_test_chart.png")
build_pdf(stats, "Test narrative.", "/tmp/_test_chart.png", "/tmp/_test_report.pdf")

assert os.path.getsize("/tmp/_test_chart.png") > 0
assert os.path.getsize("/tmp/_test_report.pdf") > 0

print("OK: pipeline produced valid stats, chart, and PDF.")
