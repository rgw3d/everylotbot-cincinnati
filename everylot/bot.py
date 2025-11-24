#!/usr/bin/env python3
import argparse
import logging
import os
from dotenv import load_dotenv
### from . import __version__ as version
from .everylot import EveryLot
from .bluesky import BlueskyPoster

version = '0.3.1'

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='every lot bot for Twitter and Bluesky')
    parser.add_argument('--database', type=str, default=os.getenv('DATABASE_PATH', 'cincinnati.db'),
                      help='path to SQLite lots database')
    parser.add_argument('--id', type=str, default=os.getenv('START_PIN10'),
                      help='start with this PIN10 ID')
    parser.add_argument('-s', '--search-format', type=str, 
                      default=os.getenv('SEARCH_FORMAT', '{address}, {city} {state}'),
                      help='Python format string for searching Google')
    parser.add_argument('-p', '--print-format', type=str,
                      default=os.getenv('PRINT_FORMAT', '{address}, {zipcode}\n\nZoning: {zoning}\n\nLand Value: ${land_value:,}\n\nImprovement Value: ${improvement_value:,}\n\nNeighborhood: {neighborhood}\n\nAcreage: {acreage}'),
                      help='Python format string for post text')
    parser.add_argument('--dry-run', action='store_true',
                      help='Do not actually post')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Show debug output')
    parser.add_argument('--save-image', action='store_true',
                      help='Save the fetched image to disk')
    parser.add_argument('--no-image', action='store_true',
                      help='Skip fetching image from Google API')
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logger = logging.getLogger('everylot')

    # Initialize the lot finder
    el = EveryLot(args.database,
                  logger=logger,
                  print_format=args.print_format,
                  search_format=args.search_format,
                  id_=args.id)

    if not el.lot:
        logger.error('No lot found')
        return

    logger.debug('%s address: %s', el.lot['id'], el.lot.get('address'))

    # Get the streetview image
    image = None
    if not args.no_image:
        google_key = os.getenv('GOOGLE_API_KEY')
        image = el.get_streetview_image(google_key)

    # Initialize posters based on environment settings
    post_ids = []
    enable_bluesky = os.getenv('ENABLE_BLUESKY', 'true').lower() == 'true'

    if not enable_bluesky:
        logger.error('Bluesky is not enabled')
        return

    # Compose the post data with sanitized address
    post_data = el.compose()
    logger.info(f"Post text: {post_data['status']}")

    if args.save_image:
        if image:
            filename = f"image_{el.lot['id']}.jpg"
            with open(filename, 'wb') as f:
                f.write(image.getvalue())
            logger.info(f"Saved image to {filename}")
        else:
            logger.warning("No image to save (image fetching skipped)")

    if not args.dry_run:
        if enable_bluesky:
            try:
                bluesky = BlueskyPoster(logger=logger)
                # Get clean address for ALT text
                clean_address = el.sanitize_address(el.lot['address'])
                
                if image:
                    post_id = bluesky.post(post_data['status'], image, auditorIds=el.lot['auditor_parcel_ids'], clean_address=clean_address)
                    el.mark_as_posted('bluesky', post_id)
                    logger.info("Posted to Bluesky")
                else:
                    logger.warning("Skipping Bluesky post because no image was fetched")
            except Exception as e:
                logger.error(f"Failed to post to Bluesky: {e}")

if __name__ == '__main__':
    main()
