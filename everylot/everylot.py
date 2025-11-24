#!/usr/bin/env python3
import sqlite3
import logging
from io import BytesIO
import requests
import os

NEXT_LOT_QUERY = """
    SELECT ogc_fid AS id, *
    FROM cincinnati_lots
    WHERE is_posted = 0
    AND improvement_value > 0
    ORDER BY RANDOM()
    LIMIT 1;
"""

SPECIFIC_LOT_QUERY = """
    SELECT ogc_fid AS id, *
    FROM cincinnati_lots
    WHERE ogc_fid = ?
    LIMIT 1;
"""

SVAPI = "https://maps.googleapis.com/maps/api/streetview"
GCAPI = "https://maps.googleapis.com/maps/api/geocode/json"

class EveryLot:

    def __init__(self, database, search_format=None, print_format=None, id_=None, **kwargs):
        """
        Initialize EveryLot with database connection and formatting options.
        
        Args:
            database (str): Path to SQLite database file
            search_format (str, optional): Format string for Google Street View search
            print_format (str, optional): Format string for social media posts
            id_ (str, optional): Specific ogc_fid to use
            **kwargs: Additional options including logger
        """
        self.logger = kwargs.get('logger', logging.getLogger('everylot'))

        # Set address formats - default to just address since city/state are constant
        self.search_format = search_format or os.getenv('SEARCH_FORMAT', '{address}, Cincinnati, OH')
        self.print_format = print_format or os.getenv('PRINT_FORMAT', '{address}')

        self.logger.debug('Search format: %s', self.search_format)
        self.logger.debug('Print format: %s', self.print_format)

        # Connect to database
        self.conn = sqlite3.connect(database)
        self.conn.row_factory = sqlite3.Row

        # Get the next lot
        if id_:
            # Get specific ogc_fid
            cursor = self.conn.execute(SPECIFIC_LOT_QUERY, (id_,))
        else:
            # Get a random unposted lot
            cursor = self.conn.execute(NEXT_LOT_QUERY)

        row = cursor.fetchone()
        self.lot = dict(row) if row else None

    def aim_camera(self):
        """Calculate optimal camera settings based on building height."""
        # Default values for a typical 2-story building
        fov, pitch = 65, 10
        return fov, pitch

    def get_streetview_image(self, key):
        """
        Fetch image from Google Street View API.
        
        Args:
            key (str): Google Street View API key
            
        Returns:
            BytesIO: Image data
        """
        if not key:
            raise ValueError("Google Street View API key is required")

        params = {
            "location": self.streetviewable_location(key),
            "key": key,
            "size": "640x640"
        }

        fov, _ = self.aim_camera()  # Get FOV but use configured pitch
        params.update({
            'fov': fov,
            'pitch': float(os.getenv('STREETVIEW_PITCH', -10)),
            'zoom': float(os.getenv('STREETVIEW_ZOOM', 0.8))
        })

        try:
            r = requests.get(SVAPI, params=params)
            r.raise_for_status()
            self.logger.debug('Street View URL: %s', r.url)

            sv = BytesIO()
            for chunk in r.iter_content(chunk_size=8192):
                sv.write(chunk)

            sv.seek(0)
            return sv

        except requests.exceptions.RequestException as e:
            self.logger.error('Failed to fetch Street View image: %s', str(e))
            raise

    def streetviewable_location(self, key):
        """
        Determine the best location for Street View image.
        Uses the formatted address with hardcoded city/state since this is Cincinnati-specific.
        Only falls back to lat/lon if address formatting completely fails.
        
        Args:
            key (str): Google Geocoding API key
            
        Returns:
            str: Location string for Street View API
        """
        try:
            # Get the address and ensure it's not empty/None
            address = self.lot.get('address')
            if not address:
                raise ValueError('No address available')
                
            # Format with hardcoded city/state since this is Cincinnati-specific
            location = f"{address}, Cincinnati, OH"
            self.logger.debug('Using formatted address for Street View: %s', location)
            return location
            
        except (KeyError, ValueError) as e:
            raise ValueError(f"No valid location data available: {str(e)}")

    def sanitize_address(self, address):
        """
        Convert address components into a clean, readable format.
        Example: '2023 N DAMEN AVE' -> '2023 North Damen Avenue'
        
        Args:
            address (str): Raw address string
            
        Returns:
            str: Sanitized address string
        """
        if not address:
            return address

        # Split address into components
        parts = address.strip().split(',')[0].split()  # Take first part before comma
        if not parts:
            return address

        # Direction mapping
        directions = {
            'N': 'North',
            'S': 'South',
            'E': 'East',
            'W': 'West'
        }

        # Street type mapping
        street_types = {
            'AVE': 'Avenue',
            'ST': 'Street',
            'BLVD': 'Boulevard',
            'RD': 'Road',
            'DR': 'Drive',
            'CT': 'Court',
            'PL': 'Place',
            'TER': 'Terrace',
            'LN': 'Lane',
            'WAY': 'Way',
            'CIR': 'Circle',
            'PKY': 'Parkway',
            'SQ': 'Square'
        }

        # Process each part
        result = []
        for i, part in enumerate(parts):
            part = part.strip()
            if i == 0:  # Street number
                result.append(part)
            elif part in directions:  # Direction
                result.append(directions[part])
            elif part in street_types:  # Street type
                result.append(street_types[part])
                break  # Stop processing after street type
            else:  # Street name
                result.append(part.capitalize())

        return ' '.join(result)

    # Example Usage:
    # print(get_cincinnati_zoning_description("SF-4-T")) 
    # -> "Single-family (4,000 sq ft min lot) - Transportation Corridor Overlay"
    # print(get_cincinnati_zoning_description("CC-A-MH"))
    # -> "Commercial Community - Auto-Oriented, Middle Housing Overlay"
    def get_cincinnati_zoning_description(code):
        """
        Parses a Cincinnati zoning code into a human-readable description.
        Handles base districts, form-based codes, and overlays/suffixes.
        """
        # 1. Define Base Descriptions
        base_descriptions = {
            # Single-family
            "SF-20": "Single-family (20,000 sq ft min lot)",
            "SF-10": "Single-family (10,000 sq ft min lot)",
            "SF-6":  "Single-family (6,000 sq ft min lot)",
            "SF-4":  "Single-family (4,000 sq ft min lot)",
            "SF-2":  "Single-family (2,000 sq ft min lot)",
            
            # Multi-family
            "RMX":    "Residential Mixed",
            "RM-2.0": "Residential Multi-family (2,000 sq ft land/unit)",
            "RM-1.2": "Residential Multi-family (1,200 sq ft land/unit)",
            "RM-0.7": "Residential Multi-family (700 sq ft land/unit)",
            
            # Office
            "OL": "Office Limited",
            "OG": "Office General",
            
            # Commercial
            "CN": "Commercial Neighborhood",
            "CC": "Commercial Community",
            "CG": "Commercial General",
            
            # Urban Mix & Downtown
            "UM": "Urban Mix",
            "DD": "Downtown Development",
            
            # Manufacturing
            "MA": "Manufacturing Agricultural",
            "ML": "Manufacturing Limited",
            "MG": "Manufacturing General",
            "ME": "Manufacturing Exclusive",
            
            # Riverfront
            "RF-R": "Riverfront Residential/Recreational",
            "RF-C": "Riverfront Commercial",
            "RF-M": "Riverfront Manufacturing",
            
            # Other
            "PR": "Parks and Recreation",
            "IR": "Institutional-Residential",
            "PD": "Planned Development",
            
            # Form-Based Code (Transect Zones)
            "T3E": "T3 Estate (Sub-Urban)",
            "T3N": "T3 Neighborhood (Sub-Urban)",
            "T4N.MF": "T4 Neighborhood Medium Footprint (General Urban)",
            "T4N.SF": "T4 Neighborhood Small Footprint (General Urban)",
            "T5MS": "T5 Main Street (Urban Center)",
            "T5N.LS": "T5 Neighborhood Large Setback (Urban Center)",
            "T5N.SS": "T5 Neighborhood Small Setback (Urban Center)",
            "T5F": "T5 Flex (Urban Center)",
        }

        # 2. Handle Suffixes iteratively
        # We strip suffixes from the end until we find a match in base_descriptions
        # or run out of parts.
        
        parts = code.split('-')
        suffixes = []
        base_code = code
        
        # Special handling for Form-Based Codes which have dots (e.g. T4N.MF)
        # and Riverfront (RF-M) which uses hyphen but is a base code.
        # We check if the full code is a base code first.
        if code in base_descriptions:
            return base_descriptions[code]

        # Iteratively strip known suffixes
        known_suffixes = {
            "T": "Transportation Corridor Overlay",
            "MH": "Middle Housing Overlay",
            "B": "Neighborhood Business District",
            "P": "Pedestrian-Oriented",
            "A": "Auto-Oriented",
            "M": "Mixed-Use", # Note: Only for Commercial. RF-M is handled in base.
            "O": "Open Sub-Zone", # Form-based
        }

        # Work backwards
        description_parts = []
        
        # Naive stripping of suffixes
        # This loop tries to find the longest prefix that is a base code
        for i in range(len(parts), 0, -1):
            candidate_base = "-".join(parts[:i])
            if candidate_base in base_descriptions:
                base_desc = base_descriptions[candidate_base]
                
                # Process the remaining parts as suffixes
                remaining_suffixes = parts[i:]
                suffix_descs = []
                for suf in remaining_suffixes:
                    if suf in known_suffixes:
                        # Context check for 'M' (Mixed vs Manufacturing)
                        # RF-M is already caught as a base code. 
                        # So 'M' here is likely Commercial Mixed.
                        suffix_descs.append(known_suffixes[suf])
                    else:
                        suffix_descs.append(suf) # Unknown suffix
                
                full_desc = f"{base_desc}"
                if suffix_descs:
                    full_desc += " - " + ", ".join(suffix_descs)
                return full_desc

        return f"Unknown Zoning Code: {code}"


    def compose(self):
        """
        Compose a social media post with location info.

        Returns:
            dict: Post parameters including status text and location
        """
        # Get the sanitized address
        sanitized_address = self.sanitize_address(self.lot.get('address', ''))
        
        # Create post data with sanitized address
        post_data = dict(self.lot)
        post_data['address'] = sanitized_address
        
        # Enhance zoning description
        if 'zoning' in post_data:
            old = post_data['zoning']
            post_data['zoning'] = EveryLot.get_cincinnati_zoning_description(post_data['zoning']) + " (" + old + ")"
        
        # Format the status text using sanitized address
        status = self.print_format.format(**post_data)
        
        # Build the final post data
        result = {
            "status": status,
            "lat": self.lot.get('lat', 0.0),
            "long": self.lot.get('lon', 0.0),
        }
        
        return result

    def mark_as_posted(self, platform, post_id):
        """
        Mark the current lot as posted for a specific platform.
        
        Args:
            platform (str): Platform name ('twitter' or 'bluesky')
            post_id (str): ID or URL of the post
        """
        # For Cincinnati bot, we use is_posted, post_url, and post_date
        # We assume post_id is the URL if platform is bluesky, or we just store it there.
        self.conn.execute(
            "UPDATE cincinnati_lots SET is_posted = 1, post_url = ?, post_date = date('now') WHERE ogc_fid = ?",
            (post_id, self.lot['id'])
        )
        self.conn.commit()
