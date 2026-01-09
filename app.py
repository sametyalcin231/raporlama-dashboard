# -*- coding: utf-8 -*-
import os, json
from io import BytesIO
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from filelock import FileLock
from streamlit_autorefresh import st_autorefresh

from toplama import run_report as run_toplama
from yerlestirme import run_report as run_yerlestirme
from backlog import run_report as run_backlog

# =====================================================
# ENV
# =====================================================
load_dotenv()

ACTIVE_USERS_FILE = "active_users.json"
ACTIVE_WINDOW_SECONDS = 120  # 2 dk aktiflik penceresi

# =====================================================
# AUTO REFRESH 1 DK
# =====================================================
st_autorefresh(interval=60 * 1000, key="auto_refresh")

# =====================================================
# PAGE
# =====================================================
st.set_page_config(page_title="Operasyon Dashboard", layout="wide")
st.sidebar.title("📊 Operasyon Dashboard")

# =====================================================
# AKTİF KULLANICI
# =====================================================
lock = FileLock(f"{ACTIVE_USERS_FILE}.lock")
now = datetime.now()

with lock:
    if os.path.exists(ACTIVE_USERS_FILE):
        with open(ACTIVE_USERS_FILE, "r", encoding="utf-8") as f:
            active_users = json.load(f)
    else:
        active_users = {}

    # Örnek kullanıcı: "Ziyaretçi"
    active_users["Ziyaretçi"] = now.strftime("%Y-%m-%d %H:%M:%S")

    # eski kullanıcıları temizle
    cleaned = {}
    for u, t in active_users.items():
        try:
            t_dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            if now - t_dt < timedelta(seconds=ACTIVE_WINDOW_SECONDS):
                cleaned[u] = t
        except:
            pass

    with open(ACTIVE_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4)

active_users = cleaned

# =====================================================
# CACHE
# =====================================================
@st.cache_data(ttl=120)
def get_toplama():
    return run_toplama()

@st.cache_data(ttl=120)
def get_yerlestirme():
    return run_yerlestirme()

@st.cache_data(ttl=300)
def get_backlog_safe():
    try:
        return run_backlog()
    except Exception:
        return pd.DataFrame(), {}, None

last_update_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

# =====================================================
# MENU
# =====================================================
menu_items = ["👷 Toplama", "📦 Yerleştirme", "📈 Backlog", "🔑 Admin Paneli"]
selected_tab = st.sidebar.radio("Menü Seç", menu_items)

# =====================================================
# ORTAK TOPLAM SATIRI SABİTLEYİCİ
# =====================================================
def move_total_bottom(df):
    name_col = df.columns[0]
    total_row = df[df[name_col].astype(str).str.upper() == "TOPLAM"]
    df = df[df[name_col].astype(str).str.upper() != "TOPLAM"]
    return pd.concat([df, total_row])

# =====================================================
# ANALYTICS PANEL (detay ve KPI)
# =====================================================
def show_analytics(df, saat_cols, max_value_divisor=50):
    # KPI hesapla
    for c in saat_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        df[f"{c} KPI"] = (df[c] / max_value_divisor * 100).clip(0, 100).astype(int)

    toplam_adet = df[saat_cols].sum().sum()
    kpi_mean = df[[f"{c} KPI" for c in saat_cols]].mean().mean()
    calisan_sayisi = df[df[df.columns[0]].astype(str).str.upper() != "TOPLAM"][df.columns[0]].nunique()

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Adet", int(toplam_adet))
    c2.metric("Ortalama KPI", int(round(kpi_mean)))
    c3.metric("Çalışan Sayısı", calisan_sayisi)

    if st.checkbox("📊 Grafik Göster"):
        st.bar_chart(df.set_index(df.columns[0])[saat_cols])

    st.subheader("👥 Çalışan Bazlı Toplam")
    st.dataframe(pd.DataFrame({
        "Çalışan": df[df.columns[0]],
        "Toplam Adet": df[saat_cols].sum(axis=1)
    }))

    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    st.download_button("⬇ Excel İndir", buffer, f"{df.columns[0]}_raporu.xlsx")

# =====================================================
# TOPLAMA
# =====================================================
if selected_tab == "👷 Toplama":
    st.header("👷 Toplama KPI")
    st.caption(f"🕒 Son Güncelleme: {last_update_time}")

    df = get_toplama()
    if not df.empty:
        df = move_total_bottom(df)
        saat_cols = [c for c in df.columns if ":" in c]
        show_analytics(df, saat_cols, max_value_divisor=50)
    else:
        st.warning("Veri yok")

# =====================================================
# YERLEŞTİRME
# =====================================================
elif selected_tab == "📦 Yerleştirme":
    st.header("📦 Yerleştirme KPI")
    st.caption(f"🕒 Son Güncelleme: {last_update_time}")

    df = get_yerlestirme()
    if not df.empty:
        df = move_total_bottom(df)
        saat_cols = [c for c in df.columns if ":" in c]
        show_analytics(df, saat_cols, max_value_divisor=100)
    else:
        st.warning("Veri yok")

# =====================================================
# BACKLOG
# =====================================================
elif selected_tab == "📈 Backlog":
    st.header("📈 Backlog Durumu")
    st.caption(f"🕒 Son Güncelleme: {last_update_time}")

    pivot, totals, _ = get_backlog_safe()
    if not pivot.empty:
        st.dataframe(pivot)
    else:
        st.warning("Backlog verisi yok")

# =====================================================
# ADMIN PANEL
# =====================================================
elif selected_tab == "🔑 Admin Paneli":
    st.header("🔑 Admin Paneli")

    st.metric("🟢 Online Kullanıcı", len(active_users))
    st.table(pd.DataFrame([
        {"Kullanıcı": u, "Son Görülme": t}
        for u, t in active_users.items()
    ]))
