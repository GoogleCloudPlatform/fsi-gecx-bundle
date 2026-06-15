SELECT id, type, name, address, latitude, longitude, hours, phone_number,
  CAST(0.0 AS FLOAT64) as distance_meters
FROM `{table_ref}`
WHERE (@type = 'ALL' OR type = @type)
  AND (
    LOWER(address) LIKE CONCAT('%', LOWER(@search_text), '%')
    OR LOWER(name) LIKE CONCAT('%', LOWER(@search_text), '%')
  )
LIMIT 20
