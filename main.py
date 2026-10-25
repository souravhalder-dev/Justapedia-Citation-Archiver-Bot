"""Command-Line Interface for Justapedia Wayback Machine Citation Archiver Bot."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

from bot.article_scanner import ArticleScanner
from bot.config import config
from bot.database import Database
from bot.logging_config import setup_logging
from bot.mediawiki_client import MediaWikiClient
from bot.reporting import ScanReport


def parse_arguments() -> argparse.Namespace:
    """Parse and validate command line arguments."""
    parser = argparse.ArgumentParser(
        description="Justapedia Wayback Machine Citation Archiver Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --article "Kevin Gorey" --dry-run
  python main.py --input articles.txt --dry-run --report report.json
  python main.py --category "Living people" --limit 10 --dry-run
  python main.py --article "Kevin Gorey" --apply --max-edits 1
  python main.py --resume
        """,
    )

    # Article Discovery Options (Target)
    target_group = parser.add_mutually_exclusive_group(required=False)
    target_group.add_argument(
        "--article",
        type=str,
        help="Process a single article by its exact title",
    )
    target_group.add_argument(
        "--input",
        type=str,
        help="Process a list of article titles from a text file (one title per line)",
    )
    target_group.add_argument(
        "--category",
        type=str,
        help="Process articles belonging to a specific MediaWiki category",
    )
    target_group.add_argument(
        "--resume",
        action="store_true",
        help="Resume processing from the most recent incomplete job checkpoint",
    )

    # Execution Mode (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run without making any live edits to Justapedia (Enabled by default)",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly enable live editing to save changes on Justapedia",
    )

    # Operational Parameters
    parser.add_argument(
        "--max-edits",
        type=int,
        default=None,
        help="Maximum number of articles to edit in live-edit mode",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of articles to retrieve from category or file (default: 50)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="File path to export execution report (.json or .csv)",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        default=None,
        help="Specify a particular job ID when resuming an interrupted job",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed debug logging output",
    )

    return parser.parse_args()


def load_titles_from_file(file_path: str, limit: int = 50) -> List[str]:
    """Read article titles from a text file, ignoring empty lines and comments."""
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: Specified file does not exist: {file_path}", file=sys.stderr)
        sys.exit(1)

    titles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if clean and not clean.startswith("#"):
                titles.append(clean)
                if len(titles) >= limit:
                    break
    return titles


def main() -> None:
    """CLI execution entrypoint."""
    args = parse_arguments()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging(level=log_level, log_file="logs/bot.log")

    # Mode determination
    is_live_edit = bool(args.apply)
    is_dry_run = not is_live_edit

    if is_live_edit:
        logger.warning("LIVE EDIT MODE IS ACTIVE! Edits will be committed to Justapedia.")
    else:
        logger.info("DRY-RUN MODE ACTIVE: No edits will be saved.")

    db = Database(config.db_path)
    wiki_client = MediaWikiClient()

    titles_to_process: List[str] = []
    target_type = "unknown"
    target_name = "unknown"
    job_id = args.job_id
    is_resuming = bool(args.resume)

    if args.resume:
        latest = db.get_latest_job(incomplete_only=True)
        if not latest:
            logger.error("No incomplete job found in database to resume.")
            sys.exit(1)
        job_id = latest["id"]
        target_type = latest["target_type"]
        target_name = latest["target"]
        logger.info(f"Resuming job {job_id} for target '{target_name}' ({target_type})")

        # Refetch list based on target type
        if target_type == "article":
            titles_to_process = [target_name]
        elif target_type == "category":
            titles_to_process = wiki_client.get_category_members(target_name, limit=args.limit)
        elif target_type == "file":
            titles_to_process = load_titles_from_file(target_name, limit=args.limit)

    elif args.article:
        target_type = "article"
        target_name = args.article
        titles_to_process = [args.article]

    elif args.input:
        target_type = "file"
        target_name = args.input
        titles_to_process = load_titles_from_file(args.input, limit=args.limit)
        logger.info(f"Loaded {len(titles_to_process)} article titles from {args.input}")

    elif args.category:
        target_type = "category"
        target_name = args.category
        logger.info(f"Fetching articles for category '{args.category}' (limit {args.limit})...")
        titles_to_process = wiki_client.get_category_members(args.category, limit=args.limit)
        logger.info(f"Retrieved {len(titles_to_process)} articles from category.")

    else:
        logger.error("Please specify a target: --article, --input, --category, or --resume.")
        sys.exit(1)

    if not titles_to_process:
        logger.warning("No articles found to process.")
        sys.exit(0)

    # Initialize Scanner
    scanner = ArticleScanner(
        wiki_client=wiki_client,
        db=db,
        dry_run=is_dry_run,
        max_edits=args.max_edits,
    )

    logger.info(f"Starting processing of {len(titles_to_process)} article(s)...")

    # Run Scanner
    report = scanner.run_batch(
        titles=titles_to_process,
        target_type=target_type,
        target_name=target_name,
        job_id=job_id,
        resume=is_resuming,
    )

    # Print Diffs in Dry Run
    if is_dry_run and report.article_diffs:
        print("\n" + "=" * 60)
        print("                 PROPOSED WIKITEXT DIFFS")
        print("=" * 60)
        for title, diff in report.article_diffs.items():
            print(f"\n--- Diff for [[{title}]] ---")
            print(diff)

    # Print Summary Report
    print("\n" + report.get_summary_text())

    # Export Report if requested
    if args.report:
        rep_path = Path(args.report)
        if rep_path.suffix.lower() == ".csv":
            report.export_csv(rep_path)
        else:
            report.export_json(rep_path)
        print(f"\nSaved report to: {rep_path.resolve()}")


if __name__ == "__main__":
    main()
