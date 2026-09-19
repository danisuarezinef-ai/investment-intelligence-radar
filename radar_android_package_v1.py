"""APK/AAB release metadata gate. Does not claim a package has been physically built."""
REAL_TRADING=False
ALLOWED_ARTIFACTS=("apk","aab")
def package_gate(meta):
    meta=meta if isinstance(meta,dict) else {}
    needed=("version","version_code","artifact","package_id","sha256","signature_verified","min_sdk","target_sdk")
    missing=[k for k in needed if meta.get(k) in (None,"")]
    if missing:return {"allowed":False,"reason":"MISSING_METADATA","missing":missing}
    if meta["artifact"] not in ALLOWED_ARTIFACTS:return {"allowed":False,"reason":"INVALID_ARTIFACT"}
    if meta.get("signature_verified") is not True:return {"allowed":False,"reason":"SIGNATURE_UNVERIFIED"}
    if meta.get("real_trading") is not False:return {"allowed":False,"reason":"UNSAFE_TRADING_STATE"}
    return {"allowed":True,"reason":"PACKAGE_CANDIDATE"}
