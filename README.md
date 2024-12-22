In einer kleinen EEG möchten die Teilnehmer wissen, ob gerade ein Leistungsüberschuss besteht. 
Ich nahm mich dem Thema an und erstellte eine Python Demo-Anwendung. 
Jeder EEG AMIS Lesekopf überträgt auf einen MQTT Broker z.B. jede zehn Sekunden den Saldo, der Summensaldo wird auf einer Webseite angezeigt. Die Teilnehmer einer EEG können somit in Echtzeit sehen, ob in der EEG ein Leistungsüberschuss besteht. Ebenso werden EEG-Teilnehmer angezeigt, die über zwei Minuten keinen Datensatz mehr übertragen haben. 
Meine Lösung basiert auf einem Raspberry Pi (ab 1. Generation; Lan Port) mit installiertem Mosquitto MQTT Broker. Die Python Anwendung erstellt die Webseite und eine Logdatei. Es ist weiters eine öffentliche IPv4 mit Weiterleitungen der Ports für MQTT und Webseite auf den Raspberry notwendig.

![amis_eeg](https://github.com/user-attachments/assets/5c83e486-9095-4d77-89ee-306589424393)
