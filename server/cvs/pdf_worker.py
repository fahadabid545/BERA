"""Reads the text of a PDF in a separate, limited process. Run as a script by `text_reading.py`:

    python -I pdf_worker.py <memory limit in MB> <pages to read>   (the PDF arrives on stdin)

A broken or hostile PDF can ask for huge amounts of memory or time. Running the reader in its
own process, with a memory limit here and a time limit on the caller's side, means the worst
that can happen is that this process dies and the file is reported as unreadable."""

import io
import resource
import sys

BYTES_PER_MEGABYTE = 1024 * 1024


def main():
    memory_limit = int(sys.argv[1]) * BYTES_PER_MEGABYTE
    pages = int(sys.argv[2])
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    data = sys.stdin.buffer.read()

    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams

    # The layout analysis puts a two-column page in reading order, column by column.
    text = extract_text(io.BytesIO(data), laparams=LAParams(), maxpages=pages)
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
