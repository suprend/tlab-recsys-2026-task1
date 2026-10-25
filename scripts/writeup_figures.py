"""Рисунки отчёта docs/writeup/REPORT.md: рис. 1 (fig-rees46-verdict.png) и
рис. 2 (fig-otto-dev-vs-private.png) в docs/writeup/fig/.

Все числа лежат ниже в одном словаре FACTS; у каждого значения — ID факта из
docs/writeup/facts.md. Скрипт не читает ни артефактов, ни данных, ни facts.md:
при правке facts.md значения правятся здесь вручную, по ID.

Значения хранятся строками ровно в том виде, в каком они записаны в facts.md:
так подписи на рисунках совпадают с источником символ в символ.

Запуск: .venv/bin/python -I scripts/writeup_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

# --------------------------------------------------------------------------
# Числа. Единственный источник — docs/writeup/facts.md (ID в комментариях).
# Тройка (оценка, нижняя, верхняя) — разность и её 95% CI парного бутстрапа.
# --------------------------------------------------------------------------
FACTS = {
    # ---- REES46: разности NDCG@20 с ручной базой H -------------------------
    # Порог: разности меньше ≈0.001 не считаются установленными даже при CI > 0.
    "rees_noise": "0.001",  # REES46, «Обязательные оговорки», п. 4 (шум зёрен — R48)
    # база + вся автоматика без отбора (H+ − H)
    "hplus_b2019": ("+0.00221", "+0.00118", "+0.00324"),  # R23, среднее зёрен, описательно (B после теста)
    "hplus_t2020_s1": ("+0.00307", "+0.00249", "+0.00364"),  # R24, первое зерно, по протоколу
    "hplus_t2020_s2": ("+0.00290", "+0.00233", "+0.00347"),  # R24, второе зерно, по протоколу
    # лучший (единственный принятый) признак агента p5
    "p5_t2019": ("+0.00035", "-0.00008", "+0.00079"),  # R13, по протоколу
    "p5_t2020": ("+0.00081", "+0.00047", "+0.00116"),  # R14, по протоколу
    # DFS, 20 лучших оконных агрегатов
    "dfs_t2019": ("-0.00075", "-0.00116", "-0.00035"),  # R18, по протоколу
    "dfs_t2020": ("-0.00033", "-0.00062", "-0.00001"),  # R18, по протоколу
    # автоматика вместо ручных признаков (F1 − H)
    "f1_b2019": ("-0.00253", "-0.00390", "-0.00125"),  # R20, описательно (B после теста)
    "f1_t2020": ("-0.00112", "-0.00174", "-0.00053"),  # R21, по протоколу
    # новые источники кандидатов в ручной базе (base − base_4src)
    "src_t2019": ("+0.00358", "+0.00301", "+0.00412"),  # R5, вместе с глубиной 8, по протоколу
    "src_t2020": ("+0.00208", "+0.00163", "+0.00250"),  # R6, при одинаковой глубине 8, по протоколу
    # ---- OTTO: согласие приростов dev F3 и private (раздел 2.3) -------------
    "otto_d_B_otto1_dev": ("+0.0855", "0.0838", "0.0873"),  # O9 (зерно 2026), описательно
    "otto_d_B_otto1_private": ("+0.08823", "+0.08820"),  # O15, зёрна 2026 / 2027, описательно
    "otto_d_B_otto1_private_short": "+0.0882",  # оговорка i («B → OTTO-1 (+0.0882 private)»)
    "otto_d_otto1_it1000": ("+0.0011", "+0.0014"),  # таблица 2.3 (dev, private)
    "otto_d_it1000_lr10": ("+0.0009", "+0.0003"),  # таблица 2.3 (dev, private)
    "otto_d_otto1_otto2": ("+0.0020", "+0.0017"),  # таблица 2.3 (dev вычислено), исследовательский
    "otto_d_otto2_i1_dev": ("+0.0125", "+0.0115", "+0.0134"),  # G3, O36
    "otto_d_otto2_i1_private": "+0.0125",  # таблица 2.3
    "otto_d_i1_i2_dev": ("+0.0024", "+0.0018", "+0.0030"),  # G4, O36
    "otto_d_i1_i2_private": "+0.0025",  # таблица 2.3
    "otto_d_otto2_i2_dev": ("+0.0149", "+0.0139", "+0.0159"),  # G5, O36
    "otto_d_otto2_i2_private": "+0.0150",  # таблица 2.3 (вычислено)
    "otto_d_i2_i3_dev": ("+0.0009", "+0.0004", "+0.0014"),  # G12
    "otto_d_i2_i3_private": "+0.0008",  # таблица 2.3 (вычислено)
    "otto_d_otto2_i3_dev": ("+0.0158", "+0.0148", "+0.0168"),  # G13
    "otto_d_otto2_i3_private": "+0.0158",  # таблица 2.3 (вычислено)
}

# --------------------------------------------------------------------------
# Оформление
# --------------------------------------------------------------------------
OUT = Path(__file__).resolve().parents[1] / "docs" / "writeup" / "fig"
DPI = 200
WIDTH_IN = 16 / 2.54  # 16 см под A4

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BAND = "#ecebe6"
BLUE = "#1c5cab"  # private / проверено по правилу
ORANGE = "#eb6834"  # неделя для выбора (dev F3)
GRAYM = "#6f6e69"  # описательно

# Метка доказательности несёт форма маркера (и текст в легенде и подписях).
EVID = {
    "protocol": dict(marker="o", ms=5.2, color=BLUE, text="по протоколу"),
    "holdout": dict(marker="s", ms=4.8, color=BLUE, text="holdout с отклонением"),
    "descriptive": dict(marker="D", ms=4.4, color=GRAYM, text="описательно"),
    "exploratory": dict(marker="^", ms=5.6, color=BLUE, text="исследовательский"),
}

# Рисунок шириной 16 см растягивается на 17 см набора, так что 7.5 pt на
# рисунке дают на странице ≈8 pt. Мельче 7.5 pt шрифт нигде не ставится
# (``save`` это проверяет); к тому же PT Sans из PTSans.ttc при 200 dpi
# мельче 6.7 pt молча пропадает.
MIN_FONT_PT = 7.5
plt.rcParams.update(
    {
        "font.family": ["PT Sans", "Helvetica", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 7.5,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.6,
        "axes.unicode_minus": True,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.fontsize": 7.5,
        "legend.frameon": False,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
)


def num(s: str) -> float:
    return float(s)


def txt(s: str) -> str:
    """Число из FACTS для подписи: типографский минус."""
    return s.replace("-", "−")


def signed_tick(x: float, _pos=None, nd: int = 3) -> str:
    if abs(x) < 1e-12:
        return "0"
    s = f"{x:+.{nd}f}"
    return s.replace("-", "−")


def plot_ci(ax, est, lo, hi, y, evid: str, filled: bool = True, color: str | None = None, zorder=3):
    st = EVID[evid]
    c = color or st["color"]
    ax.plot([lo, hi], [y, y], color=c, lw=1.3, solid_capstyle="butt", zorder=zorder)
    ax.plot(
        [est],
        [y],
        marker=st["marker"],
        ms=st["ms"],
        mfc=c if filled else "white",
        mec=c if filled else c,
        mew=1.1,
        ls="none",
        zorder=zorder + 1,
    )


def plot_point(ax, x, y, evid: str, filled: bool = True, color: str | None = None, zorder=4):
    st = EVID[evid]
    c = color or st["color"]
    ax.plot(
        [x],
        [y],
        marker=st["marker"],
        ms=st["ms"],
        mfc=c if filled else "white",
        mec=c,
        mew=1.1,
        ls="none",
        zorder=zorder,
    )


def evid_handle(evid: str, label: str | None = None, filled: bool = True, color: str | None = None):
    st = EVID[evid]
    c = color or st["color"]
    return Line2D(
        [],
        [],
        marker=st["marker"],
        ms=st["ms"],
        mfc=c if filled else "white",
        mec=c,
        mew=1.1,
        ls="none",
        label=label or st["text"],
    )


def clean_axes(ax, left=False):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if not left:
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", left=False, labelleft=False)


def text_problems(fig) -> list[str]:
    """Подписи мельче MIN_FONT_PT, с длинным тире, за краем рисунка или
    наезжающие друг на друга (по рамкам текста после отрисовки)."""
    from matplotlib.text import Text

    fig.canvas.draw()  # до сбора: подписи делений от FuncFormatter пусты до отрисовки
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    problems = [f"мельче {MIN_FONT_PT} pt: «{t.get_text()}»" for t in texts if t.get_fontsize() < MIN_FONT_PT]
    problems += [f"длинное тире: «{t.get_text()}»" for t in texts if "—" in t.get_text()]
    renderer = fig.canvas.get_renderer()
    page = fig.bbox
    boxes = [(t, t.get_window_extent(renderer)) for t in texts]
    for t, b in boxes:
        if b.x0 < page.x0 - 0.5 or b.y0 < page.y0 - 0.5 or b.x1 > page.x1 + 0.5 or b.y1 > page.y1 + 0.5:
            problems.append(f"за краем рисунка: «{t.get_text()}»")
    for i, (t, b) in enumerate(boxes):
        for u, c in boxes[i + 1 :]:
            if b.overlaps(c) and min(b.x1, c.x1) - max(b.x0, c.x0) > 1 and min(b.y1, c.y1) - max(b.y0, c.y0) > 1:
                problems.append(f"наезжают: «{t.get_text()}» и «{u.get_text()}»")
    return problems


def save(fig, name: str) -> Path:
    problems = text_problems(fig)
    if problems:
        raise SystemExit(f"{name}: " + "; ".join(problems[:5]))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Общая раскладка: строки слева, интервалы на оси, числа справа (если есть)
# --------------------------------------------------------------------------
class RowLayout:
    """Строки сверху вниз: заголовки групп, подзаголовки и строки с интервалами."""

    def __init__(self):
        self.items: list[dict] = []
        self.y = 0.0

    def header(self, text: str, gap: float = 0.0):
        self.y -= gap
        self.items.append(dict(kind="header", y=self.y, text=text))
        self.y -= 1.0

    def sub(self, text: str):
        self.y += 0.25
        self.items.append(dict(kind="sub", y=self.y, text=text))
        self.y -= 1.0

    def row(self, text: str, height: float = 1.0, **kw):
        """Строка; ``height`` больше 1 — для подписи в две строки."""
        self.items.append(dict(kind="row", y=self.y - (height - 1.0) / 2, text=text, **kw))
        self.y -= height

    def separator(self):
        self.items.append(dict(kind="sep", y=self.y + 0.5))

    @property
    def span(self) -> float:
        return -self.y


def draw_labels(fig, ax, items, x_header, x_row, x_value=None, x_sep=(0.0, 1.0)):
    tr = blended_transform_factory(fig.transFigure, ax.transData)
    for it in items:
        if it["kind"] == "header":
            fig.text(x_header, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=8, fontweight="bold", color=INK)
        elif it["kind"] == "sub":
            fig.text(x_header, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=7.5, color=MUTED)
        elif it["kind"] == "row":
            fig.text(x_row, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=7.5, color=INK2, linespacing=1.15)
            if it.get("value") and x_value is not None:
                fig.text(x_value, it["y"], it["value"], transform=tr, va="center", ha="left",
                         fontsize=7.5, color=INK2)
        elif it["kind"] == "sep":
            fig.add_artist(Line2D(list(x_sep), [it["y"], it["y"]], transform=tr, color=GRID, lw=0.6))


# --------------------------------------------------------------------------
# Рис. 1. REES46: вердикт-карта
# --------------------------------------------------------------------------
def fig_rees46_verdict() -> Path:
    F = FACTS
    L = RowLayout()

    L.header("вся автоматика без отбора")
    L.sub("колонки агента и DFS поверх ручной базы")
    L.row("подтверждающая половина 2019 (описательно)", ci=F["hplus_b2019"], evid="descriptive")
    L.row("тест 2020, первое зерно", ci=F["hplus_t2020_s1"], evid="protocol")
    L.row("тест 2020, второе зерно", ci=F["hplus_t2020_s2"], evid="protocol")
    L.separator()
    L.header("лучший признак агента", gap=0.3)
    L.row("тест 2019", ci=F["p5_t2019"], evid="protocol")
    L.row("тест 2020", ci=F["p5_t2020"], evid="protocol")
    L.separator()
    L.header("DFS, 20 лучших оконных агрегатов", gap=0.3)
    L.row("тест 2019", ci=F["dfs_t2019"], evid="protocol")
    L.row("тест 2020", ci=F["dfs_t2020"], evid="protocol")
    L.separator()
    L.header("автоматика вместо ручных признаков", gap=0.3)
    L.row("подтверждающая половина 2019 (описательно)", ci=F["f1_b2019"], evid="descriptive")
    L.row("тест 2020", ci=F["f1_t2020"], evid="protocol")
    L.separator()
    L.header("новые источники кандидатов", gap=0.3)
    L.sub("для масштаба: ручная база, 6 источников против 4")
    L.row("тест 2019 (вместе с глубиной 8)", ci=F["src_t2019"], evid="protocol")
    L.row("тест 2020 (при равной глубине 8)", ci=F["src_t2020"], evid="protocol")

    # числа справа не пишутся: точку видно по оси, главные числа есть в тексте
    unit = 0.168  # дюйма на строку
    top, bottom = 0.30, 0.42
    ax_h = (L.span + 0.2) * unit
    H = top + ax_h + bottom
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1 = 0.385, 0.975
    ax = fig.add_axes([x0, bottom / H, x1 - x0, ax_h / H])
    ax.set_ylim(L.y + 0.5, 0.7)

    thr = num(F["rees_noise"])
    ax.axvspan(-thr, thr, color=BAND, lw=0, zorder=0)
    ax.axvline(0, color=INK2, lw=0.8, zorder=1)
    ax.set_xlim(-0.0045, 0.0045)
    ticks = [i / 1000 for i in range(-4, 5)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([signed_tick(t) if i % 2 == 0 else "" for i, t in enumerate(ticks)])
    ax.grid(axis="x", color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    clean_axes(ax)
    ax.set_xlabel("разность NDCG@20 с ручной базой, абс. ед. Линия: 95% CI парного бутстрапа")

    for it in L.items:
        if it["kind"] == "row":
            est, lo, hi = (num(v) for v in it["ci"])
            plot_ci(ax, est, lo, hi, it["y"], it["evid"])

    draw_labels(fig, ax, L.items, x_header=0.012, x_row=0.028, x_sep=(0.012, 0.99))

    handles = [
        evid_handle("protocol", "по протоколу: тест открыт один раз"),
        evid_handle("descriptive", "описательно: посчитано после теста"),
        Patch(facecolor=BAND, edgecolor="none", label=f"|Δ| < {F['rees_noise']}: ниже порога шума"),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=3,
               handletextpad=0.4, columnspacing=1.0, borderaxespad=0.3)
    return save(fig, "fig-rees46-verdict.png")


# --------------------------------------------------------------------------
# Рис. 2. OTTO: приросты за шаг на неделе для выбора и на Kaggle private
# --------------------------------------------------------------------------
def fig_otto_dev_vs_private() -> Path:
    F = FACTS
    OFF = 0.17  # неделя для выбора чуть выше линии строки, Kaggle private чуть ниже
    HEAD = 0.55  # заголовок группы стоит над осью на столько строк

    # панель A: простая база → OTTO-1 (масштаб другой)
    LA = RowLayout()
    LA.header("простая база → OTTO-1 (описательно)")
    LA.row("агент добавил кандидаты и признаки", dev=F["otto_d_B_otto1_dev"],
           private=F["otto_d_B_otto1_private"], evid="descriptive",
           value=f"{txt(F['otto_d_B_otto1_dev'][0])} / {txt(F['otto_d_B_otto1_private_short'])}")

    # строки «в т. ч.» — рецепты из docs/otto2.md:27–28
    LB = RowLayout()
    LB.header("OTTO-2 и OTTO-3 (исследовательский)")
    LB.row("OTTO-1 → OTTO-2: обучение ранкера", dev=(F["otto_d_otto1_otto2"][0],),
           private=(F["otto_d_otto1_otto2"][1],), evid="exploratory")
    LB.row("    в т. ч. обучение на всех размеченных сессиях\n    недели вместо выборки, 1000 деревьев",
           height=1.5, dev=(F["otto_d_otto1_it1000"][0],), private=(F["otto_d_otto1_it1000"][1],),
           evid="exploratory")
    LB.row("    в т. ч. затем 2000 деревьев с шагом 0.1", dev=(F["otto_d_it1000_lr10"][0],),
           private=(F["otto_d_it1000_lr10"][1],), evid="exploratory")
    LB.separator()
    LB.row("OTTO-2 → OTTO-3, итерация 1: новый набор агента", dev=F["otto_d_otto2_i1_dev"],
           private=(F["otto_d_otto2_i1_private"],), evid="exploratory")
    LB.row("итерация 1 → 2: 18 новых предложений агента", dev=F["otto_d_i1_i2_dev"],
           private=(F["otto_d_i1_i2_private"],), evid="exploratory")
    LB.row("итерация 2 → 3: 20 новых предложений агента", dev=F["otto_d_i2_i3_dev"],
           private=(F["otto_d_i2_i3_private"],), evid="exploratory")
    LB.row("OTTO-2 → итерация 3: итог OTTO-3", dev=F["otto_d_otto2_i3_dev"],
           private=(F["otto_d_otto2_i3_private"],), evid="exploratory")
    for it in LB.items:
        if it["kind"] == "row":
            it["value"] = f"{txt(it['dev'][0])} / {txt(it['private'][0])}"

    unit = 0.20
    top_m, mid, bot_m = 0.62, 0.50, 0.40
    limA = (LA.y + 0.5, -HEAD)
    limB = (LB.y + 0.5, -HEAD)
    hA = (limA[1] - limA[0]) * unit
    hB = (limB[1] - limB[0]) * unit
    H = top_m + hA + mid + hB + bot_m
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1, xv = 0.43, 0.80, 0.815
    axB = fig.add_axes([x0, bot_m / H, x1 - x0, hB / H])
    axA = fig.add_axes([x0, (bot_m + hB + mid) / H, x1 - x0, hA / H])
    axA.set_ylim(*limA)
    axB.set_ylim(*limB)
    axA.set_xlim(0.0830, 0.0905)
    axA.set_xticks([0.084, 0.086, 0.088, 0.090])
    axB.set_xlim(-0.0006, 0.0176)
    axB.set_xticks([0, 0.004, 0.008, 0.012, 0.016])
    for ax, layout in ((axA, LA), (axB, LB)):
        clean_axes(ax)
        ax.grid(axis="x", color=GRID, lw=0.5, zorder=0)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(lambda v, p: signed_tick(v, p, nd=3))
        for it in layout.items:
            if it["kind"] != "row":
                continue
            y = it["y"]
            dev = it["dev"]
            if len(dev) == 3:
                plot_ci(ax, num(dev[0]), num(dev[1]), num(dev[2]), y + OFF, it["evid"], filled=False, color=ORANGE)
            else:
                plot_point(ax, num(dev[0]), y + OFF, it["evid"], filled=False, color=ORANGE)
            for p in it["private"]:
                plot_point(ax, num(p), y - OFF, it["evid"], filled=True, color=BLUE)
        draw_labels(fig, ax, layout.items, x_header=0.012, x_row=0.028, x_value=xv, x_sep=(0.012, 0.99))
    axB.axvline(0, color=INK2, lw=0.8, zorder=1)
    axA.set_xlabel("прирост Score за шаг (ось не от нуля)")
    axB.set_xlabel("прирост Score за шаг, абс. ед. Усы: 95% CI парного бутстрапа на неделе для выбора")

    tr = blended_transform_factory(fig.transFigure, axA.transData)
    fig.text(xv, 0, "выбор / private", transform=tr, va="center", ha="left", fontsize=7.5, color=MUTED)

    handles = [
        evid_handle("descriptive", "неделя для выбора, описательно", filled=False, color=ORANGE),
        evid_handle("exploratory", "неделя для выбора, исследовательский", filled=False, color=ORANGE),
        evid_handle("descriptive", "Kaggle private, описательно", filled=True, color=BLUE),
        evid_handle("exploratory", "Kaggle private, исследовательский", filled=True, color=BLUE),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=2,
               handletextpad=0.4, columnspacing=1.6, borderaxespad=0.3)
    return save(fig, "fig-otto-dev-vs-private.png")


def main() -> None:
    for build in (fig_rees46_verdict, fig_otto_dev_vs_private):
        path = build()
        print(path.relative_to(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    main()
