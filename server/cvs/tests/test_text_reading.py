import io
import subprocess
import unicodedata

import pytest
from docx import Document
from docx.shared import Pt
from lxml import etree

from cvs import text_reading
from cvs.file_checks import check_cv_file
from cvs.tests.files import make_pdf
from cvs.text_reading import CvTextUnreadable, clean_text, read_text, trim_text
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache

pytestmark = pytest.mark.django_db

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def word(build):
    document = Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def short_samples_are_fine():
    """The sample files here are short; the real minimum is tested in TestFailures."""
    set_setting("reading.min_characters", 5)


def lines_of(result):
    return [line for line in result.text.splitlines() if line.strip()]


class TestPdfSamples:
    def test_a_plain_cv_reads_in_order(self):
        data = make_pdf(
            commands=(
                "BT /F1 18 Tf 72 740 Td (Jane Doe) Tj ET\n"
                "BT /F1 12 Tf 72 700 Td (Senior Backend Engineer) Tj ET\n"
                "BT /F1 12 Tf 72 680 Td (Built payment systems in Python) Tj ET\n"
            )
        )
        assert lines_of(read_text("pdf", data)) == [
            "Jane Doe",
            "Senior Backend Engineer",
            "Built payment systems in Python",
        ]

    def test_a_two_column_page_reads_one_column_after_the_other(self):
        rows = [
            ("Skills", "Experience"),
            ("Python and Django", "Acme Corp 2019 to 2023"),
            ("PostgreSQL", "Built billing systems"),
            ("Teamwork", "Led a team of five"),
        ]
        commands, y = "", 700
        for left, right in rows:  # written row by row, as many templates do
            commands += f"BT /F1 12 Tf 72 {y} Td ({left}) Tj ET\n"
            commands += f"BT /F1 12 Tf 330 {y} Td ({right}) Tj ET\n"
            y -= 20
        text = read_text("pdf", make_pdf(commands=commands)).text
        assert text.index("Teamwork") < text.index("Experience")
        assert text.index("Python and Django") < text.index("PostgreSQL") < text.index("Teamwork")
        assert text.index("Acme Corp") < text.index("Built billing") < text.index("Led a team")

    def test_accented_letters_are_kept(self):
        data = make_pdf(
            commands=(
                "BT /F1 12 Tf 72 700 Td (Jos\\351 Mu\\361oz, \\334bersetzer, Fran\\347ois) Tj ET"
            )
        )
        assert read_text("pdf", data).text == "José Muñoz, Übersetzer, François"

    def test_only_the_first_fifteen_pages_are_read(self):
        data = make_pdf(pages=16, page_texts=[f"Page number {n} of the CV" for n in range(1, 17)])
        text = read_text("pdf", data).text
        assert "Page number 1 of" in text and "Page number 15 of" in text
        assert "Page number 16 of" not in text

    def test_the_pages_read_come_from_platform_settings(self):
        set_setting("uploads.cv_pages_read", 2)
        data = make_pdf(pages=3, page_texts=[f"Page number {n} of the CV" for n in range(1, 4)])
        text = read_text("pdf", data).text
        assert "Page number 2 of" in text and "Page number 3 of" not in text

    def test_a_pdf_that_passes_the_file_checks_reads(self):
        data = make_pdf()
        assert check_cv_file("cv.pdf", data).problem is None
        assert read_text("pdf", data).text == "Experienced backend engineer"


class TestWordSamples:
    def test_headings_lists_and_paragraphs_keep_their_shape(self):
        def build(document):
            document.add_heading("Jane Doe", level=0)
            document.add_heading("Experience", level=1)
            document.add_paragraph("Acme Corp, backend engineer")
            document.add_paragraph("Built billing systems", style="List Bullet")
            document.add_paragraph("Led a team of five", style="List Bullet")

        result = read_text("docx", word(build))
        assert lines_of(result) == [
            "Jane Doe",
            "Experience",
            "Acme Corp, backend engineer",
            "- Built billing systems",
            "- Led a team of five",
        ]

    def test_tables_are_read_row_by_row_in_place(self):
        def build(document):
            document.add_paragraph("Skills")
            table = document.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Python"
            table.cell(0, 1).text = "Expert"
            table.cell(1, 0).text = "SQL"
            table.cell(1, 1).text = "Advanced"
            document.add_paragraph("References on request")

        assert lines_of(read_text("docx", word(build))) == [
            "Skills",
            "Python | Expert",
            "SQL | Advanced",
            "References on request",
        ]

    def test_a_merged_cell_is_read_once(self):
        def build(document):
            table = document.add_table(rows=1, cols=3)
            merged = table.cell(0, 0).merge(table.cell(0, 1))
            merged.text = "Languages"
            table.cell(0, 2).text = "English, French"

        assert lines_of(read_text("docx", word(build))) == ["Languages | English, French"]

    def test_contact_details_in_the_page_header_are_included(self):
        def build(document):
            document.sections[0].header.paragraphs[0].text = "jane@example.com | +1 555 010 0100"
            document.add_paragraph("Backend engineer with eight years of experience in payments")

        assert lines_of(read_text("docx", word(build)))[0] == "jane@example.com | +1 555 010 0100"

    def test_text_boxes_are_read_once_not_twice(self):
        def build(document):
            document.add_paragraph("Backend engineer with eight years of experience in payments")
            run = document.add_paragraph().add_run()
            xml = (
                f'<mc:AlternateContent xmlns:mc="{MC}" xmlns:w="{W}">'
                f"<mc:Choice><w:txbxContent><w:p><w:r><w:t>Phone 555 010 0100</w:t></w:r></w:p>"
                f"</w:txbxContent></mc:Choice>"
                f"<mc:Fallback><w:txbxContent><w:p><w:r><w:t>Phone 555 010 0100</w:t></w:r></w:p>"
                f"</w:txbxContent></mc:Fallback></mc:AlternateContent>"
            )
            run._r.append(etree.fromstring(xml))

        assert read_text("docx", word(build)).text.count("Phone 555 010 0100") == 1

    @pytest.mark.parametrize(
        "line",
        [
            "José Müller, Straße 5, Zürich",
            "Фёдор Достоевский — инженер",
            "李小龍，高級軟件工程師",
            "مهندس برمجيات بخبرة ثماني سنوات",
            "ภาษาไทย และ 日本語 のテキスト",
            "Skills: C++ • Python – SQL",
        ],
    )
    def test_many_languages_and_scripts_are_read(self, line):
        def build(document):
            document.add_paragraph(line)

        assert read_text("docx", word(build)).text == unicodedata.normalize("NFKC", line)

    def test_odd_spaces_and_invisible_characters_are_made_ordinary(self):
        def build(document):
            document.add_paragraph("Senior engineer​ at Acme﻿ Corp")

        assert read_text("docx", word(build)).text == "Senior engineer at Acme Corp"

    def test_fonts_and_formatting_do_not_matter(self):
        def build(document):
            run = document.add_paragraph().add_run("Backend engineer, Python and SQL experts")
            run.bold = True
            run.font.size = Pt(20)

        assert read_text("docx", word(build)).text == "Backend engineer, Python and SQL experts"


class TestFailures:
    @pytest.mark.parametrize("file_type", ["pdf", "docx"])
    def test_garbage_is_unreadable(self, file_type):
        with pytest.raises(CvTextUnreadable) as caught:
            read_text(file_type, b"this is not a real file at all" * 10)
        assert caught.value.message == "We could not read this file."
        assert caught.value.code == "cv_unreadable"

    def test_a_pdf_with_no_text_is_unreadable(self):
        with pytest.raises(CvTextUnreadable):
            read_text("pdf", make_pdf(text=" "))

    def test_an_empty_word_file_is_unreadable(self):
        with pytest.raises(CvTextUnreadable):
            read_text("docx", word(lambda document: None))

    def test_almost_no_text_is_unreadable(self):
        set_setting("reading.min_characters", 30)
        with pytest.raises(CvTextUnreadable):
            read_text("docx", word(lambda document: document.add_paragraph("Hi there")))

    def test_the_default_minimum_is_thirty_letters_and_digits(self):
        set_setting("reading.min_characters", 30)
        assert read_text("docx", word(lambda d: d.add_paragraph("a" * 30))).text == "a" * 30
        with pytest.raises(CvTextUnreadable):
            read_text("docx", word(lambda document: document.add_paragraph("a" * 29)))

    def test_the_minimum_comes_from_platform_settings(self):
        set_setting("reading.min_characters", 2)
        assert read_text("docx", word(lambda document: document.add_paragraph("Hi"))).text == "Hi"
        set_setting("reading.min_characters", 3)
        with pytest.raises(CvTextUnreadable):
            read_text("docx", word(lambda document: document.add_paragraph("Hi")))

    def test_a_pdf_whose_font_has_no_text_map_is_unreadable(self):
        data = make_pdf(commands="BT /F1 12 Tf 72 700 Td (\\000\\001\\002) Tj ET")
        with pytest.raises(CvTextUnreadable):
            read_text("pdf", data)

    def test_cid_placeholders_are_not_kept_as_text(self):
        assert clean_text("(cid:12)(cid:99)") == ""

    def test_the_message_is_friendly_and_leaks_nothing(self):
        try:
            read_text("pdf", b"%PDF-1.7 broken")
        except CvTextUnreadable as error:
            assert error.message == "We could not read this file."
            assert error.details is None

    def test_a_pdf_that_hangs_the_reader_is_stopped(self, monkeypatch):
        def hang(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="reader", timeout=1)

        monkeypatch.setattr(text_reading.subprocess, "run", hang)
        with pytest.raises(CvTextUnreadable):
            read_text("pdf", make_pdf())

    def test_a_pdf_that_unpacks_enormously_cannot_use_up_the_servers_memory(self):
        set_setting("reading.worker_memory_mb", 256)
        data = make_pdf(content=b"BT /F1 12 Tf 72 700 Td (a) Tj ET\n" * (12 * 1024 * 1024))
        assert len(data) < 3 * 1024 * 1024  # small to send, about 400 MB once unpacked
        with pytest.raises(CvTextUnreadable):
            read_text("pdf", data)

    def test_the_reader_gets_no_secrets_from_the_environment(self, monkeypatch):
        seen = {}
        real = subprocess.run

        def spy(*args, **kwargs):
            seen.update(kwargs)
            return real(*args, **kwargs)

        monkeypatch.setattr(text_reading.subprocess, "run", spy)
        read_text("pdf", make_pdf())
        assert seen["env"] == {}
        assert seen["cwd"] == "/"


class TestLongText:
    def test_long_text_is_trimmed_at_a_word_and_flagged(self):
        set_setting("reading.max_characters", 1000)
        sentence = "Experienced backend engineer working with Python. "

        def build(document):
            for _ in range(60):
                document.add_paragraph(sentence)

        result = read_text("docx", word(build))
        assert result.trimmed is True
        assert len(result.text) <= 1000
        assert result.text.endswith(("Python.", "Python", "engineer", "working", "with", "backend"))

    def test_text_within_the_limit_is_not_flagged(self):
        result = read_text("docx", word(lambda d: d.add_paragraph("Backend engineer, Python")))
        assert result.trimmed is False

    def test_a_caller_may_ask_for_a_shorter_limit(self):
        text = "word " * 100

        def build(document):
            document.add_paragraph(text)

        result = read_text("docx", word(build), max_characters=50)
        assert result.trimmed is True and len(result.text) <= 50

    def test_trimming_never_cuts_a_character_from_its_accent(self):
        text = "a" * 9 + "é" + "b" * 20  # "é" written as e plus a combining accent
        trimmed, was_cut = trim_text(text, 10)
        assert was_cut and not trimmed.endswith("́") and trimmed == "a" * 9

    def test_trimming_keeps_whole_words_when_it_can(self):
        trimmed, _ = trim_text("alpha beta gamma delta", 14)
        assert trimmed == "alpha beta"

    def test_a_single_very_long_word_is_cut_at_the_limit(self):
        trimmed, was_cut = trim_text("x" * 5000, 1000)
        assert was_cut and len(trimmed) == 1000

    def test_the_default_limit_comes_from_platform_settings(self):
        set_setting("reading.max_characters", 1000)
        long_text = "word " * 500

        def build(document):
            document.add_paragraph(long_text)

        assert read_text("docx", word(build)).trimmed is True


class TestCleaning:
    def test_ligatures_and_width_variants_are_made_ordinary(self):
        assert clean_text("oﬃce ＡＢＣ ﬁrst") == "office ABC first"

    def test_control_characters_and_nul_bytes_are_removed(self):
        assert clean_text("a\x00b\x07c\x1fd") == "abcd"

    def test_page_breaks_become_blank_lines_and_runs_of_blank_lines_shrink(self):
        assert clean_text("one\x0ctwo\n\n\n\n\nthree") == "one\n\ntwo\n\nthree"

    def test_spaces_around_line_breaks_are_tidied(self):
        assert clean_text("one   \n   two\t\tthree") == "one\ntwo three"

    def test_text_that_cannot_be_encoded_is_still_returned(self):
        assert clean_text("a\ud800b").encode("utf-8", errors="replace")
