import frappe
import random
from frappe.utils import now_datetime
from frappe import _
from frappe.utils import now
import uuid
from werkzeug.wrappers import Response
import json
from frappe.core.doctype.user.user import reset_password

# --- CORS Helper ---
def cors_response(body, status=200):
    response = Response(json.dumps(body), status=status, content_type="application/json")
    response.headers["Access-Control-Allow-Origin"] = "http://localhost:8081"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response

@frappe.whitelist(allow_guest=True)
def send_otp(email):
    cooldown_key = f"otp_cooldown:{email}"
    if frappe.cache().get_value(cooldown_key):
        return {
            "status": "error",
            "message": "OTP already sent. Please wait before requesting again."
        }

    otp = str(random.randint(100000, 999999))
    frappe.cache().set_value(f"otp:{email}", otp, expires_in_sec=300)  # OTP valid for 5 minutes
    frappe.cache().set_value(cooldown_key, True, expires_in_sec=60)    # 1-minute cooldown

    email_content = f"""
        <p>Your OTP is: <strong>{otp}</strong></p>
        <p>This code expires in 5 minutes.</p>
    """

    try:
        frappe.sendmail(
            recipients=email,
            subject="Your OTP Code",
            message=email_content,
            now=True
        )
        return {
            "status": "success",
            "message": "OTP sent successfully."
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "OTP Email Sending Failed")
        return {
            "status": "error",
            "message": f"Error sending OTP: {str(e)}"
        }

@frappe.whitelist(allow_guest=True)
def verify_otp(email, otp):
    cached_otp = frappe.cache().get_value(f"otp:{email}")

    if not cached_otp:
        return {
            "status": "error",
            "message": "OTP expired or not found."
        }

    if str(cached_otp) != str(otp).strip():
        return {
            "status": "error",
            "message": "Invalid OTP."
        }

    # OTP is valid – you can now delete it and proceed with whatever follows
    frappe.cache().delete_value(f"otp:{email}")

    return {
        "status": "success",
        "message": "OTP verified successfully."
    }

@frappe.whitelist(allow_guest=True)
def login_user(email, password):
    try:
        from frappe.auth import LoginManager

        # Attempt login
        login_manager = LoginManager()
        login_manager.authenticate(user=email, pwd=password)
        login_manager.post_login()

        # Fetch session ID
        sid = frappe.session.sid

        return {
            "status": "success",
            "message": "Login successful",
            "sid": sid,
            "user": frappe.session.user
        }

    except frappe.AuthenticationError as e:
        frappe.clear_messages()
        return {
            "status": "error",
            "message": "Invalid email or password",
            "error": str(e)
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Login Failed")
        return {
            "status": "error",
            "message": "Login failed due to an unexpected error.",
            "error": str(e)
        }

@frappe.whitelist(allow_guest=True)
def forgot_password(email):
    """
    Accepts an email address and triggers the password reset process.
    """

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not email:
            raise frappe.ValidationError("Missing required field: 'email'")

        user_email = email.strip().lower()

        # Check if user exists
        if not frappe.db.exists("User", user_email):
            return cors_response({
                "data": None,
                "status": "error",
                "code": 404,
                "message": _("User not found."),
                "errors": {
                    "description": f"No user exists with email '{user_email}'."
                },
                "meta": {
                    "request_id": request_id,
                    "timestamp": timestamp
                }
            }, status=404)

        # Use built-in method to send reset email
        reset_password(user_email)

        return cors_response({
            "data": {"email": user_email},
            "status": "success",
            "code": 200,
            "message": "Password reset link sent to email.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        })

    except frappe.ValidationError as ve:
        frappe.log_error(frappe.get_traceback(), "Forgot Password Validation Failed")
        return cors_response({
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Validation failed.",
            "errors": {
                "description": str(ve)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }, status=400)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Forgot Password Failed")
        return cors_response({
            "data": None,
            "status": "error",
            "code": 500,
            "message": "Failed to send password reset link.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }, status=500)

# The duplicated block at the end of your original script appears redundant and is now removed.
