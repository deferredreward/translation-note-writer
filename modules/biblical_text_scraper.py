#!/usr/bin/env python3
"""
Biblical Text Scraper
Scrapes ULT/UST biblical text from Door43 preview pages with JavaScript rendering.
"""

import re
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urljoin
import requests

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class BiblicalTextScraper:
    """Scrapes biblical text from Door43 preview pages."""
    
    def __init__(self):
        """Initialize the scraper."""
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://preview.door43.org/u/unfoldingWord"
        
        # Book code mappings (3-letter codes to full names)
        self.book_codes = {
            'GEN': 'gen', 'EXO': 'exo', 'LEV': 'lev', 'NUM': 'num', 'DEU': 'deu',
            'JOS': 'jos', 'JDG': 'jdg', 'RUT': 'rut', '1SA': '1sa', '2SA': '2sa',
            '1KI': '1ki', '2KI': '2ki', '1CH': '1ch', '2CH': '2ch', 'EZR': 'ezr',
            'NEH': 'neh', 'EST': 'est', 'JOB': 'job', 'PSA': 'psa', 'PRO': 'pro',
            'ECC': 'ecc', 'SNG': 'sng', 'ISA': 'isa', 'JER': 'jer', 'LAM': 'lam',
            'EZK': 'ezk', 'DAN': 'dan', 'HOS': 'hos', 'JOL': 'jol', 'AMO': 'amo',
            'OBA': 'oba', 'JON': 'jon', 'MIC': 'mic', 'NAM': 'nam', 'HAB': 'hab',
            'ZEP': 'zep', 'HAG': 'hag', 'ZEC': 'zec', 'MAL': 'mal',
            'MAT': 'mat', 'MRK': 'mrk', 'LUK': 'luk', 'JHN': 'jhn', 'ACT': 'act',
            'ROM': 'rom', '1CO': '1co', '2CO': '2co', 'GAL': 'gal', 'EPH': 'eph',
            'PHP': 'php', 'COL': 'col', '1TH': '1th', '2TH': '2th', '1TI': '1ti',
            '2TI': '2ti', 'TIT': 'tit', 'PHM': 'phm', 'HEB': 'heb', 'JAS': 'jas',
            '1PE': '1pe', '2PE': '2pe', '1JN': '1jn', '2JN': '2jn', '3JN': '3jn',
            'JUD': 'jud', 'REV': 'rev'
        }
        
        if not SELENIUM_AVAILABLE:
            self.logger.warning("Selenium not available. Install with: pip install selenium")
    
    def scrape_biblical_text(self, book_code: str, text_type: str = 'ULT',
                             door43_username: str = None) -> Optional[Dict[str, Any]]:
        """Scrape biblical text from Door43.

        Args:
            book_code: 3-letter book code (e.g., 'DEU', 'OBA')
            text_type: 'ULT' or 'UST'
            door43_username: Optional Door43 username to try user's branch first

        Returns:
            Dictionary with book and chapters data
        """
        if not SELENIUM_AVAILABLE:
            self.logger.error("Selenium is required for scraping Door43. Please install: pip install selenium")
            return None

        try:
            # Convert book code to lowercase for URL
            book_lower = self.book_codes.get(book_code.upper())
            if not book_lower:
                self.logger.error(f"Unknown book code: {book_code}")
                return None

            book_upper = book_code.upper()
            text_lower = text_type.lower()

            # Setup Chrome driver
            driver = self._setup_driver()
            if not driver:
                return None

            try:
                # Try user branch first if username provided
                if door43_username:
                    user_branch = f"auto-{door43_username}-{book_upper}"
                    user_url = f"{self.base_url}/en_{text_lower}/{user_branch}?book={book_lower}"

                    self.logger.info(f"Trying user branch for {text_type} {book_code}: {user_url}")
                    result = self._try_scrape_url(driver, user_url, book_code)

                    if result and not self._is_error_page(driver):
                        self.logger.info(f"Successfully scraped {text_type} for {book_code} from user branch: {len(result.get('chapters', []))} chapters")
                        return result
                    else:
                        self.logger.info(f"User branch not found or error for {door43_username}/{book_upper}, falling back to master")

                # Fall back to (or use directly) master branch
                master_url = f"{self.base_url}/en_{text_lower}/master?book={book_lower}"
                self.logger.info(f"Scraping {text_type} for {book_code} from master: {master_url}")

                result = self._try_scrape_url(driver, master_url, book_code)
                if result:
                    self.logger.info(f"Successfully scraped {text_type} for {book_code} from master: {len(result.get('chapters', []))} chapters")
                return result

            finally:
                driver.quit()

        except Exception as e:
            self.logger.error(f"Error scraping {text_type} for {book_code}: {e}")
            return None

    def _is_error_page(self, driver: webdriver.Chrome) -> bool:
        """Check if the current page shows a Door43 error (branch doesn't exist).

        Args:
            driver: Chrome WebDriver instance

        Returns:
            True if page shows error indicating branch doesn't exist
        """
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            return "Unable to get a valid catalog entry for this resource" in page_text
        except Exception:
            return False

    def _try_scrape_url(self, driver: webdriver.Chrome, url: str, book_code: str) -> Optional[Dict[str, Any]]:
        """Try to scrape biblical text from a specific URL.

        Args:
            driver: Chrome WebDriver instance
            url: URL to scrape
            book_code: Book code for parsing

        Returns:
            Dictionary with book and chapters data, or None if failed
        """
        try:
            # Load the page
            driver.get(url)

            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Check for error page before proceeding
            if self._is_error_page(driver):
                return None

            # Check the USFM checkbox
            usfm_checked = self._check_usfm_checkbox(driver)
            if not usfm_checked:
                self.logger.warning("Could not find or check USFM checkbox, trying to extract content anyway")

            # Wait for content to load
            time.sleep(3)

            # Get the USFM content
            usfm_content = self._extract_usfm_content(driver)

            if not usfm_content:
                self.logger.warning("No USFM content found, trying alternative extraction methods")
                usfm_content = self._extract_alternative_content(driver)

            if not usfm_content:
                self.logger.error("No content found with any extraction method")
                return None

            # Parse USFM content
            parsed_data = self._parse_usfm_content(usfm_content, book_code)
            return parsed_data

        except Exception as e:
            self.logger.error(f"Error scraping from {url}: {e}")
            return None
    
    def _setup_driver(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome WebDriver with appropriate options.
        
        Returns:
            Chrome WebDriver instance or None
        """
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Try to create driver (assumes chromedriver is in PATH)
            driver = webdriver.Chrome(options=chrome_options)
            return driver
            
        except Exception as e:
            self.logger.error(f"Failed to setup Chrome driver: {e}")
            self.logger.error("Make sure chromedriver is installed and in PATH")
            return None
    
    def _check_usfm_checkbox(self, driver: webdriver.Chrome) -> bool:
        """Check the USFM checkbox on the page.

        Args:
            driver: Chrome WebDriver instance

        Returns:
            True if checkbox was found and checked
        """
        retries = 5
        for i in range(retries):
            try:
                # Check for error page BEFORE waiting for checkbox
                # Door43 JS may have rendered the error by now
                if self._is_error_page(driver):
                    self.logger.info("Error page detected, skipping USFM checkbox retries")
                    return False

                # Wait for the page to fully load, increasing wait time with each retry
                wait_time = 10 + (i * 5)
                self.logger.info(f"Attempt {i+1}/{retries}: Waiting up to {wait_time} seconds for USFM checkbox.")
                
                # Look for USFM checkbox - try multiple selectors
                selectors = [
                    "input[type='checkbox'][value='usfm']",
                    "input[type='checkbox']#usfm",
                    "input[type='checkbox'][name='usfm']",
                    "//input[@type='checkbox' and contains(@id, 'usfm')]",
                    "//input[@type='checkbox' and contains(@name, 'usfm')]",
                    "//input[@type='checkbox' and contains(@value, 'usfm')]",
                    "//label[contains(text(), 'USFM')]/input[@type='checkbox']",
                    "//label[contains(text(), 'usfm')]/input[@type='checkbox']"
                ]
                
                checkbox = None
                for selector in selectors:
                    try:
                        wait = WebDriverWait(driver, wait_time)
                        if selector.startswith('//'):
                            # XPath selector
                            condition = EC.presence_of_element_located((By.XPATH, selector))
                        else:
                            # CSS selector
                            condition = EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        
                        checkbox = wait.until(condition)
                        
                        if checkbox:
                            self.logger.debug(f"Found USFM checkbox with selector: {selector}")
                            break
                    except TimeoutException:
                        continue
                
                if not checkbox:
                    # Try to find any checkbox near "USFM" text
                    try:
                        usfm_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'USFM') or contains(text(), 'usfm')]")
                        for element in usfm_elements:
                            # Look for nearby checkbox
                            parent = element.find_element(By.XPATH, "./..")
                            checkbox = parent.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            if checkbox:
                                self.logger.debug("Found USFM checkbox near USFM text")
                                break
                    except NoSuchElementException:
                        pass
                
                if checkbox:
                    # Check if it's already checked
                    if not checkbox.is_selected():
                        # Click to check it
                        driver.execute_script("arguments[0].click();", checkbox)
                        self.logger.info("USFM checkbox checked")
                    else:
                        self.logger.info("USFM checkbox was already checked")
                    
                    # Wait for content to update
                    time.sleep(2)
                    return True
                else:
                    self.logger.warning(f"USFM checkbox not found on attempt {i+1}")
                    
            except Exception as e:
                self.logger.error(f"Error checking USFM checkbox on attempt {i+1}: {e}")

            if i < retries - 1:
                time.sleep(5)  # Wait before next retry

        self.logger.error("USFM checkbox not found after all retries.")
        return False
    
    def _extract_usfm_content(self, driver: webdriver.Chrome) -> Optional[str]:
        """Extract USFM content from the page.
        
        Args:
            driver: Chrome WebDriver instance
            
        Returns:
            USFM content as string
        """
        try:
            # Wait for content to load
            time.sleep(3)
            
            # Try multiple selectors for the content area
            content_selectors = [
                "pre",  # USFM is often in <pre> tags
                ".usfm-content",
                "#usfm-content", 
                ".content pre",
                ".markdown-body pre",
                "code",
                ".highlight",
                "[data-usfm]"
            ]
            
            content = None
            for selector in content_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        # Check if this looks like USFM content
                        if text and ('\\c ' in text or '\\v ' in text or '\\id ' in text):
                            content = text
                            self.logger.debug(f"Found USFM content with selector: {selector}")
                            break
                    if content:
                        break
                except NoSuchElementException:
                    continue
            
            if not content:
                # Fallback: get all text and look for USFM patterns
                page_text = driver.find_element(By.TAG_NAME, "body").text
                if '\\c ' in page_text or '\\v ' in page_text:
                    content = page_text
                    self.logger.debug("Found USFM content in page body")
            
            if content:
                self.logger.info(f"Extracted USFM content: {len(content)} characters")
                return content
            else:
                self.logger.error("No USFM content found on page")
                return None
                
        except Exception as e:
            self.logger.error(f"Error extracting USFM content: {e}")
            return None
    
    def _parse_usfm_content(self, usfm_content: str, book_code: str) -> Dict[str, Any]:
        """Parse USFM content into structured data.
        
        Args:
            usfm_content: Raw USFM content
            book_code: Book code for the content
            
        Returns:
            Structured biblical text data
        """
        try:
            chapters = []
            current_chapter = None
            current_chapter_num = None
            
            # Split content into lines
            lines = usfm_content.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Chapter marker: \c 1
                chapter_match = re.match(r'\\c\s+(\d+)', line)
                if chapter_match:
                    # Save previous chapter
                    if current_chapter is not None:
                        chapters.append({
                            'chapter': current_chapter_num,
                            'verses': current_chapter
                        })
                    
                    # Start new chapter
                    current_chapter_num = int(chapter_match.group(1))
                    current_chapter = []
                    continue
                
                # Verse marker: \v 1 verse content OR \v 41-42 combined verse content
                # Can be at start of line or embedded in poetry markup (e.g., "\q1 \v 3 content")
                verse_match = re.search(r'\\v\s+(\d+(?:-\d+)?)\s+(.*)', line)
                if verse_match and current_chapter is not None:
                    verse_range = verse_match.group(1)
                    verse_content = verse_match.group(2).strip()
                    
                    # Clean up USFM markup in verse content (including any preceding poetry markers)
                    verse_content = self._clean_usfm_markup(verse_content)
                    
                    # Handle combined verses (e.g., "41-42")
                    if '-' in verse_range:
                        start_verse, end_verse = map(int, verse_range.split('-'))
                        # Create individual verse entries for each verse in the range
                        for v_num in range(start_verse, end_verse + 1):
                            current_chapter.append({
                                'number': v_num,
                                'content': verse_content  # Same content for all verses in range
                            })
                    else:
                        # Single verse
                        verse_num = int(verse_range)
                        current_chapter.append({
                            'number': verse_num,
                            'content': verse_content
                        })
                    continue
                
                # Continuation of verse content (no \v marker)
                # This includes poetry lines like "\q2 text" that continue the previous verse
                if current_chapter and line and not line.startswith('\\c') and not re.search(r'\\v\s+\d+', line):
                    # Poetry markup or continuation line - add to last verse if it exists
                    if current_chapter:
                        last_verse = current_chapter[-1]
                        cleaned_line = self._clean_usfm_markup(line)
                        if cleaned_line:
                            # Add space only if both existing content and new content exist
                            if last_verse['content']:
                                last_verse['content'] += ' ' + cleaned_line
                            else:
                                last_verse['content'] = cleaned_line
            
            # Save last chapter
            if current_chapter is not None:
                chapters.append({
                    'chapter': current_chapter_num,
                    'verses': current_chapter
                })
            
            result = {
                'book': book_code,
                'chapters': chapters
            }
            
            self.logger.info(f"Parsed USFM content: {len(chapters)} chapters")
            return result
            
        except Exception as e:
            self.logger.error(f"Error parsing USFM content: {e}")
            return {'book': book_code, 'chapters': []}
    
    def _clean_usfm_markup(self, text: str) -> str:
        """Clean USFM markup from text.
        
        Args:
            text: Text with USFM markup
            
        Returns:
            Cleaned text
        """
        # Remove common USFM tags
        # \add, \nd, \wj, \em, etc.
        text = re.sub(r'\\add\s+([^\\]+)\\add\*', r'\1', text)
        text = re.sub(r'\\nd\s+([^\\]+)\\nd\*', r'\1', text)
        text = re.sub(r'\\wj\s+([^\\]+)\\wj\*', r'\1', text)
        text = re.sub(r'\\em\s+([^\\]+)\\em\*', r'\1', text)
        text = re.sub(r'\\qt\s+([^\\]+)\\qt\*', r'"\1"', text)
        
        # Remove footnotes and cross-references
        text = re.sub(r'\\f\s+[^\\]*\\f\*', '', text)
        text = re.sub(r'\\x\s+[^\\]*\\x\*', '', text)
        
        # Remove other markup
        text = re.sub(r'\\[a-z]+\*?', '', text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _extract_alternative_content(self, driver: webdriver.Chrome) -> Optional[str]:
        """Extract content using alternative methods when USFM is not available.
        
        Args:
            driver: Chrome WebDriver instance
            
        Returns:
            Content as string or None
        """
        try:
            self.logger.info("Trying alternative content extraction methods")
            
            # Method 1: Look for any content that might be biblical text
            content_selectors = [
                ".content",
                ".markdown-body",
                "#content",
                "main",
                "article",
                ".text-content",
                ".bible-text"
            ]
            
            for selector in content_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        # Look for verse-like patterns
                        if self._looks_like_biblical_text(text):
                            self.logger.info(f"Found biblical text with selector: {selector}")
                            return self._convert_to_usfm_format(text)
                except NoSuchElementException:
                    continue
            
            # Method 2: Get all visible text and try to parse it
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if self._looks_like_biblical_text(body_text):
                    self.logger.info("Found biblical text in body")
                    return self._convert_to_usfm_format(body_text)
            except Exception:
                pass
            
            self.logger.warning("No biblical text found with alternative methods")
            return None
            
        except Exception as e:
            self.logger.error(f"Error in alternative content extraction: {e}")
            return None
    
    def _looks_like_biblical_text(self, text: str) -> bool:
        """Check if text looks like biblical content.
        
        Args:
            text: Text to check
            
        Returns:
            True if text looks like biblical content
        """
        if not text or len(text) < 100:
            return False
        
        # Look for verse-like patterns
        verse_patterns = [
            r'\b\d+:\d+\b',  # Chapter:verse references
            r'\b\d+\s+[A-Z]',  # Verse number followed by text
            r'Chapter \d+',
            r'Verse \d+',
        ]
        
        pattern_count = 0
        for pattern in verse_patterns:
            if re.search(pattern, text):
                pattern_count += 1
        
        # Also check for common biblical words
        biblical_words = ['Lord', 'God', 'Yahweh', 'Israel', 'Jerusalem', 'prophet', 'covenant']
        word_count = sum(1 for word in biblical_words if word in text)
        
        return pattern_count >= 1 or word_count >= 2
    
    def _convert_to_usfm_format(self, text: str) -> str:
        """Convert regular text to USFM-like format for parsing.
        
        Args:
            text: Regular text
            
        Returns:
            USFM-formatted text
        """
        try:
            lines = text.split('\n')
            usfm_lines = []
            current_chapter = 1
            verse_number = 1
            
            # Add book identifier
            usfm_lines.append('\\id DEU')
            usfm_lines.append(f'\\c {current_chapter}')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line looks like a chapter header
                chapter_match = re.search(r'Chapter (\d+)', line, re.IGNORECASE)
                if chapter_match:
                    current_chapter = int(chapter_match.group(1))
                    usfm_lines.append(f'\\c {current_chapter}')
                    verse_number = 1
                    continue
                
                # Check if this line starts with a verse number
                verse_match = re.match(r'^(\d+)\s+(.+)', line)
                if verse_match:
                    verse_number = int(verse_match.group(1))
                    verse_content = verse_match.group(2)
                    usfm_lines.append(f'\\v {verse_number} {verse_content}')
                    continue
                
                # Check if this line contains a verse reference
                verse_ref_match = re.search(r'(\d+):(\d+)\s+(.+)', line)
                if verse_ref_match:
                    chapter_num = int(verse_ref_match.group(1))
                    verse_num = int(verse_ref_match.group(2))
                    verse_content = verse_ref_match.group(3)
                    
                    if chapter_num != current_chapter:
                        current_chapter = chapter_num
                        usfm_lines.append(f'\\c {current_chapter}')
                    
                    usfm_lines.append(f'\\v {verse_num} {verse_content}')
                    continue
                
                # If it looks like verse content, add it as a verse
                if len(line) > 20 and not line.startswith(('Chapter', 'Book', 'The')):
                    usfm_lines.append(f'\\v {verse_number} {line}')
                    verse_number += 1
            
            return '\n'.join(usfm_lines)
            
        except Exception as e:
            self.logger.error(f"Error converting to USFM format: {e}")
            return text  # Return original text as fallback


def test_scraper():
    """Test the biblical text scraper."""
    print("🧪 Testing Biblical Text Scraper")
    print("=" * 50)
    
    scraper = BiblicalTextScraper()
    
    # Test with Obadiah (small book)
    print("📖 Testing with Obadiah (ULT)...")
    ult_data = scraper.scrape_biblical_text('OBA', 'ULT')
    
    if ult_data:
        print(f"✅ ULT Success: {len(ult_data['chapters'])} chapters")
        if ult_data['chapters']:
            first_chapter = ult_data['chapters'][0]
            print(f"   Chapter {first_chapter['chapter']}: {len(first_chapter['verses'])} verses")
            if first_chapter['verses']:
                first_verse = first_chapter['verses'][0]
                print(f"   Verse {first_verse['number']}: {first_verse['content'][:100]}...")
    else:
        print("❌ ULT Failed")
    
    print()
    print("📖 Testing with Obadiah (UST)...")
    ust_data = scraper.scrape_biblical_text('OBA', 'UST')
    
    if ust_data:
        print(f"✅ UST Success: {len(ust_data['chapters'])} chapters")
        if ust_data['chapters']:
            first_chapter = ust_data['chapters'][0]
            print(f"   Chapter {first_chapter['chapter']}: {len(first_chapter['verses'])} verses")
            if first_chapter['verses']:
                first_verse = first_chapter['verses'][0]
                print(f"   Verse {first_verse['number']}: {first_verse['content'][:100]}...")
    else:
        print("❌ UST Failed")
    
    print()
    print("📖 Testing with Deuteronomy 22:1...")
    deu_data = scraper.scrape_biblical_text('DEU', 'ULT')
    
    if deu_data:
        # Find chapter 22
        chapter_22 = None
        for chapter in deu_data['chapters']:
            if chapter['chapter'] == 22:
                chapter_22 = chapter
                break
        
        if chapter_22:
            # Find verse 1
            verse_1 = None
            for verse in chapter_22['verses']:
                if verse['number'] == 1:
                    verse_1 = verse
                    break
            
            if verse_1:
                print(f"✅ Deuteronomy 22:1 found: {verse_1['content']}")
            else:
                print("❌ Deuteronomy 22:1 not found")
        else:
            print("❌ Deuteronomy chapter 22 not found")
    else:
        print("❌ Deuteronomy scraping failed")


if __name__ == '__main__':
    test_scraper() 