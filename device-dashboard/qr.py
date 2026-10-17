"""Small pure-Python QR code encoder (byte mode, versions 1-10, ECC L/M).

`encode(text)` returns a square list of lists of booleans (True = dark),
without the quiet zone. It picks the smallest version that fits at ECC M,
falls back to ECC L, and chooses the mask with the lowest penalty score.
"""

from __future__ import annotations

# (ecc codewords per block, [(block count, data codewords per block), ...])
_BLOCKS = {
    "L": {
        1: (7, [(1, 19)]), 2: (10, [(1, 34)]), 3: (15, [(1, 55)]),
        4: (20, [(1, 80)]), 5: (26, [(1, 108)]), 6: (18, [(2, 68)]),
        7: (20, [(2, 78)]), 8: (24, [(2, 97)]), 9: (30, [(2, 116)]),
        10: (18, [(2, 68), (2, 69)]),
    },
    "M": {
        1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]),
        4: (18, [(2, 32)]), 5: (24, [(2, 43)]), 6: (16, [(4, 27)]),
        7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
        9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)]),
    },
}
_FORMAT_BITS = {"L": 1, "M": 0}
_ALIGNMENT = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}
MAX_VERSION = 10

# GF(256) with the QR polynomial x^8 + x^4 + x^3 + x^2 + 1.
_EXP = [0] * 512
_LOG = [0] * 256
_value = 1
for _index in range(255):
    _EXP[_index] = _value
    _LOG[_value] = _index
    _value <<= 1
    if _value & 0x100:
        _value ^= 0x11D
for _index in range(255, 512):
    _EXP[_index] = _EXP[_index - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree):
    poly = [1]
    for power in range(degree):
        poly = [a ^ _gf_mul(b, _EXP[power]) for a, b in zip(poly + [0], [0] + poly)]
    return poly


def _rs_remainder(data, degree):
    generator = _rs_generator(degree)
    remainder = [0] * degree
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        for index in range(degree):
            remainder[index] ^= _gf_mul(generator[index + 1], factor)
    return remainder


def _capacity(version, level):
    _, groups = _BLOCKS[level][version]
    return sum(count * size for count, size in groups)


def _choose(length):
    for level in ("M", "L"):
        for version in range(1, MAX_VERSION + 1):
            count_bits = 8 if version < 10 else 16
            if 4 + count_bits + 8 * length <= 8 * _capacity(version, level):
                return version, level
    raise ValueError("text too long for a version %d QR code" % MAX_VERSION)


def _codewords(payload, version, level):
    bits = []

    def put(value, width):
        bits.extend((value >> shift) & 1 for shift in range(width - 1, -1, -1))

    capacity = _capacity(version, level)
    put(0b0100, 4)
    put(len(payload), 8 if version < 10 else 16)
    for byte in payload:
        put(byte, 8)
    put(0, min(4, capacity * 8 - len(bits)))
    put(0, (-len(bits)) % 8)
    data = [int("".join(map(str, bits[index:index + 8])), 2) for index in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < capacity:
        data.append(pad)
        pad ^= 0xEC ^ 0x11

    ecc_len, groups = _BLOCKS[level][version]
    blocks = []
    offset = 0
    for count, size in groups:
        for _ in range(count):
            block = data[offset:offset + size]
            offset += size
            blocks.append((block, _rs_remainder(block, ecc_len)))
    result = []
    for index in range(max(len(block) for block, _ in blocks)):
        result.extend(block[index] for block, _ in blocks if index < len(block))
    for index in range(ecc_len):
        result.extend(ecc[index] for _, ecc in blocks)
    return result


def _mask_bit(mask, x, y):
    if mask == 0:
        return (x + y) % 2 == 0
    if mask == 1:
        return y % 2 == 0
    if mask == 2:
        return x % 3 == 0
    if mask == 3:
        return (x + y) % 3 == 0
    if mask == 4:
        return (x // 3 + y // 2) % 2 == 0
    if mask == 5:
        return x * y % 2 + x * y % 3 == 0
    if mask == 6:
        return (x * y % 2 + x * y % 3) % 2 == 0
    return ((x + y) % 2 + x * y % 3) % 2 == 0


class _Matrix:
    def __init__(self, version):
        self.version = version
        self.size = 17 + 4 * version
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]

    def set_function(self, x, y, dark):
        self.modules[y][x] = dark
        self.function[y][x] = True

    def draw_function_patterns(self, level):
        size = self.size
        for index in range(size):
            self.set_function(6, index, index % 2 == 0)
            self.set_function(index, 6, index % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.set_function(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        positions = _ALIGNMENT[self.version]
        last = len(positions) - 1
        for i, cx in enumerate(positions):
            for j, cy in enumerate(positions):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_function(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(level, 0)
        if self.version >= 7:
            remainder = self.version
            for _ in range(12):
                remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
            bits = self.version << 12 | remainder
            for index in range(18):
                dark = (bits >> index) & 1 == 1
                a, b = size - 11 + index % 3, index // 3
                self.set_function(a, b, dark)
                self.set_function(b, a, dark)

    def draw_format(self, level, mask):
        size = self.size
        data = _FORMAT_BITS[level] << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412

        def bit(index):
            return (bits >> index) & 1 == 1

        for index in range(6):
            self.set_function(8, index, bit(index))
        self.set_function(8, 7, bit(6))
        self.set_function(8, 8, bit(7))
        self.set_function(7, 8, bit(8))
        for index in range(9, 15):
            self.set_function(14 - index, 8, bit(index))
        for index in range(8):
            self.set_function(size - 1 - index, 8, bit(index))
        for index in range(8, 15):
            self.set_function(8, size - 15 + index, bit(index))
        self.set_function(8, size - 8, True)

    def place_data(self, codewords):
        size = self.size
        index = 0
        total = len(codewords) * 8
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vertical in range(size):
                y = size - 1 - vertical if upward else vertical
                for column in range(2):
                    x = right - column
                    if self.function[y][x]:
                        continue
                    if index < total:
                        self.modules[y][x] = (codewords[index >> 3] >> (7 - (index & 7))) & 1 == 1
                        index += 1
            right -= 2

    def apply_mask(self, mask):
        for y in range(self.size):
            for x in range(self.size):
                if not self.function[y][x] and _mask_bit(mask, x, y):
                    self.modules[y][x] = not self.modules[y][x]


def penalty(modules):
    """ISO 18004 mask penalty (rules N1-N4)."""
    size = len(modules)
    score = 0
    lines = [row for row in modules] + [[modules[y][x] for y in range(size)] for x in range(size)]
    finder_a = [True, False, True, True, True, False, True, False, False, False, False]
    finder_b = finder_a[::-1]
    for line in lines:
        run = 1
        for index in range(1, size):
            if line[index] == line[index - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
        for index in range(size - 10):
            window = line[index:index + 11]
            if window == finder_a or window == finder_b:
                score += 40
    for y in range(size - 1):
        for x in range(size - 1):
            color = modules[y][x]
            if color == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                score += 3
    dark = sum(sum(1 for value in row if value) for row in modules)
    total = size * size
    score += 10 * (abs(dark * 20 - total * 10) // total)
    return score


def encode(text, mask=None):
    payload = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    version, level = _choose(len(payload))
    codewords = _codewords(payload, version, level)
    best = None
    for candidate in range(8) if mask is None else [mask]:
        matrix = _Matrix(version)
        matrix.draw_function_patterns(level)
        matrix.place_data(codewords)
        matrix.apply_mask(candidate)
        matrix.draw_format(level, candidate)
        score = penalty(matrix.modules)
        if best is None or score < best[0]:
            best = (score, matrix.modules)
    return best[1]


def wifi_payload(ssid, password, security="WPA", hidden=False):
    """Standard `WIFI:` payload understood by iOS and Android cameras."""
    def escape(value):
        return "".join("\\" + char if char in "\\;,:\"" else char for char in value)

    if not password:
        security = "nopass"
    parts = ["WIFI:T:%s" % security, "S:%s" % escape(ssid)]
    if password:
        parts.append("P:%s" % escape(password))
    if hidden:
        parts.append("H:true")
    return ";".join(parts) + ";;"
