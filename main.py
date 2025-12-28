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
    
    # --- SANITIZE DATA (Fix for NoneType Error) ---
    reps = last_set.get('reps')
    if reps is None: reps = 0
    
    weight_kg = last_set.get('weight_kg')
    if weight_kg is None: weight_kg = 0
    
    # Convert KG to LBS
    weight_lbs = round(weight_kg * 2.20462, 1)

    rpe = last_set.get('rpe')
    if rpe is None: rpe = 8.0

    recommendation = {}
    
    # LOGIC ENGINE (Universal Rule)
    
    # 0. SKIP: If reps are 0 (e.g. Cardio/Plank), skip it
    if reps == 0:
        return None

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

    print("Fetching workout history...")
    workouts = get_recent_workouts()
    latest_routines = group_by_routine(workouts)
    
    if not latest_routines:
        print("No workouts found.")
        exit()

    print(f"Found {len(latest_routines)} active routines: {list(latest_routines.keys())}")

    html_content = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">📋 Your Workout Menu</h2>
        <p>Targets calculated for your next session of each routine.</p>
    """
    text_content = "YOUR WORKOUT MENU\nTargets calculated for next session:\n\n"

    for title, data in latest_routines.items():
        
        # Routine Header
        html_content += f"""
        <div style="background-color: #f4f4f4; padding: 10px; margin-top: 20px; border-radius: 5px;">
            <h3 style="margin: 0; color: #222;">{title}</h3>
            <span style="font-size: 12px; color: #666;">Last: {datetime.fromisoformat(data['start_time'].replace('Z', '+00:00')).strftime('%b %d')}</span>
        </div>
        <ul style="list-style-type: none; padding: 0;">
        """
        text_content += f"=== {title} ===\n"

        for ex in data.get('exercises', []):
            res = calculate_next_target(ex.get('title'), ex.get('sets', []))
            if res:
                html_content += f"""
                <li style="padding: 10px 0; border-bottom: 1px solid #eee;">
                    <strong>{res['exercise']}</strong><br>
                    <span style="color:#666; font-size:13px;">Last: {res['last']}</span><br>
                    <strong style="color:{res['color']}; font-size:14px;">👉 {res['action']}</strong>: {res['detail']}
                </li>
                """
                text_content += f"[{res['exercise']}] {res['action']}: {res['detail']}\n"
        
        html_content += "</ul>"
        text_content += "\n"

    html_content += "</div>"

    send_email(html_content, text_content)
