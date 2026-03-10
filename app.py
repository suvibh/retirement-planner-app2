import streamlit as st
import pandas as pd
import requests
import json
import datetime
import time
import random
import math
import html
import re
from dateutil.relativedelta import relativedelta
import warnings
import firebase_admin
from firebase_admin import credentials, firestore
from concurrent.futures import ThreadPoolExecutor

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# --- CONFIG & SUPPRESSION ---
warnings.simplefilter(action='ignore', category=FutureWarning)
st.set_page_config(page_title="AI Retirement Planner Pro", layout="wide", page_icon="🏦",
                   initial_sidebar_state="expanded")

# --- GLOBAL CONSTANTS ---
SS_WAGE_BASE_2026 = 168600
ADDL_MED_TAX_THRESHOLD = 250000
IRA_LIMIT_BASE = 7000
PLAN_401K_LIMIT_BASE = 23500
CATCHUP_401K_BASE = 7500
CATCHUP_IRA_BASE = 1000

SS_MFJ_TIER1_BASE = 32000
SS_MFJ_TIER2_BASE = 44000
SS_SINGLE_TIER1_BASE = 25000
SS_SINGLE_TIER2_BASE = 34000

MEDICARE_GAP_COST = 15000
LTC_SHOCK_COST = 100000
SHORTFALL_PENALTY_RATE = 0.12  # 12% Annual Penalty on Unfunded Debt
WIDOW_EXPENSE_MULTIPLIER = 0.60
MEDICARE_CLIFF_SINGLE_DROP = 0.25  # 25% drop per spouse going on Medicare
ROTH_CASH_BUFFER_MARGIN = 0.95
BUDGET_CATEGORIES = ["Housing / Rent", "Transportation", "Food", "Utilities", "Insurance", "Healthcare",
                     "Entertainment", "Education", "Personal Care", "Subscriptions", "Travel", "Debt Payments", "Other"]

# --- GOOGLE ANALYTICS INJECTION ---
GA_MEASUREMENT_ID = st.secrets.get("GA_MEASUREMENT_ID", "")
if GA_MEASUREMENT_ID:
    ga_script = f"""
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={html.escape(GA_MEASUREMENT_ID)}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{html.escape(GA_MEASUREMENT_ID)}');
    </script>
    """
    st.components.v1.html(ga_script, width=0, height=0)

# --- DESIGN SYSTEM & CSS ---
DESIGN_SYSTEM = """
<style>
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --primary-light: #e0e7ff;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --surface: #ffffff;
    --border: #e2e8f0;
    --text-primary: #0f172a;
    --text-secondary: #64748b;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 20px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.08);
}
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
* { font-family: 'Inter', sans-serif !important; }
h1 { font-size: 2.2rem !important; font-weight: 900 !important; background: linear-gradient(135deg, var(--primary-dark), #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.5px; }
h2 { font-weight: 800 !important; color: var(--text-primary) !important; }
h3 { font-weight: 700 !important; color: var(--text-primary) !important; }
[data-testid="stSidebar"] { background: var(--text-primary) !important; border-right: none !important; }
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] .stRadio label { padding: 10px 16px !important; border-radius: var(--radius-sm) !important; transition: background 0.15s ease !important; cursor: pointer !important; }
[data-testid="stSidebar"] .stRadio label:hover { background: rgba(255,255,255,0.1) !important; }
[data-testid="stMetric"] { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; padding: 20px !important; box-shadow: var(--shadow-sm) !important; }
[data-testid="stMetricValue"] { color: var(--primary-dark) !important; font-size: 1.75rem !important; font-weight: 800 !important; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important; }
[data-testid="stDataEditor"] { border-radius: var(--radius-md) !important; border: 1px solid var(--border) !important; overflow: hidden !important; box-shadow: var(--shadow-sm) !important; }
[data-testid="stDataEditor"] tr:hover td { background: #f8fafc !important; }
[data-testid="stTabs"] button { font-weight: 600 !important; border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important; }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input { border-radius: var(--radius-sm) !important; border-color: var(--border) !important; font-size: 0.95rem !important; transition: border-color 0.15s ease, box-shadow 0.15s ease !important; }
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus { border-color: var(--primary) !important; box-shadow: 0 0 0 3px var(--primary-light) !important; }
[data-testid="stProgress"] > div > div { background: linear-gradient(90deg, var(--primary), #7c3aed) !important; border-radius: 999px !important; }
[data-testid="stPlotlyChart"] { border-radius: 16px !important; overflow: hidden !important; box-shadow: 0 2px 12px rgba(0,0,0,0.06) !important; background: white; border: 1px solid var(--border); padding: 10px; }
div[data-testid="stExpander"] { background-color: white !important; border: 1px solid var(--border) !important; border-radius: var(--radius-md) !important; box-shadow: var(--shadow-sm) !important; }
div.stButton > button { border-radius: 8px !important; font-weight: 600 !important; }
</style>
"""

MOBILE_CSS = """
<style>
@media (max-width: 768px) {
    [data-testid="column"] { min-width: 100% !important; }
    button { min-height: 48px !important; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
}
</style>
"""
st.markdown(DESIGN_SYSTEM + MOBILE_CSS, unsafe_allow_html=True)


# --- REUSABLE UI COMPONENTS ---
def apply_chart_theme(fig, title=""):
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, weight=700, color="#0f172a")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#64748b", size=12), hovermode="x unified",
        hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0", font_size=13, font_family="Inter"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=12)),
        xaxis=dict(showgrid=False, zeroline=False, color="#94a3b8", tickfont=dict(size=11)),
        yaxis=dict(gridcolor="#f1f5f9", zeroline=False, tickformat="$,.0f", color="#94a3b8", tickfont=dict(size=11)),
        margin=dict(l=0, r=0, t=50, b=0)
    )
    return fig


def stat_card(label, value, delta=None, color="indigo", icon=""):
    delta_html = ""
    if delta is not None:
        color_d = "#10b981" if delta > 0 else "#ef4444"
        arrow = "↑" if delta > 0 else "↓"
        delta_html = f"<div style='color:{color_d}; font-size:0.8rem; font-weight:600;'>{arrow} {abs(delta):,.0f}</div>"

    colors = {
        "indigo": ("linear-gradient(135deg,#6366f1,#4f46e5)", "#e0e7ff"),
        "emerald": ("linear-gradient(135deg,#10b981,#059669)", "#d1fae5"),
        "amber": ("linear-gradient(135deg,#f59e0b,#d97706)", "#fef3c7"),
        "rose": ("linear-gradient(135deg,#ef4444,#dc2626)", "#fee2e2"),
    }
    grad, _ = colors.get(color, colors["indigo"])

    st.markdown(f"""
    <div style='background:{grad}; padding:20px; border-radius:16px; color:white; box-shadow: 0 4px 14px rgba(0,0,0,0.1);'>
        <div style='font-size:1.5rem; margin-bottom:4px;'>{html.escape(str(icon))}</div>
        <div style='font-size:1.8rem; font-weight:900; letter-spacing:-0.5px;'>{html.escape(str(value))}</div>
        <div style='font-size:0.85rem; opacity:0.9; margin-top:2px;'>{html.escape(str(label))}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def section_header(title, subtitle="", icon=""):
    st.markdown(f"""
    <div style='margin: 24px 0 16px 0;'>
        <div style='display:flex; align-items:center; gap:10px;'>
            <span style='font-size:1.4rem;'>{html.escape(str(icon))}</span>
            <h2 style='margin:0; font-size:1.3rem; font-weight:800; color:#0f172a;'>{html.escape(str(title))}</h2>
        </div>
        {f"<p style='margin:4px 0 0 34px; color:#64748b; font-size:0.9rem;'>{html.escape(str(subtitle))}</p>" if subtitle else ""}
    </div>
    """, unsafe_allow_html=True)


def info_banner(text, type="info"):
    configs = {
        "info": ("#eff6ff", "#3b82f6", "#1d4ed8", "💡"),
        "success": ("#f0fdf4", "#22c55e", "#15803d", "✅"),
        "warning": ("#fffbeb", "#f59e0b", "#b45309", "⚠️"),
        "danger": ("#fef2f2", "#ef4444", "#b91c1c", "🚨"),
    }
    bg, border, text_color, emoji = configs.get(type, configs["info"])
    st.markdown(f"""
    <div style='background:{bg}; border-left:4px solid {border}; padding:12px 16px; border-radius:0 8px 8px 0; margin-bottom:16px;'>
        <span style='color:{text_color}; font-size:0.9rem;'>{emoji} {html.escape(str(text))}</span>
    </div>
    """, unsafe_allow_html=True)


def retirement_health_score(score):
    color = "#10b981" if score > 75 else "#f59e0b" if score > 50 else "#ef4444"
    label = "Excellent" if score > 75 else "Needs Work" if score > 50 else "At Risk"
    st.markdown(f"""
    <div style='text-align:center; padding:20px; background:white; border-radius:16px; border:1px solid #e2e8f0; box-shadow:0 2px 8px rgba(0,0,0,0.04);'>
        <svg width='140' height='140' viewBox='0 0 140 140'>
            <circle cx='70' cy='70' r='56' fill='none' stroke='#f1f5f9' stroke-width='12'/>
            <circle cx='70' cy='70' r='56' fill='none' stroke='{color}' stroke-width='12' stroke-dasharray='{2 * 3.14159 * 56}' stroke-dashoffset='{2 * 3.14159 * 56 * (1 - score / 100)}' stroke-linecap='round' transform='rotate(-90 70 70)'/>
            <text x='70' y='66' text-anchor='middle' font-size='26' font-weight='900' fill='{color}' font-family='Inter'>{score}</text>
            <text x='70' y='84' text-anchor='middle' font-size='11' fill='#64748b' font-family='Inter'>{label}</text>
        </svg>
        <div style='color:#0f172a; font-weight:700; font-size:0.95rem; margin-top:8px;'>Monte Carlo Success Probability</div>
    </div>
    """, unsafe_allow_html=True)


def render_status_bar(deplete_year, deplete_age, final_nw, mc_success_rate=None):
    if deplete_year is not None:
        bg, icon, msg, sub = "#fef2f2", "🔴", "Liquidity Crisis Detected", f"Assets depleted at age {int(deplete_age)} ({int(deplete_year)}). Adjust retirement age or savings rate."
    elif final_nw > 2000000:
        bg, icon, msg, sub = "#f0fdf4", "🟢", "Strongly On Track", f"${final_nw:,.0f} projected at end of plan. Consider legacy or gifting strategies."
    elif final_nw > 0:
        bg, icon, msg, sub = "#fffbeb", "🟡", "Solvent but Tight", f"${final_nw:,.0f} margin at end of plan. Small changes could significantly improve outcome."
    else:
        bg, icon, msg, sub = "#fef2f2", "🔴", "Projected Insolvency", "Net worth goes negative before end of plan."

    mc_html = f"<span style='margin-left:16px; font-size:0.85rem; color:#64748b;'>Monte Carlo: <b>{mc_success_rate:.0f}%</b> success rate</span>" if mc_success_rate is not None else ""
    st.markdown(f"""
    <div style='background:{bg}; border-radius:12px; padding:16px 20px; display:flex; align-items:center; gap:12px; margin-bottom:20px; border: 1px solid #e2e8f0;'>
        <span style='font-size:1.8rem;'>{icon}</span>
        <div><div style='font-weight:800; font-size:1.1rem; color:#0f172a;'>{html.escape(msg)}</div><div style='font-size:0.9rem; color:#64748b; margin-top:2px;'>{html.escape(sub)}{mc_html}</div></div>
    </div>
    """, unsafe_allow_html=True)


def render_empty_state(section, icon):
    st.markdown(f"""
    <div style='text-align:center; padding:48px 24px; background:#f8fafc; border-radius:16px; border:2px dashed #cbd5e1; margin-bottom:20px;'>
        <div style='font-size:3rem; margin-bottom:12px;'>{icon}</div>
        <h3 style='color:#0f172a; margin:0 0 8px;'>No {html.escape(section)} Added Yet</h3>
        <p style='color:#64748b; margin:0 0 20px; font-size:0.95rem;'>Use the table to add rows, or click the AI button to auto-populate based on your profile.</p>
    </div>
    """, unsafe_allow_html=True)


def render_total(label, series):
    total = pd.to_numeric(series, errors='coerce').fillna(0).sum()
    st.markdown(
        f"<div style='text-align: right; font-weight: 600; color: #4f46e5; font-size: 1.1rem;'>{label}: <span style='color: #111827;'>${total:,.0f}</span></div>",
        unsafe_allow_html=True)


# --- 1. FIREBASE & SESSION CORE ---
try:
    import extra_streamlit_components as stx
except ImportError:
    st.error("Missing dependency: pip install extra-streamlit-components")
    st.stop()

if 'firebase_enabled' not in st.session_state:
    st.session_state['firebase_enabled'] = True
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(
                dict(st.secrets["firebase"])) if "firebase" in st.secrets else credentials.Certificate(
                'firebase_creds.json')
            firebase_admin.initialize_app(cred)
        except Exception:
            st.session_state['firebase_enabled'] = False
            st.warning("⚠️ Cloud Sync Disabled (Local Mode Active). Firebase initialization failed.")

try:
    if st.session_state['firebase_enabled']:
        db = firestore.client()
except Exception:
    st.session_state['firebase_enabled'] = False

FIREBASE_WEB_API_KEY = st.secrets.get("FIREBASE_WEB_API_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

with st.spinner("Authenticating Session..."):
    cookie_manager = stx.CookieManager(key="auth_cookie_manager")
    if cookie_manager.get_all() is None:
        time.sleep(0.5)


def sign_in(email, password):
    return requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}",
        json={"email": email, "password": password, "returnSecureToken": True}).json()


def sign_up(email, password):
    return requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_WEB_API_KEY}",
                         json={"email": email, "password": password, "returnSecureToken": True}).json()


def load_user_data(email):
    if email == "guest_demo" or not st.session_state['firebase_enabled']:
        return {}
    doc = db.collection('users').document(email).get()
    return doc.to_dict() if doc.exists else {}


def call_gemini_json(prompt, retries=3):
    if not GEMINI_API_KEY:
        st.error("⚠️ GEMINI_API_KEY is missing. AI operations disabled.")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json"}}

    for attempt in range(retries):
        try:
            res = requests.post(url, json=payload, timeout=15)
            res.raise_for_status()
            res_json = res.json()
            if "error" in res_json:
                if attempt == retries - 1:
                    st.error(f"⚠️ API Error: {res_json['error'].get('message')}")
                    return None
                time.sleep(2 ** attempt)
                continue
            text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
            parsed = json.loads(text)
            if isinstance(parsed, dict) and len(parsed) == 1 and isinstance(list(parsed.values())[0], list):
                return list(parsed.values())[0]
            return parsed
        except Exception:
            time.sleep(2 ** attempt)
    return None


def safe_num(val, default=0.0):
    if val is None or (isinstance(val, float) and math.isnan(val)) or val is pd.NA: return default
    try:
        clean_val = re.sub(r'[^\d.-]', '', str(val))
        if clean_val == "": return default
        return float(clean_val)
    except Exception:
        return default


def scrub_records(records):
    if not records: return []
    scrubbed = []
    for r in records:
        new_r = {}
        for k, v in r.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                new_r[k] = None
            else:
                new_r[k] = v
        scrubbed.append(new_r)
    return scrubbed


# --- AUTH LAYER ---
if 'user_email' not in st.session_state:
    saved_email = cookie_manager.get(cookie="user_email")
    if saved_email:
        st.session_state['user_email'] = saved_email
        st.session_state['user_data'] = load_user_data(saved_email)
        st.rerun()

    st.markdown(
        "<div style='text-align: center; padding-top: 50px;'><h1>🏦 AI Retirement Planner Pro</h1></div><p style='text-align: center; color: #64748b;'>Secure Login required to access your financial blueprint.</p>",
        unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab1, tab2 = st.tabs(["Secure Login", "New Account"])
        with tab1:
            le = st.text_input("Email", key="le")
            lp = st.text_input("Password", type="password", key="lp")
            if st.button("Sign In", type="primary", use_container_width=True):
                res = sign_in(le, lp)
                if "idToken" in res:
                    st.session_state['user_email'] = res['email']
                    st.session_state['user_data'] = load_user_data(res['email'])
                    cookie_manager.set("user_email", res['email'],
                                       expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    time.sleep(0.2)
                    st.rerun()
                else:
                    st.error("Login failed. Please check your email and password.")
        with tab2:
            se = st.text_input("New Email", key="se")
            sp = st.text_input("New Password", type="password", key="sp")
            if st.button("Create Account", type="primary", use_container_width=True):
                if len(sp) >= 6:
                    res = sign_up(se, sp)
                    if "idToken" in res:
                        st.session_state['user_email'] = res['email']
                        st.session_state['user_data'] = {}
                        cookie_manager.set("user_email", res['email'],
                                           expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                        time.sleep(0.2)
                        st.rerun()
                else:
                    st.warning("Password must be at least 6 characters long.")

        st.divider()
        if st.button("🚀 Try the Demo (Guest Mode)", use_container_width=True):
            st.session_state['user_email'] = "guest_demo"
            st.session_state['user_data'] = {}
            cookie_manager.set("user_email", "guest_demo",
                               expires_at=datetime.datetime.now() + datetime.timedelta(days=1))
            st.toast("Guest mode active.", icon="⚠️")
            st.rerun()
    st.stop()


# --- STATE INIT ---
def update_state(key, val):
    st.session_state[key] = val
    st.session_state['dirty'] = True


def initialize_session_state():
    if 'migration_v1' not in st.session_state:
        ud = st.session_state.get('user_data', {})
        p_info = ud.get('personal_info', {})

        st.session_state['my_name'] = p_info.get('name', '')
        st.session_state['my_dob'] = datetime.datetime.strptime(p_info.get('dob', '1980-01-01'),
                                                                "%Y-%m-%d").date() if p_info.get(
            'dob') else datetime.date(1980, 1, 1)
        st.session_state['has_spouse'] = p_info.get('has_spouse', False)
        st.session_state['spouse_name'] = p_info.get('spouse_name', '')
        st.session_state['spouse_dob'] = datetime.datetime.strptime(p_info.get('spouse_dob', '1982-01-01'),
                                                                    "%Y-%m-%d").date() if p_info.get(
            'spouse_dob') else datetime.date(1982, 1, 1)

        st.session_state['ret_age'] = int(p_info.get('retire_age', 65))
        st.session_state['s_ret_age'] = int(p_info.get('spouse_retire_age', 65))
        st.session_state['my_life_exp'] = int(p_info.get('my_life_exp', 95))
        st.session_state['spouse_life_exp'] = int(p_info.get('spouse_life_exp', 95))
        st.session_state['kids_data'] = p_info.get('kids', [])
        st.session_state['curr_city_flow'] = p_info.get('current_city', '')
        st.session_state['retire_city_flow'] = ud.get('retire_city', st.session_state['curr_city_flow'])
        st.session_state['income_data'] = ud.get('income', [])
        st.session_state['real_estate_data'] = ud.get('real_estate', [])
        st.session_state['business_data'] = ud.get('business', [])
        st.session_state['liquid_assets_data'] = ud.get('liquid_assets', [])
        st.session_state['liabilities_data'] = ud.get('liabilities', [])

        life_exp = ud.get('lifetime_expenses', [])
        if not life_exp:
            migrated = []
            current_year = datetime.date.today().year
            for c in ud.get('current_expenses', []):
                if c.get("Description"):
                    migrated.append({"Description": c.get("Description"), "Category": c.get("Category", "Other"),
                                     "Frequency": c.get("Frequency", "Monthly"), "Amount ($)": c.get("Amount ($)", 0),
                                     "Start Phase": "Now", "Start Year": None, "End Phase": "At Retirement",
                                     "End Year": None, "AI Estimate?": c.get("AI Estimate?", False)})
            for r in ud.get('retire_expenses', []):
                if r.get("Description"):
                    migrated.append({"Description": r.get("Description"), "Category": r.get("Category", "Other"),
                                     "Frequency": r.get("Frequency", "Monthly"), "Amount ($)": r.get("Amount ($)", 0),
                                     "Start Phase": "At Retirement", "Start Year": None, "End Phase": "End of Life",
                                     "End Year": None, "AI Estimate?": r.get("AI Estimate?", False)})
            for m in ud.get('one_time_events', []):
                if m.get("Description"):
                    try:
                        sy_int = int(str(m.get("Start Date (MM/YYYY)", "")).split('/')[-1])
                    except:
                        sy_int = current_year
                    try:
                        ey_int = int(str(m.get("End Date (MM/YYYY)", "")).split('/')[-1])
                    except:
                        ey_int = sy_int
                    migrated.append({"Description": m.get("Description"), "Category": "Other",
                                     "Frequency": m.get("Frequency", "One-Time"), "Amount ($)": m.get("Amount ($)", 0),
                                     "Start Phase": "Custom Year", "Start Year": sy_int, "End Phase": "Custom Year",
                                     "End Year": ey_int, "AI Estimate?": m.get("AI Estimate?", False)})

            if migrated:
                life_exp = migrated
            else:
                life_exp = [{"Description": "Groceries", "Category": "Food", "Frequency": "Monthly", "Amount ($)": 0,
                             "Start Phase": "Now", "Start Year": None, "End Phase": "End of Life", "End Year": None,
                             "AI Estimate?": False}]
        st.session_state['lifetime_expenses'] = life_exp

        st.session_state['assumptions'] = ud.get('assumptions', {
            "inflation": 3.0, "inflation_healthcare": 5.5, "inflation_education": 4.5,
            "market_growth": 7.0, "income_growth": 3.0, "property_growth": 3.0, "rent_growth": 3.0,
            "current_tax_rate": 5.0, "retire_tax_rate": 0.0, "roth_conversions": False,
            "roth_target": "24%", "withdrawal_strategy": "Standard", "stress_test": False,
            "glidepath": True, "medicare_gap": True, "medicare_cliff": True, "ltc_shock": False
        })

        st.session_state['dirty'] = False
        st.session_state['migration_v1'] = True


initialize_session_state()


def mark_dirty():
    st.session_state['dirty'] = True


def get_completion_score():
    score = 10
    if st.session_state.get('my_name'): score += 10
    if len(st.session_state.get('income_data', [])) > 0: score += 20
    if len(st.session_state.get('liquid_assets_data', [])) > 0: score += 20
    if len(st.session_state.get('lifetime_expenses', [])) > 0: score += 20
    if 'df_sim' in st.session_state and not st.session_state['df_sim'].empty: score += 20
    return min(100, score)


def city_autocomplete(label, key_prefix, default_val=""):
    input_key = f"{key_prefix}_input"
    if input_key not in st.session_state:
        st.session_state[input_key] = default_val
    current_val = st.text_input(label, key=input_key,
                                help="Type a major city. The AI uses this to look up local costs of living, property values, and state taxes.",
                                on_change=mark_dirty)
    if current_val and len(current_val) > 2 and current_val != default_val:
        current_val_clean = re.sub(r'[^a-zA-Z0-9, ]', '', str(current_val))[:100]
        try:
            api_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
            if api_key:
                url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={current_val_clean}&types=(cities)&key={api_key}"
                res = requests.get(url).json()
                if res.get("status") == "OK":
                    predictions = res.get("predictions", [])
                    if not any(current_val_clean == p["description"] for p in predictions):
                        st.caption("Did you mean:")
                        for p in predictions[:3]:
                            st.button(p["description"], key=f"{key_prefix}_{p['place_id']}",
                                      on_click=lambda k=input_key, v=p["description"]: st.session_state.update(
                                          {k: v, 'dirty': True}))
        except:
            pass
    return current_val


def clean_df(df, primary_key):
    if not isinstance(df, pd.DataFrame): return df
    if df.empty: return []
    valid_rows = []
    for r in df.to_dict('records'):
        clean_r = {}
        for vk, vv in r.items():
            if pd.isna(vv) or vv is pd.NA:
                clean_r[vk] = None
            else:
                clean_r[vk] = vv
        if str(clean_r.get(primary_key, '')).strip() != "":
            valid_rows.append(clean_r)
    return valid_rows


def save_profile():
    if st.session_state['user_email'] == "guest_demo":
        st.error("Persistent configurations disabled within the demonstration environment.")
        return
    if not st.session_state.get('firebase_enabled', True):
        st.error("Cloud saving disabled due to connection issues.")
        return

    my_age = relativedelta(datetime.date.today(), st.session_state['my_dob']).years
    spouse_age = relativedelta(datetime.date.today(), st.session_state['spouse_dob']).years if st.session_state[
        'has_spouse'] else 0

    user_data = {
        "personal_info": {
            "name": st.session_state['my_name'], "dob": st.session_state['my_dob'].strftime("%Y-%m-%d"),
            "age": my_age, "retire_age": st.session_state['ret_age'],
            "spouse_retire_age": st.session_state['s_ret_age'], "my_life_exp": st.session_state['my_life_exp'],
            "spouse_life_exp": st.session_state['spouse_life_exp'], "current_city": st.session_state['curr_city_flow'],
            "has_spouse": st.session_state['has_spouse'], "spouse_name": st.session_state['spouse_name'],
            "spouse_dob": st.session_state['spouse_dob'].strftime("%Y-%m-%d") if st.session_state[
                'has_spouse'] else None,
            "spouse_age": spouse_age, "kids": st.session_state['kids_data']
        },
        "retire_city": st.session_state['retire_city_flow'],
        "income": clean_df(pd.DataFrame(st.session_state['income_data']), "Description"),
        "real_estate": clean_df(pd.DataFrame(st.session_state['real_estate_data']), "Property Name"),
        "business": clean_df(pd.DataFrame(st.session_state['business_data']), "Business Name"),
        "liquid_assets": clean_df(pd.DataFrame(st.session_state['liquid_assets_data']), "Account Name"),
        "liabilities": clean_df(pd.DataFrame(st.session_state['liabilities_data']), "Debt Name"),
        "lifetime_expenses": clean_df(pd.DataFrame(st.session_state['lifetime_expenses']), "Description"),
        "assumptions": st.session_state['assumptions']
    }
    db.collection('users').document(st.session_state['user_email']).set(user_data)
    st.session_state['user_data'] = user_data
    st.session_state['dirty'] = False
    st.toast("✅ Complete Financial Blueprint Synchronized Successfully!")


# --- MODULE LEVEL SIMULATION CORE (CACHED) ---
def calc_federal_tax(ordinary_income, is_mfj, year_offset, inflation_rate):
    infl_factor = (1 + inflation_rate / 100) ** year_offset
    std_deduction = (29200 if is_mfj else 14600) * infl_factor
    taxable_ordinary = max(0, ordinary_income - std_deduction)

    b_mfj = [(23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24), (487450, 0.32), (731200, 0.35),
             (float('inf'), 0.37)]
    b_single = [(11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24), (243725, 0.32), (609350, 0.35),
                (float('inf'), 0.37)]
    brackets = b_mfj if is_mfj else b_single

    ord_tax = 0
    prev_limit = 0
    for limit, rate in brackets:
        adj_limit = limit * infl_factor
        if taxable_ordinary > prev_limit:
            taxable_in_bracket = min(taxable_ordinary, adj_limit) - prev_limit
            ord_tax += taxable_in_bracket * rate
        prev_limit = adj_limit

    marginal_rate = 0.10
    for limit, rate in brackets:
        if taxable_ordinary < limit * infl_factor:
            marginal_rate = rate
            break
    if taxable_ordinary > brackets[-1][0] * infl_factor: marginal_rate = 0.37
    return ord_tax, marginal_rate


def get_ltcg_rate(ordinary_income, is_mfj, year_offset, inflation_rate):
    infl_factor = (1 + inflation_rate / 100) ** year_offset
    niit_threshold = ADDL_MED_TAX_THRESHOLD * infl_factor
    cg_threshold_0 = 94050 * infl_factor if is_mfj else 47025 * infl_factor
    cg_threshold_15 = 583750 * infl_factor if is_mfj else 518900 * infl_factor

    if ordinary_income < cg_threshold_0:
        base_rate = 0.0
    elif ordinary_income < cg_threshold_15:
        base_rate = 0.15
    else:
        base_rate = 0.20
    niit = 0.038 if ordinary_income > niit_threshold else 0.0
    return base_rate + niit


def get_ss_multi(birth_year, claim_year):
    fra = 67 if birth_year >= 1960 else (66 + (min(birth_year - 1954, 10) / 12.0) if birth_year >= 1955 else 66)
    claim_age = claim_year - birth_year
    if claim_age < fra:
        months_early = (fra - claim_age) * 12
        if months_early <= 36:
            return 1.0 - (months_early * (5 / 9 * 0.01))
        else:
            return 1.0 - (36 * (5 / 9 * 0.01)) - ((months_early - 36) * (5 / 12 * 0.01))
    elif claim_age > fra:
        months_late = min((claim_age - fra) * 12, (70 - fra) * 12)
        return 1.0 + (months_late * (2 / 3 * 0.01))
    return 1.0


def run_simulation(mkt_sequence, ctx):
    if ctx['max_years'] <= 0: return [], [], [], {}
    irs_uniform_table = {73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4,
                         82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2,
                         91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4,
                         101: 6.0, 102: 5.6, 103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9, 109: 3.7,
                         110: 3.5, 111: 3.4, 112: 3.3, 113: 3.1, 114: 3.0, 115: 2.9, 116: 2.8, 117: 2.7, 118: 2.5,
                         119: 2.3, 120: 2.0}

    sim_assets = [{"Account Name": a.get("Account Name"), "Type": a.get("Type"), "Owner": a.get("Owner", "Me"),
                   "bal": safe_num(a.get("Current Balance ($)")),
                   "contrib": safe_num(a.get("Annual Contribution ($/yr)")), "growth": a.get("Est. Annual Growth (%)"),
                   "stop_at_ret": a.get("Stop Contrib at Ret.?", True)} for a in ctx['ast_records'] if
                  a.get("Account Name")]
    if not sim_assets: sim_assets = [
        {"Account Name": "Unallocated Cash", "Type": "Checking/Savings", "Owner": "Me", "bal": 0.0, "contrib": 0.0,
         "growth": 0.0, "stop_at_ret": False}]

    sim_debts = [{"bal": safe_num(d.get("Current Balance ($)")), "pmt": safe_num(d.get("Monthly Payment ($)")) * 12,
                  "rate": safe_num(d.get("Interest Rate (%)")) / 100, "name": d.get("Debt Name")} for d in
                 ctx['debt_records'] if d.get("Debt Name")]
    sim_re = [{"name": r.get("Property Name", "Property"), "is_primary": r.get("Is Primary Residence?", False),
               "val": safe_num(r.get("Market Value ($)")), "debt": safe_num(r.get("Mortgage Balance ($)")),
               "pmt": safe_num(r.get("Mortgage Payment ($)")) * 12, "exp": safe_num(r.get("Monthly Expenses ($)")) * 12,
               "rent": safe_num(r.get("Monthly Rent ($)")) * 12,
               "v_growth": float(r.get("Override Prop Growth (%)")) if pd.notna(
                   r.get("Override Prop Growth (%)")) and str(r.get("Override Prop Growth (%)")).strip() != "" else ctx[
                   'prop_g'], "r_growth": float(r.get("Override Rent Growth (%)")) if pd.notna(
            r.get("Override Rent Growth (%)")) and str(r.get("Override Rent Growth (%)")).strip() != "" else ctx[
            'rent_g'], "rate": safe_num(r.get("Interest Rate (%)")) / 100} for r in ctx['re_records'] if
              r.get("Property Name")]
    sim_biz = [{"name": b.get("Business Name"), "val": safe_num(b.get("Total Valuation ($)")),
                "own": safe_num(b.get("Your Ownership (%)")) / 100.0,
                "dist": safe_num(b.get("Annual Distribution ($)")),
                "v_growth": float(b.get("Override Val. Growth (%)")) if pd.notna(
                    b.get("Override Val. Growth (%)")) and str(b.get("Override Val. Growth (%)")).strip() != "" else
                ctx['mkt'], "d_growth": float(b.get("Override Dist. Growth (%)")) if pd.notna(
            b.get("Override Dist. Growth (%)")) and str(b.get("Override Dist. Growth (%)")).strip() != "" else ctx[
            'inc_g']} for b in ctx['biz_records'] if b.get("Business Name")]

    unfunded_debt_bal = 0
    prev_unfunded_debt_bal = 0
    last_irmaa_tier = 0

    primary_ss_record = next(
        (r for r in ctx['inc_records'] if r.get('Category') == 'Social Security' and r.get('Owner') == 'Me'), None)
    spouse_ss_record = next(
        (r for r in ctx['inc_records'] if r.get('Category') == 'Social Security' and r.get('Owner') == 'Spouse'), None)

    primary_ss_start_year = int(
        safe_num(primary_ss_record['Start Year'], ctx['current_year'])) if primary_ss_record else 9999
    spouse_ss_start_year = int(
        safe_num(spouse_ss_record['Start Year'], ctx['current_year'])) if spouse_ss_record else 9999

    primary_ss_multi = get_ss_multi(ctx['my_birth_year'], primary_ss_start_year)
    spouse_ss_multi = get_ss_multi(ctx['spouse_birth_year'], spouse_ss_start_year)

    sim_res, det_res, nw_det_res = [], [], []
    milestones_by_year = {}

    tapped_brokerage = tapped_trad = tapped_roth = cash_depleted = False
    ss_started_me = ss_started_spouse = irmaa_triggered = spouse_died_notified = me_died_notified = False

    prev_debt_bals = {d['name']: d['bal'] for d in sim_debts}
    prev_re_debts = {r['name']: r['debt'] for r in sim_re}
    prev_ast_bals = {a['Account Name']: a['bal'] for a in sim_assets}

    for year_offset in range(ctx['max_years'] + 1):
        year = ctx['current_year'] + year_offset
        my_current_age = year - ctx['my_birth_year']
        spouse_current_age = year - ctx['spouse_birth_year'] if ctx['has_spouse'] else 0

        is_my_alive = year <= ctx['primary_end_year']
        is_spouse_alive = ctx['has_spouse'] and (year <= ctx['spouse_end_year'])

        if not is_my_alive and not is_spouse_alive:
            break

        # Base Milestones
        if ctx['has_spouse'] and not is_spouse_alive and not spouse_died_notified:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append(
                {"desc": "💀 Spouse Passes Away (Step-up Basis Applied)", "amt": 0, "type": "critical"})
            spouse_died_notified = True

        if not is_my_alive and not me_died_notified:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "💀 You Pass Away", "amt": 0, "type": "critical"})
            me_died_notified = True

        if year == ctx['primary_retire_year'] and is_my_alive:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🎓 You Retire", "amt": 0, "type": "system"})

        if ctx['has_spouse'] and year == ctx['spouse_retire_year'] and is_spouse_alive:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🎓 Spouse Retires", "amt": 0, "type": "system"})

        if is_my_alive and my_current_age == 65:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🏥 Medicare Kicks In (You)", "amt": 0, "type": "system"})

        if ctx['has_spouse'] and is_spouse_alive and spouse_current_age == 65:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🏥 Medicare Kicks In (Spouse)", "amt": 0, "type": "system"})

        if is_my_alive and my_current_age == ctx['primary_rmd_age']:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🏦 Your RMDs Begin", "amt": 0, "type": "system"})

        if ctx['has_spouse'] and is_spouse_alive and spouse_current_age == ctx['spouse_rmd_age']:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append({"desc": "🏦 Spouse RMDs Begin", "amt": 0, "type": "system"})

        is_retired = year >= ctx['primary_retire_year']
        yd = {"Year": year, "Age (Primary)": my_current_age, "Age (Spouse)": spouse_current_age}
        nw_yd = {"Year": year, "Age (Primary)": my_current_age, "Age (Spouse)": spouse_current_age}

        annual_inc, annual_ss, pre_tax_ord, total_tax = 0, 0, 0, 0
        earned_income_me, earned_income_spouse = 0, 0
        match_income_by_owner = {"Me": 0, "Spouse": 0, "Joint": 0}

        base_mkt_yr = mkt_sequence[year_offset]
        if ctx['stress_test'] and year == ctx['primary_retire_year']:
            mkt_glide = -25.0
            mkt_roth = -25.0
        elif ctx['glidepath'] and is_retired:
            years_retired = year - ctx['primary_retire_year']
            mkt_glide = max(3.0, base_mkt_yr - (math.floor(years_retired / 5) * 1.0))
            mkt_roth = base_mkt_yr
        else:
            mkt_glide = base_mkt_yr
            mkt_roth = base_mkt_yr

        active_mfj = True if ctx['has_spouse'] and is_my_alive and is_spouse_alive else False

        # RMDs
        rmd_income = 0
        for a in sim_assets:
            if a.get('Type') in ['Traditional 401(k)', 'Traditional IRA'] and a['bal'] > 0:
                owner = a.get('Owner', 'Me')
                owner_age = my_current_age if owner in ['Me', 'Joint'] else spouse_current_age
                owner_alive = is_my_alive if owner in ['Me', 'Joint'] else is_spouse_alive
                owner_rmd_age = ctx['primary_rmd_age'] if owner in ['Me', 'Joint'] else ctx['spouse_rmd_age']
                if owner_alive and owner_age >= owner_rmd_age:
                    rmd_amt = a['bal'] / irs_uniform_table.get(owner_age, 2.0)
                    a['bal'] -= rmd_amt
                    rmd_income += rmd_amt
                    pre_tax_ord += rmd_amt

        if rmd_income > 0:
            annual_inc += rmd_income
            yd["Income: RMDs"] = rmd_income

        # Incomes
        primary_ss_entitlement, spouse_ss_entitlement = 0, 0
        for inc in ctx['inc_records']:
            owner = inc.get("Owner", "Me")
            cat_name = inc.get("Category", "Other")
            owner_retire_year = ctx['primary_retire_year'] if owner in ["Me", "Joint"] else ctx['spouse_retire_year']
            start_year = safe_num(inc.get('Start Year'), ctx['current_year'])
            end_year = safe_num(inc.get('End Year'), 2100)

            is_active = (year >= start_year) and (not inc.get("Stop at Ret.?", False) or year < owner_retire_year)
            if cat_name in ["Social Security", "Pension"]:
                is_active = (year >= start_year) and (year <= end_year)

            if inc.get("Description"):
                base_amt = safe_num(inc.get('Annual Amount ($)'))
                if cat_name == "Social Security":
                    ss_start = primary_ss_start_year if owner == "Me" else spouse_ss_start_year
                    offset = max(0, year - int(ss_start))
                    amt = (base_amt * (primary_ss_multi if owner == "Me" else spouse_ss_multi)) * (
                                (1 + ctx['infl'] / 100) ** offset)
                    if owner == "Me":
                        primary_ss_entitlement = amt
                    elif owner == "Spouse":
                        spouse_ss_entitlement = amt
                    continue

                if not is_active:
                    continue

                g = safe_num(inc.get('Override Growth (%)'), ctx['inc_g'])
                offset_for_growth = max(0, year - max(int(start_year), ctx['current_year']))
                amt = base_amt * ((1 + g / 100) ** offset_for_growth)

                if cat_name == "Employer Match (401k/HSA)":
                    if (owner == "Me" and is_my_alive) or (owner == "Spouse" and is_spouse_alive) or (
                            owner == "Joint" and (is_my_alive or is_spouse_alive)):
                        match_income_by_owner[owner] += amt
                    continue

                if (owner == "Me" and not is_my_alive) or (owner == "Spouse" and not is_spouse_alive) or (
                        owner == "Joint" and not is_my_alive and not is_spouse_alive):
                    continue

                annual_inc += amt
                pre_tax_ord += amt
                yd[f"Income: {cat_name}"] = yd.get(f"Income: {cat_name}", 0) + amt

                if cat_name in ["Base Salary (W-2)", "Bonus / Commission", "Contractor (1099)"]:
                    if owner in ["Me", "Joint"]:
                        earned_income_me += amt
                    elif owner == "Spouse":
                        earned_income_spouse += amt

        # SS Survivor & Taxation
        active_ss = 0
        if is_my_alive and is_spouse_alive:
            if year >= primary_ss_start_year: active_ss += primary_ss_entitlement
            if year >= spouse_ss_start_year: active_ss += spouse_ss_entitlement
            if primary_ss_entitlement > 0 and year >= primary_ss_start_year and not ss_started_me:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": "📈 Social Security Begins (You)", "amt": primary_ss_entitlement, "type": "system"})
                ss_started_me = True
            if spouse_ss_entitlement > 0 and year >= spouse_ss_start_year and not ss_started_spouse:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": "📈 Social Security Begins (Spouse)", "amt": spouse_ss_entitlement, "type": "system"})
                ss_started_spouse = True
        elif is_my_alive and not is_spouse_alive:
            primary_actual = primary_ss_entitlement if year >= primary_ss_start_year else 0
            survivor_benefit = max(primary_ss_entitlement, spouse_ss_entitlement)
            active_ss = max(primary_actual, survivor_benefit)
            if active_ss > 0 and not ss_started_me:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": "📈 Social Security Survivor Benefit Begins", "amt": active_ss, "type": "system"})
                ss_started_me = True
        elif is_spouse_alive and not is_my_alive:
            spouse_actual = spouse_ss_entitlement if year >= spouse_ss_start_year else 0
            survivor_benefit = max(primary_ss_entitlement, spouse_ss_entitlement)
            active_ss = max(spouse_actual, survivor_benefit)
            if active_ss > 0 and not ss_started_spouse:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": "📈 Social Security Survivor Benefit Begins", "amt": active_ss, "type": "system"})
                ss_started_spouse = True

        if active_ss > 0:
            annual_inc += active_ss
            annual_ss += active_ss
            yd["Income: Social Security"] = active_ss

            ss_provisional_income = pre_tax_ord + (active_ss * 0.5)
            if active_mfj:
                if ss_provisional_income <= SS_MFJ_TIER1_BASE:
                    taxable_ss = 0
                elif ss_provisional_income <= SS_MFJ_TIER2_BASE:
                    taxable_ss = min(0.5 * active_ss, 0.5 * (ss_provisional_income - SS_MFJ_TIER1_BASE))
                else:
                    taxable_ss = min(0.85 * active_ss,
                                     0.85 * (ss_provisional_income - SS_MFJ_TIER2_BASE) + min(0.5 * active_ss, 6000))
            else:
                if ss_provisional_income <= SS_SINGLE_TIER1_BASE:
                    taxable_ss = 0
                elif ss_provisional_income <= SS_SINGLE_TIER2_BASE:
                    taxable_ss = min(0.5 * active_ss, 0.5 * (ss_provisional_income - SS_SINGLE_TIER1_BASE))
                else:
                    taxable_ss = min(0.85 * active_ss,
                                     0.85 * (ss_provisional_income - SS_SINGLE_TIER2_BASE) + min(0.5 * active_ss, 4500))
            pre_tax_ord += taxable_ss

        # Business & Real Estate
        cur_biz_val, re_equity, total_exp, biz_income_total = 0, 0, 0, 0
        for b in sim_biz:
            if year_offset > 0:
                b['val'] *= (1 + b['v_growth'] / 100)
                b['dist'] *= (1 + b['d_growth'] / 100)
            cur_biz_val += (b['val'] * b['own'])
            annual_inc += b['dist']
            biz_income_total += b['dist']
            yd["Income: Biz Dist"] = yd.get("Income: Biz Dist", 0) + b['dist']

        # QBI Shield
        qbi_deduction = 0
        if biz_income_total > 0:
            infl_factor = (1 + ctx['infl'] / 100) ** year_offset
            qbi_threshold = (383900 if active_mfj else 191950) * infl_factor
            qbi_phaseout = (483900 if active_mfj else 241950) * infl_factor
            if pre_tax_ord < qbi_threshold:
                qbi_deduction = biz_income_total * 0.20
            elif pre_tax_ord < qbi_phaseout:
                qbi_deduction = biz_income_total * 0.20 * (
                            (qbi_phaseout - pre_tax_ord) / (qbi_phaseout - qbi_threshold))
            else:
                qbi_deduction = 0

        for r in sim_re:
            if year_offset > 0:
                r['rent'] *= (1 + r['r_growth'] / 100)
                r['exp'] *= (1 + ctx['infl'] / 100)
                r['val'] *= (1 + r['v_growth'] / 100)

            monthly_rate = r['rate'] / 12
            monthly_pmt = r['pmt'] / 12
            interest_paid, actual_mortgage_paid = 0, 0
            for _ in range(12):
                if r['debt'] > 0:
                    m_int = r['debt'] * monthly_rate
                    interest_paid += m_int
                    actual_mortgage_paid += min(r['debt'] + m_int, monthly_pmt)
                    r['debt'] = max(0, r['debt'] - max(0, monthly_pmt - m_int))
                else:
                    break

            if r['debt'] <= 0 and prev_re_debts.get(r['name'], 0) > 0:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": f"🏡 Mortgage Paid Off: {r['name']}", "amt": 0, "type": "system"})
            prev_re_debts[r['name']] = r['debt']
            re_equity += (r['val'] - r['debt'])

            if r['is_primary']:
                total_exp += (r['exp'] + actual_mortgage_paid)
                yd["Expense: Primary Home (Mortgage & Upkeep)"] = yd.get("Expense: Primary Home (Mortgage & Upkeep)",
                                                                         0) + (r['exp'] + actual_mortgage_paid)
                if r['rent'] > 0:
                    annual_inc += r['rent']
                    yd["Income: Primary Home Rent"] = yd.get("Income: Primary Home Rent", 0) + r['rent']
            else:
                net_re_cashflow = r['rent'] - (r['exp'] + actual_mortgage_paid)
                if net_re_cashflow > 0:
                    annual_inc += net_re_cashflow
                    yd["Income: Net Investment RE Cashflow"] = yd.get("Income: Net Investment RE Cashflow",
                                                                      0) + net_re_cashflow
                elif net_re_cashflow < 0:
                    total_exp += abs(net_re_cashflow)
                    yd["Expense: Net Investment RE Loss"] = yd.get("Expense: Net Investment RE Loss", 0) + abs(
                        net_re_cashflow)

            pre_tax_ord += max(0, r['rent'] - r['exp'] - interest_paid)

        tax_base_ord = max(0, pre_tax_ord - qbi_deduction)

        # Expenses
        for ev in ctx['exp_records']:
            desc = str(ev.get("Description", "")).strip()
            if not desc: continue

            cat = ev.get("Category", "Other")
            if ctx['owns_home'] and cat in ["Housing / Rent", "Debt Payments"]: continue
            if not ctx['owns_home'] and cat == "Debt Payments": continue

            freq = ev.get("Frequency", "Monthly")
            amt = safe_num(ev.get("Amount ($)", 0)) * (12 if freq == "Monthly" else 1)

            start_phase = ev.get("Start Phase", "Now")
            end_phase = ev.get("End Phase", "End of Life")

            actual_start = ctx['current_year']
            if start_phase == "At Retirement":
                actual_start = ctx['primary_retire_year']
            elif start_phase == "Custom Year":
                actual_start = safe_num(ev.get("Start Year"), ctx['current_year'])

            actual_end = ctx['max_year']
            if end_phase == "At Retirement":
                actual_end = ctx['primary_retire_year'] - 1
            elif end_phase == "Custom Year":
                actual_end = safe_num(ev.get("End Year"), ctx['max_year'])

            is_active = False
            if freq == "One-Time":
                is_active = (year == actual_start)
            else:
                is_active = (actual_start <= year <= actual_end)

            if is_active:
                cat_infl = ctx['infl_hc'] if cat in ["Healthcare", "Insurance"] else (
                    ctx['infl_ed'] if cat == "Education" else ctx['infl'])
                inflated_amt = amt * ((1 + cat_infl / 100) ** year_offset)

                if ctx['has_spouse'] and not (is_my_alive and is_spouse_alive) and freq != "One-Time" and cat not in [
                    "Education", "Debt Payments", "Healthcare", "Insurance", "Housing / Rent"]:
                    if year >= ctx['primary_retire_year']:
                        inflated_amt *= WIDOW_EXPENSE_MULTIPLIER

                primary_on_medicare = is_my_alive and my_current_age >= 65
                spouse_on_medicare = ctx['has_spouse'] and is_spouse_alive and spouse_current_age >= 65

                if ctx['medicare_cliff'] and cat == "Healthcare":
                    if actual_start < (ctx['my_birth_year'] + 65):
                        reduction = 1.0
                        if primary_on_medicare: reduction -= MEDICARE_CLIFF_SINGLE_DROP
                        if spouse_on_medicare: reduction -= MEDICARE_CLIFF_SINGLE_DROP
                        inflated_amt *= max(0.5, reduction)

                total_exp += inflated_amt

                if freq == "One-Time":
                    yd[f"Expense: Milestone ({desc})"] = inflated_amt
                    if year not in milestones_by_year: milestones_by_year[year] = []
                    milestones_by_year[year].append({"desc": desc, "amt": inflated_amt, "type": "normal"})
                else:
                    yd[f"Expense: {cat}"] = yd.get(f"Expense: {cat}", 0) + inflated_amt

                # 529 Plan Routing
                if any(k in desc.lower() for k in ['college', 'tuition', 'university', 'education', 'school']):
                    amount_to_cover = inflated_amt
                    covered_by_529 = 0
                    target_kid = next(
                        (k['name'].lower() for k in ctx['kids_data'] if k['name'].lower() in desc.lower()), None)

                    if target_kid:
                        for a in sim_assets:
                            if a.get('Type') == '529 Plan' and a['bal'] > 0 and re.search(
                                    rf'\b{re.escape(target_kid)}\b', str(a.get('Account Name', '')).lower()):
                                pull = min(a['bal'], amount_to_cover)
                                a['bal'] -= pull
                                amount_to_cover -= pull
                                covered_by_529 += pull
                                if amount_to_cover <= 0: break

                    if amount_to_cover > 0:
                        for a in sim_assets:
                            if a.get('Type') == '529 Plan' and a['bal'] > 0:
                                pull = min(a['bal'], amount_to_cover)
                                a['bal'] -= pull
                                amount_to_cover -= pull
                                covered_by_529 += pull
                                if amount_to_cover <= 0: break

                    if covered_by_529 > 0:
                        annual_inc += covered_by_529
                        yd[f"Income: Tax-Free 529 Withdrawal ({desc})"] = covered_by_529

        # Global Medicare Gap
        if ctx['medicare_gap'] and is_retired and my_current_age < 65:
            subsidy_factor = min(1.0, max(0.0, pre_tax_ord / 100000.0))
            gap_cost = (MEDICARE_GAP_COST * subsidy_factor) * ((1 + ctx['infl_hc'] / 100) ** year_offset)
            total_exp += gap_cost
            yd["Expense: Healthcare (Pre-Medicare Gap Proxy)"] = gap_cost

        # LTC Shock
        if ctx['ltc_shock']:
            if is_my_alive and my_current_age >= (ctx['my_life_exp_val'] - 2):
                ltc_cost = LTC_SHOCK_COST * ((1 + ctx['infl_hc'] / 100) ** year_offset)
                total_exp += ltc_cost
                yd["Expense: Long Term Care Shock (Primary)"] = ltc_cost
            if ctx['has_spouse'] and is_spouse_alive and spouse_current_age >= (ctx['spouse_life_exp_val'] - 2):
                ltc_cost_spouse = LTC_SHOCK_COST * ((1 + ctx['infl_hc'] / 100) ** year_offset)
                total_exp += ltc_cost_spouse
                yd["Expense: Long Term Care Shock (Spouse)"] = ltc_cost_spouse

        # Debt Amortization
        debt_bal_total = 0
        for d in sim_debts:
            actual_paid = 0
            for _ in range(12):
                if d['bal'] > 0:
                    m_int = d['bal'] * (d['rate'] / 12)
                    actual_paid += min(d['bal'] + m_int, d['pmt'] / 12)
                    d['bal'] = max(0, d['bal'] - max(0, (d['pmt'] / 12) - m_int))
                else:
                    break

            total_exp += actual_paid
            yd["Expense: Debt Payments"] = yd.get("Expense: Debt Payments", 0) + actual_paid

            if d['bal'] <= 0 and prev_debt_bals.get(d['name'], 0) > 0:
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append({"desc": f"🎉 Debt Paid Off: {d['name']}", "amt": 0, "type": "system"})
            prev_debt_bals[d['name']] = d['bal']
            debt_bal_total += d['bal']

        # Base Taxes & Contributions Pass
        base_fed_tax_pre_conversion, marginal_rate_pre_conversion = calc_federal_tax(tax_base_ord, active_mfj,
                                                                                     year_offset, ctx['infl'])
        state_tax_rate = ctx['cur_t'] if not is_retired else ctx['ret_t']
        base_state_tax_pre_conversion = tax_base_ord * (state_tax_rate / 100.0)

        user_out_of_pocket_contribs = 0
        person_401k_contribs = {'Me': 0, 'Spouse': 0, 'Joint': 0}

        plan_401k_limit = PLAN_401K_LIMIT_BASE * ((1 + ctx['infl'] / 100) ** year_offset)
        catchup_401k = CATCHUP_401K_BASE * ((1 + ctx['infl'] / 100) ** year_offset)
        ira_limit = IRA_LIMIT_BASE * ((1 + ctx['infl'] / 100) ** year_offset)
        catchup_ira = CATCHUP_IRA_BASE * ((1 + ctx['infl'] / 100) ** year_offset)

        for owner, match_left in list(match_income_by_owner.items()):
            if match_left <= 0: continue
            for acct_type_target in ['Traditional 401(k)', 'Roth 401(k)', 'HSA']:
                for a in sim_assets:
                    if a.get('Type') == acct_type_target and a.get('Owner') == owner:
                        a['match_contrib_queue'] = a.get('match_contrib_queue', 0) + match_left
                        match_income_by_owner[owner] = 0
                        break
                if match_income_by_owner[owner] == 0: break

        for owner, match_left in match_income_by_owner.items():
            if match_left > 0:
                found_fallback = False
                for a in sim_assets:
                    if a.get('Owner') == owner and a.get('Type') in ['Brokerage (Taxable)', 'HYSA', 'Checking/Savings']:
                        a['match_contrib_queue'] = a.get('match_contrib_queue', 0) + match_left
                        found_fallback = True
                        break
                if not found_fallback and len(sim_assets) > 0:
                    sim_assets[0]['match_contrib_queue'] = sim_assets[0].get('match_contrib_queue', 0) + match_left
                match_income_by_owner[owner] = 0

        for a in sim_assets:
            o_acct = a.get('Owner', 'Me')
            o_birth = ctx['my_birth_year'] if o_acct in ['Me', 'Joint'] else ctx['spouse_birth_year']
            o_ret = ctx['primary_retire_year'] if o_acct in ['Me', 'Joint'] else ctx['spouse_retire_year']
            o_alive = is_my_alive if o_acct in ['Me', 'Joint'] else is_spouse_alive
            added_this_year = 0

            if o_alive and not (a.get('stop_at_ret', True) and year >= o_ret):
                added_this_year = a['contrib']
                if a.get('Type') in ['Traditional 401(k)', 'Roth 401(k)']:
                    limit = plan_401k_limit + (catchup_401k if (year - o_birth) >= 50 else 0)
                    added_this_year = min(added_this_year, max(0, limit - person_401k_contribs[o_acct]))
                    person_401k_contribs[o_acct] += added_this_year
                elif a.get('Type') in ['Traditional IRA', 'Roth IRA']:
                    limit = ira_limit + (catchup_ira if (year - o_birth) >= 50 else 0)
                    added_this_year = min(added_this_year, limit)
                user_out_of_pocket_contribs += added_this_year
            a['approved_oop_contrib'] = added_this_year

        # Roth Conversion Optimizer
        total_converted = 0
        if ctx['roth_conversions'] and is_retired:
            infl_factor = (1 + ctx['infl'] / 100) ** year_offset
            std_deduction = (29200 if active_mfj else 14600) * infl_factor
            b_limits = {"12%": 94300, "22%": 201050, "24%": 383900, "32%": 487450} if active_mfj else {"12%": 47150,
                                                                                                       "22%": 100525,
                                                                                                       "24%": 191950,
                                                                                                       "32%": 243725}
            target_limit = b_limits.get(ctx['roth_target'], 383900) * infl_factor + std_deduction

            conversion_room = max(0, target_limit - tax_base_ord)
            available_cash = sum(a['bal'] for a in sim_assets if
                                 a.get('Type') in ['Checking/Savings', 'HYSA', 'Brokerage (Taxable)',
                                                   'Unallocated Cash'])
            locked_outflows = total_exp + user_out_of_pocket_contribs + base_fed_tax_pre_conversion + base_state_tax_pre_conversion
            safe_liquid_cash = max(0, available_cash - locked_outflows)

            est_tax_rate = marginal_rate_pre_conversion + (state_tax_rate / 100.0)
            max_tax_budget = safe_liquid_cash * ROTH_CASH_BUFFER_MARGIN
            max_conversion_by_cash = max_tax_budget / max(0.10, est_tax_rate)
            conversion_room = min(conversion_room, max_conversion_by_cash)

            if conversion_room > 0:
                for a in sim_assets:
                    if a.get('Type') in ['Traditional 401(k)', 'Traditional IRA'] and a['bal'] > 0:
                        convert = min(a['bal'], conversion_room - total_converted)
                        if convert > 0:
                            a['bal'] -= convert
                            total_converted += convert

                            tax_cost = convert * est_tax_rate
                            for ca in sim_assets:
                                if tax_cost <= 0: break
                                if ca.get('Type') in ['Checking/Savings', 'HYSA', 'Brokerage (Taxable)',
                                                      'Unallocated Cash']:
                                    pull = min(ca['bal'], tax_cost)
                                    ca['bal'] -= pull
                                    tax_cost -= pull

                            roth_found = False
                            for ra in sim_assets:
                                if ra.get('Type') in ['Roth 401(k)', 'Roth IRA'] and ra.get('Owner') == a.get('Owner'):
                                    ra['bal'] += convert
                                    roth_found = True
                                    break
                            if not roth_found:
                                sim_assets.append(
                                    {"Account Name": f"Converted Roth ({a.get('Owner')})", "Type": "Roth IRA",
                                     "Owner": a.get("Owner", "Me"), "bal": convert, "contrib": 0.0,
                                     "growth": a.get('growth'), "stop_at_ret": True})
                            if total_converted >= conversion_room:
                                break

            if total_converted > 0:
                pre_tax_ord += total_converted
                tax_base_ord += total_converted
                yd["Roth Conversion Amount"] = total_converted

        # Execute Mid-Year Growth
        for a in sim_assets:
            g = float(a.get('growth')) if pd.notna(a.get('growth')) and str(a.get('growth')).strip() != "" else (
                0.0 if a.get('Type') in ['Checking/Savings', 'HYSA', 'Unallocated Cash'] else (
                    mkt_glide if a.get('Type') in ['Traditional 401(k)', 'Traditional IRA',
                                                   'Brokerage (Taxable)'] else mkt_roth))
            add = a.pop('approved_oop_contrib', 0)
            match = a.pop('match_contrib_queue', 0)
            a['bal'] = (a['bal'] + (add + match) * 0.5) * (1 + g / 100) + (add + match) * 0.5

        # Final Taxes & IRMAA
        base_fed_tax, marginal_rate = calc_federal_tax(tax_base_ord, active_mfj, year_offset, ctx['infl'])
        state_tax = tax_base_ord * (state_tax_rate / 100.0)
        fica_tax = 0
        wage_base, addl_thresh = SS_WAGE_BASE_2026 * (
                    (1 + ctx['infl'] / 100) ** year_offset), ADDL_MED_TAX_THRESHOLD * (
                                             (1 + ctx['infl'] / 100) ** year_offset)
        for ei in [earned_income_me, earned_income_spouse]:
            if ei > 0: fica_tax += min(ei, wage_base) * 0.062 + ei * 0.0145 + max(0, ei - addl_thresh) * 0.009

        total_tax = base_fed_tax + state_tax + fica_tax
        yd["Expense: Taxes"] = total_tax

        num_medicare = (1 if is_my_alive and my_current_age >= 65 else 0) + (
            1 if is_spouse_alive and spouse_current_age >= 65 else 0)
        if num_medicare > 0:
            magi_for_irmaa = pre_tax_ord
            infl_f = (1 + ctx['infl'] / 100) ** year_offset
            t1, t2, t3, t4, t5 = 103000 * infl_f * (2 if active_mfj else 1), 129000 * infl_f * (
                2 if active_mfj else 1), 161000 * infl_f * (2 if active_mfj else 1), 193000 * infl_f * (
                                     2 if active_mfj else 1), 500000 * infl_f * (1.5 if active_mfj else 1)
            surcharge = 0
            if magi_for_irmaa > t5:
                surcharge = 6500 * infl_f
            elif magi_for_irmaa > t4:
                surcharge = 5500 * infl_f
            elif magi_for_irmaa > t3:
                surcharge = 4000 * infl_f
            elif magi_for_irmaa > t2:
                surcharge = 2500 * infl_f
            elif magi_for_irmaa > t1:
                surcharge = 1000 * infl_f
            if surcharge > 0:
                total_irmaa = surcharge * num_medicare
                total_exp += total_irmaa
                yd["Expense: Medicare IRMAA Surcharge"] = total_irmaa
                if not irmaa_triggered:
                    if year not in milestones_by_year: milestones_by_year[year] = []
                    milestones_by_year[year].append(
                        {"desc": "📉 Medicare IRMAA Surcharge Triggered", "amt": total_irmaa, "type": "system"})
                    irmaa_triggered = True
                if total_irmaa > last_irmaa_tier + 500:
                    if year not in milestones_by_year: milestones_by_year[year] = []
                    milestones_by_year[year].append(
                        {"desc": "📉 Medicare IRMAA Surcharge Tier Jumped", "amt": total_irmaa, "type": "system"})
                    last_irmaa_tier = total_irmaa

        # Waterfall
        if user_out_of_pocket_contribs > 0:
            yd["Expense: Portfolio Contributions"] = user_out_of_pocket_contribs

        cash_outflows = total_exp + user_out_of_pocket_contribs + total_tax
        net_cash_flow = annual_inc - cash_outflows
        yd["Net Savings"] = net_cash_flow

        if net_cash_flow > 0:
            yd["Cashflow: Surplus Reinvested"] = net_cash_flow
            if unfunded_debt_bal > 0:
                payoff = min(net_cash_flow, unfunded_debt_bal)
                unfunded_debt_bal -= payoff
                net_cash_flow -= payoff
            if net_cash_flow > 0 and sim_assets:
                brokerage = next((a for a in sim_assets if a.get('Type') == 'Brokerage (Taxable)'),
                                 next((a for a in sim_assets if a.get('Type') in ['Checking/Savings', 'HYSA']),
                                      sim_assets[0]))
                brokerage['bal'] += net_cash_flow
        elif net_cash_flow < 0:
            shortfall = abs(net_cash_flow)

            for a in sim_assets:
                if shortfall <= 0: break
                if a.get('Type') in ['Checking/Savings', 'HYSA', 'Unallocated Cash']:
                    shortfall, _ = _withdraw(a, shortfall, 'free', ctx, my_current_age, spouse_current_age, active_mfj,
                                             year_offset, tax_base_ord, marginal_rate, state_tax_rate, year)

            if shortfall > 0 and not cash_depleted and not any(a['bal'] > 0 for a in sim_assets if
                                                               a.get('Type') in ['Checking/Savings', 'HYSA',
                                                                                 'Unallocated Cash']):
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": "⚠️ Cash Reserves Depleted. Now drawing from investments.", "amt": 0, "type": "system"})
                cash_depleted = True

            for a in sim_assets:
                if shortfall <= 0: break
                if a.get('Type') == 'Brokerage (Taxable)':
                    shortfall, t_inc = _withdraw(a, shortfall, 'cg', ctx, my_current_age, spouse_current_age,
                                                 active_mfj, year_offset, tax_base_ord, marginal_rate, state_tax_rate,
                                                 year)
                    total_tax += t_inc
                    yd["Expense: Taxes"] = yd.get("Expense: Taxes", 0) + t_inc

            seq = ['Traditional 401(k)', 'Traditional IRA', 'Roth 401(k)', 'Roth IRA', 'HSA', 'Crypto', '529 Plan',
                   'Other'] if 'Standard' in ctx['active_withdrawal_strategy'] else ['Roth 401(k)', 'Roth IRA', 'HSA',
                                                                                     'Crypto', '529 Plan', 'Other',
                                                                                     'Traditional 401(k)',
                                                                                     'Traditional IRA']
            for t in seq:
                if shortfall <= 0: break
                for a in sim_assets:
                    if a.get('Type') == t:
                        shortfall, t_inc = _withdraw(a, shortfall, 'ordinary' if 'Traditional' in t else 'free', ctx,
                                                     my_current_age, spouse_current_age, active_mfj, year_offset,
                                                     tax_base_ord, marginal_rate, state_tax_rate, year)
                        total_tax += t_inc
                        yd["Expense: Taxes"] = yd.get("Expense: Taxes", 0) + t_inc

            if shortfall > 0:
                unfunded_debt_bal += shortfall
                yd["Income: Shortfall Debt Funded"] = shortfall

        if unfunded_debt_bal > 0 and prev_unfunded_debt_bal <= 0:
            if year not in milestones_by_year: milestones_by_year[year] = []
            milestones_by_year[year].append(
                {"desc": "🚨 MAJOR SHORTFALL: Retirement Accounts Depleted!", "amt": unfunded_debt_bal,
                 "type": "critical"})

        # Record final balances
        liquid_assets_total = sum(max(0, a['bal']) for a in sim_assets)
        for a in sim_assets: nw_yd[f"Asset: {a.get('Account Name', 'Account')}"] = max(0, a['bal'])

        net_worth = liquid_assets_total + re_equity + cur_biz_val - debt_bal_total - unfunded_debt_bal
        nw_yd.update({"Total Liquid Assets": liquid_assets_total, "Total Real Estate Equity": re_equity,
                      "Total Business Equity": cur_biz_val,
                      "Total Debt Liabilities": -(debt_bal_total + unfunded_debt_bal), "Total Net Worth": net_worth})

        for a in sim_assets:
            if a['bal'] <= 0 and prev_ast_bals.get(a['Account Name'], 0) > 0 and a.get('Type') == '529 Plan':
                if year not in milestones_by_year: milestones_by_year[year] = []
                milestones_by_year[year].append(
                    {"desc": f"🎓 529 Plan Depleted: {a['Account Name']}", "amt": 0, "type": "system"})
            prev_ast_bals[a['Account Name']] = a['bal']

        sim_res.append({"Year": year, "Age (Primary)": my_current_age, "Age (Spouse)": spouse_current_age,
                        "Annual Income": annual_inc, "Annual Expenses": total_exp,
                        "Annual Taxes": yd.get("Expense: Taxes", 0), "Annual Net Savings": yd.get("Net Savings", 0),
                        "Liquid Assets": liquid_assets_total, "Real Estate Equity": re_equity,
                        "Business Equity": cur_biz_val, "Debt": -debt_bal_total, "Unfunded Debt": unfunded_debt_bal,
                        "Net Worth": net_worth})
        det_res.append(yd)
        nw_det_res.append(nw_yd)

    return sim_res, det_res, nw_det_res, milestones_by_year


@st.cache_data(show_spinner=False)
def run_cached_simulation(mkt_sequence_tuple, ctx_str, user_email):
    ctx = json.loads(ctx_str)
    s_res, d_res, nw_res, milestones = run_simulation(list(mkt_sequence_tuple), ctx)
    return pd.DataFrame(s_res), pd.DataFrame(d_res).fillna(0), pd.DataFrame(nw_res).fillna(0), milestones


# --- PAGE RENDERERS ---
def render_dashboard():
    section_header("Executive Summary", "Your complete financial trajectory at a glance.", "🏠")

    sim_ctx = build_sim_context()
    if sim_ctx['my_age'] <= 0:
        render_empty_state("Profile", "👤")
        info_banner("Please complete your Profile (specifically your Date of Birth) to unlock the simulation.",
                    "warning")
        return

    if sim_ctx['max_years'] <= 0:
        st.warning("Your Life Expectancy must be greater than your Current Age to run the simulation.")
        return

    with st.spinner("Running high-precision simulation engine..."):
        mkt_seq = tuple([sim_ctx['mkt']] * (sim_ctx['max_years'] + 1))
        ctx_str = json.dumps(sim_ctx, sort_keys=True)
        df_sim_nominal, df_det_nominal, df_nw_nominal, run_milestones = run_cached_simulation(mkt_seq, ctx_str,
                                                                                              st.session_state.get(
                                                                                                  'user_email',
                                                                                                  'guest'))

        st.session_state['df_sim_nominal'] = df_sim_nominal
        st.session_state['df_det'] = df_det_nominal
        st.session_state['df_nw'] = df_nw_nominal

    if df_sim_nominal.empty:
        st.error("Simulation returned no data. Please check your profile and start dates.")
        return

    # Build Display DF
    df_sim = df_sim_nominal.copy()
    if st.session_state.get('view_todays_dollars', True):
        discounts = (1 + sim_ctx['infl'] / 100) ** (df_sim['Year'] - sim_ctx['current_year'])
        cols_sim = ["Annual Income", "Annual Expenses", "Annual Taxes", "Annual Net Savings", "Liquid Assets",
                    "Real Estate Equity", "Business Equity", "Debt", "Unfunded Debt", "Net Worth"]
        df_sim[cols_sim] = df_sim[cols_sim].div(discounts, axis=0)

    st.session_state['df_sim_display'] = df_sim

    final_nw = df_sim.iloc[-1]['Net Worth']
    shortfall_mask = df_sim['Unfunded Debt'] > 0
    deplete_year = df_sim[shortfall_mask]['Year'].min() if not df_sim[shortfall_mask].empty else None
    deplete_age = df_sim[shortfall_mask]['Age (Primary)'].min() if not df_sim[shortfall_mask].empty else None

    mc_success = st.session_state.get('mc_success_rate')
    if final_nw > 0 and deplete_year is None:
        score = 90
    elif deplete_year is not None:
        score = max(0, min(100, int(((deplete_year - sim_ctx['current_year']) / sim_ctx['max_years']) * 100)))
    else:
        score = 50

    render_status_bar(deplete_year, deplete_age, final_nw, mc_success)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        stat_card("Years to Retirement", max(0, sim_ctx['primary_retire_year'] - sim_ctx['current_year']), icon="⏳",
                  color="indigo")
    with col2:
        stat_card("Current Net Worth", f"${df_sim.iloc[0]['Net Worth']:,.0f}", icon="💵", color="emerald")
    with col3:
        stat_card("Retirement Net Worth",
                  f"${df_sim[df_sim['Year'] == sim_ctx['primary_retire_year']]['Net Worth'].values[0]:,.0f}", icon="🚀",
                  color="amber")
    with col4:
        stat_card("End of Plan Net Worth", f"${final_nw:,.0f}", icon="🏁", color="rose")

    c_gauge, c_sankey = st.columns([1, 2])
    with c_gauge:
        st.markdown("<br><br>", unsafe_allow_html=True)
        retirement_health_score(score)

    with c_sankey:
        sankey_title = "#### 🌊 Year 1 Cash Flow Snapshot" + (
            " (Today's $)" if st.session_state.get('view_todays_dollars', True) else "")
        st.write(sankey_title)
        row = df_det_nominal.iloc[0].copy()

        if st.session_state.get('view_todays_dollars', True):
            discount = (1 + sim_ctx['infl'] / 100) ** (row['Year'] - sim_ctx['current_year'])
            for k in row.keys():
                if isinstance(row[k], (int, float)) and k not in ["Age (Primary)", "Age (Spouse)", "Year"]:
                    row[k] /= discount

        inflows = {k.replace('Income: ', ''): v for k, v in row.items() if
                   k.startswith('Income:') and v > 0 and k != 'Income: Shortfall Debt Funded'}
        outflows = {k.replace('Expense: ', ''): v for k, v in row.items() if
                    k.startswith('Expense:') and v > 0 and k not in ['Expense: Unallocated Surplus Saved']}

        net_savings = row.get('Net Savings', 0)
        if net_savings > 0:
            outflows['Cashflow: Surplus Reinvested'] = net_savings
        elif net_savings < 0:
            inflows['Shortfall Debt Funded'] = abs(net_savings)

        in_labels = [f"{html.escape(k)}<br>${v:,.0f}" for k, v in inflows.items()]
        out_labels = [f"{html.escape(k)}<br>${v:,.0f}" for k, v in outflows.items()]
        total_inflow = sum(inflows.values())
        mid_label = f"Total Cash Pool<br>${total_inflow:,.0f}"

        labels = in_labels + [mid_label] + out_labels
        middle_idx = len(inflows)
        source, target, value, node_colors, link_colors = [], [], [], [], []

        for i, (k, v) in enumerate(inflows.items()):
            source.append(i);
            target.append(middle_idx);
            value.append(v)
            node_colors.append('#f43f5e' if k == 'Shortfall Debt Funded' else '#10b981')
            link_colors.append('rgba(244, 63, 94, 0.4)' if k == 'Shortfall Debt Funded' else 'rgba(16, 185, 129, 0.4)')

        node_colors.append('#3b82f6')

        for i, (k, v) in enumerate(outflows.items()):
            source.append(middle_idx);
            target.append(middle_idx + 1 + i);
            value.append(v)
            node_colors.append(
                '#10b981' if k in ['Portfolio Contributions', 'Cashflow: Surplus Reinvested'] else '#f43f5e')
            link_colors.append('rgba(16, 185, 129, 0.4)' if k in ['Portfolio Contributions',
                                                                  'Cashflow: Surplus Reinvested'] else 'rgba(244, 63, 94, 0.4)')

        if total_inflow > 0 and HAS_PLOTLY:
            fig_sankey = go.Figure(data=[go.Sankey(arrangement="snap",
                                                   node=dict(pad=35, thickness=30, line=dict(color="black", width=0.5),
                                                             label=labels, color=node_colors),
                                                   textfont=dict(color="black", size=12),
                                                   link=dict(source=source, target=target, value=value,
                                                             color=link_colors))])
            fig_sankey.update_layout(height=800, margin=dict(l=0, r=0, t=30, b=0), font=dict(size=12))
            st.plotly_chart(fig_sankey, use_container_width=True)


def render_profile():
    section_header("Profile & Family Context",
                   "Precision matters. Your exact birth year dictates RMDs, SS scaling, and IRS Catch-Up limits.",
                   "👨‍👩‍👧‍👦")

    c1, c2 = st.columns(2)
    my_name = c1.text_input("Your Name", value=st.session_state['my_name'], on_change=mark_dirty, key="input_my_name")
    my_dob = c2.date_input("Your Date of Birth", value=st.session_state['my_dob'], min_value=datetime.date(1920, 1, 1),
                           max_value=datetime.date.today(), on_change=mark_dirty, key="input_my_dob")

    st.session_state['my_name'] = my_name
    st.session_state['my_dob'] = my_dob

    st.session_state['curr_city_flow'] = city_autocomplete("Current City of Residence", "curr_city",
                                                           default_val=st.session_state['curr_city_flow'])

    st.divider()
    has_spouse = st.checkbox("Include a Spouse or Partner? (Enables joint tax brackets)",
                             value=st.session_state['has_spouse'], on_change=mark_dirty, key="input_has_spouse")
    st.session_state['has_spouse'] = has_spouse

    if has_spouse:
        sc1, sc2 = st.columns(2)
        spouse_name = sc1.text_input("Spouse/Partner Name", value=st.session_state['spouse_name'], on_change=mark_dirty,
                                     key="input_sp_name")
        spouse_dob = sc2.date_input("Spouse Date of Birth", value=st.session_state['spouse_dob'],
                                    min_value=datetime.date(1920, 1, 1), max_value=datetime.date.today(),
                                    on_change=mark_dirty, key="input_sp_dob")
        st.session_state['spouse_name'] = spouse_name
        st.session_state['spouse_dob'] = spouse_dob

    st.divider()
    st.write("**Dependent Details** *(AI uses ages to drop daycare costs and start college timelines)*")
    num_kids = st.number_input("Number of Dependents (Kids)", 0, 10, len(st.session_state['kids_data']),
                               on_change=mark_dirty, key="input_num_kids")

    new_kids_data = []
    for i in range(num_kids):
        k1, k2 = st.columns([3, 1])
        kn = k1.text_input(f"Dependent {i + 1} Name", value=st.session_state['kids_data'][i]['name'] if i < len(
            st.session_state['kids_data']) else "", key=f"kn_{i}", on_change=mark_dirty)
        ka = k2.number_input(f"Age {i + 1}", 0, 25,
                             st.session_state['kids_data'][i]['age'] if i < len(st.session_state['kids_data']) else 5,
                             key=f"ka_{i}", on_change=mark_dirty)
        new_kids_data.append({"name": kn, "age": ka})
    st.session_state['kids_data'] = new_kids_data


def render_income():
    section_header("Active Annual Income Streams",
                   "List your current and future income sources. The engine handles inflation and precise tax routing.",
                   "💵")
    info_banner(
        "Employer Match Note: List 401(k) matches here. The engine strips them from your spendable cash flow, but safely deposits them into your portfolios.")

    df_inc = pd.DataFrame(st.session_state.get('income_data', []))
    current_year = datetime.date.today().year
    my_age = relativedelta(datetime.date.today(), st.session_state['my_dob']).years
    if df_inc.empty:
        df_inc = pd.DataFrame(
            [{"Description": "Base Salary", "Category": "Base Salary (W-2)", "Owner": "Me", "Annual Amount ($)": 0,
              "Start Year": current_year, "End Year": current_year + max(0, 65 - my_age), "Stop at Ret.?": True,
              "Override Growth (%)": None}])
    else:
        if "Start Age" in df_inc.columns:
            df_inc["Start Year"] = current_year + (pd.to_numeric(df_inc["Start Age"], errors='coerce') - my_age)
            df_inc["End Year"] = current_year + (pd.to_numeric(df_inc["End Age"], errors='coerce') - my_age)
            df_inc = df_inc.drop(columns=["Start Age", "End Age"])

        if "Stop at Ret.?" not in df_inc.columns: df_inc["Stop at Ret.?"] = False
        df_inc = df_inc.reindex(
            columns=["Description", "Category", "Owner", "Annual Amount ($)", "Start Year", "End Year", "Stop at Ret.?",
                     "Override Growth (%)"])

    edited_inc = st.data_editor(
        df_inc,
        column_config={
            "Description": st.column_config.TextColumn("Description"),
            "Category": st.column_config.SelectboxColumn("Category", options=["Base Salary (W-2)", "Bonus / Commission",
                                                                              "Employer Match (401k/HSA)",
                                                                              "Equity / RSUs", "Contractor (1099)",
                                                                              "Dividends", "Social Security", "Pension",
                                                                              "Other"]),
            "Owner": st.column_config.SelectboxColumn("Whose Income?", options=["Me", "Spouse", "Joint"]),
            "Annual Amount ($)": st.column_config.NumberColumn("Amount per Year ($)", step=1000, format="$%d"),
            "Start Year": st.column_config.NumberColumn("Start Year", min_value=1900, max_value=2100, format="%d"),
            "End Year": st.column_config.NumberColumn("End Year", min_value=1900, max_value=2100, format="%d"),
            "Stop at Ret.?": st.column_config.CheckboxColumn("Stop at Retirement?",
                                                             help="If checked, this income will automatically turn off when the specific owner reaches their chosen retirement year."),
            "Override Growth (%)": st.column_config.NumberColumn("Custom Growth (%)", step=0.1, format="%.1f%%")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="inc_editor", on_change=mark_dirty
    )
    st.session_state['income_data'] = edited_inc.to_dict('records')

    for idx, inc in edited_inc.iterrows():
        if not inc.get("Stop at Ret.?") and (pd.isna(inc.get("End Year")) or str(inc.get("End Year")).strip() == ""):
            st.warning(
                f"⚠️ Income '{html.escape(str(inc.get('Description', 'Unknown')))}': 'Stop at Retirement' is unchecked, but no 'End Year' is provided. This income will continue indefinitely.")
        if inc.get("Category") == "Social Security" and safe_num(inc.get("Start Year")) > (
                st.session_state['my_dob'].year + 70):
            st.warning(
                f"⚠️ Social Security '{html.escape(str(inc.get('Description', 'Unknown')))}': Start Year implies claiming after age 70. The IRS permanently caps delayed retirement credits at age 70.")

    render_total("Total Pre-Tax Income", edited_inc['Annual Amount ($)'])

    col_ai_inc, _ = st.columns([3, 1])
    with col_ai_inc:
        if st.button("✨ Auto-Estimate My Social Security (AI)", type="primary", use_container_width=True):
            with st.spinner("Asking AI to estimate your Social Security benefits based on your age and income..."):
                spouse_age = relativedelta(datetime.date.today(), st.session_state['spouse_dob']).years if \
                st.session_state['has_spouse'] else 0
                curr_inc = pd.to_numeric(edited_inc['Annual Amount ($)'], errors='coerce').fillna(0).sum()
                if st.session_state['has_spouse']:
                    prompt = f"User is {my_age} years old making ${curr_inc}/year. Spouse is {spouse_age} years old. Estimate realistic annual Social Security primary insurance amounts (PIA) at Full Retirement Age for both. Return JSON: {{'ss_amount_me': integer, 'ss_amount_spouse': integer}}"
                else:
                    prompt = f"User is {my_age} years old making ${curr_inc}/year. Estimate their annual Social Security primary insurance amount (PIA) at Full Retirement Age. Return JSON: {{'ss_amount_me': integer}}"
                res = call_gemini_json(prompt)
                if res:
                    current_inc = edited_inc.to_dict('records')
                    my_birth_year = st.session_state['my_dob'].year
                    spouse_birth_year = st.session_state['spouse_dob'].year if st.session_state[
                        'has_spouse'] else current_year
                    if 'ss_amount_me' in res:
                        current_inc.append(
                            {"Description": "Estimated Social Security (Primary)", "Category": "Social Security",
                             "Owner": "Me", "Annual Amount ($)": res['ss_amount_me'], "Start Year": my_birth_year + 67,
                             "End Year": 2100, "Stop at Ret.?": False, "Override Growth (%)": None})
                    if 'ss_amount_spouse' in res and st.session_state['has_spouse']:
                        current_inc.append(
                            {"Description": "Estimated Social Security (Spouse)", "Category": "Social Security",
                             "Owner": "Spouse", "Annual Amount ($)": res['ss_amount_spouse'],
                             "Start Year": spouse_birth_year + 67, "End Year": 2100, "Stop at Ret.?": False,
                             "Override Growth (%)": None})
                    st.session_state['income_data'] = current_inc
                    mark_dirty()
                    st.rerun()


def render_assets():
    section_header("Assets, Debts & Net Worth",
                   "Construct your balance sheet. The AI draws down these buckets dynamically.", "🏦")

    tab_re, tab_biz, tab_ast, tab_debt = st.tabs(
        ["🏢 Real Estate", "💼 Business Interests", "🏦 Liquid Assets", "💳 Debts & Loans"])

    with tab_re:
        info_banner(
            "Smart Mortgages: Enter your balance, rate, and payment. The math engine automatically pays it down and drops the expense once it hits zero.")
        df_re = pd.DataFrame(st.session_state.get('real_estate_data', []))
        if df_re.empty:
            df_re = pd.DataFrame(
                [{"Property Name": "Primary Home", "Is Primary Residence?": True, "Market Value ($)": 0,
                  "Mortgage Balance ($)": 0, "Interest Rate (%)": 0.0, "Mortgage Payment ($)": 0,
                  "Monthly Expenses ($)": 0, "Monthly Rent ($)": 0, "Override Prop Growth (%)": None,
                  "Override Rent Growth (%)": None}])
        else:
            df_re = df_re.reindex(
                columns=["Property Name", "Is Primary Residence?", "Market Value ($)", "Mortgage Balance ($)",
                         "Interest Rate (%)", "Mortgage Payment ($)", "Monthly Expenses ($)", "Monthly Rent ($)",
                         "Override Prop Growth (%)", "Override Rent Growth (%)"])

        edited_re = st.data_editor(
            df_re,
            column_config={
                "Property Name": st.column_config.TextColumn("Property Name",
                                                             help="A simple label for your property (e.g. 'Beach House' or 'Main St')."),
                "Is Primary Residence?": st.column_config.CheckboxColumn("Primary Home?", default=False),
                "Market Value ($)": st.column_config.NumberColumn("Market Value ($)", step=10000, format="$%d"),
                "Mortgage Balance ($)": st.column_config.NumberColumn("Mortgage Balance ($)", step=10000, format="$%d"),
                "Interest Rate (%)": st.column_config.NumberColumn("Interest Rate (%)", step=0.001, format="%.3f%%"),
                "Mortgage Payment ($)": st.column_config.NumberColumn("Monthly P&I ($)", step=100, format="$%d"),
                "Monthly Expenses ($)": st.column_config.NumberColumn("Taxes/Ins/HOA ($)", step=100, format="$%d"),
                "Monthly Rent ($)": st.column_config.NumberColumn("Monthly Rent ($)", step=100, format="$%d"),
                "Override Prop Growth (%)": st.column_config.NumberColumn("Property Growth (%)", step=0.1,
                                                                          format="%.1f%%"),
                "Override Rent Growth (%)": st.column_config.NumberColumn("Rent Growth (%)", step=0.1, format="%.1f%%")
            }, num_rows="dynamic", width="stretch", hide_index=True, key="re_editor", on_change=mark_dirty
        )
        st.session_state['real_estate_data'] = edited_re.to_dict('records')

        # Validation Warning: Check if mortgage payments cover interest
        for idx, r in edited_re.iterrows():
            bal = safe_num(r.get('Mortgage Balance ($)'))
            rate = safe_num(r.get('Interest Rate (%)'))
            pmt = safe_num(r.get('Mortgage Payment ($)'))
            if bal > 0 and rate > 0 and pmt > 0:
                monthly_interest = (bal * (rate / 100.0)) / 12.0
                if pmt < monthly_interest:
                    st.warning(
                        f"⚠️ Property '{html.escape(str(r.get('Property Name', 'Unknown')))}': Your monthly payment (${pmt:,.0f}) is less than the monthly interest generated (${monthly_interest:,.0f}). This loan balance will grow forever.")

    with tab_biz:
        df_biz = pd.DataFrame(st.session_state.get('business_data', []))
        if df_biz.empty:
            df_biz = pd.DataFrame([{"Business Name": "", "Total Valuation ($)": 0, "Your Ownership (%)": 100,
                                    "Annual Distribution ($)": 0, "Override Val. Growth (%)": None,
                                    "Override Dist. Growth (%)": None}])
        else:
            if "Override Val. Growth (%)" not in df_biz.columns: df_biz["Override Val. Growth (%)"] = None
            if "Override Dist. Growth (%)" not in df_biz.columns: df_biz["Override Dist. Growth (%)"] = None
            df_biz = df_biz.reindex(
                columns=["Business Name", "Total Valuation ($)", "Your Ownership (%)", "Annual Distribution ($)",
                         "Override Val. Growth (%)", "Override Dist. Growth (%)"])

        edited_biz = st.data_editor(
            df_biz,
            column_config={
                "Total Valuation ($)": st.column_config.NumberColumn("Total Value ($)", step=10000, format="$%d"),
                "Annual Distribution ($)": st.column_config.NumberColumn("Annual Income ($)", step=1000, format="$%d"),
                "Your Ownership (%)": st.column_config.NumberColumn("Your Ownership (%)", min_value=0, max_value=100,
                                                                    format="%d%%"),
                "Override Val. Growth (%)": st.column_config.NumberColumn("Value Growth (%)", step=0.1, format="%.1f%%",
                                                                          help="Private assets do not follow portfolio glidepaths. Set a static growth rate."),
                "Override Dist. Growth (%)": st.column_config.NumberColumn("Income Growth (%)", step=0.1,
                                                                           format="%.1f%%")
            }, num_rows="dynamic", width="stretch", hide_index=True, key="biz_editor", on_change=mark_dirty
        )
        st.session_state['business_data'] = edited_biz.to_dict('records')

    with tab_ast:
        info_banner(
            "Contribution Engine Update: Put ONLY your own out-of-pocket contributions here. The AI engine automatically detects 'Employer Matches' from your Income table and securely routes them directly into your 401(k) behind the scenes!")
        df_ast = pd.DataFrame(st.session_state.get('liquid_assets_data', []))
        if df_ast.empty:
            df_ast = pd.DataFrame([{"Account Name": "Primary 401(k)", "Type": "Traditional 401(k)", "Owner": "Me",
                                    "Current Balance ($)": 0, "Annual Contribution ($/yr)": 0,
                                    "Est. Annual Growth (%)": None, "Stop Contrib at Ret.?": True}])
        else:
            if "Annual Contribution ($)" in df_ast.columns: df_ast.rename(
                columns={'Annual Contribution ($)': 'Annual Contribution ($/yr)'}, inplace=True)
            if "Stop Contrib at Ret.?" not in df_ast.columns: df_ast["Stop Contrib at Ret.?"] = True

            df_ast['Type'] = df_ast['Type'].replace(
                {'Traditional 401k/IRA': 'Traditional 401(k)', 'Roth 401k/IRA': 'Roth 401(k)'})
            df_ast = df_ast.reindex(
                columns=["Account Name", "Type", "Owner", "Current Balance ($)", "Annual Contribution ($/yr)",
                         "Est. Annual Growth (%)", "Stop Contrib at Ret.?"])

        edited_ast = st.data_editor(
            df_ast,
            column_config={
                "Type": st.column_config.SelectboxColumn("Account Type",
                                                         options=["Checking/Savings", "HYSA", "Brokerage (Taxable)",
                                                                  "Traditional 401(k)", "Traditional IRA",
                                                                  "Roth 401(k)", "Roth IRA", "HSA", "Crypto",
                                                                  "529 Plan", "Other"]),
                "Owner": st.column_config.SelectboxColumn("Whose Account?", options=["Me", "Spouse", "Joint"]),
                "Current Balance ($)": st.column_config.NumberColumn("Current Balance ($)", step=5000, format="$%d"),
                "Annual Contribution ($/yr)": st.column_config.NumberColumn("Your Contributions ($/yr)", step=1000,
                                                                            format="$%d",
                                                                            help="Include ONLY your out-of-pocket contributions."),
                "Est. Annual Growth (%)": st.column_config.NumberColumn("Custom Return (%)", format="%.1f%%",
                                                                        help="Leave blank to use global market growth assumptions."),
                "Stop Contrib at Ret.?": st.column_config.CheckboxColumn("Stop Adding at Ret.?",
                                                                         help="Check this if you will stop saving into this account once the owner retires.")
            }, num_rows="dynamic", width="stretch", hide_index=True, key="assets_editor", on_change=mark_dirty
        )
        st.session_state['liquid_assets_data'] = edited_ast.to_dict('records')

        # Validation Warning: Check if 401k/IRA contributions wildly exceed normal limits
        for idx, a in edited_ast.iterrows():
            if a.get('Type') in ['Traditional 401(k)', 'Roth 401(k)', 'Traditional IRA', 'Roth IRA']:
                contrib = safe_num(a.get('Annual Contribution ($/yr)'))
                if contrib > 31500:
                    st.warning(
                        f"⚠️ Account '{html.escape(str(a.get('Account Name', 'Unknown')))}': Contribution of ${contrib:,.0f}/yr exceeds standard IRS maximums. The simulation engine will automatically cap these to legal limits.")

    with tab_debt:
        info_banner(
            "Like mortgages, simply provide the balance, rate, and payment. We'll dynamically pay it down to zero.")
        df_debt = pd.DataFrame(st.session_state.get('liabilities_data', []))
        if df_debt.empty:
            df_debt = pd.DataFrame(
                [{"Debt Name": "Auto Loan", "Type": "Auto Loan", "Current Balance ($)": 0, "Interest Rate (%)": 0.0,
                  "Monthly Payment ($)": 0}])
        else:
            df_debt = df_debt.reindex(
                columns=["Debt Name", "Type", "Current Balance ($)", "Interest Rate (%)", "Monthly Payment ($)"])

        edited_debt = st.data_editor(
            df_debt,
            column_config={
                "Current Balance ($)": st.column_config.NumberColumn("Current Balance ($)", step=1000, format="$%d"),
                "Interest Rate (%)": st.column_config.NumberColumn("Interest Rate (%)", step=0.001, format="%.3f%%"),
                "Monthly Payment ($)": st.column_config.NumberColumn("Monthly Payment ($)", step=100, format="$%d")
            }, num_rows="dynamic", width="stretch", hide_index=True, key="debt_editor", on_change=mark_dirty
        )
        st.session_state['liabilities_data'] = edited_debt.to_dict('records')

    re_eq = pd.to_numeric(edited_re['Market Value ($)'], errors='coerce').fillna(0).sum() - pd.to_numeric(
        edited_re['Mortgage Balance ($)'], errors='coerce').fillna(0).sum()
    biz_eq = (pd.to_numeric(edited_biz['Total Valuation ($)'], errors='coerce').fillna(0) * (
                pd.to_numeric(edited_biz['Your Ownership (%)'], errors='coerce').fillna(0) / 100)).sum()
    liq_ast = pd.to_numeric(edited_ast['Current Balance ($)'], errors='coerce').fillna(0).sum()
    total_debt = pd.to_numeric(edited_debt['Current Balance ($)'], errors='coerce').fillna(0).sum()
    net_worth = re_eq + biz_eq + liq_ast - total_debt

    st.divider()
    c_met1, c_met2, c_met3, c_met4 = st.columns(4)
    c_met1.metric("Real Estate Equity", f"${re_eq:,.0f}")
    c_met2.metric("Business Equity", f"${biz_eq:,.0f}")
    c_met3.metric("Liquid Assets", f"${liq_ast:,.0f}")
    c_met4.metric("Other Debt", f"${total_debt:,.0f}")
    st.markdown(
        f"<div style='text-align: center; padding: 15px; margin-top: 15px; background: #eff6ff; border-radius: 8px;'><h3 style='margin:0; color: #1e293b;'>Total Estimated Net Worth: <span style='color: #3b82f6;'>${net_worth:,.0f}</span></h3></div>",
        unsafe_allow_html=True)


def render_cashflows():
    section_header("Lifetime Cash Flows", "Map out budgets and milestones. Do not double-count housing or debt.", "💸")
    info_banner(
        "Healthcare Note: Assume you are covered by employer-sponsored healthcare while working. The engine automatically builds in Pre-Medicare coverage gaps, Medicare premium cliffs at age 65, and IRMAA surcharges.")

    c_loc1, c_loc2 = st.columns(2)
    with c_loc1:
        curr_city_flow = city_autocomplete("Current City", "curr_city_flow",
                                           default_val=st.session_state['curr_city_flow'])
        st.session_state['curr_city_flow'] = curr_city_flow
    with c_loc2:
        ret_city_flow = city_autocomplete("Retirement City (Optional)", "retire_city_flow",
                                          default_val=st.session_state['retire_city_flow'])
        st.session_state['retire_city_flow'] = ret_city_flow

    st.divider()
    df_exp = pd.DataFrame(st.session_state['lifetime_expenses'])
    if df_exp.empty: df_exp = pd.DataFrame(
        [{"Description": "Groceries", "Category": "Food", "Frequency": "Monthly", "Amount ($)": 0, "Start Phase": "Now",
          "Start Year": None, "End Phase": "End of Life", "End Year": None, "AI Estimate?": False}])

    if not df_exp.empty:
        if 'Start Phase' in df_exp.columns and 'Start Year' in df_exp.columns: df_exp.loc[
            df_exp['Start Phase'] != 'Custom Year', 'Start Year'] = None
        if 'End Phase' in df_exp.columns and 'End Year' in df_exp.columns: df_exp.loc[
            df_exp['End Phase'] != 'Custom Year', 'End Year'] = None

    edited_exp = st.data_editor(
        df_exp,
        column_config={
            "Description": st.column_config.TextColumn("Description"),
            "Category": st.column_config.SelectboxColumn("Category", options=BUDGET_CATEGORIES),
            "Frequency": st.column_config.SelectboxColumn("Frequency", options=["Monthly", "Yearly", "One-Time"]),
            "Amount ($)": st.column_config.NumberColumn("Amount ($)", step=100, format="$%d"),
            "Start Phase": st.column_config.SelectboxColumn("Starts", options=["Now", "At Retirement", "Custom Year"]),
            "Start Year": st.column_config.NumberColumn("Start Year (If Custom)", format="%d", min_value=1900,
                                                        max_value=2100),
            "End Phase": st.column_config.SelectboxColumn("Ends",
                                                          options=["End of Life", "At Retirement", "Custom Year"]),
            "End Year": st.column_config.NumberColumn("End Year (If Custom)", format="%d", min_value=1900,
                                                      max_value=2100),
            "AI Estimate?": st.column_config.CheckboxColumn("🤖 AI?")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="exp_ed", on_change=mark_dirty
    )
    st.session_state['lifetime_expenses'] = edited_exp.to_dict('records')

    col_ai_cb, _ = st.columns([3, 1])
    with col_ai_cb:
        if st.button("✨ Auto-Estimate Budget & Milestones for selected locations (AI)", type="primary",
                     use_container_width=True):
            try:
                with st.spinner("Analyzing localized CPI data, timelines, and family needs..."):
                    valid = edited_exp[edited_exp["Description"].astype(str) != ""].copy()
                    locked = valid[valid["AI Estimate?"] == False].to_dict('records')
                    locked_desc = [x['Description'] for x in locked]

                    current_year = datetime.date.today().year
                    my_age = relativedelta(datetime.date.today(), st.session_state['my_dob']).years
                    spouse_age = relativedelta(datetime.date.today(), st.session_state['spouse_dob']).years if \
                    st.session_state['has_spouse'] else 0
                    k_ctx_list = [f"{k['name']}:{k['age']}" for k in st.session_state['kids_data']]
                    k_ctx_str = ", ".join(k_ctx_list)
                    f_ctx = f"User({my_age})" + (
                        f", Spouse({st.session_state['spouse_name']}:{spouse_age})" if st.session_state[
                            'has_spouse'] else "") + f", Dependents({k_ctx_str})"

                    df_inc = pd.DataFrame(st.session_state['income_data'])
                    curr_inc_total = pd.to_numeric(df_inc['Annual Amount ($)'], errors='coerce').fillna(
                        0).sum() if not df_inc.empty else 0
                    df_ast = pd.DataFrame(st.session_state['liquid_assets_data'])
                    liq_ast_total = pd.to_numeric(df_ast['Current Balance ($)'], errors='coerce').fillna(
                        0).sum() if not df_ast.empty else 0

                    df_re = pd.DataFrame(st.session_state['real_estate_data'])
                    primary_re = df_re[df_re[
                                           "Is Primary Residence?"] == True] if not df_re.empty and "Is Primary Residence?" in df_re.columns else pd.DataFrame()
                    h_pmt = pd.to_numeric(primary_re["Mortgage Payment ($)"], errors='coerce').fillna(
                        0).sum() if not primary_re.empty else 0
                    h_exp = pd.to_numeric(primary_re["Monthly Expenses ($)"], errors='coerce').fillna(
                        0).sum() if not primary_re.empty else 0
                    owns_home = not primary_re.empty

                    curr_city_flow_clean = re.sub(r'[^a-zA-Z0-9, ]', '', str(curr_city_flow))[:100]
                    ret_city_flow_clean = re.sub(r'[^a-zA-Z0-9, ]', '', str(ret_city_flow))[:100]

                    if owns_home:
                        ai_exclusion = "STRICT RULE: DO NOT INCLUDE Housing, Rent, Mortgages, Auto Loans, or Debt Payments in this list. They are explicitly tracked via balance sheet parameters."
                    else:
                        ai_exclusion = "STRICT RULE: DO NOT INCLUDE Mortgages, Auto Loans, or Debt Payments. HOWEVER, YOU MUST INCLUDE a realistic 'Housing / Rent' expense reflecting current local market rates."

                    wealth_ctx = f"The household has a current annual pre-tax income of ${curr_inc_total:,.0f} and liquid assets totaling ${liq_ast_total:,.0f}. VERY IMPORTANT: While you should scale the budget to reflect this wealth, assume these users are savvy spenders and aggressive savers (comfortable but smart with money), so avoid over-inflating lifestyle costs unnecessarily."
                    allowed_cats = ", ".join(BUDGET_CATEGORIES)
                    prompt = f"Current City: {curr_city_flow_clean}. Planned Retirement City: {ret_city_flow_clean}. Family: {f_ctx}. Current Year is {current_year}. {wealth_ctx} Generate a comprehensive list of missing living expenses AND expected future life milestones (like college or weddings). {ai_exclusion} CRITICAL INSTRUCTIONS: 1) Medical expenses (IRMAA, Medicare Cliff, Pre-Medicare gap, LTC) are handled automatically by the simulation engine; only provide modest baseline out-of-pocket healthcare costs. 2) Model 'Empty Nesting': phase out child-heavy groceries, utility expenses, and ANY K-12 extracurriculars/lessons using 'Custom Year' End Phases exactly when the youngest child turns 18. 3) ALL College/University expenses MUST be categorized strictly as 'Education' (not 'Other') so they receive the 5% education inflation penalty. NOTE: Start and End Years are INCLUSIVE. For a standard 4-year college, the End Year must be exactly 3 years after the Start Year (e.g., Start 2032, End 2035 is 4 years). 4) Model Retirement Lifestyle Phases: split travel and entertainment into 'Go-Go Years' (high spend, starts at retirement, lasts 10 years, calculate costs based on {ret_city_flow_clean}), 'Slow-Go Years' (medium spend, lasts next 10 years), and 'No-Go Years' (low spend) using 'Custom Year' Start/End phases. 5) STRICT PHASE SHIFTING: Never overlap the same living expense category. If an expense changes at retirement, the 'Now' version MUST have 'End Phase' set to 'At Retirement', and the new version MUST have 'Start Phase' set to 'At Retirement'. If an expense continues unchanged forever, set it to 'Now' until 'End of Life'. Skip these items as they are already accounted for: {json.dumps(locked_desc)}. Return ONLY a JSON array of objects with keys: 'Description', 'Category' (MUST be exactly one of: {allowed_cats}. If unsure, default to 'Other'), 'Frequency' (Monthly/Yearly/One-Time), 'Amount ($)' (number), 'Start Phase' (Now/At Retirement/Custom Year), 'Start Year' (integer, ONLY if 'Start Phase' is 'Custom Year', otherwise null), 'End Phase' (End of Life/At Retirement/Custom Year), 'End Year' (integer, ONLY if 'End Phase' is 'Custom Year', otherwise null), and 'AI Estimate?' (true)."
                    res = call_gemini_json(prompt)
                    if res and isinstance(res, list) and len(res) > 0:
                        st.session_state['lifetime_expenses'] = locked + res
                        mark_dirty()
                        st.rerun()
            except Exception as e:
                st.error(f"Failed to generate AI budget: {e}")


def render_simulation():
    section_header("📈 Simulation", "Fine-tune your timeline and run Monte Carlo scenarios.")

    my_age = relativedelta(datetime.date.today(), st.session_state['my_dob']).years
    spouse_age = relativedelta(datetime.date.today(), st.session_state['spouse_dob']).years if st.session_state[
        'has_spouse'] else 0

    cc1, cc2, cc3, cc4 = st.columns(4)
    ret_age = cc1.slider("Retirement Age", max(int(my_age), 1), 100, max(int(my_age), int(st.session_state['ret_age'])),
                         key="sld_ret_age")
    s_ret_age = cc2.slider("Spouse Retire Age", max(int(spouse_age), 1), 100,
                           max(int(spouse_age), int(st.session_state['s_ret_age'])), key="sld_s_ret_age") if \
    st.session_state['has_spouse'] else 65
    my_life_exp = cc3.slider("Your Life Expectancy", max(70, ret_age), 115,
                             max(ret_age, int(st.session_state['my_life_exp'])), key="sld_life_exp")
    spouse_life_exp = cc4.slider("Spouse Life Expectancy", max(70, s_ret_age), 115,
                                 max(s_ret_age, int(st.session_state['spouse_life_exp'])), key="sld_s_life_exp") if \
    st.session_state['has_spouse'] else 0

    if ret_age < my_age: info_banner("Retirement age cannot be lower than current age.", "warning")
    if my_life_exp < ret_age: info_banner("Life expectancy cannot be lower than retirement age.", "warning")

    if st.session_state.get('ret_age') != ret_age: update_state('ret_age', ret_age)
    if st.session_state.get('s_ret_age') != s_ret_age: update_state('s_ret_age', s_ret_age)
    if st.session_state.get('my_life_exp') != my_life_exp: update_state('my_life_exp', my_life_exp)
    if st.session_state.get('spouse_life_exp') != spouse_life_exp: update_state('spouse_life_exp', spouse_life_exp)

    st.markdown(
        """<div class='card' style='margin-bottom: 24px;'><h3 style='margin-top:0;'>Macroeconomic Assumptions</h3>""",
        unsafe_allow_html=True)

    def ai_number_input(label, state_key, prompt, col):
        with col:
            sub_c1, sub_c2 = st.columns([5, 2])
            widget_key = f"in_{state_key}"
            input_placeholder = sub_c1.empty()

            sub_c2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if sub_c2.button("✨ AI", key=f"btn_{state_key}", help=f"AI Estimate for {label}", type="primary",
                             use_container_width=True):
                try:
                    with st.spinner("AI estimating..."):
                        enhanced_prompt = prompt + " CRITICAL INSTRUCTION: You MUST return the value as a percentage number between 0 and 100 (e.g., return 5.5 for 5.5%, DO NOT return 0.055)."
                        res = call_gemini_json(enhanced_prompt)
                        if res and state_key in res:
                            new_val = float(res[state_key])
                            if 0 < new_val < 0.30: new_val *= 100.0
                            new_assumptions = st.session_state['assumptions'].copy()
                            new_assumptions[state_key] = new_val
                            st.session_state['assumptions'] = new_assumptions
                            mark_dirty()
                            st.rerun()
                except Exception as e:
                    st.error(f"Failed to generate estimate: {e}")

            val = input_placeholder.number_input(label, step=0.1, key=widget_key,
                                                 value=float(st.session_state['assumptions'].get(state_key, 0.0)))
            if val != st.session_state['assumptions'].get(state_key):
                new_assumptions = st.session_state['assumptions'].copy()
                new_assumptions[state_key] = val
                st.session_state['assumptions'] = new_assumptions
                mark_dirty()
            return val

    ac1, ac2, ac3 = st.columns(3)
    mkt = ai_number_input("Market Growth (%)", 'market_growth',
                          f"What is a realistic conservative long-term annual market growth rate for a diversified retirement portfolio? Return JSON: {{'market_growth': float}}",
                          ac1)
    infl = ai_number_input("General CPI Inflation (%)", 'inflation',
                           f"What is the projected long-term average general US CPI inflation rate? Return JSON: {{'inflation': float}}",
                           ac2)
    inc_g = ai_number_input("Income Growth (%)", 'income_growth',
                            f"What is a realistic annual salary growth/merit increase rate? Return JSON: {{'income_growth': float}}",
                            ac3)

    ac4, ac5, ac6 = st.columns(3)
    curr_city_flow = st.session_state.get('curr_city_flow', '')
    curr_city_flow_clean = re.sub(r'[^a-zA-Z0-9, ]', '', str(curr_city_flow))[:100]
    infl_hc = ai_number_input("Healthcare Inflation (%)", 'inflation_healthcare',
                              f"What is the projected long-term annual healthcare cost inflation rate in the US? Return JSON: {{'inflation_healthcare': float}}",
                              ac4)
    infl_ed = ai_number_input("Education Inflation (%)", 'inflation_education',
                              f"What is the projected long-term annual college tuition inflation rate in the US? Return JSON: {{'inflation_education': float}}",
                              ac5)
    prop_g = ai_number_input("Property Growth (%)", 'property_growth',
                             f"Historical average annual real estate appreciation rate for {curr_city_flow_clean}? Return JSON: {{'property_growth': float}}",
                             ac6)

    ac7, ac8, ac9 = st.columns(3)
    ret_city_flow = st.session_state.get('retire_city_flow', '')
    ret_city_flow_clean = re.sub(r'[^a-zA-Z0-9, ]', '', str(ret_city_flow))[:100]
    curr_inc_total = pd.to_numeric(pd.DataFrame(st.session_state['income_data'])['Annual Amount ($)'],
                                   errors='coerce').fillna(0).sum() if st.session_state['income_data'] else 0
    rent_g = ai_number_input("Rent Growth (%)", 'rent_growth',
                             f"Projected average annual rent increase rate for {curr_city_flow_clean}? Return JSON: {{'rent_growth': float}}",
                             ac7)
    cur_t = ai_number_input("Current State Tax (%)", 'current_tax_rate',
                            f"User lives in {curr_city_flow_clean} with ${curr_inc_total:,.0f} income. Suggest effective STATE/LOCAL income tax rate ONLY. Return JSON: {{'current_tax_rate': float}}",
                            ac8)
    ret_t = ai_number_input("Retire State Tax (%)", 'retire_tax_rate',
                            f"User plans to retire in {ret_city_flow_clean} with estimated retirement income. Suggest effective STATE/LOCAL income tax rate ONLY. Return JSON: {{'retire_tax_rate': float}}",
                            ac9)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """<div class='card' style='margin-bottom: 24px;'><h3 style='margin-top:0;'>Tax Engine & Stress Tests</h3>""",
        unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)

    def update_asm_toggle(key, val):
        if st.session_state['assumptions'].get(key) != val:
            new_asm = st.session_state['assumptions'].copy()
            new_asm[key] = val
            st.session_state['assumptions'] = new_asm
            mark_dirty()

    with sc1:
        medicare_gap = st.toggle("🏥 Model Pre-Medicare Gap",
                                 value=st.session_state['assumptions'].get('medicare_gap', True))
        update_asm_toggle('medicare_gap', medicare_gap)
        medicare_cliff = st.toggle("🏥 Apply Medicare Cliff (Drop Healthcare at 65)",
                                   value=st.session_state['assumptions'].get('medicare_cliff', True))
        update_asm_toggle('medicare_cliff', medicare_cliff)
        glidepath = st.toggle("📉 Apply Investment Glidepath",
                              value=st.session_state['assumptions'].get('glidepath', True))
        update_asm_toggle('glidepath', glidepath)
        stress_test = st.toggle("📉 Apply -25% Market Crash at Retirement",
                                value=st.session_state['assumptions'].get('stress_test', False))
        update_asm_toggle('stress_test', stress_test)
        ltc_shock = st.toggle("🛏️ Long-Term Care (LTC) Shock",
                              value=st.session_state['assumptions'].get('ltc_shock', False))
        update_asm_toggle('ltc_shock', ltc_shock)

    with sc2:
        active_withdrawal_strategy = st.selectbox("Shortfall Withdrawal Sequence",
                                                  options=["Standard (Taxable -> 401k -> Roth)",
                                                           "Roth Preferred (Taxable -> Roth -> 401k)"],
                                                  index=0 if "Standard" in st.session_state['assumptions'].get(
                                                      'withdrawal_strategy', 'Standard') else 1)
        roth_conversions = st.toggle("🔄 Enable Roth Conversion Optimizer",
                                     value=st.session_state['assumptions'].get('roth_conversions', False))
        roth_target_idx = ["12%", "22%", "24%", "32%"].index(st.session_state['assumptions'].get('roth_target', "24%"))
        roth_target = st.selectbox("Target Bracket to Fill", options=["12%", "22%", "24%", "32%"],
                                   index=roth_target_idx)
        update_asm_toggle('roth_conversions', roth_conversions)
        update_asm_toggle('roth_target', roth_target)
        update_asm_toggle('withdrawal_strategy', active_withdrawal_strategy.split(' ')[0])

    st.divider()
    view_todays_dollars = st.toggle("💵 View Charts in Today's Dollars", value=True,
                                    help="Removes the effect of inflation so you can easily understand what these big future numbers feel like today.")
    st.session_state['view_todays_dollars'] = view_todays_dollars

    sim_ctx = build_sim_context()
    if sim_ctx['my_age'] <= 0:
        st.warning("Please enter a valid Date of Birth in the Profile section to run the simulation.")
    elif sim_ctx['max_years'] <= 0:
        st.warning("Your Life Expectancy must be greater than your Current Age to run the simulation.")
    else:
        mkt_seq = tuple([sim_ctx['mkt']] * (sim_ctx['max_years'] + 1))
        ctx_json_str = json.dumps(sim_ctx, sort_keys=True)

        with st.spinner("Running high-precision simulation engine..."):
            df_sim_nominal, df_det_nominal, df_nw_nominal, run_milestones = run_cached_simulation(mkt_seq, ctx_json_str,
                                                                                                  st.session_state.get(
                                                                                                      'user_email',
                                                                                                      'guest'))

        if not df_sim_nominal.empty:
            df_sim, df_det, df_nw = df_sim_nominal.copy(), df_det_nominal.copy(), df_nw_nominal.copy()
            st.session_state['df_sim_nominal'], st.session_state['df_det'], st.session_state[
                'df_nw'] = df_sim_nominal, df_det_nominal, df_nw_nominal

            final_nw = df_sim.iloc[-1]['Net Worth']
            shortfall_mask = df_sim['Unfunded Debt'] > 0
            deplete_year = df_sim[shortfall_mask]['Year'].min() if not df_sim[shortfall_mask].empty else None
            deplete_age = df_sim[shortfall_mask]['Age (Primary)'].min() if not df_sim[shortfall_mask].empty else None

            c_status, c_ai_btn = st.columns([3, 2])
            with c_status:
                if deplete_year is not None:
                    st.error(
                        f"🔴 **Liquidity Crisis:** You completely exhaust your liquid cash in **Year {int(deplete_year)}** (Age {int(deplete_age)}) and begin accumulating high-interest shortfall debt.")
                elif final_nw >= 1000000:
                    st.success(
                        f"🟢 **On Track:** Projected Net Worth at timeline end is **${final_nw:,.0f}**. Your assets comfortably outlive your life expectancy.")
                elif final_nw > 0:
                    st.warning(
                        f"🟡 **Caution:** Projected Net Worth at timeline end is **${final_nw:,.0f}**. You are solvent, but with a narrow margin of safety.")

            if view_todays_dollars:
                current_year = datetime.date.today().year
                discounts = (1 + sim_ctx['infl'] / 100) ** (df_sim['Year'] - current_year)
                cols_sim = ["Annual Income", "Annual Expenses", "Annual Taxes", "Annual Net Savings", "Liquid Assets",
                            "Real Estate Equity", "Business Equity", "Debt", "Unfunded Debt", "Net Worth"]
                df_sim[cols_sim] = df_sim[cols_sim].div(discounts, axis=0)
                cols_det = [c for c in df_det.columns if
                            c not in ["Age (Primary)", "Age (Spouse)", "Year"] and pd.api.types.is_numeric_dtype(
                                df_det[c])]
                df_det[cols_det] = df_det[cols_det].div(discounts, axis=0)
                cols_nw = [c for c in df_nw.columns if
                           c not in ["Age (Primary)", "Age (Spouse)", "Year"] and pd.api.types.is_numeric_dtype(
                               df_nw[c])]
                df_nw[cols_nw] = df_nw[cols_nw].div(discounts, axis=0)

            st.session_state['df_sim_display'] = df_sim

            if HAS_PLOTLY:
                current_year = datetime.date.today().year
                m_x_normal, m_y_normal, m_text_normal, m_x_system, m_y_system, m_text_system, m_x_alert, m_y_alert, m_text_alert = [], [], [], [], [], [], [], [], []

                if run_milestones:
                    m_years = sorted(list(run_milestones.keys()))
                    for y in m_years:
                        row = df_sim[df_sim['Year'] == y]
                        nw_val = row['Net Worth'].values[0] if not row.empty else 0
                        events = run_milestones[y]
                        normals, systems, alerts = [e for e in events if e.get('type') == 'normal'], [e for e in events
                                                                                                      if e.get(
                                'type') == 'system'], [e for e in events if e.get('type') == 'critical']
                        discount = (1 + sim_ctx['infl'] / 100) ** (y - current_year) if view_todays_dollars else 1.0

                        if normals:
                            m_x_normal.append(y);
                            m_y_normal.append(nw_val);
                            m_text_normal.append(f"<b>Year {y}:</b><br>" + "<br>".join(
                                [f"• {html.escape(m['desc'])} (${m['amt'] / discount:,.0f})" for m in normals]))
                        if systems:
                            m_x_system.append(y);
                            m_y_system.append(nw_val);
                            m_text_system.append(f"<b>System Event ({y}):</b><br>" + "<br>".join(
                                [f"• {html.escape(m['desc'])}" for m in systems]))
                        if alerts:
                            m_x_alert.append(y);
                            m_y_alert.append(nw_val);
                            m_text_alert.append(f"<b>⚠️ ALERT ({y}):</b><br>" + "<br>".join(
                                [f"• {html.escape(m['desc'])}" for m in alerts]))

                st.write("#### Net Worth Composition (Smart Asset Drawdown)")
                fig_nw = go.Figure()
                ast_cols = [c for c in df_nw.columns if c.startswith("Asset: ")]
                fill_colors = ['rgba(45, 212, 191, 0.6)', 'rgba(56, 189, 248, 0.6)', 'rgba(129, 140, 248, 0.6)',
                               'rgba(167, 139, 250, 0.6)', 'rgba(232, 121, 249, 0.6)', 'rgba(251, 113, 133, 0.6)',
                               'rgba(52, 211, 153, 0.6)', 'rgba(251, 191, 36, 0.6)', 'rgba(163, 230, 53, 0.6)',
                               'rgba(250, 204, 21, 0.6)']
                line_colors = ['#2dd4bf', '#38bdf8', '#818cf8', '#a78bfa', '#e879f9', '#fb7185', '#34d399', '#fbbf24',
                               '#a3e635', '#facc15']

                for i, col in enumerate(ast_cols):
                    fig_nw.add_trace(go.Scatter(x=df_nw["Year"], y=df_nw[col], mode='lines', stackgroup='one',
                                                name=col.replace("Asset: ", ""),
                                                fillcolor=fill_colors[i % len(fill_colors)],
                                                line=dict(color=line_colors[i % len(line_colors)], width=1.5)))

                fig_nw.add_trace(
                    go.Scatter(x=df_nw["Year"], y=df_nw["Total Real Estate Equity"], mode='lines', stackgroup='one',
                               name='Real Estate Equity', fillcolor='rgba(139, 92, 246, 0.5)',
                               line=dict(color='#8b5cf6', width=1.5)))
                fig_nw.add_trace(
                    go.Scatter(x=df_nw["Year"], y=df_nw["Total Business Equity"], mode='lines', stackgroup='one',
                               name='Business Equity', fillcolor='rgba(245, 158, 11, 0.5)',
                               line=dict(color='#f59e0b', width=1.5)))
                fig_nw.add_trace(
                    go.Scatter(x=df_nw["Year"], y=df_nw["Total Debt Liabilities"], mode='lines', stackgroup='two',
                               name='Total Liabilities (Inc. Shortfalls)', fillcolor='rgba(244, 63, 94, 0.5)',
                               line=dict(color='#f43f5e', width=1.5)))
                fig_nw.add_trace(
                    go.Scatter(x=df_nw["Year"], y=df_nw["Total Net Worth"], mode='lines', name='Total Net Worth',
                               line=dict(color='#111827', width=3, dash='dot')))

                if m_x_normal: fig_nw.add_trace(go.Scatter(x=m_x_normal, y=m_y_normal, mode='markers',
                                                           marker=dict(symbol='star', size=14, color='#eab308',
                                                                       line=dict(width=1.5, color='white')),
                                                           name='User Milestones', hoverinfo='text',
                                                           text=m_text_normal))
                if m_x_system: fig_nw.add_trace(go.Scatter(x=m_x_system, y=m_y_system, mode='markers',
                                                           marker=dict(symbol='star', size=14, color='#3b82f6',
                                                                       line=dict(width=1.5, color='white')),
                                                           name='System Events', hoverinfo='text', text=m_text_system))
                if m_x_alert: fig_nw.add_trace(go.Scatter(x=m_x_alert, y=m_y_alert, mode='markers',
                                                          marker=dict(symbol='star', size=18, color='#ef4444',
                                                                      line=dict(width=2, color='white')),
                                                          name='Critical Alerts', hoverinfo='text', text=m_text_alert))

                fig_nw = apply_chart_theme(fig_nw)
                st.plotly_chart(fig_nw, use_container_width=True)

                st.write("#### Annual Cash Flow & Progressive Taxes")
                fig_cf = go.Figure()
                fig_cf.add_trace(
                    go.Scatter(x=df_sim["Year"], y=df_sim["Annual Income"], mode='lines', name='Organic Income',
                               line=dict(color='#4f46e5', width=3)))
                fig_cf.add_trace(
                    go.Scatter(x=df_sim["Year"], y=df_sim["Annual Expenses"], mode='lines', name='Expenses',
                               line=dict(color='#f43f5e', width=3)))
                fig_cf.add_trace(go.Scatter(x=df_sim["Year"], y=df_sim["Annual Taxes"], mode='lines', name='Taxes',
                                            line=dict(color='#f59e0b', width=3)))
                fig_cf.add_trace(
                    go.Scatter(x=df_sim["Year"], y=df_sim["Annual Net Savings"], mode='lines', name='Net Cashflow',
                               line=dict(color='#10b981', width=3, dash='dot')))

                if m_x_normal: fig_cf.add_trace(go.Scatter(x=m_x_normal, y=[0] * len(m_x_normal), mode='markers',
                                                           marker=dict(symbol='star', size=14, color='#eab308',
                                                                       line=dict(width=1.5, color='white')),
                                                           name='User Milestones', hoverinfo='text',
                                                           text=m_text_normal))
                if m_x_system: fig_cf.add_trace(go.Scatter(x=m_x_system, y=[0] * len(m_x_system), mode='markers',
                                                           marker=dict(symbol='star', size=14, color='#3b82f6',
                                                                       line=dict(width=1.5, color='white')),
                                                           name='System Events', hoverinfo='text', text=m_text_system))
                if m_x_alert: fig_cf.add_trace(go.Scatter(x=m_x_alert, y=[0] * len(m_x_alert), mode='markers',
                                                          marker=dict(symbol='star', size=18, color='#ef4444',
                                                                      line=dict(width=2, color='white')),
                                                          name='Critical Alerts', hoverinfo='text', text=m_text_alert))

                fig_cf = apply_chart_theme(fig_cf)
                st.plotly_chart(fig_cf, use_container_width=True)

            st.divider()
            st.subheader("🎲 Monte Carlo Risk Analysis")
            st.markdown(
                '<div class="info-text">💡 <strong>Stress Test Your Plan:</strong> The Monte Carlo simulation runs your exact plan through hundreds of randomized market scenarios (based on historical volatility) to find your true probability of success.</div>',
                unsafe_allow_html=True)

            col_mc1, col_mc2, col_mc3 = st.columns([1, 1, 2])
            mc_vol = col_mc1.number_input("Portfolio Volatility (%)", value=15.0,
                                          help="Historically, the S&P 500 maintains a volatility (standard deviation) proximal to 15%.")
            mc_runs = col_mc2.number_input("Number of Simulations", min_value=10, max_value=500, value=100, step=10)

            with col_mc3:
                st.markdown("<div style='height: 27px;'></div>", unsafe_allow_html=True)
                if st.button("✨ Run Monte Carlo Simulation", type="primary", use_container_width=True):
                    with st.spinner(f"Rendering {mc_runs} parallel market sequences (Multi-threaded)..."):
                        success_count = 0
                        all_nw_paths = []
                        mc_progress = st.progress(0)

                        random_sequences = [
                            [random.gauss(sim_ctx['mkt'], mc_vol) for _ in range(sim_ctx['max_years'] + 1)] for _ in
                            range(mc_runs)]

                        try:
                            with ThreadPoolExecutor(max_workers=min(mc_runs, 8)) as executor:
                                futures = [executor.submit(run_simulation, seq, sim_ctx) for seq in random_sequences]

                                for i, future in enumerate(futures):
                                    res, _, _, _ = future.result()
                                    if res:
                                        nw_path = [step["Net Worth"] for step in res]
                                        all_nw_paths.append(nw_path)
                                        if res[-1].get("Unfunded Debt", 0) <= 0: success_count += 1
                                    if i % max(1, mc_runs // 20) == 0: mc_progress.progress(min(1.0, (i + 1) / mc_runs))
                        except Exception as e:
                            st.error(f"Simulation failed during multi-threading: {e}")
                        finally:
                            mc_progress.empty()

                        if all_nw_paths:
                            success_rate = (success_count / len(all_nw_paths)) * 100
                            st.session_state['mc_success_rate'] = success_rate

                            path_len = len(all_nw_paths[0])
                            current_year = datetime.date.today().year
                            years_list = [sim_ctx['current_year'] + i for i in range(path_len)]
                            p10, p50, p90 = [], [], []

                            for i in range(path_len):
                                step_vals = sorted([path[i] for path in all_nw_paths])
                                discount = (1 + sim_ctx['infl'] / 100) ** i if view_todays_dollars else 1.0
                                p10.append(step_vals[int(len(all_nw_paths) * 0.10)] / discount)
                                p50.append(step_vals[int(len(all_nw_paths) * 0.50)] / discount)
                                p90.append(step_vals[int(len(all_nw_paths) * 0.90)] / discount)

                            st.markdown(
                                f"<h3 style='text-align: center; color: {'#10b981' if success_rate > 80 else '#f59e0b' if success_rate > 50 else '#f43f5e'};'>Probability of Success: {success_rate:.1f}%</h3>",
                                unsafe_allow_html=True)

                            if HAS_PLOTLY:
                                fig_mc = go.Figure()
                                fig_mc.add_trace(go.Scatter(x=years_list, y=p90, mode='lines',
                                                            name='90th Percentile (Favorable Timeline)',
                                                            line=dict(color='#10b981', dash='dot')))
                                fig_mc.add_trace(go.Scatter(x=years_list, y=p50, mode='lines',
                                                            name='50th Percentile (Median Expectation)',
                                                            line=dict(color='#3b82f6', width=3)))
                                fig_mc.add_trace(go.Scatter(x=years_list, y=p10, mode='lines',
                                                            name='10th Percentile (Severe Contraction)',
                                                            line=dict(color='#f43f5e', dash='dot')))
                                fig_mc = apply_chart_theme(fig_mc, "Stochastic Net Worth Projections")
                                st.plotly_chart(fig_mc, use_container_width=True)

            st.divider()
            csv = df_sim_nominal.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download Full Simulation (.csv)", data=csv,
                               file_name='retirement_simulation.csv', mime='text/csv')

            t1, t2 = st.tabs(["Income & Expense Log", "Net Worth Log"])
            with t1:
                st.subheader("Detailed Tax & Expense Log")
                inc_c = sorted([c for c in df_det.columns if
                                c.startswith("Income:") or c.startswith("Roth") or c.startswith("Cashflow:")])
                exp_c = sorted([c for c in df_det.columns if c.startswith("Expense:")])
                ord_det = ["Year", "Age (Primary)", "Age (Spouse)"] + inc_c + exp_c + ["Net Savings"]
                st.dataframe(df_det[ord_det].set_index("Year").style.format(
                    {c: "${:,.0f}" for c in ord_det if c not in ["Age (Primary)", "Age (Spouse)", "Year"]} | {
                        "Age (Primary)": "{:.0f}", "Age (Spouse)": "{:.0f}"}), use_container_width=True)
            with t2:
                st.subheader("Detailed Net Worth Log")
                ast_c = sorted([c for c in df_nw.columns if c.startswith("Asset:")])
                ord_nw = ["Year", "Age (Primary)", "Age (Spouse)"] + ast_c + ["Total Liquid Assets",
                                                                              "Total Real Estate Equity",
                                                                              "Total Business Equity",
                                                                              "Total Debt Liabilities",
                                                                              "Total Net Worth"]
                st.dataframe(df_nw[ord_nw].set_index("Year").style.format(
                    {c: "${:,.0f}" for c in ord_nw if c not in ["Age (Primary)", "Age (Spouse)", "Year"]} | {
                        "Age (Primary)": "{:.0f}", "Age (Spouse)": "{:.0f}"}), use_container_width=True)


def render_ai():
    section_header("AI Fiduciary Health & What-If Simulator",
                   "Analyze your cash flows chronologically to provide tactical, phase-by-phase advice.", "🤖")

    df_sim = st.session_state.get('df_sim_display')
    if df_sim is not None and not df_sim.empty:
        shortfall_mask = df_sim['Unfunded Debt'] > 0
        deplete_year = df_sim[shortfall_mask]['Year'].min() if not df_sim[shortfall_mask].empty else None
        my_age = relativedelta(datetime.date.today(), st.session_state['my_dob']).years

        sim_summary = {
            "Current Age": my_age, "Retirement Age": st.session_state['ret_age'],
            "Life Expectancy": st.session_state['my_life_exp'],
            "Current Net Worth": df_sim.iloc[0]['Net Worth'], "Final Net Worth": df_sim.iloc[-1]['Net Worth'],
            "Shortfall Year": str(deplete_year) if deplete_year is not None else "None"
        }

        timeline_summary = []
        for idx, row in df_sim.iloc[::5].iterrows():
            timeline_summary.append({
                "Age": int(row["Age (Primary)"]), "Income": int(row["Annual Income"]),
                "Expenses": int(row["Annual Expenses"]), "Taxes": int(row["Annual Taxes"]),
                "Liquid_Assets": int(row["Liquid Assets"]), "Net_Worth": int(row["Net Worth"])
            })
        timeline_summary.append(
            {"Age": int(df_sim.iloc[-1]["Age (Primary)"]), "Income": int(df_sim.iloc[-1]["Annual Income"]),
             "Expenses": int(df_sim.iloc[-1]["Annual Expenses"]), "Taxes": int(df_sim.iloc[-1]["Annual Taxes"]),
             "Liquid_Assets": int(df_sim.iloc[-1]["Liquid Assets"]), "Net_Worth": int(df_sim.iloc[-1]["Net Worth"])})
    else:
        sim_summary, timeline_summary = {}, []

    tab_report, tab_whatif = st.tabs(["📊 Comprehensive Health Report", "🔮 What-If Simulator"])
    with tab_report:
        if st.button("✨ Generate Comprehensive AI Report", type="primary", use_container_width=True, key="btn_report"):
            if sim_summary:
                try:
                    with st.spinner("AI extracting timeseries data and acting as fiduciary advisor..."):
                        prompt = f"Act as an expert fiduciary financial planner. Review this user's summary: {json.dumps(sim_summary)} and their chronological 5-year cash flow progression: {json.dumps(timeline_summary)}. Provide a highly detailed, year-by-year or phase-by-phase tactical analysis. Focus on specific strategies they can use to optimize their tax buckets (e.g., when exactly to execute Roth conversions before RMDs begin), sequence of withdrawals, and managing the gaps between retirement and Social Security/Medicare. Return ONLY valid JSON exactly like this: {{\"analysis\": \"your detailed markdown text here, using \\n for line breaks\"}}"
                        res = call_gemini_json(prompt)
                        if res and 'analysis' in res:
                            st.session_state['ai_analysis_report'] = res['analysis']
                        else:
                            st.error("⚠️ AI Analysis failed to generate.")
                finally:
                    st.rerun()
            else:
                st.warning("Please run the baseline simulation first on the Dashboard or Simulation tab.")

        if 'ai_analysis_report' in st.session_state:
            st.info(st.session_state['ai_analysis_report'].replace('\\n', '\n').replace('$', r'\$'))

    with tab_whatif:
        what_if_query = st.text_area(
            "Ask the AI to simulate a scenario (e.g., 'What if I sold my rental property in 2030 and put the cash in my brokerage?' or 'What if I added $50k in income starting in 2029?')",
            key="what_if_text")
        if st.button("✨ Run What-If Analysis (AI)", type="primary", use_container_width=True, key="btn_whatif"):
            if sim_summary and what_if_query:
                try:
                    with st.spinner("AI processing alternative timelines and computing what-if scenario..."):
                        prompt = f"Act as an expert fiduciary financial planner. Review this user's baseline simulation summary: {json.dumps(sim_summary)} and their chronological 5-year cash flow progression: {json.dumps(timeline_summary)}. The user wants to run the following 'what-if' scenario: '{what_if_query}'. Analyze how this change would mathematically and strategically impact their net worth, cash flow, and tax strategy compared to the baseline. Provide a highly detailed, reasonable estimate and tactical breakdown of this scenario. Return ONLY valid JSON exactly like this: {{\"analysis\": \"your detailed markdown text here, using \\n for line breaks\"}}"
                        res = call_gemini_json(prompt)
                        if res and 'analysis' in res:
                            st.session_state['what_if_analysis_report'] = res['analysis']
                        else:
                            st.error("⚠️ AI Analysis failed to generate.")
                finally:
                    st.rerun()
            elif not what_if_query:
                st.warning("Please enter a scenario to simulate.")
            else:
                st.warning("Please run the baseline simulation first.")

        if 'what_if_analysis_report' in st.session_state:
            st.success(st.session_state['what_if_analysis_report'].replace('\\n', '\n').replace('$', r'\$'))


def render_faq():
    section_header("Complete Beginner's Guide & FAQ", "Everything you need to know about the engine.", "📖")
    st.markdown("""
### FAQ Placeholder
*(Paste your FAQ content here)*
    """)


# --- PAGE ROUTING & EXECUTION ---
PAGES = {
    "🏠 Dashboard": render_dashboard,
    "👤 Profile & Family": render_profile,
    "💵 Income Streams": render_income,
    "🏦 Assets & Debts": render_assets,
    "💸 Cash Flows": render_cashflows,
    "📈 Simulation": render_simulation,
    "🤖 AI Advisor": render_ai,
    "📖 User Guide & FAQ": render_faq
}

with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: white;'>🏦 Pro Planner</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    current_page = st.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")
    st.session_state['current_page'] = current_page

    st.markdown("<br>", unsafe_allow_html=True)
    completed = get_completion_score()
    st.progress(completed / 100)
    st.caption(f"<div style='text-align: center;'>Profile {completed}% Complete</div>", unsafe_allow_html=True)

    if 'df_sim' in st.session_state and not st.session_state['df_sim'].empty:
        nw = st.session_state['df_sim'].iloc[0]['Net Worth']
        st.markdown(
            f"<div style='text-align: center; margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.1); border-radius: 8px;'><span style='font-size: 0.8rem; color: #cbd5e1;'>Live Net Worth</span><br><b style='font-size: 1.2rem;'>${nw:,.0f}</b></div>",
            unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    save_btn_label = "⚠️ Save Changes" if st.session_state.get('dirty', False) else "🚀 Save Profile"
    if st.button(save_btn_label, type="primary", use_container_width=True):
        save_profile()

# Execute selected page
PAGES[st.session_state['current_page']]()