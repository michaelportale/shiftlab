#!/usr/bin/env bash
# Superseded by tools/make_keybag.py.
#
# The openssl route failed on a real Apple Configurator export with
# "Could not find certificate from <stdin>", because `openssl pkcs12 -clcerts`
# returns nothing when the identity certificate is not flagged as a client
# cert. Configurator exports are frequently in that shape. The Python version
# reads the p12 with the same cryptography library that later consumes the
# keybag, and recovers the cert from the additional-certificates bag.
echo "use: python tools/make_keybag.py <identity.p12> <out.pem>" >&2
exit 1
