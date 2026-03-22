import re
import time
import csv
import random
import os
import platform
import requests
import zipfile
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By


all_emails = set()

def is_geckodriver_installed():
    driver_path = "C:\\geckodriver\\geckodriver.exe"
    if os.path.exists(driver_path):
        print(f"Geckodriver found at: {driver_path}")
        return driver_path
    print("Geckodriver not found.")
    return None

def download_geckodriver():
    if platform.system().lower() != "windows":
        print("This script supports only Windows.")
        return None
    gecko_url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win64.zip"
    zip_path = "geckodriver.zip"
    print("Downloading geckodriver...")
    response = requests.get(gecko_url, stream=True)
    with open(zip_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)
    os.makedirs("C:\\geckodriver", exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall("C:\\geckodriver")
    os.remove(zip_path)
    print("Geckodriver installed successfully.")
    return "C:\\geckodriver\\geckodriver.exe"

def check_and_install_geckodriver():
    driver_path = is_geckodriver_installed()
    return driver_path or download_geckodriver()

def is_captcha_present(driver):
    captcha_elements = [
        (By.CLASS_NAME, "g-recaptcha"),
        (By.TAG_NAME, "iframe[src*='recaptcha']"),
        (By.ID, "recaptcha-anchor"),
    ]
    for by, value in captcha_elements:
        if driver.find_elements(by, value):
            return True
    return False

def wait_for_captcha_resolution(driver, timeout=60, check_interval=3):
    print("Waiting for CapMonster Cloud to solve CAPTCHA...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_captcha_present(driver):
            print("CAPTCHA solved. Resuming scraping...")
            return True
        time.sleep(check_interval)
    print("CAPTCHA not solved within timeout.")
    return False

def save_last_url(url):
    with open("last_url.txt", "w") as f:
        f.write(url)

def load_last_url():
    if os.path.exists("last_url.txt"):
        with open("last_url.txt", "r") as f:
            return f.read().strip()
    return None

def initialize_driver(geckodriver_path, headless=False):
    options = Options()
    options.headless = headless
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0")
    extension_path = os.path.abspath("capmonster_cloud-1.2.0.xpi")
    if not os.path.exists(extension_path):
        print(f"CapMonster extension not found at {extension_path}. Exiting.")
        exit(1)
    print("Installing CapMonster Cloud extension...")
    driver = webdriver.Firefox(service=Service(geckodriver_path), options=options)
    driver.install_addon(extension_path, temporary=True)
    return driver

def enter_api_key(driver):
    API_KEY = "28a1451d3a8ea6763bc3049e15fb0bb4"  # Replace with your actual CapMonster API key
    try:
        print("Attempting to enter CapMonster API key...")
        driver.get("moz-extension://<extension-id>/options.html")  # Replace <extension-id> if known, or use next steps
        time.sleep(2)  # Wait for extension page to load
        api_input = driver.find_element(By.XPATH, '//*[@id="client-key-input"]')
        api_input.clear()
        api_input.send_keys(API_KEY)
        print("API key entered successfully.")
        time.sleep(1)  # Allow settings to save
    except Exception as e:
        print(f"Error entering API key: {e}")
        print("Please ensure the CapMonster extension settings page is accessible.")

def extract_emails(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@gmail\.com'
    emails = re.findall(email_pattern, text)
    return [email for email in emails if email not in all_emails]

def extract_area_from_url(url):
    if "gmail.com" in url:
        match = re.search(r'%22gmail\.com%22\+%22(.+?)%22', url)
        if match:
            return match.group(1).replace("+", " ")
    return "Unknown"

def scrape_urls(driver, urls, geckodriver_path, start_url=None):
    output_file = "surgeon_emails_by_area.csv"
    captcha_solve_count = 0
    max_captcha_solves = 5
    max_attempts = 2
    max_captcha_attempts = 3
    start_index = 0
    if start_url:
        try:
            start_index = urls.index(start_url)
        except ValueError:
            print(f"Last URL {start_url} not found. Starting from beginning.")
    with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if os.stat(output_file).st_size == 0:
            writer.writerow(["Email", "Area", "Profession"])
        for i in range(start_index, len(urls)):
            url = urls[i]
            area = extract_area_from_url(url)
            profession = "Unknown"
            collected_emails = set()
            new_emails_found = True
            attempt = 0
            captcha_attempts = 0
            save_last_url(url)
            print(f"Scraping: {area}")
            try:
                driver.get(url)
                while is_captcha_present(driver) and captcha_attempts < max_captcha_attempts:
                    print(f"CAPTCHA detected. Attempt {captcha_attempts + 1}/{max_captcha_attempts}")
                    if wait_for_captcha_resolution(driver):
                        captcha_solve_count += 1
                        print(f"Total CAPTCHAs solved: {captcha_solve_count}")
                        if captcha_solve_count >= max_captcha_solves:
                            print("Max CAPTCHA solves reached. Restarting.")
                            driver.quit()
                            new_driver = initialize_driver(geckodriver_path, headless=True)
                            enter_api_key(new_driver)
                            return scrape_urls(new_driver, urls, geckodriver_path, url)
                    else:
                        captcha_attempts += 1
                        time.sleep(random.uniform(1, 3))
                    if captcha_attempts >= max_captcha_attempts:
                        print(f"Failed to solve CAPTCHA after {max_captcha_attempts} attempts.")
                        break
                while new_emails_found and attempt < max_attempts:
                    page_source = driver.page_source
                    emails = extract_emails(page_source)
                    current_emails = set(emails)
                    new_emails = current_emails - collected_emails
                    collected_emails.update(new_emails)
                    if new_emails:
                        for email in new_emails:
                            all_emails.add(email)
                            writer.writerow([email, area, profession])
                            csvfile.flush()
                            print(f"Found and saved: {email} in {area}")
                    else:
                        new_emails_found = False
                        print(f"No new emails found for {area} after attempt {attempt + 1}")
                    attempt += 1
                    if attempt < max_attempts:
                        time.sleep(random.uniform(1, 3))
                if not collected_emails:
                    print(f"No emails found for {area}")
            except Exception as e:
                print(f"Error scraping {area}: {str(e)}")
                continue

def main():
    url_file = "professional_search_urls.txt"
    try:
        with open(url_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading URLs file: {e}")
        return
    geckodriver_path = check_and_install_geckodriver()
    if not geckodriver_path:
        print("Failed to install geckodriver. Exiting.")
        return
    driver = initialize_driver(geckodriver_path, headless=False)
  
    enter_api_key(driver)
    driver.quit()
    driver = initialize_driver(geckodriver_path, headless=True)
    enter_api_key(driver)
    print("Switched to headless mode.")
    try:
        last_url = load_last_url()
        scrape_urls(driver, urls, geckodriver_path, last_url)
    finally:
        driver.quit()
        print("Scraping complete. Results saved to surgeon_emails_by_area.csv")

if __name__ == "__main__":
    main()