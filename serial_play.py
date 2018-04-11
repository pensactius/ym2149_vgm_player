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

#BAUD = 57600
BAUD = 9600


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
        self.__fd.seek (0x14 + self.__header['gd3_offset'] + 12)
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

        # Seek to ay8910 clock info (absolute offset 0x74)
        s = self.__fd.seek(0x74)
        d['clk_ay8910'] = struct.unpack('< I', s)[0]
        
        self.__header = d

        # In python3 everything we read from a binary file are bytes
        # so we need to decode these to str to show them correctly.
        d['id'] = d['id'].decode()

        # Get version in string format 'maj.min'
        d['str_version'] = __get_str_version()

        self.__parse_gd3_info()

    def __get_str_version (self):
        high, low = divmod (self.__header['version'])
        str_version = format(high, 'x') + '.' + format(low, 'x')
        return str_version


    def __read_data_interleaved(self):
        cnt = self.__header['nb_frames']
        regs = [self.__fd.read(cnt) for i in range(16)]
        self.__data = [f for f in zip(*regs)]

    def __read_data(self):
        if not self.__header['interleaved']:
            raise Exception(
                'Unsupported file format: Only interleaved data are supported')
        self.__read_data_interleaved()

    def __check_eof(self):
        if self.__fd.read(4).decode() != 'End!':
            print('*Warning* End! marker not found after frames')

    def __init__(self, fd):
        self.__fd = fd
        self.__parse_header()
        self.__data = []

    def dump_header(self):
        for k in ('id', 'check_string', 'nb_frames', 'song_attributes',
                  'nb_digidrums', 'chip_clock', 'frames_rate', 'loop_frame',
                  'extra_data', 'song_name', 'author_name', 'song_comment'):
            print("{}: {}".format(k, self.__header[k]))

    def get_header(self):
        return self.__header

    def get_data(self):
        if not self.__data:
            self.__read_data()
            self.__check_eof()
        return self.__data


def to_minsec(frames, frames_rate):
    secs = frames // frames_rate
    mins = secs // 60
    secs = secs % 60
    return (mins, secs)


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
            print (header)

    with open(sys.argv[2], 'rb') as fd:
        vgm = vgmReader(fd)
        vgm.dump_header()
        header = vgm.get_header()
        data = vgm.get_data()
        print(header)

    song_min, song_sec = to_minsec(header['nb_frames'], header['frames_rate'])
    print("")

    with serial.Serial(sys.argv[1], BAUD) as ser:
        time.sleep(2)  # Wait for Arduino reset
        frame_t = time.time()
        try:
            for i in range(header['nb_frames']):
                # Substract time spent in code
                time.sleep(1. / header['frames_rate'] -
                           (time.time() - frame_t))
                frame_t = time.time()
                ser.write(data[i])
                i += 1

                # Additionnal processing
                cur_min, cur_sec = to_minsec(i, header['frames_rate'])
                sys.stdout.write(
                    "\x1b[2K\rPlaying {0:02}:{1:02} / {2:02}:{3:02}".format(
                        cur_min, cur_sec, song_min, song_sec))
                sys.stdout.flush()

            # Clear vgm2149 registers
            ser.write(16)       # Write 16 bytes set to 0x00
            print("")
        except KeyboardInterrupt:
            # Clear vgm2149 registers
            ser.write(16)       # Write 16 bytes set to 0x00
            print("")


if __name__ == '__main__':
    main()