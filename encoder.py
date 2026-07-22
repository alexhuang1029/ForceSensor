import time
from datetime import datetime
import pigpio

# --- CONFIGURATION ---
GPIO_A = 17        # GPIO pin for Encoder Channel A (Channel B is unused)
PPR = 500          # Match your AMT102 DIP switch settings
INTERVAL = 0.25    # How often to calculate RPM (in seconds)

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

# Generate a unique filename using the current start timestamp
filename = f"rpm_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
print(f"Logging RPM data to {filename} ... Press Ctrl+C to stop.")

# Record the start time for elapsed time calculation
start_time = time.time()

try:
    with open(filename, mode='w', newline='') as csv_file:
        # Write CSV header including Elapsed Time
        csv_file.write("Timestamp,Elapsed_Seconds,RPM\n")
        
        while True:
            # Reset counter, wait for the interval
            pulse_count = 0
            time.sleep(INTERVAL)
            
            # Capture current time measurements
            now = time.time()
            current_timestamp = datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            elapsed_seconds = now - start_time
            
            # Read the accumulated pulses
            pulses_in_interval = pulse_count
            
            # Formula: RPM = (Pulses / PPR) * (60 / Interval)
            # Since we use EITHER_EDGE, we get 2 pulse edges (one rising, one falling) per cycle.
            # We divide the total counted edges by 2 to get full physical cycles.
            cycles = pulses_in_interval / 2.0
            rpm = (cycles / PPR) * (60.0 / INTERVAL)
            
            # Print to console
            print(f"Elapsed: {elapsed_seconds:.2f}s | RPM: {rpm:.2f}")
            
            # Write to CSV file and flush immediately
            csv_file.write(f"{current_timestamp},{elapsed_seconds:.3f},{rpm:.2f}\n")
            csv_file.flush()

except KeyboardInterrupt:
    print(f"\nStopping... Data saved to {filename}")
finally:
    cbA.cancel()
    pi.stop()
