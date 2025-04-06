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
        
        # Initialize folder paths but don't create them yet
        # They will be created after we get the search details
        self.queries_dir = "queries"
        self.query_dir = None
        self.json_file = None
        self.csv_file = None
        
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

    def get_next_button(self):
        """Find and return the Next button if it's not disabled"""
        try:
            # First try to find a Next link
            next_button = self.driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Next"]')
            return next_button
        except:
            try:
                # Then try to find a disabled Next button
                next_button = self.driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Next"][disabled]')
                return None  # Return None if we found a disabled button
            except:
                return None  # Return None if we couldn't find any Next button
    
    def process_listing_page(self, listing):
        """Process an individual listing page and extract its full text"""
        try:
            print(f"\nProcessing listing: {listing['name']}")
            print(f"URL: {listing['url']}")
            
            # Load the listing page
            self.driver.get(listing['url'])
            time.sleep(2)  # Wait for page load
            
            # Handle any popups
            self.handle_popups()
            
            # Get the full page text
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            full_text = ' '.join(soup.stripped_strings)
            
            # Extract specific details
            listing_details = self.extract_listing_details(full_text)
                        
            # Get amenities text first
            print("\n" + "="*50)
            print("AMENITIES:")
            print("="*50)
            
            try:
                # Find the Show all amenities button by text pattern
                show_all_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//button[contains(text(), 'Show all') and contains(text(), 'amenities')]"
                    ))
                )
                
                if show_all_button:
                    # Scroll to the button and click it
                    self.scroll_to_element(show_all_button)
                    time.sleep(1)
                    
                    try:
                        show_all_button.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", show_all_button)
                    
                    time.sleep(1)
                    
                    # Try to find the modal
                    try:
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((
                                By.CSS_SELECTOR,
                                "div[role='dialog'] section"
                            ))
                        )
                        amenities_text = modal.text
                        print(amenities_text)
                    except:
                        print("Could not access modal, getting amenities from page...")
                        amenities_section = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((
                                By.CSS_SELECTOR,
                                "div[data-section-id='AMENITIES_DEFAULT']"
                            ))
                        )
                        amenities_text = amenities_section.text
                        print(amenities_text)
                
            except Exception as e:
                print(f"Error accessing amenities: {str(e)}")
                amenities_text = ""
            
            print("="*50)
            
            # Add amenities analysis to the listing details
            if amenities_text:
                listing_details["amenities_analysis"] = self.check_amenities_with_text_matching(amenities_text)
            
            # Update the listing with new details
            listing.update(listing_details)
            
            # Update the output files with the new details
            self.update_output_files(listing)
            
            return full_text
            
        except Exception as e:
            print(f"Error processing listing page: {str(e)}")
            return None

    def extract_search_params(self, text):
        """Extract search parameters from the initial page text to create folder name"""
        try:
            # Extract location
            location_match = re.search(r'Location\s+([^Check]+)', text)
            location = location_match.group(1).strip() if location_match else ""
            
            # Extract dates
            dates_match = re.search(r'Check\s+(?:in|out)\s+([A-Za-z]+\s+\d+\s*[–-]\s*\d+)', text)
            dates = dates_match.group(1).strip() if dates_match else ""
            
            # Extract guests
            guests_match = re.search(r'(\d+)\s+guests?', text)
            guests = guests_match.group(1) if guests_match else ""
            
            # Create folder name
            folder_name = f"{location}_{dates.replace(' ', '')}_{guests}guests"
            
            # Sanitize folder name
            folder_name = re.sub(r'[^\w\-\.]', '_', folder_name)  # Replace non-word chars with underscore
            folder_name = re.sub(r'_+', '_', folder_name)  # Replace multiple underscores with single
            folder_name = folder_name.strip('_')  # Remove leading/trailing underscores
            
            return folder_name
            
        except Exception as e:
            print(f"Error extracting search parameters: {str(e)}")
            # Fallback to timestamp if we can't extract params
            return datetime.now().strftime("%Y%m%d_%H%M%S")

    def setup_output_files(self, folder_name):
        """Setup output files in the query-specific directory"""
        try:
            # Create queries directory if it doesn't exist
            if not os.path.exists(self.queries_dir):
                os.makedirs(self.queries_dir)
            
            # Set up query-specific directory
            self.query_dir = os.path.join(self.queries_dir, folder_name)
            if not os.path.exists(self.query_dir):
                os.makedirs(self.query_dir)
            
            # Set up file paths
            self.json_file = os.path.join(self.query_dir, "listings.json")
            self.csv_file = os.path.join(self.query_dir, "listings.csv")
            
            # If files don't exist, create them with headers
            if not os.path.exists(self.json_file):
                with open(self.json_file, 'w') as f:
                    json.dump([], f)
            
            if not os.path.exists(self.csv_file):
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
            
            print(f"\nUsing query directory: {self.query_dir}")
            
        except Exception as e:
            print(f"Error setting up output files: {str(e)}")
            raise

    def scrape_url(self, url):
        """
        Scrape Airbnb listings from all pages
        Args:
            url (str): Complete Airbnb search URL
        """
        try:
            current_page = 1
            all_listings = []
            
            # Add page parameter to URL if not present
            if 'page=' not in url:
                url = f"{url}&page=1" if '?' in url else f"{url}?page=1"
            
            # First load the page to get search parameters
            print("\nLoading URL:", url)
            self.driver.get(url)
            self.handle_popups()
            
            # Get initial page text and set up directories
            initial_page_text, _, _ = self.scrape_initial_page_text()
            if not initial_page_text:
                print("Failed to load initial page")
                return []
            
            # Setup output files with folder name from search parameters
            folder_name = self.extract_search_params(initial_page_text)
            self.setup_output_files(folder_name)
            
            # Now start the pagination loop
            while True:  # Continue until we can't find a next button
                print(f"\n{'='*50}")
                print(f"Processing page {current_page}")
                print(f"{'='*50}")
                
                if current_page == 1:
                    # Load next page
                    print("\nLoading URL:", url)
                    self.driver.get(url)
                
                # Handle popups
                self.handle_popups()
                
                # Scrape current page
                _, _, initial_listings = self.scrape_initial_page_text()
                if not initial_listings:
                    print("Failed to load page")
                    break
                
                print(f"\nProcessed {len(initial_listings)} listings from page {current_page}")
                all_listings.extend(initial_listings)
                
                # Try to find and click next button
                next_button = self.get_next_button()
                if next_button is None:
                    print("\nReached last page - no more active Next button")
                    break
                
                try:
                    # Scroll to the button to make sure it's clickable
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    time.sleep(1)  # Small wait after scroll
                    
                    # Get the href before clicking
                    next_url = next_button.get_attribute('href')
                    
                    # Try to click the button
                    try:
                        next_button.click()
                    except:
                        # If direct click fails, try JavaScript click
                        self.driver.execute_script("arguments[0].click();", next_button)
                    
                    # If click seems to fail, try loading the URL directly
                    if next_url:
                        self.driver.get(next_url)
                    
                    current_page += 1
                    print(f"\nMoving to page {current_page}...")
                    time.sleep(2)  # Wait for page load
                    
                except Exception as e:
                    print(f"Error navigating to next page: {str(e)}")
                    break
            
            print(f"\nFinished scraping {current_page} pages, found {len(all_listings)} total listings")
            
            # Process each listing's page
            print("\n" + "="*50)
            print("PROCESSING INDIVIDUAL LISTING PAGES")
            print("="*50)
            
            for listing in all_listings:
                self.process_listing_page(listing)
            
            return all_listings
            
        except Exception as e:
            print(f"Error in scrape_url: {str(e)}")
            return []

    def update_output_files(self, listing_details):
        """Update both JSON and CSV files with new listing data"""
        try:
            # Helper function to handle boolean values
            def get_boolean_value(value):
                if value is None:
                    return ""  # Return empty if not checked
                return "TRUE" if value else "FALSE"  # Return TRUE/FALSE if we know the value
            
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
                "TV": self._get_amenity_value(listing_details, "TV"),
                "Pool": self._get_amenity_value(listing_details, "Pool"),
                "Jacuzzi": self._get_amenity_value(listing_details, "Jacuzzi"),
                "Historical House": get_boolean_value(listing_details.get("is_historical")),
                "Billiards Table": self._get_amenity_value(listing_details, "Billiards/Pool Table"),
                "Large Yard": self._get_amenity_value(listing_details, "Large Yard"),
                "Balcony": self._get_amenity_value(listing_details, "Balcony"),
                "Laundry": self._get_amenity_value(listing_details, "Laundry"),
                "Home Gym": self._get_amenity_value(listing_details, "Home Gym"),
                "Guest Favorite Status": get_boolean_value(listing_details.get("is_guest_favorite"))
            }
            
            # Update JSON file
            with open(self.json_file, 'r') as f:
                current_data = json.load(f)
            
            # Find and update existing entry or add new one
            listing_url = listing_details.get("url", "")
            entry_updated = False
            
            for i, entry in enumerate(current_data):
                if entry.get("Link") == listing_url:
                    # Update existing entry
                    current_data[i].update(reformatted_data)
                    entry_updated = True
                    break
            
            if not entry_updated:
                # Add new entry if not found
                current_data.append(reformatted_data)
            
            # Write updated JSON
            with open(self.json_file, 'w') as f:
                json.dump(current_data, f, indent=2)
            
            # Update CSV file - rewrite entire file with updated data
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write headers
                writer.writerow([
                    "Link", "Name", "Bedrooms", "Beds", "Bathrooms", "Guest Limit",
                    "Stars", "Price/Night in May", "AirBnB Location Rating", "Source",
                    "Amenities", "TV", "Pool", "Jacuzzi", "Historical House",
                    "Billiards Table", "Large Yard", "Balcony", "Laundry", "Home Gym",
                    "Guest Favorite Status"
                ])
                # Write all entries
                for entry in current_data:
                    writer.writerow([
                        entry["Link"],
                        entry["Name"],
                        entry["Bedrooms"],
                        entry["Beds"],
                        entry["Bathrooms"],
                        entry["Guest Limit"],
                        entry["Stars"],
                        entry["Price/Night in May"],
                        entry["AirBnB Location Rating"],
                        entry["Source"],
                        entry["Amenities"],
                        entry["TV"],
                        entry["Pool"],
                        entry["Jacuzzi"],
                        entry["Historical House"],
                        entry["Billiards Table"],
                        entry["Large Yard"],
                        entry["Balcony"],
                        entry["Laundry"],
                        entry["Home Gym"],
                        entry["Guest Favorite Status"]
                    ])
            
        except Exception as e:
            print(f"Error updating output files: {str(e)}")

    def _get_amenity_value(self, listing_details, amenity_key):
        """Helper method to get amenity value with proper blank handling"""
        amenities_analysis = listing_details.get("amenities_analysis")
        if not amenities_analysis:
            return ""  # Return empty if we haven't checked amenities
        if amenity_key in amenities_analysis:
            return "TRUE" if amenities_analysis[amenity_key] else "FALSE"
        return ""  # Return empty if this specific amenity wasn't checked

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
        print("Results are being saved in real-time to:", self.query_dir)
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
        """Check amenities using exact text matching"""
        # Convert amenities text to lowercase for case-insensitive matching
        amenities_text_lower = amenities_text.lower()
        
        # Initialize results dictionary
        results = {
            "Pool": False,
            "Jacuzzi": False,
            "Home Gym": False
        }
        
        # Check for pool (excluding pool table)
        pool_index = amenities_text_lower.find("pool")
        while pool_index != -1:
            # Get some context around the match
            start = max(0, pool_index - 10)
            end = min(len(amenities_text_lower), pool_index + 14)  # pool + table + some extra
            context = amenities_text_lower[start:end]
            
            # If "pool table" is not in the context, count it as a pool
            if "pool table" not in context and "billiard" not in context:
                results["Pool"] = True
                break
            
            # Look for next occurrence
            pool_index = amenities_text_lower.find("pool", pool_index + 1)
        
        # Check for exact "jacuzzi"
        if "jacuzzi" in amenities_text_lower:
            results["Jacuzzi"] = True
        
        # Check for exact "gym"
        if "gym" in amenities_text_lower:
            results["Home Gym"] = True
        
        print("\nAmenities found:")
        print(f"Pool: {results['Pool']}")
        print(f"Jacuzzi: {results['Jacuzzi']}")
        print(f"Gym: {results['Home Gym']}")
        
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
                    
                    listings.append(listing_details)
                    
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

    def extract_listing_details(self, page_text):
        """Extract specific details from listing page text"""
        try:
            details = {
                "bedrooms": "N/A",
                "beds": "N/A",
                "bathrooms": "N/A",
                "guest_limit": "N/A",
                "is_guest_favorite": False
            }
            
            # Find the list items containing the details
            try:
                # The parent div containing all the details
                details_container = self.driver.find_element(By.CSS_SELECTOR, "div.ok4wssy")
                
                # Find all list items with the specific class
                detail_items = details_container.find_elements(By.CSS_SELECTOR, "li.l7n4lsf")
                
                for item in detail_items:
                    try:
                        # Get the text content of the item
                        item_text = item.text.strip()
                        
                        # Check which detail this is
                        if "guest" in item_text.lower():
                            # Extract guest limit, handling both "X guests" and "X+ guests" formats
                            guest_num = re.search(r'(\d+)(?:\+)?\s*guests?', item_text)
                            if guest_num:
                                details["guest_limit"] = guest_num.group(1)
                        elif "bedroom" in item_text.lower():
                            details["bedrooms"] = ''.join(filter(str.isdigit, item_text))
                        elif "bed" in item_text.lower() and "bedroom" not in item_text.lower():
                            details["beds"] = ''.join(filter(str.isdigit, item_text))
                        elif "bath" in item_text.lower():
                            # For bathrooms, keep decimal points
                            bath_num = re.search(r'([\d.]+)', item_text)
                            if bath_num:
                                details["bathrooms"] = bath_num.group(1)
                    except Exception as e:
                        print(f"Error processing detail item: {str(e)}")
                        continue
                        
            except Exception as e:
                print(f"Error finding details container: {str(e)}")
            
            # Check for guest favorite status using the page text
            guest_favorite_patterns = [
                "Guest favorite",
                "One of the most loved homes on Airbnb",
                "This home is in the top 5% of eligible listings"
            ]
            details["is_guest_favorite"] = any(pattern in page_text for pattern in guest_favorite_patterns)
            
            print("\nExtracted listing details:")
            print(f"Guest Limit: {details['guest_limit']}")
            print(f"Bedrooms: {details['bedrooms']}")
            print(f"Beds: {details['beds']}")
            print(f"Bathrooms: {details['bathrooms']}")
            print(f"Guest Favorite: {details['is_guest_favorite']}")
            
            return details
            
        except Exception as e:
            print(f"Error extracting listing details: {str(e)}")
            return {
                "bedrooms": "N/A",
                "beds": "N/A",
                "bathrooms": "N/A",
                "guest_limit": "N/A",
                "is_guest_favorite": False
            }

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
