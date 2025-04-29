#!/usr/bin/env python3

import argparse
import os
import sys
import json
from datetime import datetime
from enhanced_mzalendo_scraper import EnhancedMzalendoScraper


def setup_args():
    """Set up command line arguments"""
    parser = argparse.ArgumentParser(
        description='Mzalendo Kenya Politicians Data Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all categories (National Assembly, Senate, County Assemblies)
  python run_scraper.py --all
  
  # Scrape only National Assembly
  python run_scraper.py --national-assembly
  
  # Scrape Senate and County Assemblies
  python run_scraper.py --senate --county-assemblies
  
  # Scrape specific counties only
  python run_scraper.py --counties "Nairobi,Mombasa,Kisumu"
  
  # Scrape with 10 concurrent threads
  python run_scraper.py --all --threads 10
  
  # Output to specific directory
  python run_scraper.py --all --output-dir "./my_data"
"""
    )
    
    parser.add_argument('--all', action='store_true', help='Scrape all categories')
    parser.add_argument('--national-assembly', action='store_true', help='Scrape National Assembly')
    parser.add_argument('--senate', action='store_true', help='Scrape Senate')
    parser.add_argument('--county-assemblies', action='store_true', help='Scrape County Assemblies')
    parser.add_argument('--counties', type=str, help='Comma-separated list of specific counties to scrape')
    parser.add_argument('--threads', type=int, default=5, help='Number of concurrent threads (default: 5)')
    parser.add_argument('--no-threading', action='store_true', help='Disable threading for debugging')
    parser.add_argument('--output-dir', type=str, default='kenyan_leaders_data', help='Output directory (default: kenyan_leaders_data)')
    parser.add_argument('--format', type=str, choices=['standard', 'ahmed'], default='standard', 
                        help='Output format: standard or ahmed (matches provided example)')
    
    return parser.parse_args()


def print_banner():
    """Print script banner"""
    banner = """
┌─────────────────────────────────────────────────────┐
│                                                     │
│    MZALENDO KENYA POLITICIANS DATA SCRAPER          │
│                                                     │
└─────────────────────────────────────────────────────┘
    """
    print(banner)


def print_summary(results):
    """Print summary of scraped data"""
    print("\n" + "="*60)
    print("SCRAPING SUMMARY")
    print("="*60)
    print(f"National Assembly Members: {results.get('national_assembly', 0)}")
    print(f"Senate Members: {results.get('senate', 0)}")
    print(f"County Assembly Members: {results.get('county_assemblies', 0)}")
    print(f"Total Leaders Scraped: {results.get('total', 0)}")
    print(f"Total Time: {results.get('duration_seconds', 0)} seconds")
    print("="*60)


def format_output(output_dir, format_type):
    """Format output files if requested"""
    if format_type == 'ahmed':
        print("\nFormatting output to match example schema...")
        
        # Read all leaders file
        all_leaders_path = os.path.join(output_dir, "all_leaders.json")
        if os.path.exists(all_leaders_path):
            with open(all_leaders_path, 'r', encoding='utf-8') as f:
                all_leaders = json.load(f)
            
            # Import formatting function
            from enhanced_mzalendo_scraper import format_json_output
            
            # Format the data
            formatted_leaders = format_json_output(all_leaders)
            
            # Save formatted output
            formatted_path = os.path.join(output_dir, "formatted_leaders.json")
            with open(formatted_path, 'w', encoding='utf-8') as f:
                json.dump(formatted_leaders, f, indent=2, ensure_ascii=False)
            
            print(f"Formatted output saved to {formatted_path}")


def main():
    """Main entry point"""
    print_banner()
    args = setup_args()
    
    # Create timestamp for output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir
    
    # Create scraper instance
    scraper = EnhancedMzalendoScraper(
        output_dir=output_dir,
        max_workers=args.threads
    )
    
    # Determine what to scrape
    if not (args.all or args.national_assembly or args.senate or args.county_assemblies or args.counties):
        print("Error: You must specify what to scrape. Use --all or specific options.")
        print("Use --help for more information.")
        sys.exit(1)
    
    results = {}
    use_threading = not args.no_threading
    
    # Scrape everything
    if args.all:
        print(f"\nScraping all political leaders using {args.threads} threads...")
        results = scraper.scrape_all(use_threading=use_threading)
    
    # Scrape specific categories
    else:
        if args.national_assembly:
            print("\nScraping National Assembly...")
            national_assembly = scraper.scrape_leaders_threaded(
                "https://mzalendo.com/parliament/national_assembly/", 
                "national_assembly"
            ) if use_threading else scraper.scrape_leaders(
                "https://mzalendo.com/parliament/national_assembly/", 
                "national_assembly"
            )
            results["national_assembly"] = len(national_assembly)
        
        if args.senate:
            print("\nScraping Senate...")
            senate = scraper.scrape_leaders_threaded(
                "https://mzalendo.com/parliament/senate/", 
                "senate"
            ) if use_threading else scraper.scrape_leaders(
                "https://mzalendo.com/parliament/senate/", 
                "senate"
            )
            results["senate"] = len(senate)
        
        if args.county_assemblies:
            print("\nScraping County Assemblies...")
            county_assemblies_html = scraper.get_page("https://mzalendo.com/parliament/county_assemblies/")
            
            county_assemblies = []
            if county_assemblies_html:
                from bs4 import BeautifulSoup
                from urllib.parse import urljoin
                
                soup = BeautifulSoup(county_assemblies_html, 'html.parser')
                county_links = soup.select('.county-assembly-link')
                
                # Filter counties if specified
                specific_counties = []
                if args.counties:
                    specific_counties = [c.strip().lower() for c in args.counties.split(',')]
                
                for link in county_links:
                    county_name = link.text.strip()
                    
                    # Skip if not in specific counties list
                    if specific_counties and county_name.lower() not in specific_counties:
                        continue
                    
                    county_url = urljoin(scraper.base_url, link['href'])
                    
                    print(f"  Scraping {county_name} County Assembly...")
                    county_data = scraper.scrape_leaders_threaded(
                        county_url, 
                        "county_assemblies",
                        county_name
                    ) if use_threading else scraper.scrape_leaders(
                        county_url, 
                        "county_assemblies",
                        county_name
                    )
                    
                    county_assemblies.extend(county_data)
            
            results["county_assemblies"] = len(county_assemblies)
    
    # Calculate total
    results["total"] = sum(value for key, value in results.items() if key in ["national_assembly", "senate", "county_assemblies"])
    
    # Print summary
    print_summary(results)
    
    # Format output if requested
    format_output(output_dir, args.format)
    
    print(f"\nAll data has been saved to: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    main()
