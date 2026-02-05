"""
Chart Generator für Telegram Reports
Erstellt visuelle Portfolio-Analysen
"""

import io
from datetime import datetime

# Matplotlib mit nicht-interaktivem Backend (für Server)
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge

# Style konfigurieren
plt.style.use("dark_background")
COLORS = {
    "green": "#00ff88",
    "red": "#ff4444",
    "blue": "#4488ff",
    "yellow": "#ffcc00",
    "purple": "#aa44ff",
    "cyan": "#00ccff",
    "orange": "#ff8844",
    "pink": "#ff44aa",
    "gray": "#888888",
    "white": "#ffffff",
    "bg": "#1a1a2e",
    "grid": "#333355",
}


def create_portfolio_chart(
    portfolio_history: pd.DataFrame,
    benchmark_data: pd.DataFrame = None,
    title: str = "Portfolio Performance",
) -> bytes:
    """
    Erstellt einen Portfolio-Performance-Chart.

    Args:
        portfolio_history: DataFrame mit 'total_value' Spalte
        benchmark_data: Optional, DataFrame mit Benchmark (z.B. BTC)
        title: Chart-Titel

    Returns:
        PNG als Bytes
    """
    _fig, ax = plt.subplots(figsize=(10, 6), facecolor=COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])

    # Portfolio-Linie
    ax.plot(
        portfolio_history.index,
        portfolio_history["total_value"],
        color=COLORS["green"],
        linewidth=2,
        label="Portfolio",
    )

    # Benchmark wenn vorhanden
    if benchmark_data is not None:
        # Normalisiere Benchmark auf gleichen Startwert
        start_value = portfolio_history["total_value"].iloc[0]
        benchmark_normalized = benchmark_data / benchmark_data.iloc[0] * start_value
        ax.plot(
            benchmark_normalized.index,
            benchmark_normalized,
            color=COLORS["gray"],
            linewidth=1,
            linestyle="--",
            label="BTC Benchmark",
            alpha=0.7,
        )

    # Styling
    ax.set_title(title, fontsize=14, color=COLORS["white"], pad=15)
    ax.set_xlabel("Datum", color=COLORS["gray"])
    ax.set_ylabel("Wert ($)", color=COLORS["gray"])

    ax.tick_params(colors=COLORS["gray"])
    ax.grid(True, alpha=0.3, color=COLORS["grid"])
    ax.legend(loc="upper left", facecolor=COLORS["bg"], edgecolor=COLORS["grid"])

    # Datum-Formatierung
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45)

    # Return Annotation
    start_val = portfolio_history["total_value"].iloc[0]
    end_val = portfolio_history["total_value"].iloc[-1]
    total_return = (end_val - start_val) / start_val * 100

    return_color = COLORS["green"] if total_return >= 0 else COLORS["red"]
    ax.annotate(
        f"{total_return:+.1f}%",
        xy=(0.98, 0.95),
        xycoords="axes fraction",
        fontsize=16,
        color=return_color,
        ha="right",
        va="top",
        weight="bold",
    )

    plt.tight_layout()

    # Als Bytes zurückgeben
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=COLORS["bg"])
    buf.seek(0)
    plt.close()

    return buf.getvalue()


def create_allocation_pie(
    allocations: dict[str, float], title: str = "Portfolio Allocation"
) -> bytes:
    """
    Erstellt ein Pie-Chart der Asset-Allokation.

    Args:
        allocations: Dict mit {symbol: prozent}
        title: Chart-Titel

    Returns:
        PNG als Bytes
    """
    _fig, ax = plt.subplots(figsize=(8, 8), facecolor=COLORS["bg"])

    # Farben für Coins
    coin_colors = {
        "BTC": "#f7931a",
        "ETH": "#627eea",
        "SOL": "#00ffa3",
        "AVAX": "#e84142",
        "LINK": "#2a5ada",
        "DOT": "#e6007a",
        "MATIC": "#8247e5",
        "ARB": "#28a0f0",
        "OP": "#ff0420",
        "INJ": "#17ead9",
        "USDT": "#26a17b",
        "CASH": "#888888",
    }

    labels = list(allocations.keys())
    sizes = list(allocations.values())
    colors = [coin_colors.get(label, COLORS["purple"]) for label in labels]

    # Explode die größte Position leicht
    max_idx = sizes.index(max(sizes))
    explode = [0.05 if i == max_idx else 0 for i in range(len(sizes))]

    _wedges, _texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        explode=explode,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.75,
        textprops={"color": COLORS["white"], "fontsize": 10},
    )

    # Prozent-Text Styling
    for autotext in autotexts:
        autotext.set_color(COLORS["white"])
        autotext.set_fontsize(9)
        autotext.set_weight("bold")

    ax.set_title(title, fontsize=14, color=COLORS["white"], pad=15)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=COLORS["bg"])
    buf.seek(0)
    plt.close()

    return buf.getvalue()


def create_trade_chart(price_data: pd.Series, trades: list[dict], symbol: str) -> bytes:
    """
    Erstellt einen Preis-Chart mit Trade-Markierungen.

    Args:
        price_data: Preisdaten als Series
        trades: Liste von Trades mit 'timestamp', 'type', 'price'
        symbol: Asset-Symbol

    Returns:
        PNG als Bytes
    """
    _fig, ax = plt.subplots(figsize=(10, 6), facecolor=COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])

    # Preis-Linie
    ax.plot(price_data.index, price_data.values, color=COLORS["blue"], linewidth=1.5)

    # Trade-Marker
    for trade in trades:
        if trade.get("symbol") == symbol:
            color = COLORS["green"] if trade["type"] == "BUY" else COLORS["red"]
            marker = "^" if trade["type"] == "BUY" else "v"
            ax.scatter(
                trade["timestamp"], trade["price"], color=color, marker=marker, s=100, zorder=5
            )

    # Styling
    ax.set_title(f"{symbol} Price & Trades", fontsize=14, color=COLORS["white"])
    ax.set_xlabel("Datum", color=COLORS["gray"])
    ax.set_ylabel("Preis ($)", color=COLORS["gray"])
    ax.tick_params(colors=COLORS["gray"])
    ax.grid(True, alpha=0.3, color=COLORS["grid"])

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    plt.xticks(rotation=45)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=COLORS["bg"])
    buf.seek(0)
    plt.close()

    return buf.getvalue()


def create_fear_greed_gauge(value: int) -> bytes:
    """
    Erstellt ein Fear & Greed Gauge-Chart.

    Args:
        value: Fear & Greed Index (0-100)

    Returns:
        PNG als Bytes
    """
    _fig, ax = plt.subplots(figsize=(6, 4), facecolor=COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])

    # Gauge-Hintergrund (Halbkreis)
    colors_gradient = ["#ff4444", "#ff8844", "#ffcc00", "#88cc44", "#00cc44"]
    for i, color in enumerate(colors_gradient):
        start_angle = 180 - (i * 36)
        end_angle = 180 - ((i + 1) * 36)
        wedge = Wedge(
            (0.5, 0),
            0.4,
            end_angle,
            start_angle,
            facecolor=color,
            transform=ax.transAxes,
            alpha=0.8,
        )
        ax.add_patch(wedge)

    # Nadel
    angle = 180 - (value * 1.8)  # 0-100 auf 180-0 Grad
    angle_rad = np.radians(angle)
    needle_length = 0.35

    ax.annotate(
        "",
        xy=(0.5 + needle_length * np.cos(angle_rad), needle_length * np.sin(angle_rad)),
        xytext=(0.5, 0),
        arrowprops=dict(arrowstyle="->", color=COLORS["white"], lw=3),
        transform=ax.transAxes,
    )

    # Wert-Anzeige
    if value < 25:
        label = "EXTREME FEAR"
        color = "#ff4444"
    elif value < 45:
        label = "FEAR"
        color = "#ff8844"
    elif value < 55:
        label = "NEUTRAL"
        color = "#ffcc00"
    elif value < 75:
        label = "GREED"
        color = "#88cc44"
    else:
        label = "EXTREME GREED"
        color = "#00cc44"

    ax.text(
        0.5,
        -0.15,
        str(value),
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=32,
        color=color,
        weight="bold",
    )
    ax.text(
        0.5,
        -0.3,
        label,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=12,
        color=COLORS["gray"],
    )

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")

    ax.set_title("Fear & Greed Index", fontsize=14, color=COLORS["white"], pad=10)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=COLORS["bg"])
    buf.seek(0)
    plt.close()

    return buf.getvalue()


def create_daily_summary_image(
    portfolio_value: float,
    daily_pnl: float,
    daily_pnl_pct: float,
    allocations: dict[str, float],
    fear_greed: int,
    portfolio_history: pd.DataFrame = None,
) -> bytes:
    """
    Erstellt ein kombiniertes Tages-Summary Bild.

    Returns:
        PNG als Bytes
    """
    fig = plt.figure(figsize=(12, 8), facecolor=COLORS["bg"])

    # Layout: 2x2 Grid
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

    # 1. Portfolio Value (oben links)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(COLORS["bg"])
    ax1.axis("off")

    pnl_color = COLORS["green"] if daily_pnl >= 0 else COLORS["red"]
    ax1.text(
        0.5,
        0.7,
        f"${portfolio_value:,.2f}",
        transform=ax1.transAxes,
        ha="center",
        fontsize=28,
        color=COLORS["white"],
        weight="bold",
    )
    ax1.text(
        0.5,
        0.4,
        f"{daily_pnl:+,.2f} ({daily_pnl_pct:+.2f}%)",
        transform=ax1.transAxes,
        ha="center",
        fontsize=16,
        color=pnl_color,
    )
    ax1.text(
        0.5,
        0.15,
        "Portfolio Value",
        transform=ax1.transAxes,
        ha="center",
        fontsize=12,
        color=COLORS["gray"],
    )

    # 2. Allocation Pie (oben rechts)
    ax2 = fig.add_subplot(gs[0, 1])
    coin_colors = {
        "BTC": "#f7931a",
        "ETH": "#627eea",
        "SOL": "#00ffa3",
        "AVAX": "#e84142",
        "LINK": "#2a5ada",
        "CASH": "#888888",
    }
    colors = [coin_colors.get(k, COLORS["purple"]) for k in allocations]
    ax2.pie(
        allocations.values(),
        labels=allocations.keys(),
        colors=colors,
        autopct="%1.0f%%",
        textprops={"color": COLORS["white"], "fontsize": 9},
    )
    ax2.set_title("Allocation", color=COLORS["white"], fontsize=12)

    # 3. Performance Chart (unten links) - wenn Historie vorhanden
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor(COLORS["bg"])
    if portfolio_history is not None and len(portfolio_history) > 0:
        ax3.plot(
            portfolio_history.index,
            portfolio_history["total_value"],
            color=COLORS["green"],
            linewidth=1.5,
        )
        ax3.fill_between(
            portfolio_history.index,
            portfolio_history["total_value"],
            alpha=0.3,
            color=COLORS["green"],
        )
    ax3.set_title("Performance", color=COLORS["white"], fontsize=12)
    ax3.tick_params(colors=COLORS["gray"])
    ax3.grid(True, alpha=0.2, color=COLORS["grid"])

    # 4. Fear & Greed (unten rechts)
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(COLORS["bg"])
    ax4.axis("off")

    if fear_greed < 25:
        fg_color, fg_label = "#ff4444", "EXTREME FEAR"
    elif fear_greed < 45:
        fg_color, fg_label = "#ff8844", "FEAR"
    elif fear_greed < 55:
        fg_color, fg_label = "#ffcc00", "NEUTRAL"
    elif fear_greed < 75:
        fg_color, fg_label = "#88cc44", "GREED"
    else:
        fg_color, fg_label = "#00cc44", "EXTREME GREED"

    ax4.text(
        0.5,
        0.6,
        str(fear_greed),
        transform=ax4.transAxes,
        ha="center",
        fontsize=48,
        color=fg_color,
        weight="bold",
    )
    ax4.text(
        0.5, 0.3, fg_label, transform=ax4.transAxes, ha="center", fontsize=14, color=COLORS["gray"]
    )
    ax4.text(
        0.5,
        0.1,
        "Fear & Greed",
        transform=ax4.transAxes,
        ha="center",
        fontsize=10,
        color=COLORS["gray"],
    )

    # Timestamp
    fig.text(
        0.99,
        0.01,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        ha="right",
        fontsize=8,
        color=COLORS["gray"],
    )

    buf = io.BytesIO()
    plt.savefig(
        buf, format="png", dpi=150, facecolor=COLORS["bg"], bbox_inches="tight", pad_inches=0.2
    )
    buf.seek(0)
    plt.close()

    return buf.getvalue()
