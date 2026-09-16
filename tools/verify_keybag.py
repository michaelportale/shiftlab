"""Verify a supervision keybag offline, before erasing anything.

Runs the exact calls pymobiledevice3's MobileConfigService.escalate() makes,
including the PKCS7 challenge signature, against a dummy challenge. Everything
here is local. The only thing it cannot prove is that the device accepts the
certificate, and that is guaranteed by construction if you prepare the device
with this same Configurator organization.

    python tools/verify_keybag.py ~/.shiftd/keybag.pem
"""
from __future__ import annotations

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
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.hazmat.primitives.serialization.pkcs7 import (
        PKCS7Options,
        PKCS7SignatureBuilder,
    )
except ImportError:
    sys.exit("cryptography not importable. Activate the venv first.")

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}pass{OFF}  {msg}")


def fail(msg: str, fix: str = "") -> None:
    print(f"  {RED}FAIL{OFF}  {msg}")
    if fix:
        print(f"        {DIM}{fix}{OFF}")
    sys.exit(1)


def main(path_str: str) -> int:
    path = Path(path_str).expanduser()
    print(f"\nverifying {path}\n")

    if not path.exists():
        fail(f"{path} does not exist")
    data = path.read_bytes()

    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        print(f"  {RED}warn{OFF}  mode is {oct(mode)}, should be 0600. chmod 600 it.")
    else:
        ok("file permissions are 0600")

    # 1. private key, unencrypted, exactly as escalate() loads it
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except TypeError:
        fail(
            "private key is encrypted",
            "the keybag must be unencrypted. Re-run make_keybag.sh; openssl pkey "
            "without -aes256 strips the passphrase.",
        )
    except ValueError as e:
        fail(f"no loadable PEM private key in the file: {e}",
             "the file needs a BEGIN PRIVATE KEY or BEGIN RSA PRIVATE KEY block.")
    ok(f"private key loads unencrypted ({type(key).__name__})")

    # 2. key type gate, escalate() raises ProfileError on anything else
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        fail(
            f"unsupported key type {type(key).__name__}",
            "pymobiledevice3 accepts RSA and EC only.",
        )
    bits = getattr(key, "key_size", None)
    ok(f"key type accepted by escalate() ({type(key).__name__}, {bits} bits)")

    # 3. certificate from the same bytes
    try:
        cert = x509.load_pem_x509_certificate(data)
    except ValueError as e:
        fail(f"no loadable PEM certificate in the file: {e}",
             "key and cert must both live in this one file.")
    subject = cert.subject.rfc4514_string()
    ok(f"certificate loads: {subject}")

    # 4. cert public key must match the private key, or PKCS7 signing produces
    #    a signature the device will reject
    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        fail(
            "certificate does not match the private key",
            "the p12 held more than one identity. Re-export with only the "
            "supervision identity selected.",
        )
    ok("certificate public key matches the private key")

    # 5. validity window
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    not_before = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    if not_before.tzinfo is None:
        not_before = not_before.replace(tzinfo=_dt.timezone.utc)
        not_after = not_after.replace(tzinfo=_dt.timezone.utc)
    if not (not_before <= now <= not_after):
        fail(f"certificate not currently valid ({not_before} to {not_after})")
    days = (not_after - now).days
    ok(f"certificate valid for another {days} days (until {not_after.date()})")

    # 6. DER encode, which is what goes in SupervisorCertificate
    der = cert.public_bytes(Encoding.DER)
    ok(f"DER encodes for SupervisorCertificate ({len(der)} bytes)")

    # 7. THE REAL TEST: the exact PKCS7 signature escalate() builds
    challenge = os.urandom(32)
    try:
        signed = (
            PKCS7SignatureBuilder()
            .set_data(challenge)
            .add_signer(cert, key, hashes.SHA256())
            .sign(Encoding.DER, [PKCS7Options.Binary])
        )
    except Exception as e:
        fail(f"PKCS7 challenge signing failed: {e}",
             "this is the operation escalate() performs. If it fails here it "
             "will fail against the device.")
    ok(f"PKCS7 challenge signature builds ({len(signed)} bytes)")

    print(f"\n{GREEN}This keybag will work with install_profile_silent.{OFF}")
    print(f"{DIM}The only untested step is the device accepting this certificate,")
    print(f"which holds by construction if you Prepare with this same organization.{OFF}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
