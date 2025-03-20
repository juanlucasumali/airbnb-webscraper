# Airbnb Web Scraper

This is a Python-based web scraper for Airbnb listings. It uses Selenium and BeautifulSoup to extract information about properties listed on Airbnb.

## Features

- Scrapes multiple pages of Airbnb listings
- Extracts key information including:
  - Title
  - URL
  - Price
  - Rating
  - Number of reviews
  - Property type
  - Amenities
- Saves results to CSV file
- Headless browser operation
- Configurable number of pages to scrape

## Installation

1. Clone this repository
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the script using Python:
```bash
python webscraper.py
```

The script will prompt you for:
1. Location to search (e.g., 'New-York')
2. Number of pages to scrape (default is 5)

The results will be saved to a CSV file in the current directory with the format: `airbnb_listings_YYYYMMDD_HHMMSS.csv`

## Requirements

- Python 3.7+
- Chrome browser installed
- Internet connection

## Notes

- The script uses a headless Chrome browser
- Respect Airbnb's terms of service and rate limiting
- Some listings might not be scraped if they don't follow the expected HTML structure
- The script includes error handling for common issues

## Disclaimer

This scraper is for educational purposes only. Make sure to review and comply with Airbnb's terms of service and robots.txt before using this scraper. 