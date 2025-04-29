import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re
from urllib.parse import urljoin
import logging
from concurrent.futures import ThreadPoolExecutor


class EnhancedMzalendoScraper:
    def __init__(self, output_dir="scraped_data", max_workers=5):
        self.base_url = "https://mzalendo.com"
        self.session = requests.Session()
        self.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://mzalendo.com/"
        }
        self.output_dir = output_dir
        self.max_workers = max_workers

        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Create subdirectories for different types of leaders
        for subdir in ["national_assembly", "senate", "county_assemblies"]:
            subdir_path = os.path.join(output_dir, subdir)
            if not os.path.exists(subdir_path):
                os.makedirs(subdir_path)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(output_dir, "scraping.log")),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
      
    
    def get_page(self, url, retry_count=3):
        """Get page content with error handling, retries and rate limiting"""
        for attempt in range(retry_count):
            try:
                response = self.session.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                # Be nice to the server with increasing delays between retries
                time.sleep(1 + attempt * 0.5)  
                return response.text
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Attempt {attempt+1}/{retry_count} failed for {url}: {e}")
                if attempt == retry_count - 1:
                    self.logger.error(f"Failed to fetch {url} after {retry_count} attempts: {e}")
                    return None
                time.sleep(2 * (attempt + 1))  # Exponential backoff
        return None


    def scrape_leaders(self, url, category, subcategory=None):
        """Scrape leaders from a specific category page without threading"""
        self.logger.info(f"Scraping {category} from {url}")
        
        # Get the page content
        html = self.get_page(url)
        if not html:
            return []
        
        # Parse the politician list
        politicians = self.parse_politician_list_page(html, category)
        
        # Get pagination links
        pagination_urls = self.get_pagination_links(html)
        
        # Process additional pages
        for page_url in pagination_urls:
            self.logger.info(f"Processing page: {page_url}")
            page_html = self.get_page(page_url)
            politicians.extend(self.parse_politician_list_page(page_html, category))
        
        self.logger.info(f"Found {len(politicians)} politicians in {category}")
        detailed_politicians = []
        
        # Process each politician to get detailed information
        for politician in politicians:
            try:
                self.logger.info(f"Getting details for {politician['name']}")
                detail_html = self.get_page(politician['profile_url'])
                detailed_data = self.parse_politician_detail_page(detail_html, politician)
                
                if subcategory:
                    detailed_data['subcategory'] = subcategory
                    
                # Save individual JSON file
                self.save_politician_data(detailed_data, category)
                
                detailed_politicians.append(detailed_data)
            except Exception as e:
                self.logger.error(f"Error processing {politician['name']}: {e}")
                continue
        self.logger.info(f"Successfully scraped details for {len(detailed_politicians)} politicians in {category}")

        return detailed_politicians    
    
    def parse_politician_list_page(self, html, category):
        """Parse a page listing politicians"""
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'lxml')
        politician_items = soup.select('.person-item')
        politicians = []

        # Updated selector for politician cards
        politician_items = soup.select('.mp_card')
        
        for item in politician_items:
            try:
                name_elem = item.select_one('.shujaa_details a')
                if not name_elem:
                    continue
                
                name = name_elem.text.strip()
                profile_url = urljoin(self.base_url, name_elem['href'])
                
                # Extract position/constituency information
                position_elem = item.select_one('.shujaa_details p')
                position = position_elem.text.strip() if position_elem else "Unknown"
                
                # Parse constituency from position text
                constituency = None
                county = None
                
                if "Member for" in position:
                    constituency_match = re.search(r'Member for ([\w\s\-]+) Constituency', position)
                    if constituency_match:
                        constituency = constituency_match.group(1).strip()
                
                # Extract image if available
                img_elem = item.select_one('.mp_pic img')
                image_url = None
                if img_elem and 'src' in img_elem.attrs:
                    image_url = urljoin(self.base_url, img_elem['src'])
                    if image_url.endswith('default-person.jpg'):
                        image_url = None  # Skip default images
                
                politicians.append({
                    "name": name,
                    "position": position,
                    "constituency": constituency,
                    "county": county,  # Will be filled later if available
                    "profile_url": profile_url,
                    "image_url": image_url,
                    "category": category
                })
            except Exception as e:
                self.logger.error(f"Error parsing politician item: {e}")
                continue
        
        return politicians
    
    def get_pagination_links(self, html):
        """Extract pagination links"""
        soup = BeautifulSoup(html, 'lxml')
        pagination = soup.select('.pagination a')
        page_urls = []

        # Get numbered page links
        pagination_links = soup.select('.pagination-container a.number_box')
        for link in pagination_links:
            if 'href' in link.attrs:
                page_url = urljoin(self.base_url, link['href'])
                page_urls.append(page_url)

        # Add first page if not in pagination
        if not any ('page=1' in url for url in page_urls):
            base_url = urljoin(self.base_url, '/parliament/national_assembly/')
            page_urls.insert(0, base_url)

            # Remove duplicates while preserving order
            seen = set()
            return [x for x in page_urls if not (x in seen or seen.add(x))]


    def parse_politician_detail_page(self, html, basic_info):
        """Parse a politician's detail page"""
        if not html:
            return basic_info
        
        soup = BeautifulSoup(html, 'html.parser')
        politician_data = basic_info.copy()
        
        # Extract ID from URL
        politician_id = basic_info['profile_url'].strip('/').split('/')[-1]
        politician_data['id'] = politician_id
        
        # Extract details from profile
        try:
            # Party affiliation
            party_elem = soup.select_one('.person-party-membership')
            if party_elem:
                party_text = party_elem.text.strip()
                party_match = re.search(r'Member of ([\w\s\-]+)', party_text)
                if party_match:
                    politician_data['party'] = party_match.group(1).strip()
            
            # County information - look for it in the breadcrumbs or text
            county_elem = soup.select_one('.location a')
            if county_elem:
                county_text = county_elem.text.strip()
                if "County" in county_text:
                    politician_data['county'] = county_text.replace("County", "").strip()
            
            # Election data
            election_elem = soup.select_one('.election-results')
            if election_elem:
                election_data = {}
                date_elem = election_elem.select_one('.date')
                if date_elem:
                    election_data['electedDate'] = date_elem.text.strip()
                
                votes_elem = election_elem.select_one('.votes')
                if votes_elem:
                    votes_text = votes_elem.text.strip()
                    votes_match = re.search(r'(\d+)', votes_text)
                    if votes_match:
                        election_data['totalVotes'] = int(votes_match.group(1))
                
                if election_data:
                    politician_data['election'] = election_data
            
            # Contact information
            contact_section = soup.select_one('#contact') or soup.select_one('.contact-details')
            if contact_section:
                contact_info = {}
                
                # Email
                email_elem = contact_section.select_one('a[href^="mailto:"]')
                if email_elem:
                    contact_info['email'] = email_elem['href'].replace('mailto:', '').strip()
                
                # Phone
                phone_elems = contact_section.select('a[href^="tel:"]')
                if phone_elems:
                    contact_info['phone'] = [phone['href'].replace('tel:', '').strip() for phone in phone_elems]
                
                # Office location
                office_elem = contact_section.select_one('.address')
                if office_elem:
                    contact_info['office'] = office_elem.text.strip()
                
                # Social media
                social_media = {}
                
                twitter_elem = contact_section.select_one('a[href*="twitter.com"]')
                if twitter_elem:
                    social_media['twitter'] = twitter_elem['href'].strip()
                
                facebook_elem = contact_section.select_one('a[href*="facebook.com"]')
                if facebook_elem:
                    social_media['facebook'] = facebook_elem['href'].strip()
                
                if social_media:
                    contact_info['socialMedia'] = social_media
                
                if contact_info:
                    politician_data['contact'] = contact_info
            
            # Experience and education
            experience_section = soup.select_one('#experience') or soup.select('.person-detail-experience')
            if experience_section:
                education = []
                positions = []
                
                # Extract education entries
                education_entries = experience_section.select('.education-entry') or experience_section.select('.education')
                for entry in education_entries:
                    qualification = entry.select_one('.qualification') or entry
                    if qualification:
                        education_text = qualification.text.strip()
                        if education_text and len(education_text) > 5:  # Ensure it's not just an empty or invalid entry
                            education.append(education_text)
                
                if education:
                    politician_data['education'] = education
                
                # Extract position history
                position_entries = experience_section.select('.position-entry') or experience_section.select('.position')
                for entry in position_entries:
                    title_elem = entry.select_one('.position-title') or entry
                    org_elem = entry.select_one('.position-org')
                    date_elem = entry.select_one('.position-date') or entry.select_one('.date')
                    
                    if title_elem:
                        title_text = title_elem.text.strip()
                        if not title_text:
                            continue
                            
                        position_info = {
                            "title": title_text
                        }
                        
                        if org_elem:
                            position_info["organization"] = org_elem.text.strip()
                        
                        if date_elem:
                            date_text = date_elem.text.strip()
                            if date_text:
                                position_info["date"] = date_text
                        
                        positions.append(position_info)
                
                if positions:
                    politician_data['positions'] = positions
            
            # Promises and statements
            promises = []
            statements_section = soup.select('#statements .statement') or soup.select('.statement')
            for statement in statements_section:
                statement_date = statement.select_one('.statement-date') or statement.select_one('.date')
                statement_text = statement.select_one('.statement-text') or statement.select_one('.text')
                
                if statement_text:
                    promise_text = statement_text.text.strip()
                    if promise_text:
                        promise = {
                            "id": f"pr{len(promises)+1}",
                            "description": promise_text,
                            "category": self.categorize_promise(promise_text)
                        }
                        
                        if statement_date:
                            date_text = statement_date.text.strip()
                            if date_text:
                                promise["madeDate"] = date_text
                                # Set a future due date (3 years from made date)
                                if re.match(r'\d{4}-\d{2}-\d{2}', date_text):
                                    year, month, day = date_text.split('-')
                                    due_year = int(year) + 3
                                    promise["dueDate"] = f"{due_year}-{month}-{day}"
                        
                        promise["status"] = "in-progress"  # Default status
                        promises.append(promise)
            
            if promises:
                politician_data['promises'] = promises
            
            # Attendance records if available
            attendance_section = soup.select_one('#attendance') or soup.select_one('.attendance')
            if attendance_section:
                attendance = []
                attendance_entries = attendance_section.select('.attendance-record') or attendance_section.select('table tr')
                
                for entry in attendance_entries:
                    if entry.select_one('th'):  # Skip header row
                        continue
                        
                    period_elem = entry.select_one('.period') or entry.select_one('td:nth-child(1)')
                    present_elem = entry.select_one('.present') or entry.select_one('td:nth-child(2)')
                    absent_elem = entry.select_one('.absent') or entry.select_one('td:nth-child(3)')
                    
                    if period_elem:
                        period_text = period_elem.text.strip()
                        if period_text:
                            attendance_record = {
                                "period": period_text
                            }
                            
                            if present_elem:
                                present_text = present_elem.text.strip()
                                if present_text and re.search(r'\d+', present_text):
                                    attendance_record["present"] = int(re.search(r'\d+', present_text).group())
                            
                            if absent_elem:
                                absent_text = absent_elem.text.strip()
                                if absent_text and re.search(r'\d+', absent_text):
                                    attendance_record["absent"] = int(re.search(r'\d+', absent_text).group())
                            
                            if "present" in attendance_record and "absent" in attendance_record:
                                attendance_record["total"] = attendance_record["present"] + attendance_record["absent"]
                            
                            attendance.append(attendance_record)
                
                if attendance:
                    politician_data['attendance'] = attendance
            
            # Committees
            committees_section = soup.select_one('#committees') or soup.select_one('.committees')
            if committees_section:
                committees = []
                committee_entries = committees_section.select('.committee') or committees_section.select('li')
                
                for entry in committee_entries:
                    committee_text = entry.text.strip()
                    if committee_text:
                        committees.append(committee_text)
                
                if committees:
                    politician_data['committees'] = committees
            
            # Enrich with some additional calculated fields
            
            # Calculate approval rating based on attendance (just an example)
            if 'attendance' in politician_data and politician_data['attendance']:
                total_present = sum(record.get('present', 0) for record in politician_data['attendance'])
                total_sessions = sum(record.get('total', 0) for record in politician_data['attendance'])
                
                if total_sessions > 0:
                    approval_rating = round((total_present / total_sessions) * 5, 1)  # Scale to 0-5
                    politician_data['approvalRating'] = approval_rating
            
            # Add some key achievements based on statements/promises
            if 'promises' in politician_data and politician_data['promises']:
                achievements = []
                for promise in politician_data['promises'][:5]:  # Take up to 5 promises as achievements
                    achievements.append(promise['description'])
                
                if achievements:
                    politician_data['keyAchievements'] = achievements
        
        except Exception as e:
            self.logger.error(f"Error parsing detail page for {basic_info['name']}: {e}")
        
        return politician_data
    
    def categorize_promise(self, promise_text):
        """Categorize a promise based on its text content"""
        # Simple keyword-based categorization
        categories_keywords = {
            "Education": ["education", "school", "university", "college", "student", "learning"],
            "Healthcare": ["health", "hospital", "medical", "clinic", "doctor", "disease", "treatment"],
            "Infrastructure": ["road", "bridge", "building", "construction", "infrastructure"],
            "Water": ["water", "irrigation", "dam", "borehole", "pipeline"],
            "Agriculture": ["farm", "agriculture", "crop", "livestock", "cattle", "dairy"],
            "Economy": ["economy", "business", "enterprise", "job", "employment", "income"],
            "Security": ["security", "police", "crime", "safety"]
        }
        
        promise_lower = promise_text.lower()
        
        for category, keywords in categories_keywords.items():
            for keyword in keywords:
                if keyword in promise_lower:
                    return category
        
        return "Other"  # Default category
    
    def scrape_leaders_threaded(self, url, category, subcategory=None):
        """Scrape leaders from a specific category page using threading for details"""
        self.logger.info(f"Scraping {category} {'- ' + subcategory if subcategory else ''} from {url}")
        
        # Get first page
        html = self.get_page(url)
        if not html:
            return []
        
        # Get all politicians from first page
        politicians = self.parse_politician_list_page(html, category)
        
        # Get pagination links
        pagination_urls = self.get_pagination_links(html)
        
        # Process additional pages
        for page_url in pagination_urls:
            self.logger.info(f"Processing page: {page_url}")
            page_html = self.get_page(page_url)
            politicians.extend(self.parse_politician_list_page(page_html, category))
        
        self.logger.info(f"Found {len(politicians)} politicians in {category}")
        
        # Use threading to get detailed information for each politician
        detailed_politicians = []
        
        # Function to process a single politician
        def process_politician(politician):
            try:
                self.logger.info(f"Getting details for {politician['name']}")
                detail_html = self.get_page(politician['profile_url'])
                detailed_data = self.parse_politician_detail_page(detail_html, politician)
                
                if subcategory:
                    detailed_data['subcategory'] = subcategory
                    
                # Save individual JSON file
                self.save_politician_data(detailed_data, category)
                
                return detailed_data
            except Exception as e:
                self.logger.error(f"Error processing {politician['name']}: {e}")
                return None
        
        # Use ThreadPoolExecutor to speed up detail page scraping
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(process_politician, politicians))
        
        # Filter out None results (failed scrapes)
        detailed_politicians = [p for p in results if p is not None]
        
        self.logger.info(f"Successfully scraped details for {len(detailed_politicians)} politicians in {category}")
        return detailed_politicians
    
    def save_politician_data(self, politician_data, category):
        """Save individual politician data to JSON file"""
        if 'id' not in politician_data:
            # Generate ID from name if not available
            politician_id = politician_data['name'].lower().replace(' ', '-')
        else:
            politician_id = politician_data['id']
        
        # Sanitize ID for filename
        safe_id = re.sub(r'[^\w\-]', '', politician_id)
        
        # Save to appropriate directory
        filename = os.path.join(self.output_dir, category, f"{safe_id}.json")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(politician_data, f, indent=2, ensure_ascii=False)
    
    def enrich_county_data(self, politicians_data):
        """Add county information based on constituency"""
        # Kenya constituency-county mapping (partial)
        constituency_county_map = {
            "Tarbaj": "Wajir",
            "Lafey": "Mandera",
            "Kamukunji": "Nairobi",
            "Rongo": "Migori",
            "Tigania East": "Meru",
            "Wajir East": "Wajir",
            "Wajir South": "Wajir",
            "Bura": "Tana River",
            "Lomas": "Tana River",
            "Bomachoge Chache": "Kisii",
            "Ijara": "Garissa",
            "Nyali": "Mombasa",
            "Rangwe": "Homa Bay",
            "Turkana South": "Turkana"
            # Add more mappings as needed
        }
        
        enriched_data = []
        for politician in politicians_data:
            if 'constituency' in politician and politician['constituency'] and not politician.get('county'):
                constituency = politician['constituency']
                if constituency in constituency_county_map:
                    politician['county'] = constituency_county_map[constituency]
            
            enriched_data.append(politician)
        
        return enriched_data
    
    def scrape_all(self, use_threading=True):
        """Scrape data from all sources"""
        start_time = time.time()
        self.logger.info("Starting complete scrape of Mzalendo website")
        
        scrape_function = self.scrape_leaders_threaded if use_threading else self.scrape_leaders
        
        # National Assembly
        self.logger.info("=== Scraping National Assembly ===")
        national_assembly = scrape_function(
            "https://mzalendo.com/parliament/national_assembly/", 
            "national_assembly"
        )
        
        # Senate
        self.logger.info("=== Scraping Senate ===")
        senate = scrape_function(
            "https://mzalendo.com/parliament/senate/", 
            "senate"
        )
        
        # County Assemblies
        self.logger.info("=== Scraping County Assemblies ===")
        county_assemblies_html = self.get_page("https://mzalendo.com/parliament/county_assemblies/")
        
        county_assemblies = []
        if county_assemblies_html:
            soup = BeautifulSoup(county_assemblies_html, 'html.parser')
            county_links = soup.select('.county-assembly-link')
            
            for link in county_links:
                county_name = link.text.strip()
                county_url = urljoin(self.base_url, link['href'])
                
                county_data = scrape_function(
                    county_url, 
                    "county_assemblies",
                    county_name
                )
                
                county_assemblies.extend(county_data)
        
        # Enrich data with county information where missing
        national_assembly = self.enrich_county_data(national_assembly)
        senate = self.enrich_county_data(senate)
        
        # Create summary files
        self.save_summary_data(national_assembly, "national_assembly")
        self.save_summary_data(senate, "senate")
        self.save_summary_data(county_assemblies, "county_assemblies")
        
        # Create a combined data file
        all_leaders = national_assembly + senate + county_assemblies
        
        # Save all leaders to a single file
        with open(os.path.join(self.output_dir, "all_leaders.json"), 'w', encoding='utf-8') as f:
            json.dump(all_leaders, f, indent=2, ensure_ascii=False)
        
        # Generate county-wise data
        self.generate_county_data(all_leaders)
        
        # Generate statistics
        self.generate_statistics(all_leaders)
        
        end_time = time.time()
        duration = round(end_time - start_time)
        self.logger.info(f"Scraping complete in {duration} seconds. Data saved to {self.output_dir}")
        
        return {
            "national_assembly": len(national_assembly),
            "senate": len(senate),
            "county_assemblies": len(county_assemblies),
            "total": len(all_leaders),
            "duration_seconds": duration
        }
    
    def save_summary_data(self, data, category):
        """Save summary data for a category"""
        filename = os.path.join(self.output_dir, f"{category}_summary.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def generate_county_data(self, all_leaders):
        """Generate county-wise data files"""
        counties = {}
        
        for leader in all_leaders:
            if 'county' in leader and leader['county']:
                county = leader['county']
                if county not in counties:
                    counties[county] = []
                counties[county].append(leader)
        
        # Create county directory if it doesn't exist
        county_dir = os.path.join(self.output_dir, "counties")
        if not os.path.exists(county_dir):
            os.makedirs(county_dir)
        
        # Save county-wise data
        for county, leaders in counties.items():
            safe_county = re.sub(r'[^\w\-]', '', county.lower().replace(' ', '_'))
            filename = os.path.join(county_dir, f"{safe_county}.json")
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(leaders, f, indent=2, ensure_ascii=False)
        
        # Save county summary
        county_summary = [{"name": county, "leaders_count": len(leaders)} for county, leaders in counties.items()]
        with open(os.path.join(self.output_dir, "counties_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(county_summary, f, indent=2, ensure_ascii=False)
    
    def generate_statistics(self, all_leaders):
        """Generate various statistics about the leaders"""
        stats = {
            "total_leaders": len(all_leaders),
            "by_category": {},
            "by_party": {},
            "by_gender": {"male": 0, "female": 0, "unknown": 0},
            "education_levels": {},
            "attendance_average": 0,
            "projects_total": 0,
            "promises_by_category": {}
        }
        
        # Process each leader to compile statistics
        total_attendance = 0
        leaders_with_attendance = 0
        
        for leader in all_leaders:
            # Category stats
            category = leader.get('category', 'unknown')
            if category not in stats["by_category"]:
                stats["by_category"][category] = 0
            stats["by_category"][category] += 1
            
            # Party stats
            party = leader.get('party', 'unknown')
            if party not in stats["by_party"]:
                stats["by_party"][party] = 0
            stats["by_party"][party] += 1
            
            # Gender stats (estimated from name, not ideal but a placeholder)
            # This is a very rough estimate and should be replaced with actual data
            name = leader.get('name', '')
            if name.startswith('Ms.') or name.startswith('Mrs.') or 'women' in leader.get('position', '').lower():
                stats["by_gender"]["female"] += 1
            elif name.startswith('Mr.') or name.startswith('Hon.'):
                stats["by_gender"]["male"] += 1
            else:
                stats["by_gender"]["unknown"] += 1
            
            # Education stats
            if 'education' in leader:
                for edu in leader['education']:
                    degree_type = "unknown"
                    if "phd" in edu.lower() or "doctorate" in edu.lower():
                        degree_type = "PhD"
                    elif "master" in edu.lower():
                        degree_type = "Masters"
                    elif "bachelor" in edu.lower() or "degree" in edu.lower():
                        degree_type = "Bachelors"
                    elif "diploma" in edu.lower():
                        degree_type = "Diploma"
                    elif "certificate" in edu.lower():
                        degree_type = "Certificate"
                    
                    if degree_type not in stats["education_levels"]:
                        stats["education_levels"][degree_type] = 0
                    stats["education_levels"][degree_type] += 1
            
            # Attendance stats
            if 'attendance' in leader and leader['attendance']:
                leader_attendance = 0
                total_sessions = 0
                
                for record in leader['attendance']:
                    if 'present' in record and 'total' in record and record['total'] > 0:
                        leader_attendance += record['present'] / record['total']
                        total_sessions += 1
                
                if total_sessions > 0:
                    total_attendance += (leader_attendance / total_sessions) * 100
                    leaders_with_attendance += 1
            
            # Projects stats
            if 'projects' in leader:
                stats["projects_total"] += len(leader['projects'])
            
            # Promises by category
            if 'promises' in leader:
                for promise in leader['promises']:
                    category = promise.get('category', 'Other')
                    if category not in stats["promises_by_category"]:
                        stats["promises_by_category"][category] = 0
                    stats["promises_by_category"][category] += 1
        
        # Calculate average attendance
        if leaders_with_attendance > 0:
            stats["attendance_average"] = round(total_attendance / leaders_with_attendance, 2)
        
        # Save statistics to file
        with open(os.path.join(self.output_dir, "statistics.json"), 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)


def format_json_output(json_data):
    """Format JSON data to match the example format"""
    output = []
    
    for leader in json_data:
        # Format leader data according to example
        formatted_leader = {
            "id": leader.get("id", "").lower().replace(" ", "-"),
            "name": leader.get("name", ""),
            "position": leader.get("position", ""),
            "county": leader.get("county", ""),
            "party": leader.get("party", ""),
            "imageUrl": leader.get("image_url", "")
        }
        
        # Add electoral information
        if "election" in leader and "electedDate" in leader["election"]:
            formatted_leader["electedDate"] = leader["election"]["electedDate"]
        
        if "approvalRating" in leader:
            formatted_leader["approvalRating"] = leader["approvalRating"]
        
        if "election" in leader and "totalVotes" in leader["election"]:
            formatted_leader["totalVotes"] = leader["election"]["totalVotes"]
        
        # Add contact information
        if "contact" in leader:
            formatted_leader["contact"] = {
                "email": leader["contact"].get("email", ""),
                "office": leader["contact"].get("office", "")
            }
            
            if "socialMedia" in leader["contact"]:
                formatted_leader["contact"]["socialMedia"] = leader["contact"]["socialMedia"]
        
        # Add education
        if "education" in leader:
            formatted_leader["education"] = leader["education"]
        
        # Add projects
        if "projects" in leader:
            formatted_leader["projects"] = leader["projects"]
        
        # Add promises
        if "promises" in leader:
            formatted_leader["promises"] = leader["promises"]
        
        # Add attendance
        if "attendance" in leader:
            formatted_leader["attendance"] = leader["attendance"]
        
        # Add key achievements
        if "keyAchievements" in leader:
            formatted_leader["keyAchievements"] = leader["keyAchievements"]
        
        output.append(formatted_leader)
    
    return output


def main():
    scraper = EnhancedMzalendoScraper(output_dir="kenyan_leaders_data")
    results = scraper.scrape_all(use_threading=True)
    
    print("\nScraping Results:")
    print(f"National Assembly Members: {results['national_assembly']}")
    print(f"Senate Members: {results['senate']}")
    print(f"County Assembly Members: {results['county_assemblies']}")
    print(f"Total Leaders Scraped: {results['total']}")
    print(f"Total Time: {results['duration_seconds']} seconds")


if __name__ == "__main__":
    main()
        