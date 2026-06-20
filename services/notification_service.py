import os
import json
import base64
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
import database as db
from config import VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL, TIMEZONE


_vapid_instance = None
_vapid_public_key_cache = None
_pywebpush_available = None
_webpush_func = None


class NotificationService:

    @staticmethod
    def load_vapid():
        global _vapid_instance, _vapid_public_key_cache
        if _vapid_instance is not None:
            return _vapid_instance, _vapid_public_key_cache
        try:
            key_bytes = VAPID_PRIVATE_KEY.encode()
            try:
                from py_vapid import Vapid
                _vapid_instance = Vapid.from_pem(key_bytes)
            except ImportError:
                _vapid_instance = serialization.load_pem_private_key(
                    key_bytes, password=None, backend=default_backend(),
                )
            if isinstance(_vapid_instance, EllipticCurvePrivateKey):
                raw_pub = _vapid_instance.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            else:
                raw_pub = _vapid_instance.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            _vapid_public_key_cache = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
            return _vapid_instance, _vapid_public_key_cache
        except Exception:
            _vapid_instance = None
            _vapid_public_key_cache = None
            return None, None

    @staticmethod
    def send_push_notification(user_id, title, body, icon=None, tag=None, data=None):
        global _pywebpush_available, _webpush_func
        if not VAPID_PRIVATE_KEY or not VAPID_CLAIM_EMAIL:
            return 0
        if _pywebpush_available is None:
            try:
                from pywebpush import webpush
                _webpush_func = webpush
                _pywebpush_available = True
            except ImportError:
                _pywebpush_available = False
                return 0
        if not _pywebpush_available or _webpush_func is None:
            return 0
        vapid_key, _ = NotificationService.load_vapid()
        if vapid_key is None:
            return 0
        subs = db.get_user_push_subscriptions(user_id)
        if not subs:
            return 0
        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": icon or "/static/icon-192.png",
            "badge": "/static/icon-192.png",
            "tag": tag or "default",
            "data": data or {},
        })
        ok_count = 0
        for sub in subs:
            try:
                _webpush_func(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh_key"], "auth": sub["auth_key"]},
                    },
                    data=payload,
                    vapid_private_key=vapid_key,
                    vapid_claims={"sub": VAPID_CLAIM_EMAIL},
                )
                ok_count += 1
            except Exception as e:
                err_str = str(e)
                if "410" in err_str or "404" in err_str or "gone" in err_str.lower() or "unregistered" in err_str.lower():
                    try:
                        db.remove_push_subscription(user_id, sub["endpoint"])
                    except Exception:
                        pass
        return ok_count

    @staticmethod
    def build_digest_body(user_id):
        yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        month = datetime.now(TIMEZONE).strftime("%Y-%m")
        summary = db.get_yesterday_expense_summary(user_id, yesterday)
        month_total = db.get_month_to_date_total(user_id, month)
        daily_avg = db.get_daily_average(user_id, month)
        parts = []
        if summary["total"] > 0:
            parts.append(f"Yesterday: ৳{summary['total']:,.0f} ({summary['count']} entries)")
        else:
            parts.append("Yesterday: No expenses")
        parts.append(f"MTD: ৳{month_total:,.0f}")
        if daily_avg > 0:
            parts.append(f"Avg: ৳{daily_avg:,.0f}/day")
        body = " | ".join(parts)
        extra = []
        if summary["top_category"] and summary["top_category_amount"] > 0:
            extra.append(f"Top: {summary['top_category']} (৳{summary['top_category_amount']:,.0f})")
        budget_alerts = db.get_budget_status(user_id, month)
        for alert in budget_alerts:
            pct = int(alert["percentage"])
            if pct >= 80:
                extra.append(f"⚠️ {alert['category']} {pct}%")
        if extra:
            body += "\n" + " | ".join(extra)
        return body

    @staticmethod
    def is_vapid_configured():
        return _vapid_instance is not None

    @staticmethod
    def is_webpush_available():
        return _pywebpush_available is True
