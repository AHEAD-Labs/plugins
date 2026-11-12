INCIDENTS = {
    "INC-101": {"title": "Payment API latency", "severity": "sev2", "state": "investigating", "owner_team": "platform"},
    "INC-102": {"title": "VPN certificate expiry", "severity": "sev3", "state": "monitoring", "owner_team": "network"},
    "INC-103": {"title": "Data pipeline delay", "severity": "sev2", "state": "resolved", "owner_team": "data"},
}
ACL = {"alice": ["INC-101", "INC-102", "INC-103"], "bob": ["INC-102"], "carol": ["INC-101", "INC-103"]}


class NotAllowed(Exception):
    pass
