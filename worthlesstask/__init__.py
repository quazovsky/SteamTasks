"""worthlesstask: Discord Rich Presence driver.

Sets an authentic "Playing <game>" activity on the local Discord client over the
Discord IPC socket, keeps it alive, and reconnects on drops.
"""

#: Single source of truth for the reported version. The health endpoint and the
#: Server header both come from here; keep installer\worthlesstask.iss in step with it.
__version__ = "3.1.0"
__all__ = ["__version__"]
