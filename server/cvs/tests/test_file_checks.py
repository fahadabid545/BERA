import io
import zipfile

import pytest
from pypdf import PdfWriter

from cvs import file_checks
from cvs.file_checks import check_cv_file
from cvs.tests.files import (
    make_docx,
    make_encrypted_docx,
    make_old_doc,
    make_pdf,
)
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache

pytestmark = pytest.mark.django_db


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def code_of(result):
    return result.problem.code if result.problem else None


class TestGoodFiles:
    def test_a_text_pdf_is_accepted_with_its_page_count(self):
        result = check_cv_file("cv.pdf", make_pdf(pages=2))
        assert result.problem is None
        assert (result.file_type, result.page_count, result.notice) == ("pdf", 2, "")

    def test_a_word_file_is_accepted(self):
        result = check_cv_file("cv.docx", make_docx(pages=3))
        assert result.problem is None
        assert (result.file_type, result.page_count) == ("docx", 3)

    def test_a_word_file_that_does_not_state_its_pages_is_accepted_without_a_count(self):
        assert check_cv_file("cv.docx", make_docx()).page_count is None

    def test_the_name_may_be_in_capitals(self):
        assert check_cv_file("CV.PDF", make_pdf()).problem is None

    def test_a_little_data_before_the_pdf_signature_is_allowed(self):
        assert check_cv_file("cv.pdf", b"\n\n" + make_pdf()).problem is None


class TestPageCount:
    def test_fifteen_pages_are_all_read_without_a_notice(self):
        assert check_cv_file("cv.pdf", make_pdf(pages=15)).notice == ""

    def test_more_than_fifteen_pages_are_accepted_and_flagged(self):
        result = check_cv_file("cv.pdf", make_pdf(pages=16))
        assert result.problem is None
        assert result.page_count == 16
        assert result.notice == "This CV has 16 pages. Only the first 15 are read."

    def test_a_long_word_file_is_flagged_too(self):
        result = check_cv_file("cv.docx", make_docx(pages=40))
        assert result.notice == "This CV has 40 pages. Only the first 15 are read."

    def test_the_number_of_pages_read_comes_from_platform_settings(self):
        set_setting("uploads.cv_pages_read", 3)
        assert check_cv_file("cv.pdf", make_pdf(pages=4)).notice == (
            "This CV has 4 pages. Only the first 3 are read."
        )


class TestRealTypeFromContent:
    def test_a_word_file_renamed_to_pdf_is_refused(self):
        result = check_cv_file("cv.pdf", make_docx())
        assert code_of(result) == "type_mismatch"
        assert "not really a PDF file" in result.problem.message

    def test_a_pdf_renamed_to_docx_is_refused(self):
        assert code_of(check_cv_file("cv.docx", make_pdf())) == "type_mismatch"

    @pytest.mark.parametrize(
        "content",
        [
            b"MZ\x90\x00" + b"\x00" * 100,
            b"#!/bin/sh\necho hi\n",
            b"plain text",
            b"\x89PNG\r\n\x1a\n",
        ],
    )
    @pytest.mark.parametrize("name", ["cv.pdf", "cv.docx"])
    def test_programs_scripts_images_and_text_renamed_are_refused(self, name, content):
        assert code_of(check_cv_file(name, content)) == "type_mismatch"

    def test_an_old_word_document_is_not_accepted_as_docx(self):
        assert code_of(check_cv_file("cv.docx", make_old_doc())) == "type_mismatch"

    def test_a_zip_that_is_not_a_word_file_is_refused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "x")
        assert code_of(check_cv_file("cv.docx", buffer.getvalue())) == "type_mismatch"

    def test_a_double_extension_is_judged_by_the_last_one(self):
        assert code_of(check_cv_file("cv.pdf.exe", make_pdf())) == "wrong_type"


class TestNameAndSize:
    @pytest.mark.parametrize("name", ["cv.txt", "cv", "cv.doc", "cv.exe", ".pdf.bak"])
    def test_other_types_are_refused(self, name):
        assert code_of(check_cv_file(name, make_pdf())) == "wrong_type"

    def test_empty(self):
        result = check_cv_file("cv.pdf", b"")
        assert (result.problem.code, result.problem.message) == ("empty", "This file is empty.")

    def test_oversized(self):
        set_setting("uploads.max_file_size_mb", 1)
        result = check_cv_file("cv.pdf", make_pdf() + b"0" * (1024 * 1024))
        assert (result.problem.code, result.problem.message) == (
            "too_large",
            "This file is larger than 1 MB.",
        )

    def test_exactly_the_size_limit_is_allowed(self):
        set_setting("uploads.max_file_size_mb", 1)
        data = make_pdf()
        data += b"0" * (1024 * 1024 - len(data))
        assert check_cv_file("cv.pdf", data).problem is None


class TestDamaged:
    def test_a_pdf_that_starts_right_but_is_cut_off(self):
        assert code_of(check_cv_file("cv.pdf", make_pdf()[:200])) == "damaged"

    def test_a_pdf_with_only_a_header(self):
        result = check_cv_file("cv.pdf", b"%PDF-1.4\n")
        assert (result.problem.code, result.problem.message) == (
            "damaged",
            "This file looks damaged and could not be read.",
        )

    def test_a_pdf_with_garbage_inside(self):
        assert (
            code_of(check_cv_file("cv.pdf", b"%PDF-1.7\n" + b"\xff\x00garbage" * 200)) == "damaged"
        )

    def test_a_cut_off_word_file(self):
        assert code_of(check_cv_file("cv.docx", make_docx()[:60])) == "damaged"

    def test_a_word_file_missing_its_content_types(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", "<w:document/>")
        assert code_of(check_cv_file("cv.docx", buffer.getvalue())) == "damaged"


class TestPasswordProtected:
    def test_an_encrypted_pdf(self):
        writer = PdfWriter()
        writer.add_blank_page(612, 792)
        writer.encrypt("secret")
        buffer = io.BytesIO()
        writer.write(buffer)
        result = check_cv_file("cv.pdf", buffer.getvalue())
        assert (result.problem.code, result.problem.message) == (
            "password_protected",
            "This file is password protected. Remove the password and upload it again.",
        )

    def test_an_encrypted_word_file(self):
        assert code_of(check_cv_file("cv.docx", make_encrypted_docx())) == "password_protected"


class TestScannedPdf:
    def test_a_pdf_with_no_text_is_refused_with_the_scanned_message(self):
        writer = PdfWriter()
        writer.add_blank_page(612, 792)
        buffer = io.BytesIO()
        writer.write(buffer)
        result = check_cv_file("scan.pdf", buffer.getvalue())
        assert (result.problem.code, result.problem.message) == (
            "scanned_image",
            "This looks like a scanned image. Please upload a text-based PDF or a Word file.",
        )

    def test_a_pdf_with_blank_text_is_refused_too(self):
        assert code_of(check_cv_file("scan.pdf", make_pdf(text="   "))) == "scanned_image"


class TestMacrosScriptsAndEmbeddedContent:
    def test_a_word_file_with_macros(self):
        data = make_docx(extra_parts={"word/vbaProject.bin": b"\x00macro"})
        result = check_cv_file("cv.docx", data)
        assert code_of(result) == "active_content"
        assert "macros, scripts or embedded content" in result.problem.message

    def test_the_macro_part_name_is_matched_in_any_case(self):
        data = make_docx(extra_parts={"WORD/VBAPROJECT.BIN": b"x"})
        assert code_of(check_cv_file("cv.docx", data)) == "active_content"

    def test_a_macro_enabled_file_renamed_to_docx(self):
        types = (
            '<Types><Override ContentType="application/vnd.ms-word.document.'
            'macroEnabled.main+xml"/></Types>'
        )
        assert code_of(check_cv_file("cv.docx", make_docx(content_types=types))) == "active_content"

    def test_a_word_file_with_an_embedded_object(self):
        data = make_docx(extra_parts={"word/embeddings/oleObject1.bin": b"x"})
        assert code_of(check_cv_file("cv.docx", data)) == "active_content"

    def test_a_pdf_with_javascript_on_open(self):
        data = make_pdf(root_extra="/OpenAction << /S /JavaScript /JS (app.alert\\(1\\)) >>")
        assert code_of(check_cv_file("cv.pdf", data)) == "active_content"

    def test_a_pdf_with_a_launch_action(self):
        data = make_pdf(root_extra="/OpenAction << /S /Launch /F (cmd.exe) >>")
        assert code_of(check_cv_file("cv.pdf", data)) == "active_content"

    def test_a_pdf_with_document_level_scripts(self):
        data = make_pdf(root_extra="/Names << /JavaScript << /Names [] >> >>")
        assert code_of(check_cv_file("cv.pdf", data)) == "active_content"

    def test_a_pdf_with_attached_files(self):
        data = make_pdf(root_extra="/Names << /EmbeddedFiles << /Names [] >> >>")
        assert code_of(check_cv_file("cv.pdf", data)) == "active_content"

    def test_a_pdf_with_page_actions(self):
        data = make_pdf(page_extra="/AA << /O << /S /JavaScript /JS (x) >> >>")
        assert code_of(check_cv_file("cv.pdf", data)) == "active_content"

    def test_a_pdf_whose_text_merely_mentions_javascript_is_fine(self):
        assert (
            check_cv_file("cv.pdf", make_pdf(text="I know JavaScript and Launch")).problem is None
        )


class TestSafety:
    def test_a_word_file_that_would_unpack_enormously_is_refused_unopened(self):
        set_setting("uploads.max_unpacked_mb", 1)
        data = make_docx(extra_parts={"word/media/big.bin": b"0" * (3 * 1024 * 1024)})
        assert len(data) < 100 * 1024  # small to send, large once unpacked
        assert code_of(check_cv_file("cv.docx", data)) == "damaged"

    def test_a_word_file_with_too_many_parts_is_refused(self):
        set_setting("uploads.max_archive_entries", 5)
        parts = {f"word/media/{n}.png": b"x" for n in range(10)}
        assert code_of(check_cv_file("cv.docx", make_docx(extra_parts=parts))) == "damaged"

    def test_a_pdf_stream_that_unpacks_enormously_is_refused(self):
        commands = b"BT /F1 12 Tf 72 720 Td (a) Tj ET\n" * (70 * 1024)  # about 2 MB unpacked
        data = make_pdf(content=commands)
        assert len(data) < 100 * 1024  # small to send, large once unpacked
        assert check_cv_file("cv.pdf", data).problem is None  # fine under the default cap
        set_setting("uploads.max_unpacked_mb", 1)
        assert code_of(check_cv_file("cv.pdf", data)) == "damaged"

    def test_nothing_in_the_checks_runs_or_opens_a_file_as_a_program(self):
        from pathlib import Path

        source = "".join(
            path.read_text() for path in Path(file_checks.__file__).parent.glob("*_checks.py")
        )
        for forbidden in ("subprocess", "os.system", "eval(", "exec(", "pickle", "popen"):
            assert forbidden not in source

    def test_the_checks_never_log_the_file_or_its_name(self, caplog):
        with caplog.at_level("DEBUG"):
            check_cv_file("Jane Doe CV.pdf", b"%PDF-1.7\n" + b"Jane Doe secret" * 50)
        assert "Jane Doe" not in caplog.text
