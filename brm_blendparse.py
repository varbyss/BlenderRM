"""Fast .blend file reader (no Blender needed).

Reads render settings straight from the .blend binary format:
Blender 5.x format v1 (17-byte header, LargeBHead8, zstd-compressed files)
and legacy v0 files (12-byte header, classic block headers).

Only parses what the render queue needs: scenes, cameras, view layers,
frame ranges, fps, resolution, engine, output, image format, samples,
active scene, missing external images, simulator markers.
"""

import io
import os
import re
import struct

__all__ = ["fast_probe", "preview_probe", "BlendFile", "BlendParseError",
           "load_cached_probe", "store_cached_probe"]


class BlendParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# low level file reading
# ---------------------------------------------------------------------------

def _decompress(path, raw):
    if raw[:4] == bytes([0x28, 0xB5, 0x2F, 0xFD]):
        reader = None
        try:
            import zstandard
            reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw))
        except ImportError:
            pass
        if reader is None:
            try:
                from compression import zstd as _zstd
                reader = _zstd.ZstdDecompressor().stream_reader(io.BytesIO(raw))
            except Exception:
                pass
        if reader is None:
            raise BlendParseError("zstd-compressed .blend but no zstandard module (pip install zstandard)")
        # Chunked: one giant .read() is a single C call holding the GIL for
        # many seconds on big sim files, freezing the whole UI (no clicks get
        # through). Small chunks + yields keep the app alive while parsing.
        import time as _t
        out = []
        _err = None
        try:
            while True:
                try:
                    chunk = reader.read(4 * 1024 * 1024)
                except Exception as e:
                    _err = e
                    break
                if not chunk:
                    break
                out.append(chunk)
                try:
                    _t.sleep(0)
                except Exception:
                    pass
        finally:
            try:
                reader.close()
            except Exception:
                pass
        if not out and _err is not None:
            raise BlendParseError("zstd decompress failed for {}: {}".format(path, _err))
        return b"".join(out)
    return raw


def _decode_header(data):
    if data[:7] != b'BLENDER':
        raise BlendParseError("not a .blend file")
    if data[7:8] in (b'-', b'_'):
        # legacy v0, 12-byte header
        return {"format": 0, "hlen": 12,
                "ptrsize": 8 if data[7:8] == b'-' else 4,
                "endian": '<' if data[8:9] == b'v' else '>',
                "version": data[9:12].decode('ascii', 'replace')}
    # v1: BLENDER + 2-digit header size + '-' + 2-digit format + 'v' + 4-digit version
    try:
        hlen = int(data[7:9])
    except ValueError:
        raise BlendParseError("unknown .blend header: %r" % data[:17])
    if data[9:10] != b'-' or data[12:13] not in (b'v', b'V'):
        raise BlendParseError("unknown .blend header: %r" % data[:17])
    return {"format": 1, "hlen": hlen, "ptrsize": 8,
            "endian": '<' if data[12:13] == b'v' else '>',
            "version": data[13:17].decode('ascii', 'replace')}


# 4-byte block codes whose data we actually read; everything else is skipped.
# NOTE: some datablocks (e.g. master "Scene Collection") hide in DATA blocks,
# handled via data_sizes below.
_KEEP_C4 = [b'SC\x00\x00', b'GLOB', b'WM\x00\x00', b'GR\x00\x00', b'OB\x00\x00',
            b'CA\x00\x00', b'IM\x00\x00', b'DNA1', b'REND']
_DATA_C4 = b'DATA'
_ENDB_C4 = b'ENDB'


def _find_dna1(data, hdr):
    """Locate the DNA1 block from the end (it sits right before ENDB)."""
    e = hdr["endian"]
    pos = data.rfind(b'DNA1')
    while pos != -1:
        try:
            # pos is the start of the block header (code comes first)
            hstart = pos
            if hdr["format"] == 1:
                code_i, sdna, old, size, nr = struct.unpack(e + 'iiQqq', data[hstart:hstart + 32])
                dstart = hstart + 32
            else:
                hlen = 20 if hdr["ptrsize"] == 8 else 16
                size, = struct.unpack(e + 'i', data[hstart + 4:hstart + 8])
                dstart = hstart + hlen
            if size > 0 and dstart + size <= len(data) and data[dstart:dstart + 4] == b'SDNA':
                _parse_sdna(bytes(data[dstart:dstart + size]))
                return dstart, size
        except Exception:
            pass
        pos = data.rfind(b'DNA1', 0, pos)
    return None, None


def _parse_blocks(data, hdr, keep_ints=None, data_sizes=None, node_sizes=None, idname_off=0):
    keep = keep_ints if keep_ints is not None else frozenset()
    dsizes = data_sizes if data_sizes is not None else {}
    nsizes = node_sizes if node_sizes is not None else frozenset()
    ptrsize = hdr["ptrsize"]
    e = hdr["endian"]
    off = hdr["hlen"]
    blocks = []
    n = len(data)
    append = blocks.append
    endb_i = struct.unpack(e + 'i', _ENDB_C4)[0]
    data_i = struct.unpack(e + 'i', _DATA_C4)[0]
    if hdr["format"] == 1:
        up = struct.Struct(e + 'iiQqq').unpack_from
        while off + 32 <= n:
            code_i, sdna, old, size, nr = up(data, off)
            if code_i == endb_i:
                append((b'ENDB', size, old, sdna, nr, off + 32))
                break
            if size < 0 or nr < 0 or sdna < 0 or off + 32 + size > n:
                break
            if code_i in keep:
                append((struct.pack(e + 'i', code_i), size, old, sdna, nr, off + 32))
            elif code_i == data_i and nr == 1 and idname_off:
                if size in nsizes:
                    append((b'DATA', size, old, sdna, nr, off + 32))
                elif size in dsizes:
                    end = off + 32 + idname_off + 2
                    if end <= n and data[off + 32 + idname_off:end] == dsizes[size]:
                        append((dsizes[size] + b'\x00\x00', size, old, sdna, nr, off + 32))
            off += 32 + size
    else:
        hlen = 20 if ptrsize == 8 else 16
        while off + hlen <= n:
            code = bytes(data[off:off + 4])
            size, = struct.unpack(e + 'i', data[off + 4:off + 8])
            if ptrsize == 8:
                old, = struct.unpack(e + 'Q', data[off + 8:off + 16])
                sdna, nr = struct.unpack(e + 'ii', data[off + 16:off + 24])
            else:
                old, = struct.unpack(e + 'I', data[off + 8:off + 12])
                sdna, nr = struct.unpack(e + 'ii', data[off + 12:off + 20])
            if code == b'ENDB':
                append((code, size, old, sdna, nr, off + hlen))
                break
            if size < 0 or nr < 0 or sdna < 0 or off + hlen + size > n:
                break
            if struct.unpack(e + 'i', code)[0] in keep:
                append((code, size, old, sdna, nr, off + hlen))
            elif code == b'DATA' and nr == 1 and idname_off:
                if size in nsizes:
                    append((code, size, old, sdna, nr, off + hlen))
                elif size in dsizes:
                    end = off + hlen + idname_off + 2
                    if end <= n and data[off + hlen + idname_off:end] == dsizes[size]:
                        append((dsizes[size] + b'\x00\x00', size, old, sdna, nr, off + hlen))
            off += hlen + size
    return blocks


def _parse_sdna(d):
    """Parse SDNA blob. Handles v1 (unpadded strings) and v0 (padded) layouts."""
    e = '<'  # SDNA section endianness follows file; try LE first, fallback BE
    for endian in ('<', '>'):
        try:
            p = 0
            assert d[p:p + 4] == b'SDNA'
            p += 4
            assert d[p:p + 4] == b'NAME'
            p += 4
            nn, = struct.unpack(endian + 'i', d[p:p + 4])
            p += 4
            names = []
            for _ in range(nn):
                end = d.index(b'\0', p)
                names.append(d[p:end].decode('utf-8', 'replace'))
                p = end + 1
            for padded in (False, True):
                pp = (p + 3) & ~3 if padded else p
                if d[pp:pp + 4] != b'TYPE':
                    continue
                p = pp + 4
                nt, = struct.unpack(endian + 'i', d[p:p + 4])
                p += 4
                types = []
                for _ in range(nt):
                    end = d.index(b'\0', p)
                    types.append(d[p:end].decode('utf-8', 'replace'))
                    p = end + 1
                for padded2 in (False, True):
                    pp2 = (p + 3) & ~3 if padded2 else p
                    if d[pp2:pp2 + 4] != b'TLEN':
                        continue
                    p = pp2 + 4
                    tlens = struct.unpack(endian + 'H' * nt, d[p:p + 2 * nt])
                    p += 2 * nt
                    for padded3 in (False, True):
                        pp3 = (p + 3) & ~3 if padded3 else p
                        if d[pp3:pp3 + 4] != b'STRC':
                            continue
                        p = pp3 + 4
                        nst, = struct.unpack(endian + 'i', d[p:p + 4])
                        p += 4
                        structs = {}
                        for _ in range(nst):
                            ti, nf = struct.unpack(endian + 'HH', d[p:p + 4])
                            p += 4
                            fields = []
                            for _ in range(nf):
                                fti, fni = struct.unpack(endian + 'HH', d[p:p + 4])
                                p += 4
                                fields.append((types[fti], names[fni]))
                            structs[types[ti]] = fields
                        return endian, names, types, tlens, structs
        except Exception:
            continue
    raise BlendParseError("could not parse SDNA")


_ATOMIC_SIZES = {
    'char': 1, 'uchar': 1, 'int8_t': 1, 'uint8_t': 1, 'bool': 1,
    'short': 2, 'ushort': 2, 'int16_t': 2, 'uint16_t': 2,
    'int': 4, 'uint': 4, 'int32_t': 4, 'uint32_t': 4, 'float': 4,
    'int64_t': 8, 'uint64_t': 8, 'double': 8, 'long': 4, 'ulong': 4,
}


def _split_field(fname):
    """Split DNA field name into (is_pointer, base_name, array_lengths).

    Handles '*camera', '**mat', 'pic[1024]', 'parentinv[4][4]', '(*callback)(...)'.
    """
    is_ptr = False
    name = fname
    if name.startswith('(*'):
        end = name.find(')')
        base = name[2:end] if end != -1 else name[2:]
        return True, base, []
    while name.startswith('*'):
        is_ptr = True
        name = name[1:]
    arr = []
    m = re.match(r'^([^\[]+)((?:\[[^\]]*\])*)$', name)
    if m:
        base = m.group(1)
        arr = [int(x) for x in re.findall(r'\[(\d+)\]', m.group(2))]
    else:
        base = name
    return is_ptr, base, arr


class BlendFile:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            raw = f.read()
        self.raw = raw
        data = _decompress(path, raw)
        self.data = data
        self.hdr = _decode_header(data)
        self.endian = self.hdr["endian"]
        self.ptrsize = self.hdr["ptrsize"]
        # DNA first (located from the end), so the block walk knows struct sizes
        dstart, dsize = _find_dna1(data, self.hdr)
        if dstart is None:
            raise BlendParseError("DNA1 block not found")
        endian, names, types, tlens, structs = _parse_sdna(bytes(data[dstart:dstart + dsize]))
        self.endian = endian
        self.dna_names = names
        self.dna_types = types
        self.dna_tlens = dict(zip(types, tlens))
        self.dna_structs = structs
        self._layouts = {}
        # DATA blocks that secretly carry datablocks: match by struct size + ID prefix.
        # Small list-node structs (32/48/320B…): retain by size, correctness comes
        # from following real list pointers only.
        keep_ints = frozenset(struct.unpack(self.endian + 'i', c)[0] for c in _KEEP_C4)
        data_sizes = {}
        node_sizes = set()
        try:
            idname_off = self.layout("ID")['name'][0]
            for tname, prefix in (("Scene", b'SC'), ("Object", b'OB'), ("Camera", b'CA'),
                                  ("Image", b'IM'), ("Collection", b'GR')):
                if tname in self.dna_structs:
                    data_sizes[self.layout(tname)['_size']] = prefix
            for tname in ("CollectionChild", "CollectionObject", "Base", "ViewLayer"):
                if tname in self.dna_structs:
                    node_sizes.add(self.layout(tname)['_size'])
        except Exception:
            idname_off = 0
            data_sizes = {}
            node_sizes = set()
        self.blocks = _parse_blocks(data, self.hdr, keep_ints, data_sizes, node_sizes, idname_off)
        # addr -> block index for pointer resolution
        self.addr_index = {}
        for i, b in enumerate(self.blocks):
            if b[2]:
                self.addr_index.setdefault(b[2], []).append(i)

    # -- struct layouts -----------------------------------------------------
    def _atomic_size(self, tname):
        if tname in _ATOMIC_SIZES:
            return _ATOMIC_SIZES[tname]
        if tname == 'void':
            return 1
        return None

    def _struct_align(self, tname, depth=0):
        if depth > 8:
            return 8
        if tname in self._layouts:
            return self._layouts[tname][1]
        fields = self.dna_structs.get(tname)
        if fields is None:
            return min(self.ptrsize, 8)
        best = 1
        for ft, fn in fields:
            is_ptr, base, arr = _split_field(fn)
            if is_ptr or base == 'void':
                a = self.ptrsize
            else:
                s = self._atomic_size(ft)
                a = s if s else self._struct_align(ft, depth + 1)
            best = max(best, min(a, 8))
        return best

    def layout(self, tname):
        """Return {field_base_name: (offset, type, is_ptr, array)} + total size."""
        if tname in self._layouts:
            return self._layouts[tname][0]
        fields = self.dna_structs.get(tname)
        if fields is None:
            raise BlendParseError("unknown struct %s" % tname)
        out = {}
        off = 0
        for ft, fn in fields:
            is_ptr, base, arr = _split_field(fn)
            if is_ptr or base == 'void':
                size, align = self.ptrsize, self.ptrsize
                ftype = 'ptr'
            else:
                a = self._atomic_size(ft)
                if a is not None:
                    nelem = 1
                    for x in arr:
                        nelem *= x
                    size, align, ftype = a * nelem, min(a, 8), ft
                else:
                    sub = self.layout(ft)
                    sub_size = sub['_size']
                    nelem = 1
                    for x in arr:
                        nelem *= x
                    size = sub_size * nelem
                    align = self._struct_align(ft)
                    ftype = ft
            off = (off + align - 1) & ~(align - 1)
            if base not in out:
                out[base] = (off, ftype, is_ptr, arr)
            off += size
        total_align = self._struct_align(tname)
        total = (off + total_align - 1) & ~(total_align - 1)
        out['_size'] = total
        self._layouts[tname] = (out, total_align)
        return out

    def check_layout(self, tname):
        expect = self.dna_tlens.get(tname)
        got = self.layout(tname)['_size']
        return expect, got

    # -- value readers ------------------------------------------------------
    def _read_atomic(self, ftype, buf, off):
        e = self.endian
        if ftype in ('char', 'int8_t'):
            return struct.unpack(e + 'b', buf[off:off + 1])[0]
        if ftype in ('uchar', 'uint8_t', 'bool'):
            return buf[off]
        if ftype in ('short', 'int16_t'):
            return struct.unpack(e + 'h', buf[off:off + 2])[0]
        if ftype in ('ushort', 'uint16_t'):
            return struct.unpack(e + 'H', buf[off:off + 2])[0]
        if ftype in ('int', 'int32_t', 'long', 'ulong'):
            return struct.unpack(e + 'i', buf[off:off + 4])[0]
        if ftype in ('uint', 'uint32_t'):
            return struct.unpack(e + 'I', buf[off:off + 4])[0]
        if ftype == 'float':
            return struct.unpack(e + 'f', buf[off:off + 4])[0]
        if ftype in ('int64_t',):
            return struct.unpack(e + 'q', buf[off:off + 8])[0]
        if ftype in ('uint64_t',):
            return struct.unpack(e + 'Q', buf[off:off + 8])[0]
        if ftype == 'double':
            return struct.unpack(e + 'd', buf[off:off + 8])[0]
        raise BlendParseError("cannot read atomic %s" % ftype)

    def read_ptr(self, tname, buf, base, field):
        lay = self.layout(tname)
        off, ftype, is_ptr, arr = lay[field]
        if not is_ptr:
            raise BlendParseError("%s.%s is not a pointer" % (tname, field))
        if self.ptrsize == 8:
            return struct.unpack(self.endian + 'Q', buf[base + off:base + off + 8])[0]
        return struct.unpack(self.endian + 'I', buf[base + off:base + off + 4])[0]

    def read_value(self, tname, buf, base, field):
        """Read scalar field (follows one struct level; use read_path for nesting)."""
        lay = self.layout(tname)
        off, ftype, is_ptr, arr = lay[field]
        if is_ptr or arr:
            raise BlendParseError("%s.%s is not scalar" % (tname, field))
        return self._read_atomic(ftype, buf, base + off)

    def read_string(self, tname, buf, base, field, maxlen=None):
        lay = self.layout(tname)
        off, ftype, is_ptr, arr = lay[field]
        n = 1
        for x in arr:
            n *= x
        raw = buf[base + off:base + off + n]
        if maxlen:
            raw = raw[:maxlen]
        return raw.split(b'\0', 1)[0].decode('utf-8', 'replace')

    def read_path(self, tname, buf, base, path):
        """Follow 'field.field' nesting (non-pointer structs inline)."""
        cur_t, cur_off = tname, base
        for part in path.split('.'):
            lay = self.layout(cur_t)
            off, ftype, is_ptr, arr = lay[part]
            if is_ptr:
                raise BlendParseError("pointer in path: %s" % part)
            if arr:
                raise BlendParseError("array in path: %s" % part)
            if ftype in _ATOMIC_SIZES or ftype == 'void':
                return self._read_atomic(ftype, buf, cur_off + off)
            cur_t, cur_off = ftype, cur_off + off
        raise BlendParseError("empty path")

    def read_path_string(self, tname, buf, base, path):
        cur_t, cur_off = tname, base
        parts = path.split('.')
        for part in parts[:-1]:
            lay = self.layout(cur_t)
            off, ftype, is_ptr, arr = lay[part]
            cur_t, cur_off = ftype, cur_off + off
        return self.read_string(cur_t, buf, cur_off, parts[-1])

    def iter_list(self, buf, base, tname, field, node_type):
        """Iterate a ListBase field, yielding data offsets of node_type structs."""
        lay = self.layout(tname)
        off, ftype, is_ptr, arr = lay[field]
        first = self._read_ptr_at(buf, base + off)
        addr = first
        guard = 0
        while addr and guard < 1000000:
            guard += 1
            bl = self.block_by_addr(addr)
            if bl is None:
                return
            yield bl[5]
            nlay = self.layout(node_type)
            noff = nlay['next'][0] if 'next' in nlay else 0
            addr = self._read_ptr_at(buf, bl[5] + noff)

    def _read_ptr_at(self, buf, off):
        if self.ptrsize == 8:
            return struct.unpack(self.endian + 'Q', buf[off:off + 8])[0]
        return struct.unpack(self.endian + 'I', buf[off:off + 4])[0]

    def block_by_addr(self, addr):
        lst = self.addr_index.get(addr)
        if not lst:
            return None
        return self.blocks[lst[0]]

    def blocks_of_type(self, typename):
        try:
            ti = self.dna_types.index(typename)
        except ValueError:
            return []
        return [b for b in self.blocks if b[3] == ti]


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def id_name(bf, buf, base, tname="ID", field="id"):
    """Read ID.name and split Blender's 2-letter type prefix ('SCScene.001' -> 'Scene.001')."""
    if field == "id" and tname != "ID":
        try:
            lay = bf.layout(tname)
            if 'id' in lay and lay['id'][1] not in ('ptr',) and not lay['id'][2]:
                sub = lay['id'][1]
                if sub in bf.dna_structs:
                    raw = bf.read_string(sub, buf, base + lay['id'][0], 'name')
                    return _strip_id_prefix(raw)
        except Exception:
            pass
    raw = bf.read_string("ID", buf, base, 'name')
    return _strip_id_prefix(raw)


def _strip_id_prefix(raw):
    if len(raw) > 2 and raw[2:3] not in ('',):
        return raw[2:]
    return raw


# ---------------------------------------------------------------------------
# fast probe
# ---------------------------------------------------------------------------

FILE_FORMAT_MAP = {0: "TARGA", 1: "IRIS", 2: "TARGA", 3: "TARGA", 4: "JPEG",
                   14: "TARGA_RAW", 17: "PNG", 20: "BMP", 21: "HDR", 22: "TIFF",
                   23: "OPEN_EXR", 24: "FFMPEG", 26: "CINEON", 27: "DPX",
                   28: "OPEN_EXR_MULTILAYER", 30: "JPEG2000", 35: "WEBP", 37: "AVIF"}
COLOR_MODE_MAP = {8: "BW", 24: "RGB", 32: "RGBA"}
COLOR_DEPTH_MAP = {2: "8", 4: "10", 8: "12", 16: "16", 64: "32"}

SIM_MARKERS = (b'hurr_original_mesh_deform', b'Hurricane_GN_SoftBody', b'HurricaneCache',
               b'HurricaneEmitter', b'HurricaneCollider', b'FLIPFluids', b'flip_fluids_addon',
               b'molecularplus', b'Molecular')
_SIM_RE = re.compile(b'|'.join(re.escape(m) for m in SIM_MARKERS))


def _walk_collection_objects(bf, data, coll_addr, seen, out_addrs, depth=0):
    if not coll_addr or coll_addr in seen or depth > 64:
        return
    seen.add(coll_addr)
    cbl = bf.block_by_addr(coll_addr)
    if cbl is None:
        return
    coff = cbl[5]
    try:
        for noff in bf.iter_list(data, coff, "Collection", 'gobject', "CollectionObject"):
            try:
                oaddr = bf.read_ptr("CollectionObject", data, noff, 'ob')
            except Exception:
                continue
            if oaddr:
                out_addrs.add(oaddr)
    except Exception:
        pass
    try:
        for noff in bf.iter_list(data, coff, "Collection", 'children', "CollectionChild"):
            try:
                caddr = bf.read_ptr("CollectionChild", data, noff, 'collection')
            except Exception:
                continue
            _walk_collection_objects(bf, data, caddr, seen, out_addrs, depth + 1)
    except Exception:
        pass


def _is_camera(bf, data, obl, data_block_codes):
    try:
        daddr = bf.read_ptr("Object", data, obl[5], 'data')
    except Exception:
        return False
    return bool(daddr) and data_block_codes.get(daddr) == b'CA'


def _resolve_object_name(bf, data, obj_addr, ob_blocks_by_addr):
    bl = ob_blocks_by_addr.get(obj_addr)
    if bl is None:
        return None
    base = bl[5]
    try:
        return id_name(bf, data, base, "Object")
    except Exception:
        return None


def _head_bytes(path, limit=131072):
    """First `limit` DECOMPRESSED bytes without decoding the whole file."""
    with open(path, 'rb') as f:
        head = f.read(1048576)
    if head[:4] == bytes([0x28, 0xB5, 0x2F, 0xFD]):
        try:
            import zstandard
            dctx = zstandard.ZstdDecompressor()
            return dctx.stream_reader(io.BytesIO(head)).read(limit)
        except ImportError:
            pass
        try:
            from compression import zstd as _zstd
            return _zstd.ZstdDecompressor().stream_reader(io.BytesIO(head)).read(limit)
        except Exception:
            pass
        return b''
    return head[:limit]


def preview_probe(path):
    """Instant active-scene + frame-range read from the REND block (file head only).

    Returns a partial probe dict with preview=True, or None. Never raises.
    """
    try:
        dec = _head_bytes(path)
        if len(dec) < 64 or dec[:7] != b'BLENDER':
            return None
        if dec[7:8] in (b'-', b'_'):
            hlen, hsize, e = 12, 4, ('<' if dec[8:9] == b'v' else '>')
            ptrsize = 8 if dec[7:8] == b'-' else 4
            bhlen = 20 if ptrsize == 8 else 16
            v1 = False
        else:
            try:
                hlen = int(dec[7:9])
            except ValueError:
                return None
            hsize, e, bhlen, v1 = 4, '<', 32, True
        off = hlen
        for _ in range(64):
            if off + bhlen > len(dec):
                return None
            if v1:
                code_i, sdna, old, size, nr = struct.unpack(e + 'iiQqq', dec[off:off + 32])
                code = struct.pack(e + 'i', code_i)
            else:
                code = bytes(dec[off:off + 4])
                size, = struct.unpack(e + 'i', dec[off + 4:off + 8])
            if code == b'REND' and 64 <= size <= 4096:
                if off + bhlen + size > len(dec):
                    return None
                d0 = off + bhlen
                sfra, = struct.unpack(e + 'i', dec[d0:d0 + 4])
                efra, = struct.unpack(e + 'i', dec[d0 + 4:d0 + 8])
                rawname = dec[d0 + 8:d0 + 72].split(b'\0', 1)[0]
                try:
                    scene = rawname.decode('utf-8', 'replace')
                except Exception:
                    return None
                if not (0 <= sfra <= efra <= 2000000):
                    return None
                if not scene or len(scene) > 63 or not all(32 <= ord(c) < 127 for c in scene):
                    return None
                return {"active": scene, "preview": True, "fast": True,
                        "hurricane": False, "hurricane_objects": [],
                        "missing": [], "missing_count": 0,
                        "scenes": [{"name": scene, "frame_start": int(sfra),
                                    "frame_end": int(efra)}]}
            if code == b'ENDB':
                return None
            if size < 0 or off + bhlen + size > len(dec):
                return None
            off += bhlen + size
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# persistent probe cache (survives restarts; keyed by path+size+mtime)
# ---------------------------------------------------------------------------

def _cache_dir():
    d = os.path.join(os.path.expanduser("~"), ".blender_monitor_probecache")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _cache_key(path):
    import hashlib
    try:
        st = os.stat(path)
        sig = "%s|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime))
    except Exception:
        return None
    return os.path.join(_cache_dir(), hashlib.sha1(sig.encode('utf-8')).hexdigest() + ".json")


def load_cached_probe(path):
    try:
        import json as _json
        key = _cache_key(path)
        if not key or not os.path.exists(key):
            return None
        with open(key, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        if isinstance(data, dict) and data.get("scenes"):
            return data
    except Exception:
        pass
    return None


def store_cached_probe(path, probe):
    try:
        import json as _json
        key = _cache_key(path)
        if not key or not isinstance(probe, dict):
            return
        with open(key, 'w', encoding='utf-8') as f:
            _json.dump(probe, f)
    except Exception:
        pass
def fast_probe(path):
    """Return a probe-compatible dict without starting Blender. Raises on failure."""
    bf = BlendFile(path)
    data = bf.data
    out = {"active": None, "scenes": [], "hurricane": False, "hurricane_objects": [],
           "missing": [], "missing_count": 0, "fast": True}

    # --- addr -> scene/object block maps ---
    scene_blocks = [b for b in bf.blocks if b[0][:2] == b'SC']
    ob_by_addr = {}
    for b in bf.blocks:
        if b[0][:2] == b'OB' and b[2]:
            ob_by_addr[b[2]] = b
    data_block_codes = {}  # addr -> 2-letter code of datablock (CA/ME/...)
    for b in bf.blocks:
        if b[2]:
            data_block_codes.setdefault(b[2], b[0][:2])

    # --- active scene: FileGlobal.curscene, fallback wm chain, fallback first ---
    active = None
    try:
        for b in bf.blocks:
            if b[0] == b'GLOB':
                cur = bf.read_ptr("FileGlobal", data, b[5], 'curscene')
                if cur:
                    sbl = bf.block_by_addr(cur)
                    if sbl is not None:
                        active = id_name(bf, data, sbl[5], "Scene")
                break
    except Exception:
        pass
    if not active:
        try:
            for b in bf.blocks:
                if b[0][:2] == b'WM':
                    for woff in bf.iter_list(data, b[5], "wmWindowManager", 'windows', "wmWindow"):
                        sptr = bf.read_ptr("wmWindow", data, woff, 'scene')
                        if sptr:
                            sbl = bf.block_by_addr(sptr)
                            if sbl is not None:
                                active = id_name(bf, data, sbl[5], "Scene")
                                break
                    break
        except Exception:
            pass
    out["active"] = active

    # --- scenes ---
    for sb in scene_blocks:
        base = sb[5]
        try:
            name = id_name(bf, data, base, "Scene")
        except Exception:
            continue
        try:
            sfra = bf.read_path("Scene", data, base, 'r.sfra')
            efra = bf.read_path("Scene", data, base, 'r.efra')
        except Exception:
            sfra, efra = 1, 250
        try:
            frs = bf.read_path("Scene", data, base, 'r.frs_sec')
            frs_base = bf.read_path("Scene", data, base, 'r.frs_sec_base')
            fps = float(frs) / float(frs_base) if frs_base else float(frs or 24)
        except Exception:
            fps = 24.0
        try:
            rx = bf.read_path("Scene", data, base, 'r.xsch')
            ry = bf.read_path("Scene", data, base, 'r.ysch')
            rpct = bf.read_path("Scene", data, base, 'r.size')
        except Exception:
            rx, ry, rpct = 1920, 1080, 100
        try:
            engine = bf.read_path_string("Scene", data, base, 'r.engine')
        except Exception:
            engine = ""
        try:
            output = bf.read_path_string("Scene", data, base, 'r.pic')
        except Exception:
            output = "//"
        try:
            imtype = int(bf.read_path("Scene", data, base, 'r.im_format.imtype'))
            file_format = FILE_FORMAT_MAP.get(imtype, "")
        except Exception:
            file_format = ""
        try:
            planes = int(bf.read_path("Scene", data, base, 'r.im_format.planes'))
            color_mode = COLOR_MODE_MAP.get(planes, "")
        except Exception:
            color_mode = ""
        try:
            depth = int(bf.read_path("Scene", data, base, 'r.im_format.depth'))
            color_depth = COLOR_DEPTH_MAP.get(depth, "")
        except Exception:
            color_depth = ""
        try:
            compression = int(bf.read_path("Scene", data, base, 'r.im_format.compress'))
        except Exception:
            compression = None
        try:
            alphamode = int(bf.read_path("Scene", data, base, 'r.alphamode'))
            film = (alphamode == 2)
        except Exception:
            film = False
        try:
            mode = int(bf.read_path("Scene", data, base, 'r.mode'))
            overwrite = not bool(mode & 1024)
            placeholder = bool(mode & 2)
        except Exception:
            overwrite, placeholder = True, False
        # camera: Scene.camera -> Object name
        camera = None
        try:
            cam_addr = bf.read_ptr("Scene", data, base, 'camera')
            if cam_addr:
                camera = _resolve_object_name(bf, data, cam_addr, ob_by_addr)
        except Exception:
            pass
        # cameras in this scene: legacy base list + master collection walk (5.x)
        scene_obj_addrs = set()
        try:
            for boff in bf.iter_list(data, base, "Scene", 'base', "Base"):
                oaddr = bf.read_ptr("Base", data, boff, 'object')
                if oaddr:
                    scene_obj_addrs.add(oaddr)
        except Exception:
            pass
        try:
            master = bf.read_ptr("Scene", data, base, 'master_collection')
            _walk_collection_objects(bf, data, master, set(), scene_obj_addrs)
        except Exception:
            pass
        cameras = []
        try:
            for oaddr in scene_obj_addrs:
                obl = ob_by_addr.get(oaddr)
                if obl is None or not _is_camera(bf, data, obl, data_block_codes):
                    continue
                nm = _resolve_object_name(bf, data, oaddr, ob_by_addr)
                if nm and nm not in cameras:
                    cameras.append(nm)
        except Exception:
            pass
        cameras.sort()
        # view layers
        view_layers = []
        try:
            for vloff in bf.iter_list(data, base, "Scene", 'view_layers', "ViewLayer"):
                try:
                    vn = bf.read_string("ViewLayer", data, vloff, 'name')
                except Exception:
                    vn = ""
                if vn:
                    view_layers.append(vn)
        except Exception:
            pass
        out["scenes"].append({
            "name": name, "frame_start": int(sfra), "frame_end": int(efra),
            "fps": fps, "camera": camera, "cameras": cameras,
            "view_layers": view_layers, "engine": engine, "samples": None,
            "eevee_samples": None, "res_x": int(rx), "res_y": int(ry),
            "res_pct": int(rpct), "film_transparent": film,
            "use_overwrite": overwrite, "use_placeholder": placeholder,
            "output": output, "file_format": file_format,
            "color_mode": color_mode, "color_depth": str(color_depth),
            "compression": compression,
        })
    if not out["active"] and out["scenes"]:
        out["active"] = out["scenes"][0]["name"]

    # --- external images: quick missing-file scan ---
    try:
        blend_dir = os.path.dirname(os.path.abspath(path))
        miss = []

        def _resolve(p):
            if p.startswith("//"):
                return os.path.normpath(os.path.join(blend_dir, p[2:]))
            if not os.path.isabs(p):
                return os.path.normpath(os.path.join(blend_dir, p))
            return os.path.normpath(p)

        for b in bf.blocks:
            if b[0][:2] != b'IM':
                continue
            try:
                nm = bf.read_path_string("Image", data, b[5], 'name')
            except Exception:
                continue
            if not nm:
                continue
            try:
                packed = bf.read_ptr("Image", data, b[5], 'packedfile')
            except Exception:
                packed = 0
            if packed:
                continue
            try:
                source = bf.read_value("Image", data, b[5], 'source')
            except Exception:
                source = 1
            if source not in (1, 4):
                continue
            if not os.path.exists(_resolve(nm)):
                miss.append(nm)
        out["missing"] = miss[:20]
        out["missing_count"] = len(miss)
    except Exception:
        pass

    # --- simulator markers: single regex pass over decompressed data ---
    try:
        if _SIM_RE.search(data):
            out["hurricane"] = True
    except Exception:
        pass
    return out