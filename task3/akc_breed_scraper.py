
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import OperationalError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Configuration
load_dotenv()

INPUT_FILE = Path(
    os.getenv("INPUT_FILE", "breed_names.csv")
).expanduser()

MAX_BREEDS = int(os.getenv("MAX_BREEDS", "10"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "akc_dogs"),
    "user": os.getenv("DB_USER", "akc_user"),
    "password": os.getenv("DB_PASSWORD"),
    "connect_timeout": 10,
}


def validate_configuration():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input CSV file was not found: {INPUT_FILE}"
        )

    if not DB_CONFIG["password"]:
        raise ValueError(
            "DB_PASSWORD is missing from the .env file."
        )


def create_breeds_table(connection):
    query = """
        CREATE TABLE IF NOT EXISTS akc_breeds (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            breed_name VARCHAR(255) NOT NULL UNIQUE,
            url TEXT NOT NULL,
            height TEXT,
            weight TEXT,
            life_expectancy TEXT,
            scraped_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def save_breed(connection, breed):
    query = """
        INSERT INTO akc_breeds (
            breed_name, url, height, weight, life_expectancy
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (breed_name)
        DO UPDATE SET
            url = EXCLUDED.url,
            height = EXCLUDED.height,
            weight = EXCLUDED.weight,
            life_expectancy = EXCLUDED.life_expectancy,
            updated_at = CURRENT_TIMESTAMP;
    """

    values = (
        breed["Breed Name"],
        breed["URL"],
        breed["Height"],
        breed["Weight"],
        breed["Life Expectancy"],
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, values)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def make_slug(breed_name):
    normalized = unicodedata.normalize("NFKD", breed_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def extract_value(detail_element):
    value_container = detail_element.find_element(
        By.CSS_SELECTOR, ".flex.flex-col"
    )

    values = [
        element.text.strip()
        for element in value_container.find_elements(
            By.CSS_SELECTOR,
            ".breed-page__hero__overview__subtitle"
        )
        if element.text.strip()
    ]

    return "; ".join(values) or None


def scrape_breed(driver, wait, breed_name):
    slug = make_slug(breed_name)
 
    if breed_name.strip().lower() == "poodle":
        url = "https://www.akc.org/dog-breeds/poodle-standard/"
    else:
        url = f"https://www.akc.org/dog-breeds/{slug}/"

    driver.get(url)

    overview = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                ".breed-page__hero__overview__icon-block-wrap"
            )
        )
    )

    details = overview.find_elements(
        By.CSS_SELECTOR,
        ".breed-page__hero__overview__icon-block"
    )

    if len(details) < 3:
        raise ValueError(
            f"Expected at least 3 overview blocks; found {len(details)}."
        )

    return {
        "Breed Name": breed_name,
        "URL": url,
        "Height": extract_value(details[0]),
        "Weight": extract_value(details[1]),
        "Life Expectancy": extract_value(details[2]),
    }


def main():
    validate_configuration()

    breeds_df = pd.read_csv(INPUT_FILE)

    if "Breed Name" not in breeds_df.columns:
        raise ValueError(
            "The CSV must contain a column named 'Breed Name'. "
            f"Available columns: {list(breeds_df.columns)}"
        )

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-notifications")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    saved = 0
    failed = 0
    skipped = 0

    try:
        with psycopg.connect(**DB_CONFIG) as connection:
            print(f"Connected to database: {DB_CONFIG['dbname']}")
            create_breeds_table(connection)
            print("Table akc_breeds is ready.")

            for index, raw_name in enumerate(breeds_df["Breed Name"]):
                if MAX_BREEDS > 0 and index >= MAX_BREEDS:
                    break

                if pd.isna(raw_name) or not str(raw_name).strip():
                    skipped += 1
                    continue

                breed_name = str(raw_name).strip()
                print(f"Processing {index + 1}: {breed_name}")

                try:
                    breed = scrape_breed(driver, wait, breed_name)
                    save_breed(connection, breed)
                    saved += 1
                    print(f"Saved: {breed_name}")
                except Exception as error:
                    failed += 1
                    print(
                        f"Failed: {breed_name} | "
                        f"{type(error).__name__}: {error}"
                    )

    except OperationalError as error:
        raise RuntimeError(
            "Could not connect to PostgreSQL. Check that the service "
            "is running and verify the .env credentials. "
            f"Original error: {error}"
        ) from error
    finally:
        driver.quit()

    print("\nCompleted")
    print(f"Saved or updated: {saved}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
