"""Проверка подписей рисунков отчёта: text_problems из scripts/writeup_figures.py."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from scripts.writeup_figures import text_problems  # noqa: E402


class TextProblemsTests(unittest.TestCase):
    def test_overlapping_formatter_ticks_are_caught_on_first_call(self):
        # подписи делений от FuncFormatter пусты до отрисовки: проверка обязана их видеть
        fig, ax = plt.subplots(figsize=(1.5, 1.0))
        ax.set_xlim(0, 1)
        ax.set_xticks([k / 20 for k in range(21)])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"+{x:.4f}"))
        ax.tick_params(labelsize=8)  # get_xticklabels() заполнил бы подписи заранее
        try:
            problems = text_problems(fig)
        finally:
            plt.close(fig)
        self.assertTrue(any("наезжают" in p for p in problems), problems)

    def test_long_dash_in_tick_label_is_caught(self):
        fig, ax = plt.subplots(figsize=(4, 2))
        ax.set_xticks([0.5])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: "a — b"))
        ax.tick_params(labelsize=8)  # get_xticklabels() заполнил бы подписи заранее
        try:
            problems = text_problems(fig)
        finally:
            plt.close(fig)
        self.assertTrue(any("длинное тире" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
