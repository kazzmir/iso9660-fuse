#!/usr/bin/env python3

import fuse
import struct
import errno
import stat

def lsb(data):
    return struct.unpack('<I', data[0:4])[0]

class Directory:
    def __init__(self, entries, data):
        self.entries = entries
        self.data = data

    def attributes(self):
        import time

        return {'st_mode': stat.S_IFDIR,
                'st_nlink': 1,
                'st_size': 0,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()}


class File:
    def __init__(self, iso_file, data):
        self.iso_file = iso_file
        self.length = lsb(data[10:10+4])
        self.lba = lsb(data[2: 2+4])

    def read(self, offset, size):
        self.iso_file.seek(self.lba * 2 * 1024 + offset)
        return self.iso_file.read(size)

    def attributes(self):
        import time
        return {'st_mode': stat.S_IFREG,
                'st_nlink': 1,
                'st_size': self.length,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()}


def read_iso(iso):
    sector_size = 2 * 1024

    iso_file = open(iso, 'rb')

    # data = file.read(32 * 1024)
    for x in range(0, 0xf):
        iso_file.read(sector_size)

    def find_primary_volume():
        while True:
            volume = iso_file.read(sector_size)
            type = volume[0]
            print("Volume is {}".format(type))
            if type == 1:
                return volume

    primary_volume = find_primary_volume()
    standard_id = primary_volume[1:1+5]
    version = primary_volume[6]
    system_id = primary_volume[8:8+32]
    volume_id = primary_volume[40:40+32]
    volume_space_size = primary_volume[80:80+4]
    volume_space_size_msb = primary_volume[84:84+4]
    volume_set_size = primary_volume[120:120+4]
    volume_sequence_number = primary_volume[124:124+4]
    logical_block_size = primary_volume[128:128+4]
    path_table_size = primary_volume[132:132+8]
    path_table_size_L = primary_volume[140:140+4]
    root_entry = primary_volume[156:156+34]
    volume_set_identifier = primary_volume[190:190+128]
    publisher_id = primary_volume[318:318+128]
    prepaper_id = primary_volume[446:446+128]
    application_id = primary_volume[574:574+128]
    creation_date = primary_volume[813:813+17]
    modification_date = primary_volume[830:830+17]
    expiration_date = primary_volume[847:847+17]

    print("Version {}. System id '{}'. Volume id '{}'. Space {} {}".format(version, system_id.decode(), volume_id.decode(), struct.unpack('<I', volume_space_size), struct.unpack('>I', volume_space_size_msb)))

    root_length = root_entry[0]
    root_filename_length = int(root_entry[32])
    root_filename = root_entry[33:33+root_filename_length]
    root_extent = struct.unpack('<I', root_entry[2:2+4])[0]
    print("Root length {}".format(root_length))
    print("Root extent {}".format(root_extent))
    print("Root entry {}".format(root_filename))

    iso_file.seek(root_extent * sector_size)
    root_data = iso_file.read(sector_size)

    seen_lbas = set()

    def populate_filesystem(filesystem, data, extent):
        if extent in seen_lbas:
            return
        seen_lbas.add(extent)
        import time
        offset = 0
        while offset < len(data):
            # time.sleep(0.1)
            length = data[offset]
            if length == 0:
                break
            print('Entry length {}'.format(length))
            flags = data[offset + 25]
            lba = lsb(data[offset+2: offset+2+4])
            name_length = data[offset + 32]
            name = data[offset + 33: offset + 33 + name_length]
            print("Read {}".format(name.decode()))

            if name[0] == 0 or name[0] == 1:
                offset += length
                continue

            if flags == 2:
                print("Subdirectory at {}".format(lba))
                more = {}
                iso_file.seek(lba * sector_size)
                populate_filesystem(more, iso_file.read(sector_size), lba)
                filesystem[name.decode()] = Directory(more, data[offset:offset + length])
            else:
                filesystem[name.decode()] = File(iso_file, data[offset:offset + length])

            offset += length

    filesystem = {}

    populate_filesystem(filesystem, root_data, root_extent)

    print("Done reading iso")
    print(filesystem)
    return {'/': Directory(filesystem, None)}

class Iso9660(fuse.Operations):
    def __init__(self, iso):
        self.filesystem = read_iso(iso)
        self.fds = [0]
        self.last_fd = 0

    def lookup(self, path):
        if path == '/':
            parts = ['/']
        else:
            parts = ['/'] + path.split('/')[1:]

        tree = self.filesystem

        out = None

        for part in parts:
            # print("Search for {} in {}".format(part, tree))
            if not part in tree:
                # print("didnt find it")
                raise fuse.FuseOSError(errno.ENOENT)

            out = tree[part]
            if type(out) is Directory:
                tree = tree[part].entries

        return out

    def next_fd(self):
        if len(self.fds) > 0:
            return self.fds.pop(0)
        self.fds += list(range(self.last_fd, self.last_fd + 10))
        self.last_fd += 10
        return self.fds.pop(0)

    def open(self, path, flags):
        print("Open {}".format(path))
        return self.next_fd()

    def read(self, path, size, offset, handle):
        print("Read {} handle {} size {} offset {}".format(path, handle, size, offset))
        item = self.lookup(path)
        return item.read(offset, size)

    def getattr(self, path, handle=None):
        item = self.lookup(path)
        return item.attributes()

    def readdir(self, path, handle):
        print("Read dir: {}".format(path))
        item = self.lookup(path)
        entries = list(item.entries.keys())
        print("Keys {}".format(entries))
        return ['.', '..'] + entries

import sys
if len(sys.argv) < 3:
    print("{} <iso> <mount-point>".format(sys.argv[0]))
    sys.exit(1)

iso = sys.argv[1]
mountpoint = sys.argv[2]
filesystem = fuse.FUSE(Iso9660(iso), mountpoint, foreground=True)
