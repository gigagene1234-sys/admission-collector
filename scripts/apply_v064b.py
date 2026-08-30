from pathlib import Path
import runpy
import xml.etree.ElementTree as ET

# Apply the full v0.6.4 patch from the persisted v0.6.3 source first.
runpy.run_path('scripts/apply_v064.py', run_name='__main__')

manifest = Path('app/src/main/AndroidManifest.xml')
text = manifest.read_text()
# Android XML cannot contain a raw ampersand in an attribute value.
text = text.replace(
    'Admission Collector v0.6.4 Crash Guard & Stall Recovery',
    'Admission Collector v0.6.4 Crash Guard and Stall Recovery'
)
manifest.write_text(text)

# Fail before Gradle if XML is malformed.
ET.parse(manifest)

if 'Admission Collector v0.6.4 Crash Guard and Stall Recovery' not in text:
    raise SystemExit('corrected v0.6.4 manifest label missing')

print('v0.6.4 manifest correction applied and XML parsed successfully')
