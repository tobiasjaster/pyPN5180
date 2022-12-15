from pn5180 import PN5180, PN5180ISO15693
import sys
import time


if __name__ == '__main__':
    check_debug = sys.argv[1] if len(sys.argv) == 2 else ''
    debug = True if check_debug == '-v' else False

    reader = PN5180.PN5180(bus=0, device=0, busy_pin=25, reset_pin=7)
    pn5180_15693 = PN5180ISO15693.PN5180ISO15693(reader)
    while True:
        cards = pn5180_15693.inventory()
        print(f"{len(cards)} card(s) detected: {' - '.join(cards)}")
        time.sleep(.4)
