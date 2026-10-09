"""Solar pumping station sizing calculations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MotorSpecs:
    power_kw: float
    current_a: float
    voltage_v: float = 380.0
    phases: int = 3


@dataclass
class PanelSpecs:
    model: str
    pmax_w: float
    voc_v: float
    vmp_v: float
    isc_a: float
    imp_a: float
    coeff_voc_pct: float      # %/°C (negative value, e.g. -0.250)
    coeff_isc_pct: float      # %/°C (positive value, e.g. +0.045)
    coeff_pmax_pct: float     # %/°C (negative value, e.g. -0.290)
    noct_c: float = 45.0
    bifacial: bool = False
    bifaciality_pct: float = 0.0  # e.g. 80 for 80%
    max_system_voltage: float = 1500.0
    max_series_fuse_a: float = 35.0
    power_tolerance_pct: float = 3.0  # positive tolerance


@dataclass
class InverterSpecs:
    model: str
    power_kw: float
    vdc_max: float
    vdc_range_min: float
    vdc_range_max: float
    vdc_mpp: float
    vdc_start: float
    vdc_min_work: float
    input_current_nominal: float
    input_current_max: float
    output_current_nominal: float


@dataclass
class EnvironmentSpecs:
    temp_min_c: float = -10.0
    temp_max_c: float = 50.0
    bifacial_gain_pct: float = 10.0  # estimated rear-side gain


@dataclass
class PVConfig:
    panels_per_string: int
    num_strings: int

    @property
    def total_panels(self) -> int:
        return self.panels_per_string * self.num_strings


@dataclass
class CheckResult:
    name: str
    calculated: float
    calculated_str: str
    limit: float
    limit_str: str
    verdict: str  # "OK", "LIMITE", "NON CONFORME"
    detail: str = ""


@dataclass
class SizingResult:
    # PV array characteristics at STC
    total_power_w: float = 0.0
    voc_stc: float = 0.0
    vmp_stc: float = 0.0
    isc_stc: float = 0.0
    imp_stc: float = 0.0

    # Temperature-corrected values
    voc_max_cold: float = 0.0
    vmp_min_hot: float = 0.0
    isc_max_hot: float = 0.0
    tcell_cold: float = 0.0
    tcell_hot: float = 0.0

    # With bifacial gain
    isc_bifacial: float = 0.0
    imp_bifacial: float = 0.0

    # Ratios
    ratio_pv_inverter: float = 0.0
    ratio_pv_motor: float = 0.0
    ratio_inverter_motor_current: float = 0.0

    # Checks
    checks: list = field(default_factory=list)

    # Recommendations
    recommended_panels_per_string_min: int = 0
    recommended_panels_per_string_max: int = 0
    recommended_max_strings: int = 0

    # Overall verdict
    overall_verdict: str = "CONFORME"


def calculate_cell_temp(ambient_c: float, noct_c: float, irradiance: float = 1000.0) -> float:
    """Calculate cell temperature from ambient temperature and NOCT."""
    return ambient_c + (noct_c - 20.0) / 800.0 * irradiance


def correct_voltage_for_temp(v_stc: float, coeff_pct: float, tcell: float, tref: float = 25.0) -> float:
    """Correct voltage for temperature. coeff_pct is in %/°C (e.g., -0.250)."""
    delta_t = tcell - tref
    return v_stc * (1.0 + coeff_pct / 100.0 * delta_t)


def correct_current_for_temp(i_stc: float, coeff_pct: float, tcell: float, tref: float = 25.0) -> float:
    """Correct current for temperature. coeff_pct is in %/°C (e.g., +0.045)."""
    delta_t = tcell - tref
    return i_stc * (1.0 + coeff_pct / 100.0 * delta_t)


def compute_optimal_config(
    panel: PanelSpecs,
    inverter: InverterSpecs,
    motor: MotorSpecs,
    env: EnvironmentSpecs,
) -> PVConfig:
    """Compute optimal PV configuration (panels per string, number of strings)."""
    # Cell temperature at coldest (for max Voc)
    tcell_cold = env.temp_min_c  # conservative: cell temp = ambient when cold, no irradiance heating yet at startup

    # Max panels per string: Voc_cold < Vdc_range_max (recommended)
    voc_cold_per_panel = correct_voltage_for_temp(panel.voc_v, panel.coeff_voc_pct, tcell_cold)
    max_panels_voltage = int(inverter.vdc_range_max / voc_cold_per_panel)

    # Also check absolute max
    max_panels_abs = int(inverter.vdc_max / voc_cold_per_panel)

    # Min panels per string: Vmp_hot > Vdc_min_work
    tcell_hot = calculate_cell_temp(env.temp_max_c, panel.noct_c)
    vmp_hot_per_panel = correct_voltage_for_temp(panel.vmp_v, panel.coeff_voc_pct, tcell_hot)
    min_panels_voltage = int(inverter.vdc_min_work / vmp_hot_per_panel) + 1

    # Optimal: Vmp_stc * n ≈ Vdc_mpp
    optimal_panels = round(inverter.vdc_mpp / panel.vmp_v)

    # Clamp to valid range
    panels_per_string = max(min_panels_voltage, min(optimal_panels, max_panels_voltage))

    # Max strings: consider bifacial gain
    if panel.bifacial and env.bifacial_gain_pct > 0:
        isc_effective = panel.isc_a * (1.0 + env.bifacial_gain_pct / 100.0)
    else:
        isc_effective = panel.isc_a

    max_strings_nominal = int(inverter.input_current_nominal / panel.imp_a)
    max_strings_max = int(inverter.input_current_max / isc_effective)
    num_strings = min(max_strings_nominal, max_strings_max)
    num_strings = max(1, num_strings)

    # Check that total power is reasonable (1.2-1.6x inverter power)
    total_power = panels_per_string * num_strings * panel.pmax_w
    if total_power < motor.power_kw * 1000 * 1.2:
        # Try adding a string if possible
        test_strings = num_strings + 1
        if test_strings * isc_effective <= inverter.input_current_max:
            num_strings = test_strings

    return PVConfig(panels_per_string=panels_per_string, num_strings=num_strings)


def run_sizing(
    panel: PanelSpecs,
    inverter: InverterSpecs,
    motor: MotorSpecs,
    env: EnvironmentSpecs,
    config: PVConfig,
) -> SizingResult:
    """Run full sizing analysis for a pumping station."""
    result = SizingResult()

    n_series = config.panels_per_string
    n_parallel = config.num_strings

    # --- STC values ---
    result.total_power_w = n_series * n_parallel * panel.pmax_w
    result.voc_stc = n_series * panel.voc_v
    result.vmp_stc = n_series * panel.vmp_v
    result.isc_stc = n_parallel * panel.isc_a
    result.imp_stc = n_parallel * panel.imp_a

    # --- Temperature corrections ---
    # Cold case: cell temp = ambient (conservative for startup with no irradiance heating)
    result.tcell_cold = env.temp_min_c
    voc_cold_panel = correct_voltage_for_temp(panel.voc_v, panel.coeff_voc_pct, result.tcell_cold)
    result.voc_max_cold = n_series * voc_cold_panel

    # Hot case: cell temp from NOCT formula at max ambient
    result.tcell_hot = calculate_cell_temp(env.temp_max_c, panel.noct_c)
    vmp_hot_panel = correct_voltage_for_temp(panel.vmp_v, panel.coeff_voc_pct, result.tcell_hot)
    result.vmp_min_hot = n_series * vmp_hot_panel

    isc_hot_panel = correct_current_for_temp(panel.isc_a, panel.coeff_isc_pct, result.tcell_hot)
    result.isc_max_hot = n_parallel * isc_hot_panel

    # --- Bifacial gain ---
    if panel.bifacial and env.bifacial_gain_pct > 0:
        gain = 1.0 + env.bifacial_gain_pct / 100.0
        result.isc_bifacial = result.isc_stc * gain
        result.imp_bifacial = result.imp_stc * gain
    else:
        result.isc_bifacial = result.isc_stc
        result.imp_bifacial = result.imp_stc

    # --- Ratios ---
    result.ratio_pv_inverter = result.total_power_w / (inverter.power_kw * 1000)
    result.ratio_pv_motor = result.total_power_w / (motor.power_kw * 1000)
    result.ratio_inverter_motor_current = inverter.output_current_nominal / motor.current_a

    # --- Optimal range ---
    voc_cold_per_panel = correct_voltage_for_temp(panel.voc_v, panel.coeff_voc_pct, env.temp_min_c)
    vmp_hot_per_panel = correct_voltage_for_temp(panel.vmp_v, panel.coeff_voc_pct,
                                                  calculate_cell_temp(env.temp_max_c, panel.noct_c))
    result.recommended_panels_per_string_max = int(inverter.vdc_range_max / voc_cold_per_panel)
    result.recommended_panels_per_string_min = max(1, int(inverter.vdc_min_work / vmp_hot_per_panel) + 1)

    if panel.bifacial and env.bifacial_gain_pct > 0:
        isc_eff = panel.isc_a * (1.0 + env.bifacial_gain_pct / 100.0)
    else:
        isc_eff = panel.isc_a
    result.recommended_max_strings = int(inverter.input_current_max / isc_eff)

    # --- Checks ---
    checks = []

    # 1. Voc max (cold) vs absolute max
    v = result.voc_max_cold
    lim = inverter.vdc_max
    if v > lim:
        verdict = "NON CONFORME"
    elif v > lim * 0.95:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    margin = (1 - v / lim) * 100
    checks.append(CheckResult(
        "Voc max (froid) vs Vdc max",
        v, f"{v:.1f} V", lim, f"{lim:.0f} V", verdict,
        f"Marge : {margin:.1f}%"
    ))

    # 2. Voc max (cold) vs recommended range
    lim = inverter.vdc_range_max
    if v > lim:
        verdict = "NON CONFORME"
    elif v > lim * 0.97:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    margin = lim - v
    checks.append(CheckResult(
        "Voc max (froid) vs plage recommandee",
        v, f"{v:.1f} V", lim, f"{lim:.0f} V", verdict,
        f"Marge : {margin:.1f} V ({margin/lim*100:.1f}%)"
    ))

    # 3. Vmp STC vs MPP recommended
    v = result.vmp_stc
    lim = inverter.vdc_mpp
    diff_pct = abs(v - lim) / lim * 100
    if diff_pct < 5:
        verdict = "EXCELLENT"
    elif diff_pct < 15:
        verdict = "OK"
    else:
        verdict = "LIMITE"
    checks.append(CheckResult(
        "Vmp (STC) vs MPP recommande",
        v, f"{v:.1f} V", lim, f"{lim:.0f} V", verdict,
        f"Ecart : {diff_pct:.1f}%"
    ))

    # 4. Vmp min (hot) vs minimum working voltage
    v = result.vmp_min_hot
    lim = inverter.vdc_start  # use start voltage as practical minimum
    if v < lim:
        verdict = "NON CONFORME"
    elif v < lim * 1.1:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    checks.append(CheckResult(
        "Vmp min (chaud) vs tension demarrage",
        v, f"{v:.1f} V", lim, f"{lim:.0f} V", verdict,
        f"Marge : {v - lim:.1f} V"
    ))

    # 5. Imp vs nominal input current
    v = result.imp_stc
    lim = inverter.input_current_nominal
    if v > lim:
        verdict = "NON CONFORME"
    elif v > lim * 0.95:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    checks.append(CheckResult(
        "Imp total vs courant entree nominal",
        v, f"{v:.2f} A", lim, f"{lim:.1f} A", verdict,
        f"{'Depassement' if v > lim else 'Marge'} : {abs(v-lim)/lim*100:.1f}%"
    ))

    # 6. Isc vs max DC input current
    v = result.isc_stc
    lim = inverter.input_current_max
    if v > lim:
        verdict = "NON CONFORME"
    elif v > lim * 0.90:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    checks.append(CheckResult(
        "Isc total vs courant DC max",
        v, f"{v:.2f} A", lim, f"{lim:.1f} A", verdict,
        f"Marge : {(1-v/lim)*100:.1f}%"
    ))

    # 7. Bifacial Isc vs max DC input current
    if panel.bifacial and env.bifacial_gain_pct > 0:
        v = result.isc_bifacial
        lim = inverter.input_current_max
        if v > lim:
            verdict = "NON CONFORME"
        elif v > lim * 0.90:
            verdict = "LIMITE"
        else:
            verdict = "OK"
        checks.append(CheckResult(
            f"Isc bifacial (+{env.bifacial_gain_pct:.0f}%) vs courant DC max",
            v, f"{v:.2f} A", lim, f"{lim:.1f} A", verdict,
            f"Gain arriere {env.bifacial_gain_pct:.0f}%"
        ))

    # 8. Motor current vs inverter output
    v = motor.current_a
    lim = inverter.output_current_nominal
    if v > lim:
        verdict = "NON CONFORME"
    elif v > lim * 0.95:
        verdict = "LIMITE"
    else:
        verdict = "OK"
    checks.append(CheckResult(
        "Courant moteur vs sortie variateur",
        v, f"{v:.1f} A", lim, f"{lim:.1f} A", verdict,
        f"Marge : {(1-v/lim)*100:.1f}%"
    ))

    # 9. PV/Inverter ratio
    v = result.ratio_pv_inverter
    if v < 1.0:
        verdict = "LIMITE"
        detail = "Sous-dimensionnement PV"
    elif v > 1.8:
        verdict = "LIMITE"
        detail = "Sur-dimensionnement PV excessif"
    elif 1.2 <= v <= 1.6:
        verdict = "EXCELLENT"
        detail = "Ratio optimal"
    else:
        verdict = "OK"
        detail = "Ratio acceptable"
    checks.append(CheckResult(
        "Ratio PV / Variateur",
        v, f"{v:.2f}x", 0, "1.2x - 1.6x ideal", verdict, detail
    ))

    result.checks = checks

    # --- Overall verdict ---
    has_non_conforme = any(c.verdict == "NON CONFORME" for c in checks)
    has_limite = any(c.verdict == "LIMITE" for c in checks)
    if has_non_conforme:
        result.overall_verdict = "NON CONFORME"
    elif has_limite:
        result.overall_verdict = "A VERIFIER"
    else:
        result.overall_verdict = "CONFORME"

    return result
