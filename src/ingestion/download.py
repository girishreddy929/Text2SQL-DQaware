"""Run:  python -m src.ingestion.download
Downloads the Olist datasets from Kaggle into data/raw/.
Skips anything already present, so it is safe to re-run."""

import sys

from dotenv import load_dotenv

from config.settings import ENV_FILE, PROJECT_ROOT
from src.common.logging import get_logger

log = get_logger("download")

RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Kaggle dataset slug -> the CSV files we expect to find afterwards
DATASETS = {
    "olistbr/brazilian-ecommerce": [
        "olist_customers_dataset.csv",
        "olist_geolocation_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv",
        "olist_orders_dataset.csv",
        "olist_products_dataset.csv",
        "olist_sellers_dataset.csv",
        "product_category_name_translation.csv",
    ],
    "olistbr/marketing-funnel-olist": [
        "olist_marketing_qualified_leads_dataset.csv",
        "olist_closed_deals_dataset.csv",
    ],
}


def missing_files(slug: str) -> list[str]:
    return [f for f in DATASETS[slug] if not (RAW_DIR / f).exists()]


def download_dataset(slug: str) -> bool:
    """Download + unzip one dataset. Returns True on success."""
    try:
        # Imported here because the kaggle package can raise on import if
        # credentials are missing; we want to catch that and explain it.
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(slug, path=str(RAW_DIR), unzip=True, quiet=False)
        return True
    except Exception as exc:  # broad on purpose: auth, network, terms not accepted
        log.error("Kaggle download of %s failed: %s: %s", slug, type(exc).__name__, exc)
        log.error(
            "Manual fallback: open https://www.kaggle.com/datasets/%s , click Download, "
            "unzip, and copy the CSVs directly into %s",
            slug,
            RAW_DIR,
        )
        return False


def main() -> int:
    load_dotenv(ENV_FILE)  # puts KAGGLE_* from .env into the environment
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    ok = True
    for slug in DATASETS:
        todo = missing_files(slug)
        if not todo:
            log.info(
                "%s: all %d files already present, skipping", slug, len(DATASETS[slug])
            )
            continue
        log.info("%s: missing %d file(s), downloading...", slug, len(todo))
        if not download_dataset(slug):
            ok = False

    print("\nFile check")
    print("-" * 60)
    all_present = True
    for slug, files in DATASETS.items():
        for f in files:
            path = RAW_DIR / f
            if path.exists():
                print(f"[OK]      {f:<48} {path.stat().st_size / 1_048_576:7.1f} MB")
            else:
                print(f"[MISSING] {f}")
                all_present = False
    print("-" * 60)
    print(
        "All 11 files present" if all_present else "Some files are missing (see above)"
    )
    return 0 if (ok and all_present) else 1


if __name__ == "__main__":
    sys.exit(main())
