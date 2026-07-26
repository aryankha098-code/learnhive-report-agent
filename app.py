import os
import uuid
import tempfile
from flask import Flask, request, send_file, render_template, jsonify
from dotenv import load_dotenv

load_dotenv()

from report_agent import load_input, compute_stats, generate_narrative, build_chart, build_pdf

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "pdf"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB upload cap


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    file = request.files.get("csv_file")
    if not file or file.filename == "":
        return jsonify({"error": "Please choose a file to upload."}), 400

    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only .csv, .xlsx, .xls, or .pdf files are supported."}), 400

    try:
        df, doc = load_input(file, file.filename)
    except Exception as e:
        return jsonify({"error": f"Could not read that file: {e}"}), 400

    if df is not None and df.empty:
        return jsonify({"error": "That file has no rows."}), 400

    # ponytail: temp files aren't cleaned up; fine for low-volume demo use,
    # would need a scheduled sweep or object storage if traffic grows.
    run_id = uuid.uuid4().hex[:8]
    tmp_dir = tempfile.gettempdir()
    chart_path = os.path.join(tmp_dir, f"chart_{run_id}.png")
    pdf_path = os.path.join(tmp_dir, f"report_{run_id}.pdf")

    stats = compute_stats(df=df, doc=doc)
    narrative = generate_narrative(stats)
    has_chart = build_chart(stats, chart_path, df=df)
    build_pdf(stats, narrative, chart_path if has_chart else None, pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name="Report.pdf")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
