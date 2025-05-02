import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import re

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
    st.markdown(f"**Last Week File:** {last_week_file.name}")
    st.markdown(f"**This Week File:** {this_week_file.name}")

    # Try to extract dates
    date_last = extract_date_from_filename(last_week_file.name)
    date_this = extract_date_from_filename(this_week_file.name)

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
    })

    # Merge on Login ID (inner to find returning students)
    merged = pd.merge(this_trimmed, last_trimmed, on="Login ID", how="inner", suffixes=("_This", "_Last"))

    # Calculate weekly difference
    merged["Worksheets This Week"] = merged["WS_This"] - merged["WS_Last"]
    merged["Study Days This Week"] = merged["Days_This"] - merged["Days_Last"]

    weekly_report = merged[[
        "Login ID",
        "Full Name_This",
        "WS_This",
        "WS_Last",
        "Worksheets This Week",
        "Days_This",
        "Days_Last",
        "Study Days This Week",
        "Highest WS Completed_This"
    ]]
    weekly_report = weekly_report.rename(columns={
        "Full Name_This": "Full Name",
        "WS_This": "Worksheets This Week (Total)",
        "WS_Last": "Worksheets Last Week (Total)",
        "Days_This": "Study Days This Week (Total)",
        "Days_Last": "Study Days Last Week (Total)",
        "Highest WS Completed_This": "Highest Worksheet Completed"
    })

    # Find new students
    new_students = this_trimmed[~this_trimmed["Login ID"].isin(last_trimmed["Login ID"])]

    st.subheader("📈 Returning Students – Weekly Progress")
    st.dataframe(weekly_report)

    st.subheader("🆕 New Students")
    st.dataframe(new_students)

    # Option to download results
    st.download_button("Download Weekly Report CSV", data=weekly_report.to_csv(index=False), file_name="weekly_report.csv")
    st.download_button("Download New Students CSV", data=new_students.to_csv(index=False), file_name="new_students.csv")
