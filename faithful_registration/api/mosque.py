import frappe
from frappe.utils import now
import uuid
from werkzeug.wrappers import Response
import json

def safe_date(val):
    return val.isoformat() if hasattr(val, "isoformat") else val

@frappe.whitelist(allow_guest=True)
def register_mosque():
    """Create a new Mosque via API"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")
        
        payload = data["data"]

        # Ensure mandatory field
        if not payload.get("mosque_name"):
            raise frappe.ValidationError("Field 'mosque_name' is mandatory.")

        doc = frappe.new_doc("Mosque")
        doc.update(payload)
        doc.insert(ignore_permissions=True)

        response = {
            "data": {k: safe_date(v) for k, v in doc.as_dict().items()},
            "status": "success",
            "code": 201,
            "message": "Mosque registered successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=201, content_type="application/json")

    except frappe.DuplicateEntryError:
        frappe.log_error(frappe.get_traceback(), "Duplicate Mosque Registration")
        error = {
            "data": None,
            "status": "error",
            "code": 409,
            "message": "Duplicate entry error.",
            "errors": {
                "description": "A mosque with the same name already exists."
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
        frappe.log_error(frappe.get_traceback(), "Mosque Registration Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to register mosque.",
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
def get_all_mosques():
    """Retrieve all Mosque records"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        records = frappe.get_all(
            "Mosque",
            fields=[
                "name", "mosque_name", "location", "date_established",
                "head_imam", "total_capacity", "contact_email", "contact_phone", "creation"
            ],
            order_by="creation desc"
        )

        for r in records:
            r["date_established"] = safe_date(r["date_established"])
            r["creation"] = safe_date(r["creation"])

        response = {
            "data": records,
            "status": "success",
            "code": 200,
            "message": "Mosques retrieved successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Mosques Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve mosques.",
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
def get_mosque(name):
    """Retrieve one Mosque by name"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        doc = frappe.get_doc("Mosque", name)
        doc_dict = doc.as_dict()
        for key, value in doc_dict.items():
            doc_dict[key] = safe_date(value)

        response = {
            "data": doc_dict,
            "status": "success",
            "code": 200,
            "message": "Mosque retrieved successfully.",
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
            "message": "Mosque not found.",
            "errors": {
                "description": f"No Mosque found with name '{name}'"
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Mosque Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve mosque.",
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
def update_mosque():
    """Update Mosque using full payload"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")

        payload = data["data"]
        name = payload.get("name")
        if not name:
            raise frappe.ValidationError("Missing 'name' field in data for update.")

        doc = frappe.get_doc("Mosque", name)
        doc.update(payload)
        doc.save(ignore_permissions=True)

        response = {
            "data": {k: safe_date(v) for k, v in doc.as_dict().items()},
            "status": "success",
            "code": 200,
            "message": "Mosque updated successfully.",
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
            "message": "Mosque not found.",
            "errors": {
                "description": f"No Mosque found for name={name}"
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
            "message": "Failed to update mosque.",
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
        frappe.log_error(frappe.get_traceback(), "Update Mosque Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to update mosque.",
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
def delete_mosque(name=None):
    """Delete Mosque by name"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not name:
            raise frappe.ValidationError("You must provide 'name' to delete a mosque.")

        doc = frappe.get_doc("Mosque", name)
        deleted_name = doc.name
        doc.delete(ignore_permissions=True)

        response = {
            "data": {"name": deleted_name},
            "status": "success",
            "code": 200,
            "message": "Mosque deleted successfully.",
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
            "message": "Mosque not found.",
            "errors": {
                "description": f"No Mosque found for name={name}"
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete Mosque Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to delete mosque.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(error), status=400, content_type="application/json")
