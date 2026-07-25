import os
import uuid
import tempfile
import pandas as pd
from flask import Flask, request, send_file, render_template, jsonify
from dotenv import load_dotenv

load_dotenv()

from report_agent import compute_stats, generate_narrative, build_chart, build_pdf

REQUIRED_COLUMNS = {
    "date", "student_id", "tutor_id", "tutor_name",
    "subject", "duration_minutes", "status", "price_usd",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload cap


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    file = request.files.get("csv_file")
    if not file or file.filename == "":
        return jsonify({"error": "Please choose a CSV file to upload."}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only .csv files are supported."}), 400

    try:
        df = pd.read_csv(file)
    except Exception:
        return jsonify({"error": "Could not parse that file as a CSV."}), 400

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return jsonify({"error": f"CSV is missing required columns: {', '.join(sorted(missing))}"}), 400
    if df.empty:
        return jsonify({"error": "CSV has no rows."}), 400

    # ponytail: temp files aren't cleaned up; fine for low-volume demo use,
    # would need a scheduled sweep or object storage if traffic grows.
    run_id = uuid.uuid4().hex[:8]
    tmp_dir = tempfile.gettempdir()
    chart_path = os.path.join(tmp_dir, f"chart_{run_id}.png")
    pdf_path = os.path.join(tmp_dir, f"report_{run_id}.pdf")

    stats = compute_stats(df)
    narrative = generate_narrative(stats)
    build_chart(stats, chart_path)
    build_pdf(stats, narrative, chart_path, pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name="Weekly_Report.pdf")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
