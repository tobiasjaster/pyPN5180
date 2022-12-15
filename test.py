from pn5180 import PN5180, PN5180_Firmware
import sys
import time
import logging

LOGGER = logging.getLogger(__name__).setLevel(logging.DEBUG)

if __name__ == '__main__':
    check_debug = sys.argv[1] if len(sys.argv) == 2 else ''
    debug = True if check_debug == '-v' else False

    pn5180 = PN5180.PN5180(bus=0, device=0, busy_pin=25, reset_pin=7, req_pin=24)
    recvBuffer = pn5180.read_eeprom(0x10, 2)
    print(recvBuffer)
    pn5180_firmware = PN5180_Firmware.PN5180_FIRMWARE(pn5180)
    pn5180_firmware.start_sfd_mode()
    major = 0
    minor = 0
    pn5180_firmware.get_version(major, minor)
    pn5180_firmware.stop_sfd_mode()
    del pn5180_firmware
    del pn5180 

