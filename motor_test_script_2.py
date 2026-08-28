import pigpio
import time

pi = pigpio.pi() #create pigpio object
LED_PIN = 18 # Define the GPIO port to which the LED is connected.
PWM_FREQUENCY = 50 #define the PWM frequency in Hz
PWM_range = 1000
PWM_DUTYCYCLE = 0 # Define PWM duty cycle, value range 0 (2) 55,
pi.set_mode(LED_PIN, pigpio.OUTPUT) #Set the GPIO port to output mode
pi.set_PWM_frequency(LED_PIN, PWM_FREQUENCY) #set PWM frequency
pi.set_PWM_range(LED_PIN, PWM_range) # set range 1000

pi.set_PWM_dutycycle(LED_PIN, 75) # set PWM duty cycle 75/1000=7.5 per cent
time.sleep(4) # delay 3s unlock successful

print("START")
time.sleep(2)

pi.set_PWM_dutycycle(LED_PIN, 80)
print("80")
# Positive rotation 7.5%-10% duty cycle, the larger the duty cycle, the faster the positive rotation speed
time.sleep(5)



pi.set_PWM_dutycycle(LED_PIN, 75) # set PWM duty cycle 75/1000=7.5 per cent
print("end")
time.sleep(1) # delay 3s unlock successful
