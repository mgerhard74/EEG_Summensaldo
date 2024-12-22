import random
import json
import time
import logging
from paho.mqtt import client as mqtt_client
from flask import Flask, render_template_string
import threading

broker = '10.0.0.164'
port = 1883
topic = "amis/user"
# Generate a Client ID with the subscribe prefix.
# client_id = f'subscribe-{random.randint(0, 100)}'
username = 'mqttuser'
password = 'xxxxxxxx'

saldo = 10 * [0]
epoch_time = 10 * [0]
alive = 10 * [0]

# Setup logging
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Flask app
app = Flask(__name__)

summensaldo = 0
offline = ""

def connect_mqtt() -> mqtt_client:
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Verbunden mit MQTT broker " + broker + "!")
        else:
            logger.error("Verbindung nicht möglich; Fehlercode von on_connect %d\n", rc)

    client = mqtt_client.Client()
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        global summensaldo, offline
        logger.info(f"Empfange `{msg.payload.decode()}` von `{msg.topic}` Topic")
        result = json.loads(msg.payload.decode('utf-8'))
        for i in range(1, 6):
            if msg.topic == topic + str(i):
                saldo[i] = result['saldo']
                alive[i] = True
                epoch_time[i] = int(time.time())

    for i in range(1, 6):
        client.subscribe(topic + str(i))
    client.on_message = on_message

def mqtt_loop():
    global summensaldo, offline
    client = connect_mqtt()
    subscribe(client)
    while True:
        client.loop(1)
        for i in range(1, 6):
            if int(time.time()) > (epoch_time[i] + 120):  # für 2 Min keine Werte
                saldo[i] = 0
                alive[i] = False
        offline = ""
        for i in range(1, 6):
            if not alive[i]:
                offline += f"{i},"
        if len(offline) > 0:
            offline = offline[:-1]
        summensaldo = int(saldo[1] + saldo[2] + saldo[3] + saldo[4] + saldo[5])
        logger.info(f"Summensaldo: {summensaldo} Watt, Offline Teilnehmer: {offline}")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="5">
    <title>EEG Status</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
        }
        h1 {
            color: #333;
        }
        .status {
            margin-top: 20px;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
            background-color: #f9f9f9;
        }
        .status p {
            margin: 5px 0;
        }
    </style>
</head>
<body>
    <h1>EEG Status</h1>
    <div class="status">
        <p><strong>Summensaldo:</strong> {{ summensaldo }} Watt</p>
        <p><strong>Offline Teilnehmer:</strong> {{ offline }}</p>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def get_status():
    return render_template_string(HTML_TEMPLATE, summensaldo=summensaldo, offline=offline)

def start_mqtt():
    mqtt_thread = threading.Thread(target=mqtt_loop)
    mqtt_thread.daemon = True
    mqtt_thread.start()

if __name__ == '__main__':
    start_mqtt()
    app.run(host='10.0.0.164', port=5000)
