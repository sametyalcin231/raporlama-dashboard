# -*- coding: utf-8 -*-
import os
import glob
import time
import logging
from datetime import datetime, timedelta
from configparser import ConfigParser

import pandas as pd
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =====================================================
# PATHS
# =====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")

LOG_DIR = os.path.join(BASE_DIR, "logs")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "output", "downloads")
REPORT_DIR = os.path.join(BASE_DIR, "output", "reports")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "backlog.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S"
)
log = logging.getLogger("BACKLOG")

# =====================================================
# CONFIG
# =====================================================
config = ConfigParser()
if not os.path.exists(CONFIG_PATH):
    config["GENERAL"] = {
        "days": "30",
        "interval_minutes": "10"
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)
    log.info("config.ini otomatik oluşturuldu")

config.read(CONFIG_PATH, encoding="utf-8")
DAYS = config.getint("GENERAL", "days", fallback=30)

# =====================================================
# ENV
# =====================================================
load_dotenv()
ECOM_URL_LOGIN = "https://ecomweb.sertrans.com.tr/Login"
ECOM_URL_OUTBOUND = (
    "https://ecomweb.sertrans.com.tr/OutboundOrder/"
    "OutboundOrderList?fldUserWarehouseCompanyId=295&parentid=119"
)
USERNAME = os.getenv("ECOM_USERNAME", "")
PASSWORD = os.getenv("ECOM_PASSWORD", "")

# =====================================================
# SELENIUM
# =====================================================
def login_and_export(start_date: str, end_date: str) -> None:
    log.info("Login başlatıldı")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False
        }
    )

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    try:
        driver.get(ECOM_URL_LOGIN)
        wait.until(EC.visibility_of_element_located((By.ID, "fldUserName"))).send_keys(USERNAME)
        wait.until(EC.visibility_of_element_located((By.ID, "fldPassword"))).send_keys(PASSWORD)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn.btn-lg.btn-primary"))).click()
        wait.until(EC.url_contains("/Home/Index"))
        log.info("Login başarılı")

        driver.get(ECOM_URL_OUTBOUND)

        start_el = wait.until(EC.visibility_of_element_located((By.ID, "fldStartDate")))
        end_el = wait.until(EC.visibility_of_element_located((By.ID, "fldEndDate")))

        start_el.clear()
        end_el.clear()
        start_el.send_keys(start_date)
        end_el.send_keys(end_date)

        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Kayıtları Getir')]"))).click()
        log.info("Kayıtlar getirildi")

        export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".dx-datagrid-export-button")))
        driver.execute_script("arguments[0].click();", export_btn)
        log.info("Excel export alındı")
        time.sleep(10)

    finally:
        driver.quit()
        log.info("Tarayıcı kapatıldı")

# =====================================================
# UTILS
# =====================================================
def latest_xlsx() -> str:
    files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.xlsx"))
    if not files:
        raise RuntimeError("Excel dosyası bulunamadı")
    return max(files, key=os.path.getctime)

# =====================================================
# REPORT
# =====================================================
def build_report(df: pd.DataFrame):
    df = df.rename(columns={
        df.columns[1]: "SiparisTarihi",
        df.columns[6]: "Miktar",
        df.columns[11]: "Statu"
    })

    df["SiparisTarihi"] = pd.to_datetime(df["SiparisTarihi"], errors="coerce")
    df["Statu"] = (
        df["Statu"].astype(str).str.strip().replace({
            "Henüz aktif edilmedi": "İşlem Bekliyor",
            "Toplama iş emri oluşturuldu": "Toplama İş Emri Oluşturuldu",
            "Toplandı": "Toplandı"
        })
    )
    df = df[df["Statu"].isin(["İşlem Bekliyor", "Toplama İş Emri Oluşturuldu", "Toplandı"])]
    df["Miktar"] = pd.to_numeric(df["Miktar"], errors="coerce").fillna(0)

    detail_csv = os.path.join(REPORT_DIR, f"Backlog_Detail_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
    df.to_csv(detail_csv, index=False, encoding="utf-8-sig")

    pivot = (
        df.groupby([df["SiparisTarihi"].dt.date, "Statu"])["Miktar"]
        .sum()
        .reset_index()
        .pivot(index="SiparisTarihi", columns="Statu", values="Miktar")
        .fillna(0)
        .astype(int)
        .sort_index()
    )

    for col in ["İşlem Bekliyor", "Toplama İş Emri Oluşturuldu", "Toplandı"]:
        if col not in pivot.columns:
            pivot[col] = 0

    pivot = pivot[["İşlem Bekliyor", "Toplama İş Emri Oluşturuldu", "Toplandı"]]
    pivot["Günlük Toplam"] = pivot.sum(axis=1)

    totals = {
        "bekliyor": int(pivot["İşlem Bekliyor"].sum()),
        "toplama": int(pivot["Toplama İş Emri Oluşturuldu"].sum()),
        "toplandi": int(pivot["Toplandı"].sum())
    }
    totals["genel"] = totals["bekliyor"] + totals["toplama"] + totals["toplandi"]

    pivot.index = pivot.index.map(lambda d: d.strftime("%d.%m.%Y"))
    pivot.reset_index(inplace=True)
    pivot.rename(columns={"SiparisTarihi": "Sipariş Tarihi"}, inplace=True)

    return pivot, totals, detail_csv

# =====================================================
# MAIN ENTRY FOR DASHBOARD
# =====================================================
def run_report():
    """
    Backlog raporunu çalıştırır, pivot tablo ve totals döner.
    Streamlit dashboard içinde kullanılacak.
    """
    end = datetime.now()
    start = end - timedelta(days=DAYS)

    login_and_export(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    df = pd.read_excel(latest_xlsx(), engine="openpyxl")
    pivot, totals, csv_path = build_report(df)
    return pivot, totals, csv_path