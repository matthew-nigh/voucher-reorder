"""Quiet background launches: no console window or Windows startup cursor feedback."""

import subprocess


def background_options():
    if not hasattr(subprocess, "STARTUPINFO"):
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= 0x80  # STARTF_FORCEOFFFEEDBACK (not exported by subprocess)
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startup}
