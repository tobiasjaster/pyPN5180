from pn5180 import PN5180
import sys
import time


if __name__ == '__main__':
    check_debug = sys.argv[1] if len(sys.argv) == 2 else ''
    debug = True if check_debug == '-v' else False

    pn5180 = PN5180.PN5180(bus=0, device=0, busy_pin=25, reset_pin=7)
    #recvBuffer = [0xFF, 0xFF]
    #reader.transceiveCommand([0x07,0x10,0x02],recvBuffer)
    recvBuffer = pn5180.read_eeprom(0x10, 2)
    print(recvBuffer)
    del pn5180

