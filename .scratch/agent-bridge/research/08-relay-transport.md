# 08 - Outbound-only relay and E2E encryption

Date: 2026-10-07. Sources are primary docs/repos fetched today. Anything not read from a primary source is marked UNVERIFIED.

## Summary
Recommended minimal design: a small custom relay (Node/TypeScript or Go, a few hundred lines) on AWS that only forwards opaque frames over outbound WebSocket connections, plus a NATS-style inbox model only if we want a ready-made durable queue. Identity is an Ed25519 keypair per machine (did:key as the printable form). Session security is the Noise protocol (IK/XX over 25519 + ChaChaPoly) or, simpler, libsodium/noble `crypto_box`-style per-message encryption with signed envelopes. Do not hand-roll primitives; use audited libraries. libp2p, Tailscale/Headscale, Cloudflare Tunnel and Matrix are credible but each adds setup or does not match the "relay sees ciphertext only, per-task marketplace" shape as cleanly.

## Key facts (with sources)
- libp2p circuit relay v2: lets unreachable peers receive connections via public relays, with duration/data limits and reservations (signed voucher). The spec says nothing about encryption; peers upgrade the relayed connection with a security protocol, as with TCP. https://github.com/libp2p/specs/blob/master/relay/circuit-v2.md
- js-libp2p: WebSocket, WebRTC, TCP, WebTransport; circuit relay; Noise handshake; hole punching; Apache-2.0/MIT; used in production in Ethereum, IPFS. https://github.com/libp2p/js-libp2p
- NATS: Apache-2.0, CNCF project, 40+ client languages. https://github.com/nats-io/nats-server
- NATS JetStream: persistence, at-least-once delivery, work-queue style consumers with ack/redelivery, replay; publishers and subscribers need not be online simultaneously. https://docs.nats.io/nats-concepts/jetstream
- NATS WebSocket: enabled by setting `websocket { port }`; TLS required by default; browser origin controls. https://docs.nats.io/running-a-nats-service/configuration/websocket/websocket_conf
- NATS NKey auth: client holds an Ed25519 seed and signs a server nonce; no secret crosses the wire. (Doc page text says "public-key cryptography"; Ed25519 specifically is UNVERIFIED from fetched text.) https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro/nkey_auth
- Noise: XX (mutual auth, static keys exchanged), IK (initiator knows responder static key), KK; all resist key-compromise impersonation; recommended 25519 DH, ChaChaPoly or AESGCM, SHA-256/BLAKE2s. https://noiseprotocol.org/noise.html
- libsodium `crypto_box`: X25519 + XSalsa20-Poly1305; nonce must not repeat per key pair; sender can decrypt/forge own messages (use sealed boxes if that matters); `crypto_secretstream` for replay protection. https://doc.libsodium.org/public-key_cryptography/authenticated_encryption
- age: X25519 file encryption, Go/Rust(rage)/TS(typage) libs, but NO sender authentication. Fit: encrypting results/artifacts at rest, not sessions. https://github.com/FiloSottile/age
- MLS (RFC 9420): async group key establishment with forward secrecy and post-compromise security, groups of 2 to thousands. Overkill for 1:1 requester/owner tasks. https://www.rfc-editor.org/rfc/rfc9420
- Cloudflare Tunnel: `cloudflared` makes outbound-only connections to Cloudflare; good for exposing a service, but Cloudflare terminates TLS (relay sees plaintext unless we add our own E2E layer). https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ (TLS termination claim: general knowledge, UNVERIFIED here)
- Headscale: self-hosted Tailscale control server, BSD-3, supports ONE tailnet only, suited to personal/small orgs; includes DERP relay config. Tailscale DERP servers cannot see the encrypted data. https://github.com/juanfont/headscale ; https://tailscale.com/kb/1118/custom-derp-servers
- did:key: DID spec defines a DID as a globally unique identifier needing no central registry. https://www.w3.org/TR/did-core/ (the did:key method page at w3c-ccg.github.io returned 404; the Ed25519 `z6Mk` format is UNVERIFIED here, check https://w3c-ccg.github.io/did-key-spec/)
- @noble/curves: ed25519 and x25519, MIT, minimal dependencies (1), audited (page lists Trail of Bits, Cure53, Kudelski; the "August 2026" date as fetched should be double-checked). https://github.com/paulmillr/noble-curves
- OpenClaw Gateway: local control plane on a WebSocket (port 18789); remote exposure via Tailscale Serve, SSH tunnel, or LAN/tailnet bind; token/password auth; nodes are peripherals of one gateway; DM channels use pairing codes (`openclaw pairing approve`). https://docs.openclaw.ai/gateway/remote ; https://github.com/openclaw/openclaw

## Fit for agent-bridge
Requirements: both sides dial OUT (owner machine behind NAT), relay sees ciphertext only, owner approval via phone, offline owners, task queueing, marketplace-style many requesters x many owners, works on two real machines, hosted on AWS.

Comparison:
| Option | Outbound-only | Relay sees plaintext? | Queue/offline | Effort | Verdict |
|---|---|---|---|---|---|
| Custom WS relay + Noise/crypto_box | yes | no (our E2E) | we add small queue | low-medium | primary |
| NATS (+JetStream) on EC2/Fargate | yes (client dials out) | broker sees payload unless we E2E it | built in | low | strong alternative for queue/presence |
| libp2p circuit relay | yes | no (Noise) | none, must add | medium-high (concepts, NAT, AWS relay tuning) | too heavy |
| Tailscale/Headscale | yes | no | none | low per demo but single tailnet, wrong for marketplace trust | dev convenience only |
| Cloudflare Tunnel | yes | edge sees traffic | none | low | for exposing the web UI, not the E2E channel |
| Matrix (Olm/Megolm) | yes | no | built in | high, heavy homeserver (details UNVERIFIED, not fetched) | skip |
| MLS | n/a | no | async | high | skip (group crypto not needed) |

Proposed design:
1. Identity: each machine/user generates Ed25519 (identity) with X25519 derived for key agreement; display as did:key. Marketplace listing is signed by the owner key. Library: @noble/curves (JS) or libsodium.
2. Relay: stateless-ish WebSocket server on AWS (ECS Fargate or one EC2 behind ALB with TLS). Clients authenticate by signing a server nonce (same idea as NATS NKey). Relay routes by public key, stores encrypted envelopes in a per-recipient queue (DynamoDB or in-memory + SQS for AWS story; UNVERIFIED which is cheapest), delivers on reconnect, applies TTL. Presence = connected socket + heartbeat; listing shows online/offline.
3. E2E: requester and owner run a Noise handshake through the relay (XX first contact; IK once the owner key is known from the listing, which is the marketplace case: requester knows owner static key, so IK fits). Then task/result frames are AEAD-encrypted. If offline queueing is needed before a live handshake, use sealed-box style (ephemeral X25519 to owner key, signed by sender) for the task request; the live session is only needed for streaming. Relay learns metadata only (who talks to whom, sizes, timing).
4. Pairing (phone approval): owner machine shows a QR containing its public key + a one-time secret + relay URL. Phone opens the web page, scans/opens it, registers its own keypair (WebCrypto/noble), and the machine signs the phone's key into an approved-devices list. Approvals are signed messages from the phone key, verified by the desktop agent. Pattern is similar to OpenClaw's pairing code approval.
5. Offline/queue: tasks carry id, expiry, and are acked; requester sees queued/delivered/approved/running/done states (feeds the observability UI). Retry is idempotent by task id.
6. AWS: relay on Fargate/EC2 with ALB (WebSocket supported by ALB: UNVERIFIED, check AWS docs), optional DynamoDB for queue and listings, CloudWatch logs. Satisfies the AWS Builder narrative.

Reuse choice: if time is tight, run `nats-server` on AWS (JetStream gives queue, redelivery, presence-ish via heartbeats; WebSocket for the phone page) and layer our own E2E envelope on top. That removes writing the queue and reconnect logic, at the cost of a less custom "relay" story. Otherwise a ~300 line WS relay is quicker to make bulletproof for a demo.

## Recommendation
- Transport: outbound WebSocket (WSS) to an AWS-hosted relay. Choose between custom relay (default) and NATS+JetStream (if we want durable queues for free). Decide after a 2-hour spike.
- Crypto: Noise IK/XX via an existing Noise library (js-libp2p's noise implementation or `noise-protocol`/`noise-handshake` packages, UNVERIFIED which is best maintained) or libsodium crypto_box + signed envelopes. No custom primitives. Use age only for encrypting stored result artifacts.
- Identity: Ed25519 / did:key, marketplace listings and tasks signed.
- Pairing: QR with pubkey + one-time secret; phone key bound to desktop key.
- Skip libp2p, Matrix, MLS, Headscale for the product; Tailscale/Cloudflare Tunnel are fine for dev access only. Do not rely on OpenClaw's gateway as the cross-user transport: it is designed as a single-owner local control plane with shared token auth, not a multi-party relay (inference from docs, UNVERIFIED for multi-user use).

## Risks
- Metadata leakage to the relay (who/when/size); document it in the threat model.
- Replay and nonce reuse: need per-session counters or Noise's built-in handling; test it.
- Key loss/rotation and revocation of phone devices need a minimal story.
- Relay is a single point of failure/DoS; rate limit by public key; hosted on one AWS instance for the demo.
- Offline queueing conflicts with forward secrecy of a live Noise session; the sealed-box request is weaker in that regard.
- Encrypted transport does not stop a malicious third-party harness from misusing data once decrypted on its machine; that is the isolation problem covered by other research topics.
- Library maturity of JS Noise packages is unverified.

## Open questions
- Is the owner OS Windows on both ends (Windows firewall/outbound proxies on hackathon networks)? WSS on 443 mitigates.
- NATS vs custom relay: does the team prefer less code or more control? Spike needed.
- Which Noise library to adopt (js-libp2p noise vs standalone)?
- DynamoDB/SQS vs in-memory queue for the AWS Builder story and cost.
- Confirm did:key encoding and NKey curve from their specs before relying on them.
- Does PayPal flow need relay-visible metadata (task id, price)? Probably yes; keep it outside the encrypted payload only if necessary.
