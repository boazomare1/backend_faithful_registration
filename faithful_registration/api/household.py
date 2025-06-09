import frappe
from frappe import _
from frappe.utils import now
import uuid
from werkzeug.wrappers import Response
import json
import pandas as pd
from io import BytesIO
def safe_date(val):
    return val.isoformat() if hasattr(val, "isoformat") else val

@frappe.whitelist(allow_guest=True, methods=["POST"])
def bulk_register_households():
    """Upload an Excel file to create multiple Household records in bulk."""

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        file = frappe.request.files.get("file")
        if not file:
            raise frappe.ValidationError("No Excel file uploaded.")

        df = pd.read_excel(BytesIO(file.read()))
        if "household_name" not in df.columns:
            raise frappe.ValidationError("Missing required column: 'household_name'.")

        total = len(df)
        created, duplicates, failed = 0, 0, 0
        failed_records = []

        for _, row in df.iterrows():
            try:
                household_name = str(row.get("household_name")).strip()
                if not household_name:
                    raise frappe.ValidationError("household_name is required.")

                if frappe.db.exists("Household", {"household_name": household_name}):
                    duplicates += 1
                    failed_records.append({
                        "household_name": household_name,
                        "error": "Duplicate household_name"
                    })
                    continue

                doc = frappe.new_doc("Household")
                for col in df.columns:
                    value = row.get(col)
                    if pd.notna(value):
                        doc.set(col, value)
                doc.insert(ignore_permissions=True)
                created += 1

            except Exception as e:
                failed += 1
                failed_records.append({
                    "household_name": row.get("household_name", "Unknown"),
                    "error": str(e)
                })
                frappe.log_error(frappe.get_traceback(), "Bulk Household Upload Error")

        failed_file_url = None
        if failed_records:
            failed_df = pd.DataFrame(failed_records)
            output = BytesIO()
            failed_df.to_excel(output, index=False)
            output.seek(0)

            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": f"failed_households_{timestamp}.xlsx",
                "is_private": 1,
                "content": output.read()
            })
            file_doc.save(ignore_permissions=True)
            failed_file_url = file_doc.file_url

        response = {
            "data": {
                "total": total,
                "created": created,
                "duplicates": duplicates,
                "failed": failed,
                "failed_file_url": failed_file_url
            },
            "status": "success",
            "code": 200,
            "message": f"Processed {total} records. Created: {created}, Duplicates: {duplicates}, Failed: {failed}.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Bulk Household Upload Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 500,
            "message": "Bulk household upload failed.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=500, content_type="application/json")


@frappe.whitelist(allow_guest=True)
def create_household():
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")

        payload = data["data"]

        doc = frappe.new_doc("Household")
        doc.update(payload)
        doc.insert(ignore_permissions=True)

        response = {
            "data": {k: safe_date(v) for k, v in doc.as_dict().items()},
            "status": "success",
            "code": 201,
            "message": "Household created successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(response), status=201, content_type="application/json")

    except frappe.DuplicateEntryError:
        frappe.log_error(frappe.get_traceback(), "Duplicate Household Creation")
        error = {
            "data": None,
            "status": "error",
            "code": 409,
            "message": "Duplicate entry error.",
            "errors": {
                "description": "A household with the same name already exists."
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
        frappe.log_error(frappe.get_traceback(), "Household Creation Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to create household.",
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
def get_all_households():
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        records = frappe.get_all(
            "Household",
            fields=[
                "name", "household_name", "head_of_household", "address_line",
                "mosque", "total_members", "creation"
            ],
            order_by="creation desc"
        )

        for r in records:
            r["creation"] = safe_date(r["creation"])

        response = {
            "data": records,
            "status": "success",
            "code": 200,
            "message": "Households retrieved successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(response), status=200, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Households Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve households.",
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
def get_household(name):
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        doc = frappe.get_doc("Household", name)
        doc_dict = doc.as_dict()

        for key, value in doc_dict.items():
            if hasattr(value, "isoformat"):
                doc_dict[key] = value.isoformat()

        response = {
            "data": doc_dict,
            "status": "success",
            "code": 200,
            "message": "Household retrieved successfully.",
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
            "message": "Household not found.",
            "errors": {
                "description": f"No Household found with name '{name}'."
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Household Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to retrieve household.",
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
def update_household():
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

        doc = frappe.get_doc("Household", name)
        doc.update(payload)
        doc.save(ignore_permissions=True)

        response = {
            "data": {k: safe_date(v) if hasattr(v, "isoformat") else v for k, v in doc.as_dict().items()},
            "status": "success",
            "code": 200,
            "message": "Household updated successfully.",
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
            "message": "Household not found.",
            "errors": {
                "description": f"No Household found with name '{name}'."
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
            "message": "Failed to update household.",
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
        frappe.log_error(frappe.get_traceback(), "Update Household Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to update household.",
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
def delete_household(name):
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        doc = frappe.get_doc("Household", name)
        doc.delete(ignore_permissions=True)

        response = {
            "data": {"name": name},
            "status": "success",
            "code": 200,
            "message": "Household deleted successfully.",
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
            "message": "Household not found.",
            "errors": {
                "description": f"No Household found with name '{name}'."
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=404, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete Household Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to delete household.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")
