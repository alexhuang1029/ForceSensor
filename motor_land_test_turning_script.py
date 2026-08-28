# v3 Dual Motor Controller with Universal Acceleration Boost
# Applies an initial 0.5s power boost across all movement keys (W, S, A, D).
# Release keys to stop (0.3s timeout). Press 'q' to quit.

import curses
import sys
import time
import pigpio

MOTOR_PINS = [18, 19]  # GPIO 18 (Pin 12) and GPIO 19 (Pin 35)
PWM_FREQUENCY = 50
PWM_RANGE = 1000

# Timeout in seconds before assuming key is released (300ms)
KEY_TIMEOUT = 0.30

pi = pigpio.pi()

if not pi.connected:
    print("Failed to connect to pigpio daemon.")
    sys.exit(1)


def set_dual_dutycycle(duty):
    """Updates PWM signal on both motor pins together."""
    for pin in MOTOR_PINS:
        pi.set_PWM_dutycycle(pin, duty)


def main(stdscr):
    curses.cbreak()
    stdscr.nodelay(True)
    stdscr.clear()

    # Configure both GPIO pins
    for pin in MOTOR_PINS:
        pi.set_mode(pin, pigpio.OUTPUT)
        pi.set_PWM_frequency(pin, PWM_FREQUENCY)
        pi.set_PWM_range(pin, PWM_RANGE)

    # Startup at neutral (75)
    current_duty = 75
    set_dual_dutycycle(current_duty)

    stdscr.addstr(0, 0, "=== Dual Motor Controller (GPIO 18 & 19) ===")
    stdscr.addstr(1, 0, "Hold 'w' -> Boost: 80 (0.5s) -> Sustained: 79")
    stdscr.addstr(2, 0, "Hold 's' -> Boost: 70 (0.5s) -> Sustained: 71")
    stdscr.addstr(3, 0, "Hold 'a'/'d' -> Boost Turn: 80 (0.5s) -> Sustained: 79")
    stdscr.addstr(4, 0, "Release  -> 75 (Neutral)")
    stdscr.addstr(5, 0, "Press 'q' to quit.")

    last_key_time = 0

    # Boost tracking state
    active_key = None
    key_press_start_time = 0.0

    try:
        while True:
            key = stdscr.getch()
            now = time.time()

            if key != -1:
                last_key_time = now
                key_char = chr(key).lower() if key < 256 else None

                if key_char in ("w", "s", "a", "d"):
                    # Detect new action or direction switch
                    if active_key != key_char:
                        active_key = key_char
                        key_press_start_time = now

                    # Check if within boost duration
                    is_boosting = (now - key_press_start_time) <= 0.5

                    # Determine target duties based on movement type
                    if key_char == "w":
                        target_duty = 80 if is_boosting else 79
                        turn_left = False
                        turn_right = False
                    elif key_char == "s":
                        target_duty = 70 if is_boosting else 71
                        turn_left = False
                        turn_right = False
                    elif key_char == "a":
                        target_duty = 80 if is_boosting else 79
                        turn_left = True
                        turn_right = False
                    elif key_char == "d":
                        target_duty = 80 if is_boosting else 79
                        turn_left = False
                        turn_right = True

                elif key_char == "q":
                    break
                else:
                    active_key = None
                    target_duty = 75
                    turn_left = False
                    turn_right = False

            else:
                # Key timeout / release check
                if now - last_key_time > KEY_TIMEOUT:
                    active_key = None
                    target_duty = 75
                    turn_left = False
                    turn_right = False
                elif active_key:
                    # Still held down; re-evaluate boost state
                    is_boosting = (now - key_press_start_time) <= 0.5

                    if active_key == "w":
                        target_duty = 80 if is_boosting else 79
                    elif active_key == "s":
                        target_duty = 70 if is_boosting else 71
                    elif active_key in ("a", "d"):
                        target_duty = 80 if is_boosting else 79

            # Apply motor power output
            if turn_left:
                pi.set_PWM_dutycycle(MOTOR_PINS[0], target_duty)
                pi.set_PWM_dutycycle(MOTOR_PINS[1], 75)
            elif turn_right:
                pi.set_PWM_dutycycle(MOTOR_PINS[1], target_duty)
                pi.set_PWM_dutycycle(MOTOR_PINS[0], 75)
            else:
                set_dual_dutycycle(target_duty)

            current_duty = target_duty

            # UI Update
            boosting_status = "ACTIVE" if active_key and (now - key_press_start_time <= 0.5) else "OFF"
            stdscr.addstr(
                7,
                0,
                f"Active Key: {str(active_key).upper()} | Target Duty: {target_duty} | Boost: {boosting_status}   ",
                curses.A_BOLD,
            )
            stdscr.refresh()

            time.sleep(0.02)

    finally:
        # Safe shutdown sequence
        set_dual_dutycycle(75)
        time.sleep(0.2)
        set_dual_dutycycle(0)
        pi.stop()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        set_dual_dutycycle(75)
        time.sleep(0.2)
        set_dual_dutycycle(0)
        pi.stop()
        print("\nExited safely.")