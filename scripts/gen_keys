"""Generate an RSA keypair for SMART Backend Services. Writes private_key.pem (SECRET) and jwks.json (public)."""
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KID = "plugin-key-1"
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
with open("private_key.pem", "wb") as f:
    f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()))
jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
jwk.update({"kid": KID, "alg": "RS384", "use": "sig", "key_ops": ["verify"]})
with open("jwks.json", "w") as f:
    json.dump({"keys": [jwk]}, f, indent=2)
print("Wrote private_key.pem (keep secret, never commit) and jwks.json (register with the FHIR server)")
