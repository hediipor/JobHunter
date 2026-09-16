"""Self-check: country-code resolution + location-first query coverage."""
from scraper import MAX_JSEARCH_QUERIES_PER_SCAN, _country_code


def demo():
    assert _country_code("Barcelona, Spain") == "es"
    assert _country_code("Spain") == "es"
    assert _country_code("Canada") == "ca"
    assert _country_code("Toronto, Canada") == "ca"
    assert _country_code("Amsterdam, Netherlands") == "nl"
    assert _country_code("Atlantis") is None

    # combo builder (mirrors scrape_all): terms alternate across locations so
    # both get used within one budget, instead of term[0] alone starving term[1]
    terms = ["Software Engineer", "Full Stack Developer"]
    locs = ["Barcelona, Spain", "Spain", "Canada", "Netherlands", "Germany",
            "Ireland", "Remote", "France", "Portugal", "United Kingdom"]
    terms2 = terms[:2] or terms[:1]
    combos = [(terms2[i % len(terms2)], l) for i, l in enumerate(locs)][:MAX_JSEARCH_QUERIES_PER_SCAN]

    queried = [l for _, l in combos]
    assert set(queried) == set(locs), f"not every location queried: {set(locs) - set(queried)}"
    used_terms = {t for t, _ in combos}
    assert used_terms == set(terms), f"not every term used: {set(terms) - used_terms}"
    # each location keeps a stable, predictable term (not random) across scans
    assert combos[0] == (terms[0], locs[0]) and combos[1] == (terms[1], locs[1])
    print("ok")


if __name__ == "__main__":
    demo()
