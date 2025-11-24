Desired Post Output
===

3355 N 98TH ST, 53222

Zoning: SF-6

Land Value: $123,123

Improvement Value: $123,123

Neighborhood: Over-the-Rhine

Acreage: 0.12

[Google Street View Image]

PART 1: Data Sources
===

I used a postgres database for initial data processing. 
I eventually convert the output to a sqlite databse that I can easily embed in this gitrepo. 


1. "Hamilton County Parcels - Open Data" from the CAGIS Open Data Portal. `parcels` in the postgres database. https://data-cagisportal.opendata.arcgis.com/datasets/19b43147c5f14160bbf2a04017d7f5a8_46/about
  - Address
  - Zip Code
  - Land Value
  - Improvement Value
  - Acreage
  - Auditor Parcel ID

```
ogr2ogr -f "PostgreSQL" \
  PG:"dbname=cincinnati_lot user=$USER" \
  HamiltonCountyParcels_open_data.geojson \
  -nln parcels \
  -overwrite \
  -lco GEOMETRY_NAME=geom \
  -nlt PROMOTE_TO_MULTI \
  -progress
```


2. "Cincinnati Zoning - Open Data" from the CAGIS Open Data Portal. `zoning` in the postgres database. https://data-cagisportal.opendata.arcgis.com/datasets/858e1196b3aa4ad1b5589d7c32091b79_19/about  
  - Cincinnati Boundary
  - Zoning
  - Neighborhood

```
ogr2ogr -f "PostgreSQL" \
  PG:"dbname=cincinnati_lot user=$USER" \
  CincinnatiZoning_open_data.geojson \
  -nln zoning \
  -overwrite \
  -lco GEOMETRY_NAME=geom \
  -nlt PROMOTE_TO_MULTI \
  -progress
```

3. Zipcodes geojson. `zip_codes` in the postgres database. https://github.com/OpenDataDE/State-zip-code-GeoJSON/blob/master/oh_ohio_zip_codes_geo.min.json 

```
ogr2ogr -f "PostgreSQL" \
  PG:"dbname=cincinnati_lot user=$USER" \
  oh_ohio_zip_codes_geo.min.json \
  -nln zip_codes \
  -overwrite \
  -lco GEOMETRY_NAME=geom \
  -nlt PROMOTE_TO_MULTI \
  -progress
```

PART 2: Refined Table
===

`psql -d cincinnati_lot -U $USER`

A CTAS that does the following: 
* Join "Hamilton County Parcels" and "Cincinnati Zoning" together 
* Join the resulting table with "Zipcodes" to get the zip code
* The remaining rows are all parcels within the Cincinnati boundary
* The final table should have the following columns:
  - Address
  - Zip Code
  - Land Value
  - Improvement Value
  - Total Market Value
  - Acreage
  - Auditor Parcel ID
  - Zoning
  - Neighborhood

```sql
CREATE TABLE cincinnati_lots AS
SELECT DISTINCT ON (p.audpclid)
    TRIM(CONCAT(p.addrno, ' ', p.addrst, ' ', p.addrsf)) AS address,
    zips.zcta5ce10 AS zipcode, 
    p.mktlnd AS land_value,
    p.mktimp AS improvement_value,
    p.mkt_total_val AS total_market_value,
    p.acredeed AS acreage,
    ST_Area(p.geom::geography) * 0.000247105 AS calculated_acreage,
    p.audpclid AS auditor_parcel_id,
    z.zoning AS zoning,
    z.dis_name AS neighborhood,
    p.geom
FROM parcels p
JOIN zoning z ON ST_Intersects(ST_Centroid(p.geom), z.geom)
LEFT JOIN zip_codes zips ON ST_Intersects(ST_Centroid(p.geom), zips.geom)
WHERE p.addrno IS NOT NULL
ORDER BY p.audpclid, ST_Area(ST_Intersection(ST_MakeValid(p.geom), ST_MakeValid(z.geom))) DESC;
```

PART 3: Eliminate Nulls/ Empties 
=== 

* Exclude the geom column, as it is not needed for posting
* Exclude rows where neighborhood is null/empty
* Exclude rows where land_value == property_value == 0

```sql
CREATE TABLE cincinnati_lots_refined AS
SELECT
    address,
    zipcode, 
    land_value,
    improvement_value,
    total_market_value,
    acreage,
    calculated_acreage,
    auditor_parcel_id,
    zoning,
    neighborhood
FROM cincinnati_lots
WHERE neighborhood IS NOT NULL
AND neighborhood != ''
AND neighborhood != ' '
AND ( not (land_value = 0 AND improvement_value = 0));
```

PART 4: Duplicate Handling 
===

I've noticed that there are some duplicate addresses (not including the unit/suite number) in the data. But these correspond to to different parcels, such as Condos. 

Further refine the data by aggregating rows with the same address:
* If the address, zoning, and neighborhood is the same:
* Sum the land_value, improvement_value, and total_market_value
* Take the max of the acreage
* Put the auditor_parcel_id into an array

```sql
CREATE TABLE cincinnati_lots_aggregated AS
SELECT
    address,
    zipcode,
    zoning,
    neighborhood,
    SUM(land_value) AS land_value,
    SUM(improvement_value) AS improvement_value,
    SUM(total_market_value) AS total_market_value,
    MAX(acreage) AS acreage,
    MAX(calculated_acreage) AS calculated_acreage,
    ARRAY_AGG(auditor_parcel_id) AS auditor_parcel_ids
FROM cincinnati_lots_refined
GROUP BY address, zipcode, zoning, neighborhood;
```

PART 5: Extraction to SQLite
===

```
ogr2ogr -f "SQLite" \
  cincinnati.db \
  PG:"dbname=cincinnati_lot user=$USER" \
  -sql "SELECT address, zipcode, zoning, neighborhood, land_value, improvement_value, total_market_value, acreage, calculated_acreage, array_to_string(auditor_parcel_ids, ',') AS auditor_parcel_ids, FALSE::boolean AS is_posted, NULL::text AS post_url, NULL::date AS post_date FROM cincinnati_lots_aggregated" \
  -nln cincinnati_lots \
  -dsco SPATIALITE=NO
```