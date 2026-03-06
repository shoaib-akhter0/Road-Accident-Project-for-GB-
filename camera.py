import cv2
from detection import AccidentDetectionModel
import numpy as np
import os
import winsound
import threading
import time
import tkinter as tk
from twilio.rest import Client
from PIL import Image, ImageTk  # Import PIL modules for image handling

emergency_timer = None
alarm_triggered = False  # Flag to track if an alarm has been triggered

model = AccidentDetectionModel("model.json", "model_weights.keras")
font = cv2.FONT_HERSHEY_SIMPLEX

def save_accident_photo(frame):
    try:
        current_date_time = time.strftime("%Y-%m-%d-%H%M%S")
        directory = "accident_photos"
        if not os.path.exists(directory):
            os.makedirs(directory)
        filename = f"{directory}/{current_date_time}.jpg"
        cv2.imwrite(filename, frame)
        print(f"Accident photo saved as {filename}")
    except Exception as e:
        print(f"Error saving accident photo: {e}")

def send_whatsapp_alert():
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        client = Client(account_sid, auth_token)

        message = client.messages.create(
            body="🚨 Accident detected! Please send an ambulance immediately.",
            from_="whatsapp:+14155238886",   # Twilio Sandbox WhatsApp number
            to="whatsapp:+923554381250"      # Replace with your verified WhatsApp number
        )

        print(f"WhatsApp alert sent! SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")

def show_alert_message():
    def on_send_whatsapp():
        send_whatsapp_alert()
        alert_window.destroy()

    # Play the beep sound
    frequency = 2500  
    duration = 2000  
    winsound.Beep(frequency, duration)

    alert_window = tk.Tk()
    alert_window.title("Alert")
    alert_window.geometry("500x250")  
    alert_label = tk.Label(alert_window, text="Alert: Accident Detected!\n\nIs the Accident Critical?", fg="black", font=("Helvetica", 16))
    alert_label.pack()

    # Load and display the GIF (optional)
    gif_path = ""  # Replace with actual path if you have a GIF
    if gif_path:
        try:
            gif = Image.open(gif_path)
            resized_gif = gif.resize((150, 100), Image.Resampling.BICUBIC)
            global gif_image
            gif_image = ImageTk.PhotoImage(resized_gif)
            gif_label = tk.Label(alert_window, image=gif_image)
            gif_label.pack()
        except Exception as e:
            print(f"Error loading GIF: {e}")

    # Updated button for WhatsApp
    whatsapp_button = tk.Button(alert_window, text="Send WhatsApp Alert", command=on_send_whatsapp)
    whatsapp_button.pack()

    cancel_button = tk.Button(alert_window, text="Cancel", command=alert_window.destroy)
    cancel_button.pack()

    alert_window.mainloop()
    
def start_alert_thread():
    alert_thread = threading.Thread(target=show_alert_message)
    alert_thread.daemon = True  
    alert_thread.start()

def startapplication():
    global alarm_triggered  
    video = cv2.VideoCapture("C:/Users/ge/Desktop/Road-Accident-Detection-Alert-System-main/SRN-4000_DHQ CHWK PTZ(10.4.225.200.554)_20240820_091907_092035_ID_0000.avi") 
    while True:
        ret, frame = video.read()
        if not ret:
            print("No more frames to read")
            break
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        roi = cv2.resize(gray_frame, (250, 250))

        pred, prob = model.predict_accident(roi[np.newaxis, :, :])
        if pred == "Accident" and not alarm_triggered:
            prob = round(prob[0][0] * 100, 2)
            
            if prob > 80:
                frequency = 2500  
                duration = 2000  
                winsound.Beep(frequency, duration)
                save_accident_photo(frame)
                alarm_triggered = True  
                start_alert_thread()  

            cv2.rectangle(frame, (0, 0), (280, 40), (0, 0, 0), -1)
            cv2.putText(frame, pred + " " + str(prob), (20, 30), font, 1, (255, 255, 0), 2)

        if cv2.waitKey(33) & 0xFF == ord('q'):
            return
        cv2.imshow('Video', frame)  

if __name__ == '__main__':
    startapplication()
