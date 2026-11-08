"""Generate fictional student and rebate imports for the local mess pilot."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def sample_rows(today: date | None = None) -> tuple[list[list[str]], list[list[str]]]:
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    current_month = today.replace(day=1)
    allocation_start = (current_month - timedelta(days=1)).replace(day=1)
    month_index = today.year * 12 + today.month - 1 + 3
    allocation_end = date(month_index // 12, month_index % 12 + 1, 1) - timedelta(days=1)
    courses = [("BTech", "Computer Science"), ("BTech", "Electrical"),
               ("BTech", "Mechanical"), ("MTech", "Data Science"), ("MSc", "Physics")]
    students = [["name", "email", "phone", "roll_number", "start_date", "end_date", "gender", "course", "branch"]]
    for number in range(1, 41):
        course, branch = courses[(number - 1) % len(courses)]
        students.append([f"Sample Student {number:02d}", f"sample{number:03d}@example.com",
                         f"+910009{number:06d}", f"UFSAMPLE{number:03d}",
                         allocation_start.isoformat(), allocation_end.isoformat(),
                         "Female" if number % 2 == 0 else "Male", course, branch])

    rebates = [["roll_number", "start_date", "end_date", "reason"]]
    for number in range(1, 11):
        offset, duration, reason = [(-7, 3, "Home visit"), (-1, 3, "Travel"), (4, 3, "Academic event")][(number - 1) % 3]
        start = today + timedelta(days=offset)
        rebates.append([f"UFSAMPLE{number:03d}", start.isoformat(),
                        (start + timedelta(days=duration)).isoformat(), reason])
    return students, rebates


def generate(output_dir: Path, today: date | None = None) -> None:
    students, rebates = sample_rows(today)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("students.csv", students), ("rebates.csv", rebates)):
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as file:
            csv.writer(file).writerows(rows)


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1] / "frontend" / "sample-data")
