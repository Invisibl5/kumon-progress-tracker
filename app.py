import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# --- Session State for Settings ---
if 'saved_settings' not in st.session_state:
    st.session_state.saved_settings = {
        'email': '',
        'subject': '',
        'message': '',
        'password': '',
        'sheet_url': ''
    }

# Use Eastern Time
eastern = pytz.timezone("America/New_York")
today = datetime.now(eastern)

st.title("📊 Weekly Study Activity Tracker")
st.caption(f"Report generated at {today.strftime('%I:%M %p on %B %d, %Y')} (Eastern Time)")

report_mode = st.radio("Choose Report Mode", ["📅 Weekly Comparison", "🗓️ Monthly Summary"])

def extract_date_from_filename(filename):
    match = re.search(r'(\d{8})', filename)
    if match:
        return datetime.strptime(match.group(1), "%m%d%Y")
    return None

# Helper to check if email is valid
def is_valid_email(email):
    return isinstance(email, str) and re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)

def load_parent_map(url):
    try:
        parent_map = pd.read_csv(url)
    except Exception:
        parent_map = pd.read_csv(url, on_bad_lines='skip')
        st.warning("⚠️ Some rows in the parent contact sheet were skipped due to formatting issues.")
    # Normalize column names: strip whitespace for easier comparison
    parent_map.columns = [col.strip() for col in parent_map.columns]
    normalized_cols = [col.strip().lower() for col in parent_map.columns]
    if "parent email" not in normalized_cols:
        # Fallback 1: find first column containing "email" (case-insensitive)
        found = False
        for idx, col in enumerate(normalized_cols):
            if "email" in col:
                orig_col = parent_map.columns[idx]
                parent_map.rename(columns={orig_col: "Parent Email"}, inplace=True)
                found = True
                break
        # Fallback 2: scan for column with majority of non-null values containing "@"
        if not found:
            # Exclude "Full Name" and "Login ID" columns
            exclude = set([c.strip().lower() for c in ["Full Name", "Login ID"]])
            for col in parent_map.columns:
                col_lc = col.strip().lower()
                if col_lc in exclude:
                    continue
                # Count non-null values and those with '@'
                series = parent_map[col].dropna().astype(str)
                if len(series) == 0:
                    continue
                at_count = series.str.contains("@").sum()
                if at_count > (len(series) / 2):  # majority
                    parent_map.rename(columns={col: "Parent Email"}, inplace=True)
                    break
    return parent_map

# --- Report Modes ---
if report_mode == "📅 Weekly Comparison":
    st.write("Upload last week's and this week's CSV files to compare study progress.")
    # File uploaders
    last_week_file = st.file_uploader("Upload LAST week's CSV", type="csv", key="last")
    this_week_file = st.file_uploader("Upload THIS week's CSV", type="csv", key="this")

    if last_week_file and this_week_file:
        # Display file names
        # st.markdown(f"**Last Week File:** {last_week_file.name}")
        # st.markdown(f"**This Week File:** {this_week_file.name}")

        # Try to extract dates
        date_last = extract_date_from_filename(last_week_file.name)
        date_this = extract_date_from_filename(this_week_file.name)
        # --- Formatted Date Range String ---
        date_range_str = f"{date_last.strftime('%B %d')} to {date_this.strftime('%B %d')}" if date_last and date_this else ""
        if date_range_str:
            st.markdown(f"**Date Range:** {date_range_str}  ")

        # Infer subject type from filename
        subject_type = ""
        if "math" in this_week_file.name.lower():
            subject_type = "Math"
        elif "reading" in this_week_file.name.lower():
            subject_type = "Reading"

        if date_last and date_this:
            delta_days = (date_this - date_last).days
            st.markdown(f"**Date Range:** {date_last.strftime('%B %d, %Y')} to {date_this.strftime('%B %d, %Y')}  ")
            st.markdown(f"**Days Between Reports:** {delta_days} days")

        last_df = pd.read_csv(last_week_file)
        this_df = pd.read_csv(this_week_file)

        # Ensure Login ID is treated as string
        last_df["Login ID"] = last_df["Login ID"].astype(str)
        this_df["Login ID"] = this_df["Login ID"].astype(str)

        # Select relevant columns only
        last_trimmed = last_df[["Login ID", "Full Name", "# of WS", "# of Study Days", "Highest WS Completed"]].copy()
        this_trimmed = this_df[["Login ID", "Full Name", "# of WS", "# of Study Days", "Highest WS Completed"]].copy()

        # Rename columns for clarity before merging
        last_trimmed = last_trimmed.rename(columns={
            "# of WS": "WS_Last", 
            "# of Study Days": "Days_Last"
        })
        this_trimmed = this_trimmed.rename(columns={
            "# of WS": "WS_This", 
            "# of Study Days": "Days_This"
        }).copy()

        # Merge on Login ID (inner to find returning students)
        merged = pd.merge(this_trimmed, last_trimmed, on="Login ID", how="inner", suffixes=("_This", "_Last"))

        # Calculate weekly difference
        merged["Worksheets This Week"] = merged["WS_This"] - merged["WS_Last"]
        merged["Study Days This Week"] = merged["Days_This"] - merged["Days_Last"]

        weekly_report = merged[[
            "Login ID",
            "Full Name_This",
            "Worksheets This Week",
            "Study Days This Week",
            "Highest WS Completed_This"
        ]]
        weekly_report = weekly_report.rename(columns={
            "Full Name_This": "Full Name",
            "Highest WS Completed_This": "Highest WS Completed"
        })

        # Find new students
        new_students = this_trimmed[~this_trimmed["Login ID"].isin(last_trimmed["Login ID"])]
        new_students = new_students.rename(columns={
            "WS_This": "Worksheets This Week",
            "Days_This": "Study Days This Week"
        })

        st.subheader("📈 Returning Students – Weekly Progress")
        st.dataframe(weekly_report)

        st.subheader("🆕 New Students")
        st.dataframe(new_students)

        # Option to download results
        st.download_button("Download Weekly Report CSV", data=weekly_report.to_csv(index=False), file_name="weekly_report.csv")
        st.download_button("Download New Students CSV", data=new_students.to_csv(index=False), file_name="new_students.csv")

        st.subheader("📧 Email Weekly Reports to Parents")

        # --- Email Settings Section (with session state) ---
        st.markdown("""To use Gmail SMTP, you'll need to [create an App Password](https://support.google.com/accounts/answer/185833). Use that instead of your normal Gmail password.""")
        sender_email = st.text_input("Sender Gmail address", value=st.session_state.saved_settings['email'])
        sender_pass = st.text_input("App Password", type="password", value=st.session_state.saved_settings.get('password', ''))
        subject_line = st.text_input(
            "Email Subject",
            value=st.session_state.saved_settings['subject'] or (f"Your Child's Weekly {subject_type} Progress" if subject_type else "Your Child's Weekly Study Progress")
        )
        # Message template with new default and {date_range}
        message_template = st.text_area(
            "Email Message Template (use {parent}, {student}, {worksheets}, {days}, {highest_ws}, {date_range})",
            value=st.session_state.saved_settings['message'] or (
                "Dear {parent},\n\n"
                "Here is the weekly study update for {student} from {date_range}:\n"
                "- Worksheets completed this week: {worksheets}\n"
                "- Study days this week: {days}\n"
                "- Highest worksheet completed: {highest_ws}\n\n"
                "Keep up the great work!\n"
            ),
            height=180
        )
        # Parent email mapping via Google Sheets CSV export link
        parent_map_url = st.text_input(
            "Paste Google Sheets CSV export link for parent contacts",
            value=st.session_state.saved_settings.get('sheet_url', '')
        )
        # Save button for settings
        if st.button("💾 Save Email Settings"):
            st.session_state.saved_settings = {
                'email': sender_email,
                'subject': subject_line,
                'message': message_template,
                'password': sender_pass,
                'sheet_url': parent_map_url
            }
            st.success("✅ Settings saved.")

        refresh = st.button("🔄 Refresh Parent Contact Data")

        if parent_map_url:
            # Always load the map, and allow refresh to be a manual trigger too
            if (
                "docs.google.com/spreadsheets" in parent_map_url
                and "export?format=csv" not in parent_map_url
            ):
                sheet_id_match = re.search(r"/d/([a-zA-Z0-9-_]+)", parent_map_url)
                if sheet_id_match:
                    sheet_id = sheet_id_match.group(1)
                    parent_map_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

            parent_map = load_parent_map(parent_map_url)
            st.write("Loaded Parent Map Columns:", parent_map.columns.tolist())
            parent_map.columns = parent_map.columns.str.strip()
            # Ensure "Parent Email" column exists, else fallback to any column containing "email"
            normalized_cols = [col.strip().lower() for col in parent_map.columns]
            if "parent email" not in normalized_cols:
                for idx, col in enumerate(normalized_cols):
                    if "email" in col:
                        orig_col = parent_map.columns[idx]
                        parent_map.rename(columns={orig_col: "Parent Email"}, inplace=True)
                        break
            if "Login ID" not in parent_map.columns:
                for col in parent_map.columns:
                    if col.strip().lower() == "login id":
                        parent_map.rename(columns={col: "Login ID"}, inplace=True)
                        break
            weekly_report["Login ID"] = weekly_report["Login ID"].astype(str)
            parent_map["Login ID"] = parent_map["Login ID"].astype(str)
            new_students["Login ID"] = new_students["Login ID"].astype(str)
            full_report = pd.merge(weekly_report, parent_map, on="Login ID", how="left", suffixes=("", "_parent"))
            # After merging, also ensure "Parent Email" column exists in full_report (fallback)
            if "Parent Email" not in full_report.columns:
                normalized_cols = [col.strip().lower() for col in full_report.columns]
                for idx, col in enumerate(normalized_cols):
                    if "email" in col:
                        orig_col = full_report.columns[idx]
                        full_report.rename(columns={orig_col: "Parent Email"}, inplace=True)
                        break
            full_report["Full Name"] = weekly_report["Full Name"]
            if "Login ID" not in full_report.columns:
                full_report = pd.merge(full_report, this_trimmed[["Login ID", "Full Name"]], on="Full Name", how="left")

            unmatched_parents = full_report[full_report["Parent Email"].isnull()][["Login ID", "Full Name"]].copy()
            unmatched_parents["Reason"] = "No matching parent email"
            new_students_merged = pd.merge(new_students, parent_map, on="Login ID", how="left", suffixes=("", "_parent"))
            new_students_merged["Full Name"] = new_students_merged["Full Name"].combine_first(new_students["Full Name"])
            # Ensure "Parent Email" column exists in new_students_merged (fallback)
            if "Parent Email" not in new_students_merged.columns:
                normalized_cols = [col.strip().lower() for col in new_students_merged.columns]
                for idx, col in enumerate(normalized_cols):
                    if "email" in col:
                        orig_col = new_students_merged.columns[idx]
                        new_students_merged.rename(columns={orig_col: "Parent Email"}, inplace=True)
                        break
            if "Login ID" not in new_students_merged.columns:
                new_students_merged = pd.merge(new_students_merged, this_trimmed[["Login ID", "Full Name"]], on="Full Name", how="left")
            unmatched_new = new_students_merged[new_students_merged["Parent Email"].isnull()][["Login ID", "Full Name"]].copy()
            unmatched_new["Reason"] = "New student with no parent email"
            unmatched_all = pd.concat([unmatched_parents, unmatched_new], ignore_index=True)
            if not unmatched_all.empty:
                st.subheader("⚠️ Students Without Parent Emails")
                st.dataframe(unmatched_all)
                st.download_button("Download Missing Parent Emails CSV", data=unmatched_all.to_csv(index=False), file_name="missing_parent_emails.csv")
            if full_report["Parent Email"].isnull().any():
                st.warning("⚠️ Some students do not have a matching parent email in the mapping file.")
            else:
                st.success("✅ All students matched to parent emails.")

            # --- Charts Section ---
            st.subheader("📊 Student Engagement Charts")
            import altair as alt

            chart_df = full_report.copy()
            chart_df["Worksheets"] = chart_df.get("Worksheets This Week", chart_df.get("Worksheets This Month", 0))
            chart_df["Study Days"] = chart_df.get("Study Days This Week", chart_df.get("Study Days This Month", 0))
            chart_df = chart_df.dropna(subset=["Full Name"])
            chart_data = chart_df[["Full Name", "Worksheets", "Study Days"]].set_index("Full Name")
            st.bar_chart(chart_data)

        # Send emails button and logic (always visible if full_report exists)
        if 'full_report' in locals():
            # --- Dashboard Summary ---
            st.subheader("📊 Summary")
            total_sent = len(full_report.dropna(subset=["Parent Email"]))
            total_new = len(new_students)
            total_missing = len(unmatched_all) if 'unmatched_all' in locals() else 0
            st.markdown(f"""
- 📩 **{total_sent} students** matched with parent emails
- 🆕 **{total_new} new students**
- ⚠️ **{total_missing} students** missing parent emails
""")

            # --- Email Preview Section ---
            st.subheader("📧 Email Preview")
            st.write(f"**Subject Line Preview:** {subject_line}")
            st.write("✅ Select which students should receive the email below:")
            preview_df = full_report.copy()
            filter_valid_only = st.checkbox("✅ Only show students with valid parent emails", value=True)
            # Mark valid emails, if column exists
            if "Parent Email" in preview_df.columns:
                if filter_valid_only:
                    email_mask = preview_df["Parent Email"].astype(str).apply(
                        lambda x: isinstance(x, str) and bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", x))
                    )
                    preview_df = preview_df[email_mask]
                preview_df["Valid Email"] = preview_df["Parent Email"].astype(str).apply(
                    lambda x: "✅" if is_valid_email(x) else "❌"
                )
            else:
                st.warning("⚠️ 'Parent Email' column not found in preview data. Skipping email preview filtering.")
                preview_df["Valid Email"] = "❌"
            preview_df["Email Body"] = preview_df.apply(
                lambda row: message_template.format(
                    parent=row.get('Parent Name') if pd.notna(row.get('Parent Name')) else "Parent",
                    student=row['Full Name'],
                    worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                    days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                    highest_ws=row['Highest WS Completed'],
                    date_range=date_range_str
                ), axis=1)

            selected_emails = st.multiselect(
                "Check students to include in the email send list:",
                options=preview_df["Full Name"].tolist(),
                default=preview_df["Full Name"].tolist(),
                key="email_preview_selector"
            )

            preview_df = preview_df[preview_df["Full Name"].isin(selected_emails)]
            cols_to_show = [col for col in ["Parent Name", "Parent Email", "Valid Email", "Email Body"] if col in preview_df.columns]
            st.dataframe(preview_df[cols_to_show])

            # --- Send to Self Toggle ---
            send_to_self = st.checkbox("Send preview email to myself only", value=False)

            # --- Send Emails Section ---
            test_mode = st.checkbox("Test Mode (Print emails to console only, do not send)", value=True)
            if st.button("Send Emails"):
                progress_bar = st.progress(0)
                total = len(preview_df.dropna(subset=["Parent Email"]))
                email_log = []
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Preview to self (always send, then print if test_mode)
                if send_to_self:
                    row = preview_df.iloc[0]
                    body = message_template.format(
                        parent=row.get('Parent Name', 'Parent'),
                        student=row['Full Name'],
                        worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                        days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                        highest_ws=row['Highest WS Completed'],
                        date_range=date_range_str
                    )
                    msg = MIMEMultipart()
                    msg['From'] = sender_email
                    msg['To'] = sender_email
                    msg['Subject'] = subject_line
                    msg.attach(MIMEText(body, 'plain'))
                    try:
                        server = smtplib.SMTP("smtp.gmail.com", 587)
                        server.starttls()
                        server.login(sender_email, sender_pass)
                        server.send_message(msg)
                        server.quit()
                        if test_mode:
                            st.write("📨 Preview email (to self):")
                            st.code(body)
                        else:
                            st.success("✅ Preview email sent to yourself.")
                        email_log.append({
                            'Timestamp': timestamp,
                            'Login ID': row['Login ID'],
                            'Student': row['Full Name'],
                            'Parent Email': sender_email,
                            'Status': 'Preview to Self' + (' (Test Mode)' if test_mode else '')
                        })
                    except Exception as e:
                        st.error(f"❌ Failed to send preview email to yourself: {e}")

                # Now branch: test_mode or real send (excluding first row if send_to_self)
                if test_mode:
                    for i, (_, row) in enumerate(preview_df.iterrows()):
                        print(f"TO: {row['Parent Email']}")
                        body = message_template.format(
                            parent=row.get('Parent Name', 'Parent'),
                            student=row['Full Name'],
                            worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                            days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                            highest_ws=row['Highest WS Completed'],
                            date_range=date_range_str
                        )
                        print(body)
                        st.write(f"📨 Email to: {row['Parent Email']}")
                        st.code(body)
                        email_log.append({
                            'Timestamp': timestamp,
                            'Login ID': row['Login ID'],
                            'Student': row['Full Name'],
                            'Parent Email': row['Parent Email'],
                            'Status': 'Test Mode'
                        })
                        progress_value = min((i + 1) / total, 1.0) if total else 1.0
                        progress_bar.progress(progress_value)
                    if email_log:
                        email_log_df = pd.DataFrame(email_log)
                        st.subheader("📜 Test Mode Email Log")
                        st.dataframe(email_log_df)
                    st.success("✅ Test mode: Emails printed to console.")
                    st.balloons()
                elif not send_to_self:
                    try:
                        server = smtplib.SMTP("smtp.gmail.com", 587)
                        server.starttls()
                        server.login(sender_email, sender_pass)
                        failed_emails = []
                        email_rows = preview_df.copy()
                        if send_to_self:
                            email_rows = email_rows.iloc[1:]
                        for i, (_, row) in enumerate(email_rows.dropna(subset=["Parent Email"]).iterrows()):
                            try:
                                msg = MIMEMultipart()
                                msg['From'] = sender_email
                                msg['To'] = str(row['Parent Email'])
                                msg['Subject'] = subject_line
                                body = message_template.format(
                                    parent=row.get('Parent Name', 'Parent'),
                                    student=row['Full Name'],
                                    worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                                    days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                                    highest_ws=row['Highest WS Completed'],
                                    date_range=date_range_str
                                )
                                msg.attach(MIMEText(body, 'plain'))
                                server.send_message(msg)
                                email_log.append({
                                    'Timestamp': timestamp,
                                    'Login ID': row['Login ID'],
                                    'Student': row['Full Name'],
                                    'Parent Email': row['Parent Email'],
                                    'Status': 'Sent'
                                })
                            except Exception as e:
                                failed_emails.append({
                                    'Login ID': row.get('Login ID', ''),
                                    'Full Name': row.get('Full Name', ''),
                                    'Parent Name': row.get('Parent Name', ''),
                                    'Parent Email': row.get('Parent Email', ''),
                                    'Error': str(e)
                                })
                            progress_value = min((i + 1) / total, 1.0) if total else 1.0
                            progress_bar.progress(progress_value)
                        server.quit()
                        if failed_emails:
                            failed_df = pd.DataFrame(failed_emails)
                            st.subheader("❌ Failed Email Report")
                            st.dataframe(failed_df)
                            st.download_button("Download Failed Emails CSV", data=failed_df.to_csv(index=False), file_name="failed_emails.csv")
                        else:
                            st.success("✅ Emails sent successfully!")
                            st.balloons()
                    except Exception as e:
                        st.error(f"❌ Failed to send emails: {e}")
                # --- Show Email Log if any emails handled ---
                if email_log:
                    email_log_df = pd.DataFrame(email_log)
                    st.subheader("📜 Email Log")
                    st.dataframe(email_log_df)
                    st.download_button("Download Email Log", data=email_log_df.to_csv(index=False), file_name="email_log.csv")


elif report_mode == "🗓️ Monthly Summary":
    st.subheader("🗓️ Monthly Summary Mode")
    st.write("Upload a single CSV file representing the end-of-month progress.")
    monthly_file = st.file_uploader("Upload Monthly Report CSV", type="csv", key="monthly")

    if monthly_file:
        date_month = extract_date_from_filename(monthly_file.name)
        if date_month:
            date_range_str = date_month.strftime('%B %d, %Y')
        else:
            date_range_str = "this month"
        st.markdown(f"**Date Range:** {date_range_str}")
        # --- Subject detection logic like weekly mode ---
        subject_type = ""
        if "math" in monthly_file.name.lower():
            subject_type = "Math"
        elif "reading" in monthly_file.name.lower():
            subject_type = "Reading"

        month_df = pd.read_csv(monthly_file)
        month_df["Login ID"] = month_df["Login ID"].astype(str)

        summary = month_df[["Login ID", "Full Name", "# of WS", "# of Study Days", "Highest WS Completed"]].copy()
        summary = summary.rename(columns={
            "# of WS": "Worksheets This Month",
            "# of Study Days": "Study Days This Month"
        })

        st.dataframe(summary)
        st.download_button("Download Monthly Summary CSV", data=summary.to_csv(index=False), file_name="monthly_summary.csv")

        # Ensure parent_map_url is defined before charts section
        parent_map_url = st.session_state.saved_settings.get('sheet_url', '')

        # --- Charts Section ---
        st.subheader("📊 Student Engagement Charts")
        import altair as alt

        if parent_map_url:
            if (
                "docs.google.com/spreadsheets" in parent_map_url
                and "export?format=csv" not in parent_map_url
            ):
                sheet_id_match = re.search(r"/d/([a-zA-Z0-9-_]+)", parent_map_url)
                if sheet_id_match:
                    sheet_id = sheet_id_match.group(1)
                    parent_map_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

            parent_map = load_parent_map(parent_map_url)
            parent_map.columns = parent_map.columns.str.strip()
            # Ensure "Parent Email" column exists, else fallback to any column containing "email"
            normalized_cols = [col.strip().lower() for col in parent_map.columns]
            if "parent email" not in normalized_cols:
                for idx, col in enumerate(normalized_cols):
                    if "email" in col:
                        orig_col = parent_map.columns[idx]
                        parent_map.rename(columns={orig_col: "Parent Email"}, inplace=True)
                        break
            if "Login ID" not in parent_map.columns:
                for col in parent_map.columns:
                    if col.strip().lower() == "login id":
                        parent_map.rename(columns={col: "Login ID"}, inplace=True)
                        break
            summary["Login ID"] = summary["Login ID"].astype(str)
            parent_map["Login ID"] = parent_map["Login ID"].astype(str)

            full_report = pd.merge(summary, parent_map, on="Login ID", how="left", suffixes=("", "_parent"))
            # After merging, also ensure "Parent Email" column exists in full_report (fallback)
            if "Parent Email" not in full_report.columns:
                normalized_cols = [col.strip().lower() for col in full_report.columns]
                for idx, col in enumerate(normalized_cols):
                    if "email" in col:
                        orig_col = full_report.columns[idx]
                        full_report.rename(columns={orig_col: "Parent Email"}, inplace=True)
                        break
            chart_df = full_report.copy()
        else:
            # If no parent map, just use summary
            full_report = summary
            chart_df = summary.copy()

        chart_df["Worksheets"] = chart_df.get("Worksheets This Week", chart_df.get("Worksheets This Month", 0))
        chart_df["Study Days"] = chart_df.get("Study Days This Week", chart_df.get("Study Days This Month", 0))
        chart_df = chart_df.dropna(subset=["Full Name"])
        chart_data = chart_df[["Full Name", "Worksheets", "Study Days"]].set_index("Full Name")
        st.bar_chart(chart_data)

        # Email options
        st.subheader("📧 Email Monthly Reports to Parents")
        st.markdown("""To use Gmail SMTP, you'll need to [create an App Password](https://support.google.com/accounts/answer/185833). Use that instead of your normal Gmail password.""")

        sender_email = st.text_input("Sender Gmail address", value=st.session_state.saved_settings['email'])
        sender_pass = st.text_input("App Password", type="password", value=st.session_state.saved_settings.get('password', ''))
        subject_line = st.text_input(
            "Email Subject",
            value=st.session_state.saved_settings['subject'] or (f"Your Child's Monthly {subject_type} Progress" if subject_type else "Your Child's Monthly Study Progress")
        )
        message_template = st.text_area(
            "Email Message Template (use {parent}, {student}, {worksheets}, {days}, {highest_ws}, {date_range})",
            value=st.session_state.saved_settings['message'] or (
                "Dear {parent},\n\n"
                "Here is the monthly study summary for {student} from {date_range}:\n"
                "- Worksheets completed: {worksheets}\n"
                "- Study days: {days}\n"
                "- Highest worksheet completed: {highest_ws}\n\n"
                "Keep up the great work!\n"
            ),
            height=180
        )

        parent_map_url = st.text_input(
            "Paste Google Sheets CSV export link for parent contacts",
            value=st.session_state.saved_settings.get('sheet_url', '')
        )

        if st.button("💾 Save Email Settings"):
            st.session_state.saved_settings = {
                'email': sender_email,
                'subject': subject_line,
                'message': message_template,
                'password': sender_pass,
                'sheet_url': parent_map_url
            }
            st.success("✅ Settings saved.")

        if parent_map_url:
            # The parent_map and full_report code above already ran, so we don't need to reload it here.
            # --- Show students without parent emails ---
            if "Parent Email" in full_report.columns:
                unmatched_students = full_report[full_report["Parent Email"].isnull()][["Login ID", "Full Name"]].copy()
                unmatched_students["Reason"] = "No matching parent email"
            else:
                st.warning("⚠️ 'Parent Email' column not found in parent mapping. Please ensure your sheet includes it.")
                unmatched_students = pd.DataFrame(columns=["Login ID", "Full Name", "Reason"])

            if not unmatched_students.empty:
                st.subheader("⚠️ Students Without Parent Emails")
                st.dataframe(unmatched_students)
                st.download_button(
                    "Download Missing Parent Emails CSV",
                    data=unmatched_students.to_csv(index=False),
                    file_name="missing_parent_emails.csv"
                )

            st.subheader("📊 Summary")
            if "Parent Email" in full_report.columns:
                unmatched = full_report[full_report["Parent Email"].isnull()][["Login ID", "Full Name"]]
            else:
                unmatched = pd.DataFrame(columns=["Login ID", "Full Name"])
            if "Parent Email" in full_report.columns:
                matched_count = len(full_report.dropna(subset=["Parent Email"]))
            else:
                matched_count = 0
            missing_count = len(unmatched)
            st.markdown(f"""
- 📩 **{matched_count} students** matched with parent emails
- ⚠️ **{missing_count} students** missing parent emails
""")

            st.subheader("📧 Email Preview")
            st.write(f"**Subject Line Preview:** {subject_line}")
            st.write("✅ Select which students should receive the email below:")
            preview_df = full_report.copy()
            filter_valid_only = st.checkbox("✅ Only show students with valid parent emails", value=True)
            if "Parent Email" in preview_df.columns and filter_valid_only:
                email_mask = preview_df["Parent Email"].astype(str).apply(lambda x: isinstance(x, str) and bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", x)))
                preview_df = preview_df[email_mask]
            elif "Parent Email" not in preview_df.columns:
                st.warning("⚠️ 'Parent Email' column not found in preview data. Skipping email preview filtering.")
            if "Parent Email" in preview_df.columns:
                preview_df["Valid Email"] = preview_df["Parent Email"].astype(str).apply(lambda x: "✅" if is_valid_email(x) else "❌")
            else:
                preview_df["Valid Email"] = "❌"
                st.warning("⚠️ 'Parent Email' column missing — unable to mark valid emails.")
            preview_df["Email Body"] = preview_df.apply(
                lambda row: message_template.format(
                    parent=row.get('Parent Name') if pd.notna(row.get('Parent Name')) else "Parent",
                    student=row['Full Name'],
                    worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                    days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                    highest_ws=row['Highest WS Completed'],
                    date_range=date_range_str
                ), axis=1)
            selected_emails = st.multiselect(
                "Check students to include in the email send list:",
                options=preview_df["Full Name"].tolist(),
                default=preview_df["Full Name"].tolist(),
                key="email_preview_selector"
            )
            preview_df = preview_df[preview_df["Full Name"].isin(selected_emails)]
            cols_to_show = [col for col in ["Parent Name", "Parent Email", "Valid Email", "Email Body"] if col in preview_df.columns]
            st.dataframe(preview_df[cols_to_show])

            send_to_self = st.checkbox("Send preview email to myself only", value=False)
            test_mode = st.checkbox("Test Mode (Print emails to console only, do not send)", value=True)

            if st.button("Send Emails"):
                progress_bar = st.progress(0)
                total = len(preview_df.dropna(subset=["Parent Email"]))
                email_log = []
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Preview to self (always send, then print if test_mode)
                if send_to_self:
                    row = preview_df.iloc[0]
                    body = message_template.format(
                        parent=row.get('Parent Name', 'Parent'),
                        student=row['Full Name'],
                        worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                        days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                        highest_ws=row['Highest WS Completed'],
                        date_range=date_range_str
                    )
                    msg = MIMEMultipart()
                    msg['From'] = sender_email
                    msg['To'] = sender_email
                    msg['Subject'] = subject_line
                    msg.attach(MIMEText(body, 'plain'))
                    try:
                        server = smtplib.SMTP("smtp.gmail.com", 587)
                        server.starttls()
                        server.login(sender_email, sender_pass)
                        server.send_message(msg)
                        server.quit()
                        if test_mode:
                            st.write("📨 Preview email (to self):")
                            st.code(body)
                        else:
                            st.success("✅ Preview email sent to yourself.")
                        email_log.append({
                            'Timestamp': timestamp,
                            'Login ID': row['Login ID'],
                            'Student': row['Full Name'],
                            'Parent Email': sender_email,
                            'Status': 'Preview to Self' + (' (Test Mode)' if test_mode else '')
                        })
                    except Exception as e:
                        st.error(f"❌ Failed to send preview email to yourself: {e}")

                # Now branch: test_mode or real send (excluding first row if send_to_self)
                if test_mode:
                    for i, (_, row) in enumerate(preview_df.iterrows()):
                        print(f"TO: {row['Parent Email']}")
                        body = message_template.format(
                            parent=row.get('Parent Name', 'Parent'),
                            student=row['Full Name'],
                            worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                            days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                            highest_ws=row['Highest WS Completed'],
                            date_range=date_range_str
                        )
                        print(body)
                        st.write(f"📨 Email to: {row['Parent Email']}")
                        st.code(body)
                        email_log.append({
                            'Timestamp': timestamp,
                            'Login ID': row['Login ID'],
                            'Student': row['Full Name'],
                            'Parent Email': row['Parent Email'],
                            'Status': 'Test Mode'
                        })
                        progress_value = min((i + 1) / total, 1.0) if total else 1.0
                        progress_bar.progress(progress_value)
                    if email_log:
                        email_log_df = pd.DataFrame(email_log)
                        st.subheader("📜 Test Mode Email Log")
                        st.dataframe(email_log_df)
                    st.success("✅ Test mode: Emails printed to console.")
                    st.balloons()
                elif not send_to_self:
                    try:
                        server = smtplib.SMTP("smtp.gmail.com", 587)
                        server.starttls()
                        server.login(sender_email, sender_pass)
                        failed_emails = []
                        email_rows = preview_df.copy()
                        if send_to_self:
                            email_rows = email_rows.iloc[1:]
                        for i, (_, row) in enumerate(email_rows.dropna(subset=["Parent Email"]).iterrows()):
                            try:
                                msg = MIMEMultipart()
                                msg['From'] = sender_email
                                msg['To'] = str(row['Parent Email'])
                                msg['Subject'] = subject_line
                                body = message_template.format(
                                    parent=row.get('Parent Name', 'Parent'),
                                    student=row['Full Name'],
                                    worksheets=row.get("Worksheets This Week", row.get("Worksheets This Month", 0)),
                                    days=row.get("Study Days This Week", row.get("Study Days This Month", 0)),
                                    highest_ws=row['Highest WS Completed'],
                                    date_range=date_range_str
                                )
                                msg.attach(MIMEText(body, 'plain'))
                                server.send_message(msg)
                                email_log.append({
                                    'Timestamp': timestamp,
                                    'Login ID': row['Login ID'],
                                    'Student': row['Full Name'],
                                    'Parent Email': row['Parent Email'],
                                    'Status': 'Sent'
                                })
                            except Exception as e:
                                failed_emails.append({
                                    'Login ID': row.get('Login ID', ''),
                                    'Full Name': row.get('Full Name', ''),
                                    'Parent Name': row.get('Parent Name', ''),
                                    'Parent Email': row.get('Parent Email', ''),
                                    'Error': str(e)
                                })
                            progress_value = min((i + 1) / total, 1.0) if total else 1.0
                            progress_bar.progress(progress_value)
                        server.quit()
                        if failed_emails:
                            failed_df = pd.DataFrame(failed_emails)
                            st.subheader("❌ Failed Email Report")
                            st.dataframe(failed_df)
                            st.download_button("Download Failed Emails CSV", data=failed_df.to_csv(index=False), file_name="failed_emails.csv")
                        else:
                            st.success("✅ Emails sent successfully!")
                            st.balloons()
                    except Exception as e:
                        st.error(f"❌ Failed to send emails: {e}")
                if email_log:
                    email_log_df = pd.DataFrame(email_log)
                    st.subheader("📜 Email Log")
                    st.dataframe(email_log_df)
                    st.download_button("Download Email Log", data=email_log_df.to_csv(index=False), file_name="email_log.csv")
