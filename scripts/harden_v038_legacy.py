from pathlib import Path

root = Path(__file__).resolve().parents[1]
worker = root / "cloudflare/src/index.js"
text = worker.read_text()

old = '''  for (const record of chunk.records) {
    const fingerprint = String(
      record.sourceRowFingerprint ||
      record.fingerprint ||
      fallbackFingerprint(record)
    );

    const result = await env.DB.prepare(`
'''
new = '''  for (const record of chunk.records) {
    const recordProvider = String(record.provider || chunk.provider || "");
    const recordYear = nullableInt(record.year);
    const rawFingerprint = String(
      record.sourceRowFingerprint ||
      record.fingerprint ||
      fallbackFingerprint(record)
    );
    const fingerprint = scopeProviderFingerprint(recordProvider, recordYear, rawFingerprint);

    const result = await env.DB.prepare(`
'''
if old not in text:
    raise SystemExit("processChunk fingerprint block not found")
text = text.replace(old, new, 1)

old_bind = '''      String(record.provider || chunk.provider || ""),
      nullableString(record.recordType),
      nullableInt(record.year),
'''
new_bind = '''      recordProvider,
      nullableString(record.recordType),
      recordYear,
'''
if old_bind not in text:
    raise SystemExit("record provider/year bind block not found")
text = text.replace(old_bind, new_bind, 1)

marker = "function fallbackFingerprint(record) {\n"
helper = '''function scopeProviderFingerprint(provider, year, fingerprint) {
  const value = String(fingerprint || "");
  if (provider !== "adiga" || value.startsWith("yr:")) return value;
  return `yr:${year == null ? "na" : year}:${value}`;
}

'''
if marker not in text:
    raise SystemExit("fallbackFingerprint marker not found")
text = text.replace(marker, helper + marker, 1)
worker.write_text(text)

migration = root / "cloudflare/migrations/0003_repair_legacy_adiga_fingerprints.sql"
migration.write_text('''-- v0.3.8 compatibility hardening for legacy Android clients.
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
''')

print("Legacy Adiga fingerprint compatibility hardening applied")
