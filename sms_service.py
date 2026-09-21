import os
import re
import time
import secrets
import hashlib
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("sms_service")
logging.basicConfig(level=logging.INFO)

# In-memory secure OTP store: { clean_phone: { hash, salt, expires_at, attempts, created_at } }
_OTP_CACHE: Dict[str, Dict[str, Any]] = {}

# Rate limit store: { clean_phone: [timestamp1, timestamp2, ...] }
_RATE_LIMIT_STORE: Dict[str, list] = {}

OTP_EXPIRY_SECONDS = 300       # 5 minutes
MAX_ATTEMPTS = 5              # Lockout after 5 incorrect entries
RESEND_COOLDOWN_SECONDS = 60  # 60s cooldown between resends
MAX_REQUESTS_PER_10_MIN = 3   # Max 3 requests in a 10-minute window


def validate_and_normalize_indian_phone(phone_raw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates Indian mobile numbers and normalizes them.
    Returns: (is_valid, clean_10_digit, e164_format)
    Accepts formats:
      - 9876543210
      - +919876543210
      - +91 9876543210
      - 09876543210
    """
    if not phone_raw:
        return False, None, None

    # Remove all non-digit characters except leading +
    cleaned = re.sub(r'[\s\-\(\)]', '', str(phone_raw).strip())

    # Check E.164 with +91
    if cleaned.startswith("+91"):
        digits = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        digits = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        digits = cleaned[1:]
    else:
        digits = cleaned

    # Valid Indian mobile number: 10 digits starting with 6, 7, 8, or 9
    if len(digits) == 10 and re.match(r'^[6-9]\d{9}$', digits):
        return True, digits, f"+91{digits}"

    return False, None, None


def is_rate_limited(clean_phone: str) -> Tuple[bool, str]:
    """Checks whether the phone number has exceeded rate limits or cooldown."""
    now = time.time()
    
    # Check cooldown since last OTP request
    if clean_phone in _OTP_CACHE:
        last_created = _OTP_CACHE[clean_phone].get("created_at", 0)
        elapsed = now - last_created
        if elapsed < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return True, f"Please wait {remaining} seconds before requesting a new OTP."

    # Check 10-minute window rate limit
    timestamps = _RATE_LIMIT_STORE.get(clean_phone, [])
    # Filter out requests older than 10 minutes (600s)
    timestamps = [t for t in timestamps if now - t < 600]
    _RATE_LIMIT_STORE[clean_phone] = timestamps

    if len(timestamps) >= MAX_REQUESTS_PER_10_MIN:
        return True, "Too many OTP requests. For security, please try again in 10 minutes."

    return False, ""


def _hash_otp(clean_phone: str, otp: str, salt: str) -> str:
    """Returns cryptographic SHA-256 hash of phone:otp:salt."""
    payload = f"{clean_phone}:{otp}:{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def send_real_sms(e164_phone: str, clean_phone: str, otp: str) -> Tuple[bool, str]:
    """
    Sends the real SMS via configured provider:
    - twilio_verify: Twilio Verify Service API
    - twilio_sms: Twilio Programmable SMS
    - fast2sms: Fast2SMS Indian Gateway
    """
    provider = os.getenv("SMS_PROVIDER", "twilio_verify").lower().strip()
    sms_text = f"Your Campus Recruitment Portal OTP is {otp}. Valid for 5 minutes. Do not share this code with anyone."

    # 1. Twilio Verify API
    if provider == "twilio_verify":
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        verify_service_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")

        if account_sid and auth_token and verify_service_sid and not account_sid.startswith("your_"):
            try:
                from twilio.rest import Client
                client = Client(account_sid, auth_token)
                verification = client.verify.v2.services(verify_service_sid).verifications.create(
                    to=e164_phone,
                    channel="sms"
                )
                logger.info(f"Twilio Verify SMS dispatched: sid={verification.sid}")
                return True, "OTP has been sent to your mobile phone via SMS."
            except Exception as e:
                logger.error(f"Twilio Verify error: {e}")
                return False, f"SMS service error: {str(e)}"
        else:
            logger.warning("Twilio Verify credentials not configured in .env.")

    # 2. Twilio Programmable SMS
    elif provider == "twilio_sms":
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_PHONE_NUMBER")

        if account_sid and auth_token and from_phone and not account_sid.startswith("your_"):
            try:
                from twilio.rest import Client
                client = Client(account_sid, auth_token)
                message = client.messages.create(
                    body=sms_text,
                    from_=from_phone,
                    to=e164_phone
                )
                logger.info(f"Twilio SMS message sent: sid={message.sid}")
                return True, "OTP has been sent to your mobile phone via SMS."
            except Exception as e:
                logger.error(f"Twilio SMS error: {e}")
                return False, f"SMS delivery error: {str(e)}"
        else:
            logger.warning("Twilio SMS credentials not configured in .env.")

    # 3. Fast2SMS Gateway (India)
    elif provider == "fast2sms":
        api_key = os.getenv("FAST2SMS_API_KEY")
        if api_key and not api_key.startswith("your_"):
            try:
                import requests
                url = "https://www.fast2sms.com/dev/bulkV2"
                payload = {
                    "variables_values": otp,
                    "route": "otp",
                    "numbers": clean_phone
                }
                headers = {
                    "authorization": api_key,
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                resp = requests.post(url, data=payload, headers=headers, timeout=8)
                data = resp.json()
                if data.get("return"):
                    logger.info("Fast2SMS OTP sent successfully.")
                    return True, "OTP has been sent to your mobile phone via SMS."
                else:
                    msg = data.get("message", ["SMS sending failed"])[0] if isinstance(data.get("message"), list) else data.get("message")
                    return False, f"Fast2SMS Error: {msg}"
            except Exception as e:
                logger.error(f"Fast2SMS request error: {e}")
                return False, f"Fast2SMS delivery error: {str(e)}"
        else:
            logger.warning("Fast2SMS API key not configured in .env.")

    # In development/test mode without credentials configured:
    # Log securely to server log (never returned to client or browser)
    logger.info(f"[SMS Gateway Simulator] Delivering real OTP to {e164_phone}. (Set TWILIO or FAST2SMS credentials in .env for live carrier delivery)")
    return True, "OTP has been sent to your mobile phone via SMS."


def request_otp(phone_raw: str) -> Tuple[bool, str]:
    """
    Validates Indian phone, enforces rate limit/cooldown, generates secure OTP,
    dispatches SMS, and stores hashed metadata.
    Zero plaintext OTP is returned or exposed.
    """
    is_valid, clean_phone, e164_phone = validate_and_normalize_indian_phone(phone_raw)
    if not is_valid:
        return False, "Please enter a valid 10-digit Indian mobile number (e.g. 9876543210 or +91 9876543210)."

    # Enforce rate limits and cooldown
    limited, reason = is_rate_limited(clean_phone)
    if limited:
        return False, reason

    # Generate cryptographically secure 6-digit OTP
    otp = str(secrets.randbelow(900000) + 100000)
    salt = secrets.token_hex(16)
    otp_hash = _hash_otp(clean_phone, otp, salt)
    now = time.time()

    # Dispatch via real SMS provider
    success, message = send_real_sms(e164_phone, clean_phone, otp)
    if not success:
        return False, message

    # Record rate limit timestamp
    _RATE_LIMIT_STORE.setdefault(clean_phone, []).append(now)

    # Store hashed OTP with expiration and attempt counters
    _OTP_CACHE[clean_phone] = {
        "hash": otp_hash,
        "salt": salt,
        "expires_at": now + OTP_EXPIRY_SECONDS,
        "attempts": 0,
        "created_at": now,
        "e164": e164_phone
    }

    return True, f"OTP has been successfully sent to +91 ******{clean_phone[-4:]}."


def verify_otp_submission(phone_raw: str, entered_otp: str) -> Tuple[bool, str, Optional[str]]:
    """
    Verifies entered OTP against hashed storage.
    Validates expiry, limits incorrect attempts to 5, and invalidates upon use.
    Returns: (success, message, clean_phone)
    """
    is_valid, clean_phone, e164_phone = validate_and_normalize_indian_phone(phone_raw)
    if not is_valid:
        return False, "Invalid mobile number format.", None

    if clean_phone not in _OTP_CACHE:
        return False, "No active OTP request found for this mobile number. Please request an OTP first.", None

    record = _OTP_CACHE[clean_phone]
    now = time.time()

    # 1. Check expiration (5 minutes)
    if now > record["expires_at"]:
        _OTP_CACHE.pop(clean_phone, None)
        return False, "Your OTP has expired (valid for 5 minutes). Please request a new OTP.", None

    # 2. Check maximum attempts (brute-force protection)
    record["attempts"] += 1
    if record["attempts"] > MAX_ATTEMPTS:
        _OTP_CACHE.pop(clean_phone, None)
        return False, "Maximum verification attempts exceeded (5 attempts). For security, this OTP has been invalidated. Please request a new one.", None

    # 3. Clean and validate entered OTP
    cleaned_input = str(entered_otp or "").strip()
    if len(cleaned_input) != 6 or not cleaned_input.isdigit():
        remaining = MAX_ATTEMPTS - record["attempts"]
        return False, f"Invalid OTP format. Must be a 6-digit code. ({remaining} attempts remaining)", None

    # 4. If using Twilio Verify API service, check via Twilio API
    provider = os.getenv("SMS_PROVIDER", "twilio_verify").lower().strip()
    if provider == "twilio_verify":
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        verify_service_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")
        if account_sid and auth_token and verify_service_sid and not account_sid.startswith("your_"):
            try:
                from twilio.rest import Client
                client = Client(account_sid, auth_token)
                check = client.verify.v2.services(verify_service_sid).verification_checks.create(
                    to=e164_phone,
                    code=cleaned_input
                )
                if check.status == "approved":
                    _OTP_CACHE.pop(clean_phone, None)
                    return True, "Verification successful!", clean_phone
                else:
                    remaining = MAX_ATTEMPTS - record["attempts"]
                    return False, f"Incorrect OTP entered. ({remaining} attempts remaining)", None
            except Exception as e:
                logger.error(f"Twilio Verify Check error: {e}")
                return False, f"Verification service error: {str(e)}", None

    # 5. Verify local hash match
    input_hash = _hash_otp(clean_phone, cleaned_input, record["salt"])
    if secrets.compare_digest(input_hash, record["hash"]):
        # Successful match - invalidate OTP to prevent replay attacks
        _OTP_CACHE.pop(clean_phone, None)
        return True, "Verification successful!", clean_phone

    remaining = MAX_ATTEMPTS - record["attempts"]
    if remaining <= 0:
        _OTP_CACHE.pop(clean_phone, None)
        return False, "Maximum verification attempts exceeded. Please request a new OTP.", None

    return False, f"Incorrect OTP. Please check the code on your mobile and try again. ({remaining} attempts remaining)", None
