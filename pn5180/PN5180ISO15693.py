class PN5180ISO15693:
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