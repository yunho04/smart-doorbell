from gpiozero import DigitalInputDevice
from signal import pause
from datetime import datetime

sensor = DigitalInputDevice(17)

def on_sound():
    print(datetime.now().strftime("%H:%M:%S.%f")[:-3], "소리 감지")

sensor.when_deactivated = on_sound
print("대기 중... (Ctrl+C로 종료)")
pause()
