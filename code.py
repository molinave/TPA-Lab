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
import sys
import select

# Configuración de RED
SSID = "wfrre-Docentes"
PASSWORD = "20$tscFrre.24"
BROKER = "10.13.100.84"
NOMBRE_EQUIPO = "cofactores"
DESCOVERY_TOPIC = "descubrir"
TOPIC = f"sensores/{NOMBRE_EQUIPO}"

# Variables de estado de red
wifi_conectado = False
mqtt_conectado = False
mqtt_client = None
pool = None

# Intento de conexión Wi-Fi
try:
    print(f"Intentando conectar a {SSID}...")
    wifi.radio.connect(SSID, PASSWORD)
    print(f"Conectado a {SSID}")
    print(f"Dirección IP: {wifi.radio.ipv4_address}")
    wifi_conectado = True
    pool = socketpool.SocketPool(wifi.radio)
    
except Exception as e:
    print(f"Error al conectar a WiFi: {e}")
    print("El programa continuará sin funcionalidades de red.")
    wifi_conectado = False
    
# Intento de conexión MQTT (solo si hay Wi-Fi)
if wifi_conectado:
    def connect(client, userdata, flags, rc):
        global mqtt_conectado
        print("Conectado al broker MQTT")
        mqtt_conectado = True
        client.publish(DESCOVERY_TOPIC, json.dumps(
            {"equipo": NOMBRE_EQUIPO, 
             "magnitudes": ["pos_x", "pos_y"]}))

    try:
        mqtt_client = MQTT.MQTT(
            broker=BROKER,
            port=1883,
            socket_pool=pool
        )
        mqtt_client.on_connect = connect
        mqtt_client.connect()
        mqtt_conectado = True
    except Exception as e:
        print(f"Error al conectar a MQTT: {e}")
        mqtt_conectado = False


# Usamos estas varaibles globales para controlar cada cuanto publicamos
last_pub = 0
PUB_INTERVAL = 5

def publish():
    global last_pub

    if not mqtt_conectado:
        return # Salir si no hay conexión

    now = time.monotonic()
    if now - last_pub >= PUB_INTERVAL:
        try:
            x_topic = f"{TOPIC}/pos_x"
            mqtt_client.publish(x_topic, str(pos_x))

            y_topic = f"{TOPIC}/pos_y"
            mqtt_client.publish(y_topic, str(pos_y))

            last_pub = now
            # print(f"Se publico correctamente: X:{pos_x} | Y:{pos_y}")

        except Exception as e:
            # Si hay un error de publicación, intentamos reconectar en el siguiente ciclo
            print(f"Error publicando MQTT: {e}. Intentando reconectar...")
            try:
                mqtt_client.reconnect()
            except:
                pass

# CONFIGURACIÓN LED RGB 
led_r = pwmio.PWMOut(board.GP10, frequency=1000, duty_cycle=0)
led_g = pwmio.PWMOut(board.GP11, frequency=1000, duty_cycle=0)
led_b = pwmio.PWMOut(board.GP12, frequency=1000, duty_cycle=0)

def set_led_color(r, g, b):
    led_r.duty_cycle = int(r * 65535)
    led_g.duty_cycle = int(g * 65535)
    led_b.duty_cycle = int(b * 65535)

def led_off():
    set_led_color(0, 0, 0)

# CONFIGURACIÓN MOTOR PASO A PASO (28BYJ-48)
IN1 = digitalio.DigitalInOut(board.GP2)
IN2 = digitalio.DigitalInOut(board.GP3)
IN3 = digitalio.DigitalInOut(board.GP4)
IN4 = digitalio.DigitalInOut(board.GP5)
for pin in (IN1, IN2, IN3, IN4):
    pin.direction = digitalio.Direction.OUTPUT

STEP_SEQUENCE = [
    (1, 0, 0, 1),
    (1, 0, 0, 0),
    (1, 1, 0, 0),
    (0, 1, 0, 0),
    (0, 1, 1, 0),
    (0, 0, 1, 0),
    (0, 0, 1, 1),
    (0, 0, 0, 1)
]

step_index = 0

def motor_step(direction):
    global step_index
    step_index = (step_index + direction) % len(STEP_SEQUENCE)
    IN1.value, IN2.value, IN3.value, IN4.value = STEP_SEQUENCE[step_index]

# CONFIGURACIÓN JOYSTICK
joy_x = analogio.AnalogIn(board.GP26)
joy_y = analogio.AnalogIn(board.GP27)
joystick_btn = digitalio.DigitalInOut(board.GP28)
joystick_btn.direction = digitalio.Direction.INPUT
joystick_btn.pull = digitalio.Pull.UP  # Botón presionado = LOW

def read_joystick(axis):
    return axis.value / 65535 * 100  # valor 0–100%

# VARIABLES DEL SISTEMA
pos_x = 400
pos_y = 10
TOPE_X_MIN, TOPE_X_MAX = 0, 800
TOPE_Y_MIN, TOPE_Y_MAX = 0, 20
modo_config = False
input_buffer = ""

# VARIABLES DE PARPADEO
last_blink_time = 0
blink_interval = 0.3  # segundos
led_state_on = True
modo_led = "espera"  # puede ser: 'espera', 'mov_x', 'subiendo', 'bajando', 'error'

def error_tope(mensaje):
    global modo_led
    modo_led = "error"
    set_led_color(1, 0, 0)
    print(f"ERROR: {mensaje}")
    time.sleep(0.5)

# LOOP PRINCIPAL
print("Sistema de grúa iniciado.")
set_led_color(0, 1, 0)

while True:

    # MODO CONFIGURACIÓN DE LÍMITES
    if not joystick_btn.value and not modo_config:
        modo_config = True
        set_led_color(1, 1, 0)  # Amarillo
        print("\n[MODO CONFIGURACIÓN] Ingrese nuevo TOPE_X_MAX (actual: {})".format(TOPE_X_MAX))
        print("Escriba un número y presione Enter:")
        input_buffer = ""
        time.sleep(0.5)

    if modo_config:
        # Revisar si hay entrada del usuario en el puerto serial
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            c = sys.stdin.read(1)
            if c == "\n":  # Enter
                try:
                    nuevo_valor = int(input_buffer.strip())
                    if nuevo_valor <= TOPE_X_MIN:
                        print("Valor inválido. Debe ser mayor que el mínimo actual ({}).".format(TOPE_X_MIN))
                    elif pos_x > nuevo_valor:
                        print("No se puede establecer TOPE_X_MAX en {} porque la posición actual ({}) lo supera.".format(
                            nuevo_valor, pos_x))
                    else:
                        TOPE_X_MAX = nuevo_valor
                        print("Nuevo TOPE_X_MAX establecido: {}".format(TOPE_X_MAX))
                except:
                    print("Entrada no válida. Ingrese un número entero.")
                modo_config = False
                set_led_color(0, 1, 0)  # volver a verde
            else:
                input_buffer += c
        # mientras está en modo config, salteamos el resto del loop
        continue

    x_val = read_joystick(joy_x)
    y_val = read_joystick(joy_y)
    moved = False
    modo_previo = modo_led

    # CONTROL EJE X
    if x_val > 60:  # derecha
        if pos_x < TOPE_X_MAX:
            motor_step(1)
            pos_x += 1
            modo_led = "mov_x"
            moved = True
        else:
            error_tope("Tope X máximo")
    elif x_val < 40:  # izquierda
        if pos_x > TOPE_X_MIN:
            motor_step(-1)
            pos_x -= 1
            modo_led = "mov_x"
            moved = True
        else:
            error_tope("Tope X mínimo")

    # CONTROL EJE Y
    if y_val > 60:  # subiendo
        if pos_y < TOPE_Y_MAX:
            pos_y += 0.1
            modo_led = "subiendo"
            moved = True
        else:
            error_tope("Tope superior Y")
    elif y_val < 40:  # bajando
        if pos_y > TOPE_Y_MIN:
            pos_y -= 0.1
            modo_led = "bajando"
            moved = True
        else:
            error_tope("Tope inferior Y")

    # SIN MOVIMIENTO
    if not moved and modo_led != "error":
        modo_led = "espera"

    # CONTROL DE PARPADEO
    current_time = time.monotonic()

    # alternar LED solo si corresponde parpadeo
    if current_time - last_blink_time >= blink_interval:
        last_blink_time = current_time
        led_state_on = not led_state_on  # alternar ON/OFF

    # aplicar color según modo actual
    if modo_led == "espera":
        set_led_color(0, 1, 0)  # verde fijo
    elif modo_led == "mov_x":
        if led_state_on:
            set_led_color(0, 1, 0)  # verde parpadeante
        else:
            led_off()
    elif modo_led == "subiendo":
        if led_state_on:
            set_led_color(0, 0, 1)  # azul parpadeante
        else:
            led_off()
    elif modo_led == "bajando":
        set_led_color(0, 0, 1)  # azul fijo
    elif modo_led == "error":
        set_led_color(1, 0, 0)  # rojo fijo

    # MONITOREO SERIAL
    if modo_led != modo_previo:
        print(f"Modo LED: {modo_led}")
    print(f"PosX: {pos_x:.1f} | PosY: {pos_y:.1f} | JoyX: {x_val:.1f}% | JoyY: {y_val:.1f}%")

    # Publicación MQTT
    if wifi_conectado:
        publish()
        if mqtt_conectado:
            mqtt_client.loop(0.01) # Permitir la comunicación MQTT

    time.sleep(0.01)