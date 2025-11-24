#!/usr/bin/env python3
import os
import logging
import sqlite3
from tqdm import tqdm
from everylot.everylot import EveryLot

# Setup logging to suppress debug output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('everylot')

def main():
    database = 'cincinnati.db'
    output_file = 'long_posts.txt'
    
    print(f"Connecting to {database}...")
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all IDs
    print("Fetching all lot IDs...")
    cursor.execute("SELECT ogc_fid FROM cincinnati_lots ORDER BY ogc_fid")
    rows = cursor.fetchall()
    total_lots = len(rows)
    print(f"Found {total_lots} lots.")
    
    long_posts = []
    
    # Initialize EveryLot once
    # We don't need a specific ID yet, we'll set it in the loop or create new instances
    # Creating new instances might be cleaner to ensure state reset, but let's see if we can reuse.
    # EveryLot takes an ID in __init__. Let's just instantiate it inside the loop or modify it.
    # Looking at EveryLot code, it fetches the lot in __init__. 
    # So we have to instantiate it for each lot. 
    # To make it faster, we could optimize, but for 98k lots, instantiating a class is fast enough compared to DB fetch.
    
    print("Validating post lengths...")
    with open(output_file, 'w') as f:
        f.write(f"Checking {total_lots} lots for posts > 300 characters\n")
        f.write("="*50 + "\n\n")
        
        for row in tqdm(rows):
            lot_id = row['ogc_fid']
            
            try:
                # Initialize EveryLot for this ID
                # We pass print_format explicitly to match bot.py default
                print_format = '{address}, {zipcode}\n\nZoning: {zoning}\n\nLand Value: ${land_value:,}\n\nImprovement Value: ${improvement_value:,}\n\nNeighborhood: {neighborhood}\n\nAcreage: {acreage}'
                
                el = EveryLot(database, logger=logger, id_=lot_id, print_format=print_format)
                
                if not el.lot:
                    continue
                
                # Compose post
                post_data = el.compose()
                status = post_data['status']
                length = len(status)
                
                if length > 300:
                    f.write(f"ID: {lot_id} | Length: {length}\n")
                    f.write(f"{status}\n")
                    f.write("-" * 30 + "\n")
                    long_posts.append((lot_id, length))
                    
            except Exception as e:
                f.write(f"Error processing ID {lot_id}: {e}\n")
    
    print(f"\nDone. Found {len(long_posts)} posts exceeding 300 characters.")
    print(f"Results written to {output_file}")

if __name__ == '__main__':
    main()
