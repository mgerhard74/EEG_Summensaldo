import json
import time
import logging
from paho.mqtt import client as mqtt_client                      # pip install paho-mqtt
from flask import Flask, render_template_string                  # pip install Flask
import threading
import os
import schedule                                                  # pip install schedule
from collections import deque
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# === Konfiguration ===
log = int(config.get('ALLGEMEIN','LOGGING',fallback='0'))        # Schreibe app.log ?
broker = config['ALLGEMEIN']['MQTT_BROKER']                      # Mqtt auf diesem Raspi
port = int(config['ALLGEMEIN']['MQTT_PORT'])
topic = config['ALLGEMEIN']['TOPIC']                             # amis/user1, amis/user2, usw.
username = config['ALLGEMEIN']['MQTTUSER']                       # Mqtt Server Zugangsdaten
password = config['ALLGEMEIN']['MQTTPASSWORD']

eeg_name = config.get('ALLGEMEIN','EEG_NAME', fallback='DEMO')   # EEG-Name für die Website bzw EMail
anz_teilnehmer = int(config['ALLGEMEIN']['ANZ_TEILNEHMER'])      # zum Auslesen der Topics
http_ip = config['ALLGEMEIN']['HTTP_IP']
http_port = int(config['ALLGEMEIN']['HTTP_PORT'])

email_sent = False                                               # Globale Variable zum Nachverfolgen, ob eine offline-Benachrichtigung gesendet wurde

EMAIL_ADDRESS = config['EMAIL']['EMAIL_ADDRESS']
EMAIL_PASSWORD = config['EMAIL']['EMAIL_PASSWORD']
EMAIL_RECEIVER = config['EMAIL']['EMAIL_RECEIVER']
EMAIL_SERVER = config['EMAIL']['EMAIL_SERVER']

# ===

saldo = (anz_teilnehmer+1) * [0]
epoch_time = (anz_teilnehmer+1) * [0]
alive = (anz_teilnehmer+1) * [0]

program_start_time = time.time()

# Setup logging
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger()

# Flask app
app = Flask(__name__)

summensaldo = 0
online = ""
offline = ""
zeit = ""
summensaldo_mw = 60 * [0]
fifo_summensaldo = deque(maxlen=60)


def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(EMAIL_SERVER, 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
            if log:
                logger.info(f"E-Mail erfolgreich gesendet. Nachricht: {body}")
    except Exception as e:
        if log:
            logger.error(f"Fehler beim Senden der E-Mail: {e}")

def connect_mqtt() -> mqtt_client:
    def on_connect(client, userdata, flags, rc, properties):
        if rc == 0:
            if log:
                logger.info("Verbunden mit MQTT broker " + broker + "!")
        else:
            if log:
                logger.error("Verbindung nicht möglich; Fehlercode von on_connect %d\n", rc)

    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        global summensaldo, online, offline, anz_teilnehmer, zeit
        if log:
            logger.info(f"Topic `{msg.topic}`: `{msg.payload.decode()}` empfangen")
        result = json.loads(msg.payload.decode('utf-8'))
        for i in range(1, anz_teilnehmer+1):
            if msg.topic == topic + str(i):
                saldo[i] = result['saldo']
                alive[i] = True
                epoch_time[i] = int(time.time())
    global anz_teilnehmer

    for i in range(1, anz_teilnehmer+1):
        client.subscribe(topic + str(i))
    client.on_message = on_message

def mqtt_loop():
    global summensaldo, online, offline, anz_teilnehmer, zeit, email_sent, program_start_time
    client = connect_mqtt()
    subscribe(client)
    client.loop_start()
    
    while True:
        for i in range(1, anz_teilnehmer+1):
            if int(time.time()) > (epoch_time[i] + 120):  # für 2 Min keine Werte, dann ist Teilnehmer offline
                saldo[i] = 0
                alive[i] = False
        online = ""
        offline = ""
        for i in range(1, anz_teilnehmer+1):
            if not alive[i]:
                offline += f"{i},"
            elif alive[i]:
                online += f"{i},"
        if len(online) > 0:
            online = online[:-1]
        if len(offline) > 0:
            offline = offline[:-1]

        # E-Mail-Benachrichtigung senden, wenn Teilnehmer offline sind
        current_time = time.time()
        if offline and not email_sent and (current_time - program_start_time) > 180:
            subject = f"EEG {eeg_name} Teilnehmer Offline-Warnung"
            body = f"Die folgenden EEG-Teilnehmer sind offline: {offline}"
            send_email(subject, body)
            email_sent = True
        if len(offline)==0:  # Alle Teilnehmer sind online
            email_sent = False

        summensaldo = 0
        for i in range(1, anz_teilnehmer+1):
            summensaldo += saldo[i]
        summensaldo_mw[int(time.strftime("%S"))] = summensaldo

        if len(online)>0:
            if log:
                logger.info(f"Summensaldo: {summensaldo} Watt, Online Teilnehmer: {online}, Offline Teilnehmer: {offline}")
            zeit = time.strftime("%H")+":"+time.strftime("%M")+":"+time.strftime("%S")

        # Speicherung des Summensaldo im Array
        if time.strftime("%S") == "00":                              #überprüft, ob es eine volle Minute ist
            mittelwert = 0
            for i in range(0,60):
                mittelwert += summensaldo_mw[i];
                #logger.info(f"Saldo {i}: {summensaldo_mw[i]} Watt")
            mittelwert = round(mittelwert / 60);
            #logger.info(f"Mittelwert: {mittelwert} Watt")
            fifo_summensaldo.append(mittelwert)

        time.sleep(1)

def delete_log_file():
    if os.path.exists("app.log"):
        os.remove("app.log")
        if log:
            logger.info("Log-Datei wurde gelöscht")
    else:
        if log:
            logger.warning("Log-Datei konnte nicht gefunden werden, keine Aktion durchgeführt")
    # Logger neu initialisieren
    logging.basicConfig(filename='app.log', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s', force=True)

# Schedule log um Mitternacht löschen
schedule.every().day.at("00:00").do(delete_log_file)

def schedule_loop():
    while True:
        schedule.run_pending()
        time.sleep(1)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="5">
    <meta http-equiv="expires" content="0">
    <meta name="author" content="Gerhard Mitterbaur, www.mitterbaur.at">
    <meta name="keywords" content="EEG Status, Summensaldo">
    <title>EEG {{eeg_name}} Status</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
        .chart-container {
            margin-top: 40px;
            width: 80%;
            height: 40%;
        }
    </style>
</head>
<body>
    <center>
    <h1>EEG {{eeg_name}} Status</h1>
    Datensatz von {{ zeit }}
    <div class="status">
        <p><h1>Summensaldo: {{ summensaldo }} Watt</h1></p>      
        <canvas id="fifoChart"></canvas>        
    <script>
        const ctx = document.getElementById('fifoChart').getContext('2d');
        const fifoData = {{ fifo_summensaldo | tojson }};
        // Labels: 0 für aktuellen Wert, -1 für eine Minute zuvor usw.
        const labels = fifoData.map((_, index) => -(fifoData.length - 1 - index));

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Summensaldo Mittelwerte der letzten Stunde',
                    pointRadius: 1,
                    data: fifoData,
                    borderColor: 'rgba(191, 22, 22, 1)',
                    backgroundColor: 'rgba(191, 22, 22, 0.2)',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Minuten'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Watt'
                        }
                    }
                }
            }
        });
    </script>
    </div>
    <div class="status">
        <p><strong>Online Teilnehmer:</strong> {{ online }}</p>
        <p><strong>Offline Teilnehmer:</strong> {{ offline }}</p>
    </div>
    </center>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def get_status():
    return render_template_string(HTML_TEMPLATE, eeg_name=eeg_name, summensaldo=summensaldo, online=online, offline=offline, zeit=zeit,
            fifo_summensaldo=list(fifo_summensaldo))

def start_mqtt():
    mqtt_thread = threading.Thread(target=mqtt_loop)
    mqtt_thread.daemon = True
    mqtt_thread.start()

def start_schedule():
    schedule_thread = threading.Thread(target=schedule_loop)
    schedule_thread.daemon = True
    schedule_thread.start()

if __name__ == '__main__':
    #Auch das Flask Log deaktivieren, wenn in der config.ini das Logging deaktiviert ist
    if log==0:
        flasklog = logging.getLogger('werkzeug')
        flasklog.disabled = True
    
    start_mqtt()
    start_schedule()
    app.run(host=http_ip, port=http_port)
