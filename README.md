# Pre-Internship Assignments — LimeOx AI Course

This repository contains my completed pre-internship assignments for the AI course at **LimeOx, Sargodha, Pakistan**.

The projects focus on web scraping, data collection, database management, data preprocessing, and preparing structured datasets for future data analysis and AI applications.

## 📋 Project Overview

| Task | Description | Status |
|---|---|---|
| [Task 1 — Basic News Scraper](./task1/) | Scrape approximately 1,000 news articles | Completed |
| [Task 2 — Multi-Method News Scraper](./task2/) | Scrape approximately 10,000 articles using BeautifulSoup, RSS feeds, and Selenium | Completed |
| [Task 3 — Large-Scale News Scraper](./task3/) | Scrape and import 100,000+ news articles into PostgreSQL | Completed |
| [Preprocessing Task](./preprocessing-task/) | Clean and normalize article data, identify duplicate article bodies, and flag suspicious text encoding | Completed |
| Future Tasks | Additional assignments in AI, data science, machine learning, and data engineering | Planned |

---

## 📰 Task 1 — Basic News Scraper

**Objective:** Develop a basic web scraper to collect approximately 1,000 news articles.

**Key learning areas:**
- Fundamentals of web scraping.
- Extracting article titles, URLs, publication dates, and other available metadata.
- Organizing scraped information into a structured format.
- Handling basic scraping errors and missing data.

**Outcome:** Completed the basic news scraping assignment.

**Status:** Completed.

---

## 🌐 Task 2 — Multi-Method News Scraper

**Objective:** Collect approximately 10,000 news articles using multiple scraping and discovery techniques.

**Technologies:**
- **BeautifulSoup:** Parse HTML and extract article information.
- **RSS feeds:** Discover news articles from feed sources.
- **Selenium:** Automate browser interactions for pages requiring browser-based scraping.
- **Python:** Manage the scraping workflow and process collected information.

**Key learning areas:**
- Working with multiple article discovery methods.
- Extracting and organizing news data.
- Handling different website structures and scraping challenges.
- Reducing duplicate URLs and improving data collection.

**Outcome:** Completed the multi-method news scraping assignment.

**Status:** Completed.

---

## 🗄️ Task 3 — Large-Scale News Scraper and PostgreSQL Importer

**Objective:** Collect more than 100,000 news articles and store the collected data in PostgreSQL.

**Technologies:**
- Python
- Web scraping tools
- PostgreSQL
- SQL

**Key work:**
- Collect news articles at a large scale.
- Extract article information into structured fields.
- Organize the collected records for database storage.
- Import article data into PostgreSQL.
- Prepare the database for subsequent preprocessing and analysis.

**Result:** The source database contains **100,026 articles**.

**Status:** Completed.

---

## 🧹 Preprocessing Task — Article Data Cleaning

**Objective:** Clean and standardize the collected article data while preserving the original source table.

**Technologies:**
- Python
- PostgreSQL
- psycopg2
- python-dotenv
- SQL

**Key work:**
- Connect Python to PostgreSQL.
- Read records from the original `articles` table.
- Normalize whitespace in selected text fields.
- Generate normalized hashes to identify duplicate article bodies.
- Flag records with potentially suspicious text encoding.
- Store processed records in a separate `articles_cleaned` table.
- Preserve the original source data without modifying it.

### Processing Results

| Metric | Result |
|---|---:|
| Original articles | 100,026 |
| Cleaned records saved | 100,026 |
| Missing titles | 0 |
| Missing article bodies | 0 |
| Duplicate body groups | 266 |
| Rows belonging to duplicate body groups | 1,045 |
| Rows flagged for suspicious encoding | 195 |

*These figures reflect the current preprocessing run and its normalization rules. Suspicious encoding is flagged for review rather than automatically repaired. Duplicate-body counts depend on the normalization method.*

**Outcome:** Implemented and executed the preprocessing pipeline, with cleaned records stored separately from the original source data.

**Status:** Completed.

---

## 🗂️ Repository Structure

```text
pre_interns_2/
│
├── README.md
│
├── task1/
│   └── Basic news scraping assignment
│
├── task2/
│   └── BeautifulSoup, RSS, and Selenium scraper
│
├── task3/
│   └── Large-scale news scraper and PostgreSQL importer
│
├── preprocessing-task/
│   └── Article data preprocessing pipeline
│
└── Future assignments
```

*This is a high-level overview. The actual files and subfolders depend on the current repository structure.*

---

## 🛠️ Technologies Used

| Category | Technologies |
|---|---|
| Programming Language | Python |
| HTML Parsing | BeautifulSoup |
| Article Discovery | RSS feeds |
| Browser Automation | Selenium |
| Database | PostgreSQL |
| Database Queries | SQL |
| Python Database Connectivity | psycopg2 |
| Environment Configuration | python-dotenv |
| Data Processing | Python text-processing and hashing utilities |
| Version Control | Git and GitHub |

---

## 🔒 Data and Configuration

- Database credentials are stored in a local `.env` file.
- Secret configuration files should not be committed to GitHub.
- The original article table is preserved during preprocessing.
- Processed records are stored separately for validation and further analysis.
- Scraping activities should respect website terms, access restrictions, and `robots.txt` policies where applicable.

---

## 🚀 Future Tasks

This repository will continue to grow as new assignments are introduced during the LimeOx AI pre-internship program.

Potential future areas include:

- Data cleaning and validation improvements.
- Exploratory data analysis (EDA).
- SQL-based data analysis.
- Data visualization and reporting.
- Feature engineering.
- Machine learning fundamentals and model evaluation.
- Natural language processing (NLP).
- Additional AI and data engineering projects.

Each future assignment will be documented with its objective, technologies, implementation details, results, and completion status.

---

## 🎯 Project Goals

1. Apply concepts learned during the AI pre-internship program.
2. Build practical experience in web scraping and data collection.
3. Develop database management and SQL skills.
4. Learn how to clean, validate, and prepare real-world datasets.
5. Maintain reproducible, well-documented projects using Git and GitHub.
6. Extend the repository as new assignments are completed.

---

## 👨‍💻 Author

**Ahsan Ayub**  
Software Engineering Student  
University of Sargodha, Pakistan

---

*This repository documents my pre-internship learning journey and will be updated as additional assignments are completed.*
