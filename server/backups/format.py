"""The backup file: encrypted in chunks, so a dump of any size passes through in a little
memory, and so a damaged, cut-short or tampered file is always noticed.

    header   BERABKP1 | key id (length byte + text) | chunk size (4 bytes) | salt (16 bytes)
    chunks   each is AES-256-GCM of up to `chunk size` bytes of dump, plus a 16 byte tag

The header names the key that made the file, so after a key change older backups still open
with their own key. Every chunk is tied to the header and to its position, and the last chunk is
marked as the last, so reordering, dropping or cutting off chunks fails the check.
The key for one file is derived from the configured key and the file's random salt.
"""

import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import BackupFailure

MAGIC = b"BERABKP1"
CHUNK_SIZE = 1024 * 1024
LARGEST_ACCEPTED_CHUNK = 64 * 1024 * 1024
TAG_SIZE = 16
SALT_SIZE = 16
DERIVATION_LABEL = b"bera-backup-file-key-v1"
FINAL = b"\x01"
NOT_FINAL = b"\x00"


def _file_key(key_text, salt):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=DERIVATION_LABEL).derive(
        key_text.encode()
    )


def _nonce(counter, final):
    return counter.to_bytes(8, "big") + b"\x00\x00\x00" + (FINAL if final else NOT_FINAL)


def _read_full(source, size):
    """Exactly `size` bytes, or fewer only at the end of the source."""
    parts, missing = [], size
    while missing:
        part = source.read(missing)
        if not part:
            break
        parts.append(part)
        missing -= len(part)
    return b"".join(parts)


class EncryptingReader:
    """Wraps a source of dump bytes; reading from it gives the encrypted file."""

    def __init__(self, source, key_id, key_text, chunk_size=CHUNK_SIZE):
        salt = os.urandom(SALT_SIZE)
        key_id_bytes = key_id.encode()
        self._header = (
            MAGIC + bytes([len(key_id_bytes)]) + key_id_bytes + struct.pack(">I", chunk_size) + salt
        )
        self._cipher = AESGCM(_file_key(key_text, salt))
        self._source = source
        self._chunk_size = chunk_size
        self._buffer = bytearray(self._header)
        self._counter = 0
        self._finished = False
        self._ahead = _read_full(source, chunk_size)  # one chunk ahead tells which is the last
        self.bytes_read = 0

    def _next_chunk(self):
        current = self._ahead
        following = (
            _read_full(self._source, self._chunk_size) if len(current) == self._chunk_size else b""
        )
        final = not following
        self._buffer += self._cipher.encrypt(_nonce(self._counter, final), current, self._header)
        self._counter += 1
        self._ahead = following
        self._finished = final

    def read(self, size=-1):
        while (size < 0 or len(self._buffer) < size) and not self._finished:
            self._next_chunk()
        count = len(self._buffer) if size < 0 else min(size, len(self._buffer))
        out = bytes(self._buffer[:count])
        del self._buffer[:count]
        self.bytes_read += len(out)
        return out


def _fail():
    return BackupFailure("decryption")


class DecryptingReader:
    """Wraps the stored file; reading from it gives the dump back. `keys` maps key ids to keys.
    Any problem (unknown key, wrong key, damage, cut-off) raises BackupFailure("decryption")."""

    def __init__(self, source, keys):
        self._source = source
        header = _read_full(source, len(MAGIC) + 1)
        if len(header) < len(MAGIC) + 1 or not header.startswith(MAGIC):
            raise _fail()
        key_id_bytes = _read_full(source, header[-1])
        rest = _read_full(source, 4 + SALT_SIZE)
        if len(key_id_bytes) != header[-1] or len(rest) != 4 + SALT_SIZE:
            raise _fail()
        self._header = header + key_id_bytes + rest
        (self._chunk_size,) = struct.unpack(">I", rest[:4])
        key_text = keys.get(key_id_bytes.decode(errors="replace"))
        if key_text is None or not 0 < self._chunk_size <= LARGEST_ACCEPTED_CHUNK:
            raise _fail()
        self.key_id = key_id_bytes.decode()
        self._cipher = AESGCM(_file_key(key_text, rest[4:]))
        self._buffer = bytearray()
        self._counter = 0
        self._finished = False
        self._sealed = self._chunk_size + TAG_SIZE
        self._ahead = _read_full(source, self._sealed)

    def _next_chunk(self):
        current = self._ahead
        following = _read_full(self._source, self._sealed) if len(current) == self._sealed else b""
        final = not following
        try:
            self._buffer += self._cipher.decrypt(
                _nonce(self._counter, final), current, self._header
            )
        except InvalidTag:
            raise _fail() from None
        self._counter += 1
        self._ahead = following
        self._finished = final

    def read(self, size=-1):
        while (size < 0 or len(self._buffer) < size) and not self._finished:
            self._next_chunk()
        count = len(self._buffer) if size < 0 else min(size, len(self._buffer))
        out = bytes(self._buffer[:count])
        del self._buffer[:count]
        return out
