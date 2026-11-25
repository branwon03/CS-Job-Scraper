import pandas as pd
import smtplib
import os
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jobspy import scrape_jobs

# --- 1. CONFIGURATION ---
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
RECEIVER_EMAIL = os.environ.get("EMAIL_USER")

# Comma-separated proxies from GitHub Secrets: "user:pass@host:port,user:pass@host2:port"
RAW_PROXIES = os.environ.get("PROXY_LIST", "")
PROXIES = [p.strip() for p in RAW_PROXIES.split(",") if p.strip()]

JOB_TITLES = [
    "software engineer",
    "data analyst",
    "frontend developer",
    "backend developer",
    "full stack developer",
    "forward deployed engineer",
    "software developer",
    "AI Assisted Engineer"
]

LOCATIONS = [
    "San Francisco Bay Area, CA",
    "San Jose, CA",
    "Oakland, CA",
    "Sunnyvale, CA",
    "Fremont, CA",
    "Palo Alto, CA"
    "Mountainview, CA",
    "Cupertino, CA",
    "Redwood City, CA"
    "San Mateo, CA"
]

SKILLS = [
    "python", "typescript", "javascript", "c++", "java", "html", "css", "r",
    "node.js", "mongo db", "react", "postgresql", "git", "figma", "next.js",
    "docker", "rest api", "aws", "stata", "agile"
]

EXCLUDED_TITLE_WORDS = [
    'senior', 'sr', 'manager', 'lead', 'principal', 'staff',
    'director', 'vp', 'head', 'architect', 'supervisor',
    'ii', 'iii', 'iv', '2', '3', '4', '5', 'mid', 'phd'
]

# Hard disqualifiers anywhere in the job description (add/remove as needed)
EXCLUDED_DESC_PHRASES = [
    'phd required', 'ph.d. required', 'pursuing a phd', 'pursuing a ph.d',
    'phd candidate', 'ph.d. candidate', 'doctoral degree required',
    'active security clearance', 'top secret', 'ts/sci', 'secret clearance',
    'polygraph'
]

TARGET_TITLE_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop', 'part-time', 'part time', 'contract', "early-career", "new-grad", "early career", "new grad"
]

TARGET_DESC_KEYWORDS = [
    'internship', 'co-op', 'coop'
]

# Matches "3+ years of experience", "3-5 years experience", "10+ years of software experience", "minimum of 4 years"
EXPERIENCE_REGEX = re.compile(
    r'(?:\b(?:[3-9]|1[0-5])\s*(?:\+|[-–]\s*\d+|to\s*\d+)?\s*\+?\s*years?\s+(?:of\s+)?(?:[\w\s/-]{0,25})?experience\b)'
    r'|(?:(?:at least|minimum(?: of)?|requires?)\s+(?:[3-9]|1[0-5])\+?\s*years?\b)'
)

def filter_by_skills(description):
    if pd.isna(description):
        return False
    desc_lower = str(description).lower()
    return any(skill in desc_lower for skill in SKILLS)

def is_valid_role(row):
    title = str(row.get('title', '')).lower()
    desc = str(row.get('description', '')).lower()

    # 1. REJECT if title has senior/tier/PhD keywords
    for word in EXCLUDED_TITLE_WORDS:
        if re.search(rf'\b{word}\b', title):
            return False

    # 2. REJECT if description has disqualifying qualifications
    if any(phrase in desc for phrase in EXCLUDED_DESC_PHRASES):
        return False

    # 3. REJECT if description asks for 3+ years of experience
    if EXPERIENCE_REGEX.search(desc):
        return False

    # 4. KEEP only if title or description matches target student/contract keywords
    is_target = (
        any(re.search(rf'\b{kw}\b', title) for kw in TARGET_TITLE_KEYWORDS) or
        any(re.search(rf'\b{kw}\b', desc) for kw in TARGET_DESC_KEYWORDS)
    )
    return is_target

# --- 2. SCRAPING DATA ---
all_jobs = pd.DataFrame()

for location in LOCATIONS:
    for title in JOB_TITLES:
        # 2a. Scrape Indeed without proxies
        print(f"Scraping Indeed: {title} in {location}...")
        try:
            indeed_jobs = scrape_jobs(
                site_name=["indeed"],
                search_term=title,
                location=location,
                results_wanted=35,
                hours_old=72,
                country_indeed='USA'
            )
            all_jobs = pd.concat([all_jobs, indeed_jobs], ignore_index=True)
        except Exception as e:
            print(f"Indeed failed for {title} in {location}: {e}")

        # 2b. Scrape LinkedIn ONLY if proxies are configured
        if PROXIES:
            print(f"Scraping LinkedIn (via proxy): {title} in {location}...")
            try:
                linkedin_jobs = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=title,
                    location=location,
                    results_wanted=15,
                    hours_old=72,
                    linkedin_fetch_description=True,
                    proxies=PROXIES
                )
                all_jobs = pd.concat([all_jobs, linkedin_jobs], ignore_index=True)
            except Exception as e:
                print(f"LinkedIn failed for {title} in {location}: {e}")

        time.sleep(5)

if all_jobs.empty:
    print("No new jobs found in the specified timeframe.")
    exit()

# --- 3. FILTERING & CLEANING ---
# Normalize job IDs (fallback to job_url if id is missing)
if 'id' not in all_jobs.columns:
    all_jobs['id'] = all_jobs['job_url']
all_jobs['id'] = all_jobs['id'].fillna(all_jobs['job_url']).astype(str)

all_jobs = all_jobs.drop_duplicates(subset=['id'])
all_jobs = all_jobs.drop_duplicates(subset=['title', 'company', 'location'])

# Apply skills filter
all_jobs['matches_skills'] = all_jobs['description'].apply(filter_by_skills)
filtered_jobs = all_jobs[all_jobs['matches_skills'] == True].copy()

if filtered_jobs.empty:
    print("No jobs matched your specific skills.")
    exit()

# Apply strict role & qualification filter
filtered_jobs['is_valid_role'] = filtered_jobs.apply(is_valid_role, axis=1)
final_jobs = filtered_jobs[filtered_jobs['is_valid_role'] == True].copy()

if final_jobs.empty:
    print("No jobs matched your specific skills and role types.")
    exit()

# --- DEDUPLICATION BY JOB ID ---
SEEN_FILE = "seen_jobs.txt"
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r") as f:
        seen_ids = set(f.read().splitlines())
else:
    seen_ids = set()

final_jobs = final_jobs[~final_jobs['id'].isin(seen_ids)]

if final_jobs.empty:
    print("Found matching jobs, but they have all been previously sent. Exiting.")
    exit()

# Keep only display columns for the email
final_list = final_jobs[['title', 'company', 'location', 'job_url']].copy()

# --- 4. FORMATTING & SENDING EMAIL ---
html_table = final_list.to_html(index=False, render_links=True, escape=False)
html_content = f"""
<html>
  <body>
    <h2>New Job Matches ({len(final_list)} found)</h2>
    <p>Here are the jobs posted matching your skills and intern/co-op/contract criteria:</p>
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

    # Save job IDs to memory
    with open(SEEN_FILE, "a") as f:
        for job_id in final_jobs['id']:
            f.write(f"{job_id}\n")
    print("Updated seen_jobs.txt with new job IDs")

except Exception as e:
    print(f"Failed to send email: {e}")