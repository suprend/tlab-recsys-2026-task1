"""Собрать PDF из Markdown-отчёта через Typst.

Вызов:

    .venv/bin/python -I scripts/writeup_pdf.py INPUT.md OUTPUT.pdf [--typ OUT.typ] [--ref REF]

Только стандартная библиотека. Markdown переводится в Typst-разметку и
компилируется командой ``typst compile``. Поддержано подмножество, которое
встречается в отчётах: заголовки, абзацы, жирный/курсив/код/зачёркнутый,
ссылки, списки (с вложенностью), таблицы GFM, картинки, блоки кода, ``---``.

Относительные ссылки на файлы репозитория превращаются в ссылки на GitHub
``/blob/<ref>/...`` (``GITHUB_REPO``; ref по умолчанию — полный sha HEAD, чтобы
ссылка не уезжала вместе с веткой). Цель ссылки проверяется в этом коммите
(``git cat-file``); незакоммиченная — предупреждение. HTML-комментарии и
раздел «Чего не хватило» в PDF не попадают; незакрытый ``<!--`` — ошибка.
"""

from __future__ import annotations

import argparse
import math
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

GITHUB_REPO = "suprend/tlab-recsys-2026-task1"
GITHUB_BRANCH = "task1-v2"  # ref ссылок, если sha HEAD взять неоткуда
GIT = "git"
DROPPED_SECTIONS = ("чего не хватило",)
DEFAULT_TYPST = "/opt/homebrew/bin/typst"


class ConversionError(Exception):
    """Вход нельзя честно перевести в Typst (например, нет файла картинки)."""


# ---------------------------------------------------------------------------
# Предобработка: комментарии и выброшенные разделы
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
HR_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
LIST_RE = re.compile(r"^( {0,3})([-+*]|\d{1,9}[.)])(?:([ \t]+)(.*))?$")
CLOSING_PUNCT = ",.;:!?)»]…"


def _fence_open(line: str) -> tuple[str, int, int] | None:
    """Вернуть (символ, длина, отступ) открывающего забора или None."""
    m = FENCE_RE.match(line)
    if not m:
        return None
    marker, info = m.group(2), m.group(3)
    if marker[0] == "`" and "`" in info:
        return None  # в info-строке ```-забора обратных кавычек быть не может
    return marker[0], len(marker), len(m.group(1))


def _fence_closes(line: str, fence: tuple[str, int, int]) -> bool:
    char, length, _ = fence
    stripped = line.strip()
    return (
        len(line) - len(line.lstrip(" ")) <= 3
        and len(stripped) >= length
        and set(stripped) == {char}
    )


def _backtick_run(s: str, i: int) -> int:
    j = i
    while j < len(s) and s[j] == "`":
        j += 1
    return j - i


def _find_code_close(s: str, start: int, run: int) -> int:
    """Позиция закрывающей серии из ровно ``run`` обратных кавычек или -1."""
    i = start
    while i < len(s):
        if s[i] == "`":
            n = _backtick_run(s, i)
            if n == run:
                return i
            i += n
        else:
            i += 1
    return -1


Numbered = list[tuple[int, str]]  # строки с номерами во входном файле (с 1)


def _numbered(md: str) -> Numbered:
    return list(enumerate(md.split("\n"), start=1))


def _comment_end(line: str, start: int) -> int:
    """Конец комментария, открытого ``<!--`` на позиции ``start``, или -1.

    ``<!-->`` и ``<!--->`` — пустые комментарии (HTML, CommonMark 0.31)."""
    body = start + 4
    for empty in (">", "->"):
        if line.startswith(empty, body):
            return body + len(empty)
    end = line.find("-->", body)
    return end + 3 if end >= 0 else -1


def _strip_comments_numbered(lines: Numbered) -> Numbered:
    out: Numbered = []
    fence: tuple[str, int, int] | None = None
    in_comment = False
    opened_at = 0
    block = False  # комментарий открыт в начале строки: у GitHub это HTML-блок
    for lineno, line in lines:
        if fence is not None:
            out.append((lineno, line))
            if _fence_closes(line, fence):
                fence = None
            continue
        if not in_comment:
            opened = _fence_open(line)
            if opened is not None:
                fence = opened
                out.append((lineno, line))
                continue
            block = line.lstrip(" ").startswith("<!--")
        line_block = block
        had_comment = in_comment
        pieces: list[str] = []
        i = 0
        while i < len(line):
            if in_comment:
                end = line.find("-->", i)
                if end < 0:
                    i = len(line)
                    break
                i = end + 3
                in_comment = False
                if i < len(line) and line[i] in CLOSING_PUNCT:
                    pieces = ["".join(pieces).rstrip(" \t")]
                continue
            ch = line[i]
            if ch == "\\" and i + 1 < len(line):
                pieces.append(line[i : i + 2])
                i += 2
                continue
            if ch == "`":
                run = _backtick_run(line, i)
                close = _find_code_close(line, i + run, run)
                if close >= 0:
                    pieces.append(line[i : close + run])
                    i = close + run
                else:
                    pieces.append(line[i : i + run])
                    i += run
                continue
            if line.startswith("<!--", i):
                had_comment = True
                opened_at = lineno
                end = _comment_end(line, i)
                if end < 0:
                    in_comment = True
                    i = len(line)
                    break
                i = end
                if i < len(line) and line[i] in CLOSING_PUNCT:
                    pieces = ["".join(pieces).rstrip(" \t")]
                continue
            pieces.append(ch)
            i += 1
        rebuilt = "".join(pieces)
        if line_block:
            # HTML-блок у GitHub отделяет то, что до и после него: вместо
            # строки комментария — пустая строка, остаток — отдельным блоком
            if not out or out[-1][1]:
                out.append((lineno, ""))
            if rebuilt.strip():
                out.extend([(lineno, rebuilt.strip()), (lineno, "")])
            continue
        if had_comment and not rebuilt.strip():
            continue  # строка внутри комментария посреди абзаца
        out.append((lineno, rebuilt.rstrip() if had_comment else rebuilt))
    if in_comment:
        raise ConversionError(
            f"строка {opened_at}: комментарий <!-- не закрыт (нет -->); "
            "он скрыл бы весь остаток документа"
        )
    return out


def strip_html_comments(md: str) -> str:
    """Убрать ``<!-- ... -->`` вне кода, в том числе многострочные.

    Комментарий посреди строки вырезается, абзац остаётся целым. Строка,
    которая начинается с комментария, у GitHub — отдельный HTML-блок: она
    заменяется пустой строкой и разделяет абзацы, таблицы и списки так же.
    Комментарии внутри блоков кода и ``код``-вставок сохраняются как текст.
    Незакрытый ``<!--`` — ``ConversionError`` с номером строки.
    """
    return "\n".join(line for _, line in _strip_comments_numbered(_numbered(md)))


def _normalize_title(text: str) -> str:
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split()).casefold()


def _title_starts_with(title: str, phrase: str) -> bool:
    """Заголовок начинается с фразы, если отбросить номер и знаки впереди:
    «5. Чего не хватило», «Чего не хватило?», «Чего не хватило (по OTTO)»."""
    title = re.sub(r"^[\W\d_]+", "", title)
    return title.startswith(phrase) and not title[len(phrase) : len(phrase) + 1].isalnum()


def _drop_sections_numbered(
    lines: Numbered, titles: tuple[str, ...], warnings: list[str] | None
) -> Numbered:
    wanted = [_normalize_title(t) for t in titles]
    out: Numbered = []
    fence: tuple[str, int, int] | None = None
    dropping_level: int | None = None
    for lineno, line in lines:
        heading = None
        if fence is not None:
            if _fence_closes(line, fence):
                fence = None
        else:
            opened = _fence_open(line)
            if opened is not None:
                fence = opened
            else:
                heading = HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group(1))
            if dropping_level is not None and level <= dropping_level:
                dropping_level = None
            if dropping_level is None:
                title = _normalize_title(heading.group(2) or "")
                if any(_title_starts_with(title, w) for w in wanted):
                    dropping_level = level
                elif warnings is not None:
                    for w in wanted:
                        if w in title:
                            warnings.append(
                                f"строка {lineno}: заголовок «{(heading.group(2) or '').strip()}» "
                                f"содержит «{w}», но не начинается с этой фразы; раздел оставлен в PDF"
                            )
        if dropping_level is None:
            out.append((lineno, line))
    return out


def drop_sections(
    md: str, titles: tuple[str, ...] = DROPPED_SECTIONS, warnings: list[str] | None = None
) -> str:
    """Удалить разделы, чей заголовок начинается с одной из ``titles``
    (без учёта регистра, разметки, номера впереди и знаков после фразы), до
    следующего заголовка того же или более высокого уровня (или до конца
    файла). Заголовок, где фраза стоит не в начале, остаётся; о нём —
    предупреждение в ``warnings``."""
    kept = _drop_sections_numbered(_numbered(md), titles, warnings)
    return "\n".join(line for _, line in kept)


# ---------------------------------------------------------------------------
# Блоки
# ---------------------------------------------------------------------------


@dataclass
class Heading:
    level: int
    text: str
    slug: str = ""


@dataclass
class Paragraph:
    text: str


@dataclass
class CodeBlock:
    lang: str
    code: str


@dataclass
class Rule:
    pass


@dataclass
class Table:
    aligns: list[str]
    header: list[str]
    rows: list[list[str]]


@dataclass
class ListBlock:
    ordered: bool
    start: int
    tight: bool
    items: list[list[object]] = field(default_factory=list)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            if s[i + 1] == "|":
                buf.append("|")
            else:
                buf.append(s[i : i + 2])
            i += 2
            continue
        if s[i] == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(s[i])
        i += 1
    cells.append("".join(buf).strip())
    return cells


DELIM_CELL_RE = re.compile(r"^:?-+:?$")


def _delimiter_aligns(line: str) -> list[str] | None:
    if "-" not in line or ("|" not in line and not line.strip().startswith(":")):
        return None
    cells = _split_row(line)
    aligns = []
    for cell in cells:
        cell = cell.replace(" ", "")
        if not DELIM_CELL_RE.match(cell):
            return None
        if cell.startswith(":") and cell.endswith(":"):
            aligns.append("center")
        elif cell.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


def _table_starts(lines: list[str], i: int) -> list[str] | None:
    if i + 1 >= len(lines) or "|" not in lines[i] or _indent(lines[i]) > 3:
        return None
    aligns = _delimiter_aligns(lines[i + 1])
    if aligns is None or len(_split_row(lines[i])) != len(aligns):
        return None
    return aligns


def _list_match(line: str):
    if HR_RE.match(line):
        return None
    return LIST_RE.match(line)


def _starts_block(lines: list[str], i: int, *, in_paragraph: bool) -> bool:
    line = lines[i]
    if HEADING_RE.match(line) or HR_RE.match(line) or _fence_open(line):
        return True
    m = _list_match(line)
    if m:
        if not in_paragraph:
            return True
        # список прерывает абзац, только если пункт не пустой и нумерация с 1
        if (m.group(4) or "").strip():
            marker = m.group(2)
            return not marker[0].isdigit() or int(marker[:-1]) == 1
    return _table_starts(lines, i) is not None


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_blocks(
    lines: list[str], linenos: list[int] | None = None, warnings: list[str] | None = None
) -> list[object]:
    """Разобрать строки на блоки. ``linenos`` — номера строк во входном
    файле (для предупреждений), по умолчанию 1, 2, …"""
    if linenos is None:
        linenos = list(range(1, len(lines) + 1))
    blocks: list[object] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = _fence_open(line)
        if fence is not None:
            info = FENCE_RE.match(line).group(3).strip()
            lang = info.split()[0] if info else ""
            body: list[str] = []
            i += 1
            while i < n and not _fence_closes(lines[i], fence):
                text = lines[i]
                drop = min(fence[2], _indent(text))
                body.append(text[drop:])
                i += 1
            i += 1  # закрывающий забор (или конец файла)
            blocks.append(CodeBlock(lang, "\n".join(body)))
            continue
        heading = HEADING_RE.match(line)
        if heading:
            blocks.append(Heading(len(heading.group(1)), (heading.group(2) or "").strip()))
            i += 1
            continue
        if HR_RE.match(line):
            blocks.append(Rule())
            i += 1
            continue
        if _list_match(line):
            block, i = _parse_list(lines, i, linenos, warnings)
            blocks.append(block)
            continue
        aligns = _table_starts(lines, i)
        if aligns is not None:
            header = _split_row(lines[i])
            rows = []
            i += 2
            while i < n and lines[i].strip() and "|" in lines[i]:
                if not lines[i].lstrip().startswith("|") and _starts_block(lines, i, in_paragraph=False):
                    break
                cells = _split_row(lines[i])
                if len(cells) > len(aligns) and warnings is not None:
                    extra = " | ".join(cells[len(aligns) :])
                    warnings.append(
                        f"строка {linenos[i]}: в строке таблицы {len(cells)} ячеек при "
                        f"{len(aligns)} колонках, лишние отброшены: «{_short(extra)}»; "
                        "если | — часть текста, экранируй его как \\|"
                    )
                cells = (cells + [""] * len(aligns))[: len(aligns)]
                rows.append(cells)
                i += 1
            blocks.append(Table(aligns, header, rows))
            continue
        para = [line.lstrip()]
        i += 1
        while i < n and lines[i].strip() and not _starts_block(lines, i, in_paragraph=True):
            para.append(lines[i].lstrip())
            i += 1
        # GFM: два пробела в конце строки — жёсткий перенос; убираем только у последней
        para[-1] = para[-1].rstrip()
        blocks.append(Paragraph("\n".join(para)))
    return blocks


def _parse_list(
    lines: list[str], i: int, linenos: list[int], warnings: list[str] | None
) -> tuple[ListBlock, int]:
    first = _list_match(lines[i])
    marker = first.group(2)
    ordered = marker[0].isdigit()
    kind = marker[-1] if ordered else marker
    block = ListBlock(ordered, int(marker[:-1]) if ordered else 1, tight=True)
    n = len(lines)
    while i < n:
        m = _list_match(lines[i])
        if not m:
            break
        mk = m.group(2)
        if mk[0].isdigit() != ordered or (mk[-1] if ordered else mk) != kind:
            break
        indent = len(m.group(1))
        spaces = m.group(3) or ""
        rest = m.group(4) or ""
        if not rest.strip():
            content_indent = indent + len(mk) + 1
            rest = ""
        elif len(spaces) > 4:
            content_indent = indent + len(mk) + 1
            rest = spaces[1:] + rest
        else:
            content_indent = indent + len(mk) + len(spaces)
        item_lines = [rest]
        item_nos = [linenos[i]]
        i += 1
        fence = _fence_open(rest)
        while i < n:
            line = lines[i]
            if not line.strip():
                j = i
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and _indent(lines[j]) >= content_indent:
                    item_lines.extend([""] * (j - i))
                    item_nos.extend(linenos[i:j])
                    i = j
                    continue
                break
            if _indent(line) >= content_indent:
                text = line[content_indent:]
                item_lines.append(text)
                item_nos.append(linenos[i])
                if fence is None:
                    fence = _fence_open(text)
                elif _fence_closes(text, fence):
                    fence = None
                i += 1
                continue
            if fence is not None or _list_match(line):
                break
            # ленивое продолжение абзаца
            last = item_lines[-1] if item_lines else ""
            if last.strip() and not _starts_block(lines, i, in_paragraph=True):
                item_lines.append(line.strip())
                item_nos.append(linenos[i])
                i += 1
                continue
            break
        while item_lines and not item_lines[-1].strip():
            item_lines.pop()
            item_nos.pop()
        if "" in item_lines:
            block.tight = False
        block.items.append(parse_blocks(item_lines, item_nos, warnings))
        # пустые строки между пунктами одного списка делают его «рыхлым»
        j = i
        while j < n and not lines[j].strip():
            j += 1
        if j > i and j < n:
            nxt = _list_match(lines[j])
            if nxt and (nxt.group(2)[0].isdigit() == ordered) and (
                (nxt.group(2)[-1] if ordered else nxt.group(2)) == kind
            ):
                block.tight = False
                i = j
                continue
            break
    return block, i


# ---------------------------------------------------------------------------
# Строчная разметка
# ---------------------------------------------------------------------------


@dataclass
class Text:
    text: str


@dataclass
class Code:
    text: str


@dataclass
class Strong:
    children: list


@dataclass
class Emph:
    children: list


@dataclass
class Strike:
    children: list


@dataclass
class Link:
    dest: str
    children: list
    autolink: bool = False


@dataclass
class Image:
    alt: str
    src: str


@dataclass
class LineBreak:
    pass


@dataclass
class _Delim:
    char: str
    count: int
    can_open: bool
    can_close: bool
    orig: int


ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
AUTOLINK_RE = re.compile(r"<((?:https?|ftp)://[^\s<>]+|mailto:[^\s<>]+)>")
BARE_URL_RE = re.compile(r"https?://[^\s<>]+")


def _is_ws(ch: str) -> bool:
    return ch == "" or ch.isspace()


def _is_punct(ch: str) -> bool:
    return ch != "" and (ch in ASCII_PUNCT or unicodedata.category(ch)[0] in "PS")


def _skip_bracket(s: str, i: int) -> int:
    """Для ``s[i] == '['`` вернуть позицию парной ``]`` или -1."""
    depth = 0
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "`":
            run = _backtick_run(s, j)
            close = _find_code_close(s, j + run, run)
            j = close + run if close >= 0 else j + run
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _parse_link_at(s: str, i: int) -> tuple[str, str, int] | None:
    """``[текст](адрес "заголовок")`` с ``s[i] == '['`` → (текст, адрес, конец)."""
    close = _skip_bracket(s, i)
    if close < 0 or close + 1 >= len(s) or s[close + 1] != "(":
        return None
    j = close + 2
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j < len(s) and s[j] == "<":
        end = s.find(">", j)
        if end < 0:
            return None
        dest = s[j + 1 : end]
        j = end + 1
    else:
        depth = 0
        start = j
        while j < len(s):
            ch = s[j]
            if ch == "\\" and j + 1 < len(s):
                j += 2
                continue
            if ch.isspace():
                break
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            j += 1
        dest = s[start:j]
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j < len(s) and s[j] in "\"'(":
        closer = ")" if s[j] == "(" else s[j]
        end = s.find(closer, j + 1)
        if end < 0:
            return None
        j = end + 1
        while j < len(s) and s[j] in " \t\n":
            j += 1
    if j >= len(s) or s[j] != ")":
        return None
    dest = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", dest)
    return s[i + 1 : close], dest, j + 1


BARE_URL_TRAILING = ".,:;!?\"'*_~»…”"


def _trim_bare_url(url: str) -> str:
    while True:
        before = url
        url = url.rstrip(BARE_URL_TRAILING)
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        if url == before:
            return url


def parse_inline(s: str) -> list:
    nodes: list = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            nodes.append(Text("".join(buf)))
            buf.clear()

    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "\n":
                flush()
                nodes.append(LineBreak())
                i += 2
                continue
            if nxt in ASCII_PUNCT:
                buf.append(nxt)
                i += 2
                continue
        if ch == "`":
            run = _backtick_run(s, i)
            close = _find_code_close(s, i + run, run)
            if close >= 0:
                code = s[i + run : close].replace("\n", " ")
                if len(code) > 1 and code[0] == " " and code[-1] == " " and code.strip():
                    code = code[1:-1]
                flush()
                nodes.append(Code(code))
                i = close + run
            else:
                buf.append("`" * run)
                i += run
            continue
        if ch == "!" and i + 1 < n and s[i + 1] == "[":
            parsed = _parse_link_at(s, i + 1)
            if parsed:
                text, dest, end = parsed
                flush()
                nodes.append(Image(plain_text(parse_inline(text)), dest))
                i = end
                continue
        if ch == "[":
            parsed = _parse_link_at(s, i)
            if parsed:
                text, dest, end = parsed
                flush()
                nodes.append(Link(dest, parse_inline(text)))
                i = end
                continue
        if ch == "<":
            m = AUTOLINK_RE.match(s, i)
            if m:
                flush()
                nodes.append(Link(m.group(1), [Text(m.group(1))], autolink=True))
                i = m.end()
                continue
        if ch in "hH" and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] in "/:")):
            m = BARE_URL_RE.match(s, i)
            if m:
                url = _trim_bare_url(m.group(0))
                if len(url) > len("https://"):
                    flush()
                    nodes.append(Link(url, [Text(url)], autolink=True))
                    i += len(url)
                    continue
        if ch in "*_~":
            j = i
            while j < n and s[j] == ch:
                j += 1
            run = j - i
            before = s[i - 1] if i > 0 else ""
            after = s[j] if j < n else ""
            left = not _is_ws(after) and (not _is_punct(after) or _is_ws(before) or _is_punct(before))
            right = not _is_ws(before) and (not _is_punct(before) or _is_ws(after) or _is_punct(after))
            if ch == "_":
                can_open = left and (not right or _is_punct(before))
                can_close = right and (not left or _is_punct(after))
            else:
                can_open, can_close = left, right
            if ch == "~" and run != 2:
                buf.append(ch * run)
            else:
                flush()
                nodes.append(_Delim(ch, run, can_open, can_close, run))
            i = j
            continue
        if ch == "\n":
            if len(buf) >= 2 and buf[-1] == " " and buf[-2] == " ":
                while buf and buf[-1] == " ":
                    buf.pop()
                flush()
                nodes.append(LineBreak())
            else:
                while buf and buf[-1] == " ":
                    buf.pop()
                buf.append(" ")
            i += 1
            while i < n and s[i] == " ":
                i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    _process_emphasis(nodes)
    return _finalize(nodes)


def _process_emphasis(nodes: list) -> None:
    """Алгоритм разбора выделения CommonMark (стек разделителей)."""
    ci = 0
    while ci < len(nodes):
        closer = nodes[ci]
        if not isinstance(closer, _Delim) or not closer.can_close or closer.count == 0:
            ci += 1
            continue
        oi = ci - 1
        opener = None
        while oi >= 0:
            cand = nodes[oi]
            if isinstance(cand, _Delim) and cand.char == closer.char and cand.can_open and cand.count:
                if closer.char == "~":
                    if cand.count == closer.count == 2:
                        opener = cand
                        break
                else:
                    odd = (cand.can_close or closer.can_open) and (cand.orig + closer.orig) % 3 == 0
                    if not odd or (cand.orig % 3 == 0 and closer.orig % 3 == 0):
                        opener = cand
                        break
            oi -= 1
        if opener is None:
            ci += 1
            continue
        if closer.char == "~":
            use, wrap = 2, Strike
        elif opener.count >= 2 and closer.count >= 2:
            use, wrap = 2, Strong
        else:
            use, wrap = 1, Emph
        opener.count -= use
        closer.count -= use
        inner = nodes[oi + 1 : ci]
        nodes[oi + 1 : ci] = [wrap(inner)]
        ci = oi + 2
        if opener.count == 0:
            del nodes[oi]
            ci -= 1
        if closer.count == 0:
            del nodes[ci]


def _finalize(nodes: list) -> list:
    out: list = []
    for node in nodes:
        if isinstance(node, _Delim):
            node = Text(node.char * node.count) if node.count else None
        elif isinstance(node, (Strong, Emph, Strike)):
            node.children = _finalize(node.children)
        if node is None:
            continue
        if isinstance(node, Text) and out and isinstance(out[-1], Text):
            out[-1] = Text(out[-1].text + node.text)
        else:
            out.append(node)
    return out


def plain_text(nodes: list) -> str:
    parts = []
    for node in nodes:
        if isinstance(node, (Text, Code)):
            parts.append(node.text)
        elif isinstance(node, (Strong, Emph, Strike, Link)):
            parts.append(plain_text(node.children))
        elif isinstance(node, Image):
            parts.append(node.alt)
        elif isinstance(node, LineBreak):
            parts.append(" ")
    return "".join(parts)


def github_slug(text: str) -> str:
    """Якорь заголовка, как его строит GitHub."""
    kept = [
        ch
        for ch in text.strip().lower()
        if ch in "-_ " or unicodedata.category(ch)[0] in "LNM"
    ]
    return "".join(kept).replace(" ", "-")


# ---------------------------------------------------------------------------
# Вывод Typst
# ---------------------------------------------------------------------------

TYPST_SPECIAL = set("\\#$*_@<>[]~`'\"/-+=")


def escape_text(s: str, *, after_call: bool = False) -> str:
    """Экранировать текст для разметки Typst.

    ``after_call``: текст идёт сразу после ``#функция(...)[...]``; точка или
    скобка в начале иначе продолжили бы вызов, а «;» Typst съел бы как конец
    выражения.
    """
    out = []
    last = len(s) - 1
    for idx, ch in enumerate(s):
        if ch in TYPST_SPECIAL:
            out.append("\\" + ch)
        elif idx == 0 and after_call and ch in ".(;":
            out.append("\\" + ch)
        elif ch == "." and idx > 0 and s[idx - 1].isdigit() and (idx == last or s[idx + 1].isspace()):
            out.append("\\.")  # «1. текст» в начале строки Typst считает нумерованным списком
        else:
            out.append(ch)
    return "".join(out)


def typst_string(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r", "").replace("\n", "\\n").replace("\t", "\\t")
    return f'"{s}"'


def _git(args: list[str], cwd: Path) -> str | None:
    """Вывод ``git -C cwd ARGS`` или None, если git нет или он завершился ошибкой."""
    try:
        result = subprocess.run(
            [GIT, "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8"
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def default_ref(start: Path) -> str:
    """Полный sha HEAD репозитория, в котором лежит ``start``; без git — ``GITHUB_BRANCH``."""
    sha = _git(["rev-parse", "--verify", "--quiet", "HEAD"], start)
    if sha and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
        return sha
    return GITHUB_BRANCH


@dataclass
class Context:
    base_dir: Path
    repo_root: Path
    github_repo: str = GITHUB_REPO
    ref: str = GITHUB_BRANCH
    labels: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    _ref_is_commit: bool | None = field(default=None, init=False, repr=False)
    _objects: dict[str, str | None] = field(default_factory=dict, init=False, repr=False)

    def ref_is_commit(self) -> bool:
        """``ref`` — коммит в локальном репозитории (проверяется один раз)."""
        if self._ref_is_commit is None:
            sha = _git(["rev-parse", "--verify", "--quiet", f"{self.ref}^{{commit}}"], self.repo_root)
            self._ref_is_commit = sha is not None
            if not self._ref_is_commit:
                self.warnings.append(
                    f"ref {self.ref} не найден как коммит в {self.repo_root} (нет git или такого "
                    "коммита); ссылки на файлы проверены только по рабочему дереву"
                )
        return self._ref_is_commit

    def object_type(self, rel: str) -> str | None:
        """Тип объекта ``ref:rel`` («blob», «tree»…) или None, если его нет в коммите."""
        if rel not in self._objects:
            spec = f"{self.ref}:" + ("" if rel == "." else rel)
            self._objects[rel] = _git(["cat-file", "-t", spec], self.repo_root)
        return self._objects[rel]


def resolve_link(dest: str, ctx: Context) -> tuple[str, str] | None:
    """Адрес ссылки → ("url", адрес), ("label", якорь) или None (оставить текстом)."""
    dest = dest.strip()
    if not dest:
        return None
    if dest.startswith("#"):
        slug = unquote(dest[1:])
        if slug in ctx.labels:
            return "label", slug
        ctx.warnings.append(f"якорь {dest} не найден среди заголовков; ссылка оставлена текстом")
        return None
    parts = urlsplit(dest)
    if parts.scheme or dest.startswith("//"):
        return "url", dest
    path = unquote(parts.path)
    root = Path(os.path.realpath(ctx.repo_root))
    base = Path(os.path.realpath(ctx.base_dir))
    if path.startswith("/"):
        rel = posixpath.normpath(path.lstrip("/") or ".")
    else:
        try:
            base_rel = base.relative_to(root).as_posix()
        except ValueError:
            ctx.warnings.append(f"{dest}: входной файл вне репозитория; ссылка оставлена как есть")
            return "url", dest
        rel = posixpath.normpath(posixpath.join(base_rel, path))
    if rel == ".." or rel.startswith("../"):
        ctx.warnings.append(f"{dest}: путь выходит за пределы репозитория; ссылка оставлена как есть")
        return "url", dest
    local = root / rel
    kind = "tree" if local.is_dir() or path.endswith("/") else "blob"
    if ctx.ref_is_commit():
        obj = ctx.object_type(rel)
        if obj is not None:
            kind = "tree" if obj == "tree" else "blob"
        else:
            where = (
                "в рабочем дереве есть: не закоммичен или в .gitignore"
                if local.exists()
                else "нет и в рабочем дереве"
            )
            ref = ctx.ref[:12] if re.fullmatch(r"[0-9a-f]{40,64}", ctx.ref) else ctx.ref
            ctx.warnings.append(f"{dest}: {rel} нет в коммите {ref} ({where}); ссылка на GitHub будет битой")
    elif not local.exists():
        ctx.warnings.append(f"{dest}: файла {rel} нет в рабочем дереве")
    url = f"https://github.com/{ctx.github_repo}/{kind}/{quote(ctx.ref, safe='/')}"
    if rel != ".":
        url += "/" + quote(rel, safe="/")
    if parts.query:
        url += "?" + parts.query
    if parts.fragment:
        url += "#" + parts.fragment
    return "url", url


def render_inline(nodes: list, ctx: Context, soft: dict[int, set[int]] | None = None) -> str:
    """``soft`` — места разрывов в коде (см. ``soft_breaks``)."""
    out: list[str] = []
    after_call = False
    for node in nodes:
        if isinstance(node, Text):
            out.append(escape_text(node.text, after_call=after_call))
            after_call = False
            continue
        if isinstance(node, Code):
            out.append(_raw_with_breaks(node.text, (soft or {}).get(id(node), set())))
        elif isinstance(node, Strong):
            out.append(f"#strong[{render_inline(node.children, ctx, soft)}]")
        elif isinstance(node, Emph):
            out.append(f"#emph[{render_inline(node.children, ctx, soft)}]")
        elif isinstance(node, Strike):
            out.append(f"#strike[{render_inline(node.children, ctx, soft)}]")
        elif isinstance(node, LineBreak):
            out.append("#linebreak()")
        elif isinstance(node, Link):
            body = render_inline(node.children, ctx, soft) or escape_text(node.dest)
            target = resolve_link(node.dest, ctx)
            if target is None:
                out.append(body)  # дальше всё равно экранируем «.» и «(»: безвредно
                after_call = True
                continue
            kind, value = target
            if kind == "label":
                out.append(f"#link(label({typst_string(value)}))[{body}]")
            else:
                out.append(f"#link({typst_string(value)})[{body}]")
        elif isinstance(node, Image):
            out.append(f"#box({_image_call(node, ctx, height='1.2em')})")
        after_call = True
    return "".join(out)


def _image_call(node: Image, ctx: Context, *, width: str | None = None, height: str | None = None) -> str:
    src = unquote(node.src.strip())
    if urlsplit(src).scheme:
        raise ConversionError(f"картинка по сети не поддержана: {src}")
    path = Path(os.path.realpath(ctx.base_dir / src))
    if not path.is_file():
        raise ConversionError(f"нет файла картинки: {src} (искали {path})")
    args = [typst_string(path.as_posix())]
    if width:
        args.append(f"width: {width}")
    if height:
        args.append(f"height: {height}")
    return f"image({', '.join(args)})"


def _render_block(block: object, ctx: Context) -> str:
    if isinstance(block, Heading):
        nodes = parse_inline(block.text)
        out = f"#heading(level: {block.level})[{render_inline(nodes, ctx)}]"
        if block.slug:
            out += f" #label({typst_string(block.slug)})"
        return out
    if isinstance(block, Paragraph):
        nodes = parse_inline(block.text)
        images = [x for x in nodes if not (isinstance(x, Text) and not x.text.strip())]
        if len(images) == 1 and isinstance(images[0], Image):
            image = images[0]
            call = _image_call(image, ctx, width="100%")
            if image.alt.strip():
                caption = render_inline(parse_inline(image.alt), ctx)
                return f"#figure({call}, caption: [{caption}], numbering: none)"
            return f"#figure({call}, numbering: none)"
        return render_inline(nodes, ctx)
    if isinstance(block, CodeBlock):
        lang = f", lang: {typst_string(block.lang)}" if block.lang else ""
        return f"#raw({typst_string(block.code)}, block: true{lang})"
    if isinstance(block, Rule):
        return "#line(length: 100%, stroke: 0.5pt + luma(150))"
    if isinstance(block, Table):
        columns, inner = table_columns(block)

        def row_cells(row: list[str], bold: bool = False) -> str:
            cells = []
            for c, cell in enumerate(row):
                nodes = parse_inline(cell)
                soft = soft_breaks(nodes, inner[c], bold) if inner[c] is not None else None
                cells.append(f"[{render_inline(nodes, ctx, soft)}]")
            return ", ".join(cells)

        lines = [
            "#table(",
            f"  columns: {columns},",
            f"  align: ({', '.join(block.aligns)},),",
            f"  table.header({row_cells(block.header, bold=True)}),",
        ]
        lines.extend(f"  {row_cells(row)}," for row in block.rows)
        lines.append(")")
        return "\n".join(lines)
    if isinstance(block, ListBlock):
        sep = "\n" if block.tight else "\n\n"
        items = []
        for item in block.items:
            items.append("[" + sep.join(_render_block(b, ctx) for b in item) + "]")
        tight = "true" if block.tight else "false"
        if block.ordered:
            head = f"#enum(start: {block.start}, tight: {tight},"
        else:
            head = f"#list(tight: {tight},"
        return head + "\n  " + ",\n  ".join(items) + ",\n)"
    raise TypeError(block)


# Ширины колонок таблиц. Знаки замерены typst на шрифтах преамбулы:
# PT Sans 8.5 pt ≈ 4.1 pt на знак, жирный ≈ 4.4, PT Mono (7.5 pt) ≈ 4.5.
TEXT_WIDTH_PT = 481.9  # A4 минус поля по 2 см
TABLE_TEXT_PT = 4.1
TABLE_BOLD_FACTOR = 1.08
TABLE_CODE_PT = 4.5
TABLE_CELL_PAD_PT = 9.0  # inset 4 pt с каждой стороны и линия
NARROW_COLUMN_CHARS = 14  # колонка не шире стольких знаков остаётся auto
HYPHEN_PIECE_CHARS = 9  # русское слово переносится по слогам
NO_BREAK_BEFORE = set(":;,.)]}!?/»…%")  # UAX 14: перед ними не рвут даже после пробела
CODE_SOFT_BREAK_AFTER = "._:,=;"
SOFT_BREAK = "#box()"  # место разрыва без знака в тексте (см. _raw_with_breaks)


Char = tuple[str, bool]  # знак и признак «это код»


def _flat_chars(nodes: list, out: list[Char], refs: list | None = None) -> list[Char]:
    """Знаки строки ячейки; в ``refs`` — (узел Code, номер знака) или None."""
    for node in nodes:
        if isinstance(node, Text):
            out.extend((ch, False) for ch in node.text)
            if refs is not None:
                refs.extend([None] * len(node.text))
        elif isinstance(node, Code):
            out.extend((ch, True) for ch in node.text)
            if refs is not None:
                refs.extend((node, k) for k in range(len(node.text)))
        elif isinstance(node, (Strong, Emph, Strike, Link)):
            _flat_chars(node.children, out, refs)
        elif isinstance(node, Image):
            out.extend(("x", False) for _ in range(4))
            if refs is not None:
                refs.extend([None] * 4)
    return out


def _unbreakable_spans(chars: list[Char]) -> list[tuple[int, int]]:
    """Неразрывные куски [начало, конец) по приближению UAX 14: пробел (кроме
    пробела перед «:», «,» и т. п.), после «/», после дефиса перед не-цифрой."""
    spans: list[tuple[int, int]] = []
    start = None
    for i, (ch, _) in enumerate(chars):
        if ch.isspace():
            rest = next((c for c, _ in chars[i + 1 :] if not c.isspace()), "")
            if start is not None and not (rest and rest in NO_BREAK_BEFORE):
                spans.append((start, i))
                start = None
            continue
        if start is None:
            start = i
        nxt = chars[i + 1][0] if i + 1 < len(chars) else ""
        if ch == "/" or (ch in "-–—" and not nxt.isdigit()):
            spans.append((start, i + 1))
            start = None
    if start is not None:
        spans.append((start, len(chars)))
    return spans


def _soft_points(chars: list[Char], start: int, end: int) -> list[int]:
    """Где внутри куска можно поставить разрыв: после «._:,=;» в коде и перед
    кодом, который идёт за неразрывным пробелом."""
    points = []
    for i in range(start + 1, end):
        prev, cur = chars[i - 1], chars[i]
        if (prev[1] and prev[0] in CODE_SOFT_BREAK_AFTER) or (cur[1] and prev[0] == " "):
            points.append(i)
    return points


def _span_pt(chars: list[Char], bold: bool) -> float:
    text = TABLE_TEXT_PT * (TABLE_BOLD_FACTOR if bold else 1.0)
    return sum(TABLE_CODE_PT if code else text for _, code in chars)


def _span_min_pt(chars: list[Char], start: int, end: int, bold: bool, soft: bool) -> float:
    """Минимальная ширина куска: русское слово переносится по слогам, код при
    ``soft`` рвётся в точках ``_soft_points``."""
    piece = chars[start:end]
    letters = [ch for ch, code in piece if not code and ch.isalpha()]
    cyrillic = [ch for ch in letters if "а" <= ch.lower() <= "я" or ch in "ёЁ"]
    width = _span_pt(piece, bold)
    if letters and len(cyrillic) >= 0.7 * len(piece):
        return min(width, HYPHEN_PIECE_CHARS * TABLE_TEXT_PT * (TABLE_BOLD_FACTOR if bold else 1.0))
    if not soft:
        return width
    cuts = [start, *_soft_points(chars, start, end), end]
    return max(_span_pt(chars[a:b], bold) for a, b in zip(cuts, cuts[1:]))


def soft_breaks(nodes: list, inner_pt: float, bold: bool = False) -> dict[int, set[int]]:
    """Для кусков шире ``inner_pt``: id узла Code → номера знаков, перед
    которыми ставится разрыв. Typst рвёт код только после «/», дефиса и на
    пробелах; длинное имя файла в узкой колонке иначе вылезет за линию."""
    refs: list = []
    chars = _flat_chars(nodes, [], refs)
    out: dict[int, set[int]] = {}
    for start, end in _unbreakable_spans(chars):
        if _span_pt(chars[start:end], bold) <= inner_pt:
            continue
        for i in _soft_points(chars, start, end):
            if refs[i] is not None:
                node, k = refs[i]
                out.setdefault(id(node), set()).add(k)
    return out


def _raw_with_breaks(text: str, points: set[int]) -> str:
    """``#raw`` с местами разрыва перед знаками ``points``.

    Разрыв — пустой ``#box()`` между кусками кода: Typst рвёт строку до и
    после него, а в текстовом слое PDF он ничего не оставляет. U+200B давал
    то же, но попадал в копируемый текст: путь из PDF не находился.
    """
    parts: list[str] = []
    prev = 0
    for k in sorted(points):
        if k > prev:
            parts.append(f"#raw({typst_string(text[prev:k])})")
        parts.append(SOFT_BREAK)
        prev = k
    parts.append(f"#raw({typst_string(text[prev:])})")
    return "".join(parts)


@dataclass
class _ColumnStats:
    widest: float = 0.0  # самая широкая ячейка в одну строку, pt
    widest_chars: int = 0
    volume: list[float] = field(default_factory=list)
    min_hard: float = 0.0  # самый длинный неразрывный кусок, pt
    min_soft: float = 0.0  # то же, если код можно рвать после «._:,=;»


def _column_stats(table: Table) -> list[_ColumnStats]:
    stats = [_ColumnStats() for _ in table.aligns]
    for r, row in enumerate([table.header, *table.rows]):
        bold = r == 0
        for c, cell in enumerate(row):
            chars = _flat_chars(parse_inline(cell), [])
            st = stats[c]
            width = _span_pt(chars, bold)
            st.widest = max(st.widest, width)
            st.widest_chars = max(st.widest_chars, len(chars))
            if width:
                st.volume.append(width)
            for a, b in _unbreakable_spans(chars):
                st.min_hard = max(st.min_hard, _span_min_pt(chars, a, b, bold, soft=False))
                st.min_soft = max(st.min_soft, _span_min_pt(chars, a, b, bold, soft=True))
    return stats


def table_columns(table: Table) -> tuple[str, list[float | None]]:
    """Ширины колонок и ширина текста каждой колонки в pt (None для auto).

    Таблица, которая помещается, получает ``auto`` у всех колонок. Иначе узкие
    колонки остаются ``auto``, а широкие получают абсолютную ширину: доля по
    объёму текста, но не меньше самого длинного неразрывного куска. Если
    места мало и для этого, длинный код получает места разрыва.
    """
    ncols = len(table.aligns)
    stats = _column_stats(table)
    pad = TABLE_CELL_PAD_PT
    if sum(st.widest + pad for st in stats) <= TEXT_WIDTH_PT:
        return str(ncols), [None] * ncols
    narrow = [st.widest_chars <= NARROW_COLUMN_CHARS for st in stats]
    wide = [c for c in range(ncols) if not narrow[c]]
    if not wide:
        return str(ncols), [None] * ncols
    # запас 5% на auto-колонки: если они окажутся уже, таблица чуть сузится
    free = TEXT_WIDTH_PT - sum(1.05 * (stats[c].widest + pad) for c in range(ncols) if narrow[c])
    minimum = {c: stats[c].min_hard + pad for c in wide}
    if sum(minimum.values()) > free:
        minimum = {c: stats[c].min_soft + pad for c in wide}
    weight = {}
    for c in wide:
        vol = stats[c].volume or [stats[c].widest]
        weight[c] = math.sqrt(sum(vol) / len(vol) * stats[c].widest)
    total_min = sum(minimum.values())
    if total_min >= free:
        widths = {c: minimum[c] * max(free, 1.0) / total_min for c in wide}
    else:
        # «водоналив»: доля по объёму текста, но не меньше минимума
        fixed: dict[int, float] = {}
        while True:
            pool = [c for c in wide if c not in fixed]
            rest = free - sum(fixed.values())
            total = sum(weight[c] for c in pool)
            alloc = {c: rest * weight[c] / total for c in pool}
            short = [c for c in pool if alloc[c] < minimum[c]]
            if not short:
                break
            for c in short:
                fixed[c] = minimum[c]
        widths = {**alloc, **fixed}
    specs = ["auto" if narrow[c] else f"{widths[c]:.1f}pt" for c in range(ncols)]
    inner = [None if narrow[c] else widths[c] - pad for c in range(ncols)]
    return "(" + ", ".join(specs) + ",)", inner


def _collect_headings(blocks: list[object], ctx: Context, counts: dict[str, int]) -> str:
    """Присвоить заголовкам якоря GitHub; вернуть текст первого заголовка."""
    title = ""
    for block in blocks:
        if isinstance(block, Heading):
            text = plain_text(parse_inline(block.text))
            title = title or text
            base = github_slug(text)
            if not base:
                continue
            if base in counts:
                counts[base] += 1
                slug = f"{base}-{counts[base]}"
            else:
                counts[base] = 0
                slug = base
            block.slug = slug
            ctx.labels.add(slug)
        elif isinstance(block, ListBlock):
            for item in block.items:
                title = title or _collect_headings(item, ctx, counts)
    return title


PREAMBLE = """\
#set document(title: {title})
#set page(paper: "a4", margin: (x: 2cm, y: 2cm), numbering: "1 / 1", number-align: center)
#set text(font: ("PT Serif", "Libertinus Serif", "New Computer Modern"), size: 10.5pt, lang: "ru")
#set par(justify: true, leading: 0.6em, spacing: 1.0em)
#show heading: set text(font: ("PT Sans", "Helvetica Neue"), weight: "bold")
#show heading: set block(above: 1.25em, below: 0.65em)
#show heading.where(level: 1): set text(size: 16pt)
#show heading.where(level: 1): set block(above: 1.6em, below: 0.9em)
#show heading.where(level: 2): set text(size: 13pt)
#show heading.where(level: 3): set text(size: 11.5pt)
#show heading.where(level: 4): set text(size: 10.5pt)
#show link: set text(fill: rgb("#0b57b7"))
#show raw: set text(font: ("PT Mono", "Menlo", "DejaVu Sans Mono"))
#show raw.where(block: false): set text(size: 1.1em)
#show raw.where(block: true): set text(size: 8.5pt)
#show raw.where(block: true): block.with(fill: luma(245), inset: 6pt, radius: 2pt, width: 100%)
#set list(indent: 0.4em, body-indent: 0.5em)
#set enum(indent: 0.4em, body-indent: 0.5em)
#set table(stroke: 0.4pt + luma(165), inset: (x: 4pt, y: 3pt))
#set table.cell(breakable: false)
#show table: set text(font: ("PT Sans", "Helvetica Neue"), size: 8.5pt, hyphenate: true)
#show table: set par(justify: false, leading: 0.5em)
#show table.cell.where(y: 0): set text(weight: "bold")
#set table(fill: (_, y) => if y == 0 {{ luma(235) }})
#show figure: set block(above: 1em, below: 1em)
"""


def _warning_line(warning: str) -> int:
    m = re.match(r"строка (\d+):", warning)
    return int(m.group(1)) if m else 0


def markdown_to_typst(
    md: str,
    *,
    base_dir: Path,
    repo_root: Path,
    github_repo: str = GITHUB_REPO,
    ref: str | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Перевести Markdown отчёта в полный документ Typst.

    ``ref`` — коммит или ветка в ссылках на GitHub; по умолчанию sha HEAD
    репозитория ``base_dir`` (см. ``default_ref``)."""
    md = md.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    found: list[str] = []
    numbered = _drop_sections_numbered(
        _strip_comments_numbered(_numbered(md)), DROPPED_SECTIONS, found
    )
    blocks = parse_blocks([line for _, line in numbered], [no for no, _ in numbered], found)
    found.sort(key=_warning_line)
    if ref is None:
        ref = default_ref(Path(base_dir))
        if ref == GITHUB_BRANCH:
            found.append(
                f"sha HEAD не получен (нет git или {base_dir} вне репозитория): ссылки ведут на "
                f"ветку {GITHUB_BRANCH} и уедут вместе с ней; задай --ref"
            )
    ctx = Context(Path(base_dir), Path(repo_root), github_repo, ref)
    title = _collect_headings(blocks, ctx, {})
    body = "\n\n".join(_render_block(b, ctx) for b in blocks)
    if warnings is not None:
        warnings.extend(found + ctx.warnings)
    return PREAMBLE.format(title=typst_string(title or "Отчёт")) + "\n" + body + "\n"


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


def build_pdf(
    input_md: Path,
    output_pdf: Path,
    *,
    typst: str | None = None,
    typ_out: Path | None = None,
    repo_root: Path | None = None,
    ref: str | None = None,
) -> list[str]:
    """Собрать PDF; вернуть предупреждения конвертера и typst."""
    input_md = Path(os.path.realpath(input_md))
    base_dir = input_md.parent
    root = repo_root or find_repo_root(base_dir)
    warnings: list[str] = []
    source = markdown_to_typst(
        input_md.read_text(encoding="utf-8"),
        base_dir=base_dir,
        repo_root=root,
        ref=ref,
        warnings=warnings,
    )
    exe = typst or shutil.which("typst") or DEFAULT_TYPST
    output_pdf = Path(output_pdf).resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="writeup-pdf-") as tmp:
        typ_path = Path(typ_out).resolve() if typ_out else Path(tmp) / "writeup.typ"
        typ_path.parent.mkdir(parents=True, exist_ok=True)
        typ_path.write_text(source, encoding="utf-8", newline="\n")
        cmd = [exe, "compile", "--root", "/", "--diagnostic-format", "short", str(typ_path), str(output_pdf)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    diagnostics = (result.stderr or "").strip()
    if result.returncode != 0:
        raise ConversionError(f"typst compile завершился с кодом {result.returncode}:\n{diagnostics}")
    if diagnostics:
        warnings.extend(diagnostics.splitlines())
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown-отчёт → PDF через Typst")
    parser.add_argument("input", type=Path, help="входной .md")
    parser.add_argument("output", type=Path, help="выходной .pdf")
    parser.add_argument("--typ", type=Path, help="сохранить промежуточный .typ")
    parser.add_argument("--typst", help="путь к typst (по умолчанию из PATH или /opt/homebrew/bin/typst)")
    parser.add_argument("--repo-root", type=Path, help="корень репозитория для ссылок на GitHub")
    parser.add_argument(
        "--ref",
        help=(
            "коммит или ветка в ссылках /blob/REF/... (по умолчанию полный sha HEAD репозитория "
            f"входного файла, без git — {GITHUB_BRANCH}); коммит должен быть запушен"
        ),
    )
    args = parser.parse_args(argv)
    try:
        warnings = build_pdf(
            args.input,
            args.output,
            typst=args.typst,
            typ_out=args.typ,
            repo_root=args.repo_root,
            ref=args.ref,
        )
    except (ConversionError, OSError) as exc:
        print(f"writeup_pdf: ошибка: {exc}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"writeup_pdf: предупреждение: {warning}", file=sys.stderr)
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
