# Mzalendo Kenya Politicians Data Scraper

This project scrapes data about Kenyan political leaders from the Mzalendo website, compiling structured information about politicians in the National Assembly, Senate, and County Assemblies.

## Features

- Scrapes detailed politician profiles from Mzalendo
- Creates structured JSON data about Kenya's political leaders
- Supports multithreaded scraping for faster execution
- Extracts information including:
  - Basic details (name, position, party)
  - Contact information
  - Education background
  - Political history
  - Promises and statements
  - Attendance records
  - Committee memberships
- Generates county-specific data files
- Calculates useful statistics about the data
- Formats output to match specified schema

## Requirements

- Python 3.7+
- Required packages:
  - beautifulsoup4
  - requests
  - lxml

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/mzalendo-scraper.git
   cd mzalendo-scraper
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

Run the scraper with default settings to collect data from all sources:

```
python run_scraper.py --all
```

This will scrape the National Assembly, Senate, and County Assemblies, saving the data to the `kenyan_leaders_data` directory.

### Command Line Options

The script provides various command line options:

```
usage: run_scraper.py [-h] [--all] [--national-assembly] [--senate]
                     [--county-assemblies] [--counties COUNTIES]
                     [--threads THREADS] [--no-threading]
                     [--output-dir OUTPUT_DIR] [--format {standard,ahmed}]

Mzalendo Kenya Politicians Data Scraper

optional arguments:
  -h, --help            show this help message and exit
  --all                 Scrape all categories
  --national-assembly   Scrape National Assembly
  --senate              Scrape Senate
  --county-assemblies   Scrape County Assemblies
  --counties COUNTIES   Comma-separated list of specific counties to scrape
  --threads THREADS     Number of concurrent threads (default: 5)
  --no-threading        Disable threading for debugging
  --output-dir OUTPUT_DIR
                        Output directory (default: kenyan_leaders_data)
  --format {standard,ahmed}
                        Output format: standard or ahmed (matches provided example)
```

### Examples

Scrape only National Assembly:
```
python run_scraper.py --national-assembly
```

Scrape Senate and County Assemblies:
```
python run_scraper.py --senate --county-assemblies
```

Scrape specific counties only:
```
python run_scraper.py --counties "Nairobi,Mombasa,Kisumu"
```

Scrape with 10 concurrent threads:
```
python run_scraper.py --all --