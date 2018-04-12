#!/usr/bin/env python

#
# Reads a vgm or vgz file and parses its contents. 
# The file must have extension either .vgm for uncompressed
# files or .vgz for compressed files. After opening the file it sends music 
# music data to serial port specified by first parameter. 
# USB speed is configured at 9600 bps by default.
#

import gzip
import struct
import os
import sys
import time
import serial

# Serial transmission speed. Must match bps set in Serial.begin(bps)
# at the 'vgm2149_vgm_player.ino' file.

#BAUD = 115200
BAUD = 57600
WAIT60TH = 1.0/60   # delay 60th frame
WAIT50TH = 1.0/50   # delay 50th frame


class VGMReader(object):

    def __parse_gd3_info(self):
        # See:
        # http://vgmrips.net/wiki/GD3_Specification
        #
        def readcstr():
            chars = []
            while True:
                c = self.__fd.read(2)
                # bytes(2) means two repetitions of value zero
                if c == bytes(2):
                    return ("".join(chars))
                chars.append(c.decode('utf-16'))

        # Seek to start of string data
        self.__fd.seek (self.__header['gd3_offset'] + 12)
        self.__header['track_name'] = readcstr()
        self.__header['track_name_jpn'] = readcstr()
        self.__header['game_name'] = readcstr()
        self.__header['game_name_jpn'] = readcstr()
        self.__header['system_name'] = readcstr()
        self.__header['system_name_jpn'] = readcstr()
        self.__header['author_name'] = readcstr()
        self.__header['author_name_jpn'] = readcstr()
        self.__header['date'] = readcstr()

    def __parse_header(self):
        # See:
        # http://vgmrips.net/wiki/VGM_Specification
        # 
        # Read from header offsets 0x00 to 0x20
        #
        vgm_header = '< 4s I I I I I I I'
        s = self.__fd.read(struct.calcsize(vgm_header))
        d = {}
        (d['id'],
         d['eof_offset'],
         d['version'],
         d['clk_sn76489'],
         d['clk_ym2413'],
         d['gd3_offset'],
         d['total_samples'],
         d['loop_offset'],
         ) = struct.unpack(vgm_header, s)

        # Store absolute offset of gd3_offset
        d['gd3_offset'] += 0x14

        # Read the relative offset to VGM data stream
        self.__fd.seek(0x34)
        s = self.__fd.read(4)
        # Store absolute offset (0x34 + vgm_data_offset)
        d['vgm_data_offset'] = struct.unpack('< I', s)[0] + 0x34

        # Store loop offset relative to vgm song data
        d['loop_offset'] += 0x1C - d['vgm_data_offset']

        # Seek to ay8910 clock info (absolute offset 0x74)
        self.__fd.seek(0x74)
        s = self.__fd.read (4)        
        d['clk_ay8910'] = struct.unpack('< I', s)[0]
        
        self.__header = d

        # In python3 everything we read from a binary file are bytes
        # so we need to decode these to str to show them correctly.
        d['id'] = d['id'].decode()

        # Get version in string format 'maj.min'
        d['str_version'] = self.__get_str_version()

        self.__parse_gd3_info()

    def __get_str_version (self):
        high, low = divmod (self.__header['version'], 0x100)
        str_version = format(high, 'x') + '.' + format(low, 'x')
        return str_version


    def __read_data_interleaved(self):
        cnt = self.__header['nb_frames']
        regs = [self.__fd.read(cnt) for i in range(16)]
        self.__data = [f for f in zip(*regs)]

    def __read_data(self):       
        cnt = self.__header['gd3_offset'] - self.__header['vgm_data_offset']
        self.__fd.seek(self.__header['vgm_data_offset'])
        self.__data = self.__fd.read(cnt)        

    def __init__(self, fd):
        self.__fd = fd
        self.__parse_header()
        self.__data = []

    def dump_header(self):
        print("\x1b[2J")
        for k in ('id', 'str_version', 'total_samples', 
                  'track_name', 'game_name', 'system_name','author_name', 'date'):
            print("\x1b[36;1m{:>20}\x1b[0m: \x1b[37;1m{}\x1b[0m".format(k, self.__header[k]))

        # Print sound chips used in this VGM file
        snd_chips = {
            'clk_sn76489' : 'SN_76489', 
            'clk_ym2413' : 'YM_2413', 
            'clk_ay8910' : 'AY_3_8910'
            }             
        str_chips = ""   
        for key, snd_chip in snd_chips.items():
            if self.__header[key]:
                str_chips += '[' + snd_chip + '] '
        print ("\x1b[36;1m{:>20}\x1b[0m: \x1b[37;1m{}\x1b[0m".format('Sound chip', str_chips))
    
    def dump_data(self):
        toHex = lambda x: "".join("{:02X} ".format(c) for c in x)
        print (toHex (self.__data))        
       
    def get_header(self):
        return self.__header

    def get_data(self):
        if not self.__data:
            self.__read_data()            
        return self.__data


def to_minsec(frames, frames_rate):
    secs = frames // frames_rate
    mins = secs // 60
    secs = secs % 60
    return (mins, secs)

def send_data(ser, data, current_pos, nbytes):
    #print(data[current_pos:current_pos+nbytes].hex())
    ser.write(data[current_pos:current_pos+nbytes])
    #print()

def vgm_play(data, header):

    samples_played = 0;
    song_min, song_sec = to_minsec(header['total_samples'], 44100)    

    with serial.Serial(sys.argv[1], BAUD) as ser:
        print("\n\x1b[33;1mIninitalizing USB serial...\x1b[0m", end='')
        time.sleep(2)  # Wait for Arduino reset
        frame_t = time.time()
        print("\x1b[32;1m Ok\x1b[0m")
        print("\x1b[31;1mPlaying...\x1b[0m")
        try:
            i = 0
            # Interpret vgm sound data until we read end of 
            # sound data (0x66)
            while (True):
                while data[i] != 0x66:

                    # 0xA0 aa dd: Write value dd to register aa
                    if data[i] == 0xA0:                    
                        send_data(ser, data, i, 3) # Send 3 bytes to USB serial: 'A0 aa dd'
                        i += 3
                
                    # 0x61 nn nn: Wait n samples, n from 0..65535 (approx 1.49 seconds)
                    elif data[i] == 0x61:
                        wait_value = struct.unpack('< H', data[i+1:i+3])[0]
                        samples_played += wait_value
                        #print(wait_value)
                        # Substract time spent in code
                        wait_value = 1.0 * wait_value / 44100 - (time.time() - frame_t)

                        time.sleep( wait_value if wait_value >= 0 else 0)                    
                        frame_t = time.time()                
                        i += 3

                    # 0x62: Wait 1/60th second
                    elif data[i] == 0x62:
                        wait_value = WAIT60TH - (time.time() - frame_t)
                        time.sleep(wait_value if wait_value > 0 else 0)
                        frame_t = time.time()
                        i += 1
                        samples_played += 735

                    # 0x63: Wait 1/50th second
                    elif data[i] == 0x63:
                        wait_value = WAIT50TH - (time.time() - frame_t)
                        time.sleep(wait_value if wait_value > 0 else 0)
                        frame_t = time.time()
                        i += 1
                        samples_played += 882

                    # 0x7n: Wait n+1 samples, n can range from 0 to 15.
                    elif data[i] in range (0x70, 0x80):
                        #print(hex(data[i]))                        
                        wait_value = data[i] & 0x0F
                        samples_played += wait_value
                        time.sleep( 1.0 * wait_value / 44100)                         
                        i += 1

                    # Unknown VGM Command
                    else:
                        i += 1
                        print("Unknown cmd at offset ",end='')
                        print(hex(i))

                    # Additionnal processing
                    cur_min, cur_sec = to_minsec(samples_played, 44100)
                    #sys.stdout.write(
                    #    "\x1b[2K\rPlaying \x1b[36;1m{0:02}:{1:02} \x1b[0m/ \x1b[37;1m{2:02}:{3:02}\x1b[0m".format(
                    #        cur_min, cur_sec, song_min, song_sec))
                    #sys.stdout.flush()


                # 0x66: End of Sound Data
                new_offset = header['loop_offset']
                i = new_offset if new_offset >= 0 else 0

                # Clear vgm2149 registers
                #ser.write(16)       # Write 16 bytes set to 0x00
                #print("")
        except KeyboardInterrupt:
            # Clear vgm2149 registers
            ser.write(bytes([0xFF]))
            print("Aborted")


def main():
    header = None
    data = None

    if len(sys.argv) != 3:
        print("Syntax is: {} <output_device> <vgm_filepath>".format(
            sys.argv[0]))
        exit(0)

    #
    # Utiliza gzip.open si el archivo está comprimido
    #
    if (os.path.splitext (sys.argv[2])[1] == '.vgz'):
        with gzip.open (sys.argv[2], 'rb') as fd:
            vgm = VGMReader(fd)
            vgm.dump_header()
            header = vgm.get_header()
            data = vgm.get_data()
    else:

        with open(sys.argv[2], 'rb') as fd:
            vgm = VGMReader(fd)
            vgm.dump_header()
            header = vgm.get_header()
            data = vgm.get_data()

    vgm_play(data, header)


if __name__ == '__main__':
    main()