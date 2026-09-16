"""Convert an Apple Configurator supervision identity (.p12) into a keybag.

A keybag is one PEM file holding an unencrypted private key concatenated with
its certificate, which is what pymobiledevice3's escalate() reads:

    serialization.load_pem_private_key(data, password=None)
    x509.load_pem_x509_certificate(data)

Uses cryptography's PKCS12 loader rather than the openssl CLI, because
`openssl pkcs12 -clcerts` silently returns nothing when the certificate is not
flagged as a client cert, which is common in Configurator exports.

    python tools/make_keybag.py ~/.shiftd/MichaelHome.p12 ~/.shiftd/keybag.pem
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import warnings

# Apple's Configurator p12 encodes an ASN.1 DEFAULT value explicitly, so
# cryptography falls back from DER to BER parsing. The parse succeeds. And the
# identity CN is 70 characters, over the X.500 ub-common-name limit of 64, which
# only warns when stringifying the subject. Neither affects escalate(), which
# sends cert DER bytes and never stringifies. Silenced so a real failure is not
# lost in noise.
warnings.filterwarnings("ignore", message=".*could not be parsed as DER.*")
warnings.filterwarnings("ignore", message=r".*Attribute's length must be.*")

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
except ImportError:
    sys.exit("cryptography not importable. Activate the venv first.")

DIM, RED, GREEN, OFF = "\033[2m", "\033[31m", "\033[32m", "\033[0m"


def main(p12_path: str, out_path: str) -> int:
    p12 = Path(p12_path).expanduser()
    out = Path(out_path).expanduser()
    if not p12.exists():
        sys.exit(f"{p12} does not exist")

    data = p12.read_bytes()
    password = getpass.getpass(f"passphrase for {p12.name}: ").encode() or None

    try:
        key, cert, extra = pkcs12.load_key_and_certificates(data, password)
    except ValueError as e:
        msg = str(e)
        if "mac verify" in msg.lower() or "invalid password" in msg.lower():
            sys.exit(f"{RED}wrong passphrase{OFF}")
        sys.exit(
            f"{RED}could not parse the p12: {e}{OFF}\n"
            "If this mentions an unsupported algorithm, the export used legacy\n"
            "RC2. Re-export from Configurator, or convert first with:\n"
            "  openssl pkcs12 -in in.p12 -nodes -legacy -out tmp.pem\n"
            "  openssl pkcs12 -export -in tmp.pem -out new.p12"
        )

    print()
    if key is None:
        sys.exit(
            f"{RED}the p12 contains no private key.{OFF}\n"
            "Re-export from Configurator with the supervision identity selected,\n"
            "or in Keychain Access expand the certificate and select BOTH the\n"
            "certificate and the key underneath before exporting."
        )
    print(f"  key   {type(key).__name__}, {getattr(key, 'key_size', '?')} bits")

    if cert is None:
        # Configurator sometimes puts the identity cert in the "additional"
        # bag rather than marking it as the primary client cert. This is the
        # exact case `openssl -clcerts` misses.
        want = key.public_key().public_numbers()
        for candidate in extra or []:
            if candidate.public_key().public_numbers() == want:
                cert = candidate
                print(f"  {DIM}cert was in the additional-certificates bag, recovered it{OFF}")
                break
    if cert is None:
        sys.exit(
            f"{RED}no certificate in the p12 matches the private key.{OFF}\n"
            f"Found {len(extra or [])} other certificate(s). Re-export the identity."
        )
    print(f"  cert  {cert.subject.rfc4514_string()}")
    if extra:
        print(f"  {DIM}({len(extra)} additional certificate(s) in the file, not used){OFF}")

    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ) + cert.public_bytes(encoding=serialization.Encoding.PEM)

    out.parent.mkdir(parents=True, exist_ok=True)
    # create 0600 from the start rather than writing then chmod
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)

    print(f"\n{GREEN}wrote {out}{OFF}")
    print(f"{DIM}now run: python tools/verify_keybag.py {out}{OFF}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
