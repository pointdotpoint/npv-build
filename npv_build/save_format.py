"""Low-level Cyberpunk 2077 sav.dat container parser.

Ported from PixelRick/CyberpunkSaveEditor (node_tree.cpp, bstream.cpp).

Container layout:
  - Header: magic 'CSAV' (LE bytes "VASC"), v1:u32, v2:u32, suk:lpfxd-str,
    uk0:u32, uk1:u32, [v1>=83] v3:u32
  - Footer (last 8 bytes): nodedescs_start:u32, magic 'DONE'
  - NODE section @ nodedescs_start: magic 'NODE', packed-int count, node descs
  - CLZF section (LE "FZLC"): vec-lpfxd of compressed_chunk_desc (offset,size,data_size)
  - Chunks: each @ desc.offset begins with magic 'XLZ4' then LZ4 block data

Node desc: lpfxd name, then next_idx:i32, child_idx:i32, data_offset:u32, data_size:u32
(the offsets are into the concatenated, decompressed node data blob).
"""

import struct

import lz4.block


class SaveFormatError(Exception):
    pass


class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def seek(self, pos):
        self.pos = pos

    def u8(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def u32(self):
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def magic(self):
        # Magics are stored as a little-endian uint32 of the 4 ASCII chars, so
        # on disk they appear byte-reversed ('CSAV' -> b'VASC'). Return the
        # logical (un-reversed) tag for comparison.
        s = self.data[self.pos : self.pos + 4]
        self.pos += 4
        return s[::-1]

    def read_int64_packed(self):
        a = self.u8()
        value = a & 0x3F
        sign = bool(a & 0x80)
        if a & 0x40:
            a = self.u8()
            value |= (a & 0x7F) << 6
            if a & 0x80:
                a = self.u8()
                value |= (a & 0x7F) << 13
                if a & 0x80:
                    a = self.u8()
                    value |= (a & 0x7F) << 20
                    if a & 0x80:
                        a = self.u8()
                        value |= (a & 0xFF) << 27
        return -value if sign else value

    def read_str_lpfxd(self):
        cnt = self.read_int64_packed()
        if cnt < 0 and cnt > -0x1000:
            n = -cnt
            s = self.data[self.pos : self.pos + n]
            self.pos += n
            return s.decode("latin-1")
        elif cnt > 0 and cnt < 0x1000:
            n = cnt
            raw = self.data[self.pos : self.pos + n * 2]
            self.pos += n * 2
            # utf-16 stored; CSE narrows to char, we decode utf-16-le
            return raw.decode("utf-16-le", errors="replace")
        return ""


XLZ4_CHUNK_SIZE = 0x40000


class NodeDesc:
    __slots__ = ("name", "next_idx", "child_idx", "data_offset", "data_size")

    def __init__(self, name, next_idx, child_idx, data_offset, data_size):
        self.name = name
        self.next_idx = next_idx
        self.child_idx = child_idx
        self.data_offset = data_offset
        self.data_size = data_size


class SaveContainer:
    def __init__(self, data: bytes):
        self.data = data
        self.descs = []
        self.nodedata = b""
        self.version = (0, 0, 0)
        self._parse()

    def _parse(self):
        r = _Reader(self.data)
        magic = r.magic()
        if magic not in (b"CSAV", b"SAVE"):
            raise SaveFormatError(f"bad header magic: {magic!r}")
        v1 = r.u32()
        v2 = r.u32()
        r.read_str_lpfxd()  # suk
        r.u32()  # uk0
        r.u32()  # uk1
        v3 = 192
        if v1 >= 83:
            v3 = r.u32()
        self.version = (v1, v2, v3)

        # Footer
        r.seek(len(self.data) - 8)
        nodedescs_start = r.u32()
        if r.magic() != b"DONE":
            raise SaveFormatError("missing DONE tag")

        # NODE descriptors
        r.seek(nodedescs_start)
        if r.magic() != b"NODE":
            raise SaveFormatError("missing NODE tag")
        nd_cnt = r.read_int64_packed()
        descs = []
        for _ in range(nd_cnt):
            name = r.read_str_lpfxd()
            next_idx = r.i32()
            child_idx = r.i32()
            data_offset = r.u32()
            data_size = r.u32()
            descs.append(NodeDesc(name, next_idx, child_idx, data_offset, data_size))
        self.descs = descs

        # CLZF compressed chunk descriptors immediately follow NODE? No:
        # chunkdescs are located via 'CLZF' magic. CSE seeks chunkdescs_start
        # (== end of header) but the table is tagged 'CLZF'. Search for it.
        clzf_pos = self.data.find(b"FZLC")
        if clzf_pos < 0:
            raise SaveFormatError("missing CLZF/FZLC tag")
        r.seek(clzf_pos)
        r.magic()  # 'FZLC'
        chunk_cnt = r.u32()  # vec lpfxd uses u32 count
        chunks = []
        for _ in range(chunk_cnt):
            offset = r.u32()
            size = r.u32()
            data_size = r.u32()
            chunks.append([offset, size, data_size])
        chunks.sort(key=lambda c: c[0])

        # Assign cumulative data_offset, build decompressed blob
        data_offset = chunks[0][0] if chunks else 0
        total = data_offset
        for c in chunks:
            c.append(total)  # data_offset in blob
            total += c[2]
        nodedata = bytearray(total)
        for offset, size, dsize, blob_off in chunks:
            cr = _Reader(self.data, offset)
            if cr.magic() != b"XLZ4":
                raise SaveFormatError(f"missing XLZ4 at {offset}")
            # size includes XLZ4 tag + a u32; CSE reads uncompressed size (u32) then
            # the compressed bytes. The u32() call advances cr.pos past that field.
            cr.u32()
            comp_bytes = self.data[cr.pos : cr.pos + (size - 8)]
            out = lz4.block.decompress(comp_bytes, uncompressed_size=dsize)
            nodedata[blob_off : blob_off + len(out)] = out
        self.nodedata = bytes(nodedata)

    def find_node(self, name: str):
        for d in self.descs:
            if d.name == name:
                return d
        return None

    def node_bytes(self, name: str):
        d = self.find_node(name)
        if not d:
            return None
        return self.nodedata[d.data_offset : d.data_offset + d.data_size]

    def node_names(self):
        return [d.name for d in self.descs]
