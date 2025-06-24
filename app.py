import os, requests, pandas as pd
from datetime import datetime,  timezone, timedelta
from dotenv import load_dotenv, dotenv_values

import itertools
import random
import streamlit as st

import numpy as np
from typing import Union, Callable

# The total head is now fixed to this constant value in meters.
FIXED_HEAD = 88.0

#_____________________________________________________________________HydroPower Calculus_____________________________________________

class HydroPowerCalculator:
    """
    Instantaneous electrical power:

        P_elec = P_hydraulic / η_motor 

    where
        P_hydraulic = ρ g Q H / η_pump(Q)
        H = FIXED_HEAD
        Q = discharge
        η_pump(Q) = pump efficiency curve
        η_motor = motor efficiency based on nominal flow.
    """

    def __init__(
        self,
        discharge: Union[str, pd.DataFrame, float],
        head: float,
        discharge_unit: str = 'm3_h',  
        temperature: float = 20.0,
        salinity: float = 35.0,
        g: float = 9.80665,
    ):
        # Calculate seawater density based on temperature and salinity
        self.rho = 1000 - 0.2 * temperature + 0.8 * salinity
        self.g = g
        self.H = head
        
        # This part is kept for compatibility but is not used by the main logic
        self._constant_q = None
        if isinstance(discharge, (int, float)):
            if discharge_unit == 'm3_h':
                self._constant_q = float(discharge) / 3600.0
                self._nominal_flow_m3h = float(discharge)
            elif discharge_unit == 'm3_s':
                self._constant_q = float(discharge)
                self._nominal_flow_m3h = float(discharge) * 3600.0
        else:
            raise ValueError("Discharge must be a numeric value for this simplified calculator.")

        self._eta_fun: Callable[[float], float] = lambda Q: HydroPowerCalculator._poly_efficiency(Q)

    @staticmethod
    def _poly_efficiency(Q: float) -> float:
        flow_lps = Q * 1000.0
        if flow_lps <= 3000.0:
            # Flow ≤ 3000 L/s
            R = -0.000006*flow_lps**2 + 0.045268*flow_lps + 0.024584
        elif 3000 < flow_lps <= 5000 : 
            R = -0.000003*flow_lps**2 + 0.027302*flow_lps + 24.666018
        else:
            R = -0.000005*flow_lps**2 + 0.051009*flow_lps + -36.439183
        η = R / 100.0
        return max(min(η, 1.0), 1e-6)

    @staticmethod
    def _get_motor_efficiency(nominal_flow_m3h: float) -> float:
        """Return motor efficiency based on nominal flow rate"""
        if abs(nominal_flow_m3h - 18000) < 100:
            return 0.971
        elif abs(nominal_flow_m3h - 15000) < 100:
            return 0.965
        elif abs(nominal_flow_m3h - 9000) < 100:
            return 0.965
        else:
            # Return a default if no exact match, useful for initialization
            return 0.96 

    def hauteur(self) -> float:
        """Return the fixed total head."""
        return self.H

    def rendement(self, Q: float) -> float:
        η = float(self._eta_fun(Q))
        if not (0 < η <= 1):
            raise ValueError("η(Q) must be in (0,1]")
        return η

# ─────────────────────────── CONFIG & GLOBAL CSS ────────────────────────────────
st.set_page_config(page_title="Optimisation des pompes", layout="wide")

st.markdown("""
<style>
/* ──── GLOBAL STYLING ──── */
.block-container             { padding: 0.5rem 0.5rem !important; max-width: 100vw !important; }
.block-container .element-container { margin: 0 !important; }
body                         { background: #f8f9fa; color: #333; font-family: 'Segoe UI', sans-serif; }

/* ──── COMPACT PUMP TABLE ──── */
[data-testid="column"]:nth-child(1){ flex: 0 0 40px !important; max-width: 40px !important; } /* Adjust pump label column width */

/* Header */
.header         { text-align: center; font-size: 0.6rem; font-weight: 600; white-space: nowrap; color: #555; padding-bottom: 0.2rem; }

/* File grouping */
.file-header {
    background: #2c8ac9;
    color: white;
    text-align: center;
    font-weight: 600;
    font-size: 1rem; /* Smaller font */
    padding: 0.1rem 0; /* Reduced padding */
    margin: 0.1rem 0;
    border-radius: 4px;
}

/* Cells styling */
.value-cell {
    background: #e9f5fe;
    color: #2c8ac9;
    border: 1px solid #d0e3f4;
    border-radius: 4px;
    font-size: 1rem; /* Smaller font */
    
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0 0.1rem;
    box-sizing: border-box; /* Include padding/border in element's total width and height */
}

/* Input fields */
.stTextInput input {
    background: #fff !important;
    color: #333 !important;
    border: 0.5px solid #ddd !important;
    height: 30px !important; /* Reduced height */
    font-size: 1rem !important; /* Smaller font */
    padding: 0 0.2rem !important;
}

/* Checkbox */
.stCheckbox {
    transform: scale(0.7); /* Smaller checkbox */
    margin-left: 0.2rem !important; /* Adjust margin */
    padding: 0 !important;
}

/* Selection circle */
.circle {
    width: 12px; /* Smaller circle */
    height: 12px;
    border-radius: 50%;
    margin: 0 auto;
    background: #e0e0e0;
}

/* ──── CONTROL PANEL ──── */
.control-panel {
    background: #fff;
    border-radius: 8px;
    padding: 0.6rem; /* Reduced padding */
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}

.flow-input-label {
    font-size: 1rem; /* Smaller font */
    font-weight: 600;
    color: #2c8ac9;
    margin-bottom: 0.2rem; /* Reduced margin */
    display: block;
}

.flow-input {
    width: 100%;
    margin-bottom: 0.6rem; /* Reduced margin */
}

.stNumberInput input {
    border: 2px solid #2c8ac9 !important;
    font-weight: 600 !important;
    font-size: 1rem !important; /* Slightly larger for clarity */
    height: 30px !important; /* Taller for easier interaction */
}

.simulate-btn {
    background: #2c8ac9 !important;
    color: white !important;
    border: none !important;
    font-weight: 600 !important;
    width: 100% !important;
    transition: all 0.2s !important;
    padding: 0.4rem 0.5rem !important; /* Reduced padding */
    font-size: 1rem !important; /* Smaller font */
    height: auto !important;
}

.simulate-btn:hover {
    background: #1d6998 !important;
    transform: translateY(-1px);
}

/* Results boxes */
.metric-box {
    background: #e9f5fe;
    color: #2c8ac9;
    border-left: 4px solid #2c8ac9;
    border-radius: 0 4px 4px 0;
    padding: 0.4rem; /* Reduced padding */
    margin-bottom: 0.4rem; /* Reduced margin */
    font-size: 1rem; /* Smaller font */
    font-weight: 600;
}

.metric-value {
    font-size: 1rem; /* Slightly smaller */
    font-weight: 700;
    margin-top: 0.1rem; /* Reduced margin */
}

.error-box {
    background: #fee9e9;
    color: #d32f2f;
    border-left: 4px solid #d32f2f;
    border-radius: 0 4px 4px 0;
    padding: 0.4rem; /* Reduced padding */
    margin-bottom: 0.4rem; /* Reduced margin */
    font-size: 1rem; /* Smaller font */
    font-weight: 600;
}

.combo-text {
    font-size: 1rem; /* Smaller font */
    color: #555;
    margin-top: 0.4rem; /* Reduced margin */
    line-height: 1.2; /* Tighter line spacing */
}

/* Compact spacing */
.element-container:has(.stTextInput),
.element-container:has(.stCheckbox) {
    margin-bottom: -0.8rem !important; /* Further reduce space between elements */
}

/* Adjust column spacing for tight fit */
[data-testid="stVerticalBlock"] > div > div > div {
    gap: 0.2rem; /* Reduce gap between elements in vertical blocks */
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── NOMINAL PUMP SPECS ────────────────────────────────
pump_specs = {
    f"File {i}_P{j}": (
        15000 if j == 1 else 9000 if j == 2 else 18000,  # débit nominal (m³/h)
        # puissance nominale (kW)
        3800 if j == 1 else 2400 if j == 2 else 4600
    )
    for i in range(1, 5) for j in (1, 2, 3)
}

# ─────────────────────────── OPTIMISATION LOGIC ────────────────────────────────
def optimise_for_flow(pump_data: dict, target_flow: float, allow_random=True):
    """Return combo with the lowest kW that still meets ≥ target_flow (m³/h)."""
    pids = [pid for pid, d in pump_data.items() if d["avail"]]

    # Calculate total available flow
    total_available_flow = sum(
        d["obs_flow"] if d["obs_flow"] is not None else d["nom_flow"]
        for pid, d in pump_data.items() if d["avail"]
    )

    if total_available_flow < target_flow:
        return {"error": "insufficient_flow", "available_flow": total_available_flow}

    # Find all valid combinations
    valid_combos = []
    for combo in itertools.product([0, 1], repeat=len(pids)):
        F = P = 0.0
        active = []
        for flag, pid in zip(combo, pids):
            if not flag:
                continue
            d = pump_data[pid]
            F += d["obs_flow"] if d["obs_flow"] is not None else d["nom_flow"]
            P += d["obs_power"] if d["obs_power"] is not None else d["nom_power"]
            active.append(pid)

        if F >= target_flow:
            valid_combos.append(
                {"pumps_on": active, "total_flow": F, "total_power": P})

    valid_combos.sort(key=lambda x: x["total_power"])

    if not valid_combos:
        return None

    min_power = valid_combos[0]["total_power"]
    best_combos = [c for c in valid_combos if abs(
        c["total_power"] - min_power) < 0.01]

    if allow_random and len(best_combos) > 1:
        if "last_solution_hash" not in st.session_state:
            st.session_state.last_solution_hash = None

        if "reset_selection" in st.session_state and st.session_state.reset_selection:
            selected = random.choice(best_combos)
            st.session_state.last_solution_hash = hash(
                tuple(sorted(selected["pumps_on"])))
            st.session_state.reset_selection = False
            return selected
        else:
            if st.session_state.last_solution_hash is not None:
                for combo in best_combos:
                    if hash(tuple(sorted(combo["pumps_on"]))) == st.session_state.last_solution_hash:
                        return combo
            return best_combos[0]
    else:
        return best_combos[0]


# ─────────────────────────── UI LAYOUT ────────────────────────────────
st.markdown("<h1 style='text-align:center;font-size:4rem;color:#2c8ac9;margin-bottom:0.5rem;'>Optimisation de l'utilisation des pompes</h1>", unsafe_allow_html=True)

# Adjust column ratios for better fit: Left (pump table) and Right (control panel/results)
# Adjusted ratio for more space for pumps
left_col, right_col = st.columns([3, 1])

# ─── PUMP TABLE ───
with left_col:
    # Headers
    headers = ["", "P. Nom.", "D. Nom.",
               "P. Obs.", "D. Calculé", "Dispo", "Sélection"]
    # Adjusted column widths to be very compact
    col_widths = [0.4, 0.9, 0.9, 0.9, 0.9, 0.6, 0.6]
    header_cols = st.columns(col_widths)
    for col, h in zip(header_cols, headers):
        col.markdown(f'<div class="header">{h}</div>', unsafe_allow_html=True)

    pump_data = {}
    placeholders = {}
    power_placeholders = {}  # New dictionary to store power display placeholders
    flow_placeholders = {}   # New dictionary to store flow display placeholders

    # Table body
    for file_num in range(1, 5):
        st.markdown(
            f'<div class="file-header">FILE {file_num}</div>', unsafe_allow_html=True)

        for pump_num in [3,1,2]:
            pid = f"File {file_num}_P{pump_num}"
            nom_flow, nom_power = pump_specs[pid]

            cols = st.columns(col_widths)
            # Pump label
            cols[0].markdown(
                f'<div style="text-align:center;font-weight:bold;font-size:0.6rem;">P{pump_num}</div>', unsafe_allow_html=True)
            # Nominal power
            cols[1].markdown(
                f'<div class="value-cell">{nom_power} kW</div>', unsafe_allow_html=True)
            # Nominal flow
            cols[2].markdown(
                f'<div class="value-cell">{nom_flow} m³/h</div>', unsafe_allow_html=True)
            # Observed power - now an input field
            obs_p_str = cols[3].text_input("", value=str(
                nom_power), key=f"{pid}_obs_p", label_visibility="collapsed")
            # Observed flow - now just a display (empty container)
            flow_placeholders[pid] = cols[4].empty()
            # Availability
            avail = cols[5].checkbox(
                "", value=True, key=f"{pid}_avail", label_visibility="collapsed")
            # Selection circle
            placeholders[pid] = cols[6].empty()

            # Parse observed values
            try:
                obs_p = float(obs_p_str)
            except ValueError:
                obs_p = nom_power

            pump_data[pid] = {
                "nom_flow": nom_flow, "nom_power": nom_power,
                "obs_flow": None,  # Will be calculated later
                "obs_power": None if obs_p == nom_power else obs_p,
                "avail": avail
            }

# ─── CONTROL PANEL ───
with right_col:
    st.markdown('<div class="control-panel">', unsafe_allow_html=True)

    # Flow input
    st.markdown('<div class="flow-input-label">DÉBIT DÉSIRÉ (m³/h)</div>',
                unsafe_allow_html=True)
    target_flow = st.number_input(
        "",
        value=30000.0,
        step=1000.0,
        key="target_flow",
        label_visibility="collapsed",
        format="%.0f",
        min_value=0.0,
        max_value=10000000000.0
    )
    
    st.markdown('<hr style="margin: 10px 0">', unsafe_allow_html=True)
    
    # New section for water properties
    st.markdown('<div class="flow-input-label">PROPRIÉTÉS DE L\'EAU</div>', unsafe_allow_html=True)
    
    temperature = st.number_input(
        "Température (°C)",
        value=20.0,
        min_value=2.0,
        max_value=30.0,
        step=0.1,
        format="%.1f",
        help="Température de l'eau de mer (entre 2°C et 30°C)"
    )
    
    salinity = st.number_input(
        "Salinité (kg/m³)",
        value=35.0,
        min_value=0.0,
        max_value=40.0,
        step=0.1,
        format="%.1f",
        help="Salinité de l'eau de mer (typiquement autour de 35 kg/m³)"
    )
    
    st.markdown('<hr style="margin: 10px 0">', unsafe_allow_html=True)

    # Calculate button - renamed from "simulate"
    calculate = st.button(
        "CALCULER ET OPTIMISER",
        key="calculate_btn",
        help="Calcule la puissance des pompes et trouve la combinaison optimale"
    )

    # Results containers
    flow_box = st.empty()
    power_box = st.empty()
    combo_box = st.empty()
    error_box = st.empty()

    st.markdown('</div>', unsafe_allow_html=True)

# ─── CALCULATION AND OPTIMISATION EXECUTION ───
if calculate:
    # --- Step 1: Calculate flow for all available pumps ---
    for pid, pump_info in pump_data.items():
        if pump_info["avail"]:
            power_to_use_kw = pump_info["obs_power"] if pump_info["obs_power"] is not None else pump_info["nom_power"]
            
            pump_calculator = HydroPowerCalculator(
                discharge=pump_info["nom_flow"],
                head=FIXED_HEAD,
                temperature=temperature,
                salinity=salinity
            )

            H = pump_calculator.hauteur()
            rho = pump_calculator.rho
            g = pump_calculator.g
            
            eta_pump_fixed = 0.81
            eta_motor = pump_calculator._get_motor_efficiency(pump_info["nom_flow"])
            eta_total = eta_pump_fixed * eta_motor

            power_to_use_watts = power_to_use_kw * 1000.0
            
            if rho * g * H > 0:
                calculated_q_m3s = (power_to_use_watts * eta_total) / (rho * g * H)
            else:
                calculated_q_m3s = 0.0
            
            calculated_flow_m3h = calculated_q_m3s * 3600.0

            pump_data[pid]["obs_flow"] = calculated_flow_m3h
            pump_data[pid]["obs_power"] = power_to_use_kw
        else:
            # Ensure unavailable pumps have zero flow/power
            pump_data[pid]["obs_flow"] = 0
            pump_data[pid]["obs_power"] = 0

    # --- Step 2: Run optimization ---
    st.session_state.reset_selection = True
    res = optimise_for_flow(pump_data, target_flow)
    error_box.empty()

    # --- Step 3: Display results based on optimization ---
    active_pumps = set(res.get("pumps_on", [])) if res and "error" not in res else set()

    # Draw the calculated flow cells and selection circles
    for pid, pump_info in pump_data.items():
        # Draw the selection circle
        placeholders[pid].markdown(
            f'<div class="circle" style="background:{"#00ff59" if pid in active_pumps else "#e0e0e0"};"></div>',
            unsafe_allow_html=True
        )

        # Draw the calculated flow cell
        if pump_info["avail"]:
            calculated_flow_m3h = pump_data[pid]["obs_flow"]
            
            cell_style = "value-cell"
            title_warning = ""

            # Priority 1: Green if selected
            if pid in active_pumps:
                cell_style = 'value-cell" style="background-color: #e6ffed; color: #28a745; font-weight: bold;"'
                title_warning = "Cette pompe est sélectionnée pour la combinaison optimale."
            # Priority 2: Red warning if flow is off-nominal
            elif not np.isclose(calculated_flow_m3h, pump_info["nom_flow"], rtol=0.05):
                cell_style = 'value-cell" style="background-color: #fee9e9; color: #d32f2f; font-weight: bold;"'
                title_warning = f"Attention: Le débit calculé ({calculated_flow_m3h:.0f}) est différent du débit nominal ({pump_info['nom_flow']:.0f}) !"
            
            flow_placeholders[pid].markdown(
                f'<div class="{cell_style}" title="{title_warning}">{calculated_flow_m3h:.1f} m³/h</div>',
                unsafe_allow_html=True
            )
        else:
            flow_placeholders[pid].markdown(f'<div class="value-cell" style="color: #aaa;">N/A</div>', unsafe_allow_html=True)

    # Display final metrics or error messages
    if not res:
        st.error("Aucune combinaison valide ne permet d'atteindre le débit cible.")
    elif "error" in res and res["error"] == "insufficient_flow":
        flow_box.markdown(
            f'<div class="metric-box">Débit Disponible<br>'
            f'<span class="metric-value">{res["available_flow"]:.0f} m³/h</span></div>',
            unsafe_allow_html=True
        )
        power_box.empty()
        combo_box.empty()
        error_box.markdown(
            f'<div class="error-box">Débit insuffisant pour atteindre le débit demandé<br>'
            f'Débit Total Disponible: {res["available_flow"]:.0f} m³/h<br>'
            f'Débit Demandé: {target_flow:.0f} m³/h</div>',
            unsafe_allow_html=True
        )
    else:
        # This is the success case, res is valid
        flow_box.markdown(
            f'<div class="metric-box">Débit Total<br>'
            f'<span class="metric-value">{res["total_flow"]:.0f} m³/h</span></div>',
            unsafe_allow_html=True
        )
        power_box.markdown(
            f'<div class="metric-box">Puissance Totale<br>'
            f'<span class="metric-value">{res["total_power"]:.0f} kW</span></div>',
            unsafe_allow_html=True
        )
        combo_text = ", ".join(pid.replace("File ", "F") for pid in res["pumps_on"])
        combo_box.markdown(
            f'<div class="combo-text">Pompes sélectionnées:<br><strong>{combo_text}</strong></div>',
            unsafe_allow_html=True
        )
