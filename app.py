import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Use Eastern Time
eastern = pytz.timezone("America/New_York")
today = datetime.now(eastern)

st.title("📊 Weekly Study Activity Tracker")

# Display today's date
st.markdown(f"**Report generated on:** {today.strftime('%B %d, %Y')} (Eastern Time)")

st.write("Upload last week's and this week's CSV files to compare study progress.")

# File uploaders
last_week_file = st.file_uploader("Upload LAST week's CSV", type="csv", key="last")
this_week_file = st.file_uploader("Upload THIS week's CSV", type="csv", key="this")

def extract_date_from_filename(filename):
    match = re.search(r'(\d{8})', filename)
    if match:
        return datetime.strptime(match.group(1), "%m%d%Y")
    return None

if last_week_file and this_week_file:
    # Display file names
    # st.markdown(f"**Last Week File:** {last_week_file.name}")
    # st.markdown(f"**This Week File:** {this_week_file.name}")

    # Try to extract dates
    date_last = extract_date_from_filename(last_week_file.name)
    date_this = extract_date_from_filename(this_week_file.name)

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

    # Instructional note for Gmail SMTP
    st.markdown("""To use Gmail SMTP, you'll need to [create an App Password](https://support.google.com/accounts/answer/185833). Use that instead of your normal Gmail password.""")

    # Email login fields
    sender_email = st.text_input("Sender Gmail address")
    sender_pass = st.text_input("App Password", type="password")
    subject_line = st.text_input(
        "Email Subject",
        value=f"Your Child's Weekly {subject_type} Progress" if subject_type else "Your Child's Weekly Study Progress"
    )

    # Message template
    message_template = st.text_area(
        "Email Message Template (use {parent}, {student}, {worksheets}, {days}, {highest_ws})",
        value=(
            "Dear {parent},\n\n"
            "Here is the weekly study update for {student}:\n"
            "- Worksheets completed this week: {worksheets}\n"
            "- Study days this week: {days}\n"
            "- Highest worksheet completed: {highest_ws}\n\n"
            "Keep up the great work!\n"
        ),
        height=180
    )

    # Parent email mapping upload
    st.markdown("Upload a CSV mapping student names to parent names and parent emails. Columns required: Full Name, Parent Name, Parent Email")
    parent_map_file = st.file_uploader("Parent Email Mapping CSV", type="csv", key="parent_map")

    if parent_map_file:
        parent_map = pd.read_csv(parent_map_file)
        parent_map.columns = parent_map.columns.str.strip()
        # Ensure Login ID columns are string before merging
        weekly_report["Login ID"] = weekly_report["Login ID"].astype(str)
        parent_map["Login ID"] = parent_map["Login ID"].astype(str)
        new_students["Login ID"] = new_students["Login ID"].astype(str)
        # Merge parent info into weekly_report on Login ID
        full_report = pd.merge(weekly_report, parent_map, on="Login ID", how="left", suffixes=("", "_parent"))
        full_report["Full Name"] = weekly_report["Full Name"]
        if "Login ID" not in full_report.columns:
            full_report = pd.merge(full_report, this_trimmed[["Login ID", "Full Name"]], on="Full Name", how="left")
        unmatched_parents = full_report[full_report["Parent Email"].isnull()][["Login ID", "Full Name"]].copy()
        unmatched_parents["Reason"] = "No matching parent email"
        # Merge parent info into new_students on Login ID
        new_students_merged = pd.merge(new_students, parent_map, on="Login ID", how="left", suffixes=("", "_parent"))
        new_students_merged["Full Name"] = new_students_merged["Full Name"].combine_first(new_students["Full Name"])
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

        # Checkbox for test mode
        test_mode = st.checkbox("Test Mode (Print emails to console only, do not send)", value=True)

        # Send emails button and logic
        if st.button("Send Emails"):
            if test_mode:
                for _, row in full_report.iterrows():
                    print(f"TO: {row['Parent Email']}")
                    print(message_template.format(
                        parent=row['Parent Name'],
                        student=row['Full Name'],
                        worksheets=row['Worksheets This Week'],
                        days=row['Study Days This Week'],
                        highest_ws=row['Highest WS Completed']
                    ))
                st.success("✅ Test mode: Emails printed to console.")
            else:
                try:
                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(sender_email, sender_pass)

                    failed_emails = []

                    for _, row in full_report.dropna(subset=["Parent Email"]).iterrows():
                        try:
                            msg = MIMEMultipart()
                            msg['From'] = sender_email
                            msg['To'] = str(row['Parent Email'])
                            msg['Subject'] = subject_line

                            body = message_template.format(
                                parent=str(row['Parent Name']),
                                student=str(row['Full Name']),
                                worksheets=str(row['Worksheets This Week']),
                                days=str(row['Study Days This Week']),
                                highest_ws=str(row['Highest WS Completed'])
                            )

                            msg.attach(MIMEText(body, 'plain'))
                            server.send_message(msg)
                        except Exception as e:
                            failed_emails.append({
                                'Login ID': row.get('Login ID', ''),
                                'Full Name': row.get('Full Name', ''),
                                'Parent Name': row.get('Parent Name', ''),
                                'Parent Email': row.get('Parent Email', ''),
                                'Error': str(e)
                            })

                    server.quit()

                    if failed_emails:
                        failed_df = pd.DataFrame(failed_emails)
                        st.subheader("❌ Failed Email Report")
                        st.dataframe(failed_df)
                        st.download_button("Download Failed Emails CSV", data=failed_df.to_csv(index=False), file_name="failed_emails.csv")
                    else:
                        st.success("✅ Emails sent successfully!")
                except Exception as e:
                    st.error(f"❌ Failed to send emails: {e}")
