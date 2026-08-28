# v1 of this script. It is very elementary and is meant 
# to be a simple test of the motor on land. 
# When script is active, hold down 'w' to move forward.
# Hold down 's' to move backward. Release keys to stop. 
# Press 'q' to quit the script.

import curses
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
    stdscr.addstr(1, 0, "Hold 'w' -> 80 (Forward)")
    stdscr.addstr(2, 0, "Hold 's' -> 70 (Reverse)")
    stdscr.addstr(3, 0, "Release  -> 75 (Neutral)")
    stdscr.addstr(4, 0, "Press 'q' to quit.")

    last_key_time = 0

    try:
        while True:
            key = stdscr.getch()
            now = time.time()

            if key != -1:
                last_key_time = now

                if key in (ord("w"), ord("W")):
                	target_duty = 80
			turn_left = FALSE
			turn_right = FALSE
                elif key in (ord("s"), ord("S")):
                	target_duty = 70
			turn_left = FALSE
			turn_right = FALSE
		elif key in (ord("a"), ord("A")):
			target_duty = 80
			turn_left = TRUE
			turn_right = FALSE
		elif key in (ord("d"), ord("D")):
			target_duty = 80
			turn_left = FALSE
			turn_right = TRUE
                elif key in (ord("q"), ord("Q")):
                    break
                else:
                    target_duty = 75
		    turn_left = FALSE
		    turn_right = FALSE
            else:
                if now - last_key_time > 0.15:
                    target_duty = 75

            if target_duty != current_duty:
                current_duty = target_duty
		if turn_left == TRUE:
			pi.set_PWM_dutycycle(MOTOR_PINS[0], target_duty)
			pi.set_PWM_dutycycle(MOTOR_PINS[1], 75)
		if turn_right == TRUE:
			pi.set_PWM_dutycycle(MOTOR_PINS[1], target_duty)
			pi.set_PWM_dutycycle(MOTOR_PINS[0], 75)
		else:
                	set_dual_dutycycle(current_duty)
                stdscr.addstr(
                    6,
                    0,
                    f"Current Signal (Both Pins): {current_duty}   ",
                    curses.A_BOLD,
                )
                stdscr.refresh()

            time.sleep(0.02)

    finally:
        # Shutdown sequence for both pins
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
