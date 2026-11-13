"""Small real files for the tests: a text PDF, a Word file, and the damaged, protected and
risky variants of each. Nothing here is opened or run by anything but the checker."""

import io
import zipfile
import zlib


def make_pdf(
    pages=1, text="Experienced backend engineer", root_extra="", page_extra="", content=None
):
    """A valid PDF whose pages each draw `text`. `root_extra` and `page_extra` add entries to
    the catalog and to every page (for the scripts and actions the checker must refuse).
    `content` replaces the drawing commands of every page with a compressed stream."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled in below, once the pages exist
    pages_object = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_numbers = []
    for _ in range(pages):
        if content is None:
            stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
            header = b"<< /Length %d >>" % len(stream)
        else:
            stream = zlib.compress(content)
            header = b"<< /Length %d /Filter /FlateDecode >>" % len(stream)
        content_object = add(b"%s\nstream\n%s\nendstream" % (header, stream))
        page_numbers.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_object} 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {content_object} 0 R /Resources << /Font << /F1 {font} 0 R >> >> "
                    f"{page_extra} >>"
                ).encode()
            )
        )
    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects[pages_object - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_object} 0 R {root_extra} >>".encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    return out.getvalue()


def make_docx(pages=None, extra_parts=None, content_types="<Types/>"):
    """A Word file. `pages` is written to its properties; `extra_parts` maps part names to
    contents (for macros and embedded objects)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", "<w:document/>")
        if pages is not None:
            archive.writestr("docProps/app.xml", f"<Properties><Pages>{pages}</Pages></Properties>")
        for name, content in (extra_parts or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def make_encrypted_docx():
    """What Word saves when a password is set: an old-style container holding the encrypted
    package."""
    return OLE_SIGNATURE + b"\x00" * 64 + "EncryptedPackage".encode("utf-16-le") + b"\x00" * 64


def make_old_doc():
    return OLE_SIGNATURE + b"\x00" * 200
