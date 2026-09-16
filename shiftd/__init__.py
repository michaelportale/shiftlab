"""shiftd: a local daemon that hides apps on a supervised iPhone on a schedule.

Layering, top to bottom:

    cli      argument parsing, human output
    engine   decides desired state, reconciles toward it
    state    what is shifted right now, on disk, restart safe
    profiles builds the .mobileconfig
    transport the only module that talks to the phone
    config   TOML, validated hard at load

Nothing here makes network calls. The phone is reached over USB lockdown, or
over Wi-Fi lockdown using an existing pair record, both local.
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
