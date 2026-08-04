import argparse
import csv
import os
import re
import shutil
import time
import queue
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


from h3_utils import get_target_h3s, get_center

SEARCH_TYPES = [
    "restaurants",
    "banks",
    "gas stations",
    "hotels",
]

def load_target_h3s(csv_path=None):
    """Load target H3 indices from the shared input CSV (h3 column only)."""
    cells = get_target_h3s(csv_path)
    return [{"h3_index": cell} for cell in cells]

def create_driver(profile_path, headless=True):
    options = webdriver.ChromeOptions()
    
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--start-maximized")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--user-data-dir={profile_path}")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver


def open_location(driver, lat, lng):
    driver.get(f"https://www.google.com/maps/@{lat},{lng},15z")


def search(driver, query):

    wait = WebDriverWait(driver, 20)

    # Close any open place detail card left over from previous searches
    try:
        close_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Close']")
        close_btn.click()
        time.sleep(1)
    except Exception:
        pass

    search_box = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[name='q']")
        )
    )

    search_box.click()

    search_box.send_keys(Keys.COMMAND + "a" if driver.capabilities.get('platformName') in ['mac', 'darwin'] else Keys.CONTROL + "a")
    search_box.send_keys(Keys.BACKSPACE)
    search_box.clear()

    search_box.send_keys(query)
    search_box.send_keys(Keys.ENTER)

    # wait for results pane with fallback retry
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[role='feed']")
            )
        )
    except TimeoutException:
        # Re-submit ENTER key press if feed didn't appear on first attempt
        search_box.send_keys(Keys.ENTER)
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[role='feed']")
            )
        )

    time.sleep(2)

    return scrape_results(driver, query)

def scroll_results(driver):
    pane = driver.find_element(
        By.CSS_SELECTOR,
        "div[role='feed']"
    )

    previous = 0
    unchanged_count = 0
    max_unchanged = 3  # Must see same height 3 times in a row before stopping

    while True:
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight",
            pane
        )

        time.sleep(3)  # Give headless Chrome time to render new results

        current = driver.execute_script(
            "return arguments[0].scrollHeight",
            pane
        )

        if current == previous:
            unchanged_count += 1
            if unchanged_count >= max_unchanged:
                break  # Truly at the end
        else:
            unchanged_count = 0  # Reset counter if height changed

        previous = current


def parse_price(price):

    digits = re.sub(r"[^\d]", "", price)

    if digits:
        return int(digits)

    return None

def close_place(driver):

    wait = WebDriverWait(driver, 20)

    close_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "button[aria-label='Close']"
            )
        )
    )

    close_button.click()

    wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "div[role='feed']"
            )
        )
    )


def scrape_place(driver, place_name, hotel=False):

    wait = WebDriverWait(driver, 20)

    plus_code = None
    hotel_price = None

    wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "div.Io6YTe"
            )
        )
    )

    elements = driver.find_elements(
        By.CSS_SELECTOR,
        "div.Io6YTe"
    )

    for e in elements:

        text = e.text.strip()

        if re.search(r'[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}', text):
            plus_code = text
            break

    if hotel:

        try:

            price = driver.find_element(
                By.CSS_SELECTOR,
                "span.fontTitleLarge.Cbys4b"
            )

            hotel_price = parse_price(price.text)

        except:
            hotel_price = None

    return {
        "name": place_name,
        "plus_code": plus_code,
        "hotel_price": hotel_price
    }


def search_place_by_name(driver, name, hotel=False):

    wait = WebDriverWait(driver, 15)

    search_box = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[name='q']")
        )
    )

    # Clear search box thoroughly
    search_box.send_keys(Keys.COMMAND + "a" if driver.capabilities.get('platformName') in ['mac', 'darwin'] else Keys.CONTROL + "a")
    search_box.send_keys(Keys.BACKSPACE)
    search_box.clear()

    search_query = f"{name} Lagos" if "lagos" not in name.lower() else name
    search_box.send_keys(search_query)
    search_box.send_keys(Keys.ENTER)

    time.sleep(2)

    # If results list appears instead of direct place details, click the first result card
    cards = driver.find_elements(By.CSS_SELECTOR, "div[role='feed'] a.hfpxzc")
    if cards:
        try:
            driver.execute_script("arguments[0].click();", cards[0])
            time.sleep(1)
        except Exception as e:
            print(f"  Warning: could not click first result: {e}")

    return scrape_place(driver, name, hotel)


def scrape_results(driver, query):

    scroll_results(driver)

    cards = driver.find_elements(
        By.CSS_SELECTOR,
        "div[role='feed'] a.hfpxzc"
    )

    names = []
    for c in cards:
        name = c.get_attribute("aria-label")
        if name and name not in names:
            names.append(name)

    print(f"Phase 1 complete: Found {len(names)} unique places")

    data = []
    hotel = query.lower() == "hotels"

    print("Phase 2: Scraping place details via individual searches...")

    for i, name in enumerate(names):

        print(f"[{i+1}/{len(names)}] Searching place: {name}")

        try:
            place_info = search_place_by_name(driver, name, hotel)
            data.append(place_info)
            print(f"  -> Plus code: {place_info.get('plus_code')}")
        except Exception as e:
            print(f"Error scraping {name}: {e}")

    return data


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "POIs")


def save_results(query, h3_index, results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{query.replace(' ', '_')}_{h3_index}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    file_exists = os.path.exists(filepath)

    with open(filepath, "a", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name",
                "plus_code",
                "hotel_price"
            ]
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(results)

    print(f"Saved {len(results)} rows -> {filepath}")


def csv_exists(query, h3_index):
    filename = f"{query.replace(' ', '_')}_{h3_index}.csv"
    return os.path.exists(os.path.join(OUTPUT_DIR, filename))


def deduplicate(results):

    seen = set()
    cleaned = []

    for row in results:

        key = row["plus_code"] or row["name"]

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(row)

    return cleaned


def clean_cache(profile_dir):
    """Deletes large caching folders inside a Chrome profile to save disk space."""
    if not profile_dir or not os.path.exists(profile_dir):
        return
        
    cache_dirs = ['Default/Cache', 'Default/Code Cache', 'Default/GPUCache']
    for cache in cache_dirs:
        path = os.path.join(profile_dir, cache)
        if os.path.exists(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass


def process_location(loc, headless, profile_queue):
    h3_index = loc["h3_index"]
    pending_queries = [q for q in SEARCH_TYPES if not csv_exists(q, h3_index)]

    if not pending_queries:
        print(f"[Worker] All categories for H3 '{h3_index}' are complete. Skipping.")
        return

    profile_path = profile_queue.get()
    print(f"[Worker] Starting {h3_index} using {os.path.basename(profile_path)}")
    
    driver = None
    try:
        driver = create_driver(profile_path=profile_path, headless=headless)
        
        for query in pending_queries:
            print(f"[Worker] {h3_index} -> {query.upper()}")
            
            center_lat, center_lng = get_center(h3_index)
            open_location(driver, center_lat, center_lng)
            time.sleep(2)
            
            results = deduplicate(search(driver, query))
            save_results(query, h3_index, results)
            
    except Exception as e:
        print(f"[Worker] Error processing {h3_index}: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        
        clean_cache(profile_path)
        profile_queue.put(profile_path)
        print(f"[Worker] Finished {h3_index}")


def run_scraper(workers=2, headless=True):
    locations = load_target_h3s()

    total_pending_tasks = sum(1 for loc in locations for q in SEARCH_TYPES if not csv_exists(q, loc["h3_index"]))

    if total_pending_tasks == 0:
        print("\n[Scraper] All categories already scraped. Skipping.")
        return

    print(f"[Scraper] Starting with {workers} workers. Headless: {headless}")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    master_profile = os.path.join(project_root, "chrome-profile")

    profile_queue = queue.Queue()
    for i in range(workers):
        profile_dir = os.path.join(project_root, f"chrome-profile-{i}")

        if not os.path.exists(profile_dir) and os.path.exists(master_profile):
            print(f"[Scraper] Cloning primed profile to {profile_dir}...")
            shutil.copytree(master_profile, profile_dir)

        for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lock_path = os.path.join(profile_dir, lock_file)
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                os.remove(lock_path)

        profile_queue.put(profile_dir)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_location, loc, headless, profile_queue) for loc in locations]
        for future in futures:
            future.result()

    print("[Scraper] Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Maps Scraper by H3 Index")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel workers")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser (not headless)")
    args = parser.parse_args()
    run_scraper(workers=args.workers, headless=not args.headed)