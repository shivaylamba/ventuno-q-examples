"""Original game illustration for the image-required Qwen vision runner."""
# SPDX-License-Identifier: MPL-2.0
import struct
import zlib

def egg_png():
    size=256
    rows=[]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            ry=(y-140)/103
            width=69*(.82+.18*max(0,min(1,(y-37)/150)))
            inside=((x-128)/width)**2+ry**2<1
            if inside:
                light=max(0,min(1,1-(x-65+y-40)/360))
                color=(int(84+103*light),int(156+78*light),int(110+65*light))
                if 124<x<129 and 65<y<222:color=(63,122,91)
            else:color=(11,23,19)
            row.extend(color)
        rows.append(row)
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))

EGG_ART=egg_png()
