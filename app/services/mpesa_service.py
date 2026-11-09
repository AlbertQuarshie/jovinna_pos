"""M-Pesa STK Push (Lipa na M-Pesa Online) through Safaricom's Daraja API, for a Buy Goods till.

The desktop app has no public server for Safaricom's callback, so instead of waiting to be told,
it asks Safaricom for the result with the STK Push Query API every few seconds.

Settings (admin only, stored encrypted by secure_store):
  environment      "sandbox" (Safaricom's test system) or "live"
  consumer_key, consumer_secret, passkey   from the Daraja app / Go-Live email
  store_number     BusinessShortCode — for Buy Goods, the store / head office number
  till_number      PartyB — the till customers pay to
"""
import base64
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app import config
from app.services import secure_store

SETTINGS_NAME = "mpesa"
HOSTS = {"sandbox": "https://sandbox.safaricom.co.ke", "live": "https://api.safaricom.co.ke"}
# Safaricom's published sandbox test shortcode and passkey (not secret)
SANDBOX_SHORTCODE = "174379"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
# Used when no callback URL is set in Settings. The app reads results with the STK Query API, but
# Safaricom may not complete a payment whose callback address can't be reached.
DEFAULT_CALLBACK_URL = "https://example.com/jovinna-pos/mpesa-callback"
LOG_FILE = config.DATA_DIR / "mpesa.log"

TIMEOUT = 20  # seconds per request

# Codes that mean "no final answer yet" — keep checking
STILL_PROCESSING = {"4999", "500.001.1001"}

# What the customer did, from the query's ResultCode
RESULT_MESSAGES = {
    "0": "Paid",
    "1": "The customer doesn't have enough money in M-Pesa",
    "1032": "The customer cancelled the request",
    "1037": "The customer's phone didn't respond (it may be off or out of network)",
    "2001": "The customer entered the wrong M-Pesa PIN",
    "1019": "The request expired before the customer paid",
    "1001": "The customer has another M-Pesa transaction in progress, try again in a moment",
}


def _log(action: str, status: int, body: dict) -> None:
    """What Safaricom answered (never keys, tokens or passwords), for finding payment problems."""
    safe = {k: v for k, v in body.items() if k not in ("access_token", "Password")}
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {action:6} HTTP {status}  {json.dumps(safe)}\n")
    except OSError:
        pass


class MpesaError(Exception):
    pass


@dataclass
class Settings:
    environment: str = "sandbox"
    consumer_key: str = ""
    consumer_secret: str = ""
    passkey: str = ""
    store_number: str = ""
    till_number: str = ""
    callback_url: str = ""   # custom callback (e.g. webhook.site while testing); ignored when server_url is set
    server_url: str = ""     # your callback server, e.g. https://jovinna-mpesa.yourname.workers.dev
    server_key: str = ""     # the APP_KEY secret set on that server
    enabled: bool = False

    @property
    def ready(self) -> bool:
        needed = [self.consumer_key, self.consumer_secret]
        if self.environment == "live":
            needed += [self.passkey, self.store_number, self.till_number]
        return self.enabled and all(x.strip() for x in needed)


def load_settings() -> Settings:
    try:
        data = secure_store.load(SETTINGS_NAME)
    except Exception:  # noqa: BLE001 — unreadable settings act as "not set up"
        data = {}
    known = Settings.__dataclass_fields__
    return Settings(**{k: v for k, v in data.items() if k in known})


def save_settings(s: Settings) -> None:
    secure_store.save(SETTINGS_NAME, s.__dict__)
    _token_cache.clear()


def normalise_phone(text: str) -> str:
    """0712 345 678 / +254712345678 / 712345678 -> 254712345678. Raises MpesaError if not valid."""
    digits = re.sub(r"\D", "", text or "")
    if digits.startswith("254"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9 or digits[0] not in "17":
        raise MpesaError("Enter a Safaricom number like 0712 345 678 or 0110 123 456")
    return "254" + digits


def whole_shillings(amount: Decimal) -> int:
    """M-Pesa only takes whole shillings; any cents are rounded up."""
    return int(math.ceil(amount))


# ---- HTTP (replaceable in tests) ----

def _http(method: str, url: str, headers: dict, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "User-Agent": f"JovinnaPOS/{config.APP_VERSION}",  # Cloudflare blocks the default Python agent
        **headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            try:
                return resp.status, json.loads(resp.read() or b"{}")
            except ValueError:  # not JSON, e.g. a web page from the wrong address
                return resp.status, {}
    except urllib.error.HTTPError as e:  # Daraja sends useful JSON with 4xx/5xx too
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise MpesaError("Can't reach Safaricom. Check the internet connection.") from e


_token_cache: dict = {}


def _token(s: Settings) -> str:
    cached = _token_cache.get(s.environment)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    auth = base64.b64encode(f"{s.consumer_key.strip()}:{s.consumer_secret.strip()}".encode()).decode()
    status, body = _http("GET", f"{HOSTS[s.environment]}/oauth/v1/generate?grant_type=client_credentials",
                         {"Authorization": f"Basic {auth}"})
    token = body.get("access_token")
    if status != 200 or not token:
        raise MpesaError("Safaricom rejected the Consumer Key / Secret. Check them in Settings.")
    _token_cache[s.environment] = (token, time.time() + int(body.get("expires_in", 3599)))
    return token


def _shortcode_and_passkey(s: Settings) -> tuple[str, str, str, str]:
    """(BusinessShortCode, PartyB, passkey, TransactionType)."""
    if s.environment == "sandbox":
        return SANDBOX_SHORTCODE, SANDBOX_SHORTCODE, SANDBOX_PASSKEY, "CustomerPayBillOnline"
    return s.store_number.strip(), s.till_number.strip(), s.passkey.strip(), "CustomerBuyGoodsOnline"


def _password(shortcode: str, passkey: str) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return base64.b64encode(f"{shortcode}{passkey}{stamp}".encode()).decode(), stamp


def callback_url(s: Settings) -> str:
    """Where Safaricom sends the result. With a callback server, its secret path is derived from the
    server key (the server works it out the same way), so only one secret has to be managed."""
    if s.server_url.strip() and s.server_key.strip():
        path = hashlib.sha256(s.server_key.strip().encode()).hexdigest()[:24]
        return f"{s.server_url.strip().rstrip('/')}/mpesa/callback/{path}"
    return s.callback_url.strip() or DEFAULT_CALLBACK_URL


def has_server(s: Settings) -> bool:
    return bool(s.server_url.strip() and s.server_key.strip())


def _server_get(s: Settings, path: str) -> tuple[int, dict]:
    return _http("GET", s.server_url.strip().rstrip("/") + path, {"Authorization": f"Bearer {s.server_key.strip()}"})


def test_server(s: Settings) -> None:
    status, body = _server_get(s, "/health")
    if status == 401:
        raise MpesaError("The callback server rejected the key. Check the Server key matches APP_KEY.")
    if status != 200 or not body.get("ok"):
        raise MpesaError(f"The callback server didn't answer correctly (error {status}). Check the address.")


def fetch_result(s: Settings, checkout_id: str) -> dict | None:
    """The stored callback for a payment (receipt code, amount, phone), or None if not arrived yet
    or the server can't be reached. Never raises: the payment itself is already confirmed."""
    if not has_server(s):
        return None
    try:
        status, body = _server_get(s, f"/mpesa/result/{checkout_id}")
    except MpesaError:
        return None
    _log("result", status, body)
    return body if status == 200 and "result_code" in body else None


def test_connection(s: Settings) -> None:
    _token_cache.pop(s.environment, None)
    _token(s)


def stk_push(s: Settings, phone: str, amount: Decimal, reference: str) -> str:
    """Send the PIN prompt to the customer's phone. Returns Safaricom's CheckoutRequestID."""
    shortcode, party_b, passkey, tx_type = _shortcode_and_passkey(s)
    password, stamp = _password(shortcode, passkey)
    status, body = _http("POST", f"{HOSTS[s.environment]}/mpesa/stkpush/v1/processrequest",
                         {"Authorization": f"Bearer {_token(s)}"}, {
                             "BusinessShortCode": shortcode, "Password": password, "Timestamp": stamp,
                             "TransactionType": tx_type, "Amount": whole_shillings(amount),
                             "PartyA": phone, "PartyB": party_b, "PhoneNumber": phone,
                             "CallBackURL": callback_url(s),
                             "AccountReference": reference[:12], "TransactionDesc": config.SHOP_NAME[:13],
                         })
    _log("push", status, body)
    if status == 200 and str(body.get("ResponseCode")) == "0" and body.get("CheckoutRequestID"):
        return body["CheckoutRequestID"]
    raise MpesaError(body.get("errorMessage") or body.get("ResponseDescription")
                     or f"Safaricom didn't accept the request (error {status})")


def query(s: Settings, checkout_id: str) -> tuple[str, str]:
    """('pending' | 'paid' | 'failed', message for the cashier)."""
    shortcode, _, passkey, _ = _shortcode_and_passkey(s)
    password, stamp = _password(shortcode, passkey)
    status, body = _http("POST", f"{HOSTS[s.environment]}/mpesa/stkpushquery/v1/query",
                         {"Authorization": f"Bearer {_token(s)}"}, {
                             "BusinessShortCode": shortcode, "Password": password, "Timestamp": stamp,
                             "CheckoutRequestID": checkout_id,
                         })
    _log("query", status, body)
    if "ResultCode" in body:
        code = str(body["ResultCode"])
        if code == "0":
            return "paid", "Paid"
        if code in STILL_PROCESSING:
            return "pending", "Waiting for the customer to enter their PIN…"
        return "failed", RESULT_MESSAGES.get(code, body.get("ResultDesc") or f"Payment failed (code {code})")
    # While the customer hasn't answered yet, Daraja replies with an error saying it's still processing
    message = (body.get("errorMessage") or "").lower()
    if "processed" in message or "processing" in message or status in (500, 503):
        return "pending", "Waiting for the customer to enter their PIN…"
    if status == 429:
        return "pending", "Waiting…"
    raise MpesaError(body.get("errorMessage") or f"Couldn't check the payment (error {status})")
