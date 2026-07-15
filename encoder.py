import time
import pigpio

# --- CONFIGURATION ---
GPIO_A = 17       # GPIO pin for Encoder Channel A (Channel B is unused)
PPR = 2048        # Match your AMT102 DIP switch settings
INTERVAL = 1.0    # How often to calculate RPM (in seconds)

# Global pulse counter
pulse_count = 0

pi = pigpio.pi()
if not pi.connected:
    print("Failed to connect to pigpio daemon. Run 'sudo pigpiod' first.")
    exit()

# Set up Pin A
pi.set_mode(GPIO_A, pigpio.INPUT)
pi.set_pull_up_down(GPIO_A, pigpio.PUD_UP)

# Callback function: Simply increments the counter on every pulse edge
def pulse_callback(gpio, level, tick):
    global pulse_count
    pulse_count += 1

# Monitor both rising and falling edges of Channel A for maximum resolution
cbA = pi.callback(GPIO_A, pigpio.EITHER_EDGE, pulse_callback)

print("Measuring RPM (Direction Ignored)... Press Ctrl+C to stop.")

try:
    while True:
        # Reset counter, wait for the interval
        pulse_count = 0
        time.sleep(INTERVAL)
        
        # Read the accumulated pulses
        pulses_in_interval = pulse_count
        
        # Formula: RPM = (Pulses / PPR) * (60 / Interval)
        # Since we use EITHER_EDGE, we get 2 pulse edges (one rising, one falling) per cycle.
        # We divide the total counted edges by 2 to get full physical cycles.
        cycles = pulses_in_interval / 2.0
        rpm = (cycles / PPR) * (60.0 / INTERVAL)
        
        print(f"Edges/sec: {pulses_in_interval} | Calculated RPM: {rpm:.2f}")

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    cbA.cancel()
    pi.stop()