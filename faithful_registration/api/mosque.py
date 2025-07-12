import frappe
from frappe.utils import now,get_files_path
import uuid
from werkzeug.wrappers import Response
import json
import frappe
from frappe import _
import pandas as pd
from io import BytesIO
import base64, re, os
def safe_date(val):
    return val.isoformat() if hasattr(val, "isoformat") else val

@frappe.whitelist(allow_guest=True, methods=["POST"])
def bulk_register_mosques():
    """
    Upload an Excel file to register multiple mosques in bulk.
    Each row must contain at least the 'mosque_name'.
    """

    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        # Step 1: Receive the uploaded file
        file = frappe.request.files.get("file")
        if not file:
            raise frappe.ValidationError("No file uploaded. Expecting an Excel file.")

        df = pd.read_excel(BytesIO(file.read()))
        if "mosque_name" not in df.columns:
            raise frappe.ValidationError("Missing required column: 'mosque_name'")

        total_records = len(df)
        created = 0
        duplicates = 0
        failed = 0
        failed_records = []

        for i, row in df.iterrows():
            try:
                mosque_name = str(row.get("mosque_name")).strip()
                if not mosque_name:
                    raise frappe.ValidationError("Mosque name is required.")

                email = str(row.get("contact_email")).strip() if pd.notna(row.get("contact_email")) else None
                phone = str(row.get("contact_phone")).strip() if pd.notna(row.get("contact_phone")) else None

                # Check for duplicates by name
                if frappe.db.exists("Mosque", {"mosque_name": mosque_name}):
                    duplicates += 1
                    failed_records.append({
                        "mosque_name": mosque_name,
                        "error": "Duplicate mosque name"
                    })
                    continue

                # Check for duplicates by email
                if email and frappe.db.exists("Mosque", {"contact_email": email}):
                    duplicates += 1
                    failed_records.append({
                        "mosque_name": mosque_name,
                        "error": f"Duplicate contact email: {email}"
                    })
                    continue

                # Check for duplicates by phone
                if phone and frappe.db.exists("Mosque", {"contact_phone": phone}):
                    duplicates += 1
                    failed_records.append({
                        "mosque_name": mosque_name,
                        "error": f"Duplicate contact phone: {phone}"
                    })
                    continue

                # Create document
                doc = frappe.new_doc("Mosque")
                for col in df.columns:
                    value = row.get(col)
                    if pd.notna(value):
                        doc.set(col, value)

                doc.insert(ignore_permissions=True)
                created += 1

            except Exception as e:
                failed += 1
                failed_records.append({
                    "mosque_name": row.get("mosque_name", "Unknown"),
                    "error": str(e)
                })
                frappe.log_error(frappe.get_traceback(), "Bulk Mosque Upload Error")

        # Prepare failed record export (if needed)
        failed_file_url = None
        if failed_records:
            failed_df = pd.DataFrame(failed_records)
            output = BytesIO()
            failed_df.to_excel(output, index=False)
            output.seek(0)

            # Save as private file in Frappe
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": f"failed_mosques_{timestamp}.xlsx",
                "is_private": 1,
                "content": output.read()
            })
            file_doc.save(ignore_permissions=True)
            failed_file_url = file_doc.file_url

        response = {
            "data": {
                "total": total_records,
                "created": created,
                "duplicates": duplicates,
                "failed": failed,
                "failed_file_url": failed_file_url
            },
            "status": "success",
            "code": 200,
            "message": f"Processed {total_records} records. Created: {created}, Duplicates: {duplicates}, Failed: {failed}.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Bulk Register Mosques Failed")

        error = {
            "data": None,
            "status": "error",
            "code": 500,
            "message": "Bulk mosque upload failed.",
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
def register_mosque():
    """Create a new Mosque via API"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")
        
        payload = data["data"]

        # Mandatory field check
        if not payload.get("mosque_name"):
            raise frappe.ValidationError("Field 'mosque_name' is mandatory.")

        email = payload.get("contact_email")
        phone = payload.get("contact_phone")

        if email and frappe.db.exists("Mosque", {"contact_email": email}):
            raise frappe.ValidationError(f"Email `{email}` is already in use.")

        if phone and frappe.db.exists("Mosque", {"contact_phone": phone}):
            raise frappe.ValidationError(f"Phone `{phone}` is already in use.")

        # Handle base64 images
        for field in ["front_image", "back_image", "madrasa_image", "inside_image", "ceiling_image", "minbar_image"]:
            img = payload.get(field)
            if img and img.startswith("data:"):
                filename = f"{field}_{uuid.uuid4().hex}.jpg"
                payload[field] = save_base64_file(img, filename)

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
    """Retrieve all Mosque records (all fields)"""
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        # <-- pull in *all* fields -->
        records = frappe.get_all(
            "Mosque",
            fields=["*"],
            order_by="creation desc"
        )

        # convert dates to ISO and enrich with head_imam/imams
        for r in records:
            # normalize *every* field for dates
            for key, val in list(r.items()):
                r[key] = safe_date(val)

            # head_imam lookup
            if r.get("head_imam"):
                faithful = frappe.db.get_value("Imam", r["head_imam"], "faithful")
                if faithful:
                    profile = frappe.db.get_value(
                        "Faithful Profile", faithful,
                        ["full_name", "profile_image"],
                        as_dict=True
                    ) or {}
                    r["head_imam_name"]  = profile.get("full_name")
                    r["head_imam_image"] = profile.get("profile_image")

            # imams list
            imams = frappe.get_all(
                "Imam",
                filters={"mosque_assigned": r["name"]},
                fields=["name", "role_in_mosque"]
            )
            for imam in imams:
                faithful = frappe.db.get_value("Imam", imam["name"], "faithful")
                imam["imam_name"] = frappe.db.get_value("Faithful Profile", faithful, "full_name")
            r["imams"] = imams

        return {
            "data": records,
            "status": "success",
            "code": 200,
            "message": _("Mosques retrieved successfully."),
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Mosques Failed")
        error = {
            "data":   None,
            "status": "error",
            "code":   400,
            "message":"Failed to retrieve mosques.",
            "errors": {"description": str(e)},
            "meta": {"request_id": request_id, "timestamp": timestamp}
        }
        return cors_response(error, status=400)

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

        # Head Imam Name & Profile Image
        if doc.head_imam:
            faithful = frappe.db.get_value("Imam", doc.head_imam, "faithful")
            if faithful:
                profile = frappe.db.get_value(
                    "Faithful Profile",
                    faithful,
                    ["full_name", "profile_image"],
                    as_dict=True
                ) or {}
                doc_dict["head_imam_name"] = profile.get("full_name")
                doc_dict["head_imam_image"] = profile.get("profile_image")

        # List of Imams assigned to this mosque
        imams = frappe.get_all(
            "Imam",
            filters={"mosque_assigned": doc.name},
            fields=["name", "role_in_mosque"]
        )
        for imam in imams:
            faithful = frappe.db.get_value("Imam", imam["name"], "faithful")
            imam["imam_name"] = frappe.db.get_value("Faithful Profile", faithful, "full_name")
        doc_dict["imams"] = imams

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

        email = payload.get("contact_email")
        phone = payload.get("contact_phone")

        if email:
            existing = frappe.db.get_value("Mosque", {"contact_email": email}, "name")
            if existing and existing != name:
                raise frappe.ValidationError(f"Email `{email}` is already in use.")

        if phone:
            existing = frappe.db.get_value("Mosque", {"contact_phone": phone}, "name")
            if existing and existing != name:
                raise frappe.ValidationError(f"Phone `{phone}` is already in use.")

        # Handle base64 images
        for field in ["front_image", "back_image", "madrasa_image", "inside_image", "ceiling_image", "minbar_image"]:
            img = payload.get(field)
            if img and img.startswith("data:"):
                filename = f"{field}_{uuid.uuid4().hex}.jpg"
                payload[field] = save_base64_file(img, filename)

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

def save_base64_file(data_url, filename):
    try:
        # Strip out the base64 header: data:image/jpeg;base64,...
        header, encoded = data_url.split(",", 1)
        filedata = base64.b64decode(encoded)

        # Create full file path in /files/
        filepath = os.path.join(get_files_path(), filename)

        # Write the decoded image
        with open(filepath, "wb") as f:
            f.write(filedata)

        # Create and insert the File doc
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": filename,
            "file_url": f"/files/{filename}",
            "is_private": 0
        })
        file_doc.insert(ignore_permissions=True)

        return file_doc.file_url

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_base64_file failed")
        raise