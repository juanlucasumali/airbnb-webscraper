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

class AirbnbScraper:
    def __init__(self):
        self.setup_driver()
        self.results = []
        self.setup_groq()
        
    def setup_driver(self):
        """Set up the Chrome driver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
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
            time.sleep(0.5)  # Reduced from 1 to 0.5
        except (TimeoutException, ElementClickInterceptedException, NoSuchElementException):
            pass

    def scroll_to_element(self, element):
        """Scroll to a specific element using JavaScript with better reliability"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(1)  # Reduced from 2 to 1
            
            self.driver.execute_script("window.scrollBy(0, -100);")
            time.sleep(0.5)  # Reduced from 1 to 0.5
            
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
        """Click show all amenities button and extract amenities text"""
        try:
            print("\nTrying to access amenities...")
            
            # First make sure we're on the right part of the page
            self.driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)
            
            # Try multiple selectors for the button
            selectors = [
                '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[7]/div/div[2]/section/div[3]/button',  # Original XPath
                "//button[contains(., 'Show all amenities')]",  # Text content
                "//button[contains(@aria-label, 'amenities')]",  # Aria label
                "//div[contains(@data-section-id, 'AMENITIES')]//button",  # Section + button
                "//button[.//span[contains(text(), 'Show all')]]"  # Nested span with text
            ]
            
            show_all_button = None
            for selector in selectors:
                print(f"Trying selector: {selector}")
                try:
                    show_all_button = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    if show_all_button:
                        print(f"Found button using selector: {selector}")
                        break
                except:
                    continue
            
            if not show_all_button:
                raise Exception("Could not find 'Show all amenities' button with any selector")
            
            print("Found button, scrolling to it...")
            self.scroll_to_element(show_all_button)
            time.sleep(1)
            
            print("Attempting to click button...")
            try:
                show_all_button.click()
            except:
                self.driver.execute_script("arguments[0].click();", show_all_button)
            
            print("Button clicked, waiting for modal...")
            time.sleep(1.5)
            
            # Try multiple selectors for the modal content
            modal_selectors = [
                '/html/body/div[9]/div/div/section/div/div/div[2]/div/div[3]/div/div/div/section/section',  # Original XPath
                "div[role='dialog'] section",  # CSS selector
                "//div[@role='dialog']//div[@role='group']",  # Role-based XPath
                "//div[contains(@aria-label, 'amenities')]"  # Aria label
            ]
            
            modal = None
            for selector in modal_selectors:
                print(f"Trying modal selector: {selector}")
                try:
                    if selector.startswith("//"):
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    if modal:
                        print(f"Found modal using selector: {selector}")
                        break
                except:
                    continue
            
            if not modal:
                raise Exception("Could not find amenities modal with any selector")
            
            # Get all amenity items
            print("Extracting amenities text...")
            amenities_text = modal.text
            
            if not amenities_text:
                print("Warning: No amenities text found in modal")
                return None
            
            print(f"\nFound amenities text: {amenities_text[:100]}...")
            return amenities_text
            
        except Exception as e:
            print(f"Error getting amenities: {str(e)}")
            return None

    def check_historical_house(self, page_text):
        """Check if the listing is a historical house"""
        historical_terms = ['historic', 'historical', 'heritage', 'landmark', 'period', 'century']
        prompt = f"""
        Given the following listing description:
        {page_text}
        
        Analyze if this is a historical house based on mentions of: {', '.join(historical_terms)}
        Return ONLY a JSON object in this format:
        {{
            "is_historical": true/false,
            "evidence": "brief explanation or relevant text snippet"
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
            print("\nGroq historical response:", response)  # Debug print
            
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
            print(f"Error analyzing historical status: {str(e)}")
            return {"is_historical": False, "evidence": "Error in analysis"}

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

    def scrape_url(self, url, num_pages=5):
        """
        Scrape Airbnb listings from a direct URL
        Args:
            url (str): Complete Airbnb search URL
            num_pages (int): Number of pages to scrape
        """
        try:
            # Load the initial URL
            print("\nLoading URL:", url)
            self.driver.get(url)
            time.sleep(1.5)  # Reduced from 3 to 1.5
            
            # Handle any popups
            self.handle_popups()
            
            try:
                print("Waiting for listings grid to load...")
                grid_items = WebDriverWait(self.driver, 5).until(  # Reduced from 10 to 5
                    EC.presence_of_all_elements_located((
                        By.XPATH, 
                        '//*[@id="site-content"]/div/div[2]/div/div/div/div/div/div'
                    ))
                )
                print(f"Found {len(grid_items)} listings to process")
                
                all_listings = []
                original_window = self.driver.current_window_handle
                
                # Iterate through each grid item
                for index, item in enumerate(grid_items, 1):
                    try:
                        print(f"\n{'='*50}")
                        print(f"Processing listing {index} of {len(grid_items)}")
                        print(f"{'='*50}")
                        
                        # Get rating and review count from grid item first
                        try:
                            rating_element = item.find_element(
                                By.XPATH, 
                                    '//*[@id="site-content"]/div/div[2]/div/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div/div[2]/div[5]/span/span[3]'
                            )
                            rating_text = rating_element.get_attribute("innerText")
                            rating_match = re.match(r"([\d.]+)\s*\((\d+)\)", rating_text)
                            if rating_match:
                                rating = rating_match.group(1)
                                review_count = rating_match.group(2)
                                print(f"Found rating: {rating} with {review_count} reviews")
                            else:
                                rating = "N/A"
                                review_count = "0"
                                print("Could not parse rating text")
                        except Exception as e:
                            print(f"Warning: Could not extract rating from grid: {str(e)}")
                            rating = "N/A"
                            review_count = "0"

                        print("\nClicking listing and waiting for new tab...")
                        item.click()
                        time.sleep(1)  # Reduced from 2 to 1
                        
                        # Switch to new tab with shorter timeout
                        WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > 1)  # Reduced from 10 to 5
                        new_window = [window for window in self.driver.window_handles if window != original_window][0]
                        self.driver.switch_to.window(new_window)
                        time.sleep(5)  # Reduced from 3 to 1.5
                        print("Successfully switched to new tab")

                        # Define XPaths
                        xpaths = {
                            "name": '//*[@id="site-content"]/div/div[1]/div[1]/div[1]/div/div/div/div/div/section/div/div[1]/div/h1',
                            "guests": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[1]/div/div/div/section/div[2]/ol/li[1]',
                            "bedrooms": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[1]/div/div/div/section/div[2]/ol/li[2]',
                            "beds": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[1]/div/div/div/section/div[2]/ol/li[3]',
                            "baths": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[1]/div/div/div/section/div[2]/ol/li[4]',
                            "price": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[2]/div/div/div[1]/div/div/div/div[2]/div/div/div[1]/div[1]/div/div/span/div[1]/div/span/div/button/span[1]',
                            "nights": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[2]/div/div/div[1]/div/div/div/div[2]/div/div/div[1]/div[1]/div/div/span/div[2]/span',
                            "stars": '//*[@id="site-content"]/div/div[1]/div[3]/div/div[1]/div/div[2]/div/div/div/a/div/div[6]/span',
                            "location_rating": '//*[@id="site-content"]/div/div[1]/div[4]/div/div/div/div[2]/div/section/div[2]/div/div/div[3]/div/div/div/div/div[6]/div/div/div[2]/div[2]'
                        }

                        # Get listing details using existing XPaths and logic
                        
                        # Find and scroll to location rating element (it's usually at the bottom)
                        try:
                            location_element = WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, xpaths["location_rating"]))
                            )
                            self.scroll_to_element(location_element)
                        except:
                            print("Warning: Could not find location rating section")

                        # Extract all details
                        details = {}
                        print("\nExtracting listing details:")
                        print("-" * 30)
                        for key, xpath in xpaths.items():
                            try:
                                element = WebDriverWait(self.driver, 5).until(  # Reduced from 10 to 5
                                    EC.presence_of_element_located((By.XPATH, xpath))
                                )
                                details[key] = element.text
                                print(f"{key}: {details[key]}")
                            except:
                                details[key] = "N/A"
                                print(f"{key}: N/A (not found)")
                        
                        # Process details and create listing object
                        listing_details = {
                            "name": details["name"],
                            "guest_limit": self._extract_number(details["guests"]),
                            "bedrooms": self._extract_number(details["bedrooms"]),
                            "beds": self._extract_number(details["beds"]),
                            "bathrooms": self._extract_number(details["baths"]),
                            "stars": rating,
                            "review_count": review_count,
                            "price_per_night": self._calculate_price_per_night(details),
                            "total_price": self._clean_price(details["price"]),
                            "number_of_nights": self._extract_number(details["nights"]),
                            "location_rating": details.get("location_rating", "N/A"),
                            "url": self.driver.current_url
                        }
                        
                        try:
                            # Check for Guest Favorite badge
                            try:
                                guest_favorite = self.driver.find_element(
                                    By.XPATH,
                                    '//*[@id="site-content"]/div/div[1]/div[4]/div/div/div/div[2]/div/section/div[1]/div[2]'
                                ).is_displayed()
                                print(f"Guest Favorite: {guest_favorite}")
                            except:
                                guest_favorite = False
                                print("Guest Favorite badge not found")

                            # Get full page content for historical analysis
                            full_content = self.driver.find_element(
                                By.XPATH,
                                '//*[@id="site-content"]/div/div[1]'
                            ).text
                            
                            # Check for historical house
                            historical_analysis = self.check_historical_house(full_content)
                            print("\nHistorical analysis:", json.dumps(historical_analysis, indent=2))

                            # Update listing_details with new information
                            listing_details.update({
                                "is_guest_favorite": guest_favorite,
                                "is_historical": historical_analysis["is_historical"],
                                "historical_evidence": historical_analysis["evidence"]
                            })

                            # Get amenities text
                            amenities_text = self.get_amenities_text()
                            if amenities_text:
                                print("\nAnalyzing amenities with Groq...")
                                amenities_analysis = self.check_amenities_with_groq(amenities_text)
                                if amenities_analysis:
                                    listing_details["amenities_analysis"] = amenities_analysis
                                    print("\nAmenities analysis:")
                                    print(json.dumps(amenities_analysis, indent=2))
                        except Exception as e:
                            print(f"Error processing amenities: {str(e)}")
                            listing_details["amenities_analysis"] = {}
                        
                        print("\nProcessed listing details:")
                        print("-" * 30)
                        print(json.dumps(listing_details, indent=2))
                        
                        # After all extractions, check for missing fields
                        missing_fields = [k for k, v in listing_details.items() if v == "N/A"]
                        if missing_fields:
                            print(f"\nAttempting to extract missing fields: {missing_fields}")
                            additional_details = self.extract_missing_details(full_content, missing_fields)
                            for field, value in additional_details.items():
                                if field in missing_fields and value:
                                    listing_details[field] = value
                                    print(f"Updated {field} to: {value}")

                        all_listings.append(listing_details)
                        
                        # Save progress after each listing
                        print("\nSaving progress to listing_details.json...")
                        with open('listing_details.json', 'w') as f:
                            json.dump(all_listings, f, indent=2)
                        print("Progress saved")
                        
                        print("\nClosing tab and switching back to main window...")
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        time.sleep(1)  # Reduced from 2 to 1
                        print("Successfully switched back to main window")
                    
                    except Exception as e:
                        print(f"\nError processing listing {index}: {str(e)}")
                        # Make sure we're back on the original window
                        if self.driver.current_window_handle != original_window:
                            print("Closing error tab and switching back to main window...")
                            self.driver.close()
                            self.driver.switch_to.window(original_window)
                
                print(f"\n{'='*50}")
                print(f"Final Results - Successfully processed {len(all_listings)} listings")
                print(f"{'='*50}")
                print(json.dumps(all_listings, indent=2))
                
            except TimeoutException:
                print("Timeout waiting for listings to load")
            except Exception as e:
                print(f"Error processing listings: {str(e)}")
                    
        except Exception as e:
            print(f"Error accessing URL: {str(e)}")
    
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
        """Save results to a JSON file"""
        if not filename:
            filename = f"airbnb_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"Results saved to {filename}")
    
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

def main():
    # Example usage
    scraper = AirbnbScraper()
    
    try:
        # Get the Airbnb search URL from user
        url = input("Enter the complete Airbnb search URL: ")
        num_pages = int(input("Enter number of pages to scrape (default 5): ") or 5)
        
        print(f"\nScraping Airbnb listings...")
        scraper.scrape_url(url, num_pages=num_pages)
        
        # Save results
        scraper.save_results()
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
