"""Pure text helpers (no database, no model): the website name and the text a model will read."""
import re

_HOST_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)")
_WS_RE = re.compile(r"\s+")


def domain_from_url(url):
    """Website name from the stored URL: lower case, no 'www.', no port.

    Mirrors DOMAIN_SQL in data_analysis_task/domain_analysis.py so both stages agree.
    Returns '' when the URL has no scheme and host.
    """
    m = _HOST_RE.match(url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    host = re.sub(r"^www\.", "", host)
    return re.sub(r":[0-9]+$", "", host)


def normalize_whitespace(text):
    """Collapse every run of whitespace (including newlines) into one space."""
    return _WS_RE.sub(" ", text or "").strip()


def build_model_text(title, lead):
    """The text one article contributes to a model: title, then the opening of the body.

    Provisional format (Phase 3 may test alternatives). Returns '' if both parts are empty.
    """
    title, lead = normalize_whitespace(title), normalize_whitespace(lead)
    if not title:
        return lead
    if not lead:
        return title
    joiner = " " if title[-1] in ".!?:" else ". "
    return title + joiner + lead


def percentile(sorted_values, p):
    """Nearest-rank percentile (p from 0 to 100) of an already sorted list."""
    if not sorted_values:
        return None
    k = max(0, min(len(sorted_values) - 1, int(round(p / 100 * (len(sorted_values) - 1)))))
    return sorted_values[k]


def length_summary(values):
    """min, quartiles, 90th/99th percentile, max and mean of a list of numbers."""
    vals = sorted(values)
    if not vals:
        return {"count": 0}
    return {"count": len(vals), "min": vals[0], "p25": percentile(vals, 25),
            "median": percentile(vals, 50), "p75": percentile(vals, 75),
            "p90": percentile(vals, 90), "p99": percentile(vals, 99), "max": vals[-1],
            "mean": round(sum(vals) / len(vals), 1)}
