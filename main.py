import os
import smtplib
import requests
import json
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

GOAL_REPS = 12
PROGRESSION_RPE_TRIGGER = 9
WEIGHT_INCREMENT_KG = 2.5
WEIGHT_INCREMENT_LBS = 5

def get_latest_workout():
    headers = {'api-key': HEVY_API_KEY, 'accept': 'application/json'}
    try:
        # Fetch the last 3 workouts just in case the most recent one is empty
        response = requests.get(f"{HEVY_API_URL}/workouts", headers=headers, params={'page': 1, 'pageSize': 3})
        response.raise_for_status()
        workouts = response.json().get('workouts', [])
        
        # Return the first workout that actually has exercises
        for w in workouts:
            if w.get('exercises'):
                return w
        return None
    except Exception as e:
        print(f"Error fetching Hevy data: {e}")
        return None

def calculate_next_target(exercise_name, sets):
    if not sets:
        return None

    # SIMPLIFIED LOGIC: Just take the very last set, ignoring "set_type"
    last_set = sets[-1]
    
    reps = last_set.get('reps', 0)
    weight = last_set.get('weight_kg', 0)
    
    # Handle Bodyweight exercises (weight might be None)
    if weight is None: weight = 0
        
    # Handle Missing RPE (Default to 8.0)
    rpe = last_set.get('rpe')
    if rpe is None: rpe = 8.0

    recommendation = {}
    
    # LOGIC ENGINE
    if reps >= GOAL_REPS and rpe <= PROGRESSION_RPE_TRIGGER:
        recommendation = {
            "action": "INCREASE WEIGHT",
            "detail": f"Add {WEIGHT_INCREMENT_KG}kg / {WEIGHT_INCREMENT_LBS}lbs. Target 8-10 reps.",
            "color": "green"
        }
    elif reps < GOAL_REPS and rpe < 9:
        recommendation = {
            "action": "ADD REPS",
            "detail": f"Keep weight ({weight}kg). Push for {min(reps + 2, 12)} reps.",
            "color": "blue"
        }
    elif reps < (GOAL_REPS - 4) and rpe >= 9.5:
        new_weight = weight * 0.90
        recommendation = {
            "action": "DELOAD / RESET",
            "detail": f"Performance dip. Drop to {round(new_weight, 1)}kg to hit 12 reps.",
            "color": "red"
        }
    else:
        recommendation = {
            "action": "MAINTAIN",
            "detail": f"Keep weight ({weight}kg). Squeeze out 1 more rep.",
            "color": "black"
        }

    return {"exercise": exercise_name, "last": f"{reps} reps @ {weight}kg (RPE {rpe})", **recommendation}

def send_email(html_content, text_content, workout_title):
    msg = MIMEMultipart("alternative") # Important for compatibility
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"💪 Next Workout Targets: {workout_title}"

    # Attach both Plain Text and HTML versions
    part1 = MIMEText(text_content, 'plain')
    part2 = MIMEText(html_content, 'html')
    msg.attach(part1)
    msg.attach(part2)

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
    print("Starting process...")
    
    if not HEVY_API_KEY:
        print("Error: HEVY_API_KEY is missing.")
        exit()

    workout = get_latest_workout()
    
    if workout:
        print(f"Analyzing workout: {workout.get('title')}")
        
        # Build Content
        html_list_items = ""
        text_list_items = ""
        
        count = 0
        for ex in workout.get('exercises', []):
            res = calculate_next_target(ex.get('title'), ex.get('sets', []))
            if res:
                count += 1
                # HTML Format
                html_list_items += f"""
                <li style="margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
                    <strong style="font-size: 16px;">{res['exercise']}</strong><br>
                    <span style="color:#666; font-size:14px;">Last: {res['last']}</span><br>
                    <strong style="color:{res['color']}; font-size:14px;">👉 {res['action']}</strong>: {res['detail']}
                </li>
                """
                # Text Format
                text_list_items += f"[{res['exercise']}]\nLast: {res['last']}\nACTION: {res['action']} - {res['detail']}\n\n"

        if count == 0:
            html_content = "<h1>No valid exercises found in the last workout.</h1>"
            text_content = "No valid exercises found in the last workout."
        else:
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">🚀 Progressive Overload Targets</h2>
                <p>Based on: <strong>{workout.get('title')}</strong></p>
                <hr>
                <ul style="list-style-type: none; padding: 0;">
                    {html_list_items}
                </ul>
                <p style="font-size: 12px; color: #999; margin-top: 30px;">Generated automatically via Hevy API</p>
            </div>
            """
            text_content = f"PROGRESSIVE OVERLOAD PLAN\nBased on: {workout.get('title')}\n\n{text_list_items}"

        # DEBUG: Print to GitHub Logs so we can see it!
        print("--- GENERATED EMAIL CONTENT (PREVIEW) ---")
        print(text_content)
        print("-----------------------------------------")

        send_email(html_content, text_content, workout.get('title'))
    else:
        print("No workout found.")
