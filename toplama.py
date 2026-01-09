# -*- coding: utf-8 -*-
import os
import time
import logging
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ===============================
# ENV
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

ECOM_USERNAME = os.getenv("ECOM_USERNAME")
ECOM_PASSWORD = os.getenv("ECOM_PASSWORD")

LOGIN_URL = "https://ecomweb.sertrans.com.tr/Login"
REPORT_URL = "https://ecomweb.sertrans.com.tr/Reports/PersonBasedHourlyPickingPerformance/295"

# ===============================
# LOG
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S"
)
log = logging.getLogger("TOPLAMA")

# ===============================
# VARDİYA TANIMI
# ===============================
def aktif_vardiya():
    h = datetime.now().hour
    if 0 <= h < 8:
        return "GECE", list(range(0, 8))
    elif 8 <= h < 16:
        return "GÜNDÜZ", list(range(8, 16))
    else:
        return "AKŞAM", list(range(16, 24))

VARDIYA_ADI, AKTIF_SAATLER = aktif_vardiya()

# ===============================
# DRIVER (Cloud Uyumlu)
# ===============================
def get_driver():
    options = Options()
    options.add_argument("--headless=new")        # GUI olmadan çalıştır
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver

# ===============================
# GRID OKUMA
# ===============================
def read_grid(driver):
    time.sleep(6)

    headers = driver.execute_script("""
        return Array.from(
            document.querySelectorAll(".dx-datagrid-headers td")
        ).map(x => x.innerText.trim());
    """)

    rows = driver.execute_script("""
        return Array.from(
            document.querySelectorAll(".dx-data-row")
        ).map(r =>
            Array.from(r.querySelectorAll("td"))
                 .map(c => c.innerText.trim())
        );
    """)

    if not rows or not headers:
        return pd.DataFrame()

    min_len = min(len(headers), len(rows[0]))
    headers = headers[:min_len]
    rows = [r[:min_len] for r in rows]

    df = pd.DataFrame(rows, columns=headers)

    # 2. sütunu sil
    if df.shape[1] >= 2:
        df.drop(df.columns[1], axis=1, inplace=True)

    # Aktif vardiya saat kolonları
    saat_cols = []
    for c in df.columns[1:]:
        try:
            saat = int(c.split(":")[0])
            if saat in AKTIF_SAATLER:
                saat_cols.append(c)
        except:
            pass

    if not saat_cols:
        return pd.DataFrame()

    df = df[[df.columns[0]] + saat_cols]

    for c in saat_cols:
        df[c] = (
            pd.to_numeric(df[c].str.replace(",", ""), errors="coerce")
            .fillna(0)
            .astype(int)
        )

    # TOPLAM
    df["TOPLAM"] = df[saat_cols].sum(axis=1)
    df = df[df["TOPLAM"] > 0]
    df = df.sort_values("TOPLAM", ascending=False)

    # GENEL TOPLAM
    if not df.empty:
        toplam = int(df["TOPLAM"].sum())
        toplam_satiri = pd.DataFrame([{
            df.columns[0]: "GENEL TOPLAM",
            **{c: "" for c in df.columns[1:-1]},
            "TOPLAM": toplam
        }])
        df = pd.concat([df, toplam_satiri], ignore_index=True)

    return df

# ===============================
# RAPOR
# ===============================
def run_report():
    """
    Toplama raporunu çalıştırır, DataFrame döner.
    Streamlit dashboard içinde kullanılacak.
    """
    driver = get_driver()
    wait = WebDriverWait(driver, 60)

    try:
        log.info("Login")
        driver.get(LOGIN_URL)

        wait.until(EC.presence_of_element_located((By.ID, "fldUserName"))).send_keys(ECOM_USERNAME)
        driver.find_element(By.ID, "fldPassword").send_keys(ECOM_PASSWORD)
        driver.find_element(By.XPATH, "//a[contains(text(),'Giriş')]").click()
        wait.until(EC.url_contains("Home"))

        driver.get(REPORT_URL)

        today = datetime.now().strftime("%Y-%m-%d")

        driver.execute_script("""
            const d = arguments[0];
            ["fldFirstDate","fldEndDate"].forEach(id=>{
                const el=document.getElementById(id);
                el.value=d;
                el.dispatchEvent(new Event("change",{bubbles:true}));
            });
        """, today)

        wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(.,'Kayıtları Getir')]")
            )
        ).click()

        return read_grid(driver)

    except Exception as e:
        log.error(str(e))
        return pd.DataFrame()

    finally:
        driver.quit()

# ===============================
# Streamlit ile kullanım
# ===============================
if __name__ == "__main__":
    import streamlit as st

    st.set_page_config(page_title="Toplama Raporu", layout="wide")
    st.title("Toplama Raporu")

    st.info(f"Aktif Vardiya: {VARDIYA_ADI}")

    with st.spinner("Rapor alınıyor..."):
        df = run_report()

    if df.empty:
        st.warning("Rapor alınamadı veya veri yok.")
    else:
        st.dataframe(df)
        csv_file = f"toplama_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(csv_file, index=False)
        st.download_button("CSV olarak indir", csv_file, file_name=csv_file)
