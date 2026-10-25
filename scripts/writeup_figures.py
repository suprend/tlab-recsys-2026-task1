"""Рисунки для короткого отчёта task1-v2: docs/writeup/fig/*.png.

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
    # только колонки агента поверх H (Hag − H), val 2020, два зерна, без CI
    "hag_val2020": ("+0.00344", "+0.00343"),  # R36, описательно
    # ---- Перенос: BA − B («база набора + колонки агента» − «база набора») ----
    "tinkoff_holdout_s2026": ("+0.00211", "+0.00130", "+0.00293"),  # T29, holdout с отклонением
    "tinkoff_holdout_s2027": ("+0.00123", "+0.00047", "+0.00198"),  # T29, holdout с отклонением
    "tinkoff_kaggle_mean_diff": "-0.002335",  # T34: разность средних 0.002335, «BA ниже B»; описательно
    "tinkoff_kaggle_verdict": "BA ниже B",  # T34
    "sber_holdout_s2026": ("+0.00282", "+0.00251", "+0.00313"),  # T46, holdout с отклонением
    "sber_holdout_s2027": ("+0.00280", "+0.00252", "+0.00310"),  # T46, holdout с отклонением
    "sber_kaggle_status": "BA не отправлялась: гейт 2 не пройден",  # T50
    "hm_week_s2026": ("+0.00289", "+0.00018", "+0.00573"),  # T10, неделя 09-16, описательно
    "hm_week_s2027": ("+0.00303", "-0.00088", "+0.00691"),  # T10, неделя 09-16, описательно
    "hm_kaggle_mean_diff": "+0.000425",  # T18: разность средних MA − M23; описательно
    "hm_kaggle_verdict": "не различено",  # T18
    # ---- OTTO: лестница (Score; private — неделя Kaggle F5) ------------------
    "otto_private_B": "0.4906",  # таблица 2.1 (O5: 0.49059 / 0.49053), описательно
    "otto_private_otto1": "0.57878",  # таблица 2.1, O14 (среднее зёрен), описательно
    "otto_private_otto2": "0.58049",  # O18, исследовательский
    "otto_private_i1": "0.59299",  # O25, исследовательский
    "otto_private_i2": "0.59548",  # O32, G1, исследовательский
    "otto_private_i3": "0.59628",  # O33, G1, исследовательский
    "otto_dev_B": "0.4778",  # O1, описательно
    "otto_dev_otto1": "0.5633",  # O8, описательно
    "otto_dev_otto2": "0.5653",  # O16, исследовательский
    "otto_dev_i1": "0.5777",  # O24, исследовательский
    "otto_dev_i2": "0.5802",  # O31, исследовательский
    "otto_dev_i3": "0.5810",  # O33, исследовательский
    "otto_calls_otto1": "6",  # таблица 2.1, O6
    "otto_calls_i1": "8",  # таблица 2.1, O20
    "otto_new_proposals_i2": "18",  # таблица 2.1 («18 новых предложений сделал агент»)
    "otto_calls_i2": "4",  # таблица 2.1 («(4 вызова)»), O26: модель вызывалась в 4 раундах из 12
    "otto_calls_i3": "4",  # таблица 2.1 («(4 вызова)»), docs/otto3.md:127: 16 раундов, 12 — повтор i2
    "otto_new_proposals_i3": "20",  # docs/otto3.md:127: 4 раунда F, 20 действительных предложений
    # пороги §10 по private (записаны до чисел; ориентиры по чужим отчётам, не проверены)
    "otto_thr_notebook": "0.575",  # O45, O46
    "otto_thr_works": "0.580",  # O45, O46
    "otto_thr_weighty": "0.590",  # O45, O46
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
WASH = "#f5f4f0"
BLUE = "#1c5cab"  # private / проверено по правилу
ORANGE = "#eb6834"  # dev F3
GRAYM = "#6f6e69"  # описательно

# Метка доказательности несёт форма маркера (и текст в легенде и подписях).
EVID = {
    "protocol": dict(marker="o", ms=5.2, color=BLUE, text="по протоколу"),
    "holdout": dict(marker="s", ms=4.8, color=BLUE, text="holdout с отклонением"),
    "descriptive": dict(marker="D", ms=4.4, color=GRAYM, text="описательно"),
    "exploratory": dict(marker="^", ms=5.6, color=BLUE, text="исследовательский"),
}

# Обычное начертание PT Sans из PTSans.ttc при 200 dpi не рисуется мельче
# 6.7 pt: текст молча пропадает. Поэтому шрифт нигде не меньше 6.8 pt.
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
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.fontsize": 7.2,
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


def ci_text(t: tuple[str, str, str]) -> str:
    return f"{txt(t[0])} [{txt(t[1])}, {txt(t[2])}]"


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


def save(fig, name: str) -> Path:
    from matplotlib.text import Text

    small = [t.get_text() for t in fig.findobj(Text) if t.get_text().strip() and t.get_fontsize() < 6.8]
    if small:
        raise SystemExit(f"{name}: шрифт меньше 6.8 pt пропадёт при печати: {small[:3]}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Общая раскладка «строки слева — интервалы — числа справа»
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

    def row(self, text: str, **kw):
        self.items.append(dict(kind="row", y=self.y, text=text, **kw))
        self.y -= 1.0

    def separator(self):
        self.items.append(dict(kind="sep", y=self.y + 0.5))

    @property
    def span(self) -> float:
        return -self.y


def draw_labels(fig, ax, items, x_header, x_row, x_value, x_sep=(0.0, 1.0)):
    tr = blended_transform_factory(fig.transFigure, ax.transData)
    for it in items:
        if it["kind"] == "header":
            fig.text(x_header, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=8, fontweight="bold", color=INK)
        elif it["kind"] == "sub":
            fig.text(x_header, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=7, color=MUTED)
        elif it["kind"] == "row":
            fig.text(x_row, it["y"], it["text"], transform=tr, va="center", ha="left",
                     fontsize=7.5, color=INK2)
            if it.get("value"):
                fig.text(x_value, it["y"], it["value"], transform=tr, va="center", ha="left",
                         fontsize=7.2, color=INK2)
        elif it["kind"] == "sep":
            fig.add_artist(Line2D(list(x_sep), [it["y"], it["y"]], transform=tr, color=GRID, lw=0.6))


# --------------------------------------------------------------------------
# Рис. 1. REES46: вердикт-карта
# --------------------------------------------------------------------------
def fig_rees46_verdict() -> Path:
    F = FACTS
    L = RowLayout()

    L.header("база + вся автоматика без отбора")
    L.sub("таблицы агента и DFS поверх ручной базы")
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

    for it in L.items:
        if it["kind"] == "row":
            it["value"] = ci_text(it["ci"])

    unit = 0.168  # дюйма на строку
    top, bottom = 0.40, 0.42
    ax_h = (L.span + 0.2) * unit
    H = top + ax_h + bottom
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1 = 0.385, 0.725
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
    ax.set_xlabel("разность NDCG@20 с ручной базой, абс. ед.; линия — 95% CI парного бутстрапа")

    for it in L.items:
        if it["kind"] == "row":
            est, lo, hi = (num(v) for v in it["ci"])
            plot_ci(ax, est, lo, hi, it["y"], it["evid"])

    draw_labels(fig, ax, L.items, x_header=0.012, x_row=0.028, x_value=0.738, x_sep=(0.012, 0.99))

    handles = [
        evid_handle("protocol", "по протоколу: тест открыт один раз"),
        evid_handle("descriptive", "описательно: прочитано после теста"),
        Patch(facecolor=BAND, edgecolor="none", label=f"|Δ| < {F['rees_noise']}: ниже разрешения проверки"),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=3,
               handletextpad=0.4, columnspacing=1.4, borderaxespad=0.3)
    tr = blended_transform_factory(fig.transFigure, ax.transAxes)
    fig.text(0.738, 1.0, "Δ [95% CI]", transform=tr, va="bottom", ha="left", fontsize=7, color=MUTED)
    return save(fig, "fig-rees46-verdict.png")


# --------------------------------------------------------------------------
# Рис. 2. Лестница OTTO
# --------------------------------------------------------------------------
def fig_otto_ladder() -> Path:
    F = FACTS
    steps = [
        dict(name="база B", private=F["otto_private_B"], dev=F["otto_dev_B"], evid="descriptive",
             who="оркестратор:\nручная база\nпо формулам\nконтракта"),
        dict(name="OTTO-1", private=F["otto_private_otto1"], dev=F["otto_dev_otto1"], evid="descriptive",
             who=f"агент ({F['otto_calls_otto1']} вызовов):\nкандидаты\nи признаки\nбез отбора"),
        dict(name="OTTO-2", private=F["otto_private_otto2"], dev=F["otto_dev_otto2"], evid="exploratory",
             who="оркестратор:\nобъём обучения\nранкера"),
        dict(name="OTTO-3 i1", private=F["otto_private_i1"], dev=F["otto_dev_i1"], evid="exploratory",
             who=f"агент ({F['otto_calls_i1']} вызовов):\nновые кандидаты\nи признаки\nв лимитах\nоркестратора"),
        dict(name="OTTO-3 i2", private=F["otto_private_i2"], dev=F["otto_dev_i2"], evid="exploratory",
             who=f"агент ({F['otto_calls_i2']} вызова):\n{F['otto_new_proposals_i2']} новых\nпредложений:\n"
                 "кандидаты\nи признаки"),
    ]
    if F["otto_private_i3"] is not None:
        steps.append(dict(name="OTTO-3 i3", private=F["otto_private_i3"], dev=F["otto_dev_i3"],
                          evid="exploratory",
                          who=f"агент ({F['otto_calls_i3']} вызова):\n{F['otto_new_proposals_i3']} новых\nпредложений:\n"
                              "только признаки"))
    n = len(steps)
    xs = list(range(n))
    ys = [num(s["private"]) for s in steps]

    # разрыв оси: сверху 0.570–0.600, снизу — окрестность базы; масштаб одинаковый
    top_lim = (0.570, 0.600)
    bot_lim = (0.486, 0.495)
    unit_in = 0.062  # дюйма на 0.001 Score
    h_top = (top_lim[1] - top_lim[0]) * 1000 * unit_in
    h_bot = (bot_lim[1] - bot_lim[0]) * 1000 * unit_in
    gap = 0.10
    top_m, bot_m = 0.40, 1.20
    H = top_m + h_top + gap + h_bot + bot_m
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1 = 0.10, 0.985
    ax_b = fig.add_axes([x0, bot_m / H, x1 - x0, h_bot / H])
    ax_t = fig.add_axes([x0, (bot_m + h_bot + gap) / H, x1 - x0, h_top / H], sharex=ax_b)
    ax_t.set_ylim(*top_lim)
    ax_b.set_ylim(*bot_lim)
    ax_b.set_xlim(-0.55, n - 0.45)

    first_expl = next(i for i, s in enumerate(steps) if s["evid"] == "exploratory")
    for ax in (ax_t, ax_b):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color=GRID, lw=0.5, zorder=0)
        ax.set_axisbelow(True)
        # исследовательская часть — светлая подложка
        ax.axvspan(first_expl - 0.5, n - 0.45, color=WASH, lw=0, zorder=0)
    ax_t.text(first_expl - 0.45, top_lim[1] - 0.0004, "исследовательский", fontsize=7.2, color=INK2,
              va="top", ha="left", style="italic")
    ax_t.spines["bottom"].set_visible(False)
    ax_t.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_t.set_yticks([0.570, 0.575, 0.580, 0.585, 0.590, 0.595, 0.600])
    ax_b.set_yticks([0.486, 0.488, 0.490, 0.492, 0.494])
    for ax in (ax_t, ax_b):
        ax.yaxis.set_major_formatter(lambda v, _p: f"{v:.3f}")

    # знак разрыва на левой оси
    d = 0.6
    kw = dict(marker=[(-1, -d), (1, d)], markersize=7, ls="none", color=AXIS, mec=AXIS, mew=0.8, clip_on=False)
    ax_t.plot([0], [0], transform=ax_t.transAxes, **kw)
    ax_b.plot([0], [1], transform=ax_b.transAxes, **kw)

    # пороги §10: короткие подписи слева, где нет точек
    thr = [
        (F["otto_thr_notebook"], "уровень публичного ноутбука"),
        (F["otto_thr_works"], "«пайплайн работает»"),
        (F["otto_thr_weighty"], "«весомо»"),
    ]
    for v, label in thr:
        ax_t.axhline(num(v), color=INK2, lw=0.7, ls=(0, (4, 3)), zorder=1)
        ax_t.text(-0.52, num(v) + 0.0004, f"{v} — {label}", fontsize=6.8, color=INK2, va="bottom", ha="left")

    # линия лестницы и точки
    for ax in (ax_t, ax_b):
        ax.plot(xs, ys, color=BLUE, lw=1.0, zorder=2, alpha=0.7)
        for x, s in zip(xs, steps):
            plot_point(ax, x, num(s["private"]), s["evid"], color=BLUE)
    for x, s in zip(xs, steps):
        y = num(s["private"])
        ax = ax_t if y >= top_lim[0] else ax_b
        if x == 1:  # OTTO-1 лежит между двумя порогами: подпись слева от точки
            ax.annotate(s["private"], (x, y), xytext=(-7, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=7.5, color=INK, fontweight="bold")
        else:
            ax.annotate(s["private"], (x, y), xytext=(0, 6), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.5, color=INK, fontweight="bold")

    # подписи под осью: шаг, кто и что изменил, dev F3
    ax_b.set_xticks(xs)
    ax_b.set_xticklabels([s["name"] for s in steps], fontsize=7.8, color=INK, fontweight="bold")
    ax_b.tick_params(axis="x", length=0, pad=4)
    for x, s in zip(xs, steps):
        ax_b.annotate(s["who"], (x, 0), xycoords=("data", "axes fraction"), xytext=(0, -17),
                      textcoords="offset points", ha="center", va="top", fontsize=6.8, color=INK2,
                      linespacing=1.15)
        ax_b.annotate(f"dev F3: {s['dev']}", (x, 0), xycoords=("data", "axes fraction"), xytext=(0, -64),
                      textcoords="offset points", ha="center", va="top", fontsize=6.8, color=INK2)
    fig.text(0.012, 0.012, "dev F3 — Score той же модели на dev-неделе; уровни недель не сравниваются, "
             "сравниваются приросты.", fontsize=6.8, color=MUTED, va="bottom", ha="left")

    fig.text(0.012, (bot_m + (h_bot + gap + h_top) / 2) / H, "Score, Kaggle private (неделя F5)",
             rotation=90, va="center", ha="left", fontsize=7.5, color=INK2)

    handles = [
        evid_handle("descriptive", "описательно", color=BLUE),
        evid_handle("exploratory", "исследовательский: шаги выбраны по dev F3, неделя Kaggle прочитана многократно"),
        Line2D([], [], color=INK2, lw=0.7, ls=(0, (4, 3)),
               label="пороги контракта §10: записаны до чисел, ориентиры по чужим отчётам не проверены"),
    ]
    fig.legend(handles=handles[:2], loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=2,
               handletextpad=0.4, columnspacing=1.4, borderaxespad=0.3)
    fig.legend(handles=handles[2:], loc="upper left", bbox_to_anchor=(0.005, 1.0 - 0.17 / H), ncol=1,
               handletextpad=0.4, borderaxespad=0.3, handlelength=2.2)
    return save(fig, "fig-otto-ladder.png")


# --------------------------------------------------------------------------
# Рис. 3. OTTO: приросты dev F3 и private по шагам
# --------------------------------------------------------------------------
def fig_otto_dev_vs_private() -> Path:
    F = FACTS
    OFF = 0.17  # dev чуть выше линии строки, private чуть ниже

    # панель A: B → OTTO-1 (масштаб другой)
    LA = RowLayout()
    LA.header("B → OTTO-1: агент добавил кандидаты и признаки (описательно)")
    LA.row("B → OTTO-1", dev=F["otto_d_B_otto1_dev"], private=F["otto_d_B_otto1_private"], evid="descriptive",
           value=f"{txt(F['otto_d_B_otto1_dev'][0])} / {txt(F['otto_d_B_otto1_private_short'])}")

    LB = RowLayout()
    LB.header("OTTO-2 и OTTO-3 (исследовательский)")
    LB.row("OTTO-1 → OTTO-2: обучение ранкера", dev=(F["otto_d_otto1_otto2"][0],),
           private=(F["otto_d_otto1_otto2"][1],), evid="exploratory")
    LB.row("    в т. ч. OTTO-1 → f4all-it1000", dev=(F["otto_d_otto1_it1000"][0],),
           private=(F["otto_d_otto1_it1000"][1],), evid="exploratory")
    LB.row("    в т. ч. → f4all-lr10-it2000", dev=(F["otto_d_it1000_lr10"][0],),
           private=(F["otto_d_it1000_lr10"][1],), evid="exploratory")
    LB.separator()
    LB.row("OTTO-2 → i1: новый набор агента", dev=F["otto_d_otto2_i1_dev"],
           private=(F["otto_d_otto2_i1_private"],), evid="exploratory")
    LB.row("i1 → i2: 18 новых предложений агента", dev=F["otto_d_i1_i2_dev"],
           private=(F["otto_d_i1_i2_private"],), evid="exploratory")
    LB.row("i2 → i3: 20 новых признаков агента", dev=F["otto_d_i2_i3_dev"],
           private=(F["otto_d_i2_i3_private"],), evid="exploratory")
    LB.row("OTTO-2 → i3: итог OTTO-3", dev=F["otto_d_otto2_i3_dev"],
           private=(F["otto_d_otto2_i3_private"],), evid="exploratory")
    for it in LB.items:
        if it["kind"] == "row":
            it["value"] = f"{txt(it['dev'][0])} / {txt(it['private'][0])}"

    unit = 0.20
    top_m, mid, bot_m = 0.36, 0.42, 0.40
    hA = (LA.span + 0.3) * unit
    hB = (LB.span + 0.3) * unit
    H = top_m + hA + mid + hB + bot_m
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1 = 0.33, 0.80
    axB = fig.add_axes([x0, bot_m / H, x1 - x0, hB / H])
    axA = fig.add_axes([x0, (bot_m + hB + mid) / H, x1 - x0, hA / H])
    axA.set_ylim(LA.y + 0.5, 0.7)
    axB.set_ylim(LB.y + 0.5, 0.7)
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
        draw_labels(fig, ax, layout.items, x_header=0.012, x_row=0.028, x_value=0.815, x_sep=(0.012, 0.99))
    axB.axvline(0, color=INK2, lw=0.8, zorder=1)
    axA.set_xlabel("прирост Score за шаг (ось не от нуля)")
    axB.set_xlabel("прирост Score за шаг, абс. ед.; усы — 95% CI парного бутстрапа на dev F3")

    tr = blended_transform_factory(fig.transFigure, axA.transAxes)
    fig.text(0.815, 1.0, "dev / private", transform=tr, va="bottom", ha="left", fontsize=7, color=MUTED)

    handles = [
        evid_handle("descriptive", "dev F3, описательно", filled=False, color=ORANGE),
        evid_handle("descriptive", "private, описательно", filled=True, color=BLUE),
        evid_handle("exploratory", "dev F3, исследовательский", filled=False, color=ORANGE),
        evid_handle("exploratory", "private, исследовательский", filled=True, color=BLUE),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=4,
               handletextpad=0.3, columnspacing=1.2, borderaxespad=0.3)
    return save(fig, "fig-otto-dev-vs-private.png")


# --------------------------------------------------------------------------
# Рис. 4. Перенос: BA − B по наборам
# --------------------------------------------------------------------------
def fig_transfer() -> Path:
    F = FACTS
    panels = []

    L = RowLayout()
    L.header("REES46 — исходный набор, NDCG@20")
    L.row("тест 2020, первое зерно: база + агент + DFS", ci=F["hplus_t2020_s1"], evid="protocol")
    L.row("тест 2020, второе зерно: база + агент + DFS", ci=F["hplus_t2020_s2"], evid="protocol")
    L.row("val 2020, база + колонки агента, два зерна", pts=F["hag_val2020"], evid="descriptive",
          value=f"{txt(F['hag_val2020'][0])}, {txt(F['hag_val2020'][1])} (без CI)")
    panels.append(dict(layout=L, xlim=(-0.0012, 0.0042), ticks=[-0.001, 0, 0.001, 0.002, 0.003, 0.004],
                       xlabel="Δ NDCG@20 к ручной базе, абс. ед.", band=num(F["rees_noise"])))

    L = RowLayout()
    L.header("Tinkoff, NDCG@20")
    L.row("holdout 671, зерно 2026", ci=F["tinkoff_holdout_s2026"], evid="holdout")
    L.row("holdout 671, зерно 2027", ci=F["tinkoff_holdout_s2027"], evid="holdout")
    L.row("Kaggle private, разность средних зёрен", pts=(F["tinkoff_kaggle_mean_diff"],), evid="descriptive",
          value=f"{txt(F['tinkoff_kaggle_mean_diff'])}, «{F['tinkoff_kaggle_verdict']}»")
    panels.append(dict(layout=L, xlim=(-0.0030, 0.0035), ticks=[-0.002, -0.001, 0, 0.001, 0.002, 0.003],
                       xlabel="Δ NDCG@20, абс. ед."))

    L = RowLayout()
    L.header("СберМаркет, MAP@50")
    L.row("holdout 09-02, зерно 2026", ci=F["sber_holdout_s2026"], evid="holdout")
    L.row("holdout 09-02, зерно 2027", ci=F["sber_holdout_s2027"], evid="holdout")
    L.row("Kaggle private", evid=None, note=F["sber_kaggle_status"])
    panels.append(dict(layout=L, xlim=(-0.0005, 0.0035), ticks=[0, 0.001, 0.002, 0.003],
                       xlabel="Δ MAP@50, абс. ед."))

    L = RowLayout()
    L.header("H&M, MAP@12 (локально — условный)")
    L.row("неделя 09-16, зерно 2026 (holdout нет)", ci=F["hm_week_s2026"], evid="descriptive")
    L.row("неделя 09-16, зерно 2027 (holdout нет)", ci=F["hm_week_s2027"], evid="descriptive")
    L.row("Kaggle private, разность средних зёрен", pts=(F["hm_kaggle_mean_diff"],), evid="descriptive",
          value=f"{txt(F['hm_kaggle_mean_diff'])}, «{F['hm_kaggle_verdict']}»")
    panels.append(dict(layout=L, xlim=(-0.0012, 0.0072), ticks=[0, 0.002, 0.004, 0.006],
                       xlabel="Δ MAP@12, абс. ед."))

    for p in panels:
        for it in p["layout"].items:
            if it["kind"] == "row" and "ci" in it:
                it["value"] = ci_text(it["ci"])

    unit = 0.160
    top_m, gap, bot_m = 0.66, 0.40, 0.36
    hs = [(p["layout"].span + 0.15) * unit for p in panels]
    H = top_m + sum(hs) + gap * (len(panels) - 1) + bot_m
    fig = plt.figure(figsize=(WIDTH_IN, H))
    x0, x1 = 0.36, 0.715
    y = H - top_m
    for p, h in zip(panels, hs):
        y -= h
        ax = fig.add_axes([x0, y / H, x1 - x0, h / H])
        y -= gap
        L = p["layout"]
        ax.set_ylim(L.y + 0.4, 0.75)
        ax.set_xlim(*p["xlim"])
        ax.set_xticks(p["ticks"])
        ax.xaxis.set_major_formatter(lambda v, pos: signed_tick(v, pos, nd=3))
        clean_axes(ax)
        ax.grid(axis="x", color=GRID, lw=0.5, zorder=0)
        ax.set_axisbelow(True)
        if p.get("band"):
            ax.axvspan(-p["band"], p["band"], color=BAND, lw=0, zorder=0)
        ax.axvline(0, color=INK2, lw=0.8, zorder=1)
        ax.set_xlabel(p["xlabel"], labelpad=1.5)
        for it in L.items:
            if it["kind"] == "row" and it.get("note"):
                ax.text(0.0001, it["y"], it["note"], fontsize=7, color=INK2, style="italic", va="center",
                        ha="left", bbox=dict(facecolor="white", edgecolor="none", pad=1.0), zorder=5)
            if it["kind"] != "row" or it.get("evid") is None:
                continue
            if "ci" in it:
                est, lo, hi = (num(v) for v in it["ci"])
                plot_ci(ax, est, lo, hi, it["y"], it["evid"])
            else:
                for v in it["pts"]:
                    plot_point(ax, num(v), it["y"], it["evid"])
        draw_labels(fig, ax, L.items, x_header=0.012, x_row=0.028, x_value=0.732)

    handles = [
        evid_handle("protocol"),
        evid_handle("holdout"),
        evid_handle("descriptive"),
        Patch(facecolor=BAND, edgecolor="none", label=f"|Δ| < {F['rees_noise']} (порог REES46)"),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 1.0), ncol=4,
               handletextpad=0.4, columnspacing=1.4, borderaxespad=0.3)
    fig.text(0.012, 1 - 0.27 / H, "Δ — «база набора + колонки агента» минус «база набора» (REES46 — минус ручная база), "
             "в единицах метрики набора.\nУ каждого набора своя шкала; среднего по наборам нет.",
             fontsize=6.8, color=INK2, va="top", ha="left", linespacing=1.3)
    return save(fig, "fig-transfer.png")


def main() -> None:
    for build in (fig_rees46_verdict, fig_otto_ladder, fig_otto_dev_vs_private, fig_transfer):
        path = build()
        print(path.relative_to(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    main()
