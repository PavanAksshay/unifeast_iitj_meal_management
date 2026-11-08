# Try the mess portal with sample data

The files contain 40 fictional students and 10 sample rebate requests. The email addresses, phone numbers, and roll numbers are placeholders; no SMS is sent in local demo mode. Download them from the portal or open [students.csv](../frontend/sample-data/students.csv) and [rebates.csv](../frontend/sample-data/rebates.csv).

1. Open `http://localhost:3100` and sign in as the admin using `admin@unifeast.local` and `demo-admin`.
2. On the dashboard, choose **Edit capacity** and enter `50`. Mess occupancy is the number of students with active allocations divided by this capacity. Existing demo students are included.
3. Open **Bulk student upload**, select `students.csv`, choose **Preview allocation upload**, review the preview, and select **Confirm allocation import**. The sample student dates cover the current testing period.
4. Open **Students** and **Analytics** to explore the records, filters, and gender/course breakdowns. The sample file contains roll numbers `UFSAMPLE001` through `UFSAMPLE040`.
5. Open **Rebates**, select `rebates.csv`, and preview the upload. In **Pending rebate reviews**, inspect the students and dates, then approve or reject the entire batch. A finance reviewer can also sign in as `finance@unifeast.local` with password `demo-finance` and review the same pending batch.
6. To try the student flow, sign in with `UFSAMPLE001`, select **Get a student OTP**, and use the local code shown on screen to set a password. The student must register a camera photo before collecting meals. Meal collection is available during the configured meal window; it creates real test activity for the dashboard and reports.

Re-uploading the same file after confirmation produces overlapping-allocation or rebate validation errors. To create fresh sample files with dates around the current day, run `python scripts/generate_sample_data.py` from the repository root. Regeneration updates the sample files; it does not modify the database. The sample files contain student and rebate records only: menu plans, attendance, and billing snapshots are created through their corresponding workflows.
