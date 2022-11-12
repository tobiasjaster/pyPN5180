import pytest
from types import ModuleType
from unittest.mock import patch, MagicMock

class SPI_MOCK:

    def __init__(self):
        self.max_speed_hz = 0
        self.no_cs = False
        self.mode = 0
        self._return_bytes = []

    def set_return_bytes(self, content):
        self._return_bytes = content

    def xfer(self, *args):
        return self._return_bytes

    def writebytes(self, *args):
        pass

    def readbytes(self):
        return self._return_bytes

    def close(self):
        pass


spi = MagicMock()
rpi = ModuleType('RPi')
rpi.GPIO = MagicMock()

with patch.dict('sys.modules', {
    'spidev': spi,
    'RPi': rpi,
}):
    import pn5180.PN5180 as PN5180

def test_PN5180_PIN_class():
    pn5180_pin = PN5180.PN5180_PIN()
    assert pn5180_pin.busy is None
    assert pn5180_pin.cs is None
    assert pn5180_pin.reset is None
    assert pn5180_pin.req is None

    pn5180_pin = PN5180.PN5180_PIN(busy_pin=1, cs_pin=2, reset_pin=3, req_pin=4)
    assert pn5180_pin.busy == 1
    assert pn5180_pin.cs == 2
    assert pn5180_pin.reset == 3
    assert pn5180_pin.req == 4

    pn5180_pin.calc_cs(1,1)
    assert pn5180_pin.cs is None

    pn5180_pin.calc_cs(0,1)
    assert pn5180_pin.cs == 7

    pn5180_pin.calc_cs(1,0)
    assert pn5180_pin.cs == 26

    pn5180_pin.calc_cs(0,0)
    assert pn5180_pin.cs == 8

    pn5180_pin.init_gpio()
    assert pn5180_pin.initialized is True

    pn5180_pin.deinit_gpio()
    assert pn5180_pin.initialized is False


def test_PN5180_SPI_class():
    spi.SpiDev.return_value = SPI_MOCK()
    pn5180_spi = PN5180.PN5180_SPI()
    assert pn5180_spi.spi.max_speed_hz == 0
    assert pn5180_spi.spi.no_cs is False
    assert pn5180_spi.spi.mode == 0

    spi.SpiDev.return_value = SPI_MOCK()
    pn5180_spi = PN5180.PN5180_SPI(speed=7000000, no_cs=True, mode=3)
    assert pn5180_spi.spi.max_speed_hz == 7000000
    assert pn5180_spi.spi.no_cs is True
    assert pn5180_spi.spi.mode == 3


def test_PN5180_class():
    spi.SpiDev.return_value = SPI_MOCK()
    pn5180 = PN5180.PN5180()
    assert isinstance(pn5180._spi.spi, SPI_MOCK)
    assert pn5180._pins.cs == 8
    assert pn5180._pins.initialized is True

    spi.SpiDev.return_value = SPI_MOCK()
    pn5180 = PN5180.PN5180(bus=0, device=1, busy_pin=1, reset_pin=2, req_pin=3)
    assert isinstance(pn5180._spi.spi, SPI_MOCK)
    assert pn5180._pins.cs == 7
    assert pn5180._pins.busy == 1
    assert pn5180._pins.reset == 2
    assert pn5180._pins.req == 3
    assert pn5180._pins.initialized is True

def test_PN5180_transceiver_state():
    spi_mock = SPI_MOCK()
    spi_mock.set_return_bytes([0x44, 0x33, 0x22, 0x11])
    spi.SpiDev.return_value = spi_mock
    pn5180 = PN5180.PN5180(bus=0, device=1, busy_pin=1, reset_pin=2, req_pin=3)
    assert pn5180.get_transceiver_state() == PN5180.PN5180_TRANSCEIVE_STATE(1)
