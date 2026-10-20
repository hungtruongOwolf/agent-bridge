"""Probe code run INSIDE the cell. Prints one JSON line of facts about its own isolation."""
import json, os, socket

out = {}
out["interfaces"] = sorted(os.listdir("/sys/class/net"))
for name, target in (("tcp_ip", ("1.1.1.1", 443)), ("dns", ("example.com", 80))):
    try:
        socket.create_connection(target, timeout=3).close()
        out[name] = "CONNECTED"
    except Exception as e:
        out[name] = f"blocked:{type(e).__name__}"
try:
    open("/probe_write", "w").write("x")
    out["rootfs_write"] = "WRITABLE"
except OSError as e:
    out["rootfs_write"] = f"blocked:{e.errno}"
out["uid"] = os.getuid()
out["cap_eff"] = next(l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff"))
print(json.dumps(out))
