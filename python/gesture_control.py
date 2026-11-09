import cv2
import mediapipe as mp
import socket
import math

# --- Configuration ---
UDP_IP = "127.0.0.1"
UDP_PORT = 25565
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- Gesture & Control Constants ---
STEERING_SENSITIVITY = 2.5
# NEW LOGIC: Re-implementing the dead zone for nuanced control
ACCEL_DEAD_ZONE_LOWER = 0.35  # Hand openness below this starts braking
ACCEL_DEAD_ZONE_UPPER = 0.45  # Hand openness above this starts accelerating
# The range between these two is the "coasting" zone.

# MediaPipe Hand Landmarker Setup
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

# --- State Variables ---
current_gear = 1
gear_shift_cooldown = 0
GEAR_SHIFT_DELAY_FRAMES = 30
is_paused = False # new var to track pause state

# --- Gesture Processing Functions ---

def get_steering_value(hand_landmarks):
    """Calculates steering from right hand's horizontal position."""
    if not hand_landmarks: return 0.0
    wrist_x = hand_landmarks.landmark[0].x
    steer_value = (wrist_x - 0.5) * STEERING_SENSITIVITY
    return max(-1.0, min(1.0, steer_value))

def get_hand_openness(hand_landmarks):
    """
    Calculates a single normalized "openness" value from 0.0 (closed) to 1.0 (open).
    This is the raw input for our driving logic.
    """
    if not hand_landmarks: return 0.0

    # # Use distance between thumb tip and pinky for a stable metric
    # thumb_tip = hand_landmarks.landmark[4]
    # pinky_tip = hand_landmarks.landmark[20]
    # openness = math.hypot(thumb_tip.x - pinky_tip.x, thumb_tip.y - pinky_tip.y)

    # # Normalize the openness value (these may need tuning)
    # min_open, max_open = 0.05, 0.35
    # normalized_openness = (openness - min_open) / (max_open - min_open)
    # return max(0.0, min(1.0, normalized_openness))

    # 1. Calculate the distance we want to measure (the "openness")
    thumb_tip = hand_landmarks.landmark[4]
    pinky_tip = hand_landmarks.landmark[20]
    openness_distance = math.hypot(thumb_tip.x - pinky_tip.x, thumb_tip.y - pinky_tip.y)

    # 2. Calculate a reference distance to normalize against (the "hand size")
    # A good, stable reference is the width of the palm.
    index_knuckle = hand_landmarks.landmark[5]
    pinky_knuckle = hand_landmarks.landmark[17]
    hand_size_reference = math.hypot(index_knuckle.x - pinky_knuckle.x, index_knuckle.y - pinky_knuckle.y)

    # 3. Calculate the relative openness as a ratio
    # Avoid division by zero if the hand size is not detected
    if hand_size_reference == 0:
        return 0.0
    
    relative_openness = openness_distance / hand_size_reference

    # 4. Normalize this new ratio into our 0.0 to 1.0 range
    # IMPORTANT: These values now represent a ratio and will need to be re-tuned.
    # A good starting point might be:
    min_ratio, max_ratio = 0.25, 3.0 
    normalized_openness = (relative_openness - min_ratio) / (max_ratio - min_ratio)
    
    return max(0.0, min(1.0, normalized_openness))


def is_handbrake_active(hand_landmarks):
    """Checks if the right hand is in a fist for the handbrake."""
    if not hand_landmarks: return False
    index_tip_y = hand_landmarks.landmark[8].y
    index_pip_y = hand_landmarks.landmark[6].y
    middle_tip_y = hand_landmarks.landmark[12].y
    middle_pip_y = hand_landmarks.landmark[10].y
    return index_tip_y > index_pip_y and middle_tip_y > middle_pip_y

def process_gear_shift(hand_landmarks, current_gear_state, cooldown_state):
    """Determines gear from left hand's thumbs up/down gesture."""
    if not hand_landmarks: return current_gear_state, cooldown_state

    new_gear, new_cooldown = current_gear_state, cooldown_state
    thumb_tip = hand_landmarks.landmark[4]
    thumb_ip = hand_landmarks.landmark[3]
    
    fingers_closed = (hand_landmarks.landmark[8].y > hand_landmarks.landmark[6].y and
                      hand_landmarks.landmark[12].y > hand_landmarks.landmark[10].y)

    if new_cooldown > 0:
        new_cooldown -= 1
    elif fingers_closed:
        target_gear = new_gear
        if thumb_tip.y < thumb_ip.y - 0.03: target_gear = 1  # Drive
        elif thumb_tip.y > thumb_ip.y + 0.03: target_gear = -1 # Reverse
        
        if target_gear != new_gear:
            new_gear = target_gear
            new_cooldown = GEAR_SHIFT_DELAY_FRAMES
            
    return new_gear, new_cooldown

def get_hand_type(classification):
    label = classification.label
    if "Left" in label: return "Left"
    if "Right" in label: return "Right"
    return "Unknown"

def is_t_shape_to_pause(left_hand, right_hand):
    """
    Checks for a custom 'pause' gesture.
    Gesture: T-shape -> Fingertips of the right hand are touching the knuckles (MCP joints)
    of the left hand, and the left hand is positioned above the right hand.
    """
    if not left_hand or not right_hand: 
        return
    
    # Get key landmarks
    right_fingertips = [
        right_hand.landmark[8],  # Index tip
        right_hand.landmark[12], # Middle tip
        right_hand.landmark[16], # Ring tip
        right_hand.landmark[20]  # Pinky tip
    ]
    left_knuckles = [
        left_hand.landmark[5],   # Index MCP
        left_hand.landmark[9],   # Middle MCP
        left_hand.landmark[13],  # Ring MCP
        left_hand.landmark[17]   # Pinky MCP
    ]
    left_wrist = left_hand.landmark[0]
    right_wrist = right_hand.landmark[0]

    # --- Condition 1: Check if fingertips are touching knuckles ---
    total_distance = 0
    for i in range(4):
        dist = math.hypot(right_fingertips[i].x - left_knuckles[i].x, 
                          right_fingertips[i].y - left_knuckles[i].y)
        total_distance += dist
    
    avg_distance = total_distance / 4

    touch_threshold = 0.13 
    # print(f"Average distance for T-shape: {avg_distance:.4f} (Threshold: {touch_threshold})")
    is_touching = avg_distance < touch_threshold

    # --- Condition 2: Check if left hand is above right hand ---
    is_left_hand_above = (right_wrist.y > left_wrist.y)
    # print(f"Left hand is above right hand: {is_left_hand_above}")

    if is_touching and is_left_hand_above:
        # print("T-shape detected: Pausing controls.")
        return True

def is_double_ok_to_resume(left_hand, right_hand):
    """Checks if both hands are making an 'OK' sign to resume."""
    
    def is_single_ok(hand_landmarks):
        if not hand_landmarks: return False
        
        # Check if thumb tip and index tip are touching
        thumb_tip = hand_landmarks.landmark[4]
        index_tip = hand_landmarks.landmark[8]
        avg_distance = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
        # print(f"Average distance for OK sign: {avg_distance:.4f} : Threshold: 0.05")
        is_touching = avg_distance < 0.05
        
        # Check if other fingers are extended
        middle_tip_y = hand_landmarks.landmark[12].y
        middle_pip_y = hand_landmarks.landmark[10]
        pinky_tip_y = hand_landmarks.landmark[20].y
        pinky_pip_y = hand_landmarks.landmark[18]
        are_others_extended = (middle_tip_y < middle_pip_y.y) and (pinky_tip_y < pinky_pip_y.y)
        # print(f"Other fingers extended: {are_others_extended}")

        return is_touching and are_others_extended

    # Return True only if both hands are making the OK sign
    if is_single_ok(left_hand) and is_single_ok(right_hand):
        # print("Double OK detected: Resuming controls.")
        return True

# --- Main Application Loop ---
cap = cv2.VideoCapture(0)

print("|||-------------------------------------------------------------------|||")
print("|||------------- Advanced Gesture Control Started --------------------|||")
print("-> Left Hand: Thumbs Up (Drive), Thumbs Down (Reverse)")
print("-> Right Hand: Steering (L/R), Accel/Decel (Open/Close), Handbrake (Fist)")
print("=> Press 'q' to quit.")
print("-------------------------------------------------------------------------")

while cap.isOpened():
    success, image = cap.read()
    if not success: continue

    image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
    image.flags.writeable = False
    results = hands.process(image)
    image.flags.writeable = True
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # --- Detect Hands and Update State ---
    left_hand_landmarks = None
    right_hand_landmarks = None
    if results.multi_hand_landmarks and results.multi_handedness:
        for landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
            hand_type = get_hand_type(handedness.classification[0])
            if hand_type == "Left": left_hand_landmarks = landmarks
            elif hand_type == "Right": right_hand_landmarks = landmarks
            mp_drawing.draw_landmarks(image, landmarks, mp_hands.HAND_CONNECTIONS)

    # Check for pause/resume gestures to update the state
    if is_t_shape_to_pause(left_hand_landmarks, right_hand_landmarks):
        is_paused = True
    elif is_double_ok_to_resume(left_hand_landmarks, right_hand_landmarks):
        is_paused = False

    if not is_paused:
        # --- Process Gestures & Apply New Control Logic ---
        current_gear, gear_shift_cooldown = process_gear_shift(left_hand_landmarks, current_gear, gear_shift_cooldown)
        steer_val = get_steering_value(right_hand_landmarks)
        openness_val = get_hand_openness(right_hand_landmarks)
        handbrake_on = is_handbrake_active(right_hand_landmarks)

        throttle_val = 0.0
        brake_val = 0.0
        handbrake_val = 1.0 if handbrake_on else 0.0

        if handbrake_on:
            throttle_val = 0.0
            brake_val = 0.0
        else:
            # CORRECTED LOGIC: Re-implementing the dead zone correctly.
            # This block interprets the single "openness" value.
            if openness_val > ACCEL_DEAD_ZONE_UPPER:
                # Map the upper range of openness to throttle
                throttle_val = (openness_val - ACCEL_DEAD_ZONE_UPPER) / (1.0 - ACCEL_DEAD_ZONE_UPPER)
            elif openness_val < ACCEL_DEAD_ZONE_LOWER:
                # Map the lower range of openness to brake (inverted)
                brake_val = 1.0 - (openness_val / ACCEL_DEAD_ZONE_LOWER)
            # If openness is between the lower and upper bounds, both throttle and brake remain 0.0 (coasting).

        # Final override for reverse gear: if in reverse, brake input is used for throttle.
        # This logic is now compatible with the dead zone.
        if current_gear == -1:
            # If we are braking (closing hand), that value becomes the reverse throttle.
            # If we are accelerating (opening hand), throttle_val will be > 0, which will act as the reverse brake.
            reverse_throttle = brake_val
            reverse_brake = throttle_val
            throttle_val = reverse_throttle
            brake_val = reverse_brake
        
        # Clamp all values just in case
        throttle_val = max(0.0, min(1.0, throttle_val))
        brake_val = max(0.0, min(1.0, brake_val))

    # --- Pack and Send Data (Conditionally) ---
    if not is_paused:
        message = f"steer:{steer_val:.4f};throttle:{throttle_val:.4f};brake:{brake_val:.4f};gear:{current_gear};handbrake:{handbrake_val}"
        sock.sendto(message.encode('utf-8'), (UDP_IP, UDP_PORT))
    
    # --- Display UI ---
    height, width, _ = image.shape
    gear_text = {1: "DRIVE", -1: "REVERSE", 0: "NEUTRAL"}.get(current_gear, "UNKNOWN")
    status_text = "PAUSED" if is_paused else "ACTIVE"
    status_color = (0, 0, 255) if is_paused else (0, 255, 0)
    cv2.putText(image, f"Gear: {gear_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(image, f"Steer: {steer_val:.2f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    cv2.putText(image, f"Throttle: {throttle_val:.2f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(image, f"Brake: {brake_val:.2f}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.putText(image, f"HANDBRAKE: {'ON' if handbrake_on else 'OFF'}", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
    cv2.putText(image, f"UDP STATUS: {status_text}", (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
    cv2.imshow('Advanced Gesture Control', image)

    if cv2.waitKey(5) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
hands.close()
print("\nScript finished.")
