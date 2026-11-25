import io

import pytest

from backups.errors import BackupFailure
from backups.format import CHUNK_SIZE, DecryptingReader, EncryptingReader

KEY = "test-only-backup-key-one-aaaa1111bbbb2222"
OTHER_KEY = "test-only-backup-key-two-cccc3333dddd4444"
SMALL = 16
HEADER_SIZE = 8 + 1 + 2 + 4 + 16  # magic, id length, "k1", chunk size, salt


def encrypt(data, key_id="k1", key=KEY, chunk_size=SMALL):
    return EncryptingReader(io.BytesIO(data), key_id, key, chunk_size).read()


def decrypt(blob, keys=None):
    return DecryptingReader(io.BytesIO(blob), {"k1": KEY} if keys is None else keys).read()


@pytest.mark.parametrize("size", [0, 1, SMALL - 1, SMALL, SMALL + 1, SMALL * 5, SMALL * 5 + 3])
def test_every_size_comes_back_exactly(size):
    data = bytes(range(256)) * 3
    data = data[:size]
    assert decrypt(encrypt(data)) == data


def test_the_normal_chunk_size_works_across_chunks():
    data = b"fake-dump-bytes" * (CHUNK_SIZE // 5)
    assert decrypt(encrypt(data, chunk_size=CHUNK_SIZE)) == data


def test_the_file_hides_the_content_and_differs_each_time():
    data = b"A fake candidate name appears here" * 4
    first, second = encrypt(data), encrypt(data)
    assert data not in first and first != second


def test_reading_in_small_pieces_gives_the_same_result():
    data = b"x" * 100
    reader = DecryptingReader(io.BytesIO(encrypt(data)), {"k1": KEY})
    pieces = []
    while piece := reader.read(7):
        pieces.append(piece)
    assert b"".join(pieces) == data


def test_the_header_names_the_key_that_made_the_file():
    assert DecryptingReader(io.BytesIO(encrypt(b"abc")), {"k1": KEY}).key_id == "k1"


def test_after_a_key_change_an_older_file_opens_with_its_own_key():
    old_file = encrypt(b"made last year", key_id="k1", key=KEY)
    new_file = encrypt(b"made today", key_id="k2", key=OTHER_KEY)
    keys = {"k2": OTHER_KEY, "k1": KEY}
    assert decrypt(old_file, keys) == b"made last year"
    assert decrypt(new_file, keys) == b"made today"


@pytest.mark.parametrize(
    "keys",
    [{"k1": OTHER_KEY}, {"k2": KEY}, {}],
    ids=["wrong key", "unknown key id", "no keys"],
)
def test_a_wrong_or_unknown_key_is_refused(keys):
    with pytest.raises(BackupFailure) as caught:
        decrypt(encrypt(b"abc" * 20), keys)
    assert caught.value.kind == "decryption"


def damaged(blob):
    changed = bytearray(blob)
    changed[-5] ^= 1
    return bytes(changed)


def test_a_changed_byte_is_noticed():
    with pytest.raises(BackupFailure):
        decrypt(damaged(encrypt(b"abc" * 20)))


def test_a_file_cut_short_at_a_chunk_boundary_is_noticed():
    blob = encrypt(b"x" * (SMALL * 4 + 1))
    with pytest.raises(BackupFailure):
        decrypt(blob[: HEADER_SIZE + 3 * (SMALL + 16)])


def test_chunks_cannot_be_swapped_or_dropped():
    blob = encrypt(b"x" * (SMALL * 4 + 1))
    header, chunks = blob[:HEADER_SIZE], blob[HEADER_SIZE:]
    size = SMALL + 16
    parts = [chunks[i : i + size] for i in range(0, len(chunks), size)]
    for changed in ([parts[1], parts[0], *parts[2:]], [parts[0], *parts[2:]]):
        with pytest.raises(BackupFailure):
            decrypt(header + b"".join(changed))


@pytest.mark.parametrize("blob", [b"", b"short", b"NOTABACKUP" + b"x" * 60])
def test_something_that_is_not_a_backup_is_refused(blob):
    with pytest.raises(BackupFailure):
        decrypt(blob)


def test_the_source_is_read_in_chunks_not_all_at_once():
    class Counting(io.BytesIO):
        largest = 0

        def read(self, size=-1):
            Counting.largest = max(Counting.largest, size)
            return super().read(size)

    reader = EncryptingReader(Counting(b"x" * 1000), "k1", KEY, SMALL)
    while reader.read(10):
        pass
    assert Counting.largest <= SMALL
