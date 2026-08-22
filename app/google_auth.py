import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException


def google_client_id() -> str:
    return (os.getenv("GOOGLE_CLIENT_ID") or os.getenv("NEXT_PUBLIC_GOOGLE_CLIENT_ID") or "").strip()


def fetch_google_profile(access_token: str) -> dict[str, str]:
    token = (access_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Google sign-in didn’t complete. Try again.")

    if token.count(".") == 2:
        data = _tokeninfo({"id_token": token})
        _assert_audience(data)
        return _profile_from_claims(data)

    client_id = google_client_id()
    if client_id:
        try:
            _assert_audience(_tokeninfo({"access_token": token}))
        except HTTPException:
            # Some access tokens still work with userinfo even if tokeninfo is picky.
            pass

    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    return _profile_from_claims(_read_json(req, fallback="Google sign-in expired. Try again."))


def _tokeninfo(params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"https://oauth2.googleapis.com/tokeninfo?{query}",
        headers={"Accept": "application/json"},
    )
    return _read_json(req, fallback="Google sign-in expired. Try again.")


def _assert_audience(data: dict) -> None:
    client_id = google_client_id()
    if not client_id:
        return
    candidates = {str(data.get("aud") or ""), str(data.get("azp") or "")} - {""}
    if candidates and client_id not in candidates:
        raise HTTPException(status_code=401, detail="Google sign-in is not authorized for this app.")


def _profile_from_claims(data: dict) -> dict[str, str]:
    email = str(data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=401, detail="Google did not share an email address.")
    verified = str(data.get("email_verified", True)).lower()
    if verified not in ("true", "1"):
        raise HTTPException(status_code=401, detail="That Google email is not verified.")
    name = str(data.get("name") or "").strip() or email.split("@")[0]
    return {"email": email, "full_name": name}


def _read_json(req: urllib.request.Request, fallback: str) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=401, detail=fallback) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Google. Try again.") from exc
