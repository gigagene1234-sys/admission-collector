-- v0.3.8 compatibility hardening for legacy Android clients.
-- Delete an unscoped row when its year-scoped equivalent already exists,
-- then scope every remaining legacy Adiga fingerprint.
DELETE FROM records
WHERE provider = 'adiga'
  AND fingerprint NOT LIKE 'yr:%'
  AND EXISTS (
    SELECT 1
    FROM records AS scoped
    WHERE scoped.fingerprint =
      'yr:' || COALESCE(CAST(records.year AS TEXT), 'na') || ':' || records.fingerprint
  );

UPDATE records
SET fingerprint =
  'yr:' || COALESCE(CAST(year AS TEXT), 'na') || ':' || fingerprint
WHERE provider = 'adiga'
  AND fingerprint NOT LIKE 'yr:%';
