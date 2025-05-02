import streamlit as st
import pandas as pd

st.title("📊 Weekly Study Activity Tracker")
st.write("Upload last week's and this week's CSV files to compare study progress.")

# File uploaders
last_week_file = st.file_uploader("Upload LAST week's CSV", type="csv", key="last")
this_week_file = st.file_uploader("Upload THIS week's CSV", type="csv", key="this")

if last_week_file and this_week_file:
    last_df = pd.read_csv(last_week_file)
    this_df = pd.read_csv(this_week_file)

    # Ensure Login ID is treated as string
    last_df["Login ID"] = last_df["Login ID"].astype(str)
    this_df["Login ID"] = this_df["Login ID"].astype(str)

    # Select relevant columns only
    last_trimmed = last_df[["Login ID", "Full Name", "# of WS", "# of Study Days"]].copy()
    this_trimmed = this_df[["Login ID", "Full Name", "# of WS", "# of Study Days"]].copy()

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

    weekly_report = merged[["Login ID", "Full Name_This", "Worksheets This Week", "Study Days This Week"]]
    weekly_report = weekly_report.rename(columns={"Full Name_This": "Full Name"})

    # Find new students
    new_students = this_trimmed[~this_trimmed["Login ID"].isin(last_trimmed["Login ID"])]

    st.subheader("📈 Returning Students – Weekly Progress")
    st.dataframe(weekly_report)

    st.subheader("🆕 New Students")
    st.dataframe(new_students)

    # Option to download results
    st.download_button("Download Weekly Report CSV", data=weekly_report.to_csv(index=False), file_name="weekly_report.csv")
    st.download_button("Download New Students CSV", data=new_students.to_csv(index=False), file_name="new_students.csv")
