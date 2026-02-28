import base64, os
sd = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(sd, "verify.b64")
final = os.path.join(sd, "verify_isbi_migration.py")
# Read ourselves and extract the script from after the marker
import sys
print("Reading embedded script...")
me = open(os.path.abspath(__file__), "r").read()
marker = "#" + "SCRIPT_START"
idx = me.index(marker)
script = me[idx + len(marker) + 1:]
with open(final, "w") as f:
    f.write(script)
print(f"Written {len(script)} bytes to {final}")
