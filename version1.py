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
from win10toast import ToastNotifier
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from bs4 import BeautifulSoup
from uuid import uuid4

# Thread-safe set for tracking emails
all_emails = set()
email_lock = Lock()

def is_geckodriver_installed():
    """Check if geckodriver is installed and accessible."""
    try:
        driver_path = "C:\\geckodriver\\geckodriver.exe"
        if os.path.exists(driver_path):
            print(f"Geckodriver found at: {driver_path}")
            return driver_path
        else:
            print("Geckodriver not found.")
            return None
    except Exception as e:
        print(f"Error checking geckodriver: {e}")
        return None

def download_geckodriver():
    """Download and extract geckodriver."""
    system = platform.system().lower()
    if system == "windows":
        gecko_url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win64.zip"
        zip_path = "geckodriver.zip"
    else:
        print("This script currently supports only Windows.")
        return None
    
    print("Downloading geckodriver...")
    response = requests.get(gecko_url, stream=True)
    with open(zip_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            file.write(chunk)
    
    print("Extracting geckodriver...")
    os.makedirs("C:\\geckodriver", exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall("C:\\geckodriver")
    
    os.remove(zip_path)
    print("Geckodriver installed successfully.")
    return "C:\\geckodriver\\geckodriver.exe"

def check_and_install_geckodriver():
    """Check if geckodriver is installed; download if not."""
    driver_path = is_geckodriver_installed()
    if driver_path:
        return driver_path
    else:
        return download_geckodriver()

def is_captcha_present(driver):
    """Check if a CAPTCHA is present on the page."""
    try:
        captcha_elements = [
            (By.CLASS_NAME, "g-recaptcha"),
            (By.TAG_NAME, "iframe[src*='recaptcha']"),
            (By.ID, "recaptcha-anchor"),
        ]
        for by, value in captcha_elements:
            if driver.find_elements(by, value):
                return True
        return False
    except Exception as e:
        print(f"Error checking for CAPTCHA: {e}")
        return False

def wait_for_captcha_resolution(driver, timeout=30, check_interval=3):
    """Wait until the CAPTCHA is solved by the extension or timeout is reached."""
    print("Waiting for CapMonster Cloud extension to solve CAPTCHA...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if not is_captcha_present(driver):
            print("CAPTCHA solved by extension. Resuming scraping...")
            return True
        time.sleep(check_interval)
    
    print("CAPTCHA not solved within timeout period.")
    return False

def save_last_url(url):
    """Save the last processed URL to a file."""
    try:
        with open("last_url.txt", "w") as f:
            f.write(url)
    except Exception as e:
        print(f"Error saving last URL: {e}")

def load_last_url():
    """Load the last processed URL from a file."""
    try:
        if os.path.exists("last_url.txt"):
            with open("last_url.txt", "r") as f:
                return f.read().strip()
    except Exception as e:
        print(f"Error loading last URL: {e}")
    return None

def initialize_driver(geckodriver_path, headless=True):
    """Initialize Firefox WebDriver with CapMonster extension."""
    options = Options()
    options.headless = headless
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0")
    # Disable images and CSS for faster loading
    options.set_preference("permissions.default.image", 2)
    options.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", "false")
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    
    extension_path = os.path.abspath("capmonster_cloud-1.2.0.xpi")
    if not os.path.exists(extension_path):
        print(f"CapMonster extension not found at {extension_path}. Exiting.")
        exit(1)
    
    print("Installing CapMonster Cloud extension...")
    driver = webdriver.Firefox(service=Service(geckodriver_path), options=options)
    driver.install_addon(extension_path, temporary=True)
    return driver

def extract_emails(text):
    """Extract valid outlook.com emails from text."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@outlook\.com'
    emails = re.findall(email_pattern, text)
    valid_emails = []
    with email_lock:
        for email in emails:
            if email not in all_emails:
                all_emails.add(email)
                valid_emails.append(email)
    return valid_emails

def extract_area_from_url(url):
    """Extract area name from URL."""
    if "outlook.com" in url:
        match = re.search(r'%22outlook\.com%22\+%22(.+?)%22', url)
        if match:
            return match.group(1).replace("+", " ")
    return "Unknown"

def scrape_single_url(url, geckodriver_path, csv_writer, csv_lock):
    """Scrape a single URL and write results to CSV."""
    area = extract_area_from_url(url)
    profession = "Unknown"
    collected_emails = set()
    max_attempts = 2
    max_captcha_attempts = 2
    captcha_attempts = 0
    attempt = 0
    new_emails_found = True

    # Initialize driver for this thread
    driver = initialize_driver(geckodriver_path, headless=True)
    results = []

    try:
        print(f"Scraping: {area}")
        save_last_url(url)
        driver.get(url)

        # Handle CAPTCHA
        while is_captcha_present(driver) and captcha_attempts < max_captcha_attempts:
            print(f"CAPTCHA detected for {area}. Attempt {captcha_attempts + 1}/{max_captcha_attempts}")
            if wait_for_captcha_resolution(driver, timeout=30):
                print(f"CAPTCHA solved for {area}")
            else:
                captcha_attempts += 1
                time.sleep(random.uniform(0.5, 2))
            
            if captcha_attempts >= max_captcha_attempts:
                print(f"Failed to solve CAPTCHA for {area} after {max_captcha_attempts} attempts.")
                break

        # Scrape emails
        while new_emails_found and attempt < max_attempts:
            page_source = driver.page_source
            emails = extract_emails(page_source)
            current_emails = set(emails)
            new_emails = current_emails - collected_emails
            collected_emails.update(new_emails)

            if new_emails:
                for email in new_emails:
                    results.append([email, area, profession])
                    print(f"Found: {email} in {area}")
            else:
                new_emails_found = False
                print(f"No new emails found for {area} after attempt {attempt + 1}")

            attempt += 1
            if attempt < max_attempts:
                time.sleep(random.uniform(0.5, 2))

        if not collected_emails:
            print(f"No emails found for {area}")

        # Write results to CSV
        with csv_lock:
            for result in results:
                csv_writer.writerow(result)

    except Exception as e:
        print(f"Error scraping {area}: {str(e)}")
    finally:
        driver.quit()

def scrape_urls(urls, geckodriver_path, start_url=None):
    """Scrape URLs in parallel using ThreadPoolExecutor."""
    output_file = "surgeon_emails_by_area.csv"
    csv_lock = Lock()
    max_workers = 4  # Adjust based on system/server limits

    # Determine start index
    start_index = 0
    if start_url:
        try:
            start_index = urls.index(start_url)
        except ValueError:
            print(f"Last URL {start_url} not found in URL list. Starting from beginning.")

    # Initialize CSV file
    with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if os.stat(output_file).st_size == 0:
            writer.writerow(["Email", "Area", "Profession"])
            csvfile.flush()

        # Process URLs in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(scrape_single_url, url, geckodriver_path, writer, csv_lock)
                for url in urls[start_index:]
            ]
            for future in futures:
                future.result()  # Wait for all threads to complete
        csvfile.flush()

def main():
    """Main function to run the scraper."""
    # Read URLs
    url_file = "professional_search_urls.txt"
    try:
        with open(url_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading URLs file: {e}")
        return

    # Setup geckodriver
    geckodriver_path = check_and_install_geckodriver()
    if not geckodriver_path:
        print("Failed to install geckodriver. Exiting.")
        return

    # Initialize driver (non-headless for API key entry)
    driver = initialize_driver(geckodriver_path, headless=False)

    # Show Windows notification for API key
    toaster = ToastNotifier()
    toaster.show_toast(
        "CapMonster API Key",
        "Please enter your CapMonster API key in the extension within 10 seconds.",
        duration=10,
        threaded=True
    )

    print("Waiting 10 seconds for API key configuration...")
    time.sleep(10)

    # Close initial driver and start scraping
    driver.quit()
    print("Starting parallel scraping in headless mode.")
    try:
        last_url = load_last_url()
        scrape_urls(urls, geckodriver_path, last_url)
    finally:
        print("\nScraping complete. Results saved to surgeon_emails_by_area.csv")

if __name__ == "__main__":
    main()