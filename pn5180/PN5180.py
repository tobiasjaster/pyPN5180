import collections
from enum import Enum
import logging
import spidev
import time
from RPi import GPIO


class PN5180_REG(Enum):
    SYSTEM_CONFIG      = 0x00
    IRQ_ENABLE         = 0x01
    IRQ_STATUS         = 0x02
    IRQ_CLEAR          = 0x03
    TRANSCEIVE_CONTROL = 0x04
    TIMER1_RELOAD      = 0x0C
    TIMER1_CONFIG      = 0x0F
    RX_WAIT_CONFIG     = 0x11
    CRC_RX_CONFIG      = 0x12
    RX_STATUS          = 0x13
    TX_WAIT_CONFIG     = 0x17
    TX_CONFIG          = 0x18
    CRC_TX_CONFIG      = 0x19
    RF_STATUS          = 0x1D
    SYSTEM_STATUS      = 0x24
    TEMP_CONTROL       = 0x25
    AGC_REF_CONFIG     = 0x26


class PN5180_CMD(Enum):
    WRITE_REGISTER          = 0x00
    WRITE_REGISTER_OR_MASK  = 0x01
    WRITE_REGISTER_AND_MASK = 0x02
    WRITE_REGISTER_MULTIPLE = 0x03
    READ_REGISTER           = 0x04
    READ_REGISTER_MULTIPLE  = 0x05
    WRITE_EEPROM            = 0x06
    READ_EEPROM             = 0x07
    WRITE_TX_DATA           = 0x08
    SEND_DATA               = 0x09
    READ_DATA               = 0x0A
    SWITCH_MODE             = 0x0B
    MIFARE_AUTHENTICATE     = 0x0C
    LOAD_RF_CONFIG          = 0x11
    UPDATE_RF_CONFIG        = 0x12
    RETRIEVE_RF_CONFIG_SIZE = 0x13
    RETRIEVE_RF_CONFIG      = 0x14
    RF_ON                   = 0x16
    RF_OFF                  = 0x17


class PN5180_TRANSCEIVE_STATE(Enum):
    IDLE                    = 0x00
    WAIT_TRANSMIT           = 0x01
    TRANSMITTING            = 0x02
    WAIT_RECEIVE            = 0x03
    WAIT_FOR_DATA           = 0x04
    RECEIVING               = 0x05
    LOOPBACK                = 0x06
    RESERVED                = 0x07


KEY = collections.namedtuple('Key', ['bus', 'device'])
MAPPING = {KEY(bus=0, device=0):8, KEY(bus=0, device=1):7, KEY(bus=1, device=0):26}
LOGGER = logging.getLogger(__name__)


class PN5180_PIN:

    def __init__(self, **kwargs):
        self.cs = None
        self.reset = None
        self.req = None
        self.busy = None
        if 'cs_pin' in kwargs:
            self.cs = kwargs['cs_pin']
        if 'reset_pin' in kwargs:
            self.reset = kwargs['reset_pin']
        if 'req_pin' in kwargs:
            self.req = kwargs['req_pin']
        if 'busy_pin' in kwargs:
            self.busy = kwargs['busy_pin']
        self.initialized = False
    
    def __del__(self):
        if self.initialized:
            self.deinit_gpio()

    def calc_cs(self, bus, device):
        self.cs = MAPPING.get(KEY(bus=bus, device=device))

    def init_gpio(self):
        GPIO.setmode(GPIO.BCM)
        if self.busy is not None:
            GPIO.setup(self.busy, GPIO.IN)
        if self.cs is not None:
            GPIO.setup(self.cs, GPIO.OUT)
            GPIO.output(self.cs, GPIO.HIGH)
        if self.reset is not None:
            GPIO.setup(self.reset, GPIO.OUT)
            GPIO.output(self.reset, GPIO.HIGH)
        if self.req is not None:
            GPIO.setup(self.req, GPIO.OUT)
            GPIO.output(self.req, GPIO.LOW)
        self.initialized = True

    def deinit_gpio(self):
        if self.cs is not None:
            GPIO.setup(self.cs, GPIO.IN)
        if self.reset is not None:
            GPIO.setup(self.reset, GPIO.IN)
        if self.req is not None:
            GPIO.setup(self.req, GPIO.IN)
        self.initialized = False


class PN5180_SPI:
    def __init__(self, bus: int = 0, device: int = 0, **kwargs):
        self.spi = spidev.SpiDev(bus, device)
        if 'speed' in kwargs:
            self.set_speed(kwargs['speed'])
        if 'no_cs' in kwargs:
            self.set_no_cs(kwargs['no_cs'])
        if 'mode' in kwargs:
            self.set_mode(kwargs['mode'])

    def __del__(self):
        self.spi.close()

    def set_speed(self, speed: int = 0):
        self.spi.max_speed_hz = speed

    def set_no_cs(self, no_cs: bool = False):
        self.spi.no_cs = no_cs

    def set_mode(self, mode: int = 0):
        self.spi.mode = mode


class PN5180:
    def __init__(self, bus: int = 0, device: int = 0, **kwargs):
        self._spi = PN5180_SPI(bus, device, speed=7000000, no_cs=True, mode=0)
        self._pins = PN5180_PIN(**kwargs)
        self._pins.calc_cs(bus, device)
        self._pins.init_gpio()

    def __del__(self):
        del self._spi
        del self._pins

    def _wait_ready(self):
        LOGGER.debug("Check Card Ready")
        if GPIO.input(self._pins.busy):
            LOGGER.debug("Card Not Ready - Waiting for Busy Low")
            GPIO.wait_for_edge(self._pins.busy, GPIO.FALLING, timeout=10)
            LOGGER.debug("Card Ready, continuing conversation.")

    def _wait_ready_loop(self):
        LOGGER.debug("Check Card Ready")
        while GPIO.input(self._pins.busy):
            pass
        LOGGER.debug("Card Ready, continuing conversation.")

    def _send(self, bytes: list):
        self._wait_ready()
        if self._spi.spi.no_cs is True:
            GPIO.output(self._pins.cs, GPIO.LOW)
            self._spi.spi.xfer(bytes)
            GPIO.output(self._pins.cs, GPIO.HIGH)
        else:
            self._spi.spi.writebytes(bytes)
        self._wait_ready()
        LOGGER.debug(f"Sent Buffer: {bytes}")

    def _read(self, length):
        self._wait_ready()
        if self._spi.spi.no_cs is True:
            GPIO.output(self._pins.cs, GPIO.LOW)
            recvBuffer = self._spi.spi.xfer([0xff]*length)
            GPIO.output(self._pins.cs, GPIO.HIGH)
        else:
            recvBuffer = self._spi.spi.readbytes(length)
        self._wait_ready()
        LOGGER.debug(f"Read Buffer: {recvBuffer}")
        return recvBuffer
        
    def reset(self):
        LOGGER.debug("Reset PN5180")
        if self._pins.reset is not None:
            GPIO.output(self._pins.reset, GPIO.LOW)
            time.sleep(1)
            GPIO.output(self._pins.reset, GPIO.HIGH)
            time.sleep(.5)

    def transceiveBuffer(self, sendBuffer: list, recvBuffer: list = []):
        self._send(sendBuffer)
        if len(recvBuffer) == 0:
            return True
        recvBuffer = self._read(len(recvBuffer))
        return True

    def transceive(self, cmd, address, content: list, length: int = 0):
        self._send([cmd, address] + list(content))
        if length == 0:
            return None
        return self._read(length)

    def write_register(self, address, content: list):
        self.transceive(PN5180_CMD.WRITE_REGISTER.value, address, content)

    def write_register_or_mask(self, address, mask: int):
        content = [(mask>>(8*i))&0xff for i in range(0,4,1)]
        self.transceive(PN5180_CMD.WRITE_REGISTER_OR_MASK.value, address, content)

    def write_register_and_mask(self, address, mask: int):
        content = [(mask>>(8*i))&0xff for i in range(0,4,1)]
        self.transceive(PN5180_CMD.WRITE_REGISTER_AND_MASK.value, address, content)

    def read_register(self, address, length):
        return self.transceive(PN5180_CMD.READ_REGISTER.value, address, [], length)

    def write_eeprom(self, address, content):
        if address > 254:
            raise ValueError("Writing beyond address 254!")
        self.transceive(PN5180_CMD.WRITE_EEPROM.value, address, content)

    def read_eeprom(self, address, length):
        if address > 254 or (address + length) > 254:
            raise ValueError("Reading beyond address 254!")
        return self.transceive(PN5180_CMD.READ_EEPROM.value, address, [length], length)

    def write_tx_data(self, content):
        self._send([PN5180_CMD.WRITE_TX_DATA.value] + list(content))

    def send_data(self, content, validBits):
        if len(content) > 260:
            raise ValueError("send_data with more than 260 bytes is not supported!")
        self.write_register_and_mask(PN5180_REG.SYSTEM_CONFIG.value, 0xfffffff8) # Idle/StopCom Command
        self.write_register_or_mask(PN5180_REG.SYSTEM_CONFIG.value, 0x00000003)  # Transceive Command
        return self._send([PN5180_CMD.SEND_DATA.value, validBits] + list(content))

    def get_transceiver_state(self):
        value = self.read_register(PN5180_REG.RF_STATUS.value, 4)
        state = sum([value[i]<<(8*i) for i in range(0,4,1)])
        transceiver_state = state>>24&0x07
        return PN5180_TRANSCEIVE_STATE(transceiver_state)
