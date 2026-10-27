"""Lightweight CCF / venue tier mapping (partial, extendable)."""
from typing import Optional

# Simplified CCF-A/B/C examples (expand as needed)
CCF_A = {
    "neurips", "nips", "icml", "iclr", "aaai", "ijcai", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "kdd", "www", "sigir", "sigmod", "vldb", "icde",
    "osdi", "sosp", "eurosys", "asplos", "isca", "micro", "hpca",
    "nature", "science", "cell",
}
CCF_B = {
    "icra", "iros", "rss", "wacv", "bmvc", "coling", "eacl",
    "icdm", "sdm", "cikm", "recsys", "wsdm",
}
CCF_C = {
    "icpr", "accv", "icann", "ijcnn",
}


def get_venue_tier(venue: str) -> Optional[str]:
    if not venue:
        return None
    v = venue.lower().replace(" ", "").replace("-", "")
    for key in CCF_A:
        if key in v:
            return "CCF-A"
    for key in CCF_B:
        if key in v:
            return "CCF-B"
    for key in CCF_C:
        if key in v:
            return "CCF-C"
    return None
