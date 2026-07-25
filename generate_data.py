import pandas as pd
import numpy as np
from datetime import date, timedelta

np.random.seed(42)

subjects = ["Mathematics", "Physics", "Chemistry", "English", "Computer Science", "Biology"]
tutors = {
    "T101": "Sarah Ahmed", "T102": "Bilal Khan", "T103": "Ayesha Raza",
    "T104": "Omar Farooq", "T105": "Hina Malik", "T106": "Zain Abbas"
}
tutor_ids = list(tutors.keys())

start_date = date(2026, 7, 13)  # a Monday
rows = []
session_id = 1000

for day_offset in range(7):
    day = start_date + timedelta(days=day_offset)
    # more sessions on weekdays, fewer on weekend
    n_sessions = np.random.randint(18, 30) if day.weekday() < 5 else np.random.randint(8, 15)
    for _ in range(n_sessions):
        subject = np.random.choice(subjects, p=[0.28, 0.15, 0.12, 0.18, 0.17, 0.10])
        tutor_id = np.random.choice(tutor_ids)
        duration = np.random.choice([30, 45, 60, 90], p=[0.2, 0.3, 0.4, 0.1])
        status = np.random.choice(["completed", "cancelled", "no_show"], p=[0.86, 0.09, 0.05])
        price = round(duration * np.random.uniform(0.35, 0.55), 2)  # USD per session
        student_id = f"S{np.random.randint(1000, 1200)}"
        rows.append({
            "session_id": session_id,
            "date": day.isoformat(),
            "student_id": student_id,
            "tutor_id": tutor_id,
            "tutor_name": tutors[tutor_id],
            "subject": subject,
            "duration_minutes": duration,
            "status": status,
            "price_usd": price if status == "completed" else 0.0
        })
        session_id += 1

df = pd.DataFrame(rows)
df.to_csv("weekly_sessions.csv", index=False)
print(df.shape)
print(df.head(10))
