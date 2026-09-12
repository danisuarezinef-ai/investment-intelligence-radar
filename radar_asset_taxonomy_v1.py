"""Stable internal taxonomy for the current Radar observed universe.

This is an application-owned classification used prospectively for memory,
diversification, and concentration analysis. It is deliberately NOT presented as
an externally verified GICS/ICB classification. Existing immutable forward rows are
never rewritten when this taxonomy changes; the taxonomy version is stored with each
new prediction so the meaning remains auditable.
"""
from __future__ import annotations

REAL_TRADING=False
TAXONOMY_VERSION='RADAR_INTERNAL_TAXONOMY_V1'

# Broad, intentionally conservative internal categories. These labels describe the
# analytical grouping Radar uses; they are not claims about an external index vendor.
_ASSETS={
    'MSFT':('TECHNOLOGY','SOFTWARE'),
    'NVDA':('TECHNOLOGY','SEMICONDUCTORS'),
    'GOOGL':('COMMUNICATION_SERVICES','DIGITAL_PLATFORMS'),
    'AMZN':('CONSUMER_DISCRETIONARY','ECOMMERCE_CLOUD'),
    'META':('COMMUNICATION_SERVICES','DIGITAL_PLATFORMS'),
    'AVGO':('TECHNOLOGY','SEMICONDUCTORS'),
    'ASML':('TECHNOLOGY','SEMICONDUCTOR_EQUIPMENT'),
    'SAP':('TECHNOLOGY','SOFTWARE'),
    'TSM':('TECHNOLOGY','SEMICONDUCTORS'),
    'TM':('CONSUMER_DISCRETIONARY','AUTOMOTIVE'),
    'SHEL':('ENERGY','INTEGRATED_ENERGY'),
    'RIO':('MATERIALS','MINING'),
    'LLY':('HEALTH_CARE','PHARMACEUTICALS'),
    'V':('FINANCIALS','PAYMENTS'),
    'BRK-B':('FINANCIALS','DIVERSIFIED_HOLDINGS'),
    'NVS':('HEALTH_CARE','PHARMACEUTICALS'),
}


def classify(symbol:str)->dict:
    key=str(symbol or '').upper()
    item=_ASSETS.get(key)
    if not item:
        return {'sector':None,'industry':None,'taxonomy_version':TAXONOMY_VERSION,
                'taxonomy_scope':'INTERNAL_ANALYTICAL_GROUPING','known':False,'real_trading':False}
    return {'sector':item[0],'industry':item[1],'taxonomy_version':TAXONOMY_VERSION,
            'taxonomy_scope':'INTERNAL_ANALYTICAL_GROUPING','known':True,'real_trading':False}


def coverage(symbols)->dict:
    keys=[str(x or '').upper() for x in symbols]
    known=[x for x in keys if x in _ASSETS]
    return {'universe_n':len(keys),'known_n':len(known),'coverage':len(known)/len(keys) if keys else 0.0,
            'taxonomy_version':TAXONOMY_VERSION,'external_vendor_claim':False,'real_trading':False}
