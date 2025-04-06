from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
import os
from datetime import datetime
import re
from groq import Groq
from dotenv import load_dotenv
import csv

class AirbnbScraper:
    def __init__(self):
        self.setup_driver()
        self.results = []
        self.setup_groq()
        
        # Create run-specific directory
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join("runs", self.run_timestamp)
        if not os.path.exists(self.run_dir):
            os.makedirs(self.run_dir)
        
        # Initialize output files
        self.json_file = os.path.join(self.run_dir, "listings.json")
        self.csv_file = os.path.join(self.run_dir, "listings.csv")
        
        # Create empty JSON file
        with open(self.json_file, 'w') as f:
            json.dump([], f)
        
        # Create CSV with headers
        headers = [
            "Link", "Name", "Bedrooms", "Beds", "Bathrooms", "Guest Limit", 
            "Stars", "Price/Night in May", "AirBnB Location Rating", "Source", 
            "Amenities", "TV", "Pool", "Jacuzzi", "Historical House", 
            "Billiards Table", "Large Yard", "Balcony", "Laundry", "Home Gym",
            "Guest Favorite Status"
        ]
        with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        
    def setup_driver(self):
        """Set up the Chrome driver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Add user agent to mimic a real browser
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Add experimental options to prevent detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Set additional properties to prevent detection
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
    def setup_groq(self):
        """Set up the Groq client"""
        load_dotenv()
        self.groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
    def handle_popups(self):
        """Handle any popups that might appear"""
        try:
            # Reduced wait time for popup
            got_it_button = WebDriverWait(self.driver, 2).until(  # Reduced from 5 to 2
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Got it')]"))
            )
            got_it_button.click()
            # time.sleep(0.5)  # Reduced from 1 to 0.5
        except (TimeoutException, ElementClickInterceptedException, NoSuchElementException):
            pass

    def scroll_to_element(self, element):
        """Scroll to a specific element using JavaScript with better reliability"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            # time.sleep(1)  # Reduced from 2 to 1
            
            self.driver.execute_script("window.scrollBy(0, -100);")
            # time.sleep(0.5)  # Reduced from 1 to 0.5
            
            return element.is_displayed()
        except:
            return False

    def check_amenities_with_groq(self, amenities_text):
        """Use Groq to analyze amenities text"""
        target_amenities = ["TV", "Pool", "Jacuzzi", "Billiards/Pool Table", 
                          "Large Yard", "Balcony", "Laundry", "Home Gym"]
        
        prompt = f"""
        Given the following amenities text from an Airbnb listing:
        {amenities_text}
        
        Please analyze if the following amenities are present (exactly or similar terms):
        {', '.join(target_amenities)}
        
        Return ONLY a JSON object in this exact format, with no additional text:
        {{
            "TV": true/false,
            "Pool": true/false,
            "Jacuzzi": true/false,
            "Billiards/Pool Table": true/false,
            "Large Yard": true/false,
            "Balcony": true/false,
            "Laundry": true/false,
            "Home Gym": true/false
        }}
        
        Consider similar terms (e.g., "Swimming pool" for "Pool", "Hot tub" for "Jacuzzi", etc.)
        """
        
        try:
            chat_completion = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a JSON-only assistant. You must respond with valid JSON objects only, no additional text or explanation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
            )
            
            response = chat_completion.choices[0].message.content.strip()
            print("\nGroq response:", response)  # Debug print
            
            # Try to clean the response if it's not pure JSON
            try:
                return json.loads(response)
            except:
                # Try to extract JSON if there's additional text
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise Exception("Could not extract valid JSON from response")
            
        except Exception as e:
            print(f"Error analyzing amenities with Groq: {str(e)}")
            # Return a default structure instead of None
            return {
                "TV": False,
                "Pool": False,
                "Jacuzzi": False,
                "Billiards/Pool Table": False,
                "Large Yard": False,
                "Balcony": False,
                "Laundry": False,
                "Home Gym": False,
                "error": str(e)
            }

    def get_amenities_text(self):
        """Get amenities text from modal or fall back to page text"""
        try:
            # print("Trying to access amenities...")
            
            # First make sure we're on the right part of the page
            self.driver.execute_script("window.scrollBy(0, 500);")
            # time.sleep(1)
            
            # Try to find the Show all button with the first selector
            show_all_button = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[7]/div/div[2]/section/div[3]/button'
                ))
            )
            
            if not show_all_button:
                raise Exception("Could not find 'Show all amenities' button")
            
            # print("Found button, scrolling to it...")
            self.scroll_to_element(show_all_button)
            # time.sleep(1)
            
            # print("Attempting to click button...")
            try:
                show_all_button.click()
            except:
                self.driver.execute_script("arguments[0].click();", show_all_button)
            
            # print("Button clicked, waiting for modal...")
            # time.sleep(1.5)
            
            # Try to find the modal with the single CSS selector
            try:
                modal = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "div[role='dialog'] section"
                    ))
                )
                # print("Found modal")
            except:
                print("Could not access modal, falling back to page text...")
                # Get amenities section from the main page
                amenities_section = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[7]/div/div[2]/section'
                    ))
                )
                amenities_text = amenities_section.text
                if amenities_text:
                    print("Successfully retrieved amenities from page")
                    return amenities_text
            
            # If modal was found, use its text
            amenities_text = modal.text
            if amenities_text:
                # print(f"Found amenities text from modal")
                # print(f"\nFound amenities text from modal: {amenities_text[:100]}...")
                return amenities_text
            
            print("Warning: No amenities text found in either modal or page")
            return None
            
        except Exception as e:
            print(f"Error getting amenities from modal, falling back to page text...")
            try:
                # Final fallback: try to get the entire page content
                full_content = self.driver.find_element(
                    By.XPATH,
                    '//*[@id="site-content"]/div/div[1]'
                ).text
                print("Using full page content for amenities analysis")
                return full_content
            except:
                print("Could not get any amenities text")
                return None

    def extract_missing_details(self, full_content, missing_fields):
        """Use Groq to extract missing details from the full page content"""
        prompt = f"""
        Given the following Airbnb listing content:
        {full_content}
        
        Extract these missing fields: {', '.join(missing_fields)}
        Return ONLY a JSON object with the found values, like:
        {{
            "field_name": "extracted value"
        }}
        """
        
        try:
            chat_completion = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a JSON-only assistant. Respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
            )
            
            response = chat_completion.choices[0].message.content.strip()
            print("\nGroq missing details response:", response)  # Debug print
            
            # Try to clean the response if it's not pure JSON
            try:
                return json.loads(response)
            except:
                # Try to extract JSON if there's additional text
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise Exception("Could not extract valid JSON from response")
            
        except Exception as e:
            print(f"Error extracting missing details: {str(e)}")
            return {}

    def get_next_page_link(self):
        """Find and return the next page link if available"""
        try:
            # Try to find the Next button specifically
            next_button_xpath = '//*[@id="site-content"]/div/div[3]/div/div/div/nav/div/a[last()]'  # Last <a> tag in nav
            
            try:
                next_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, next_button_xpath))
                )
                
                print("\nFound next button:", next_button.get_attribute('aria-label'))
                
                # Check if the button is disabled
                aria_disabled = next_button.get_attribute('aria-disabled')
                if aria_disabled == 'true':
                    print("Next button is disabled, no more pages")
                    return None
                    
                # Make sure it's actually the "Next" button
                if 'Next' in next_button.get_attribute('aria-label'):
                    print("Found active Next button")
                    return next_button
                
                print("Button found but it's not a Next button")
                return None
                
            except Exception as e:
                print(f"Could not find Next button: {str(e)}")
                return None
                
        except Exception as e:
            print(f"Error in get_next_page_link: {str(e)}")
            return None

    def update_output_files(self, listing_details):
        """Update both JSON and CSV files with new listing data"""
        try:
            # Prepare the reformatted data
            reformatted_data = {
                "Link": listing_details.get("url", ""),
                "Name": listing_details.get("name", ""),
                "Bedrooms": listing_details.get("bedrooms", ""),
                "Beds": listing_details.get("beds", ""),
                "Bathrooms": listing_details.get("bathrooms", ""),
                "Guest Limit": listing_details.get("guest_limit", ""),
                "Stars": listing_details.get("stars", ""),
                "Price/Night in May": listing_details.get("price_per_night", ""),
                "AirBnB Location Rating": listing_details.get("location_rating", ""),
                "Source": "Airbnb",
                "Amenities": "",  # Blank as requested
                "TV": "TRUE" if listing_details.get("amenities_analysis", {}).get("TV", False) else "FALSE",
                "Pool": "TRUE" if listing_details.get("amenities_analysis", {}).get("Pool", False) else "FALSE",
                "Jacuzzi": "TRUE" if listing_details.get("amenities_analysis", {}).get("Jacuzzi", False) else "FALSE",
                "Historical House": "TRUE" if listing_details.get("is_historical", False) else "FALSE",
                "Billiards Table": "TRUE" if listing_details.get("amenities_analysis", {}).get("Billiards/Pool Table", False) else "FALSE",
                "Large Yard": "TRUE" if listing_details.get("amenities_analysis", {}).get("Large Yard", False) else "FALSE",
                "Balcony": "TRUE" if listing_details.get("amenities_analysis", {}).get("Balcony", False) else "FALSE",
                "Laundry": "TRUE" if listing_details.get("amenities_analysis", {}).get("Laundry", False) else "FALSE",
                "Home Gym": "TRUE" if listing_details.get("amenities_analysis", {}).get("Home Gym", False) else "FALSE",
                "Guest Favorite Status": "TRUE" if listing_details.get("is_guest_favorite", False) else "FALSE"
            }
            
            # Update JSON file
            with open(self.json_file, 'r') as f:
                current_data = json.load(f)
            
            current_data.append(reformatted_data)
            
            with open(self.json_file, 'w') as f:
                json.dump(current_data, f, indent=2)
            
            # Update CSV file
            with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    reformatted_data["Link"],
                    reformatted_data["Name"],
                    reformatted_data["Bedrooms"],
                    reformatted_data["Beds"],
                    reformatted_data["Bathrooms"],
                    reformatted_data["Guest Limit"],
                    reformatted_data["Stars"],
                    reformatted_data["Price/Night in May"],
                    reformatted_data["AirBnB Location Rating"],
                    reformatted_data["Source"],
                    reformatted_data["Amenities"],
                    reformatted_data["TV"],
                    reformatted_data["Pool"],
                    reformatted_data["Jacuzzi"],
                    reformatted_data["Historical House"],
                    reformatted_data["Billiards Table"],
                    reformatted_data["Large Yard"],
                    reformatted_data["Balcony"],
                    reformatted_data["Laundry"],
                    reformatted_data["Home Gym"],
                    reformatted_data["Guest Favorite Status"]
                ])
            
            # print(f"\nUpdated output files in {self.run_dir}")
            
        except Exception as e:
            print(f"Error updating output files: {str(e)}")

    def scrape_url(self, url):
        """
        Scrape Airbnb listings from the first page
        Args:
            url (str): Complete Airbnb search URL
        """
        try:
            # Add page parameter to URL if not present
            if 'page=' not in url:
                url = f"{url}&page=1" if '?' in url else f"{url}?page=1"
            
            # Load first page
            print("\nLoading URL:", url)
            self.driver.get(url)
            
            # Handle popups
            self.handle_popups()
            
            # Scrape initial page text and get listings
            initial_page_text, _, initial_listings = self.scrape_initial_page_text()
            if not initial_page_text:
                print("Failed to load initial page")
                return []
            
            print(f"\nProcessed {len(initial_listings)} listings from first page")
            return initial_listings
            
        except Exception as e:
            print(f"Error in scrape_url: {str(e)}")
            return []
    
    def _calculate_price_per_night(self, details):
        """Helper method to calculate price per night"""
        try:
            total_price = self._clean_price(details["price"])
            nights_text = details["nights"].lower()
            num_nights = int(''.join(filter(str.isdigit, nights_text)))
            return str(int(total_price) // num_nights) if num_nights > 0 else total_price
        except:
            return "N/A"
    
    def _parse_page(self):
        """Parse the current page and extract listing information"""
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        listings = soup.find_all("div", {"itemprop": "itemListElement"})
        
        for listing in listings:
            try:
                # Extract listing data
                listing_data = {
                    'title': self._get_text(listing, "meta[itemprop='name']", attr='content'),
                    'url': self._get_text(listing, "meta[itemprop='url']", attr='content'),
                    'price': self._clean_price(listing.find("span", {"class": "_tyxjp1"}).text if listing.find("span", {"class": "_tyxjp1"}) else "N/A"),
                    'rating': self._get_text(listing, "span[class*='r1dxllyb']"),
                    'reviews': self._get_text(listing, "span[class*='r1dxllyb']").split(' ')[0] if listing.find("span", {"class": "r1dxllyb"}) else "0",
                    'type': self._get_text(listing, "div[class*='t1jojoys']"),
                    'amenities': self._get_text(listing, "div[class*='f15liw5s']"),
                    'scraped_date': datetime.now().strftime("%Y-%m-%d")
                }
                
                self.results.append(listing_data)
                
            except Exception as e:
                print(f"Error parsing listing: {str(e)}")
                continue
    
    def _get_text(self, element, selector, attr=None):
        """Helper method to safely extract text or attribute from an element"""
        try:
            found = element.select_one(selector)
            if found:
                return found[attr] if attr else found.text.strip()
            return "N/A"
        except:
            return "N/A"
    
    def _clean_price(self, price_str):
        """Clean price string to extract only the number"""
        try:
            return ''.join(filter(str.isdigit, price_str))
        except:
            return "N/A"
    
    def save_results(self, filename=None):
        """This method is now deprecated since we're saving in real-time"""
        print("Results are being saved in real-time to:", self.run_dir)
        print(f"JSON file: {self.json_file}")
        print(f"CSV file: {self.csv_file}")
    
    def close(self):
        """Close the browser"""
        self.driver.quit()

    def _extract_number(self, text):
        """Helper method to extract numeric values including decimals from text"""
        try:
            # Find all numbers including decimals in the text
            numbers = re.findall(r'\d*\.?\d+', text)
            return numbers[0] if numbers else "N/A"
        except:
            return "N/A"

    def get_rating_from_tab(self):
        """Extract rating and review count from the listing tab"""
        try:
            # Try to find the rating element with the specified class
            rating_element = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "#site-content > div > div:nth-child(1) > div:nth-child(3) > div > div._16e70jgn > div > div:nth-child(2) > div > div > div > a > div > div.a8jhwcl.atm_c8_vvn7el.atm_g3_k2d186.atm_fr_1vi102y.atm_9s_1txwivl.atm_ar_1bp4okc.atm_h_1h6ojuz.atm_cx_t94yts.atm_le_14y27yu.atm_c8_sz6sci__14195v1.atm_g3_17zsb9a__14195v1.atm_fr_kzfbxz__14195v1.atm_cx_1l7b3ar__14195v1.atm_le_1l7b3ar__14195v1.dir.dir-ltr > span"
                ))
            )
            
            rating_text = rating_element.text.strip()
            # Extract the rating number from text like "Rated 4.98 out of 5 stars."
            rating_match = re.search(r"Rated\s+([\d.]+)\s+out of 5 stars", rating_text)
            
            if rating_match:
                rating = rating_match.group(1)
                print(f"Found rating: {rating}")
                return rating
            else:
                print("Could not parse rating text")
                return "N/A"
                
        except Exception as e:
            print(f"Error extracting rating: {str(e)}")
            return "N/A"

    def get_price_from_tab(self):
        """Extract price from the listing tab"""
        try:
            # Try to find the price element with the specified class
            price_element = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "#site-content > div > div:nth-child(1) > div:nth-child(3) > div > div._1s21a6e2 > div > div > div:nth-child(1) > div > div > div > div > div > div > div._wgmchy > div._1k1ce2w > div > div > span > span"
                ))
            )
            
            price_text = price_element.text.strip()
            # Extract the first price number from text like "$2,013 total, originally $2,318" or "$1,470 total"
            price_match = re.search(r'\$([\d,]+)', price_text)
            
            if price_match:
                # Remove commas and convert to integer
                price = price_match.group(1).replace(',', '')
                print(f"Found price: ${price}")
                return price
            else:
                print("Could not parse price text")
                return "N/A"
                
        except Exception as e:
            print(f"Error extracting price: {str(e)}")
            return "N/A"

    def check_amenities_with_text_matching(self, amenities_text):
        """Check amenities using text matching with comprehensive variations"""
        amenity_variations = {
            "TV": [
                "tv", "television", "smart tv", "cable tv", "hdtv", "roku", 
                "netflix", "streaming", "apple tv", "flat screen"
            ],
            "Pool": [
                "pool", "swimming pool", "outdoor pool", "indoor pool", 
                "heated pool", "lap pool", "plunge pool"
            ],
            "Jacuzzi": [
                "jacuzzi", "hot tub", "whirlpool", "jetted tub", 
                "soaking tub", "spa tub"
            ],
            "Billiards/Pool Table": [
                "pool table", "billiards", "billiard table", "game table", 
                "gaming table", "pool cue"
            ],
            "Large Yard": [
                "yard", "garden", "backyard", "outdoor space", "patio", 
                "lawn", "courtyard", "grounds"
            ],
            "Balcony": [
                "balcony", "deck", "terrace", "porch", "veranda", 
                "outdoor deck", "private balcony"
            ],
            "Laundry": [
                "laundry", "washer", "dryer", "washing machine", "laundromat",
                "clothes washer", "clothes dryer", "washer/dryer"
            ],
            "Home Gym": [
                "gym", "fitness", "exercise", "workout", "weight", 
                "treadmill", "exercise equipment", "fitness room"
            ]
        }
        
        # Convert amenities text to lowercase for case-insensitive matching
        amenities_text_lower = amenities_text.lower()
        
        # Initialize results dictionary
        results = {
            amenity: False for amenity in amenity_variations.keys()
        }
        
        # Store evidence of matches
        evidence = {}
        
        # Check each amenity
        for amenity, variations in amenity_variations.items():
            matches = []
            for variation in variations:
                if variation in amenities_text_lower:
                    matches.append(variation)
            
            if matches:
                results[amenity] = True
                # Get some context around the first match
                first_match = matches[0]
                index = amenities_text_lower.find(first_match)
                start = max(0, index - 50)
                end = min(len(amenities_text), index + len(first_match) + 50)
                context = amenities_text[start:end].strip()
                evidence[amenity] = {
                    "matched_terms": matches,
                    "context": context
                }
        
        # Add evidence to results
        # results["_evidence"] = evidence
        
        return results

    def scrape_page_text(self):
        """Scrape and log all text from the current page using BeautifulSoup"""
        try:
            # Get the page source
            page_source = self.driver.page_source
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Get all text, removing extra whitespace
            all_text = ' '.join(soup.stripped_strings)
            
            # Log the text
            print("\n" + "="*50)
            print("PAGE TEXT CONTENT:")
            print("="*50)
            # print(all_text)
            print("="*50 + "\n")
            
            return all_text
            
        except Exception as e:
            print(f"Error scraping page text: {str(e)}")
            return None

    def extract_price_per_night(self, page_text):
        """
        Extract price per night from page text using regex pattern matching
        Args:
            page_text (str): The full text content of the page
        Returns:
            str: The price per night as a string, or "N/A" if not found
        """
        try:
            # First try the price breakdown pattern
            breakdown_pattern = r"Show price breakdown \$([\d,]+) for (\d+) nights"
            breakdown_match = re.search(breakdown_pattern, page_text)
            
            if breakdown_match:
                total_price = breakdown_match.group(1).replace(',', '')  # Remove commas
                num_nights = int(breakdown_match.group(2))
                
                # Calculate price per night
                price_per_night = int(total_price) // num_nights
                
                print(f"\nFound price breakdown: ${total_price} for {num_nights} nights")
                print(f"Calculated price per night: ${price_per_night}")
                
                return str(price_per_night)
            
            # Fallback: Try to find total price pattern like "Location $2,177 total"
            total_price_pattern = r"\$([\d,]+)\s+total"
            total_match = re.search(total_price_pattern, page_text)
            
            if total_match:
                total_price = total_match.group(1).replace(',', '')  # Remove commas
                print(f"\nFound total price: ${total_price}")
                
                # If we have the number of nights from the initial page, use it
                if hasattr(self, 'num_nights') and self.num_nights:
                    price_per_night = int(total_price) // self.num_nights
                    print(f"Using {self.num_nights} nights from initial page")
                    print(f"Calculated price per night: ${price_per_night}")
                    return str(price_per_night)
                else:
                    print("No number of nights found, returning total price")
                    return total_price
            
            print("Could not find any price pattern in page text")
            return "N/A"
                
        except Exception as e:
            print(f"Error extracting price per night: {str(e)}")
            return "N/A"

    def extract_max_pages(self, text):
        """Extract the maximum number of pages from the initial search text"""
        try:
            # Look for numbered page buttons like "1 2 3 4 5 6"
            page_numbers = re.findall(r'\b\d+\b(?=\s+(?:\d+\s+)*(?:Centered|Google|Map))', text)
            if page_numbers:
                return max(map(int, page_numbers))
            return 1
        except Exception as e:
            print(f"Error extracting max pages: {str(e)}")
            return 1

    def extract_initial_listings(self, text):
        """Extract initial listing details from search page text and grid items"""
        try:
            # Wait for and get grid items
            grid_items = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((
                    By.XPATH, 
                    '//*[@id="site-content"]/div/div[2]/div/div/div/div/div/div'
                ))
            )
            print(f"\nFound {len(grid_items)} grid items to process")
            
            listings = []
            for item in grid_items:
                try:
                    # Get name using the listing-card-name data-testid
                    name_element = item.find_element(By.CSS_SELECTOR, 'span[data-testid="listing-card-name"]')
                    name = name_element.text if name_element else "N/A"
                    
                    # Get link from the parent anchor tag that wraps the entire card
                    link_element = item.find_element(By.CSS_SELECTOR, 'a[href*="/rooms/"]')
                    link = link_element.get_attribute('href') if link_element else "N/A"
                    
                    # Get the text content of this specific grid item
                    item_text = item.text
                    
                    # Extract price - look for price breakdown pattern
                    price_match = re.search(r'\$(\d+(?:,\d+)?)\s+for\s+(\d+)\s+nights', item_text)
                    if price_match:
                        total_price = int(price_match.group(1).replace(',', ''))
                        num_nights = int(price_match.group(2))
                        price_per_night = total_price // num_nights
                    else:
                        # Fallback to just finding the last price mentioned
                        prices = re.findall(r'\$(\d+(?:,\d+)?)', item_text)
                        total_price = int(prices[-1].replace(',', '')) if prices else 0
                        price_per_night = total_price // 2  # Assume 2 nights if not specified
                    
                    # Extract rating
                    rating_match = re.search(r'([\d.]+)\s+out of 5\s+average rating,\s+(\d+)\s+reviews', item_text)
                    if not rating_match:
                        rating_match = re.search(r'([\d.]+)\s+\((\d+)\)', item_text)
                    
                    rating = rating_match.group(1) if rating_match else "N/A"
                    review_count = rating_match.group(2) if rating_match else "0"
                    
                    # Check for guest favorite status
                    is_guest_favorite = "Guest favorite" in item_text
                    is_top_guest_favorite = "Top guest favorite" in item_text
                    
                    # Get location from the text before the property name
                    location = item_text.split(name)[0].replace("Home in", "").strip() if name != "N/A" else "N/A"
                    
                    listing_details = {
                        "name": name,
                        "url": link,
                        "location": location,
                        "price_per_night": str(price_per_night),
                        "total_price": str(total_price),
                        "rating": rating,
                        "review_count": review_count,
                        "is_guest_favorite": is_top_guest_favorite or is_guest_favorite,
                        "is_top_guest_favorite": is_top_guest_favorite,
                        "nights": num_nights if 'num_nights' in locals() else 2
                    }
                    
                    print(f"\nExtracted listing details: {listing_details}")
                    listings.append(listing_details)
                    
                    # Update output files immediately with initial data
                    self.update_output_files({
                        "url": listing_details["url"],
                        "name": listing_details["name"],
                        "price_per_night": listing_details["price_per_night"],
                        "total_price": listing_details["total_price"],
                        "location": listing_details["location"],
                        "stars": listing_details["rating"],
                        "review_count": listing_details["review_count"],
                        "location_rating": "N/A",
                        "bedrooms": "N/A",
                        "beds": "N/A",
                        "bathrooms": "N/A",
                        "guest_limit": "N/A",
                        "amenities_analysis": {},
                        "is_historical": False,
                        "is_guest_favorite": listing_details["is_guest_favorite"],
                        "is_top_guest_favorite": listing_details["is_top_guest_favorite"],
                        "nights": listing_details["nights"]
                    })
                    
                except Exception as e:
                    print(f"Error processing individual listing: {str(e)}")
                    continue
            
            return listings
            
        except Exception as e:
            print(f"Error extracting initial listings: {str(e)}")
            return []

    def scrape_initial_page_text(self):
        """Scrape and log all text from the initial search results page"""
        try:
            # Wait for the page to load by checking for a common element
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    '//*[@id="site-content"]/div/div[2]/div/div/div/div/div/div'
                ))
            )
            
            # Get the page source
            page_source = self.driver.page_source
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Get all text, removing extra whitespace
            all_text = ' '.join(soup.stripped_strings)
            
            # Extract max pages and initial listings
            max_pages = self.extract_max_pages(all_text)
            initial_listings = self.extract_initial_listings(all_text)
            
            print(f"\nFound {len(initial_listings)} listings on initial page")
            print(f"Maximum pages: {max_pages}")
            
            return all_text, max_pages, initial_listings
            
        except Exception as e:
            print(f"Error scraping initial page text: {str(e)}")
            return None, 1, []

    def extract_nights_from_text(self, text):
        """
        Extract the number of nights from the initial page text
        Args:
            text (str): The text content from the initial page
        Returns:
            int: Number of nights, or None if not found
        """
        try:
            # Pattern to match dates like "Check out May 23 – 25"
            pattern = r"Check out.*?(\d+)\s*[–-]\s*(\d+)"
            match = re.search(pattern, text)
            
            if match:
                start_day = int(match.group(1))
                end_day = int(match.group(2))
                nights = end_day - start_day
                print(f"Found {nights} nights from dates {start_day} to {end_day}")
                return nights
            else:
                print("Could not find date range in text")
                return None
                
        except Exception as e:
            print(f"Error extracting nights from text: {str(e)}")
            return None

def main():
    # Example usage
    scraper = AirbnbScraper()
    
    try:
        # Get the Airbnb search URL from user
        url = input("Enter the complete Airbnb search URL: ")
        
        print(f"\nScraping Airbnb listings...")
        scraper.scrape_url(url)
        
        # Save results
        scraper.save_results()
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
