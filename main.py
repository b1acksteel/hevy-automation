import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

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

# MODIFICATION : Poids en KG. 
# Mettre 2.5 pour une augmentation standard (1.25 de chaque côté)
# ou 2.0 si ta salle a des disques ronds.
WEIGHT_INCREMENT_KG = 2.5

def get_weekly_workouts():
    headers = {'api-key': HEVY_API_KEY, 'accept': 'application/json'}
    all_workouts = []
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    print(f"Filtering for workouts after: {cutoff_date.strftime('%Y-%m-%d')}")

    for page_num in range(1, 4):
        try:
            params = {'page': page_num, 'pageSize': 10}
            response = requests.get(f"{HEVY_API_URL}/workouts", headers=headers, params=params)
            
            if response.status_code != 200: break
            data = response.json()
            workouts = data.get('workouts', [])
            if not workouts: break
            
            for w in workouts:
                w_date_str = w.get('start_time', '')
                if w_date_str.endswith('Z'):
                    w_date_str = w_date_str.replace('Z', '+00:00')
                
                try:
                    w_date = datetime.fromisoformat(w_date_str)
                except ValueError:
                    continue 

                if w_date >= cutoff_date:
                    all_workouts.append(w)
                else:
                    return all_workouts
        except Exception as e:
            print(f"Error fetching page {page_num}: {e}")
            break     
    return all_workouts

def group_by_routine(workouts):
    routines = {}
    for w in workouts:
        title = w.get('title', 'Unknown Workout')
        if title not in routines:
            routines[title] = w
    return routines

def calculate_next_target(exercise_name, sets):
    if not sets: return None

    # --- UPDATED LOGIC: FIND HEAVIEST SET (KG) ---
    working_set = max(sets, key=lambda s: s.get('weight_kg') or 0)
    
    reps = working_set.get('reps')
    if reps is None: reps = 0
    
    # On récupère le poids directement en KG
    weight_kg = working_set.get('weight_kg')
    if weight_kg is None: weight_kg = 0
    
    # On garde les décimales (ex: 22.5) mais on évite les trucs genre 22.5000001
    current_weight = round(weight_kg, 2)
    # Petite astuce d'affichage: si c'est 20.0, on affiche 20. Sinon 22.5
    display_weight = int(current_weight) if current_weight.is_integer() else current_weight

    rpe = working_set.get('rpe')
    if rpe is None: rpe = 8.0

    recommendation = {}
    if reps == 0: return None

    # Logic Engine
    if reps >= GOAL_REPS and rpe <= PROGRESSION_RPE_TRIGGER:
        new_weight = current_weight + WEIGHT_INCREMENT_KG
        disp_new = int(new_weight) if new_weight.is_integer() else new_weight
        
        recommendation = {
            "action": "INCREASE WEIGHT",
            "detail": f"Add {WEIGHT_INCREMENT_KG} kg",
            "target_display": f"Target: {disp_new} kg",
            "badge_color": "#d4edda", # Light Green bg
            "text_color": "#155724"   # Dark Green text
        }
    elif reps < GOAL_REPS and rpe < 9:
        recommendation = {
            "action": "ADD REPS",
            "detail": f"Keep {display_weight} kg",
            "target_display": f"Target: {min(reps + 2, GOAL_REPS)} reps",
            "badge_color": "#cce5ff", # Light Blue bg
            "text_color": "#004085"   # Dark Blue text
        }
    elif reps < (GOAL_REPS - 4) and rpe >= 9.5:
        new_weight = round(current_weight * 0.90, 2)
        disp_new = int(new_weight) if new_weight.is_integer() else new_weight
        
        recommendation = {
            "action": "DELOAD",
            "detail": "Performance Dip",
            "target_display": f"Reset to: {disp_new} kg",
            "badge_color": "#f8d7da", # Light Red bg
            "text_color": "#721c24"   # Dark Red text
        }
    else:
        recommendation = {
            "action": "MAINTAIN",
            "detail": f"Keep {display_weight} kg",
            "target_display": "Squeeze 1 more rep",
            "badge_color": "#e2e3e5", # Light Gray bg
            "text_color": "#383d41"   # Dark Gray text
        }

    return {"exercise": exercise_name, "last": f"{reps} @ {display_weight} kg (RPE {rpe})", **recommendation}

def send_email(html_body, text_body, start_date, end_date):
    msg = MIMEMultipart("alternative")
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Weekly Training Plan ({start_date} - {end_date})"

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
        exit()

    print(f"Found {len(latest_routines)} routines from this week.")

    end_date = datetime.now().strftime('%b %d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%b %d')

    # --- HTML HEADER ---
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; padding:0; background-color:#f6f9fc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#f6f9fc; padding: 20px;">
            <tr>
                <td align="center">
                    <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color:#212529; padding: 30px 40px; text-align:center;">
                                <h1 style="margin:0; color:#ffffff; font-size:24px; font-weight:700;">Next Week's Targets</h1>
                                <p style="margin:10px 0 0 0; color:#adb5bd; font-size:14px;">Review of {start_date} - {end_date}</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px;">
    """
    
    text_content = f"WEEKLY TRAINING PLAN ({start_date} - {end_date})\n\n"

    for title, data in latest_routines.items():
        raw_date = data['start_time'].replace('Z', '+00:00')
        display_date = datetime.fromisoformat(raw_date).strftime('%A')

        # ROUTINE HEADER
        html_content += f"""
        <div style="margin-bottom: 30px;">
            <div style="border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 15px;">
                <h2 style="margin:0; color:#333; font-size:18px;">{title}</h2>
                <span style="font-size:12px; color:#888; text-transform:uppercase; letter-spacing:1px; font-weight:bold;">Last Session: {display_date}</span>
            </div>
        """
        text_content += f"=== {title} ({display_date}) ===\n"

        for ex in data.get('exercises', []):
            res = calculate_next_target(ex.get('title'), ex.get('sets', []))
            if res:
                badge_style = f"background-color:{res['badge_color']}; color:{res['text_color']}; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;"
                
                html_content += f"""
                <div style="padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
                    <table width="100%" border="0">
                        <tr>
                            <td width="60%" valign="top">
                                <strong style="color:#222; font-size:15px; display:block; margin-bottom:4px;">{res['exercise']}</strong>
                                <span style="color:#999; font-size:13px;">Top Set: {res['last']}</span>
                            </td>
                            <td width="40%" align="right" valign="top">
                                <span style="{badge_style}">{res['action']}</span>
                                <div style="margin-top:5px; font-size:13px; color:#444; font-weight:600;">{res['target_display']}</div>
                            </td>
                        </tr>
                    </table>
                </div>
                """
                text_content += f"[{res['exercise']}] {res['action']} -> {res['target_display']}\n"
        
        html_content += "</div>"
        text_content += "\n"

    html_content += """
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color:#f8f9fa; padding: 20px; text-align:center; border-top: 1px solid #eee;">
                                <p style="margin:0; color:#999; font-size:12px;">Generated by Hevy Automation Script</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    send_email(html_content, text_content, start_date, end_date)
