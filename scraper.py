import pandas as pd
import smtplib
import os
import re  # Must be added here
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jobspy import scrape_jobs

# --- 1. CONFIGURATION ---
SENDER_EMAIL = os.environ.get("EMAIL_USER") 
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
RECEIVER_EMAIL = os.environ.get("EMAIL_USER") # Sending to yourself

JOB_TITLES = [
    "software engineer", "data analyst", "software developer", "AI engineer", 
    "Data engineer", "ML engineer", "forward deployment engineer", 
    "frontend engineer", "backend engineer", "fullstack engineer", "web developer"
]

# Grouping locations to avoid excessive API calls (which lead to bans)
LOCATIONS = [
    "San Francisco Bay Area, CA", # Covers SF, San Mateo, Redwood City
    "San Jose, CA",               # Covers SJ, Santa Clara, Milpitas, Sunnyvale, Cupertino, Mountain View
    "Oakland, CA"                 # Covers Oakland, Berkeley, Hayward, Fremont
]

# Convert user skills to lowercase for exact substring matching
SKILLS = [
    "python", "typescript", "javascript", "c++", "java", "html", "css", "r", 
    "node.js", "mongo db", "react", "postgresql", "git", "figma", "next.js", 
    "docker", "rest api", "aws", "stata", "agile"
]

def filter_by_skills(description):
    """Returns True if the description contains at least one target skill."""
    if pd.isna(description):
        return False
    desc_lower = str(description).lower()
    return any(skill in desc_lower for skill in SKILLS)

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
                hours_old=72, # Crucial: Only gets jobs from the last 6 hours to prevent duplicate emails
                country_indeed='USA'
            )
            all_jobs = pd.concat([all_jobs, jobs])
        except Exception as e:
            print(f"Failed to scrape {title} in {location}: {e}")

if all_jobs.empty:
    print("No new jobs found in the last 6 hours.")
    exit()

# --- 3. FILTERING & CLEANING ---
# Drop duplicates just in case different job boards have the same listing
all_jobs = all_jobs.drop_duplicates(subset=['title', 'company', 'location'])

EXCLUDED_TITLE_WORDS = ['senior', 'sr', 'manager', 'lead', 'principal', 'staff', 'director', 'vp', 'head']
TARGET_ROLE_TYPES = ['intern', 'internship', 'co-op', 'coop', 'part-time', 'part time', 'contract']

def is_valid_role(row):
    title = str(row.get('title', '')).lower()
    desc = str(row.get('description', '')).lower()
    job_type = str(row.get('job_type', '')).lower()

    # 1. REJECT if the title contains senior/manager keywords
    for word in EXCLUDED_TITLE_WORDS:
        # \b ensures we match exact words (e.g. 'staff' doesn't accidentally match 'staffing')
        if re.search(rf'\b{word}\b', title):
            return False

    # 2. KEEP only if it explicitly matches our target student/contract role types
    is_target = (
        any(kw in job_type for kw in TARGET_ROLE_TYPES) or
        any(re.search(rf'\b{kw}\b', title) for kw in TARGET_ROLE_TYPES) or
        any(re.search(rf'\b{kw}\b', desc) for kw in TARGET_ROLE_TYPES)
    )
    
    return is_target

# Apply the skills filter first (using your existing function)
all_jobs['matches_skills'] = all_jobs['description'].apply(filter_by_skills)
filtered_jobs = all_jobs[all_jobs['matches_skills'] == True]

# Apply the new role-type filter
filtered_jobs['is_valid_role'] = filtered_jobs.apply(is_valid_role, axis=1)
final_jobs = filtered_jobs[filtered_jobs['is_valid_role'] == True]

if final_jobs.empty:
    print("No jobs matched your specific skills and role types.")
    exit()

# Select only the columns we want to see in the email
final_list = final_jobs[['title', 'company', 'location', 'job_url']]

# --- 4. FORMATTING & SENDING EMAIL ---
# Select only the columns we want to see in the email
final_list = filtered_jobs[['title', 'company', 'location', 'job_url']]

html_table = final_list.to_html(index=False, render_links=True, escape=False)
html_content = f"""
<html>
  <body>
    <h2>New Job Matches ({len(final_list)} found)</h2>
    <p>Here are the jobs posted in the last 5 hours matching your skills and locations:</p>
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
    # Set up the SMTP server (using Gmail as the standard default)
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")