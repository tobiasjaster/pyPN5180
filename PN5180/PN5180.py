import collections
import spidev
import time
import RPi.GPIO as GPIO

Key = collections.namedtuple('Key', ['bus', 'device'])
cs_mapping = {Key(bus=0, device=0):8, Key(bus=0, device=1):7, Key(bus=1, device=0):26}

class PN5180:
    def __init__(self, bus: int = 0, device: int = 0, busy_pin: int = None, reset_pin: int = None, debug=False, protocol='ISO15693'):
        self._spi = spidev.SpiDev(bus, device)
        self._spi.max_speed_hz = 7000000
        self._spi.no_cs = True
        self._spi.mode = 0
        self._cs_pin = cs_mapping.get(Key(bus=bus, device=device))
        self._busy_pin = busy_pin
        self._reset_pin = reset_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._busy_pin, GPIO.IN)  # GPIO 25 is the Busy pin (Header 22)
        GPIO.setup(self._cs_pin, GPIO.OUT)
        GPIO.output(self._cs_pin, GPIO.HIGH)
        GPIO.setup(self._reset_pin, GPIO.OUT)
        GPIO.output(self._reset_pin, GPIO.HIGH)
        # GPIO.setup(16, GPIO.OUT)  # GPIO 16 is "OK" led. run "echo none >/sys/class/leds/led0/trigger" as superuser to disable external triggers. Normally triggered by mmc0
        self.__debug = debug
        self.__protocol = protocol

    def __del__(self):
        self._spi.close()
        GPIO.cleanup()

    def __log(self, *args):
        if self.__debug:
            print(args)

    def reset(self):
        GPIO.output(self._reset_pin, GPIO.LOW)
        time.sleep(1)
        GPIO.output(self._reset_pin, GPIO.HIGH)
        time.sleep(.5)

    def transceiveCommand(self, sendBuffer: list, recvBuffer: list):
        self._wait_ready_loop()
        GPIO.output(self._cs_pin, GPIO.LOW)
        self._spi.xfer(sendBuffer)
#        self._wait_not_ready_loop()
        GPIO.output(self._cs_pin, GPIO.HIGH)
        self._wait_ready_loop()
        if len(recvBuffer) == 0:
            return True
        GPIO.output(self._cs_pin, GPIO.LOW)
        recvBuffer = self._spi.xfer(recvBuffer)
#        self._wait_not_ready_loop()
        GPIO.output(self._cs_pin, GPIO.HIGH)
        self._wait_ready_loop()
        return True

    def _wait_ready(self):
        self.__log("Check Card Ready")
        if GPIO.input(self._busy_pin):
            self.__log("Card Not Ready - Waiting for Busy Low")
            GPIO.wait_for_edge(self._busy_pin, GPIO.FALLING, timeout=10)
            self.__log("Card Ready, continuing conversation.")

    def _wait_not_ready(self):
        self.__log("Check Card not Ready")
        if not GPIO.input(self._busy_pin):
            self.__log("Card Ready - Waiting for Busy High")
            GPIO.wait_for_edge(self._busy_pin, GPIO.RISING, timeout=10)
            self.__log("Card not Ready, continuing conversation.")

    def _wait_ready_loop(self):
        self.__log("Check Card Ready")
        while GPIO.input(self._busy_pin):
            pass
        self.__log("Card Ready, continuing conversation.")

    def _wait_not_ready_loop(self):
        self.__log("Check Card not Ready")
        while GPIO.input(self._busy_pin) != 1:
            pass
        self.__log("Card not Ready, continuing conversation.")

    def _send(self, bytes: list):
        self._wait_ready()
        GPIO.output(self._cs_pin, GPIO.LOW)
        self._spi.xfer(bytes)
        GPIO.output(self._cs_pin, GPIO.HIGH)
        self.__log("Sent Frame: ", bytes)
        self._wait_ready()

    def _read(self, length):
        self._wait_ready()
        GPIO.output(self._cs_pin, GPIO.LOW)
        recvBuffer = self._spi.xfer([0xff]*length)
        GPIO.output(self._cs_pin, GPIO.HIGH)
        self._wait_ready()
        return recvBuffer

    def _send_string(self, string: str):
        msg_array = [ord(letter) for letter in string]
        self._send(msg_array)

    def transceive(self, cmd, address, content, length):
        self._send([cmd, address] + list(content))
        return self._read(length)

    def write_register(self, address, content):
        self._send([0x00, address] + list(content))

    def read_register(self, address, length):
        self._send([0x04, address])
        return self._read(length)

    def write_eeprom(self, address, content):
        self._send([0x06, address] + list(content))

    def read_eeprom(self, address, length):
        self._send([0x07, address, length])
        return self._read(length)

    def _card_has_responded(self):
        """
        The function CardHasResponded reads the RX_STATUS register, which indicates if a card has responded or not.
        Bits 0-8 of the RX_STATUS register indicate how many bytes where received.
        If this value is higher than 0, a Card has responded.
        :return:
        """
        result = self.read_register(0x13, 4)  # Read 4 bytes
        self.__log("Received", result)
        if result[0] > 0:
            self._bytes_in_card_buffer = result[0]
            return True
        return False

    def _inventory_iso15693(self):
        """
        Return UID when detected
        :return:
        """
        uids = []
        # https://www.nxp.com/docs/en/application-note/AN12650.pdf
        self._send([0x11, 0x0D, 0x8D])  # Loads the ISO 15693 protocol into the RF registers
        self._send([0x16, 0x00])  # Switches the RF field ON.
        self._send([0x00, 0x03, 0xFF, 0xFF, 0x0F, 0x00])  # Clears the interrupt register IRQ_STATUS
        self._send([0x02, 0x00, 0xF8, 0xFF, 0xFF, 0xFF])  # Sets the PN5180 into IDLE state
        self._send([0x01, 0x00, 0x03, 0x00, 0x00, 0x00])  # Activates TRANSCEIVE routine
        self._send([0x09, 0x00, 0x06, 0x01, 0x00])  # Sends an inventory command with 16 slots

        for slot_counter in range(0, 16):  # A loop that repeats 16 times since an inventory command consists of 16 time slots
            if self._card_has_responded():  # The function CardHasResponded reads the RX_STATUS register, which indicates if a card has responded or not.
                #GPIO.output(16, GPIO.LOW)
                self._send([0x0A, 0x00])  # Command READ_DATA - Reads the reception Buffer
                uid_buffer = self._read(self._bytes_in_card_buffer)  # We shall read the buffer from SPI MISO -  Everything in the reception buffer shall be saved into the UIDbuffer array.
                # uid_buffer = self._read(255)  # We shall read the buffer from SPI MISO
                self.__log(uid_buffer)
                # uid = uid_buffer[0:10]
                uids.append(uid_buffer)
            self._send([0x02, 0x18, 0x3F, 0xFB, 0xFF, 0xFF])  # Send only EOF (End of Frame) without data at the next RF communication.
            self._send([0x02, 0x00, 0xF8, 0xFF, 0xFF, 0xFF])  # Sets the PN5180 into IDLE state
            self._send([0x01, 0x00, 0x03, 0x00, 0x00, 0x00])  # Activates TRANSCEIVE routine
            self._send([0x00, 0x03, 0xFF, 0xFF, 0x0F, 0x00])  # Clears the interrupt register IRQ_STATUS
            self._send([0x09, 0x00])  # Send EOF
        self._send([0x17, 0x00])  # Switch OFF RF field
        #GPIO.output(16, GPIO.HIGH)
        return uids

    @staticmethod
    def _format_uid(uid):
        """
        Return a readable UID from a LSB byte array
        :param uid:
        :return:
        """
        uid_readable = list(uid)  # Create a copy of the original UID array
        uid_readable.reverse()
        uid_readable = "".join([format(byte, 'x').zfill(2) for byte in uid_readable])
        # print(f"UID: {uid_readable}")
        return uid_readable

    def inventory(self, raw=False):
        """
        Send inventory command for initialized protocol, returns a list of cards detected.
        'raw' parameter can be set to False to return the unstructured UID response from the card.
        :param raw:
        :return:
        """
        if self.__protocol == 'ISO15693':
            cards = self._inventory_iso15693()
            # print(f"{len(cards)} card(s) detected: {' - '.join([self._format_uid(card) for card in cards])}")
            if raw:
                return cards
            else:
                return [self._format_uid(card) for card in cards]
        else:
            NotImplementedError("Only ISO15693 is implemented as of now.")


