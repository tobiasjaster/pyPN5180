from enum import Enum
import logging
import time
from typing import (
    Any,
    Optional,
    Union
)
from . import PN5180
try:
    from RPi import GPIO
except:
    pass


LOGGER = logging.getLogger(__name__)


def calc_crc16(data):
    crc16 = 0xFFFF
    for i in range(0, len(data)):
        crc16new = crc16>>8 | (crc16&0xFF)<<8
        crc16new = crc16new^(data[i]&0xFF)
        crc16new = crc16new^((crc16new&0xFF)>>4)
        crc16new = crc16new^(((crc16new&0xFFFF)<<12)&0xFFFF)
        crc16new = crc16new^(((crc16new&0xFF)<<5)&0xFFFF)
        crc16    = crc16new
    return crc16


class PN5180_SFD_OPCODE(Enum):
    DEFAULT           = 0x00
    RESET             = 0xF0
    GET_VERSION       = 0xF1
    GET_SESSION_STATE = 0xF2
    GET_DIE_ID        = 0xF4
    CHECK_INTEGRITY   = 0xE0
    SECURE_WRITE      = 0xC0
    READ              = 0xA2


class PN5180_SFD_STATE(Enum):
    OK                      = 0x00
    INVALID_ADDR            = 0x01
    UNKNOW_CMD              = 0x0B
    ABORTED_CMD             = 0x0C
    PLL_ERROR               = 0x0D
    ADDR_RANGE_OFL_ERROR    = 0x1E
    BUFFER_OFL_ERROR        = 0x1F
    MEM_BSY                 = 0x20
    SIGNATURE_ERROR         = 0x21
    FIRMWARE_VERSION_ERROR  = 0x24
    PROTOCOL_ERROR          = 0x28
    SFWU_DEGRADED           = 0x2A
    STATUS_DL_FIRST_CHUNK   = 0x2D
    STATUS_DL_NEXT_CHUNK    = 0x2E
    STATUS_INTERNAL_ERROR_5 = 0xC5
    DEFAULT                 = 0xFF


class PN5180_SECURE_MESSAGE_DIRECTION(Enum):
    SEND                    = 0x7F
    RECEIVE                 = 0xFF


class PN5180_SECURE_MESSAGE_HEADER:
    def __init__(self):
        self.rfu = 0
        self.ch = 0
        self.pkg_length = 0

    def __iter__(self):
        calc = (self.rfu<<11)+(self.ch<<10)+self.pkg_length
        return iter([(calc>>(8*i))&0xff for i in range(1,-1,-1)])

    def __len__(self):
        return len(list(self.__iter__()))

    @property
    def rfu(self) -> int:
        return self._rfu

    @rfu.setter
    def rfu(self, value: int) -> None:
        if value&0x1F != value:
            raise ValueError("RFU size is only 5Bit!")
        self._rfu = value

    @property
    def ch(self) -> bool:
        return bool(self._ch)

    @ch.setter
    def ch(self, last_frame: bool) -> None:
        self._ch = int(last_frame)

    @property
    def pkg_length(self) -> int:
        return self._pkg_length

    @pkg_length.setter
    def pkg_length(self, value: int) -> None:
        if value&0x3FF != value or value > 256:
            raise ValueError("pkg_length size is only 10Bit and under 256!")
        self._pkg_length = value

    @classmethod
    def create_from_list(cls, value: list):
        header = PN5180_SECURE_MESSAGE_HEADER()
        header.rfu = value[0]>>3
        header.ch = (value[0]>>2)&0x01
        header.pkg_length = (value[0]&0x3)<<8 + value[1]
        return header


class PN5180_SECURE_MESSAGE_SEND_FRAME:
    def __init__(self):
        self.opcode: PN5180_SFD_OPCODE = PN5180_SFD_OPCODE.DEFAULT
        self.firmwar_version = []
        self.payload = []

    def __iter__(self):
        return iter([self.opcode.value] + self.firmwar_version + self.payload)

    def __len__(self):
        return len(list(self.__iter__()))

    @property
    def opcode(self) -> PN5180_SFD_OPCODE:
        return self._opcode

    @opcode.setter
    def opcode(self, value: PN5180_SFD_OPCODE) -> None:
        self._opcode = value

    @property
    def firmware_version(self) -> list:
        return self._firmware_version

    @firmware_version.setter
    def firmware_version(self, value: Any) -> None:
        if isinstance(value, list) and len(value) == 3:
            self._firmware_version = value
        elif isinstance(value, str) and len(value.split('.')) == 2:
            self._firmware_version = list([0x00] + value.split('.'))
        elif value == [] or value is None:
            self._firmware_version = []
        else:
            raise ValueError('Value has not a supported format!')

    @property
    def payload(self) -> list:
        return self._payload

    @payload.setter
    def payload(self, value: list) -> None:
        self._payload = value

    @classmethod
    def create_from_list(cls, value: list):
        frame = PN5180_SECURE_MESSAGE_SEND_FRAME()
        try:
            frame.opcode = PN5180_SFD_OPCODE(value[0])
        except:
            print(value)
            raise ValueError("Value is not a valid OPCODE!")
        frame.payload = value[1:]
        return frame


class PN5180_SECURE_MESSAGE_RECEIVE_FRAME:
    def __init__(self):
        self.state: PN5180_SFD_STATE = PN5180_SFD_STATE.DEFAULT
        self.payload = []

    def __iter__(self):
        return iter([self.state.value] + self.payload)

    def __len__(self):
        return len(list(self.__iter__()))

    @property
    def state(self) -> PN5180_SFD_STATE:
        return self._state

    @state.setter
    def state(self, value: PN5180_SFD_STATE) -> None:
        self._state = value

    @property
    def payload(self) -> list:
        return self._payload

    @payload.setter
    def payload(self, value: list) -> None:
        self._payload = value

    @classmethod
    def create_from_list(cls, value: list):
        frame = PN5180_SECURE_MESSAGE_RECEIVE_FRAME()
        try:
            frame.state = PN5180_SFD_STATE(value[0])
        except:
            print(value)
            raise ValueError("Value is not a valid STATE!")
        frame.payload = value[1:]
        return frame


class PN5180_SECURE_MESSAGE:
    def __init__(self):
        self.dir_byte: Optional[PN5180_SECURE_MESSAGE_DIRECTION] = None
        self.header: Optional[PN5180_SECURE_MESSAGE_HEADER] = None
        self.frame: Optional[Union[PN5180_SECURE_MESSAGE_SEND_FRAME, PN5180_SECURE_MESSAGE_RECEIVE_FRAME]] = None
        self.crc = None

    def __iter__(self):
        if self.header is None:
            raise RuntimeError("Header is not defined!")
        if self.frame is None:
            raise RuntimeError("Frame is not defined!")
        self.crc = self.calc_crc16()
        return iter([self.dir_byte.value] + list(self.header) + list(self.frame) + self.crc)

    def __len__(self):
        return len(list(self.__iter__()))

    @property
    def crc(self) -> list:
        return self._crc

    @crc.setter
    def crc(self, value: Optional[list]) -> None:
        if value is not None and len(value) != 2:
            raise ValueError('CRC Value is not valid!')
        self._crc = value
        
    def calc_crc16(self) -> list:
        data = list(self.header) + list(self.frame)
        crc16 = calc_crc16(data)
        return [(crc16>>(8*i))&0xff for i in range(1,-1,-1)]

    @classmethod
    def create_message_from_list(cls, value: list):
        message = PN5180_SECURE_MESSAGE()
        try:
            message.dir_byte = PN5180_SECURE_MESSAGE_DIRECTION(value[0])
        except:
            print(value)
            raise ValueError("Value is not a valid Message!")
        message.header = PN5180_SECURE_MESSAGE_HEADER.create_from_list(value[1:3])
        if message.dir_byte == PN5180_SECURE_MESSAGE_DIRECTION.SEND:
            message.frame = PN5180_SECURE_MESSAGE_SEND_FRAME.create_from_list(value[3:-2])
        else:
            message.frame = PN5180_SECURE_MESSAGE_RECEIVE_FRAME.create_from_list(value[3:-2])
        if value[-2:] != message.calc_crc16():
            raise RuntimeError(f'CRC of value {value[-2:]} doesn\'t match calculation {message.calc_crc16()}')
        message.crc = value[-2:]
        return message

    @classmethod
    def create_send_message(cls, opcode: PN5180_SFD_OPCODE, payload: list, cn: bool = False):
        frame = PN5180_SECURE_MESSAGE_SEND_FRAME()
        frame.opcode = opcode
        frame.payload = payload
        if len(frame) > 256:
            raise RuntimeError('Frame is larger then one message!')
        header = PN5180_SECURE_MESSAGE_HEADER()
        header.ch = cn
        header.pkg_length = len(frame)
        message = PN5180_SECURE_MESSAGE()
        message.dir_byte = PN5180_SECURE_MESSAGE_DIRECTION.SEND
        message.header = header
        message.frame = frame
        message.crc = message.calc_crc16()
        return message

    @classmethod
    def create_receive_message(cls, state: PN5180_SFD_STATE, payload: list, cn: bool = False):
        frame = PN5180_SECURE_MESSAGE_RECEIVE_FRAME()
        frame.state = state
        frame.payload = payload
        if len(frame) > 256:
            raise RuntimeError('Frame is larger then one message!')
        header = PN5180_SECURE_MESSAGE_HEADER()
        header.ch = cn
        header.pkg_length = len(frame)
        message = PN5180_SECURE_MESSAGE()
        message.dir_byte = PN5180_SECURE_MESSAGE_DIRECTION.RECEIVE
        message.header = header
        message.frame = frame
        message.crc = message.calc_crc16()
        return message


class PN5180_FIRMWARE:

    def __init__(self, pn5180: PN5180.PN5180):
        self.pn5180 = pn5180
        self.sfd_mode_active = False

    def _wait_write_ready(self):
        LOGGER.debug("Check Card Ready")
        if GPIO.input(self.pn5180._pins.busy):
            LOGGER.debug("Card Not Ready - Waiting for Busy Low")
            GPIO.wait_for_edge(self.pn5180._pins.busy, GPIO.FALLING, timeout=10)
            LOGGER.debug("Card Ready, continuing conversation.")

    def _wait_read_ready(self):
        LOGGER.debug("Check Card Ready")
        if not GPIO.input(self.pn5180._pins.busy):
            LOGGER.debug("Card Not Ready - Waiting for Busy Low")
            GPIO.wait_for_edge(self.pn5180._pins.busy, GPIO.RISING, timeout=10)
            LOGGER.debug("Card Ready, continuing conversation.")

    def _send(self, bytes: list):
        self._wait_write_ready()
        if self.pn5180._spi.spi.no_cs is True:
            GPIO.output(self.pn5180._pins.cs, GPIO.LOW)
            self.pn5180._spi.spi.xfer(bytes)
            GPIO.output(self.pn5180._pins.cs, GPIO.HIGH)
        else:
            self.pn5180._spi.spi.writebytes(bytes)
        LOGGER.debug(f"Sent Buffer: {bytes}")

    def _read(self, length):
        self._wait_read_ready()
        if self.pn5180._spi.spi.no_cs is True:
            GPIO.output(self.pn5180._pins.cs, GPIO.LOW)
            recvBuffer = self.pn5180._spi.spi.xfer([0xff]*length)
            GPIO.output(self.pn5180._pins.cs, GPIO.HIGH)
        else:
            recvBuffer = self.pn5180._spi.spi.readbytes(length)
        LOGGER.debug(f"Read Buffer: {recvBuffer}")
        return recvBuffer
    
    def start_sfd_mode(self):
        if self.pn5180._pins.req is None:
            raise RuntimeError("REQ Pin not defined!")
        GPIO.output(self.pn5180._pins.reset, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(self.pn5180._pins.req, GPIO.HIGH)
        time.sleep(.2)
        GPIO.output(self.pn5180._pins.reset, GPIO.LOW)
        time.sleep(.5)
        self.sfd_mode_active = True
    
    def stop_sfd_mode(self):
        if self.pn5180._pins.req is None:
            raise RuntimeError("REQ Pin not defined!")
        GPIO.output(self.pn5180._pins.reset, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(self.pn5180._pins.req, GPIO.LOW)
        time.sleep(.2)
        GPIO.output(self.pn5180._pins.reset, GPIO.LOW)
        time.sleep(.5)
        self.sfd_mode_active = False

    def secure_command_transceive(self, cmd_message: PN5180_SECURE_MESSAGE, resp_message: PN5180_SECURE_MESSAGE):
        if not self.sfd_mode_active:
            raise RuntimeError('Please activate SFD Mode!')
        self._send(list(cmd_message))
        if cmd_message.frame.opcode == PN5180_SFD_OPCODE.RESET:
            return True
        recv_buffer_header = self._read(3)
        resp_message.dir_byte = PN5180_SECURE_MESSAGE_DIRECTION(recv_buffer_header[0])
        resp_message.header = PN5180_SECURE_MESSAGE_HEADER.create_from_list(recv_buffer_header[1:])
        recv_buffer_frame = self._read(resp_message.header.pkg_length + 2)
        resp_message.frame = PN5180_SECURE_MESSAGE_RECEIVE_FRAME()
        resp_message.frame.state = PN5180_SFD_STATE(recv_buffer_frame[0])
        resp_message.frame.payload = recv_buffer_frame[1:-2]
        resp_message.crc = recv_buffer_frame[-2:]
        crc16 = resp_message.calc_crc16()
        if crc16 != resp_message.crc:
            print(recv_buffer_header)
            print(recv_buffer_frame)
            raise RuntimeError(f'CRC of ReceiveBuffer {recv_buffer[-2:]} doesn\'t match calculation {resp_message.crc}')
        return True

    def get_version(self, major, minor):
        print('get_version')
        tx_message = PN5180_SECURE_MESSAGE.create_send_message(PN5180_SFD_OPCODE.GET_VERSION, [0x00, 0x00, 0x00])
        rx_message = PN5180_SECURE_MESSAGE()
        self.secure_command_transceive(tx_message, rx_message)
        print(f'[get_version] - state: {rx_message.frame.state}')
        major, minor = rx_message.frame.payload[8], rx_message.frame.payload[9]
        print(f'[get_version] - major.minor: {major}.{minor}')




if __name__ in '__main__':
    data = [0x00, 0x04, 0xF1, 0x00, 0x00, 0x00]
    crc16 = calc_crc16(data)
    print(crc16)
    print([(crc16>>(8*i))&0xff for i in range(1,-1,-1)])
    header = PN5180_SECURE_MESSAGE_HEADER()
    print(len(header))