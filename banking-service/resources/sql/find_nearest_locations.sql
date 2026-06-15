SELECT id, type, name, address, latitude, longitude, hours, phone_number,
  ST_DISTANCE(ST_GEOGPOINT(longitude, latitude), ST_GEOGPOINT(@lng, @lat)) as distance_meters
FROM `{table_ref}`
WHERE (@type = 'ALL' OR type = @type)
ORDER BY distance_meters ASC
LIMIT 20
