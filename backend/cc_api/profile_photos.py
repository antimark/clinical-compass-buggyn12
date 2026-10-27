"""Bounded macOS ImageIO decode via installed sips; retain only critical PNG chunks.

Original uploads never persist. No client filename/path reaches a command.
"""
import binascii
from pathlib import Path
import struct
import subprocess
import tempfile

MAX_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 12_000_000
PNG = b'\x89PNG\r\n\x1a\n'


def dimensions(data):
    if data.startswith(PNG) and len(data) >= 33 and data[12:16] == b'IHDR':
        if b'acTL' in data: raise ValueError('Анимация не поддерживается')
        return 'image/png', *struct.unpack('>II', data[16:24])
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP' and len(data) >= 30:
        kind = data[12:16]
        if kind == b'VP8X':
            # Animation is excluded; native decoder must handle one bounded still.
            if data[20] & 2: raise ValueError('Анимация не поддерживается')
            return 'image/webp', 1+int.from_bytes(data[24:27],'little'), 1+int.from_bytes(data[27:30],'little')
        if kind == b'VP8L' and data[20] == 0x2f:
            bits = int.from_bytes(data[21:25], 'little')
            return 'image/webp', (bits & 0x3fff)+1, ((bits >> 14) & 0x3fff)+1
        if kind == b'VP8 ' and data[23:26] == b'\x9d\x01\x2a':
            width, height = struct.unpack('<HH', data[26:30])
            return 'image/webp', width & 0x3fff, height & 0x3fff
    if data.startswith(b'\xff\xd8'):
        pos = 2
        while pos+4 <= len(data):
            if data[pos] != 0xff: break
            while pos < len(data) and data[pos] == 0xff: pos += 1
            if pos >= len(data): break
            marker = data[pos]; pos += 1
            if marker in (0xd8, 0x01) or 0xd0 <= marker <= 0xd7: continue
            if marker in (0xd9, 0xda): break
            size = int.from_bytes(data[pos:pos+2], 'big')
            if size < 2 or pos+size > len(data): break
            if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf) and size >= 7:
                height, width = struct.unpack('>HH', data[pos+3:pos+7])
                return 'image/jpeg', width, height
            pos += size
    raise ValueError('Только корректные JPEG, PNG или WebP')


def clean_png(data):
    if not data.startswith(PNG): raise ValueError('Ошибка нормализации фото')
    result = bytearray(PNG); pos = 8; ended = False
    while pos+12 <= len(data):
        size = int.from_bytes(data[pos:pos+4], 'big'); kind = data[pos+4:pos+8]
        if size > MAX_BYTES or pos+12+size > len(data): raise ValueError('Повреждённое фото')
        chunk = data[pos+4:pos+8+size]
        crc = int.from_bytes(data[pos+8+size:pos+12+size], 'big')
        if binascii.crc32(chunk) & 0xffffffff != crc: raise ValueError('Повреждённое фото')
        if kind in (b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'):
            result.extend(data[pos:pos+12+size])
        if kind == b'IEND': ended=True; break
        pos += 12+size
    if not ended: raise ValueError('Повреждённое фото')
    return bytes(result)


def normalize(data, mime):
    if not data or len(data) > MAX_BYTES: raise ValueError('Фото должно быть от 1 байта до 2 МБ')
    actual, width, height = dimensions(data)
    if mime != actual: raise ValueError('Тип содержимого не соответствует MIME файла')
    if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION or width*height > MAX_PIXELS:
        raise ValueError('Фото слишком велико: до 4096 по стороне и 12 Мп')
    if not Path('/usr/bin/sips').is_file(): raise RuntimeError('ImageIO decoder unavailable')
    with tempfile.TemporaryDirectory(prefix='cc-photo-') as directory:
        source = Path(directory)/'input'; destination=Path(directory)/'output.png'
        source.write_bytes(data)
        try:
            # Independently inspect ImageIO's actual bounds before raster decoding.
            info=subprocess.run(['/usr/bin/sips','-g','pixelWidth','-g','pixelHeight',str(source)],
                check=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=4).stdout.decode()
            import re
            observed=re.findall(r'pixel(?:Width|Height): (\d+)',info)
            if observed != [str(width),str(height)]:raise ValueError('Некорректные размеры изображения')
            subprocess.run(['/usr/bin/sips','-s','format','png','-Z','512',str(source),'--out',str(destination)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            decoded = destination.read_bytes()
        except (subprocess.SubprocessError, OSError):
            raise ValueError('Не удалось прочитать изображение') from None
    if len(decoded) > MAX_BYTES: raise ValueError('Фото слишком велико после обработки')
    actual, width, height = dimensions(decoded)
    if actual != 'image/png' or width > 512 or height > 512: raise ValueError('Ошибка нормализации фото')
    return clean_png(decoded)
