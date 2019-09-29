from logging import getLogger, DEBUG, Formatter
from logging.handlers import TimedRotatingFileHandler
logger = getLogger(__name__)
logger.setLevel(DEBUG)
handler = TimedRotatingFileHandler(
    '/var/log/kiyoshimo.log',
    when='d',
    backupCount=7,
    encoding='utf-8',
    utc=False
)
handler.setFormatter(Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)


from naganami_mqtt.awsiot import AwsIotContoller
import serial
import json

class Kiyoshimo(AwsIotContoller):
    pass
    sensors = {
        1: {
            'status': False,
            'sequenceNumber': None
        },
        2: {
            'status': False,
            'sequenceNumber': None
        }
    }

    def stat(self, result):
        if self.sensors[result['logicalID']]['sequenceNumber'] == result['sequenceNumber']:
            return

        before = self.sensors[result['logicalID']]['status']
        self.sensors[result['logicalID']]['status'] = self.is_open(result['HALLIC'])
        self.sensors[result['logicalID']]['sequenceNumber'] = result['sequenceNumber']

        if before != self.sensors[result['logicalID']]['status']:
            self.update()

    def update(self):
        status = {
            "sensors": self.sensors
        }
        self._shadow_update(status)

    @staticmethod
    def is_open(state):
        return bool(state & 0b11)


def toBytes(line):
    payload = []
    if isinstance(line, bytes):
        line = line.decode('ascii')

    if line[0] != ':' or line[-2:] != "\r\n":
        raise RuntimeError()

    payload = []
    for i in range(int((len(line)-3)/ 2)):
        payload.append(int(line[1 + i * 2:3 + i * 2], 16))

    return payload

def joinHex(l):
    r = 0
    l = l.copy()
    l.reverse()
    for i in range(len(l)):
        r += l[i] << i * 8
    return r

def joinStr(l):
    r = ''
    for x in l:
        r += '{0:02X}'.format(x)
    return r

def checkSum(l):
    r = 0
    for i in l:
        r = r + i & 0xff
    return r == 0

def parse(line):
    byteList = toBytes(line)
    result = {
        "raw": str(line)
    }

    if not checkSum(byteList):
        raise RuntimeError()

    result['routerSID'] = joinStr(byteList[0:4])
    result['Lqi'] = byteList[4]
    result['sequenceNumber'] = joinHex(byteList[5:7])
    result['endDeviceSID'] = joinStr(byteList[7:11])
    result['logicalID'] = byteList[11]
    result['sensorType'] = byteList[12]
    result['palVersion'] = byteList[13]
    dataCount = byteList[14]

    _cursor = 15
    _dataCount = 0
    sensorDatas = []
    for i in range(dataCount):
        _buf = {}
        _buf['dataType'] = byteList[_cursor]
        _buf['dataSource'] = byteList[_cursor + 1]
        _buf['exByte'] = byteList[_cursor + 2]
        _dataLange = byteList[_cursor + 3]
        _buf['data'] = joinHex(byteList[_cursor + 4:_cursor + 4 + _dataLange])
        _cursor += 4 + _dataLange

        if _buf['dataSource'] == 0x30:
            if _buf['exByte'] == 0x08:
                result['battery'] = _buf['data']
                continue
            elif _buf['exByte'] == 0x01:
                result['ADC1'] = _buf['data']
                continue
        elif _buf['dataSource'] == 0x00:
            result['HALLIC'] = _buf['data']
            continue
        sensorDatas.append(_buf)

    result['data'] = sensorDatas

    return result



if __name__ == '__main__':
    from naganami_mqtt.awsiot import getAwsCredentialFromJson
    import sys
    credential = getAwsCredentialFromJson('/aws/iot.json')
    kiyoshimo = Kiyoshimo(credential)

    kiyoshimo.loop(block=False)

    ser = serial.Serial('/dev/ttyAMA0', 115200)
    devices = {}

    try:
        while True:
            l = ser.readline()
            try:
                logger.debug(l)
                payload = parse(l)

                if devices.get(payload['endDeviceSID'], None) == payload['sequenceNumber']:
                    continue

                devices[payload['endDeviceSID']] = payload['sequenceNumber']

                kiyoshimo.publish_status(payload['endDeviceSID'], json.dumps(payload))

                if payload.get('HALLIC', None) is not None:
                    kiyoshimo.stat(payload)

            except Exception as e:
                logger.exception(e)

    except KeyboardInterrupt:
        sys.exit(0)

    except Exception as e:
        logger.exception(e)
