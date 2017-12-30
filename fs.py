#!/usr/bin/env python3

import fuse

class Iso9660(fuse.Operations):
    pass

import sys
if len(sys.argv) < 2:
    print("Give a mount point")
    sys.exit(1)

mountpoint = sys.argv[1]
filesystem = fuse.FUSE(Iso9660(), mountpoint, foreground=True)
