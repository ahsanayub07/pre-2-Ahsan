# Pre-Internship Assignments — LimeOx AI Course

This repository contains my pre-internship assignments for the AI course at **LimeOx, Sargodha**. Each task focuses on developing practical skills in web scraping, data collection, database management, data preprocessing, and other areas of AI and data engineering.

## 📋 Project Overview

| Task | Description | Status |
|---|---|---|
| [Task 1 — Basic News Scraper](./task1/) | Scrape approximately 1,000 news articles | Pending |
| [Task 2 — Multi-Method News Scraper](./task2/) | Collect approximately 10,000 articles using BeautifulSoup, RSS feeds, and Selenium | Pending |
| [Task 3 — Large-Scale News Scraper](./task3/) | Scrape and import 100,000+ news articles into PostgreSQL | Completed |
| [Preprocessing Task](./preprocessing-task/) | Clean, normalize, and analyze the collected articles using Python and PostgreSQL | Completed |
| Future Tasks | Additional assignments related to AI, data science, machine learning, and data engineering | Planned |

*Note: Task 1 and Task 2 are listed for project planning and will be added when their implementations are available.*

---

## 🗂️ Repository Structure

```text
pre_interns_2/
│
├── README.md
│
├── task1/                    # Basic news scraper (planned)
│
├── task2/                    # Multi-method news scraper (planned)
│
├── task3/                    # Large-scale news scraper and importer
│
├── preprocessing-task/       # Article preprocessing pipeline
│
└── future-tasks/             # Optional location for future assignments
```

*The structure above describes the planned organization. Some folders may not exist until their tasks are added.*

---

## 📰 Task 1 — Basic News Scraper

**Objective:** Build a basic news scraper that collects approximately 1,000 news articles.

**Planned learning outcomes:**
- Understand the fundamentals of web scraping.
- Extract article titles, URLs, publication dates, and other available information.
- Store collected data in a structured format.
- Handle basic scraping errors.

**Status:** Pending implementation.

---

## 🌐 Task 2 — Multi-Method News Scraper

**Objective:** Collect approximately 10,000 news articles using multiple data collection techniques.

**Planned technologies:**
- BeautifulSoup for HTML parsing.
- RSS feeds for discovering news articles.
- Selenium for pages that require browser automation.

**Planned learning outcomes:**
- Understand different web scraping techniques.
- Combine multiple sources of article URLs.
- Handle pagination, dynamic pages, and duplicate URLs.
- Improve data collection and error handling.

**Status:** Pending implementation.

---

## 🗄️ Task 3 — Large-Scale News Scraper

**Objective:** Collect and import more than 100,000 news articles into a PostgreSQL database.

**Technologies:**
- Python
- Web scraping tools
- PostgreSQL
- SQL

**Key work:**
- Collect news articles at a large scale.
- Extract and organize article data into structured fields.
- Import the collected records into PostgreSQL.
- Store article information in a database table for further analysis.

**Result:** The source database contains **100,026 articles**.

**Status:** Completed.

---

## 🧹 Preprocessing Task — Article Data Cleaning

**Objective:** Prepare the collected news articles for further analysis by cleaning and standardizing the data.

**Technologies:**
- Python
- PostgreSQL
- psycopg2
- python-dotenv
- SQL

**Key work:**
- Connect Python to PostgreSQL.
- Read article records from the original `articles` table.
- Normalize whitespace in selected text fields.
- Generate normalized body hashes to identify duplicate article bodies.
- Flag records with potentially suspicious text encoding.
- Save processed records in a separate `articles_cleaned` table.
- Preserve the original source table without modifying its data.

**Initial processing results:**

| Metric | Result |
|---|---:|
| Original articles | 100,026 |
| Cleaned records saved | 100,026 |
| Missing titles | 0 |
| Missing article bodies | 0 |
| Duplicate body groups | 266 |
| Rows belonging to duplicate body groups | 1,045 |
| Rows flagged for suspicious encoding | 195 |

*These results reflect the current preprocessing run. Suspicious encoding is flagged for review rather than automatically repaired. Duplicate-body counts depend on the normalization method used.*

**Status:** Completed — initial preprocessing pipeline implemented and executed.

---

## 🚀 Future Tasks

This repository will be updated as additional pre-internship assignments are introduced.

Future tasks may cover:
- Advanced data cleaning and validation.
- Exploratory data analysis (EDA).
- Data visualization and reporting.
- SQL analysis and database optimization.
- Machine learning fundamentals.
- Natural language processing (NLP).
- Feature engineering and model evaluation.
- Other AI and data engineering projects.

Each new assignment will be documented with its objective, technologies, implementation details, results, and completion status.

---

## 🛠️ General Technologies

Depending on the assignment, this repository may use:

- **Programming:** Python
- **Web scraping:** BeautifulSoup, RSS, Selenium
- **Database:** PostgreSQL, SQL
- **Data processing:** pandas and Python utilities
- **Visualization:** Power BI, Matplotlib, or other suitable tools
- **AI/ML:** Relevant libraries introduced in future tasks

---

## 📌 Project Goals

1. Complete practical assignments from the LimeOx AI pre-internship program.
2. Build a structured collection of reusable projects.
3. Develop practical skills in data collection, preprocessing, databases, and AI.
4. Maintain clear documentation and reproducible workflows.
5. Track progress as new tasks are added.

---

## 👨‍💻 Author

**Ahsan Ayub**  
Software Engineering Student  
University of Sargodha, Pakistan

---

*This repository is a work in progress and will evolve as new assignments are completed.*
