-- Run after the import:  psql -U task3_user -h localhost -d task3_articles -f importer/verify.sql
\echo '1. Total rows (expect 100026 after the full import)'
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT url) AS distinct_urls FROM articles;

\echo '2. Duplicate URLs (expect 0 rows)'
SELECT url, COUNT(*) FROM articles GROUP BY url HAVING COUNT(*) > 1 LIMIT 5;

\echo '3. Top 10 sources'
SELECT source, COUNT(*) AS articles FROM articles GROUP BY source ORDER BY 2 DESC LIMIT 10;

\echo '4. Missing or empty required values (expect all 0)'
SELECT COUNT(*) FILTER (WHERE title = '')  AS empty_title,
       COUNT(*) FILTER (WHERE body = '')   AS empty_body,
       COUNT(*) FILTER (WHERE word_count < 0) AS negative_word_count
FROM articles;

\echo '5. Date and time coverage'
SELECT MIN(published_date) AS oldest, MAX(published_date) AS newest,
       COUNT(*) FILTER (WHERE published_date IS NULL) AS no_date,
       COUNT(*) FILTER (WHERE published_time IS NULL) AS no_time
FROM articles;

\echo '6. Size and word counts'
SELECT pg_size_pretty(pg_total_relation_size('articles')) AS table_size,
       ROUND(AVG(word_count)) AS avg_words, MAX(word_count) AS max_words
FROM articles;

\echo '7. Tags: articles with tags, and the most common tags'
SELECT COUNT(*) FILTER (WHERE cardinality(tags) > 0) AS with_tags FROM articles;
SELECT tag, COUNT(*) FROM articles, unnest(tags) AS tag GROUP BY tag ORDER BY 2 DESC LIMIT 5;

\echo '8. One sample row (shortened)'
SELECT id, source, left(title, 50) AS title, author, published_date, published_time,
       cardinality(tags) AS n_tags, word_count, method, left(body, 60) AS body_start
FROM articles ORDER BY id LIMIT 1;
