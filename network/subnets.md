# Task 5: Subnetting and Network Access Control (NACL)

## 1. Subnet Allocation Plan

### Overview
- **Classless Inter-Domain Routing (CIDR) Block**: `10.20.0.0/16`
- **Total Address Space**: $2^{16} = 65,536$ addresses
- **Usable Host Formula**: $\text{Usable Hosts} = 2^{32 - \text{prefix}} - 2$ (subtracting network and broadcast addresses)
- **Allocation Strategy**: Variable Length Subnet Masking (VLSM) ordered from the largest host requirement to the smallest, placed contiguously starting at `10.20.0.0`.

---

### Step-by-Step Subnet Calculations

#### Subnet 1: `app` Subnet
- **Hosts Needed**: 1,000
- **Host Bits Required ($h$)**: $2^h - 2 \ge 1000 \implies h = 10$ bits ($2^{10} - 2 = 1,022$ hosts)
- **Prefix Length**: $32 - 10 = /22$ (Subnet Mask: `255.255.252.0`)
- **Block Size**: $2^{10} = 1,024$ IP addresses
- **Network Address**: `10.20.0.0/22`
- **Usable Host Range**: `10.20.0.1` – `10.20.3.254`
- **Broadcast Address**: `10.20.3.255`
- **Total Usable Hosts**: 1,022

#### Subnet 2: `public` Subnet (Load Balancer Tier)
- **Placement**: Starts immediately after the `app` subnet at `10.20.4.0`
- **Hosts Needed**: 250
- **Host Bits Required ($h$)**: $2^h - 2 \ge 250 \implies h = 8$ bits ($2^8 - 2 = 254$ hosts)
- **Prefix Length**: $32 - 8 = /24$ (Subnet Mask: `255.255.255.0`)
- **Block Size**: $2^8 = 256$ IP addresses
- **Network Address**: `10.20.4.0/24`
- **Usable Host Range**: `10.20.4.1` – `10.20.4.254`
- **Broadcast Address**: `10.20.4.255`
- **Total Usable Hosts**: 254

#### Subnet 3: `data` Subnet (SeaweedFS / Storage Tier)
- **Placement**: Starts immediately after the `public` subnet at `10.20.5.0`
- **Hosts Needed**: 100
- **Host Bits Required ($h$)**: $2^h - 2 \ge 100 \implies h = 7$ bits ($2^7 - 2 = 126$ hosts)
- **Prefix Length**: $32 - 7 = /25$ (Subnet Mask: `255.255.255.128`)
- **Block Size**: $2^7 = 128$ IP addresses
- **Network Address**: `10.20.5.0/25`
- **Usable Host Range**: `10.20.5.1` – `10.20.5.126`
- **Broadcast Address**: `10.20.5.127`
- **Total Usable Hosts**: 126

#### Subnet 4: `management` Subnet (Bastion / Admin Tier)
- **Placement**: Starts immediately after the `data` subnet at `10.20.5.128`
- **Hosts Needed**: 20
- **Host Bits Required ($h$)**: $2^h - 2 \ge 20 \implies h = 5$ bits ($2^5 - 2 = 30$ hosts)
- **Prefix Length**: $32 - 5 = /27$ (Subnet Mask: `255.255.255.224`)
- **Block Size**: $2^5 = 32$ IP addresses
- **Network Address**: `10.20.5.128/27`
- **Usable Host Range**: `10.20.5.129` – `10.20.5.158`
- **Broadcast Address**: `10.20.5.159`
- **Total Usable Hosts**: 30

---

### Subnet Summary Table

| Subnet Name | Hosts Needed | Network Address | Prefix Length | Subnet Mask | Usable Host Range | Broadcast Address | Usable Hosts |
|---|---|---|---|---|---|---|---|
| **app** | 1,000 | `10.20.0.0` | `/22` | `255.255.252.0` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **public** | 250 | `10.20.4.0` | `/24` | `255.255.255.0` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **data** | 100 | `10.20.5.0` | `/25` | `255.255.255.128` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **management** | 20 | `10.20.5.128` | `/27` | `255.255.255.224` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

Remaining Unallocated Space in `10.20.0.0/16`: `10.20.5.160` to `10.20.255.255` (available for future growth).

---

## 2. Stateless Network Access Control List (NACL) Rationale

### Why Stateless NACLs Require Separate Reply Rules
Unlike stateful firewalls (such as AWS Security Groups or iptables `conntrack`), a **Network Access Control List (NACL) is completely stateless**. It does not maintain a session connection table and evaluates every individual packet in complete isolation:
1. When an external client sends an HTTP GET packet to the load balancer (port 80 or 443), the inbound rule allows it.
2. However, when the load balancer sends back the HTTP response packet to the client, the NACL evaluates this outbound packet as a completely new packet. Because client operating systems allocate dynamic client ports (ephemeral ports `1024`–`65535`), the outbound NACL must have an explicit rule permitting TCP traffic to destination ports `1024`–`65535` for `0.0.0.0/0`.
3. Similarly, when the load balancer forwards requests internally to the `app` subnet on port `8000`, the return packets sent from the `app` subnet back to the load balancer arrive on the load balancer's ephemeral source ports. Thus, an explicit inbound rule allowing traffic from `10.20.0.0/22` on destination ports `1024`–`65535` is strictly required. Without explicit return rules in both directions, bidirectional TCP communication completely collapses after the initial SYN packet.

### Why Rule Ordering Matters for `198.51.100.0/24`
NACLs evaluate rules in **strict numerical ascending order** (lowest rule number first), and the **first matching rule terminates evaluation** ("first match wins"):
- The abusive CIDR block `198.51.100.0/24` is a subset of the global internet range `0.0.0.0/0`.
- We have an explicit security requirement to block all traffic from `198.51.100.0/24`, even on legitimate web ports like 80 and 443.
- If the allow rule for web ports (`0.0.0.0/0` on port 80/443) had a lower rule number (e.g., Rule 100) than the deny rule (e.g., Rule 200), an incoming HTTP packet from `198.51.100.9` would match Rule 100 first, be immediately **allowed**, and the deny rule would never be evaluated.
- Therefore, the block rule for `198.51.100.0/24` **MUST** be placed at a lower rule number (Rule 100) before any general allow rules (Rules 200, 210, etc.), guaranteeing that abusive packets are dropped before wider permissions are evaluated.
