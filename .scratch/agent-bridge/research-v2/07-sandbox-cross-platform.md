# 07 - Sandboxing foreign packs on the requester machine (cross-platform)

Date: 2026-10-07. Round 2. Scope: runtime choices for Pull mode (foreign pack runs next to the requester's data) and Hosted mode (pack runs on another machine). Primary sources only; claims not seen in a primary source this session are marked UNVERIFIED.

## Summary

- No single sandbox is both strong and zero-install on all three OSes. The honest common denominator is: **a Linux guest kernel inside a hypervisor-backed VM, with an OCI container inside it** (WSL2 on Windows, a VM on macOS, native on Linux). A microVM tier (libkrun/Firecracker/Cloud Hypervisor/Kata) is the hardened upgrade.
- Windows 11 Home (the owner's machine) rules out Windows Sandbox and the Hyper-V role. WSL2 is the realistic Windows substrate. Docker Desktop officially lists only Enterprise/Pro/Education for Windows 11, and says Home allows Linux containers only; Docker Engine or Podman inside a dedicated WSL2 distro is the practical route.
- Network-off is easy and strong with `--network none` (container sees only loopback). The sidecar link should be a **unix socket in a bind-mounted directory** (no TCP at all), or vsock in microVM tiers.
- Read-only data is best done by **staging a snapshot copy** of the granted folder into the VM's own filesystem and bind-mounting that read-only, not by mounting the host drive (avoids DrvFs/9p exposure, symlink escapes, TOCTOU).
- Recommendation: a `SandboxDriver` interface with a conformance suite of attack fixtures. **Primary driver: rootless/hardened OCI container in a Linux VM** (Docker Engine or Podman; add gVisor `runsc` where available). **Hardened driver: microVM** (microsandbox as the one cross-platform candidate, beta; Firecracker/Kata/E2B-embed on Linux hosts for Hosted mode). Show the driver tier on every listing/run.

## Key facts with sources

### Platform constraints
- Windows Sandbox: hypervisor-based disposable VM, networking ON by default (disable via .wsb), can map a folder read-only, one instance at a time, "currently not supported on Windows Home edition". https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/
- Hyper-V: "The Hyper-V role can't be installed on Windows 10 Home or Windows 11 Home." https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/get-started/install-hyper-v
- Docker Desktop on Windows 11 lists Enterprise, Pro or Education 23H2+; "Windows Home or Education editions only allow you to run Linux containers"; WSL 2 backend needs WSL >= 2.1.5, 8 GB RAM, virtualization in BIOS; subscription needed for orgs over 250 employees or $10M revenue. https://docs.docker.com/desktop/setup/install/windows-install/
- WSL2: Linux kernel in a lightweight utility VM; distros share the same network namespace, devices, CPU/kernel/memory, `/init`; separate PID/mount/user/cgroup namespaces only. So distros are NOT strong mutual isolation. https://learn.microsoft.com/en-us/windows/wsl/about
- WSL config useful for hardening: `[automount] enabled=false` (do not mount `C:\` under /mnt), `[interop] enabled=false, appendWindowsPath=false`, `[boot] systemd=true`; `.wslconfig`: `networkingMode=none` disconnects the WSL network, `nestedVirtualization` default true on Windows 11, `memory`/`processors` caps, `isolateDistroCgroup` default true, `firewall` default true. https://learn.microsoft.com/en-us/windows/wsl/wsl-config
- Podman on Windows/macOS needs a VM: Windows provider WSL (default) or Hyper-V; macOS libkrun (default) or applehv. https://docs.podman.io/en/latest/markdown/podman-machine.1.html
- Apple `container`: one lightweight VM per container, Apache-2.0, Apple silicon only, macOS 26 required (macOS 15 has network limitations), uses vmnet; mount options (read-only) not confirmed from the docs I read. https://github.com/apple/container and https://github.com/apple/container/blob/main/docs/technical-overview.md

### Container controls (Docker)
- `--network none`: "only the loopback device is created". https://docs.docker.com/engine/network/drivers/none/
- `--internal` network: "no default route is configured and firewall rules are set up to drop all traffic to or from other networks" (peers on the same network can still talk). https://docs.docker.com/reference/cli/docker/network/create/
- Read-only bind: `--mount type=bind,source=...,target=...,readonly`; submounts are best-effort read-only, recursive read-only needs Linux kernel 5.12+, `bind-recursive=readonly` errors on older kernels. https://docs.docker.com/engine/storage/bind-mounts/
- `--read-only`, `--cap-drop`, `--security-opt no-new-privileges`, `--pids-limit`, `--tmpfs`, `--user`, `--runtime` exist. https://docs.docker.com/reference/cli/docker/container/run/
- Docker states daemon needs root unless rootless mode; host-directory sharing is not limited by container access rights; privileged socket exposure is dangerous. https://docs.docker.com/engine/security/ . srt README likewise warns that allowing `/var/run/docker.sock` is host access.

### Anthropic sandbox-runtime (srt), Apache-2.0
- macOS Seatbelt via `sandbox-exec`; Linux bubblewrap + seccomp (x64/arm64) + socat + ripgrep; Windows alpha (dedicated `srt-sandbox` user, NTFS ACLs, WFP egress filters allowing only loopback proxy ports 60080-60089, one-time UAC-elevated install). https://github.com/anthropic-experimental/sandbox-runtime
- Network is allow-only (blocked by default) via HTTP and SOCKS5 proxies; on Linux the network namespace is removed and traffic goes over unix-socket proxies bound into the sandbox. Domain allowlist only, no traffic inspection; domain fronting possible.
- Filesystem: **reads allowed everywhere by default** (deny-then-allow with `denyRead`/`allowRead`), writes denied by default (`allowWrite`, `denyWrite`). A hostile pack needs a deny-all-read posture configured explicitly.
- It is a process sandbox sharing the host kernel (no VM). Windows lacks per-exec allowRead/allowWrite overrides and has CRL/OCSP schannel quirks.

### microVM and VM-backed
- microsandbox (Apache-2.0, **beta**: "Expect breaking changes, missing features, and rough edges"): libkrun microVMs; macOS requires Apple Silicon, Linux requires KVM, Windows requires WHP; "under 100 ms" boot on M1; allow-list network policy; secrets bound to hosts so keys never enter the VM; SDKs for TS, Rust, Python, Go, Ruby; one-line installers per OS. Read-only volume syntax not confirmed. https://github.com/zerocore-ai/microsandbox
- Firecracker: Linux x86_64/aarch64, needs `/dev/kvm`; AWS guide recommends `.metal` instances for KVM; **guest-initiated vsock connections map to host unix sockets `./v.sock_<port>`** (ideal for a sidecar channel). https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md , https://github.com/firecracker-microvm/firecracker/blob/main/docs/vsock.md . Round 1: "all vCPU threads are considered to be running malicious code", jailer + seccomp (research/05).
- Cloud Hypervisor: Rust VMM on KVM or MSHV, virtio net/block/fs, Linux and Windows guests, host Linux 5.13+; supports virtio-fs. https://github.com/cloud-hypervisor/cloud-hypervisor
- Kata Containers: containers each in a lightweight VM, Linux only, needs hardware virtualization, Apache-2.0, `kata-runtime check`. https://github.com/kata-containers/kata-containers
- E2B infra: one Firecracker microVM per sandbox with per-sandbox nftables egress firewall; "E2B Embed" runs the stack on a single Linux KVM host via Docker Compose; Apache-2.0. https://github.com/e2b-dev/infra
- Nebius Sandboxes (Beta, access by request): cloud API, "VM-level isolation", OCI image import, Git-like branching, SDK/CLI/MCP, 50 simultaneous operations, 180-day checkpoint retention; the overview does not document network controls or mounts. https://docs.tokenfactory.nebius.com/sandboxes/overview.md . It is a remote service, so it can only serve Hosted mode (data would leave the requester).

### gVisor
- Sentry reimplements the syscall API, no syscall passed straight to the host, minimal host surface; does not protect against hardware side channels. https://gvisor.dev/docs/architecture_guide/security/
- Linux x86_64/ARM64, Linux 5.6+; `runsc install` registers a Docker runtime (`--runtime=runsc`); no Windows/macOS install path documented. https://gvisor.dev/docs/user_guide/install/
- Platforms: systrap default (recommended incl. cloud VMs), KVM for bare metal ("nested virtualization will have poor performance and is historically a cause of security issues"). https://gvisor.dev/docs/user_guide/platforms/
- Gofer file proxy, directfs default, `--overlay2` writable tmpfs layer over mounts. https://gvisor.dev/docs/user_guide/filesystem/

### WASM and kernel primitives
- Wasmtime: no direct syscalls, bounds-checked linear memory, guard regions, memory zeroing; WASI is capability-based (only pre-authorized files); Spectre mitigation "ongoing research". https://docs.wasmtime.dev/security.html
- WASI sockets is Phase 3; modules cannot open sockets without a network capability handle and implementations should deny by default. https://github.com/WebAssembly/WASI/blob/main/proposals/sockets/README.md
- Extism: host functions let plugins call back into the host (the host decides what is exposed). Its allowed-hosts / fs / timeout config was not confirmed this session: UNVERIFIED. https://extism.org/docs/concepts/host-functions
- Landlock: unprivileged self-sandboxing; filesystem rights (v1+), TCP bind/connect (ABI v4), abstract unix socket and signal scoping (ABI v6); UDP only in a later ABI (the page I read listed v10, treat as UNVERIFIED); needs `no_new_privs`; availability depends on the guest kernel (WSL2 default kernel status UNVERIFIED). https://docs.kernel.org/userspace-api/landlock.html

## Comparison

Isolation scale: P = process/syscall filter on host kernel; C = container (namespaces) on shared kernel; U = userspace kernel; V = hardware VM. "Install" is for a non-technical end user.

| Option | Isolation | Network-off | FS scoping (ro user folder) | Startup | End-user install | License | OSes |
|---|---|---|---|---|---|---|---|
| Docker Engine/Podman rootless (in Linux VM) | C (+V if inside WSL2/VM) | `--network none` or `--internal`, strong | `--mount ...,readonly`, `--read-only`; best with staged copy | not sourced (UNVERIFIED); ~1 s typical | Medium. Win Home: WSL2 + Engine inside distro; macOS: Docker Desktop/Podman machine; Linux: package | Engine Apache-2.0 (UNVERIFIED here); Docker Desktop subscription rules cited; Podman UNVERIFIED here | all (VM on Win/mac) |
| Docker + gVisor `runsc` | U on top of C | same as Docker | same; gofer mediates | not sourced; extra syscall overhead | Medium-high, Linux only (also inside WSL2) | Apache-2.0 (UNVERIFIED here) | Linux, WSL2 |
| WSL2 alone | V boundary vs Windows, but distros share one VM/kernel/netns | `networkingMode=none` is global to all distros | DrvFs mounts Windows drives by default; disable automount | VM cold start; `vmIdleTimeout` 60 s | Low-medium (`wsl --install`) | WSL open source (MIT, UNVERIFIED here) | Windows |
| Windows Sandbox | V (own kernel) | .wsb networking disabled | .wsb mapped folder read-only | "a few seconds" | None, but **not on Home** | Windows feature | Windows Pro+ only |
| Hyper-V role | V | vSwitch config | VM disk / SMB | VM boot | Not available on Home | Windows | Pro+ only |
| microsandbox (libkrun) | V (microVM) | allow-list; deny-all expected, verify | volume mounts, ro unverified | <100 ms (vendor, M1) | Low: one installer; needs KVM / WHP / Apple Silicon; WHP on Home UNVERIFIED | Apache-2.0, beta | mac (ARM), Linux, Windows |
| E2B self-hosted | V (Firecracker) + nftables egress | per-sandbox firewall | via image/volumes | not sourced | High (Linux KVM host, compose) | Apache-2.0 | Linux KVM |
| Anthropic srt | P (bwrap/Seatbelt/WFP) | proxy allow-only; no netns on Linux | allowRead/denyRead; read default-allow | process start | Low (npx; Windows needs UAC + alpha) | Apache-2.0 | mac, Linux, Windows alpha |
| Apple container | V per container | `--network` (macOS 26) | mounts, ro unverified | not sourced | Medium, Apple silicon + macOS 26 | Apache-2.0 | macOS 26 |
| Firecracker | V | no NIC unless configured; vsock to host UDS | block devices / virtio, no 9p share by default | not sourced here (UNVERIFIED) | High: KVM, kernel, rootfs | Apache-2.0 (UNVERIFIED here) | Linux KVM (WSL2 nested only if enabled, UNVERIFIED) |
| Cloud Hypervisor | V | virtio-net optional | virtio-fs | not sourced | High | Apache-2.0/BSD (UNVERIFIED) | Linux KVM / MSHV |
| Kata | V per pod | via runtime config | via shared fs | not sourced | High, Linux only | Apache-2.0 | Linux |
| Wasmtime/WASI | sandbox by construction | no sockets unless granted | preopened dirs (ro configurable) | microseconds (UNVERIFIED) | Library embed | Apache-2.0 w/ LLVM exception (UNVERIFIED here) | all |
| Extism | WASM + host functions | host-function controlled | UNVERIFIED | fast | Library embed | BSD-3 (UNVERIFIED) | all |
| Landlock/seccomp | P | TCP connect rules; no unix-socket scoping before ABI 6 | path rules | none | Kernel feature, in-guest | kernel GPL | Linux |
| Nebius Sandboxes (Beta) | V (vendor claim) | not documented | not documented | not sourced | None (cloud, request access) | service | cloud only: Hosted |

## Fit for agent-bridge

Pull mode threat: the pack is hostile code plus a hostile prompt, running beside real data. It must not see the network, the host FS beyond the granted snapshot, host credentials, the docker socket, or other tasks. Its only legal outlet is the sidecar, which holds the Nebius key and brokers tools.

What leaks in Pull mode, honestly: (1) network (cut); (2) the model path, since the pack chooses prompts that go to Nebius via the sidecar (trusted provider with ZDR, not an attacker-controlled sink); (3) anything the requester later publishes (logs, eval reports, ratings, telemetry) - route through an egress review; (4) the result itself, which stays local. Pack author never receives data unless one of these paths carries it. Trade-off to state: Pull exposes the owner's harness IP to the requester (prompts/tools are on the requester's disk); only license plus obfuscation protects it.

Active-defense hooks these runtimes can supply: `docker events`/audit for any connect attempt outside the socket; sidecar sees every model/tool call (canary strings in staged data appearing in outbound args is a kill signal); kill = `docker kill` or destroy VM; quarantine = `docker pause`/keep the rootfs diff and logs, mark pack hash as revoked locally and in the registry; revoke = sidecar closes the socket and invalidates the per-task key. microVM tiers give a cleaner kill (destroy VM) and per-VM egress control.

### Concrete config: primary tier (Linux guest; Docker/Podman)

Host-side broker, per task:
1. Snapshot-copy the granted folder into the VM filesystem: `/var/lib/bridge/stage/$TASK/in` (resolve symlinks, refuse files outside the grant, hash a manifest). On Windows do this from the Windows side into the WSL distro filesystem, not via `/mnt/c`.
2. Create `/var/lib/bridge/run/$TASK/sidecar.sock` (sidecar listens; per-task token).
3. Run the pack:

```
docker run --rm --name pack-$TASK \
  --network none \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2 --user 65532:65532 \
  --mount type=bind,source=/var/lib/bridge/stage/$TASK/in,target=/in,readonly,bind-recursive=readonly \
  --mount type=bind,source=/var/lib/bridge/run/$TASK,target=/run/bridge \
  [--runtime runsc]  \
  pack-registry/pack@sha256:<pinned digest>
```
Pack talks only to `/run/bridge/sidecar.sock` (OpenAI-compatible base URL via a unix-socket adapter, tool calls, result return). No `/out` mount: the result returns over the socket. Rootless daemon or Podman rootless preferred; never mount the docker socket. Optionally add a seccomp profile denying `socket(AF_INET/AF_INET6)` as defense in depth. Whether a connect() to a socket on a read-only bind mount works must be tested in the spike (UNVERIFIED; if not, mount the socket directory read-write with only the socket in it).

Windows 11 Home hardening for the WSL2 distro (dedicated distro `bridge-sandbox`, not the user's dev distro):
```
# /etc/wsl.conf
[automount]
enabled=false
mountFsTab=false
[interop]
enabled=false
appendWindowsPath=false
[boot]
systemd=true
```
```
# %UserProfile%\.wslconfig
[wsl2]
memory=6GB
processors=4
networkingMode=none     # only if the sidecar/model proxy runs on the Windows host and reaches the VM another way; otherwise keep NAT and enforce --network none per container
```
Caveat: even with automount off, root inside the WSL VM may be able to mount DrvFs manually (UNVERIFIED); that is why the container must never be root-in-VM, and why the microVM tier matters.

macOS: Docker Desktop or Podman machine (libkrun/applehv VM) with the same `docker run` flags, staging into the VM via `podman machine`/virtiofs share of a staging dir only. Alternative on macOS 26 / Apple silicon: `container` (VM per container).

Linux: same flags, rootless Podman or Docker rootless, plus `runsc` where installable.

### Concrete config: lightweight process tier (srt) for trusted-ish or Linux/macOS fast path
```json
{
  "network": { "allowedDomains": [], "deniedDomains": [] },
  "filesystem": {
    "denyRead": ["/"],
    "allowRead": ["/var/lib/bridge/stage/TASK/in", "/usr", "/lib", "/opt/pack"],
    "allowWrite": ["/tmp/pack-TASK"],
    "denyWrite": []
  }
}
```
(`denyRead: ["/"]` semantics and the path for reaching the sidecar through srt's proxy or an allowed unix socket are UNVERIFIED; macOS has `allowUnixSockets`, Linux uses a seccomp unix-socket filter that `allowAllUnixSockets` disables.) Do not use srt as the only barrier for foreign packs: host kernel is shared and Windows is alpha.

### Concrete config: hardened tier (microVM)
- Cross-platform candidate: microsandbox (libkrun) with network policy deny-all and one host-side channel to the sidecar; staged folder attached read-only (verify the SDK exposes read-only volumes; UNVERIFIED).
- Linux/WSL2/EC2 (also Hosted mode): Firecracker (or Kata with Cloud Hypervisor/Firecracker) with no NIC, a read-only ext4 data image built from the staged snapshot, and vsock to the sidecar through `v.sock_<port>` on the host. Pack rootfs is also a read-only image; scratch is a size-capped tmpfs. E2B Embed is the ready-made orchestrator if a full stack is wanted.
- Destroying the VM is the kill primitive; the data image is discarded.

### Hosted mode mapping
Owner host should be Linux with KVM: Firecracker/Kata/E2B-embed or gVisor+Docker; on an owner's Windows Home machine only WSL2 + container (and nested-virt microVM if enabled). Nebius Sandboxes is a cloud Hosted option with vendor-claimed VM isolation and is a natural Nebius-track fit, but its network/mount controls are undocumented in the overview, so listing it as a driver requires a spike. Hosted mode never protects the requester's data from the host owner (owner is root); keep that label.

### WASM role
Use Wasmtime/WASI only for third-party deterministic tools (parsers, transforms, scorers) with a preopened read-only dir and no socket capability. It cannot host a full Python/Node agent harness cheaply, so it complements, not replaces, the VM/container tier.

## Recommendation

1. Define `SandboxDriver` (stage, start, kill, quarantine, events) and a **conformance suite of attack fixtures** (read `~/.ssh`, connect out, DNS lookup, docker.sock probe, fork bomb, symlink escape, write to `/in`, steal sidecar token, mount DrvFs) that every driver must pass; publish the tier on each listing.
2. **Primary driver**: hardened OCI container in a Linux VM (WSL2 dedicated distro on Windows Home, Docker/Podman VM on macOS, native rootless on Linux), flags as above, staged read-only snapshot, unix-socket sidecar, `runsc` when present. Reason: the only option that works today on Win11 Home, macOS and Linux with documented flags.
3. **Hardened driver**: microVM (microsandbox as the single cross-platform candidate once spiked; Firecracker/Kata/E2B Embed for Linux and Hosted). Make it the default for packs from unverified publishers and for any non-"verified" tier.
4. Lightweight srt tier only for first-party/verified packs on Linux/macOS; WASM for tools.
5. Day-1 spikes (binary): (a) Docker Engine in dedicated WSL2 distro on this Home machine with the run flags and the attack suite; (b) connect to a unix socket on a read-only bind mount; (c) microsandbox on this Windows machine (WHP on Home) and read-only volume; (d) nested virtualization in WSL2 for Firecracker; (e) request Nebius Sandboxes access.

## Risks

- Shared-kernel container escape (Docker states isolation may be incomplete); mitigated by gVisor/microVM, not eliminated.
- WSL2 distros share one VM, kernel and netns; DrvFs/interop exposure if not disabled; root in VM may remount Windows drives (UNVERIFIED).
- microsandbox is beta; Windows needs WHP, Home support UNVERIFIED; Firecracker needs KVM (WSL2 nested virt UNVERIFIED); gVisor has no Windows/macOS install.
- Docker Desktop licensing and Home-edition support are a distribution risk; Engine-in-WSL2 is unofficial for Home.
- Covert channels via model prompts, tool args, result text, and anything the requester later uploads; hardware side channels not covered by gVisor or WASM.
- Audit/kill signals are self-hosted on the requester machine; that is fine for Pull (the requester is the victim and the enforcer) but not attestable to others.
- Pull exposes the owner's harness IP to the requester.
- srt default-allow read posture is dangerous if misconfigured; Windows alpha.

## Open questions

- Does the WSL2 default kernel enable Landlock, user namespaces and recursive ro bind (kernel 5.12+)? Check `uname -r` and Landlock ABI in the spike.
- Can microsandbox mount a host-staged folder read-only and expose a single host channel (vsock/UDS) on all three OSes?
- Is WHP/Virtual Machine Platform enabled on this Home machine, and does it coexist with WSL2?
- Best sidecar transport into each tier: unix socket (container), vsock (microVM); unify behind one HTTP-over-UDS adapter for the OpenAI-compatible client?
- Startup times for every tier on the owner's hardware (none sourced from vendors except microsandbox's <100 ms M1 claim).
- Which tier counts as "verified publisher" default, and does Nebius Sandboxes expose enough network/mount control to be a Hosted driver?
