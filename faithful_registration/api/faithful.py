import frappe
from frappe import _
from frappe.utils import now
import uuid
from werkzeug.wrappers import Response
import json

@frappe.whitelist(allow_guest=True)
def register_faithful():
    """Create a new Faithful record via API"""

    request_id = str(uuid.uuid4())
    timestamp = now()

    raw_data = frappe.local.request.get_data(as_text=True)
    frappe.log_error(f"Raw input data: {raw_data}", "Debug register_faithful input")

    try:
        data_parsed = json.loads(raw_data)

        if not isinstance(data_parsed, dict) or "data" not in data_parsed:
            raise frappe.ValidationError(_("Request payload must include a non-empty 'data' object."))

        payload = data_parsed["data"]

        if not isinstance(payload, dict) or not payload:
            raise frappe.ValidationError(_("Request payload must include a non-empty 'data' object."))

        doc = frappe.new_doc("Faithful Profile")
        doc.update(payload)
        doc.insert(ignore_permissions=True)

        response_body = {
            "data": {
                "name": doc.name,
                "created_at": doc.creation,
                **payload
            },
            "status": "success",
            "code":200,
            "message": _("Faithful profile registered successfully."),
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(
            json.dumps(response_body),
            status=201,
            content_type="application/json"
        )

    except frappe.DuplicateEntryError:
        frappe.log_error(frappe.get_traceback(), "Duplicate Faithful Registration")

        error_body = {
            "data": None,
            "status": "error",
            "message": _("Duplicate entry error."),
            "errors": {
                "field": "user_id or national_id_number",
                "description": _("A record with the same user ID or national ID already exists.")
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error_body), status=409, content_type="application/json")

    except frappe.ValidationError as e:
        frappe.log_error(frappe.get_traceback(), "Validation Error")

        error_body = {
            "data": None,
            "status": "error",
            "message": _("Validation failed."),
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error_body), status=422, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Faithful Registration Failed")

        error_body = {
            "data": None,
            "status": "error",
            "message": _("Failed to register Faithful profile."),
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(error_body), status=400, content_type="application/json")
