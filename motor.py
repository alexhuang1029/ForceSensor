import pigpio
import time

# --- Configuration ---
LED_PIN = 18          # GPIO Pin
PWM_FREQUENCY = 50    # 50 Hz
PWM_RANGE = 1000      # Resolution of the PWM (0 to 1000)

# --- Bounds configuration ---
NEUTRAL = 75
RANGE_SPAN = 25.0     # 100 - 75 or 75 - 50

# --- Initialization ---
pi = pigpio.pi()
if not pi.connected:
    print("Failed to connect to pigpio daemon. Is 'sudo pigpiod' running?")
    exit()

pi.set_mode(LED_PIN, pigpio.OUTPUT)
pi.set_PWM_frequency(LED_PIN, PWM_FREQUENCY)
pi.set_PWM_range(LED_PIN, PWM_RANGE)

def set_motor_speed(duty_value):
    """Sets motor speed and automatically prints direction and percentage."""
    if duty_value == NEUTRAL:
        status = "Neutral (0%)"
    elif duty_value > NEUTRAL:
        pct = ((duty_value - NEUTRAL) / RANGE_SPAN) * 100
        status = f"Forward ({pct:.0f}%)"
    else:
        pct = ((NEUTRAL - duty_value) / RANGE_SPAN) * 100
        status = f"Reverse ({pct:.0f}%)"
        
    print(f"Target: {duty_value:<3} | Current Action: {status}")
    pi.set_PWM_dutycycle(LED_PIN, duty_value)

# --- Main Execution Sequence ---
try:
    print("Starting motor sequence")
    print("-" * 50)

    # 1. Unlock / Neutral
    set_motor_speed(75)
    time.sleep(3)

    # 2. 20% Forward
    set_motor_speed(80)
    time.sleep(15)

    # 3. 20% Reverse
    set_motor_speed(70)
    time.sleep(5)

    # 4. Return to Neutral
    set_motor_speed(75)
    time.sleep(5)

except KeyboardInterrupt:
    print("\nSequence interrupted by user.")

finally:
    print("\n🧹 Cleaning up: Ensuring motor is neutral.")
    pi.set_PWM_dutycycle(LED_PIN, NEUTRAL)
    pi.stop()
    print("Done.")