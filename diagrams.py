"""Generate installation and wiring diagrams for solar pumping stations."""

import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle
import numpy as np

from calculations import PanelSpecs, InverterSpecs, MotorSpecs, PVConfig, SizingResult

# Color palette
C_PANEL = '#2196F3'
C_PANEL_LIGHT = '#BBDEFB'
C_INVERTER = '#FF9800'
C_INVERTER_LIGHT = '#FFE0B2'
C_MOTOR = '#4CAF50'
C_MOTOR_LIGHT = '#C8E6C9'
C_CABLE_DC = '#F44336'
C_CABLE_AC = '#2196F3'
C_CABLE_GND = '#4CAF50'
C_FUSE = '#9C27B0'
C_BG = '#FAFAFA'
C_TEXT = '#212121'
C_WATER = '#03A9F4'


def generate_installation_diagram(
    panel: PanelSpecs,
    inverter: InverterSpecs,
    motor: MotorSpecs,
    config: PVConfig,
    result: SizingResult,
    station_name: str = "Station",
) -> io.BytesIO:
    """Generate a physical installation layout diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 65)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)

    # Title
    ax.text(50, 63, f"SCHEMA D'INSTALLATION - {station_name}",
            ha='center', va='top', fontsize=16, fontweight='bold', color='#003366')
    ax.text(50, 60.5, f"{config.total_panels} panneaux {panel.model} ({panel.pmax_w:.0f} Wc) | "
            f"Variateur {inverter.model} ({inverter.power_kw:.0f} kW) | "
            f"Moteur {motor.power_kw:.1f} kW",
            ha='center', va='top', fontsize=9, color='#666666')

    # --- Draw PV Array ---
    array_x, array_y = 5, 25
    panel_w = 4.0
    panel_h = 2.2
    gap_x = 0.3
    gap_y = 0.8

    # Background for array
    array_total_w = config.panels_per_string * (panel_w + gap_x) - gap_x + 2
    array_total_h = config.num_strings * (panel_h + gap_y) - gap_y + 2
    ax.add_patch(FancyBboxPatch(
        (array_x - 1, array_y - 1), array_total_w, array_total_h,
        boxstyle="round,pad=0.5", facecolor='#E3F2FD', edgecolor='#1565C0',
        linewidth=1.5, linestyle='--', alpha=0.5
    ))
    ax.text(array_x + array_total_w / 2 - 1, array_y + array_total_h + 0.5,
            f"Champ Photovoltaique - {result.total_power_w/1000:.2f} kWc",
            ha='center', fontsize=11, fontweight='bold', color='#1565C0')

    # Limit display: if too many panels, show simplified
    max_display_cols = min(config.panels_per_string, 10)
    show_ellipsis_col = config.panels_per_string > 10
    max_display_rows = min(config.num_strings, 6)
    show_ellipsis_row = config.num_strings > 6

    for row in range(max_display_rows):
        string_label = f"String {row + 1}"
        y = array_y + row * (panel_h + gap_y)
        ax.text(array_x - 0.5, y + panel_h / 2, string_label,
                ha='right', va='center', fontsize=7, color='#1565C0', fontstyle='italic')

        cols_to_draw = max_display_cols
        if show_ellipsis_col:
            cols_to_draw = 8  # draw 8, then ellipsis, then last

        for col in range(cols_to_draw):
            x = array_x + col * (panel_w + gap_x)
            # Panel rectangle
            rect = FancyBboxPatch(
                (x, y), panel_w, panel_h,
                boxstyle="round,pad=0.1",
                facecolor=C_PANEL_LIGHT, edgecolor=C_PANEL, linewidth=0.8
            )
            ax.add_patch(rect)
            # Grid lines inside panel
            for gx in np.linspace(x + 0.3, x + panel_w - 0.3, 4):
                ax.plot([gx, gx], [y + 0.2, y + panel_h - 0.2],
                        color=C_PANEL, linewidth=0.3, alpha=0.5)
            for gy in np.linspace(y + 0.3, y + panel_h - 0.3, 3):
                ax.plot([x + 0.2, x + panel_w - 0.2], [gy, gy],
                        color=C_PANEL, linewidth=0.3, alpha=0.5)

        if show_ellipsis_col:
            ex = array_x + cols_to_draw * (panel_w + gap_x)
            ax.text(ex + 1, y + panel_h / 2, "...", ha='center', va='center',
                    fontsize=14, fontweight='bold', color=C_PANEL)
            # Last panel
            lx = ex + 3
            rect = FancyBboxPatch(
                (lx, y), panel_w, panel_h,
                boxstyle="round,pad=0.1",
                facecolor=C_PANEL_LIGHT, edgecolor=C_PANEL, linewidth=0.8
            )
            ax.add_patch(rect)

    if show_ellipsis_row:
        ey = array_y + max_display_rows * (panel_h + gap_y)
        ax.text(array_x + array_total_w / 2 - 1, ey, "...",
                ha='center', va='center', fontsize=16, fontweight='bold', color=C_PANEL)

    # --- Connection lines from array to combiner box ---
    combiner_x = array_x + array_total_w + 3
    combiner_y = array_y + array_total_h / 2 - 3
    combiner_w = 5
    combiner_h = 6

    # Combiner box
    ax.add_patch(FancyBboxPatch(
        (combiner_x, combiner_y), combiner_w, combiner_h,
        boxstyle="round,pad=0.3", facecolor='#FFF3E0', edgecolor=C_INVERTER, linewidth=2
    ))
    ax.text(combiner_x + combiner_w / 2, combiner_y + combiner_h - 0.5,
            "Boite de", ha='center', va='top', fontsize=8, fontweight='bold', color='#E65100')
    ax.text(combiner_x + combiner_w / 2, combiner_y + combiner_h - 1.3,
            "Jonction", ha='center', va='top', fontsize=8, fontweight='bold', color='#E65100')
    if config.num_strings > 1:
        ax.text(combiner_x + combiner_w / 2, combiner_y + combiner_h / 2 - 0.5,
                f"{config.num_strings} fusibles", ha='center', va='center',
                fontsize=7, color='#BF360C')
        ax.text(combiner_x + combiner_w / 2, combiner_y + combiner_h / 2 - 1.3,
                f"DC string", ha='center', va='center', fontsize=7, color='#BF360C')

    # Lines from strings to combiner
    for row in range(min(config.num_strings, max_display_rows)):
        y_line = array_y + row * (panel_h + gap_y) + panel_h / 2
        x_end = array_x + array_total_w - 1
        y_comb = combiner_y + (row + 0.5) / max(config.num_strings, max_display_rows) * combiner_h
        ax.annotate('', xy=(combiner_x, y_comb),
                    xytext=(x_end, y_line),
                    arrowprops=dict(arrowstyle='->', color=C_CABLE_DC, lw=1.5))

    # --- Inverter ---
    inv_x = combiner_x + combiner_w + 5
    inv_y = combiner_y - 1
    inv_w = 8
    inv_h = 8

    ax.add_patch(FancyBboxPatch(
        (inv_x, inv_y), inv_w, inv_h,
        boxstyle="round,pad=0.3", facecolor=C_INVERTER_LIGHT, edgecolor=C_INVERTER, linewidth=2.5
    ))
    ax.text(inv_x + inv_w / 2, inv_y + inv_h - 1, "VARIATEUR",
            ha='center', va='top', fontsize=11, fontweight='bold', color='#E65100')
    ax.text(inv_x + inv_w / 2, inv_y + inv_h - 2.2, f"INVT {inverter.model}",
            ha='center', va='top', fontsize=8, color='#BF360C')
    ax.text(inv_x + inv_w / 2, inv_y + inv_h - 3.2, f"{inverter.power_kw:.0f} kW",
            ha='center', va='top', fontsize=10, fontweight='bold', color='#E65100')

    # DC input label
    ax.text(inv_x + 0.5, inv_y + inv_h / 2, "DC\nIN",
            ha='center', va='center', fontsize=8, fontweight='bold', color=C_CABLE_DC)
    # AC output label
    ax.text(inv_x + inv_w - 0.8, inv_y + inv_h / 2, "AC\nOUT",
            ha='center', va='center', fontsize=8, fontweight='bold', color=C_CABLE_AC)

    # Line from combiner to inverter (DC)
    ax.annotate('', xy=(inv_x, inv_y + inv_h / 2),
                xytext=(combiner_x + combiner_w, combiner_y + combiner_h / 2),
                arrowprops=dict(arrowstyle='->', color=C_CABLE_DC, lw=2.5))
    mid_dc_x = (combiner_x + combiner_w + inv_x) / 2
    ax.text(mid_dc_x, combiner_y + combiner_h / 2 + 1, "DC (+/-)",
            ha='center', fontsize=8, fontweight='bold', color=C_CABLE_DC)
    ax.text(mid_dc_x, combiner_y + combiner_h / 2 - 0.8,
            f"{result.vmp_stc:.0f} V / {result.imp_stc:.1f} A",
            ha='center', fontsize=7, color=C_CABLE_DC)

    # --- Motor + Pump ---
    mot_x = inv_x + inv_w + 5
    mot_y = inv_y + 1
    mot_r = 3

    # Motor circle
    circle = plt.Circle((mot_x + mot_r, mot_y + mot_r), mot_r,
                         facecolor=C_MOTOR_LIGHT, edgecolor=C_MOTOR, linewidth=2.5)
    ax.add_patch(circle)
    ax.text(mot_x + mot_r, mot_y + mot_r + 0.5, "M",
            ha='center', va='center', fontsize=20, fontweight='bold', color='#2E7D32')
    ax.text(mot_x + mot_r, mot_y + mot_r - 1, f"{motor.power_kw:.1f} kW",
            ha='center', va='center', fontsize=9, fontweight='bold', color='#2E7D32')
    ax.text(mot_x + mot_r, mot_y - 1, "Moteur / Pompe",
            ha='center', fontsize=9, fontweight='bold', color='#2E7D32')

    # Line from inverter to motor (AC)
    ax.annotate('', xy=(mot_x, mot_y + mot_r),
                xytext=(inv_x + inv_w, inv_y + inv_h / 2),
                arrowprops=dict(arrowstyle='->', color=C_CABLE_AC, lw=2.5))
    mid_ac_x = (inv_x + inv_w + mot_x) / 2
    ax.text(mid_ac_x, inv_y + inv_h / 2 + 1.2, "AC 3~",
            ha='center', fontsize=8, fontweight='bold', color=C_CABLE_AC)
    ax.text(mid_ac_x, inv_y + inv_h / 2 - 0.5,
            f"{motor.voltage_v:.0f} V / {motor.current_a:.0f} A",
            ha='center', fontsize=7, color=C_CABLE_AC)

    # --- Water indication ---
    water_x = mot_x + mot_r
    water_y = mot_y - 3
    ax.annotate('', xy=(water_x, water_y),
                xytext=(water_x, mot_y - 0.5),
                arrowprops=dict(arrowstyle='->', color=C_WATER, lw=2, linestyle='--'))
    ax.text(water_x, water_y - 0.5, "Eau", ha='center', fontsize=9,
            fontweight='bold', color=C_WATER)

    # --- Legend box ---
    legend_y = 3
    legend_items = [
        (C_CABLE_DC, "Cable DC (PV -> Variateur)"),
        (C_CABLE_AC, "Cable AC (Variateur -> Moteur)"),
        (C_WATER, "Conduite d'eau"),
    ]
    for i, (color, text) in enumerate(legend_items):
        lx = 5 + i * 30
        ax.plot([lx, lx + 3], [legend_y, legend_y], color=color, linewidth=2.5)
        ax.text(lx + 3.5, legend_y, text, va='center', fontsize=8, color=C_TEXT)

    # --- Info box ---
    info_lines = [
        f"Puissance crete: {result.total_power_w/1000:.2f} kWc",
        f"Voc STC: {result.voc_stc:.1f} V | Vmp STC: {result.vmp_stc:.1f} V",
        f"Isc: {result.isc_stc:.2f} A | Imp: {result.imp_stc:.2f} A",
        f"Config: {config.num_strings}S x {config.panels_per_string}P",
    ]
    for i, line in enumerate(info_lines):
        ax.text(5, 17 - i * 1.5, line, fontsize=8, color='#37474F',
                fontfamily='monospace')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=C_BG)
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_wiring_diagram(
    panel: PanelSpecs,
    inverter: InverterSpecs,
    motor: MotorSpecs,
    config: PVConfig,
    result: SizingResult,
    station_name: str = "Station",
) -> io.BytesIO:
    """Generate an electrical single-line wiring diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(18, 12))
    ax.set_xlim(0, 180)
    ax.set_ylim(0, 120)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.patch.set_facecolor('white')

    # Title
    ax.text(90, 117, f"SCHEMA DE CABLAGE UNIFILAIRE - {station_name}",
            ha='center', va='top', fontsize=14, fontweight='bold', color='#003366')
    ax.text(90, 113, f"Configuration: {config.num_strings} string(s) x "
            f"{config.panels_per_string} panneaux en serie",
            ha='center', va='top', fontsize=9, color='#666666')

    n_strings = config.num_strings
    n_panels = config.panels_per_string

    # Layout constants
    string_start_x = 10
    string_spacing_y = min(18, 80 / max(n_strings, 1))
    string_base_y = 105 - (n_strings * string_spacing_y) / 2
    bus_x = 85
    fuse_x = 95
    spd_x = 105
    inverter_x = 120
    motor_x = 155

    # --- Draw each string ---
    display_strings = min(n_strings, 5)
    show_ellipsis = n_strings > 5

    for s in range(display_strings):
        y = string_base_y + s * string_spacing_y
        # String label
        ax.text(string_start_x - 2, y, f"String {s+1}",
                ha='right', va='center', fontsize=8, fontweight='bold', color='#1565C0')

        # Draw panels in string (simplified: show first 3, ellipsis, last)
        panels_to_show = min(n_panels, 4)
        panel_w = 6
        panel_gap = 1.5

        for p in range(panels_to_show):
            px = string_start_x + p * (panel_w + panel_gap)
            # Panel symbol
            ax.add_patch(Rectangle((px, y - 2), panel_w, 4,
                                   facecolor=C_PANEL_LIGHT, edgecolor=C_PANEL, linewidth=1))
            # PV symbol inside
            ax.text(px + panel_w / 2, y + 0.5, "PV", ha='center', va='center',
                    fontsize=7, fontweight='bold', color=C_PANEL)
            ax.text(px + panel_w / 2, y - 0.8, f"{panel.pmax_w:.0f}W",
                    ha='center', va='center', fontsize=6, color='#1565C0')
            # + and - terminals
            ax.text(px + 0.3, y + 1.3, "+", fontsize=6, color=C_CABLE_DC, fontweight='bold')
            ax.text(px + panel_w - 0.8, y + 1.3, "-", fontsize=6, color='#333', fontweight='bold')

            # Connection line between panels
            if p > 0:
                prev_x = string_start_x + (p - 1) * (panel_w + panel_gap) + panel_w
                ax.plot([prev_x, px], [y, y], color=C_CABLE_DC, linewidth=1.5)

        if n_panels > 4:
            # Ellipsis
            ex = string_start_x + panels_to_show * (panel_w + panel_gap)
            ax.text(ex, y, f"...({n_panels - panels_to_show} de plus)...",
                    ha='left', va='center', fontsize=7, color='#999')

        # Line from string to DC bus
        last_panel_x = string_start_x + min(panels_to_show, n_panels) * (panel_w + panel_gap)
        if n_panels > 4:
            last_panel_x += 12

        # String fuse (if multiple strings)
        if n_strings > 1:
            fuse_str_x = last_panel_x + 2
            # Fuse symbol
            ax.add_patch(Rectangle((fuse_str_x, y - 0.8), 3, 1.6,
                                   facecolor='white', edgecolor=C_FUSE, linewidth=1.5))
            ax.text(fuse_str_x + 1.5, y, "F", ha='center', va='center',
                    fontsize=7, fontweight='bold', color=C_FUSE)
            ax.plot([last_panel_x, fuse_str_x], [y, y], color=C_CABLE_DC, linewidth=1.5)
            ax.plot([fuse_str_x + 3, bus_x], [y, y], color=C_CABLE_DC, linewidth=1.5)
        else:
            ax.plot([last_panel_x, bus_x], [y, y], color=C_CABLE_DC, linewidth=1.5)

    if show_ellipsis:
        ey = string_base_y + display_strings * string_spacing_y
        ax.text(40, ey - 5, f"... ({n_strings - display_strings} strings supplementaires) ...",
                ha='center', va='center', fontsize=9, fontstyle='italic', color='#999')

    # --- DC Bus bars ---
    bus_y_top = string_base_y + (display_strings - 1) * string_spacing_y + 3
    bus_y_bot = string_base_y - 3
    bus_mid_y = (bus_y_top + bus_y_bot) / 2

    # Positive bus
    ax.plot([bus_x, bus_x], [bus_y_bot, bus_y_top],
            color=C_CABLE_DC, linewidth=3)
    ax.text(bus_x, bus_y_top + 1.5, "DC+", ha='center', fontsize=9,
            fontweight='bold', color=C_CABLE_DC)

    # Negative bus (offset)
    ax.plot([bus_x + 2, bus_x + 2], [bus_y_bot, bus_y_top],
            color='#333', linewidth=3)
    ax.text(bus_x + 2, bus_y_top + 1.5, "DC-", ha='center', fontsize=9,
            fontweight='bold', color='#333')

    # --- SPD (Surge Protection) ---
    spd_y = bus_mid_y
    ax.add_patch(FancyBboxPatch(
        (spd_x, spd_y - 3), 6, 6,
        boxstyle="round,pad=0.3", facecolor='#FFF9C4', edgecolor='#F57F17', linewidth=1.5
    ))
    ax.text(spd_x + 3, spd_y + 1.2, "SPD", ha='center', va='center',
            fontsize=9, fontweight='bold', color='#F57F17')
    ax.text(spd_x + 3, spd_y - 0.5, "Type II", ha='center', va='center',
            fontsize=7, color='#F57F17')

    # Lines to SPD
    ax.plot([bus_x, spd_x], [spd_y + 1, spd_y + 1], color=C_CABLE_DC, linewidth=1.5)
    ax.plot([bus_x + 2, spd_x], [spd_y - 1, spd_y - 1], color='#333', linewidth=1.5)

    # --- DC Main disconnect / Fuse ---
    disc_x = spd_x + 8
    disc_y = bus_mid_y
    ax.add_patch(FancyBboxPatch(
        (disc_x, disc_y - 2.5), 6, 5,
        boxstyle="round,pad=0.2", facecolor='white', edgecolor=C_FUSE, linewidth=2
    ))
    ax.text(disc_x + 3, disc_y + 0.8, "Sect.", ha='center', va='center',
            fontsize=8, fontweight='bold', color=C_FUSE)
    ax.text(disc_x + 3, disc_y - 0.5, "DC", ha='center', va='center',
            fontsize=8, fontweight='bold', color=C_FUSE)

    # Lines from bus to disconnect
    ax.plot([bus_x + 2, disc_x], [bus_mid_y, bus_mid_y], color=C_CABLE_DC, linewidth=2)

    # --- INVERTER ---
    inv_y = bus_mid_y - 5
    inv_w = 14
    inv_h = 10

    ax.add_patch(FancyBboxPatch(
        (inverter_x, inv_y), inv_w, inv_h,
        boxstyle="round,pad=0.5", facecolor=C_INVERTER_LIGHT,
        edgecolor=C_INVERTER, linewidth=2.5
    ))
    ax.text(inverter_x + inv_w / 2, inv_y + inv_h - 1.5, "VARIATEUR SOLAIRE",
            ha='center', va='top', fontsize=9, fontweight='bold', color='#E65100')
    ax.text(inverter_x + inv_w / 2, inv_y + inv_h - 3,
            f"INVT {inverter.model}",
            ha='center', va='top', fontsize=8, color='#BF360C')
    ax.text(inverter_x + inv_w / 2, inv_y + inv_h - 4.3,
            f"{inverter.power_kw:.0f} kW",
            ha='center', va='top', fontsize=10, fontweight='bold', color='#E65100')

    # DC input terminals
    ax.text(inverter_x + 1, inv_y + inv_h / 2 + 1, "PV+", fontsize=7,
            fontweight='bold', color=C_CABLE_DC)
    ax.text(inverter_x + 1, inv_y + inv_h / 2 - 1.5, "PV-", fontsize=7,
            fontweight='bold', color='#333')

    # AC output terminals
    ax.text(inverter_x + inv_w - 2, inv_y + inv_h / 2 + 1.5, "U", fontsize=7,
            fontweight='bold', color=C_CABLE_AC)
    ax.text(inverter_x + inv_w - 2, inv_y + inv_h / 2, "V", fontsize=7,
            fontweight='bold', color=C_CABLE_AC)
    ax.text(inverter_x + inv_w - 2, inv_y + inv_h / 2 - 1.5, "W", fontsize=7,
            fontweight='bold', color=C_CABLE_AC)

    # PE terminal
    ax.text(inverter_x + inv_w / 2, inv_y + 0.5, "PE", fontsize=7,
            fontweight='bold', color=C_CABLE_GND)

    # Line from disconnect to inverter DC input
    ax.plot([disc_x + 6, inverter_x], [bus_mid_y, inv_y + inv_h / 2],
            color=C_CABLE_DC, linewidth=2.5)

    # --- MOTOR ---
    mot_center_x = motor_x + 4
    mot_center_y = inv_y + inv_h / 2
    mot_r = 4

    circle = plt.Circle((mot_center_x, mot_center_y), mot_r,
                         facecolor=C_MOTOR_LIGHT, edgecolor=C_MOTOR, linewidth=2.5)
    ax.add_patch(circle)
    ax.text(mot_center_x, mot_center_y + 1, "M", ha='center', va='center',
            fontsize=18, fontweight='bold', color='#2E7D32')
    ax.text(mot_center_x, mot_center_y - 0.8, "3~", ha='center', va='center',
            fontsize=10, fontweight='bold', color='#2E7D32')
    ax.text(mot_center_x, mot_center_y - mot_r - 1.5,
            f"{motor.power_kw:.1f} kW / {motor.current_a:.0f} A",
            ha='center', fontsize=8, fontweight='bold', color='#2E7D32')

    # AC lines from inverter to motor (3 phases)
    for i, (label, offset) in enumerate(zip(['U', 'V', 'W'], [1.5, 0, -1.5])):
        ax.plot([inverter_x + inv_w, mot_center_x - mot_r],
                [inv_y + inv_h / 2 + offset, mot_center_y + offset],
                color=C_CABLE_AC, linewidth=1.5)

    # AC cable label
    mid_ac = (inverter_x + inv_w + mot_center_x - mot_r) / 2
    ax.text(mid_ac, inv_y + inv_h / 2 + 4, "Cable AC triphase",
            ha='center', fontsize=8, fontweight='bold', color=C_CABLE_AC)
    ax.text(mid_ac, inv_y + inv_h / 2 + 2.5,
            f"{motor.voltage_v:.0f}V / {motor.current_a:.0f}A",
            ha='center', fontsize=7, color=C_CABLE_AC)

    # Ground line
    ax.plot([inverter_x + inv_w / 2, inverter_x + inv_w / 2, mot_center_x, mot_center_x],
            [inv_y, inv_y - 3, inv_y - 3, mot_center_y - mot_r],
            color=C_CABLE_GND, linewidth=1.5, linestyle='--')

    # Ground symbol
    gnd_x = inverter_x + inv_w / 2 + 5
    gnd_y = inv_y - 4
    for i, w in enumerate([3, 2, 1]):
        ax.plot([gnd_x - w / 2, gnd_x + w / 2],
                [gnd_y - i * 0.8, gnd_y - i * 0.8],
                color=C_CABLE_GND, linewidth=2)
    ax.text(gnd_x, gnd_y + 1.5, "PE", ha='center', fontsize=7,
            fontweight='bold', color=C_CABLE_GND)
    ax.plot([gnd_x, gnd_x], [inv_y - 3, gnd_y], color=C_CABLE_GND,
            linewidth=1.5, linestyle='--')

    # --- Pump below motor ---
    pump_y = mot_center_y - mot_r - 5
    ax.plot([mot_center_x, mot_center_x], [mot_center_y - mot_r, pump_y + 2],
            color='#555', linewidth=2)
    ax.add_patch(FancyBboxPatch(
        (mot_center_x - 3, pump_y - 1), 6, 3,
        boxstyle="round,pad=0.3", facecolor='#E1F5FE', edgecolor=C_WATER, linewidth=2
    ))
    ax.text(mot_center_x, pump_y + 0.5, "POMPE", ha='center', va='center',
            fontsize=8, fontweight='bold', color='#0277BD')

    # Water arrow
    ax.annotate('', xy=(mot_center_x + 5, pump_y + 0.5),
                xytext=(mot_center_x + 3, pump_y + 0.5),
                arrowprops=dict(arrowstyle='->', color=C_WATER, lw=2))
    ax.text(mot_center_x + 7, pump_y + 0.5, "Eau",
            va='center', fontsize=8, color=C_WATER, fontstyle='italic')

    # --- Specifications box ---
    specs_y = 8
    specs = [
        f"Voc STC: {result.voc_stc:.1f} V | Voc max (-10C): {result.voc_max_cold:.1f} V",
        f"Vmp STC: {result.vmp_stc:.1f} V | Vmp min (50C): {result.vmp_min_hot:.1f} V",
        f"Isc: {result.isc_stc:.2f} A | Imp: {result.imp_stc:.2f} A",
        f"Puissance crete: {result.total_power_w/1000:.2f} kWc | "
        f"Ratio PV/Var: {result.ratio_pv_inverter:.2f}x",
    ]
    ax.add_patch(FancyBboxPatch(
        (5, specs_y - 3), 85, len(specs) * 2.2 + 2,
        boxstyle="round,pad=0.5", facecolor='#F5F5F5', edgecolor='#BDBDBD', linewidth=1
    ))
    ax.text(7, specs_y + len(specs) * 2.2 - 2.5, "Caracteristiques electriques:",
            fontsize=9, fontweight='bold', color='#003366')
    for i, spec in enumerate(specs):
        ax.text(7, specs_y + len(specs) * 2.2 - 4.5 - i * 2, spec,
                fontsize=8, fontfamily='monospace', color='#37474F')

    # --- Legend ---
    legend_y = 3
    legend_items = [
        (C_CABLE_DC, '-', "Cable DC"),
        (C_CABLE_AC, '-', "Cable AC"),
        (C_CABLE_GND, '--', "Terre (PE)"),
        (C_FUSE, '-', "Protection / Sectionnement"),
    ]
    for i, (color, ls, text) in enumerate(legend_items):
        lx = 100 + i * 20
        ax.plot([lx, lx + 3], [legend_y, legend_y], color=color,
                linewidth=2, linestyle=ls)
        ax.text(lx + 3.5, legend_y, text, va='center', fontsize=7, color=C_TEXT)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf
