import frappe
from frappe import _
from frappe.utils import now
import uuid
from werkzeug.wrappers import Response
import json

@frappe.whitelist(allow_guest=True)
def register_faithful():
    """Create a new Faithful Profile via API"""

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        # Parse JSON payload
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")

        payload = data["data"]

        doc = frappe.new_doc("Faithful Profile")
        doc.update(payload)
        doc.insert(ignore_permissions=True)

        # Convert dates safely
        def safe_date(val):
            return val.isoformat() if hasattr(val, "isoformat") else val

        response = {
            "data": {**{k: safe_date(v) for k, v in doc.as_dict().items()}},
            "status": "success",
            "code": 201,
            "message": "Faithful profile registered successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=201, content_type="application/json")

    except frappe.DuplicateEntryError:
        frappe.log_error(frappe.get_traceback(), "Duplicate Faithful Registration")
        error = {
            "data": None,
            "status": "error",
            "code": 409,
            "message": "Duplicate entry error.",
            "errors": {
                "description": "A record with the same user ID or national ID already exists."
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=409, content_type="application/json")

    except frappe.ValidationError as e:
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Validation failed.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Faithful Registration Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to register faithful profile.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")
@frappe.whitelist(allow_guest=True)
def get_all_faithfuls():
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        records = frappe.get_all(
            "Faithful Profile",
            fields=[
                "name", "full_name", "user_id", "phone", "gender", "mosque",
                "national_id_number", "marital_status", "occupation", "creation"
            ],
            order_by="creation desc"
        )

        # Optional: ISO format for date
        for r in records:
            r["creation"] = r["creation"].isoformat() if hasattr(r["creation"], "isoformat") else r["creation"]

        response = {
            "data": records,
            "status": "success",
            "code": 200,
            "message": "Faithful profiles retrieved successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(response), status=200, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Faithfuls Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve faithful profiles.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

@frappe.whitelist(allow_guest=True)
def get_faithful(name):
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        doc = frappe.get_doc("Faithful Profile", name)
        doc_dict = doc.as_dict()

        # Convert all date/datetime values to ISO format
        for key, value in doc_dict.items():
            if hasattr(value, "isoformat"):
                doc_dict[key] = value.isoformat()

        response = {
            "data": doc_dict,
            "status": "success",
            "code": 200,
            "message": "Faithful profile retrieved successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(response), status=200, content_type="application/json")

    except frappe.DoesNotExistError:
        error = {
            "data": None,
            "status": "error",
            "code": 404,
            "message": "Faithful profile not found.",
            "errors": {
                "description": f"No Faithful Profile found with name '{name}'"
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Faithful Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve faithful profile.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")


@frappe.whitelist(allow_guest=True)
def delete_faithful(name=None, user_id=None):
    """Delete a Faithful Profile by name or user_id."""

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not name and not user_id:
            raise frappe.ValidationError("You must provide either 'name' or 'user_id'")

        # Determine the correct record to delete
        if user_id:
            doc = frappe.get_doc("Faithful Profile", {"user_id": user_id})
        else:
            doc = frappe.get_doc("Faithful Profile", name)

        deleted_name = doc.name
        doc.delete(ignore_permissions=True)

        response = {
            "data": {
                "name": deleted_name
            },
            "status": "success",
            "message": "Faithful profile deleted successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except frappe.DoesNotExistError:
        error = {
            "data": None,
            "status": "error",
            "message": "Faithful profile not found.",
            "errors": {
                "description": f"No record found for name={name} or user_id={user_id}"
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete Faithful Failed")

        error = {
            "data": None,
            "status": "error",
            "message": "Failed to delete faithful profile.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(error), status=400, content_type="application/json")

@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_faithful():
    """Update a Faithful Profile using full payload format"""

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        # Get JSON payload directly
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")

        payload = data["data"]

        name = payload.get("name")
        if not name:
            raise frappe.ValidationError("Missing 'name' field in data for update.")

        doc = frappe.get_doc("Faithful Profile", name)
        doc.update(payload)
        doc.save(ignore_permissions=True)

        # Convert dates safely
        def safe_date(val):
            return val.isoformat() if hasattr(val, "isoformat") else val

        response = {
            "data": {**{k: safe_date(v) if hasattr(v, "isoformat") else v for k, v in doc.as_dict().items()}},
            "status": "success",
            "code": 200,
            "message": "Faithful profile updated successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except frappe.DoesNotExistError:
        error = {
            "data": None,
            "status": "error",
            "code": 404,
            "message": "Faithful profile not found.",
            "errors": {
                "description": f"No record found for name={name}"
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=404, content_type="application/json")

    except frappe.ValidationError as e:
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to update faithful profile.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Faithful Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to update faithful profile.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")
