import serial

from naganami_mqtt.awsiot import AwsIotContoller
import json

import logging
logger = logging.getLogger('naganami_mqtt')

class Kiyoshimo(AwsIotContoller):
    pass

if __name__ == '__main__':
    from naganami_mqtt.awsiot import getAwsCredentialFromJson
    credential = getAwsCredentialFromJson('/aws/iot.json')
    kiyoshimo = Kiyoshimo(credential)

    kiyoshimo.loop(block=False)


    ser = serial.Serial('/dev/ttyAMA0', 115200)

    while True:
        l = ser.readline()
        if l[0] == 58 and l[-2:] == b"\r\n":
            line = l.strip()[1:].decode()
            deviceSerial = line[14:22]
            dataLength = int(line[36:38], 16)
            data = int(line[-4-dataLength:-4], 16)
            print(deviceSerial+":"+str(data))

            kiyoshimo.publish_status(deviceSerial, json.dumps({"deviceSerial": deviceSerial, "data": data}))
