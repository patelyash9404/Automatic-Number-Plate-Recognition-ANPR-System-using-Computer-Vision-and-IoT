import cv2
import pytesseract
import sqlite3
import numpy as np
import paho.mqtt.client as mqtt
import smtplib
import re

# MQTT Configuration
MQTT_BROKER = "192.168.177.158"  # Running on the RPi
MQTT_PORT = 1883
MQTT_TOPIC = "number_plate"

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = "roshnijariwala02@gmail.com"  # Replace with your email
EMAIL_PASSWORD = "*******"  # Replace with your email password
EMAIL_RECEIVER = "yashpatel940516@gmail.com"

# Initialize MQTT client
mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print(f"Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
except Exception as e:
    print(f"Failed to connect to MQTT broker: {e}")
    exit(1)

# Database setup
DB_NAME = "number_plates.db"

def create_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS plates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plate_number TEXT UNIQUE,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def insert_plate(plate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO plates (plate_number) VALUES (?)", (plate,))
        conn.commit()
        print(f"✅ Saved to database: {plate}")
    except sqlite3.IntegrityError:
        print(f"⚠ Plate {plate} already exists in the database.")
    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        conn.close()

def send_email(new_plate):
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        subject = "New Number Plate Detected"
        body = f"A new number plate {new_plate} was detected and added to the sample list."
        message = f"Subject: {subject}\n\n{body}"
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, message)
        server.quit()
        print(f"📧 Email sent to {EMAIL_RECEIVER} about plate: {new_plate}")
    except Exception as e:
        print(f"❌ Email Error: {e}")

# Create database table if not exists
create_database()

# Define 10 sample number plates (Valid Plates for Storage)
sample_plates = {"WB 74 AH 6561", "XYZ987", "LMN456", "PQR789", "JKL321",
                 "KA 19 EQ 0001","GJ03ER0563", "GHI852", "TUV159", "MNO753", "QWE963", "TR 03 MF 4477"}

# Plate format validation
def is_valid_plate_format(plate):
    return bool(re.match(r'^[A-Z]{2} \d{2} [A-Z]{2} \d{4}$', plate))

# Open USB camera
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to capture frame from camera")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
    edges = cv2.Canny(gray, 75, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4:  # Looking for quadrilateral shapes
            x, y, w, h = cv2.boundingRect(approx)
            if 60 < w < 200 and 15 < h < 80:  # Adjusted filter for proper size
                plate_roi = gray[y:y+h, x:x+w]  # Extract plate region
                text = pytesseract.image_to_string(plate_roi, config='--psm 7').strip()

                # ✅ Show ALL detected plates (Including Noise)
                print(f"🔍 Detected Plate: {text}")

                mqtt_client.publish(MQTT_TOPIC, text)  # Publish all detected plates

                # ✅ Store ONLY valid plates in the database
                if text in sample_plates:
                    print("🎯 MATCH FOUND!")
                    insert_plate(text)  # Save to database before exiting
                    cap.release()
                    mqtt_client.disconnect()
                    exit(0)  # ✅ STOP the script as soon as a match is found
                
                # ✅ If the plate format matches but is not in the sample list
                elif is_valid_plate_format(text):
                    print("🆕 New valid plate format detected!")
                    sample_plates.add(text)
                    insert_plate(text)
                    send_email(text)  # Send an email notification

cap.release()

mqtt_client.disconnect()
