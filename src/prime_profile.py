"""
One-time script to prime a native Linux Chrome profile on a remote server.
It launches Chrome in headless mode, visits Google Maps, accepts the consent dialog,
and persists the native Linux cookies to `chrome-profile`.
"""

import os
import time
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_PROFILE = os.path.join(PROJECT_ROOT, "chrome-profile")

def prime():
    print(f"[Priming] Target directory: {MASTER_PROFILE}")
    os.makedirs(MASTER_PROFILE, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-data-dir={MASTER_PROFILE}")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US")

    print("[Priming] Launching Chrome...")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        # Step 1: Open Google Maps
        print("[Priming] Navigating to Google Maps...")
        driver.get("https://www.google.com/maps")
        time.sleep(3)

        print(f"[Priming] Current URL: {driver.current_url}")
        print(f"[Priming] Page Title: {driver.title}")

        # Step 2: Handle any consent dialogs or redirects
        print("[Priming] Checking for consent dialog...")
        accepted = False
        
        # Click button on consent.google.com or in-page modal
        consent_xpaths = [
            "//button[contains(., 'Accept all')]",
            "//button[contains(., 'I agree')]",
            "//button[contains(., 'Agree')]",
            "//button[contains(., 'Tout accepter')]",
            "//button[contains(., 'Alle akzeptieren')]",
            "//form//button",
        ]
        
        for xpath in consent_xpaths:
            buttons = driver.find_elements(By.XPATH, xpath)
            if buttons:
                print(f"[Priming] Found consent button ({xpath}). Clicking...")
                buttons[0].click()
                accepted = True
                time.sleep(3)
                break

        # Step 3: Inject Google's global GDPR accept-all cookie (SOCS) as backup
        try:
            driver.add_cookie({
                "name": "SOCS",
                "value": "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3AwGgJlbiACGgYIgLCtpgY",
                "domain": ".google.com",
                "path": "/"
            })
            print("[Priming] Injected global SOCS consent cookie.")
        except Exception as e:
            print(f"[Priming] Could not inject cookie: {e}")

        # Step 4: Re-visit Maps to verify feed or search box is present
        driver.get("https://www.google.com/maps/search/restaurants/@6.45,3.40,15z")
        time.sleep(4)
        print(f"[Priming] Post-consent URL: {driver.current_url}")
        print(f"[Priming] Post-consent Page Title: {driver.title}")

        if "consent.google" not in driver.current_url:
            print("\n[Priming] ✅ SUCCESS! Native Linux cookies have been saved to 'chrome-profile'.")
        else:
            print("\n[Priming] ⚠️ Still on consent page. Check output above.")

    finally:
        driver.quit()

if __name__ == "__main__":
    prime()
