import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

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

def get_recent_workouts():
    """Fetches the last 30 workouts safely (3 pages of 10)."""
    headers = {'api-key': HEVY_API_KEY, 'accept': 'application/json'}
    all_workouts = []
    
    for page_num in range(1, 4):
        try:
            params = {'page': page_num, 'pageSize': 10}
            response = requests.get(f"{HEVY_API_URL}/workouts", headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"Page {page_num} finished or failed.")
                break
                
            data = response.json()
            workouts = data.get('workouts', [])
            
            if not workouts:
                break
                
            all_workouts.extend(workouts)
            
        except Exception as e:
            print(f"Error fetching page {page_num}: {e}")
            break
            
    return all_workouts

def group_by_routine(workouts):
    """Groups workouts by title and keeps only the latest one."""
    routines = {}
    for w in workouts:
        title = w.get('title', 'Unknown Workout')
        if title not in routines:
            routines[title] = w
    return routines

def calculate_next_target(exercise_name, sets):
    if not sets: return None

    last_set = sets[-1]
    reps = last_set.get('reps', 0)
    weight_kg = last_set.get('weight_kg', 0)
    if weight_kg is None: weight_kg = 0
    
    # Convert KG to LBS
    weight_lbs = round(weight_kg * 2.20462, 1)

    rpe = last_set.get('rpe')
    if rpe is None: rpe = 8.0

    recommendation = {}
    
    # LOGIC ENGINE (Universal Rule)
    
    # 1. PASSED: Hit 12 reps @ RPE 9 -> Add 5 lbs
    if reps >= GOAL_REPS and rpe <= PROGRESSION_RPE_TRIGGER:
        new_weight = weight_lbs + WEIGHT_INCREMENT_LBS
        recommendation = {
            "action": "INCREASE WEIGHT",
            "detail": f"Add {WEIGHT_INCREMENT_LBS} lbs. New Target: {int(new_weight)} lbs.",
            "color": "green"
        }
    
    # 2. BUILDING: Under 12 reps, not exhausted -> Add Reps
    elif reps < GOAL_REPS and rpe < 9:
        recommendation = {
            "action": "ADD REPS",
            "detail": f"Keep weight ({int(weight_lbs)} lbs). Push for {min(reps + 2, GOAL_REPS)} reps.",
            "color": "blue"
        }
    
    # 3. STRUGGLING: Low reps + High RPE -> Deload
    elif reps < (GOAL_REPS - 4) and rpe >= 9.5:
        new_weight = weight_lbs * 0.90
        recommendation = {
            "action": "DELOAD",
            "detail": f"Performance dip. Drop to {int(new_weight)} lbs to rebuild volume.",
            "color": "red"
        }
    
    # 4. GRINDING: Close to limit -> Maintain
    else:
        recommendation = {
            "action": "MAINTAIN",
            "detail": f"Keep weight ({int(weight_lbs)} lbs). Squeeze out 1 more rep.",
            "color": "black"
        }

    return {"exercise": exercise_name, "last": f"{reps} reps @ {int(weight_lbs)} lbs (RPE {rpe})", **recommendation}

def send_email(html_body, text_body):
    msg = MIMEMultipart("alternative")
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = "🏋️ Next Workout Menu (All Routines)"

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
