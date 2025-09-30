import board
import analogio
import digitalio
import pwmio
from adafruit_motor import stepper
import time
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import json

# Configuración de RED
SSID = "wfrre-Docentes"
PASSWORD = "20$tscFrre.24"
BROKER = "10.13.100.154"
NOMBRE_EQUIPO = "cofactores"
DESCOVERY_TOPIC = "descubrir"
TOPIC = f"sensores/{NOMBRE_EQUIPO}"

print(f"Intentando conectar a {SSID}...")
try:
    wifi.radio.connect(SSID, PASSWORD)
    print(f"Conectado a {SSID}")
    print(f"Dirección IP: {wifi.radio.ipv4_address}")
except Exception as e:
    print(f"Error al conectar a WiFi: {e}")
    while True:
        pass

    # Configuración MQTT
pool = socketpool.SocketPool(wifi.radio)


def connect(client, userdata, flags, rc):
    print("Conectado al broker MQTT")
    client.publish(DESCOVERY_TOPIC, json.dumps({"equipo": NOMBRE_EQUIPO, "magnitudes": ["x_metros", "y_metros"]}))


mqtt_client = MQTT.MQTT(
    broker=BROKER,
    port=1883,
    socket_pool=pool
)

mqtt_client.on_connect = connect
mqtt_client.connect()

# Usamos estas varaibles globales para controlar cada cuanto publicamos
last_pub = 0
PUB_INTERVAL = 5


def publish():
    global last_pub
    now = time.monotonic()

    if now - last_pub >= PUB_INTERVAL:
        try:
            x_topic = f"{TOPIC}/x_metros"
            mqtt_client.publish(x_topic, str(x_value))

            y_topic = f"{TOPIC}/y_metros"
            mqtt_client.publish(y_topic, str(y_value))

            last_pub = now

        except Exception as e:
            print(f"Error publicando MQTT: {e}")


# --- Configuración del Joystick y Botón SW ---
x_axis = analogio.AnalogIn(board.GP26)
y_axis = analogio.AnalogIn(board.GP27)
button = digitalio.DigitalInOut(board.GP28)
button.pull = digitalio.Pull.UP

# --- Definición de Límites y Puntos Muertos ---
DEAD_ZONE_MIN = 30000
DEAD_ZONE_MAX = 35000

X_LIMIT_MIN = 20000
X_LIMIT_MAX = 45000
Y_LIMIT_MIN = 20000
Y_LIMIT_MAX = 45000

INICIO_X = 0
INICIO_Y = 0
TOPE_X = 1000
TOPE_Y = 20

# --- Configuración del LED RGB ---
led_red = pwmio.PWMOut(board.GP10, frequency=5000, duty_cycle=0)
led_green = pwmio.PWMOut(board.GP11, frequency=5000, duty_cycle=0)
led_blue = pwmio.PWMOut(board.GP12, frequency=5000, duty_cycle=0)

BRIGHTNESS = 65535
BLINK_DELAY = 0.2

# --- Función para apagar todos los LEDs ---
def turn_off_all_leds():
    led_red.duty_cycle = 0
    led_green.duty_cycle = 0
    led_blue.duty_cycle = 0

print("Programa de control de LED con Joystick en ejecución.")
print("Moviendo dentro del cubo. Limites X: 20000-45000, Limites Y: 20000-45000")

while True:
    x_value = x_axis.value
    y_value = y_axis.value
    button_pressed = not button.value

    publish()

    # Apaga todos los LEDs al inicio de cada ciclo
    turn_off_all_leds()

    # --- Lógica de Estado de ERROR (Prioridad Máxima) ---
    # Se añade la condición de que si hay un error, el programa
    # se detiene y solo enciende el LED rojo.
    if button_pressed:

        print("ERROR: Límites excedidos o botón presionado.")
        led_red.duty_cycle = BRIGHTNESS

    # --- Lógica de Estados de Control (Solo si no hay error) ---
    else:
        # Movimiento en el eje Y
        if y_value < DEAD_ZONE_MIN:
            if INICIO_Y > TOPE_Y:
                led_red.duty_cycle = BRIGHTNESS
            else:
                print(f"Baja brazo de grúa: {x_value}")
                led_blue.duty_cycle = BRIGHTNESS
                INICIO_Y += 1
                print(f"Brazo se baja un: {INICIO_Y}")

        elif y_value > DEAD_ZONE_MAX:
            if INICIO_Y < 0:
                led_red.duty_cycle = BRIGHTNESS
            else:
                print(f"Lev")