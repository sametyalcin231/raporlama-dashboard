# -*- coding: utf-8 -*-
import os
import time
import shutil
import re
import logging
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv

# ===============================
# ENV
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

ECOM_USERNAME = os.getenv("ECOM_USERNAME")
ECOM_PASSWORD = os.getenv("ECOM_PASSWORD")

# ===============================
# LOG
# ===============================
logging.basicConfig(
    filename="yerlestirme_rapor.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===============================
# OTOMATİK VARDİYA
# ===============================
def aktif_vardiya():
    saat = datetime.now().hour
    if 8 <= saat < 16:
        return "Sabah"
    elif 16 <= saat < 24:
        return "Öğlen"
    else:
        return "Gece"

# ===============================
# TARİH FORMAT
# ===============================
def bugun_html_date():
    return datetime.now().strftime("%Y-%m-%d")

# ===============================
# SAAT OKUMA
# ===============================
def saat_al(deger):
    if pd.isna(deger):
        return None
    m = re.search(r'(\d{1,2})', str(deger))
    if m:
        s = int(m.group(1))
        if 0 <= s <= 23:
            return s
    return None

def vardiya_araliginda_mi(saat, vardiya):
    if saat is None:
        return False
    if vardiya == "Sabah":
        return 8 <= saat < 16
    if vardiya == "Öğlen":
        return 16 <= saat <= 23
    if vardiya == "Gece":
        return 0 <= saat < 8
    return False

# ===============================
# EXCEL
# ===============================
def indirilen_excel_bul():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    start = time.time()
    while time.time() - start < 60:
        f = [x for x in os.listdir(d) if x.endswith(".xlsx")]
        if f:
            f.sort(key=lambda x: os.path.getctime(os.path.join(d, x)))
            return os.path.join(d, f[-1])
        time.sleep(1)
    raise Exception("Excel indirilemedi")

def excel_guvenli_kopya(path):
    yeni = path.replace(".xlsx", "_ORJ.xlsx")
    shutil.copy(path, yeni)
    return yeni

def excel_duzenle(path, vardiya):
    df = pd.read_excel(path)
    kisi_col = df.columns[0]

    saat_cols = []
    for col in df.columns[1:]:
        s = saat_al(col)
        if vardiya_araliginda_mi(s, vardiya):
            saat_cols.append(col)

    if not saat_cols:
        raise Exception("Vardiya saat kolonları bulunamadı")

    yeni_df = df[[kisi_col] + saat_cols].copy()

    for c in saat_cols:
        yeni_df[c] = pd.to_numeric(yeni_df[c], errors="coerce").fillna(0).astype(int)

    yeni_df["Toplam Adet"] = yeni_df[saat_cols].sum(axis=1).astype(int)
    yeni_df = yeni_df[yeni_df["Toplam Adet"] > 0]
    yeni_df = yeni_df.sort_values("Toplam Adet", ascending=False)

    toplam = int(yeni_df["Toplam Adet"].sum())

    toplam_satir = {kisi_col: "TOPLAM"}
    for c in saat_cols:
        toplam_satir[c] = ""
    toplam_satir["Toplam Adet"] = toplam

    yeni_df = pd.concat([yeni_df, pd.DataFrame([toplam_satir])], ignore_index=True)

    return yeni_df, toplam

# ===============================
# TARİH SET
# ===============================
def tarih_set(driver, element_id, tarih):
    driver.execute_script("""
        var el = document.getElementById(arguments[0]);
        el.removeAttribute('readonly');
        el.removeAttribute('disabled');
        el.value = arguments[1];
        el.dispatchEvent(new Event('change', { bubbles: true }));
    """, element_id, tarih)

# ===============================
# ANA RAPOR MOTORU
# ===============================
def run_report():
    """
    Yerleştirme raporunu çalıştırır, DataFrame ve toplam adet döner.
    Streamlit dashboard içinde kullanılacak.
    """
    driver = None
    vardiya = aktif_vardiya()

    try:
        logging.info(f"Rapor başlıyor – {vardiya}")

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 60)

        driver.get("https://ecomweb.sertrans.com.tr/Login")
        wait.until(EC.presence_of_element_located((By.ID, "fldUserName"))).send_keys(ECOM_USERNAME)
        driver.find_element(By.ID, "fldPassword").send_keys(ECOM_PASSWORD)
        driver.find_element(By.XPATH, "//a[contains(text(),'Giriş')]").click()
        time.sleep(5)

        driver.get("https://ecomweb.sertrans.com.tr/Reports/UserBasedHourlyInboundOrdersPerformance/295")

        tarih_set(driver, "fldFirstDate", bugun_html_date())
        time.sleep(1)

        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Kayıtları Getir')]"))).click()
        time.sleep(5)

        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@aria-label='xlsxfile']"))).click()
        time.sleep(5)

        excel = indirilen_excel_bul()
        guvenli = excel_guvenli_kopya(excel)

        df, toplam = excel_duzenle(guvenli, vardiya)

        logging.info("Rapor başarıyla tamamlandı")
        return df

    except Exception as e:
        logging.error(str(e))
        return pd.DataFrame()

    finally:
        if driver:
            driver.quit()