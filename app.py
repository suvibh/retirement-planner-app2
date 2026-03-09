import streamlit as st
import pandas as pd
import requests
import json
import datetime
from dateutil.relativedelta import relativedelta
import warnings
import re
import firebase_admin
from firebase_admin import credentials, firestore
import math

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# --- CONFIG & SUPPRESSION ---
warnings.simplefilter(action='ignore', category=FutureWarning)
st.set_page_config(page_title="AI Retirement Planner Pro", layout="wide", page_icon="🏦")

# --- CUSTOM CSS FOR PREMIUM LOOK ---
st.markdown("""
<style>
    .stApp { background-color: #f8fafc; }
    h1, h2, h3 { color: #1e293b !important; font-family: 'Inter', sans-serif; font-weight: 800 !important; }
    [data-testid="stExpander"] { background-color: white !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important; margin-bottom: 1rem !important; }
    .stButton > button { border-radius: 8px !important; transition: all 0.2s ease !important; }
    div[data-testid="column"]:has(button:contains("✨")) button { background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%) !important; color: white !important; border: none !important; font-weight: 600 !important; box-shadow: 0 4px 14px 0 rgba(79, 70, 229, 0.39) !important; }
    div[data-testid="column"]:has(button:contains("✨")) button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px 0 rgba(79, 70, 229, 0.39) !important; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700 !important; color: #4f46e5 !important; }
    .info-text { font-size: 0.9rem; color: #64748b; margin-bottom: 15px; border-left: 4px solid #3b82f6; padding-left: 10px; background-color: #eff6ff; padding: 10px; border-radius: 0 8px 8px 0;}

    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
    [data-testid="stMetricLabel"] { font-weight: 600 !important; color: #475569 !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. FIREBASE & SESSION CORE ---
try:
    import extra_streamlit_components as stx
except ImportError:
    st.error("Missing dependency: pip install extra-streamlit-components")
    st.stop()

if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cred_dict = dict(st.secrets["firebase"])
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        else:
            cred = credentials.Certificate('firebase_creds.json')
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"🚨 Firebase Init Failed: {e}")
        st.stop()

try:
    db = firestore.client()
except Exception as e:
    st.error(f"🚨 Firestore Connection Failed: {e}")
    st.stop()

FIREBASE_WEB_API_KEY = st.secrets.get("FIREBASE_WEB_API_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
cookie_manager = stx.CookieManager()


def sign_in_with_email_and_password(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    return requests.post(url, json={"email": email, "password": password, "returnSecureToken": True}).json()


def sign_up_with_email_and_password(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_WEB_API_KEY}"
    return requests.post(url, json={"email": email, "password": password, "returnSecureToken": True}).json()


def load_user_data(email):
    if email == "guest_demo": return {}
    doc = db.collection('users').document(email).get()
    return doc.to_dict() if doc.exists else {}


def call_gemini_json(prompt):
    if not GEMINI_API_KEY:
        st.error("⚠️ GEMINI_API_KEY is missing in Streamlit Secrets. AI features cannot run.")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json"}}
    try:
        res = requests.post(url, json=payload).json()
        if "error" in res:
            st.error(f"⚠️ API Error: {res['error'].get('message')}")
            return None
        text = res['candidates'][0]['content']['parts'][0]['text'].strip()
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict) and len(parsed) == 1 and isinstance(list(parsed.values())[0], list): return \
        list(parsed.values())[0]
        return parsed
    except Exception as e:
        st.error(f"⚠️ Failed to parse AI response. Response format may be unexpected.")
        return None


def subtract_years(dt, years):
    try:
        return dt.replace(year=dt.year - years)
    except ValueError:
        return dt.replace(year=dt.year - years, day=28)


def safe_num(val, default=0.0):
    try:
        return float(val) if val is not None and not pd.isna(val) else default
    except:
        return default


# --- AUTH LAYER ---
if 'user_email' not in st.session_state:
    saved_email = cookie_manager.get(cookie="user_email")
    if saved_email:
        st.session_state['user_email'] = saved_email
        st.session_state['user_data'] = load_user_data(saved_email)
        st.rerun()

    st.title("🛡️ AI Retirement Planner Pro")
    st.markdown(
        "#### The world's first city-aware, AI-driven financial simulator with dynamic progressive tax modeling.")

    tab1, tab2 = st.tabs(["Secure Login", "New Account"])
    with tab1:
        le = st.text_input("Email", key="le")
        lp = st.text_input("Password", type="password", key="lp")
        if st.button("Sign In", type="primary"):
            res = sign_in_with_email_and_password(le, lp)
            if "idToken" in res:
                st.session_state['user_email'] = res['email']
                st.session_state['user_data'] = load_user_data(res['email'])
                cookie_manager.set("user_email", res['email'],
                                   expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                st.rerun()
            else:
                st.error("Authentication failed.")
    with tab2:
        se = st.text_input("Email", key="se")
        sp = st.text_input("Password", type="password", key="sp")
        if st.button("Create Account"):
            if len(sp) >= 6:
                res = sign_up_with_email_and_password(se, sp)
                if "idToken" in res:
                    st.session_state['user_email'] = res['email']
                    st.session_state['user_data'] = {}
                    cookie_manager.set("user_email", res['email'],
                                       expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.rerun()
            else:
                st.warning("Min 6 characters.")

    st.divider()
    if st.button("🚀 Explore Demo (Guest Mode)", use_container_width=True):
        st.session_state['user_email'] = "guest_demo"
        st.session_state['user_data'] = {}
        st.rerun()
    st.stop()

# --- STATE INIT & GLOBAL FUNCTIONS ---
if 'onboarding_shown' not in st.session_state:
    st.toast("Welcome! Hover over the (?) icons to learn how the simulation engine works.", icon="🎓")
    st.session_state['onboarding_shown'] = True

ud = st.session_state.get('user_data', {})
p_info = ud.get('personal_info', {})
if 'current_expenses' not in st.session_state: st.session_state['current_expenses'] = ud.get('current_expenses', [])
if 'retire_expenses' not in st.session_state: st.session_state['retire_expenses'] = ud.get('retire_expenses', [])
if 'one_time_events' not in st.session_state: st.session_state['one_time_events'] = ud.get('one_time_events', [])
if 'assumptions' not in st.session_state: st.session_state['assumptions'] = ud.get('assumptions', {"inflation": 3.0,
                                                                                                   "inflation_healthcare": 5.5,
                                                                                                   "inflation_education": 4.5,
                                                                                                   "market_growth": 7.0,
                                                                                                   "income_growth": 3.0,
                                                                                                   "property_growth": 3.0,
                                                                                                   "rent_growth": 3.0,
                                                                                                   "current_tax_rate": 5.0,
                                                                                                   "retire_tax_rate": 0.0})


def city_autocomplete(label, key_prefix, default_val=""):
    input_key = f"{key_prefix}_input"
    if input_key not in st.session_state: st.session_state[input_key] = default_val
    current_val = st.text_input(label, key=input_key,
                                help="Type a major city. The AI uses this to fetch hyper-localized cost-of-living data.")
    if current_val and len(current_val) > 2 and current_val != default_val:
        try:
            api_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
            if api_key:
                url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={current_val}&types=(cities)&key={api_key}"
                res = requests.get(url).json()
                if res.get("status") == "OK":
                    predictions = res.get("predictions", [])
                    if not any(current_val == p["description"] for p in predictions):
                        st.caption("AI Location Matches:")
                        for p in predictions[:3]:
                            st.button(p["description"], key=f"{key_prefix}_{p['place_id']}",
                                      on_click=lambda k=input_key, v=p["description"]: st.session_state.update({k: v}))
        except:
            pass
    return current_val


def render_total(label, text):
    st.markdown(
        f"<div style='text-align: right; font-weight: 600; color: #4f46e5; font-size: 1.1rem;'>{label}: <span style='color: #111827;'>{text}</span></div>",
        unsafe_allow_html=True)


# ==========================================
#              THE UI SECTIONS
# ==========================================

c_title, c_logout = st.columns([4, 1])
with c_title:
    st.title("🏦 AI-Powered Retirement Planner")
    st.markdown("##### *Dynamic IRS Tax Modeling & City-Aware Lifestyle Simulations*")
with c_logout:
    st.markdown(
        f"<div style='text-align: right; font-size: 0.9rem; color: #64748b; padding-top: 10px;'>Logged in: <b>{st.session_state['user_email']}</b></div>",
        unsafe_allow_html=True)
    if st.button("Log Out", use_container_width=True):
        if cookie_manager.get("user_email"): cookie_manager.delete("user_email")
        st.session_state.clear()
        st.rerun()

save_requested = False

# --- 1. PERSONAL INFO ---
with st.expander("👨‍👩‍👧‍👦 1. Your Profile & Family Context", expanded=True):
    st.markdown(
        '<div class="info-text">💡 <strong>Why Date of Birth?</strong> Precision matters. Your exact birth year dictates your SECURE 2.0 RMD age (73 vs 75) and Social Security Full Retirement Age (FRA). Selecting "Include Spouse" activates the Married Filing Jointly (MFJ) Standard Deduction ($29,200) and wider tax brackets.</div>',
        unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    my_name = c1.text_input("Preferred Name", value=p_info.get('name', ''))

    saved_dob = p_info.get('dob')
    default_dob = datetime.datetime.strptime(saved_dob, "%Y-%m-%d").date() if saved_dob else subtract_years(
        datetime.date.today(), int(p_info.get('age', 40)))
    my_dob = c2.date_input("Your Date of Birth", value=default_dob, min_value=datetime.date(1920, 1, 1),
                           max_value=datetime.date.today())
    my_age = relativedelta(datetime.date.today(), my_dob).years

    curr_city = city_autocomplete("Current City of Residence", "curr_city", default_val=p_info.get('current_city', ''))

    st.divider()
    has_spouse = st.checkbox("Include Spouse/Partner? (Triggers MFJ Tax Logic)", value=p_info.get('has_spouse', False))
    spouse_name, spouse_dob, spouse_age = "", None, 0
    if has_spouse:
        sc1, sc2 = st.columns(2)
        spouse_name = sc1.text_input("Spouse Name", value=p_info.get('spouse_name', ''))
        s_saved_dob = p_info.get('spouse_dob')
        s_default_dob = datetime.datetime.strptime(s_saved_dob, "%Y-%m-%d").date() if s_saved_dob else subtract_years(
            datetime.date.today(), int(p_info.get('spouse_age', 40)))
        spouse_dob = sc2.date_input("Spouse Date of Birth", value=s_default_dob, min_value=datetime.date(1920, 1, 1),
                                    max_value=datetime.date.today())
        spouse_age = relativedelta(datetime.date.today(), spouse_dob).years

    st.divider()
    saved_kids = p_info.get('kids', [])
    num_kids = st.number_input("Number of Dependents (Kids)", 0, 10, len(saved_kids))
    kids_data = []
    if num_kids > 0: st.write(
        "**Dependent Details** *(AI uses ages to drop daycare costs and start college timelines)*")
    for i in range(num_kids):
        k1, k2 = st.columns([3, 1])
        kn = k1.text_input(f"Dependent {i + 1} Name", value=saved_kids[i]['name'] if i < len(saved_kids) else "",
                           key=f"kn_{i}")
        ka = k2.number_input(f"Age {i + 1}", 0, 25, saved_kids[i]['age'] if i < len(saved_kids) else 5, key=f"ka_{i}")
        kids_data.append({"name": kn, "age": ka})
    if st.button("💾 Save Profile Snapshot", key="sv_1"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 2. INCOME ---
with st.expander("💵 2. Active Annual Income Streams", expanded=False):
    st.markdown(
        '<div class="info-text">💡 <strong>Tax Torpedo Warning:</strong> The simulation separates Ordinary Income from Capital Gains. If you list a 401(k) withdrawal later, it increases your "Provisional Income," which can cause up to 85% of your Social Security to become taxable automatically.<br><br><strong>Social Security Note:</strong> Add your expected Social Security benefit below. The simulation engine automatically scales this amount up or down based on your exact Full Retirement Age (FRA) and your chosen Retirement Age.</div>',
        unsafe_allow_html=True)
    df_inc = pd.DataFrame(ud.get('income', []))
    if df_inc.empty:
        df_inc = pd.DataFrame(
            [{"Description": "Base Salary", "Category": "Base Salary (W-2)", "Owner": "Me", "Annual Amount ($)": 0,
              "Start Age": my_age, "End Age": 65, "Override Growth (%)": None}])
    else:
        df_inc = df_inc.reindex(
            columns=["Description", "Category", "Owner", "Annual Amount ($)", "Start Age", "End Age",
                     "Override Growth (%)"])

    if st.button("✨ Auto-Estimate Social Security (AI)"):
        with st.spinner("Estimating SSA Benefits..."):
            curr_inc = sum([safe_num(x.get('Annual Amount ($)', 0)) for x in ud.get('income', [])])
            if has_spouse:
                prompt = f"User is {my_age} years old making ${curr_inc}/year. Spouse is {spouse_age} years old. Estimate realistic annual Social Security benefits at Full Retirement Age for both. Return JSON: {{'ss_amount_me': integer, 'ss_amount_spouse': integer}}"
            else:
                prompt = f"User is {my_age} years old making ${curr_inc}/year. Estimate their annual Social Security benefit at Full Retirement Age. Return JSON: {{'ss_amount_me': integer}}"
            res = call_gemini_json(prompt)
            if res:
                current_inc = df_inc.to_dict('records')
                if 'ss_amount_me' in res:
                    current_inc.append(
                        {"Description": "Estimated Social Security (Me)", "Category": "Social Security", "Owner": "Me",
                         "Annual Amount ($)": res['ss_amount_me'], "Start Age": 67, "End Age": 100,
                         "Override Growth (%)": None})
                if 'ss_amount_spouse' in res and has_spouse:
                    current_inc.append(
                        {"Description": "Estimated Social Security (Spouse)", "Category": "Social Security",
                         "Owner": "Spouse", "Annual Amount ($)": res['ss_amount_spouse'], "Start Age": 67,
                         "End Age": 100, "Override Growth (%)": None})
                st.session_state['user_data']['income'] = current_inc
                st.rerun()

    edited_inc = st.data_editor(
        df_inc,
        column_config={
            "Description": st.column_config.TextColumn("Description"),
            "Category": st.column_config.SelectboxColumn("Category", options=["Base Salary (W-2)", "Bonus / Commission",
                                                                              "Employer Match (401k/HSA)",
                                                                              "Equity / RSUs", "Side Gig (1099)",
                                                                              "Dividends", "Social Security", "Pension",
                                                                              "Other"]),
            "Owner": st.column_config.SelectboxColumn("Owner", options=["Me", "Spouse", "Joint"]),
            "Annual Amount ($)": st.column_config.NumberColumn("Annual Amount ($)", step=1000, format="$%d"),
            "Start Age": st.column_config.NumberColumn("Start Age", min_value=18, max_value=100),
            "End Age": st.column_config.NumberColumn("End Age", min_value=18, max_value=100),
            "Override Growth (%)": st.column_config.NumberColumn("Override Growth (%)", step=0.1, format="%.1f%%")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="inc_editor"
    )
    render_total("Aggregate Pre-Tax Income", f"${edited_inc['Annual Amount ($)'].sum():,.0f}")
    if st.button("💾 Save Profile Snapshot", key="sv_2"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 3. ASSETS, LIABILITIES & NET WORTH ---
with st.expander("🏦 3. Assets, Liabilities & Net Worth", expanded=False):
    st.subheader("Real Estate Portfolio")
    st.markdown(
        '<div class="info-text">💡 <strong>Dynamic Amortization:</strong> You do NOT need to input a remaining loan term! By providing your Current Balance, Interest Rate, and P&amp;I Payment, the mathematical engine calculates the exact date the mortgage hits zero and automatically drops the expense from your long-term simulation.</div>',
        unsafe_allow_html=True)
    df_re = pd.DataFrame(ud.get('real_estate', []))
    if df_re.empty:
        df_re = pd.DataFrame([{"Property Name": "Primary Home", "Is Primary Residence?": True, "Market Value ($)": 0,
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
            "Property Name": st.column_config.TextColumn("Property Name"),
            "Is Primary Residence?": st.column_config.CheckboxColumn("Primary Residence?", default=False),
            "Market Value ($)": st.column_config.NumberColumn("Market Value ($)", step=10000, format="$%d"),
            "Mortgage Balance ($)": st.column_config.NumberColumn("Mortgage Balance ($)", step=10000, format="$%d"),
            "Interest Rate (%)": st.column_config.NumberColumn("Interest Rate (%)", step=0.001, format="%.3f%%"),
            "Mortgage Payment ($)": st.column_config.NumberColumn("Mortgage P&I ($)", step=100, format="$%d"),
            "Monthly Expenses ($)": st.column_config.NumberColumn("Monthly Expenses ($)", step=100, format="$%d"),
            "Monthly Rent ($)": st.column_config.NumberColumn("Monthly Rent ($)", step=100, format="$%d"),
            "Override Prop Growth (%)": st.column_config.NumberColumn("Override Prop Growth (%)", step=0.1,
                                                                      format="%.1f%%"),
            "Override Rent Growth (%)": st.column_config.NumberColumn("Override Rent Growth (%)", step=0.1,
                                                                      format="%.1f%%")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="re_editor"
    )

    st.divider()
    st.subheader("Private Business Assets")
    df_biz = pd.DataFrame(ud.get('business', []))
    if df_biz.empty:
        df_biz = pd.DataFrame(
            [{"Business Name": "", "Total Valuation ($)": 0, "Your Ownership (%)": 100, "Annual Distribution ($)": 0}])
    else:
        df_biz = df_biz.reindex(
            columns=["Business Name", "Total Valuation ($)", "Your Ownership (%)", "Annual Distribution ($)"])

    edited_biz = st.data_editor(
        df_biz,
        column_config={
            "Total Valuation ($)": st.column_config.NumberColumn("Total Valuation ($)", step=10000, format="$%d"),
            "Annual Distribution ($)": st.column_config.NumberColumn("Annual Distribution ($)", step=1000,
                                                                     format="$%d"),
            "Your Ownership (%)": st.column_config.NumberColumn("Your Ownership (%)", min_value=0, max_value=100,
                                                                format="%d%%")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="biz_editor"
    )

    st.divider()
    st.subheader("Liquid Market Portfolios")
    st.markdown(
        '<div class="info-text">💡 <strong>Smart Withdrawal Sequencing:</strong> During a retirement shortfall, the AI minimizes taxes by drawing from <em>Taxable Brokerages</em> first (Capital Gains), then <em>Traditional 401ks</em> (Ordinary Income), and saves <em>Tax-Free Roths</em> for last.</div>',
        unsafe_allow_html=True)
    df_ast = pd.DataFrame(ud.get('liquid_assets', []))
    if df_ast.empty:
        df_ast = pd.DataFrame(
            [{"Account Name": "401k", "Type": "Traditional 401k/IRA", "Owner": "Me", "Current Balance ($)": 0,
              "Annual Contribution ($/yr)": 0, "Est. Annual Growth (%)": 7.0}])
    else:
        if "Annual Contribution ($)" in df_ast.columns: df_ast.rename(
            columns={'Annual Contribution ($)': 'Annual Contribution ($/yr)'}, inplace=True)
        df_ast = df_ast.reindex(
            columns=["Account Name", "Type", "Owner", "Current Balance ($)", "Annual Contribution ($/yr)",
                     "Est. Annual Growth (%)"])

    edited_ast = st.data_editor(
        df_ast,
        column_config={
            "Type": st.column_config.SelectboxColumn("Account Type",
                                                     options=["Checking/Savings", "HYSA", "Brokerage (Taxable)",
                                                              "Traditional 401k/IRA", "Roth 401k/IRA", "HSA", "Crypto",
                                                              "529 Plan", "Other"]),
            "Owner": st.column_config.SelectboxColumn("Owner", options=["Me", "Spouse", "Joint"]),
            "Current Balance ($)": st.column_config.NumberColumn("Current Balance ($)", step=5000, format="$%d"),
            "Annual Contribution ($/yr)": st.column_config.NumberColumn("Annual Additions ($/yr)", step=1000,
                                                                        format="$%d",
                                                                        help="These additions are deposited every year until you retire."),
            "Est. Annual Growth (%)": st.column_config.NumberColumn("Est. Annual Growth (%)",
                                                                    help="If blank, uses global assumptions.",
                                                                    format="%.1f%%")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="assets_editor"
    )

    st.divider()
    st.subheader("Other Liabilities (Auto, Student Loans, etc.)")
    st.markdown(
        '<div class="info-text">💡 Just like your mortgage, simply provide the Current Balance, Rate, and Payment. The engine dynamically amortizes this debt to zero over time.</div>',
        unsafe_allow_html=True)
    df_debt = pd.DataFrame(ud.get('liabilities', []))
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
        }, num_rows="dynamic", width="stretch", hide_index=True, key="debt_editor"
    )

    # Calculate Live Net Worth
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
    c_met4.metric("Other Liabilities", f"${total_debt:,.0f}")
    st.markdown(
        f"<div style='text-align: center; padding: 15px; margin-top: 15px; background: #eff6ff; border-radius: 8px;'><h3 style='margin:0; color: #1e293b;'>Total Estimated Net Worth: <span style='color: #3b82f6;'>${net_worth:,.0f}</span></h3></div>",
        unsafe_allow_html=True)

    if st.button("💾 Save Profile Snapshot", key="sv_3"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- AI CONTEXT PREP ---
k_ctx = f"{len(kids_data)} children ages {', '.join([str(k['age']) for k in kids_data])}."
primary_re = edited_re[edited_re["Is Primary Residence?"] == True]
h_pmt = pd.to_numeric(primary_re["Mortgage Payment ($)"], errors='coerce').fillna(0).sum()
h_exp = pd.to_numeric(primary_re["Monthly Expenses ($)"], errors='coerce').fillna(0).sum()
owns_home = not primary_re.empty

if owns_home:
    h_ctx = f"Primary housing costs ${h_pmt + h_exp:,.0f}/mo (Already accounted for)."
    ai_exclusion = "STRICT RULE: DO NOT INCLUDE Housing, Rent, Mortgages, Auto Loans, or Debt Payments in this list. They are tracked elsewhere."
else:
    h_ctx = "Renting residence."
    ai_exclusion = "STRICT RULE: DO NOT INCLUDE Mortgages, Auto Loans, or Debt Payments. HOWEVER, YOU MUST INCLUDE a realistic 'Housing / Rent' expense since the user does not own a home."

f_ctx = f"User({my_age})" + (
    f", Spouse({spouse_name}:{spouse_age})" if has_spouse else "") + f", Kids({', '.join([f'{k['name']}:{k['age']}' for k in kids_data])})"
budget_categories = ["Housing / Rent", "Transportation", "Food", "Utilities", "Insurance", "Healthcare",
                     "Entertainment", "Education", "Personal Care", "Subscriptions", "Travel", "Debt Payments", "Other"]

# --- 4. CURRENT EXPENSES ---
with st.expander("💸 4. Current Expenses & AI Builder", expanded=False):
    st.markdown(
        '<div class="info-text">💡 <strong>Double-Counting Guard:</strong> The simulation automatically ignores "Housing" (if you own) and "Debt Payments" listed below, as it pulls the exact costs from your Real Estate and Liabilities sections above!</div>',
        unsafe_allow_html=True)
    df_c = pd.DataFrame(st.session_state['current_expenses'])
    if df_c.empty:
        df_c = pd.DataFrame([{"Description": "Groceries", "Category": "Food", "Frequency": "Monthly", "Amount ($)": 0,
                              "AI Estimate?": False}])
    else:
        if "AI Estimate?" not in df_c.columns: df_c["AI Estimate?"] = False
        df_c = df_c.reindex(columns=["Description", "Category", "Frequency", "Amount ($)", "AI Estimate?"])

    edited_c = st.data_editor(
        df_c,
        column_config={
            "Category": st.column_config.SelectboxColumn("Category", options=budget_categories),
            "Frequency": st.column_config.SelectboxColumn("Frequency", options=["Monthly", "Yearly"]),
            "Amount ($)": st.column_config.NumberColumn("Amount ($)", step=100, format="$%d"),
            "AI Estimate?": st.column_config.CheckboxColumn("🤖 AI Estimate?")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="cur_ed"
    )

    cur_m_total, cur_y_total = 0, 0
    for r in edited_c.to_dict('records'):
        if str(r.get("Description", "")).strip() != "":
            amt = safe_num(r.get("Amount ($)"))
            if r.get("Frequency") == "Monthly":
                cur_m_total += amt
                cur_y_total += amt * 12
            else:
                cur_y_total += amt
                cur_m_total += amt / 12
    render_total("Est. Total Baseline Budget", f"${cur_m_total:,.0f} / mo  |  ${cur_y_total:,.0f} / yr")

    if st.button("✨ Auto-Estimate Budget for " + (curr_city if curr_city else "Your Area") + " (AI)"):
        with st.spinner("Analyzing localized CPI data and family needs..."):
            valid = edited_c[edited_c["Description"].astype(str) != ""].copy()
            locked = valid[valid["AI Estimate?"] == False].to_dict('records')
            locked_desc = [x['Description'] for x in locked]
            prompt = f"City: {curr_city}. Family: {k_ctx} Housing: {h_ctx}. Generate 10-15 missing living expenses to create a complete monthly budget. {ai_exclusion} Skip these items as they are already accounted for: {json.dumps(locked_desc)}. Return ONLY a JSON array of objects with keys: 'Description', 'Category' (choose from standard budget categories), 'Frequency' (Monthly/Yearly), 'Amount ($)' (number), 'AI Estimate?' (true)."
            res = call_gemini_json(prompt)
            if res and isinstance(res, list) and len(res) > 0:
                st.session_state['current_expenses'] = locked + res
                st.rerun()
            else:
                st.error("⚠️ AI returned an invalid format. Please try again.")
    if st.button("💾 Save Profile Snapshot", key="sv_4"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 5. MILESTONES ---
with st.expander("🎉 5. AI Life Milestone Forecaster", expanded=False):
    st.markdown(
        '<div class="info-text">💡 Add descriptions like <em>"College for Sarah"</em> or <em>"Kitchen Remodel"</em>. The AI calculates exact future start years based on current family ages.</div>',
        unsafe_allow_html=True)
    df_m = pd.DataFrame(st.session_state['one_time_events'])
    current_date_str = f"{datetime.date.today().month:02d}/{datetime.date.today().year}"
    if df_m.empty:
        df_m = pd.DataFrame(
            [{"Description": "Child College Tuition", "Type": "Expense", "Frequency": "Yearly", "Amount ($)": 0,
              "Start Date (MM/YYYY)": current_date_str, "End Date (MM/YYYY)": "", "AI Estimate?": False}])
    else:
        if "AI Estimate?" not in df_m.columns: df_m["AI Estimate?"] = False
        df_m = df_m.reindex(
            columns=["Description", "Type", "Frequency", "Amount ($)", "Start Date (MM/YYYY)", "End Date (MM/YYYY)",
                     "AI Estimate?"])

    edited_m = st.data_editor(
        df_m,
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=["Expense", "Income / Windfall"]),
            "Frequency": st.column_config.SelectboxColumn("Frequency", options=["One-Time", "Monthly", "Yearly"]),
            "Amount ($)": st.column_config.NumberColumn("Amount ($)", step=1000, format="$%d"),
            "Start Date (MM/YYYY)": st.column_config.TextColumn("Start (MM/YYYY)",
                                                                validate=r"^(0?[1-9]|1[0-2])\/[0-9]{4}$"),
            "End Date (MM/YYYY)": st.column_config.TextColumn("End (MM/YYYY)",
                                                              validate=r"^(0?[1-9]|1[0-2])\/[0-9]{4}$"),
            "AI Estimate?": st.column_config.CheckboxColumn("🤖 AI Estimate?")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="mil_ed"
    )

    if st.button("✨ Forecast Milestone Timelines & Costs (AI)"):
        with st.spinner("AI mapping family timelines and projecting future costs..."):
            valid = edited_m[edited_m["Description"].astype(str) != ""].to_dict('records')
            prompt = f"Family Context: {f_ctx}. Current Date: {current_date_str}. Calculate Start/End dates (MM/YYYY) and future Amounts in today's dollars for: {json.dumps(valid)}. Return ONLY JSON array."
            res = call_gemini_json(prompt)
            if res and isinstance(res, list):
                st.session_state['one_time_events'] = res
                st.rerun()
    if st.button("💾 Save Profile Snapshot", key="sv_5"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 6. RETIREMENT SIMULATION & ASSUMPTIONS ---
with st.expander("🔮 6. Global Macroeconomic Assumptions & Retirement Sim", expanded=False):
    st.markdown(
        '<div class="info-text">💡 <strong>Global Overrides:</strong> Any specific growth percentages you typed into the Income, Real Estate, or Assets tables above will automatically override these global default rates.</div>',
        unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.write("**Your Timeline**")
        ret_age = st.slider("Retirement Age", int(my_age), 100, int(p_info.get('retire_age', 65)))
        my_life_exp = st.slider("Your Life Expectancy", 70, 115, int(p_info.get('my_life_exp', 95)))

    s_ret_age = None
    spouse_life_exp = 0
    with c2:
        if has_spouse:
            st.write("**Spouse Timeline**")
            s_ret_age = st.slider("Spouse Retire Age", int(spouse_age), 100, int(p_info.get('spouse_retire_age', 65)))
            spouse_life_exp = st.slider("Spouse Life Expectancy", 70, 115, int(p_info.get('spouse_life_exp', 95)))

    ret_city = city_autocomplete("Where will you retire? (Search any city globally)", "retire_city",
                                 default_val=ud.get('retire_city', curr_city))

    if st.button("✨ Auto-Set Macroeconomic Assumptions for " + (ret_city if ret_city else "Retirement") + " (AI)"):
        with st.spinner(f"Analyzing economic forecast and historical data for {ret_city}..."):
            prompt = f"Forecast long-term annual percentages for {ret_city if ret_city else 'the US'}. Return JSON object with keys: 'inflation', 'market_growth', 'income_growth', 'property_growth', 'rent_growth'."
            res = call_gemini_json(prompt)
            if res and isinstance(res, dict):
                st.session_state['assumptions'].update(res)
                st.rerun()

    c4, c5, c6 = st.columns(3)
    infl = c4.number_input("General CPI Inflation (%)",
                           value=float(st.session_state['assumptions'].get('inflation', 3.0)))
    infl_hc = c5.number_input("Healthcare Inflation (%)",
                              value=float(st.session_state['assumptions'].get('inflation_healthcare', 5.5)))
    infl_ed = c6.number_input("Education Inflation (%)",
                              value=float(st.session_state['assumptions'].get('inflation_education', 4.5)))

    c7, c8 = st.columns(2)
    mkt = c7.number_input("Market Growth (%)", value=float(st.session_state['assumptions'].get('market_growth', 7.0)))
    inc_g = c8.number_input("Income Growth (%)", value=float(st.session_state['assumptions'].get('income_growth', 3.0)))

    st.session_state['assumptions']['property_growth'] = st.number_input("Property Growth (%)", value=float(
        st.session_state['assumptions'].get('property_growth', 3.0)))
    st.session_state['assumptions']['rent_growth'] = st.number_input("Rent Growth (%)", value=float(
        st.session_state['assumptions'].get('rent_growth', 3.0)))

    st.divider()
    st.markdown(
        '<div class="info-text">💡 <strong>Double-Counting Guard:</strong> As with the current budget, "Housing" and "Debt Payments" are pulled automatically from your assets and excluded from this list.</div>',
        unsafe_allow_html=True)
    df_r = pd.DataFrame(st.session_state['retire_expenses'])
    if df_r.empty:
        df_r = pd.DataFrame(
            [{"Description": "Healthcare", "Category": "Healthcare", "Frequency": "Monthly", "Amount ($)": 0,
              "AI Estimate?": False}])
    else:
        if "AI Estimate?" not in df_r.columns: df_r["AI Estimate?"] = False
        df_r = df_r.reindex(columns=["Description", "Category", "Frequency", "Amount ($)", "AI Estimate?"])

    edited_r = st.data_editor(
        df_r,
        column_config={
            "Description": st.column_config.TextColumn("Description"),
            "Category": st.column_config.SelectboxColumn("Category", options=budget_categories),
            "Frequency": st.column_config.SelectboxColumn("Frequency", options=["Monthly", "Yearly"]),
            "Amount ($)": st.column_config.NumberColumn("Amount ($)", step=100, format="$%d"),
            "AI Estimate?": st.column_config.CheckboxColumn("🤖 AI Estimate?")
        }, num_rows="dynamic", width="stretch", hide_index=True, key="ret_exp_ed"
    )

    ret_m_total, ret_y_total = 0, 0
    for r in edited_r.to_dict('records'):
        if str(r.get("Description", "")).strip() != "":
            amt = safe_num(r.get("Amount ($)"))
            if r.get("Frequency") == "Monthly":
                ret_m_total += amt
                ret_y_total += amt * 12
            else:
                ret_y_total += amt
                ret_m_total += amt / 12
    render_total("Est. Total Retirement Budget", f"${ret_m_total:,.0f} / mo  |  ${ret_y_total:,.0f} / yr")

    if st.button("✨ Simulate Realistic Lifestyle Costs in " + (ret_city if ret_city else "Retirement") + " (AI)"):
        with st.spinner(f"Modelling specific living costs for {ret_city}..."):
            valid = edited_r[edited_r["Description"].astype(str) != ""].copy()
            locked = valid[valid["AI Estimate?"] == False].to_dict('records')
            locked_desc = [x['Description'] for x in locked]
            prompt = f"Retirement context: {ret_city}. Household size drops to {1 + (1 if has_spouse else 0)}. Generate 10-15 missing living expenses to create a complete retirement budget. {ai_exclusion} Skip these items as they are already accounted for: {json.dumps(locked_desc)}. Return ONLY a JSON array of objects with keys: 'Description', 'Category', 'Frequency', 'Amount ($)', 'AI Estimate?' (true)."
            res = call_gemini_json(prompt)
            if res and isinstance(res, list) and len(res) > 0:
                st.session_state['retire_expenses'] = locked + res
                st.rerun()
            else:
                st.error("⚠️ AI returned an invalid format. Please try again.")
    if st.button("💾 Save Profile Snapshot", key="sv_6"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 7. ADVANCED SCENARIOS & TAXES ---
with st.expander("⚖️ 7. AI Based Advanced Retirement Scenarios", expanded=False):
    st.markdown(
        '<div class="info-text">💡 Adjust edge-case scenarios here. The simulation integrates Federal Taxes dynamically using 2026 Brackets. Input your effective State Tax here.</div>',
        unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Simulation Stressors**")
        medicare_gap = st.toggle("🏥 Model Pre-Medicare Gap", value=True,
                                 help="If retiring before 65, adds a significant Private Health Insurance expense until Medicare eligibility.")
        medicare_cliff = st.toggle("🏥 Apply Medicare Cliff (Drop Healthcare at 65)", value=True,
                                   help="Automatically reduces 'Healthcare' budget line items by 50% when you turn 65 to simulate Medicare kicking in.")
        glidepath = st.toggle("📉 Apply Investment Glidepath", value=True,
                              help="Reduces the Market Growth rate by 1% for every 5 years you are into retirement, simulating a shift to bonds.")
        stress_test = st.toggle("📉 Apply 20% Market Crash at Retirement", value=False,
                                help="Simulates 'Sequence of Returns Risk' by dropping your portfolio by 20% in the first 3 years of retirement.")
        ltc_shock = st.toggle("🛏️ Long-Term Care (LTC) Shock", value=False,
                              help="Injects a massive $100k/yr medical expense into the final 3 years of your simulated life expectancy.")

    with col2:
        st.write("**State Tax / Effective Adjustments**")
        cur_t = st.number_input("Current State Tax Adjustment (%)",
                                value=float(st.session_state['assumptions'].get('current_tax_rate', 5.0)),
                                help="Federal taxes are calculated dynamically. Enter your effective State/Local rate here.")
        ret_t = st.number_input("Retirement State Tax Adjustment (%)",
                                value=float(st.session_state['assumptions'].get('retire_tax_rate', 0.0)),
                                help="Are you moving to a tax-free state in retirement? Adjust here.")
    if st.button("💾 Save Profile Snapshot", key="sv_7"):
        save_requested = True
        st.toast("✅ Profile Snapshot Saved!", icon="💾")

# --- 8. EXHAUSTIVE DASHBOARD ENGINE & TAX LOGIC ---
with st.expander("📈 8. Advanced Simulation & Analytics Dashboard", expanded=True):
    if my_age > 0:

        prop_g = float(st.session_state['assumptions'].get('property_growth', 3.0))
        rent_g = float(st.session_state['assumptions'].get('rent_growth', 3.0))


        # --- PROGRESSIVE IRS FEDERAL TAX CALCULATOR ---
        def calc_federal_tax(ordinary_income, cap_gains, is_mfj, year_offset, inflation_rate):
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

            cg_tax = 0
            if cap_gains > 0:
                cg_threshold = 94000 * infl_factor if is_mfj else 47000 * infl_factor
                if taxable_ordinary > cg_threshold: cg_tax = cap_gains * 0.15

            return ord_tax + cg_tax, marginal_rate


        # --- SOCIAL SECURITY FRA MATH ---
        my_ss_fra = 67 if my_dob.year >= 1960 else (
            66 + (min(my_dob.year - 1954, 10) / 12.0) if my_dob.year >= 1955 else 66)
        my_ss_multi = 1.0
        if ret_age < my_ss_fra:
            months_early = (my_ss_fra - ret_age) * 12
            if months_early <= 36:
                my_ss_multi = 1.0 - (months_early * (5 / 9 * 0.01))
            else:
                my_ss_multi = 1.0 - (36 * (5 / 9 * 0.01)) - ((months_early - 36) * (5 / 12 * 0.01))
        elif ret_age > my_ss_fra:
            months_late = min((ret_age - my_ss_fra) * 12, 36)
            my_ss_multi = 1.0 + (months_late * (2 / 3 * 0.01))

        irs_uniform_table = {73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4,
                             82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2,
                             91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8,
                             100: 6.4, 101: 6.0, 102: 5.6, 103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9,
                             109: 3.7, 110: 3.5, 111: 3.4, 112: 3.3, 113: 3.1, 114: 3.0, 115: 2.9, 116: 2.8, 117: 2.7,
                             118: 2.5, 119: 2.3, 120: 2.0}

        # INIT STATE
        sim_assets = [{"Account Name": a.get("Account Name"), "Type": a.get("Type"), "Owner": a.get("Owner", "Me"),
                       "bal": safe_num(a.get("Current Balance ($)")),
                       "contrib": safe_num(a.get("Annual Additions ($/yr)")),
                       "growth": safe_num(a.get("Est. Annual Growth (%)"), mkt)} for a in edited_ast.to_dict('records')
                      if a.get("Account Name")]
        if not sim_assets: sim_assets = [
            {"Account Name": "Unallocated Cash", "Type": "Checking/Savings", "Owner": "Me", "bal": 0.0, "contrib": 0.0,
             "growth": 0.0}]

        sim_debts = [{"bal": safe_num(d.get("Current Balance ($)")), "pmt": safe_num(d.get("Monthly Payment ($)")) * 12,
                      "rate": safe_num(d.get("Interest Rate (%)")) / 100} for d in edited_debt.to_dict('records') if
                     d.get("Debt Name")]
        sim_re = [{"val": safe_num(r.get("Market Value ($)")), "debt": safe_num(r.get("Mortgage Balance ($)")),
                   "pmt": safe_num(r.get("Mortgage Payment ($)")) * 12,
                   "exp": safe_num(r.get("Monthly Expenses ($)")) * 12,
                   "rent": safe_num(r.get("Monthly Rent ($)")) * 12,
                   "v_growth": safe_num(r.get("Override Prop Growth (%)"), prop_g),
                   "r_growth": safe_num(r.get("Override Rent Growth (%)"), rent_g),
                   "rate": safe_num(r.get("Interest Rate (%)")) / 100} for r in edited_re.to_dict('records') if
                  r.get("Property Name")]
        sim_biz = [{"name": b.get("Business Name"), "val": safe_num(b.get("Total Valuation ($)")),
                    "own": safe_num(b.get("Your Ownership (%)")) / 100.0,
                    "dist": safe_num(b.get("Annual Distribution ($)"))} for b in edited_biz.to_dict('records') if
                   b.get("Business Name")]

        # Correctly aggregate current and retirement expenses, excluding Housing and Debt Payments to prevent double counting
        curr_exp_by_cat = {}
        for r in edited_c.to_dict('records'):
            if r.get("Description") and (
            r.get("Category") not in ["Housing / Rent", "Debt Payments"] if owns_home else r.get(
                    "Category") != "Debt Payments"):
                cat = r.get("Category", "Other")
                amt = safe_num(r.get("Amount ($)")) * (12 if r.get("Frequency") == "Monthly" else 1)
                curr_exp_by_cat[cat] = curr_exp_by_cat.get(cat, 0) + amt

        ret_exp_by_cat = {}
        for r in edited_r.to_dict('records'):
            if r.get("Description") and (
            r.get("Category") not in ["Housing / Rent", "Debt Payments"] if owns_home else r.get(
                    "Category") != "Debt Payments"):
                cat = r.get("Category", "Other")
                amt = safe_num(r.get("Amount ($)")) * (12 if r.get("Frequency") == "Monthly" else 1)
                ret_exp_by_cat[cat] = ret_exp_by_cat.get(cat, 0) + amt

        sim_results, detailed_results = [], []
        current_year = datetime.date.today().year

        my_life_exp_val = my_life_exp if my_life_exp else 95
        spouse_life_exp_val = spouse_life_exp if has_spouse and spouse_life_exp else 0

        # Calculate absolute simulation bounds based on life expectancies
        max_years = max(0, my_life_exp_val - my_age)
        if has_spouse:
            max_years = max(max_years, spouse_life_exp_val - spouse_age)

        # EXHAUSTIVE SIMULATION LOOP
        for year_offset in range(max_years + 1):
            year = current_year + year_offset
            age = my_age + year_offset
            s_age = spouse_age + year_offset if has_spouse else 0

            is_my_alive = age <= my_life_exp_val
            is_spouse_alive = has_spouse and (s_age <= spouse_life_exp_val)

            if not is_my_alive and not is_spouse_alive:
                break

            is_retired = age >= ret_age
            is_spouse_retired = has_spouse and s_age >= s_ret_age
            yd = {"Age": age, "Year": year}
            annual_inc, annual_ss, pre_tax_ord, pre_tax_cg = 0, 0, 0, 0

            # Glidepath & Stress Logic (Apply mostly to primary retired)
            active_mkt = mkt
            if glidepath and is_retired:
                years_retired = age - ret_age
                active_mkt = max(3.0, mkt - (math.floor(years_retired / 5) * 1.0))
            if stress_test and is_retired and age < (int(ret_age) + 3): active_mkt = -20.0

            # Widow(er) Penalty Logic
            active_mfj = True if has_spouse and is_my_alive and is_spouse_alive else False

            # Income Generation
            for inc in edited_inc.to_dict('records'):
                owner = inc.get("Owner", "Me")
                if owner == "Me" and not is_my_alive: continue
                if owner == "Spouse" and not is_spouse_alive: continue
                if owner == "Joint" and not is_my_alive and not is_spouse_alive: continue

                # Default logic uses primary age/start limits for now
                if inc.get("Description") and safe_num(inc.get('Start Age'), 18) <= age <= safe_num(inc.get('End Age'),
                                                                                                    100):
                    g = safe_num(inc.get('Override Growth (%)'), inc_g)
                    base_amt = safe_num(inc.get('Annual Amount ($)'))
                    cat_name = inc.get("Category", "Other")

                    if cat_name == "Social Security":
                        # Basic assumption: SS starts at 'ret_age' and is scaled.
                        if is_retired:
                            base_amt = base_amt * my_ss_multi
                        else:
                            base_amt = 0

                    amt = base_amt * ((1 + g / 100) ** year_offset)
                    annual_inc += amt
                    yd[f"Income: {cat_name}"] = yd.get(f"Income: {cat_name}", 0) + amt
                    if cat_name == "Social Security": annual_ss += amt
                    if cat_name not in ["Employer Match (401k/HSA)", "Social Security"]: pre_tax_ord += amt

            # SECURE 2.0 RMDs
            rmd_income = 0
            rmd_target_age = 73 if my_dob.year <= 1959 else 75
            if age >= rmd_target_age and is_my_alive:
                factor = irs_uniform_table.get(age, 2.0)
                for a in sim_assets:
                    if a.get('Type') == 'Traditional 401k/IRA' and a['bal'] > 0:
                        rmd_amt = a['bal'] / factor
                        a['bal'] -= rmd_amt
                        rmd_income += rmd_amt
                        pre_tax_ord += rmd_amt
            if rmd_income > 0:
                annual_inc += rmd_income
                yd["Income: RMDs"] = rmd_income

            # Business & Real Estate
            cur_biz_val, biz_dist_total, re_equity, re_exp_total = 0, 0, 0, 0
            for b in sim_biz:
                if year_offset > 0: b['val'] *= (1 + active_mkt / 100); b['dist'] *= (1 + inc_g / 100)
                cur_biz_val += (b['val'] * b['own'])
                annual_inc += b['dist']
                pre_tax_ord += b['dist']
                yd["Income: Biz Dist"] = b['dist']

            for r in sim_re:
                if year_offset > 0: r['rent'] *= (1 + r['r_growth'] / 100); r['exp'] *= (1 + infl / 100); r['val'] *= (
                            1 + r['v_growth'] / 100)
                annual_inc += r['rent']
                pre_tax_ord += r['rent']
                yd["Income: RE Rent"] = r['rent'] if r['rent'] > 0 else 0
                re_exp_total += r['exp']
                yd["Expense: RE Upkeep/Tax"] = r['exp'] if r['exp'] > 0 else 0
                if r['debt'] > 0:
                    interest = r['debt'] * r['rate']
                    principal = max(0, r['pmt'] - interest)
                    r['debt'] = max(0, r['debt'] - principal)
                    re_exp_total += r['pmt']
                    yd["Expense: RE Mortgage"] = r['pmt']
                re_equity += (r['val'] - r['debt'])

            # Core Expenses & Toggles
            total_exp = re_exp_total
            active_expense_dict = ret_exp_by_cat if is_retired else curr_exp_by_cat
            for cat, base_amt in active_expense_dict.items():
                cat_infl = infl_hc if cat in ["Healthcare", "Insurance"] else (infl_ed if cat == "Education" else infl)
                inflated_exp = base_amt * ((1 + cat_infl / 100) ** year_offset)

                # Drop expenses significantly if widow(er)
                if has_spouse and not (is_my_alive and is_spouse_alive): inflated_exp *= 0.6

                # Health Insurance Logic
                if medicare_gap and is_retired and age < 65 and cat == "Healthcare": inflated_exp += (
                            15000 * ((1 + infl_hc / 100) ** year_offset))
                if medicare_cliff and cat == "Healthcare" and age >= 65: inflated_exp *= 0.50

                total_exp += inflated_exp
                yd[f"Expense: {cat}"] = inflated_exp

            # LTC Shock
            if ltc_shock and age >= (my_life_exp_val - 2) and is_my_alive:
                ltc_cost = 100000 * ((1 + infl_hc / 100) ** year_offset)
                total_exp += ltc_cost
                yd["Expense: Long Term Care Shock"] = ltc_cost

            # Debt Amortization
            debt_bal_total = 0
            for d in sim_debts:
                if d['bal'] > 0:
                    interest = d['bal'] * d['rate']
                    principal = max(0, d['pmt'] - interest)
                    d['bal'] = max(0, d['bal'] - principal)
                    total_exp += d['pmt']
                    yd["Expense: Debt Payments"] = d['pmt']
                debt_bal_total += d['bal']

            # Milestones
            for ev in edited_m.to_dict('records'):
                if ev.get("Description"):
                    try:
                        sy = int(str(ev.get('Start Date (MM/YYYY)', '')).split('/')[-1])
                    except:
                        sy = 0
                    if sy == year and sy != 0:
                        amt = safe_num(ev.get('Amount ($)')) * ((1 + infl / 100) ** year_offset)
                        if ev.get('Type') == 'Expense':
                            total_exp += amt
                            yd[f"Expense: Milestone ({ev.get('Description')})"] = amt
                        else:
                            annual_inc += amt
                            pre_tax_ord += amt
                            yd[f"Income: Milestone ({ev.get('Description')})"] = amt

            # Asset Waterfall Routing
            liquid_assets_total, asset_contributions = 0, 0
            if not is_retired:
                for a in sim_assets:
                    a['bal'] += a['contrib']
                    asset_contributions += a['contrib']

            # Pre-apply market growth
            for a in sim_assets:
                a_growth = active_mkt if a.get('Type') not in ['Checking/Savings', 'HYSA', 'Unallocated Cash'] else a[
                    'growth']
                a['bal'] *= (1 + a_growth / 100)

            # Determine Shortfall
            pre_tax_shortfall = (total_exp + asset_contributions) - annual_inc

            # Tax Calculations
            base_fed_tax, marginal_rate = calc_federal_tax(pre_tax_ord, 0, active_mfj, year_offset, infl)
            state_tax_rate = cur_t if not is_retired else ret_t
            state_tax = pre_tax_ord * (state_tax_rate / 100.0)
            yd["Expense: Taxes"] = base_fed_tax + state_tax

            if pre_tax_shortfall < 0:  # Surplus!
                if len(sim_assets) > 0: sim_assets[0]['bal'] += abs(pre_tax_shortfall) - yd["Expense: Taxes"]
            elif pre_tax_shortfall > 0:
                shortfall = pre_tax_shortfall + yd["Expense: Taxes"]

                # Sequence 1: Taxable Brokerage / Cash (Incurs 15% Cap Gains Tax)
                for a in sim_assets:
                    if shortfall <= 0: break
                    if a.get('Type') in ['Checking/Savings', 'HYSA', 'Brokerage (Taxable)', 'Unallocated Cash']:
                        req_gross = shortfall / 0.85 if a.get('Type') == 'Brokerage (Taxable)' else shortfall
                        if a['bal'] >= req_gross:
                            a['bal'] -= req_gross
                            if a.get('Type') == 'Brokerage (Taxable)': yd["Expense: Taxes"] += (req_gross - shortfall)
                            shortfall = 0
                        else:
                            withdrawn = a['bal']
                            a['bal'] = 0
                            net_cash = withdrawn * 0.85 if a.get('Type') == 'Brokerage (Taxable)' else withdrawn
                            if a.get('Type') == 'Brokerage (Taxable)': yd["Expense: Taxes"] += (withdrawn - net_cash)
                            shortfall -= net_cash

                # Sequence 2: Tax-Deferred (Traditional 401k) - Grossed up by Marginal Rate
                if shortfall > 0:
                    for a in sim_assets:
                        if shortfall <= 0: break
                        if a.get('Type') == 'Traditional 401k/IRA':
                            eff_tax = min(marginal_rate + (state_tax_rate / 100.0), 0.99)
                            req_gross = shortfall / (1.0 - eff_tax)
                            if a['bal'] >= req_gross:
                                a['bal'] -= req_gross
                                yd["Expense: Taxes"] += (req_gross - shortfall)
                                shortfall = 0
                            else:
                                withdrawn = a['bal']
                                a['bal'] = 0
                                net_cash = withdrawn * (1.0 - eff_tax)
                                yd["Expense: Taxes"] += (withdrawn - net_cash)
                                shortfall -= net_cash

                # Sequence 3: Tax-Free (Roth/HSA) - No tax drag
                if shortfall > 0:
                    for a in sim_assets:
                        if shortfall <= 0: break
                        if a.get('Type') in ['Roth 401k/IRA', 'HSA', 'Crypto', '529 Plan', 'Other']:
                            if a['bal'] >= shortfall:
                                a['bal'] -= shortfall
                                shortfall = 0
                            else:
                                shortfall -= a['bal']
                                a['bal'] = 0

            for a in sim_assets: liquid_assets_total += a['bal']
            net_worth = liquid_assets_total + re_equity + cur_biz_val - debt_bal_total
            yd["Net Savings"] = annual_inc - total_exp - yd["Expense: Taxes"]

            sim_results.append({"Age": age, "Year": year, "Annual Income": annual_inc, "Annual Expenses": total_exp,
                                "Annual Taxes": yd["Expense: Taxes"], "Liquid Assets": liquid_assets_total,
                                "Real Estate Equity": re_equity, "Business Equity": cur_biz_val,
                                "Debt": -debt_bal_total, "Net Worth": net_worth})
            detailed_results.append(yd)

        # UI RENDER
        if len(sim_results) > 0:
            df_sim = pd.DataFrame(sim_results)
            final_nw = df_sim.iloc[-1]['Net Worth']

            if final_nw >= 1000000:
                st.success(
                    f"🟢 **On Track:** Projected Net Worth at timeline end is **${final_nw:,.0f}**. Your assets outlive your life expectancy comfortably.")
            elif final_nw > 0:
                st.warning(
                    f"🟡 **Caution:** Projected Net Worth at timeline end is **${final_nw:,.0f}**. You are solvent, but with a narrow margin of safety.")
            else:
                st.error(
                    f"🔴 **Shortfall Alert:** Assets deplete entirely at Age **{df_sim[df_sim['Net Worth'] <= 0]['Age'].min()}**.")

            if HAS_PLOTLY:
                st.write("#### Net Worth Composition (Smart Asset Drawdown)")
                st.markdown(
                    '<div class="info-text">Notice how the engine drains your Taxable accounts first, shifts to your 401k (causing tax spikes), and saves your Roth for last to optimize your wealth.</div>',
                    unsafe_allow_html=True)
                fig_nw = go.Figure()
                fig_nw.add_trace(go.Scatter(x=df_sim["Age"], y=df_sim["Liquid Assets"], mode='lines', stackgroup='one',
                                            name='Liquid Assets', fillcolor='rgba(20, 184, 166, 0.5)',
                                            line=dict(color='#14b8a6')))
                fig_nw.add_trace(
                    go.Scatter(x=df_sim["Age"], y=df_sim["Real Estate Equity"], mode='lines', stackgroup='one',
                               name='Real Estate Equity', fillcolor='rgba(139, 92, 246, 0.5)',
                               line=dict(color='#8b5cf6')))
                fig_nw.add_trace(
                    go.Scatter(x=df_sim["Age"], y=df_sim["Business Equity"], mode='lines', stackgroup='one',
                               name='Business Equity', fillcolor='rgba(245, 158, 11, 0.5)', line=dict(color='#f59e0b')))
                fig_nw.add_trace(go.Scatter(x=df_sim["Age"], y=df_sim["Debt"], mode='lines', stackgroup='two',
                                            name='Debt Liabilities', fillcolor='rgba(244, 63, 94, 0.5)',
                                            line=dict(color='#f43f5e')))
                fig_nw.add_trace(
                    go.Scatter(x=df_sim["Age"], y=df_sim["Net Worth"], mode='lines', name='Total Net Worth',
                               line=dict(color='#111827', width=3, dash='dot')))
                fig_nw.update_layout(hovermode="x unified", yaxis=dict(tickformat="$,.0f"),
                                     margin=dict(l=0, r=0, t=30, b=0),
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_nw, use_container_width=True)

                st.write("#### Annual Cash Flow (Progressive Taxes Modeled)")
                fig_cf = go.Figure()
                fig_cf.add_trace(go.Scatter(x=df_sim["Age"], y=df_sim["Annual Income"], mode='lines', name='Income',
                                            line=dict(color='#4f46e5', width=3)))
                fig_cf.add_trace(go.Scatter(x=df_sim["Age"], y=df_sim["Annual Expenses"], mode='lines', name='Expenses',
                                            line=dict(color='#f43f5e', width=3)))
                fig_cf.add_trace(go.Scatter(x=df_sim["Age"], y=df_sim["Annual Taxes"], mode='lines', name='Taxes',
                                            line=dict(color='#f59e0b', width=3)))
                fig_cf.update_layout(hovermode="x unified", yaxis=dict(tickformat="$,.0f"),
                                     margin=dict(l=0, r=0, t=30, b=0),
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_cf, use_container_width=True)

            st.divider()
            csv = df_sim.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download Full Simulation (.csv)", data=csv,
                               file_name='retirement_simulation.csv', mime='text/csv', type="secondary")

            st.subheader("Granular Tax & Expense Audit Logs")
            df_det = pd.DataFrame(detailed_results).fillna(0)
            inc_c = sorted([c for c in df_det.columns if c.startswith("Income:")])
            exp_c = sorted([c for c in df_det.columns if c.startswith("Expense:")])
            ord_det = ["Age", "Year"] + inc_c + exp_c + ["Net Savings"]
            st.dataframe(df_det[ord_det].set_index("Age").style.format(
                {c: "${:,.0f}" for c in ord_det if c not in ["Age", "Year"]} | {"Year": "{:.0f}"}),
                use_container_width=True)

# --- FINAL SAVE CORE ---
st.markdown("---")
if st.button("🚀 Finalize & Save Complete Profile to Secure Cloud", type="primary", use_container_width=True,
             key="save_main") or save_requested:
    if st.session_state['user_email'] == "guest_demo":
        st.error("Cannot save data in Guest Demo Mode.")
    else:
        def clean(df, k):
            if df.empty: return []
            rows = df[df[k].astype(str) != ""].to_dict('records')
            for r in rows:
                for vk, vv in r.items():
                    if pd.isna(vv): r[vk] = None
            return rows


        user_data = {
            "personal_info": {"name": my_name, "dob": my_dob.strftime("%Y-%m-%d"), "age": my_age, "retire_age": ret_age,
                              "spouse_retire_age": s_ret_age, "my_life_exp": my_life_exp_val,
                              "spouse_life_exp": spouse_life_exp_val, "current_city": curr_city,
                              "has_spouse": has_spouse,
                              "spouse_name": spouse_name,
                              "spouse_dob": spouse_dob.strftime("%Y-%m-%d") if has_spouse else None,
                              "spouse_age": spouse_age, "kids": kids_data},
            "retire_city": ret_city, "income": clean(edited_inc, "Description"),
            "real_estate": clean(edited_re, "Property Name"), "business": clean(edited_biz, "Business Name"),
            "liquid_assets": clean(edited_ast, "Account Name"), "liabilities": clean(edited_debt, "Debt Name"),
            "current_expenses": clean(edited_c, "Description"), "one_time_events": clean(edited_m, "Description"),
            "retire_expenses": clean(edited_r, "Description"),
            "assumptions": {**st.session_state['assumptions'], "inflation": infl, "inflation_healthcare": infl_hc,
                            "inflation_education": infl_ed, "market_growth": mkt, "income_growth": inc_g,
                            "property_growth": prop_g, "rent_growth": rent_g, "current_tax_rate": cur_t,
                            "retire_tax_rate": ret_t}
        }
        db.collection('users').document(st.session_state['user_email']).set(user_data, merge=True)
        st.session_state['user_data'] = user_data
        st.success("✅ Complete Financial Blueprint Securely Saved!")