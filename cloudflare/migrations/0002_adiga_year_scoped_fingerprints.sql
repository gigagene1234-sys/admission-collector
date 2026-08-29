-- v0.3.8: Adiga row fingerprints used to ignore the requested admission year.
-- Scope existing fingerprints by their stored record year so identical rows from
-- 2026 and 2027 can coexist while same-year deduplication remains intact.
UPDATE records
SET fingerprint = 'yr:' || COALESCE(CAST(year AS TEXT), 'na') || ':' || fingerprint
WHERE provider = 'adiga'
  AND fingerprint NOT LIKE 'yr:%';
