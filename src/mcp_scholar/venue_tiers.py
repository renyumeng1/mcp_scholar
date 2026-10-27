"""Lightweight CCF / venue tier mapping (partial, extendable)."""
import re
from typing import Optional, Tuple

# Simplified CCF-A/B/C examples. Matching prefers the longest key.
CCF_A = {
    "neurips", "nips", "icml", "iclr", "aaai", "ijcai", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "kdd", "www", "sigir", "sigmod", "vldb", "icde",
    "osdi", "sosp", "eurosys", "asplos", "isca", "micro", "hpca",
    "nature", "science", "cell",
}
CCF_B = {
    "icra", "iros", "rss", "wacv", "bmvc", "coling", "eacl",
    "icdm", "sdm", "cikm", "recsys", "wsdm", "icassp",
}
CCF_C = {
    "icpr", "accv", "icann", "ijcnn",
}


def match_venue(venue: str) -> Tuple[Optional[str], int]:
    """Return the tier and the length of the most specific matching key."""
    if not venue:
        return None, 0
    compact = re.sub(r"[^a-z0-9]", "", venue.lower())
    best_tier = None
    best_len = 0
    for tier, keys in (("CCF-A", CCF_A), ("CCF-B", CCF_B), ("CCF-C", CCF_C)):
        for key in keys:
            if key in compact and len(key) > best_len:
                best_tier = tier
                best_len = len(key)
    return best_tier, best_len


def get_venue_tier(venue: str) -> Optional[str]:
    return match_venue(venue)[0]