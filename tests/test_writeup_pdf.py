"""Тесты конвертера Markdown → Typst → PDF (scripts/writeup_pdf.py).

Запуск: .venv/bin/python -I -m unittest discover -s tests -p 'test_writeup_pdf.py'
"""

import contextlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.writeup_pdf as writeup_pdf  # noqa: E402
from scripts.writeup_pdf import (  # noqa: E402
    DEFAULT_TYPST,
    GITHUB_BRANCH,
    CodeBlock,
    ConversionError,
    Context,
    Link,
    ListBlock,
    Paragraph,
    Table,
    build_pdf,
    default_ref,
    drop_sections,
    escape_text,
    main,
    markdown_to_typst,
    parse_blocks,
    parse_inline,
    TABLE_CODE_PT,
    TEXT_WIDTH_PT,
    plain_text,
    render_inline,
    resolve_link,
    soft_breaks,
    strip_html_comments,
    table_columns,
)

TYPST = shutil.which("typst") or (DEFAULT_TYPST if Path(DEFAULT_TYPST).exists() else None)
GIT = shutil.which("git")
# Тесты не зависят от HEAD рабочего репозитория: ref всегда передаётся явно.
REF = "deadbeef" * 5
BLOB = f"https://github.com/suprend/tlab-recsys-2026-task1/blob/{REF}"
TREE = f"https://github.com/suprend/tlab-recsys-2026-task1/tree/{REF}"


def _flatten(node) -> str:
    """Текст, который Typst реально покажет, из JSON-дерева content."""
    if isinstance(node, list):
        return "".join(_flatten(x) for x in node)
    if not isinstance(node, dict):
        return ""
    func = node.get("func")
    if func in ("text", "symbol", "raw"):
        return node.get("text", "")
    if func == "space":
        return " "
    if func == "smartquote":
        return "<smartquote>"
    if func == "linebreak":
        return "\n"
    if func == "item":  # нумерованный пункт: значит, Typst принял текст за список
        return f"<item>{_flatten(node.get('body'))}"
    parts = []
    for key in ("children", "body"):
        if key in node:
            parts.append(_flatten(node[key]))
    return "".join(parts)


def typst_plain(markup: str) -> str:
    """Скомпилировать фрагмент разметки и вернуть видимый текст."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.typ"
        path.write_text(f"#metadata([{markup}]) <probe>\n", encoding="utf-8")
        result = subprocess.run(
            [TYPST, "query", str(path), "<probe>", "--field", "value", "--one"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if result.returncode != 0:
        raise AssertionError(f"typst не разобрал разметку:\n{markup}\n{result.stderr}")
    return _flatten(json.loads(result.stdout))


def typst_heights(width_pt: float, *markups: str) -> list[float]:
    """Высота каждого фрагмента в блоке шириной ``width_pt`` (шрифты таблиц)."""
    items = "".join(f"[{m}], " for m in markups)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "measure.typ"
        path.write_text(
            '#set text(font: ("PT Sans", "Helvetica Neue"), size: 8.5pt)\n'
            '#show raw: set text(font: ("PT Mono", "Menlo", "DejaVu Sans Mono"))\n'
            f"#context [#metadata(({items}).map(m => measure(block(width: {width_pt}pt, m)).height.pt())) <probe>]\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [TYPST, "query", str(path), "<probe>", "--field", "value", "--one"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    if result.returncode != 0:
        raise AssertionError(f"typst не разобрал разметку:\n{markups}\n{result.stderr}")
    return json.loads(result.stdout)


def body_of(typ: str) -> str:
    """Тело документа без преамбулы."""
    return typ.split('#show figure: set block(above: 1em, below: 1em)\n', 1)[1].strip()


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00\x00\x00\xff")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class FakeRepo:
    """Временный репозиторий: .git, docs/writeup, docs/report.md, scripts/."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".git").mkdir()
        self.writeup = self.root / "docs" / "writeup"
        self.writeup.mkdir(parents=True)
        (self.root / "docs" / "report.md").write_text("# r\n", encoding="utf-8")
        (self.root / "docs" / "otto-run").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "otto3.py").write_text("", encoding="utf-8")
        (self.writeup / "facts.md").write_text("# f\n", encoding="utf-8")
        (self.writeup / "fig.png").write_bytes(tiny_png())
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def context(self) -> Context:
        return Context(self.writeup, self.root, ref=REF)

    def to_typst(self, md: str, **kwargs) -> str:
        return markdown_to_typst(md, base_dir=self.writeup, repo_root=self.root, ref=REF, **kwargs)


class EscapingTests(unittest.TestCase):
    def test_every_typst_special_is_escaped(self):
        for ch in "#$*_@<>[]\\~`":
            self.assertEqual(escape_text(ch), "\\" + ch, ch)

    def test_number_followed_by_dot_is_not_an_enum(self):
        self.assertEqual(escape_text("1. пункт"), "1\\. пункт")
        self.assertEqual(escape_text("0.4906"), "0.4906")

    def test_text_after_a_call_cannot_extend_it(self):
        self.assertEqual(escape_text(".pdf", after_call=True), "\\.pdf")
        self.assertEqual(escape_text("(x)", after_call=True), "\\(x)")
        self.assertEqual(escape_text("; y", after_call=True), "\\; y")

    @unittest.skipUnless(TYPST, "typst не найден")
    def test_tricky_text_survives_typst_literally(self):
        md = (
            "Δ ≈ 0.0033 − 0.0001 → … CI [+0.0030, +0.0036], $2.89 за 6 вызовов; "
            "# * _ @ < > [ ] \\\\ ~ \\` 'a' \"b\" a/b // c -- d --- e -? = + "
            "x_y_z C_test 3 * 4 OTTO-3 `i3`; `<!--OTTO-BEST-->`. 1. не список"
        )
        expected = (
            "Δ ≈ 0.0033 − 0.0001 → … CI [+0.0030, +0.0036], $2.89 за 6 вызовов; "
            "# * _ @ < > [ ] \\ ~ ` 'a' \"b\" a/b // c -- d --- e -? = + "
            "x_y_z C_test 3 * 4 OTTO-3 i3; <!--OTTO-BEST-->. 1. не список"
        )
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        self.assertEqual(typst_plain(body_of(typ)), expected)

    @unittest.skipUnless(TYPST, "typst не найден")
    def test_cell_starting_with_number_and_dot_stays_text(self):
        with FakeRepo() as repo:
            typ = repo.to_typst("| a |\n|---|\n| 2. шаг |\n")
        cell = re.search(r"\n  \[(.*)\],\n\)", typ).group(1)
        self.assertEqual(typst_plain(cell), "2. шаг")


class InlineTests(unittest.TestCase):
    def test_emphasis_and_intraword_underscores(self):
        nodes = parse_inline("**жирный** и *курсив*, C_test и snake_case_name, 2 * 3")
        kinds = [type(n).__name__ for n in nodes]
        self.assertEqual(kinds, ["Strong", "Text", "Emph", "Text"])
        self.assertEqual(plain_text(nodes), "жирный и курсив, C_test и snake_case_name, 2 * 3")

    def test_nested_emphasis_and_code(self):
        nodes = parse_inline("**текст с *курсивом* и `a*b`**")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(type(nodes[0]).__name__, "Strong")
        self.assertEqual(plain_text(nodes), "текст с курсивом и a*b")

    def test_brackets_without_url_are_text(self):
        nodes = parse_inline("CI [+0.0030, +0.0036] (ночь:36) и [t−48h, t)")
        self.assertEqual([type(n).__name__ for n in nodes], ["Text"])


    def test_bare_url_does_not_swallow_closing_quotes_or_ellipsis(self):
        nodes = parse_inline("см. «https://example.org/a», https://example.org/b… и “https://example.org/c(1)”.")
        links = [n.dest for n in nodes if isinstance(n, Link)]
        self.assertEqual(links, ["https://example.org/a", "https://example.org/b", "https://example.org/c(1)"])
        self.assertEqual(plain_text(nodes), "см. «https://example.org/a», https://example.org/b… и “https://example.org/c(1)”.")


class LinkTests(unittest.TestCase):
    def test_relative_paths_become_github_links(self):
        with FakeRepo() as repo:
            ctx = repo.context()
            self.assertEqual(resolve_link("../report.md", ctx), ("url", f"{BLOB}/docs/report.md"))
            self.assertEqual(resolve_link("facts.md", ctx), ("url", f"{BLOB}/docs/writeup/facts.md"))
            self.assertEqual(
                resolve_link("./sub/../../../scripts/otto3.py", ctx), ("url", f"{BLOB}/scripts/otto3.py")
            )
            self.assertEqual(resolve_link("/scripts/otto3.py", ctx), ("url", f"{BLOB}/scripts/otto3.py"))
            self.assertEqual(resolve_link("../otto-run/", ctx), ("url", f"{TREE}/docs/otto-run"))

    def test_anchor_is_kept_and_cyrillic_is_encoded(self):
        with FakeRepo() as repo:
            ctx = repo.context()
            self.assertEqual(
                resolve_link("../report.md#обязательные-оговорки", ctx),
                ("url", f"{BLOB}/docs/report.md#обязательные-оговорки"),
            )
            self.assertEqual(
                resolve_link("../отчёт.md", ctx), ("url", f"{BLOB}/docs/%D0%BE%D1%82%D1%87%D1%91%D1%82.md")
            )

    def test_external_urls_are_untouched(self):
        with FakeRepo() as repo:
            ctx = repo.context()
            for url in ("https://www.kaggle.com/c/otto?tab=1#x", "mailto:a@b.c"):
                self.assertEqual(resolve_link(url, ctx), ("url", url))

    def test_path_outside_repo_is_left_as_is(self):
        with FakeRepo() as repo:
            ctx = repo.context()
            self.assertEqual(resolve_link("../../../x.md", ctx), ("url", "../../../x.md"))
            self.assertTrue(ctx.warnings)

    def test_document_anchor_links_to_heading_label(self):
        md = "# Отчёт\n\n## Обязательные оговорки\n\nСм. [оговорки](#обязательные-оговорки) и [нет](#нет-такого).\n"
        with FakeRepo() as repo:
            warnings = []
            typ = repo.to_typst(md, warnings=warnings)
        self.assertIn('#label("обязательные-оговорки")', typ)
        self.assertIn('#link(label("обязательные-оговорки"))[оговорки]', typ)
        self.assertNotIn("нет-такого\"", typ)
        self.assertEqual(len(warnings), 1)

    def test_markdown_link_renders_as_github_link(self):
        md = "Полный [отчёт](../report.md#итог) и <https://example.org/a_b>."
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        self.assertIn(f'#link("{BLOB}/docs/report.md#итог")[отчёт]', typ)
        self.assertIn('#link("https://example.org/a_b")[https:\\/\\/example.org\\/a\\_b]\\.', typ)


class RefTests(unittest.TestCase):
    def test_ref_that_is_not_a_local_commit_warns_once(self):
        with FakeRepo() as repo:  # .git пустой: проверить ref нечем
            ctx = repo.context()
            self.assertEqual(resolve_link("../report.md", ctx), ("url", f"{BLOB}/docs/report.md"))
            resolve_link("facts.md", ctx)
            resolve_link("nope.md", ctx)
        self.assertEqual(len(ctx.warnings), 2, ctx.warnings)
        self.assertIn(f"ref {REF} не найден как коммит", ctx.warnings[0])
        self.assertIn("nope.md нет в рабочем дереве", ctx.warnings[1])

    def test_default_ref_without_git_is_the_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(writeup_pdf, "GIT", str(Path(tmp) / "no-git")):
                self.assertEqual(default_ref(Path(tmp)), GITHUB_BRANCH)
            if GIT:
                with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(Path(tmp).parent)}):
                    self.assertEqual(default_ref(Path(tmp)), GITHUB_BRANCH)

    def test_fallback_to_branch_is_reported(self):
        with FakeRepo() as repo, mock.patch.object(writeup_pdf, "GIT", str(repo.root / "no-git")):
            warnings: list[str] = []
            typ = markdown_to_typst(
                "[отчёт](../report.md)\n", base_dir=repo.writeup, repo_root=repo.root, warnings=warnings
            )
        self.assertIn(f"/blob/{GITHUB_BRANCH}/docs/report.md", typ)
        self.assertIn(f"ссылки ведут на ветку {GITHUB_BRANCH}", warnings[0])

    def test_warnings_are_ordered_by_source_line(self):
        md = "| a |\n|---|\n| 1 | 2 |\n\n## Итог: чего не хватило\n"
        warnings: list[str] = []
        with FakeRepo() as repo:
            repo.to_typst("## Итог, чего не хватило\n\n" + md, warnings=warnings)
        self.assertEqual([w.split(":")[0] for w in warnings], ["строка 1", "строка 5", "строка 7"])


GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
}


@unittest.skipUnless(GIT, "git не найден")
class GitRefTests(unittest.TestCase):
    """Настоящий репозиторий: закоммиченные, неотслеживаемые и ignored файлы."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "repo"
        self.docs = self.root / "docs"
        (self.docs / "run").mkdir(parents=True)
        self.git("init", "-q")
        (self.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (self.docs / "report.md").write_text("# r\n", encoding="utf-8")
        (self.docs / "run" / "a.csv").write_text("x\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.sha = self.git("rev-parse", "HEAD")
        (self.docs / "draft.md").write_text("черновик\n", encoding="utf-8")
        (self.docs / "debug.log").write_text("лог\n", encoding="utf-8")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            [GIT, "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **GIT_ENV},
        )
        return result.stdout.strip()

    def test_default_ref_is_full_head_sha(self):
        self.assertRegex(self.sha, r"^[0-9a-f]{40}$")
        self.assertEqual(default_ref(self.docs), self.sha)

    def test_links_point_to_the_commit_and_are_checked_in_it(self):
        ctx = Context(self.docs, self.root, ref=self.sha)
        base = "https://github.com/suprend/tlab-recsys-2026-task1"
        self.assertEqual(resolve_link("report.md#x", ctx), ("url", f"{base}/blob/{self.sha}/docs/report.md#x"))
        self.assertEqual(resolve_link("run", ctx), ("url", f"{base}/tree/{self.sha}/docs/run"))
        self.assertEqual(ctx.warnings, [])
        self.assertEqual(resolve_link("draft.md", ctx), ("url", f"{base}/blob/{self.sha}/docs/draft.md"))
        resolve_link("debug.log", ctx)
        resolve_link("missing.md", ctx)
        self.assertEqual(len(ctx.warnings), 3, ctx.warnings)
        short = self.sha[:12]
        self.assertIn(f"docs/draft.md нет в коммите {short} (в рабочем дереве есть", ctx.warnings[0])
        self.assertIn("docs/debug.log нет в коммите", ctx.warnings[1])
        self.assertIn("docs/missing.md нет в коммите", ctx.warnings[2])
        self.assertIn("нет и в рабочем дереве", ctx.warnings[2])

    def test_branch_name_ref_is_checked_too(self):
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        ctx = Context(self.docs, self.root, ref=branch)
        self.assertEqual(
            resolve_link("report.md", ctx),
            ("url", f"https://github.com/suprend/tlab-recsys-2026-task1/blob/{branch}/docs/report.md"),
        )
        resolve_link("draft.md", ctx)
        self.assertEqual(len(ctx.warnings), 1, ctx.warnings)
        self.assertIn(f"нет в коммите {branch}", ctx.warnings[0])

    @unittest.skipUnless(TYPST, "typst не найден")
    def test_cli_defaults_to_head_and_accepts_ref(self):
        src = self.docs / "w.md"
        src.write_text("[отчёт](report.md)\n", encoding="utf-8")
        typ = self.root / "out" / "w.typ"
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(main([str(src), str(self.root / "out" / "w.pdf"), "--typ", str(typ)]), 0)
        self.assertIn(f"/blob/{self.sha}/docs/report.md", typ.read_text(encoding="utf-8"))
        self.assertEqual(err.getvalue(), "")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = main([str(src), str(self.root / "out" / "w.pdf"), "--typ", str(typ), "--ref", "v-test"])
        self.assertEqual(code, 0)
        self.assertIn("/blob/v-test/docs/report.md", typ.read_text(encoding="utf-8"))
        self.assertIn("ref v-test не найден как коммит", err.getvalue())


class CommentAndSectionTests(unittest.TestCase):
    def test_inline_and_multiline_comments_are_removed(self):
        md = (
            "Лучший 0.59548 <!--OTTO-BEST-->, итог.\n"
            "До <!-- раз\nдва\nтри --> после.\n"
            "<!--\nцелый блок\n-->\n"
            "Конец."
        )
        # «До … после.» — один абзац (комментарий внутри строки), блок с начала
        # строки — HTML-блок GitHub: на его месте пустая строка
        self.assertEqual(strip_html_comments(md), "Лучший 0.59548, итог.\nДо\n после.\n\nКонец.")

    def test_comment_only_line_separates_paragraphs_like_github(self):
        md = "Первый абзац.\n<!-- служебное -->\nВторой абзац.\n"
        blocks = parse_blocks(strip_html_comments(md).split("\n"))
        self.assertEqual(blocks, [Paragraph("Первый абзац."), Paragraph("Второй абзац.")])
        multi = "Первый.\n  <!--\n  служебное\n  -->\nВторой.\n"
        blocks = parse_blocks(strip_html_comments(multi).split("\n"))
        self.assertEqual(blocks, [Paragraph("Первый."), Paragraph("Второй.")])

    def test_comment_inside_a_line_keeps_the_paragraph(self):
        md = "Первый <!-- a --> абзац\nпродолжается <!-- b\nc -->\nи тут.\n"
        blocks = parse_blocks(strip_html_comments(md).split("\n"))
        self.assertEqual(blocks, [Paragraph("Первый  абзац\nпродолжается\nи тут.")])

    def test_text_after_a_line_start_comment_is_its_own_block(self):
        md = "абзац\n<!-- x --> хвост\nдальше\n"
        blocks = parse_blocks(strip_html_comments(md).split("\n"))
        self.assertEqual(blocks, [Paragraph("абзац"), Paragraph("хвост"), Paragraph("дальше")])

    def test_comment_only_line_ends_a_table_like_github(self):
        # GitHub: строка с <!-- открывает HTML-блок, он прерывает таблицу
        md = "| a |\n|---|\n| 0 |\n<!-- note -->\n| 1 |\n"
        blocks = parse_blocks(strip_html_comments(md).split("\n"))
        self.assertEqual(blocks, [Table(["left"], ["a"], [["0"]]), Paragraph("| 1 |")])

    def test_unclosed_comment_is_an_error_with_its_line(self):
        md = "# T\n\nЧисло 0.59 <!--OTTO-BEST->.\n\n## Дальше\n\nважный текст\n"
        with self.assertRaisesRegex(ConversionError, r"строка 3: комментарий <!-- не закрыт"):
            strip_html_comments(md)
        with FakeRepo() as repo, self.assertRaisesRegex(ConversionError, "строка 3"):
            repo.to_typst(md.replace("\n", "\r\n"))
        with self.assertRaisesRegex(ConversionError, "строка 2"):
            strip_html_comments("a\n<!--\nb\n")

    def test_empty_comments_are_closed(self):
        self.assertEqual(strip_html_comments("a <!--> b <!---> c\nd"), "a  b  c\nd")

    def test_comments_inside_code_are_kept(self):
        md = "Маркер `<!--OTTO-BEST-->` ставь рядом.\n```html\n<!-- keep -->\n```\n"
        self.assertEqual(strip_html_comments(md), md)

    def test_missing_section_is_dropped_until_same_level_heading(self):
        md = (
            "# Отчёт\n\nТекст.\n\n## Чего не хватило\n\n- нет числа X\n\n### Деталь\n\nещё\n\n"
            "## Ограничения\n\nОстаётся.\n"
        )
        self.assertEqual(drop_sections(md), "# Отчёт\n\nТекст.\n\n## Ограничения\n\nОстаётся.\n")

    def test_missing_section_at_end_is_dropped_to_eof(self):
        md = "## Итог\n\nДа.\n\n## Чего не хватило:\n\n```\n## не заголовок\n```\nхвост\n"
        self.assertEqual(drop_sections(md), "## Итог\n\nДа.\n")

    def test_missing_section_ends_at_higher_heading(self):
        md = "### Чего не хватило\nx\n## Дальше\ny\n"
        self.assertEqual(drop_sections(md), "## Дальше\ny\n")

    def test_missing_section_variants_are_dropped(self):
        for title in (
            "Чего не хватило?",
            "5. Чего не хватило",
            "5.1) Чего не хватило",
            "Чего не хватило (по OTTO)",
            "**Чего  не хватило**:",
            "«Чего не хватило»",
            "ЧЕГО НЕ ХВАТИЛО",
        ):
            md = f"## Итог\n\nДа.\n\n## {title}\n\nсекрет\n\n## Дальше\n\nНет.\n"
            warnings: list[str] = []
            self.assertEqual(
                drop_sections(md, warnings=warnings), "## Итог\n\nДа.\n\n## Дальше\n\nНет.\n", title
            )
            self.assertEqual(warnings, [], title)

    def test_phrase_elsewhere_in_heading_is_kept_with_warning(self):
        md = "# T\n\n## Итог: чего не хватило\n\nостаётся\n\n## Чего не хватилось бы\n\nтоже\n"
        warnings: list[str] = []
        self.assertEqual(drop_sections(md, warnings=warnings), md)
        self.assertEqual(len(warnings), 2, warnings)
        self.assertIn("строка 3", warnings[0])
        self.assertIn("Итог: чего не хватило", warnings[0])
        self.assertIn("строка 7", warnings[1])
        with FakeRepo() as repo:
            through: list[str] = []
            typ = repo.to_typst("<!-- c\nc -->\n" + md, warnings=through)
        self.assertIn("остаётся", typ)
        self.assertIn("строка 5", through[0])  # номер во входном файле, до вырезания комментария

    def test_end_to_end_report_has_no_comment_or_section(self):
        md = "# T\n\nЧисло 0.59 <!--OTTO-BEST-->.\n\n## Чего не хватило\n\nсекрет\n"
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        self.assertNotIn("OTTO", typ)
        self.assertNotIn("секрет", typ)
        self.assertNotIn("хватило", typ)


class BlockTests(unittest.TestCase):
    def test_gfm_table_with_alignment_escaped_pipe_and_short_rows(self):
        md = (
            "Текст перед таблицей\n"
            "| ID | Утверждение | Число |\n"
            "|:---|:---:|---:|\n"
            "| R37 | \\|D\\| < 0.001 | `a\\|b` |\n"
            "| R38 | только две |\n"
        )
        blocks = parse_blocks(md.split("\n"))
        self.assertIsInstance(blocks[0], Paragraph)
        table = blocks[1]
        self.assertIsInstance(table, Table)
        self.assertEqual(table.aligns, ["left", "center", "right"])
        self.assertEqual(table.header, ["ID", "Утверждение", "Число"])
        self.assertEqual(table.rows, [["R37", "|D| < 0.001", "`a|b`"], ["R38", "только две", ""]])
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        self.assertIn("align: (left, center, right,),", typ)
        self.assertIn("table.header([ID], [Утверждение], [Число]),", typ)
        self.assertIn('[R37], [|D| \\< 0.001], [#raw("a|b")],', typ)

    def test_extra_table_cells_warn_with_source_line(self):
        md = (
            "<!-- служебное\nв две строки -->\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n"
            "| `x|y` | 3 |\n"
            "\n- пункт\n\n  | c |\n  |---|\n  | 4 | 5 |\n"
        )
        warnings: list[str] = []
        with FakeRepo() as repo:
            typ = repo.to_typst(md, warnings=warnings)
        self.assertEqual(len(warnings), 2, warnings)
        self.assertRegex(warnings[0], r"^строка 6: в строке таблицы 3 ячеек при 2 колонках")
        self.assertIn("«3»", warnings[0])
        self.assertRegex(warnings[1], r"^строка 12: в строке таблицы 2 ячеек при 1 колонках")
        self.assertIn("[\\`x], [y\\`],", typ)  # лишняя ячейка отброшена, как у GitHub

    def test_wide_table_gets_fixed_columns_within_text_width(self):
        long = "очень длинный текст ячейки " * 6
        md = f"| ID | A | B |\n|---|---|---|\n| R1 | {long} | {long} {long} |\n"
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        m = re.search(r"columns: \(auto, ([\d.]+)pt, ([\d.]+)pt,\)", typ)
        self.assertIsNotNone(m, typ)
        a, b = float(m.group(1)), float(m.group(2))
        self.assertLess(a, b)
        self.assertLessEqual(a + b, TEXT_WIDTH_PT)

    def test_column_is_not_narrower_than_its_longest_path(self):
        text = "длинное пояснение в несколько слов " * 5
        path = "`docs/xfer-sber-run/kaggle-submissions.json:35-50`"
        md = (
            "| ID | Утверждение | Источник | Примечание |\n|---|---|---|---|\n"
            f"| T50 | {text} | {path} | {text} |\n"
        )
        table = parse_blocks(md.split("\n"))[0]
        columns, inner = table_columns(table)
        widths = [float(x[:-2]) if x.endswith("pt") else None for x in columns.strip("(,)").split(", ")]
        unbreakable = len("submissions.json:35-50") * TABLE_CODE_PT
        self.assertGreaterEqual(inner[2], unbreakable)
        self.assertGreater(widths[1], widths[2])

    def test_code_run_across_nodes_gets_invisible_breaks_when_too_wide(self):
        nodes = parse_inline("`docs/otto3.md:64`, `:68`")
        with FakeRepo() as repo:
            ctx = repo.context()
            wide = render_inline(nodes, ctx, soft_breaks(nodes, 500.0))
            narrow = render_inline(nodes, ctx, soft_breaks(nodes, 30.0))
        self.assertEqual(wide, '#raw("docs/otto3.md:64"), #raw(":68")')
        self.assertEqual(
            narrow, '#raw("docs/otto3.")#box()#raw("md:")#box()#raw("64"), #box()#raw(":")#box()#raw("68")'
        )
        self.assertNotIn("\u200b", narrow)  # U+200B попадал в копируемый из PDF текст

    @unittest.skipUnless(TYPST, "typst не найден")
    def test_break_points_wrap_code_without_invisible_characters(self):
        nodes = parse_inline("`aaaaaa.bbbbbb:cccccc`, `:68`")
        with FakeRepo() as repo:
            ctx = repo.context()
            plain = render_inline(nodes, ctx)
            soft = render_inline(nodes, ctx, soft_breaks(nodes, 30.0))
        self.assertEqual(typst_plain(soft), "aaaaaa.bbbbbb:cccccc, :68")
        one_line, wrapped = typst_heights(40.0, plain, soft)
        self.assertGreater(wrapped, 2.5 * one_line)  # без мест разрыва код вылез бы одной строкой

    def test_nested_lists_and_continuation_paragraph(self):
        md = (
            "1. **Первый.** текст\n"
            "2. **Второй.**\n"
            "   - вложенный а\n"
            "   - вложенный б\n"
            "\n"
            "   Источники: отчёт.\n"
            "3. Третий\n"
            "\n"
            "После списка.\n"
            "Руки:\n"
            "- **Pop** — список\n"
            "  - `i1` — с нуля\n"
        )
        blocks = parse_blocks(md.split("\n"))
        kinds = [type(b).__name__ for b in blocks]
        self.assertEqual(kinds, ["ListBlock", "Paragraph", "ListBlock"])
        enum = blocks[0]
        self.assertTrue(enum.ordered)
        self.assertEqual(len(enum.items), 3)
        second = enum.items[1]
        self.assertEqual([type(b).__name__ for b in second], ["Paragraph", "ListBlock", "Paragraph"])
        self.assertEqual(len(second[1].items), 2)
        self.assertEqual(second[2].text, "Источники: отчёт.")
        bullets = blocks[2]
        self.assertFalse(bullets.ordered)
        self.assertIsInstance(bullets.items[0][1], ListBlock)

    def test_ordered_list_keeps_start_number(self):
        blocks = parse_blocks("4. четыре\n5. пять\n".split("\n"))
        self.assertEqual(blocks[0].start, 4)
        with FakeRepo() as repo:
            typ = repo.to_typst("4. четыре\n5. пять\n")
        self.assertIn("#enum(start: 4, tight: true,", typ)

    def test_code_block_rule_and_headings(self):
        md = "# Заголовок\n\n#### Четвёртый\n\n```python\nx = 1  # <!-- не комментарий -->\n```\n\n---\n"
        blocks = parse_blocks(strip_html_comments(md).split("\n"))
        self.assertEqual([type(b).__name__ for b in blocks], ["Heading", "Heading", "CodeBlock", "Rule"])
        self.assertIsInstance(blocks[2], CodeBlock)
        self.assertEqual(blocks[2].lang, "python")
        with FakeRepo() as repo:
            typ = repo.to_typst(md)
        self.assertIn('#raw("x = 1  # <!-- не комментарий -->", block: true, lang: "python")', typ)
        self.assertIn("#heading(level: 4)[Четвёртый]", typ)
        self.assertIn("#line(length: 100%", typ)

    def test_image_is_resolved_relative_to_input(self):
        with FakeRepo() as repo:
            typ = repo.to_typst("![Рис. 1](fig.png)\n")
            path = (repo.writeup / "fig.png").as_posix()
            self.assertIn(f'#figure(image("{path}", width: 100%), caption: [Рис. 1], numbering: none)', typ)
            with self.assertRaises(ConversionError):
                repo.to_typst("![x](nope.png)\n")


def pdf_page_count(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", path.read_bytes()))


@unittest.skipUnless(TYPST, "typst не найден")
class BuildTests(unittest.TestCase):
    def test_full_sample_compiles_to_pdf(self):
        md = (
            "# Отчёт про ≈ и −\n\n"
            "Абзац с **жирным**, *курсивом*, `кодом`, [ссылкой](../report.md#x) и $2.89.\n\n"
            "## Таблица\n\n| A | B |\n|:--|--:|\n| [+0.0030, +0.0036] | → … |\n\n"
            "- пункт\n  - вложенный\n\n1. раз\n2. два\n\n"
            "![Подпись](fig.png)\n\n```\ncode\n```\n\n---\n\n"
            "<!-- служебное -->\n## Чего не хватило\n\n- X\n"
        )
        with FakeRepo() as repo:
            src = repo.writeup / "sample.md"
            src.write_text(md, encoding="utf-8")
            out = repo.root / "out" / "sample.pdf"
            typ = repo.root / "out" / "sample.typ"
            build_pdf(src, out, typst=TYPST, typ_out=typ, ref=REF)
            data = out.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreaterEqual(pdf_page_count(out), 1)
            source = typ.read_text(encoding="utf-8")
        self.assertNotIn("служебное", source)
        self.assertNotIn("хватило", source)

    def test_typst_error_is_reported(self):
        with FakeRepo() as repo:
            src = repo.writeup / "bad.md"
            src.write_text("текст\n", encoding="utf-8")
            with self.assertRaises(ConversionError):
                build_pdf(src, repo.root / "x.pdf", typst="/usr/bin/false", ref=REF)


if __name__ == "__main__":
    unittest.main()
