# this is script is constructed for testing the UDP communication between mediapipe (this file) and Polling UDP Receiver in UE5
# a demo sequence is written to test for all the basic movements of the vehicle 
# a message is formatted in string in key:value fashion (see below) and is sent to the listener using our custom ip and port

import socket
import time
import math

# --- Configuration ---
UDP_IP = "127.0.0.1"
UDP_PORT = 25565

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- State Machine Definition with GEAR control ---
# We now have a 'gear' command: 1 for forward, -1 for reverse.
# Note that when gear is -1, throttle is POSITIVE to mean "accelerate in reverse".

S_CURVE_FREQUENCY = 1.5 

demo_sequence = [
    # --- FORWARD SEQUENCE ---
    {"name": "Forward",         "duration": 4.0, "throttle": 0.9, "steer": 0.0,  "brake": 0.0, "gear": 1},
    # {"name": "Forward Left",    "duration": 1.5, "throttle": 0.5, "steer": -0.8, "brake": 0.0, "gear": 1},
    # {"name": "Forward Right",   "duration": 1.5, "throttle": 0.5, "steer": 0.8,  "brake": 0.0, "gear": 1},
    # {"name": "Forward Left",    "duration": 2.0, "throttle": 0.5, "steer": -0.8, "brake": 0.0, "gear": 1},
    {"name": "Forward S-Curve", "duration": 4.0, "throttle": 0.5, "steer": "s_curve", "brake": 0.0, "gear": 1},
    {"name": "Stop",            "duration": 1.5, "throttle": 0.0, "steer": 0.0,  "brake": 1.0, "gear": 0},
    
    # --- BACKWARD SEQUENCE ---
    {"name": "Backward",        "duration": 2.0, "throttle": 0.0, "steer": 0.0,  "brake": 0.6, "gear": -1}, # Note: throttle is positive
    # {"name": "Backward Left",   "duration": 1.5, "throttle": 0.0, "steer": -0.8, "brake": 0.5, "gear": -1},
    # {"name": "Backward Right",  "duration": 1.5, "throttle": 0.0, "steer": 0.8,  "brake": 0.5, "gear": -1},
    # {"name": "Backward Left",   "duration": 2.0, "throttle": 0.0, "steer": -0.8, "brake": 0.5, "gear": -1},
    {"name": "Backward S-Curve","duration": 4.0, "throttle": 0.0, "steer": "s_curve", "brake": 0.5, "gear": -1},
    {"name": "Stop",            "duration": 1.5, "throttle": 1.0, "steer": 0.0,  "brake": 0.0, "gear": 0},
]

# --- State Machine Initialisation (loop over the demo sequence for some duration and send the message for every frame)---

current_state_index = 0
state_start_time = time.time()

print(f"UDP Demo Sequence Script Started.")
print(f"Sending data to {UDP_IP}:{UDP_PORT}")
print("Press Ctrl+C to stop.")

try:
    while True:
        current_time = time.time()
        current_state = demo_sequence[current_state_index]
        state_duration = current_state["duration"]
        
        # --- State Transition Logic ---
        if (current_time - state_start_time) > state_duration:
            current_state_index = (current_state_index + 1) % len(demo_sequence)
            state_start_time = current_time
            current_state = demo_sequence[current_state_index]
            print(f"\n--- New State: {current_state['name']} ---")

        # --- Get Control Values for the Current State ---
        throttle_value = current_state["throttle"]
        brake_value = current_state["brake"]
        gear_value = current_state["gear"]
        
        if current_state["steer"] == "s_curve":
            time_in_state = current_time - state_start_time
            steer_value = math.sin(time_in_state * S_CURVE_FREQUENCY)
        else:
            steer_value = current_state["steer"]

        # Format the data message, now including the gear
        message = f"steer:{steer_value:.4f};throttle:{throttle_value:.4f};brake:{brake_value:.4f};gear:{gear_value}"
        
        sock.sendto(message.encode('utf-8'), (UDP_IP, UDP_PORT))
        print(f"State: {current_state['name']:<18} | {message}", end='\r')
        time.sleep(1.0 / 60.0)

except KeyboardInterrupt:
    print("\nScript stopped by user.")
