import pandas as pd
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jobspy import scrape_jobs

# --- 1. CONFIGURATION ---
SENDER_EMAIL = os.environ.get("EMAIL_USER") 
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
RECEIVER_EMAIL = os.environ.get("EMAIL_USER")

JOB_TITLES = [
    "software engineer", "data analyst", "software developer", "AI engineer", 
    "Data engineer", "ML engineer", "forward deployment engineer", 
    "frontend engineer", "backend engineer", "fullstack engineer", "web developer"
]

LOCATIONS = [
    "San Francisco Bay Area, CA", 
    "San Jose, CA",               
    "Oakland, CA"                 
]

SKILLS = [
    "python", "typescript", "javascript", "c++", "java", "html", "css", "r", 
    "node.js", "mongo db", "react", "postgresql", "git", "figma", "next.js", 
    "docker", "rest api", "aws", "stata", "agile"
]

EXCLUDED_TITLE_WORDS = [
    'senior', 'sr', 'manager', 'lead', 'principal', 'staff', 
    'director', 'vp', 'head', 'architect', 'supervisor'
]

TARGET_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop', 'part-time', 'part time', 
    'contract', 'entry level', 'entry-level', 'junior', 'jr', 
    'new grad', 'recent grad', 'graduate', 'student'
]

def filter_by_skills(description):
    if pd.isna(description):
        return False
    desc_lower = str(description).lower()
    return any(skill in desc_lower for skill in SKILLS)

def is_valid_role(row):
    title = str(row.get('title', '')).lower()
    desc = str(row.get('description', '')).lower()
    job_type = str(row.get('job_type', '')).lower()

    # 1. REJECT instantly if the title has senior/manager keywords
    for word in EXCLUDED_TITLE_WORDS:
        if re.search(rf'\b{word}\b', title):
            return False

    # 2. KEEP only if it explicitly matches our student/entry-level requirements
    is_target = (
        any(kw in job_type for kw in TARGET_KEYWORDS) or
        any(re.search(rf'\b{kw}\b', title) for kw in TARGET_KEYWORDS) or
        any(re.search(rf'\b{kw}\b', desc) for kw in TARGET_KEYWORDS)
    )
    return is_target

# --- 2. SCRAPING DATA ---
all_jobs = pd.DataFrame()

for location in LOCATIONS:
    for title in JOB_TITLES:
        print(f"Scraping {title} in {location}...")
        try:
            jobs = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=title,
                location=location,
                results_wanted=20,
                hours_old=24# Set to 30 days for this final test
                country_indeed='USA'
            )
            all_jobs = pd.concat([all_jobs, jobs])
        except Exception as e:
            print(f"Failed to scrape {title} in {location}: {e}")

if all_jobs.empty:
    print("No new jobs found in the specified timeframe.")
    exit()

# --- 3. FILTERING & CLEANING ---
all_jobs = all_jobs.drop_duplicates(subset=['title', 'company', 'location'])

# Apply the skills filter first
all_jobs['matches_skills'] = all_jobs['description'].apply(filter_by_skills)
filtered_jobs = all_jobs[all_jobs['matches_skills'] == True].copy()

if filtered_jobs.empty:
    print("No jobs matched your specific skills.")
    exit()

# Apply the strict role-type filter
filtered_jobs['is_valid_role'] = filtered_jobs.apply(is_valid_role, axis=1)
final_jobs = filtered_jobs[filtered_jobs['is_valid_role'] == True].copy()

if final_jobs.empty:
    print("No jobs matched your specific skills and role types.")
    exit()

# Extract only the final, fully-filtered list for the email
final_list = final_jobs[['title', 'company', 'location', 'job_url']]

# --- 4. FORMATTING & SENDING EMAIL ---
html_table = final_list.to_html(index=False, render_links=True, escape=False)
html_content = f"""
<html>
  <body>
    <h2>New Job Matches ({len(final_list)} found)</h2>
    <p>Here are the jobs posted matching your skills and entry-level/intern criteria:</p>
    {html_table}
  </body>
</html>
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = f"Job Alert: {len(final_list)} New Roles Found"
msg["From"] = SENDER_EMAIL
msg["To"] = RECEIVER_EMAIL
msg.attach(MIMEText(html_content, "html"))

try:
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")