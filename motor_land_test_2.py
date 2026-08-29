from pynput import keyboard
import sys
import time
import pigpio

MOTOR_PINS = [18, 19]  # GPIO 18 (Pin 12) and GPIO 19 (Pin 35)
PWM_FREQUENCY = 50
PWM_RANGE = 1000

pi = pigpio.pi()

if not pi.connected:
    print("Failed to connect to pigpio daemon.")
    sys.exit(1)

# Configure both GPIO pins
for pin in MOTOR_PINS:
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_PWM_frequency(pin, PWM_FREQUENCY)
    pi.set_PWM_range(pin, PWM_RANGE)

# Startup at neutral (75)
pi.set_PWM_dutycycle(MOTOR_PINS[1], 75)
pi.set_PWM_dutycycle(MOTOR_PINS[0], 75)

def on_press(key):
    try:
        # Handle regular character keys (like W, A, S, D)
        if key.char == 'w':
            pi.set_PWM_dutycycle(MOTOR_PINS[0], 80)
            pi.set_PWM_dutycycle(MOTOR_PINS[1], 80)
        elif key.char == 's':
            pi.set_PWM_dutycycle(MOTOR_PINS[0], 70)
            pi.set_PWM_dutycycle(MOTOR_PINS[1], 70)
        elif key.char == 'a':
            pi.set_PWM_dutycycle(MOTOR_PINS[0], 80)
            pi.set_PWM_dutycycle(MOTOR_PINS[1], 75)
        elif key.char == 'd':
            pi.set_PWM_dutycycle(MOTOR_PINS[1], 80)
            pi.set_PWM_dutycycle(MOTOR_PINS[0], 75)
    except AttributeError:
        # Handle special keys (like Arrows, Space, etc.)
        if key == keyboard.Key.space:
            pi.set_PWM_dutycycle(MOTOR_PINS[1], 75)
            pi.set_PWM_dutycycle(MOTOR_PINS[0], 75)

def on_release(key):
    # Stop the remote control listener when Escape is pressed
    if key == keyboard.Key.esc:
        print("Exiting remote control...")
        return False

# Start listening to the keyboard in the background
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()