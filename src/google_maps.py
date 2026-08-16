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
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-data-dir={profile_path}")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver

def open_location(driver, lat, lng):
    driver.get(f"https://www.google.com/maps/@{lat},{lng},15z")
    time.sleep(3)

def parse_price(price):
    digits = re.sub(r"[^\d]", "", price)
    if digits:
        return int(digits)
    return None

def search(driver, query):
    wait = WebDriverWait(driver, 15)

    try:
        # XPath for search box
        search_box = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@id='searchboxinput'] | //input[@name='q']"))
        )
        
        # Clear search box thoroughly
        search_box.send_keys(Keys.COMMAND + "a" if driver.capabilities.get('platformName') in ['mac', 'darwin'] else Keys.CONTROL + "a")
        search_box.send_keys(Keys.BACKSPACE)
        search_box.clear()

        # Enter query
        search_box.send_keys(query)
        search_box.send_keys(Keys.ENTER)

        # Wait for feed to load
        feed_xpath = "//div[@role='feed']"
        feed = wait.until(EC.presence_of_element_located((By.XPATH, feed_xpath)))
        
        return scrape_results(driver, query, feed_xpath)
        
    except TimeoutException:
        print(f"  [Timeout] Failed to load search feed for {query}.")
        return []

def scrape_results(driver, query, feed_xpath):
    wait = WebDriverWait(driver, 15)
    
    results = []
    processed_names = set()
    index = 0
    
    is_hotel = query.lower() == "hotels"
    
    end_of_list_xpath = "//*[contains(text(), \"You've reached the end of the list\")]"
    spinner_xpath = "//div[@role='progressbar']"
    item_xpath = "//div[@role='feed']//a[contains(@href, '/maps/place/')]"

    while True:
        # Get current visible items
        items = driver.find_elements(By.XPATH, item_xpath)
        
        if index < len(items):
            try:
                # Re-fetch items to avoid StaleElementReferenceException
                items = driver.find_elements(By.XPATH, item_xpath)
                
                if index >= len(items):
                    # Force a scroll to trigger DOM reload if index out of bounds
                    feed = driver.find_element(By.XPATH, feed_xpath)
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                    time.sleep(2)
                    continue
                    
                item = items[index]
                name = item.get_attribute("aria-label") or f"Place {index+1}"
                
                if name in processed_names:
                    index += 1
                    continue
                
                # Scroll item into view and click
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", item)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", item)
                
                # Wait for place details to render (Wait for h1 element to appear)
                try:
                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//h1")))
                except:
                    time.sleep(2) # Fallback static wait
                
                # Extract Plus Code
                plus_code = None
                user_xpath = "/html/body/div[1]/div[2]/div[9]/div[9]/div/div/div[1]/div[3]/div/div[1]/div/div/div[2]/div[11]/div[7]/button/div/div[2]/div[1]"
                semantic_xpath = "//button[contains(@aria-label, 'Plus code:') or contains(@data-item-id, 'oloc')]"
                combined_xpath = f"{user_xpath} | {semantic_xpath}"
                
                try:
                    plus_elem = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, combined_xpath))
                    )
                    raw_text = plus_elem.text
                    # Search for valid Plus Code pattern
                    match = re.search(r'[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}.*', raw_text, re.IGNORECASE)
                    if match:
                        plus_code = match.group(0).strip()
                    else:
                        plus_code = raw_text.replace("\n", " ").strip()
                except:
                    plus_code = None
                    
                # Extract Price if hotel
                price_val = None
                if is_hotel:
                    price_elements = driver.find_elements(By.XPATH, "//span[contains(text(), '₦')]")
                    if price_elements:
                        price_val = parse_price(price_elements[0].text)
                        
                results.append({
                    "name": name,
                    "plus_code": plus_code,
                    "hotel_price": price_val
                })
                processed_names.add(name)
                
                index += 1
                
            except Exception as e:
                # Catch stale elements and timeout issues, just skip item
                index += 1
        else:
            # We've processed all items currently in the DOM. Time to scroll for more.
            try:
                feed = driver.find_element(By.XPATH, feed_xpath)
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                time.sleep(1.5)
            except Exception:
                break
            
            # Check for spinner
            spinners = driver.find_elements(By.XPATH, spinner_xpath)
            if spinners and spinners[0].is_displayed():
                try:
                    WebDriverWait(driver, 10).until(
                        EC.invisibility_of_element_located((By.XPATH, spinner_xpath))
                    )
                except:
                    pass
            
            # Check for end of list marker
            end_elements = driver.find_elements(By.XPATH, end_of_list_xpath)
            if end_elements and end_elements[0].is_displayed():
                break
                
            # Verify if we actually got new items
            new_items = driver.find_elements(By.XPATH, item_xpath)
            if len(new_items) <= index:
                break
                
    return results

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "POIs")

def save_results(query, h3_index, results):
    if not results:
        print(f"Skipping save for empty results -> {query} ({h3_index})")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{query.replace(' ', '_')}_{h3_index}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    file_exists = os.path.exists(filepath)

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "plus_code", "hotel_price"]
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(results)

    print(f"Saved {len(results)} rows -> {filepath}")

def csv_exists(query, h3_index):
    filename = f"{query.replace(' ', '_')}_{h3_index}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return False
    # Only consider it complete if it has more than just the header line
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
        return len(lines) > 1

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