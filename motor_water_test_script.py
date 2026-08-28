import sys
import time
import pigpio

pi = pigpio.pi()  # create pigpio object
LED_PIN = 18  # Define the GPIO port to which the LED is connected.
PWM_FREQUENCY = 50  # define the PWM frequency in Hz
PWM_range = 1000
PWM_DUTYCYCLE = 0  # Define PWM duty cycle, value range 0 (2) 55,

pi.set_mode(LED_PIN, pigpio.OUTPUT)  # Set the GPIO port to output mode
pi.set_PWM_frequency(LED_PIN, PWM_FREQUENCY)  # set PWM frequency
pi.set_PWM_range(LED_PIN, PWM_range)  # set range 1000

try:
    pi.set_PWM_dutycycle(
        LED_PIN, 75
    )  # set PWM duty cycle 75/1000=7.5 per cent
    time.sleep(4)  # delay 3s unlock successful

    print("START")
    time.sleep(2)

    pi.set_PWM_dutycycle(LED_PIN, 80)
    print("80")
    # Positive rotation 7.5%-10% duty cycle, the larger the duty cycle, the faster the positive rotation speed
    time.sleep(2)

    pi.set_PWM_dutycycle(LED_PIN, 85)
    print("85")
    time.sleep(5)

    pi.set_PWM_dutycycle(LED_PIN, 86)
    print("86")
    time.sleep(1)

    pi.set_PWM_dutycycle(LED_PIN, 87)
    print("87")
    time.sleep(5)

    pi.set_PWM_dutycycle(LED_PIN, 88)
    print("88")
    time.sleep(1)

    pi.set_PWM_dutycycle(LED_PIN, 89)
    print("89")
    time.sleep(5)

    pi.set_PWM_dutycycle(LED_PIN, 90)
    print("90")
    time.sleep(1)

    pi.set_PWM_dutycycle(LED_PIN, 91)
    print("91")
    time.sleep(5)

    pi.set_PWM_dutycycle(LED_PIN, 92)
    print("92")
    time.sleep(1)

    pi.set_PWM_dutycycle(LED_PIN, 93)
    print("93")
    time.sleep(5)

    pi.set_PWM_dutycycle(LED_PIN, 94)
    print("94")
    time.sleep(1)

    pi.set_PWM_dutycycle(LED_PIN, 95)
    print("95")
    time.sleep(5)

    # cooldown sequence to prevent motor shear
    print("cooldown")
    for duty in range(94, 75, -1):
        pi.set_PWM_dutycycle(LED_PIN, duty)
        time.sleep(0.25)

    pi.set_PWM_dutycycle(
        LED_PIN, 75
    )  # set PWM duty cycle 75/1000=7.5 per cent
    print("end")
    time.sleep(1)

except KeyboardInterrupt:
    print("\n[!] Ctrl+C detected. Immediately sending 75 signal and stopping.")
    pi.set_PWM_dutycycle(LED_PIN, 75)
finally:
    pi.stop()  # Clean up pigpio resources on exit
    sys.exit(0)