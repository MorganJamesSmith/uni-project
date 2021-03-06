"""
implements a wrapper for loading live data from the serial connection and passing it to plotting
"""
import serial
import time
import struct
import plotly.express as px
try:
    from . import log_parser
except ImportError:
    import log_parser
# TODO: clean up CLI code
class LiveLogFile():
    def __init__(self, serial_device_name: str="/dev/ttyACM0", initial_file_offset = -1,
                 callback_to_call_right_before_grabbing_new_data=lambda:None,
                 callback_to_call_when_caught_up_with_data=lambda:time.sleep(1)):
        self.serial_device_name = serial_device_name
        self.internal_buffer: bytes = b""
        self.log_file_offset: int = initial_file_offset
        self.sleep_callback = callback_to_call_when_caught_up_with_data
        self.before_serial_hook = callback_to_call_right_before_grabbing_new_data

    def read(self, nbytes=1):
        if len(self.internal_buffer) < nbytes:
            new_data = self.read_from_device()
            self.internal_buffer  = self.internal_buffer + new_data
            if len(self.internal_buffer) < nbytes:
                import warnings
                warnings.warn("reading data from device didn't produce enough content to keep going.")
        togive = self.internal_buffer[:nbytes]
        self.internal_buffer = self.internal_buffer[nbytes:]
        return togive

    def read_from_device(self):
        self.before_serial_hook()
        with serial.Serial(self.serial_device_name) as conn:
            if self.log_file_offset == -1:
                self.set_offset_to_last_reset(conn)
            print("READING FROM DEVICE")
            command_to_send = f"hcat P21 {self.log_file_offset}\n\r".encode()
            hex_data = self.interact_command(conn, command_to_send)
            # if len(hex_data) < 20:
            #     print(f"small data: {hex_data!r}")
            if hex_data == "" or hex_data.isspace(): # only \n\r
                # we have caught up with live data, need to sleep for a bit
                self.sleep_callback()
                hex_data = self.interact_command(conn, command_to_send)
            result =  bytes.fromhex(hex_data)
            self.log_file_offset += len(result)
            return result
    def set_offset_to_last_reset(self, conn):
        """sets the current tracking offset to the last reset found"""
        data = bytes.fromhex(self.interact_command(conn,b"hcat P21_OFF\n\r"))
        # last reset is just the last 4 bytes
        assert len(data)%4 == 0, "length of P21_OFF is not a multiple of 32 bits"
        [last_reset_offset] = struct.unpack("I",data[-4:])
        self.log_file_offset = last_reset_offset
    @staticmethod
    def interact_command(conn, command):
        conn.write(command)
        data_we_just_sent_and_want_to_ignore = conn.read_until(b"\n\r")
        if command != data_we_just_sent_and_want_to_ignore:
            import warnings; warnings.warn(f"sent: {command!r} but saw back {data_we_just_sent_and_want_to_ignore!r}")
        hex_data = conn.read_until(b"> ")
        return hex_data.decode().rpartition("> ")[0]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", nargs="?",default="/dev/ttyACM0")
    ns = parser.parse_args()
    for [type, *fields] in log_parser.parse_data(log_parser.parse_raw_entries(LiveLogFile(ns.input_file))):
        if type != 4:
            continue # ignore all but IMU data
        print(*map("{:>8}".format, fields), sep=",")
