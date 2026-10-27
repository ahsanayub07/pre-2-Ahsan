
from db import get_connection

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM public.articles;"
            )
            total = cursor.fetchone()[0]

        print("Database connection successful.")
        print(f"Articles available: {total:,}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
