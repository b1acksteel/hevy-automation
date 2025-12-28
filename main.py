import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION
# ==========================================
HEVY_API_KEY = os.environ.get("HEVY_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
HEVY_API_URL = 'https://api.hevyapp.com/v1'

# Global Progression Settings
GOAL_REPS = 12
PROGRESSION_RPE_TRIGGER = 9
WEIGHT_INCREMENT_LBS = 5

def get_weekly_workouts():
    """Fetches workouts from the last 7 days only."""
    headers = {'api-key': HEVY_API_KEY, 'accept': 'application/json'}
    all_workouts = []
    
    # Calculate the cutoff date (7 days ago from right now)
    cutoff_date = datetime.now() - timedelta(days=7)
    print(f"Filtering for workouts after: {cutoff_date.strftime('%Y-%m-%d')}")

    # Fetch up to 30 workouts to be safe, then filter by date
    # We fetch a bit more than needed just in case you worked out a lot
    for page_num in range(1, 4):
        try:
            params = {'page': page_num, 'pageSize': 10}
            response = requests.get(f"{HEVY_API_URL}/workouts", headers=headers, params=params)
            
            if response.status_code != 200:
                break
                
            data = response.json()
            workouts = data.get('workouts', [])
            
            if not workouts:
                break
            
            # --- DATE FILTERING LOGIC ---
            for w in workouts:
                # Hevy sends dates like '2023-10-27T12:00:00Z'
                # We strip the 'Z' and convert to a Python date object
                w_date_str = w.get('start_time', '').replace('Z', '')
                try:
                    w_date = datetime.fromisoformat(w_date_str)
                except ValueError:
                    continue # Skip if date is weird

                # If the workout is NEWER than our cutoff, keep it.
                if w_date >= cutoff_date:
                    all_workouts.append(w)
                else:
                    # If we hit an old workout, we can stop fetching entirely 
                    # (since Hevy returns them new -> old)
                    return all_workouts
            
        except Exception as e:
            print(f"Error fetching page {page_num}: {e}")
            break
            
    return all_workouts

def group_by_routine(workouts):
    """Groups workouts by title and keeps only the latest one."""
    routines = {}
    for w in workouts:
        title = w.get('title', 'Unknown Workout')
        # Only keep the most recent occurrence of each routine title
        if title not in routines:
            routines[title] = w
    return routines

def calculate_next_target(exercise_name, sets):
    if not sets: return None

    last_set = sets[-1]
    
    # Sanitize Data
    reps = last_set.get('reps')
    if reps is None: reps = 0
    
    weight_kg = last_set.get('weight_kg')
    if weight_kg is None: weight_kg = 0
    
    weight_lbs = round(weight_kg * 2.20462, 1)

    rpe = last_set.get('rpe')
    if rpe is None: rpe = 8.0

    recommendation = {}
    
    if reps == 0: return None

    # Logic Engine
    if reps >= GOAL_REPS and rpe <= PROGRESSION_RPE_TRIGGER:
        new_weight = weight_lbs + WEIGHT_INCREMENT_LBS
        recommendation = {
            "action": "INCREASE WEIGHT",
            "detail": f"Add {WEIGHT_INCREMENT_LBS} lbs. New Target: {int(new_weight)} lbs.",
            "color": "green"
        }
    elif reps < GOAL_REPS and rpe < 9:
        recommendation = {
            "action": "ADD REPS",
            "detail": f"Keep weight ({int(weight_lbs)} lbs). Push for {min(reps + 2, GOAL_REPS)} reps.",
            "color": "blue"
        }
    elif reps < (GOAL_REPS - 4) and rpe >= 9.5:
        new_weight = weight_lbs * 0.90
        recommendation = {
            "action": "DELOAD",
            "detail": f"Performance dip. Drop to {int(new_weight)} lbs to rebuild volume.",
            "color": "red"
        }
    else:
        recommendation = {
            "action": "MAINTAIN",
            "detail": f"Keep weight ({int(weight_lbs)} lbs). Squeeze out 1 more rep.",
            "color": "black"
        }

    return {"exercise": exercise_name, "last": f"{reps} reps @ {int(weight_lbs)} lbs (RPE {rpe})", **recommendation}

def send_email(html_body, text_body, start_date, end_date):
    msg = MIMEMultipart("alternative")
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📅 Weekly Training Review ({start_date} - {end_date})"

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == "__main__":
    if not HEVY_API_KEY:
        print("Error: HEVY_API_KEY is missing.")
        exit()

    print("Fetching last 7 days of workouts...")
    workouts = get_weekly_workouts()
    latest_routines = group_by_routine(workouts)
    
    if not latest_routines:
        print("No workouts found in the last 7 days.")
        # Optional: You could enable this line if you WANT an email saying "No workouts this week"
        # send_email("<h1>No workouts logged this week.</h1>", "No workouts logged this week.", "", "")
        exit()

    print(f"Found {len(latest_routines)} routines from this week.")

    # Date formatting for the email subject
    end_date = datetime.now().strftime('%b %d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%b %d')

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">📅 Weekly Review ({start_date} - {end_date})</h2>
        <p>Analysis of your workouts from the past week.</p>
    """
    text_content = f"WEEKLY REVIEW ({start_date} - {end_date})\n\n"

    for title, data in latest_routines.items():
