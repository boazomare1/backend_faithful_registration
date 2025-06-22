# your_app/your_app/api/imam_api.py

import frappe, json, uuid, tempfile
from frappe import _
from frappe.utils import now, get_files_path
from werkzeug.wrappers import Response
import pandas as pd
import base64, re, os

# ——————————————————————————————————————————————————————————————
# Helpers
# ——————————————————————————————————————————————————————————————


def _response(data, status=200, message="Success", code=None, errors=None, meta=None):
    payload = {
        "data": data,
        "status": "success" if status < 400 else "error",
        "message": message,
    }
    if code:
        payload["code"] = code
    if errors:
        payload["errors"] = errors
    if meta:
        payload["meta"] = meta

    # Use default=str so datetime (and other types) become strings
    return Response(
        json.dumps(payload, default=str), status=status, content_type="application/json"
    )


def _error(message, code, status, errors=None, meta=None):
    return _response(
        None, status=status, message=message, code=code, errors=errors, meta=meta
    )


# ——————————————————————————————————————————————————————————————
# Simple Reads
# ——————————————————————————————————————————————————————————————


@frappe.whitelist(allow_guest=True)
def get_imams_by_mosque(mosque_assigned):
    imams = frappe.get_all(
        "Imam",
        filters={"mosque_assigned": mosque_assigned},
        fields=["name", "faithful", "date_appointed", "years_of_experience"],
    )
    return _response(imams)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_all_imams():
    filters = {
        k: v
        for k, v in frappe.local.form_dict.items()
        if k not in ("cmd", "data") and v
    }

    records = frappe.get_all(
        "Imam",
        filters=filters or None,
        fields=[
            "name",
            "faithful",
            "mosque_assigned",
            "date_appointed",
            "years_of_experience",
            "role_in_mosque",
            "status",
        ],
        order_by="creation desc",
    )

    for r in records:
        # — Profile fields —
        prof = (
            frappe.db.get_value(
                "Faithful Profile",
                r["faithful"],
                [
                    "full_name",
                    "date_of_birth",
                    "place_of_birth",
                    "gender",
                    "marital_status",
                    "phone",
                    "email",
                    "profile_image",
                    "national_id_number",
                    "special_needs_proof",
                ],
                as_dict=1,
            )
            or {}
        )

        r.update(
            {
                "imam_name": prof.get("full_name"),
                "date_of_birth": prof.get("date_of_birth"),
                "place_of_birth": prof.get("place_of_birth"),
                "gender": prof.get("gender"),
                "marital_status": prof.get("marital_status"),
                "phone": prof.get("phone"),
                "email": prof.get("email"),
                "profile_image": prof.get("profile_image"),
                "national_id_number": prof.get("national_id_number"),
                "special_needs_proof": prof.get("special_needs_proof"),
            }
        )

        # — Mosque display name —
        if r.get("mosque_assigned"):
            r["mosque_name"] = (
                frappe.db.get_value("Mosque", r["mosque_assigned"], "mosque_name")
                or r["mosque_assigned"]
            )

        # — Certifications (trimmed) —
        certs = frappe.get_all(
            "Imam Certification",
            filters={
                "parent": r["name"],
                "parenttype": "Imam",
                "parentfield": "certifications",
            },
            fields=[
                "idx",
                "certification_name",
                "issuing_body",
                "date_awarded",
                "attachment",
            ],
            order_by="idx",
        )
        r["certifications"] = certs

    return _response(records)


@frappe.whitelist(allow_guest=True)
def get_imam(name=None, faithful=None):
    """
    Single-Imam with:
     - mosque_name
     - imam_name
     - key Profile fields
     - flat child-table lists and trimmed certifications
    """
    if not name and not faithful:
        return _error("Provide `name` or `faithful`", 400, 400)

    if name:
        imam = frappe.get_doc("Imam", name)
    else:
        row = frappe.get_all(
            "Imam", filters={"faithful": faithful}, fields=["name"], limit_page_length=1
        )
        if not row:
            return _error(f"No Imam found for faithful {faithful}", 404, 404)
        imam = frappe.get_doc("Imam", row[0].name)

    data = imam.as_dict()

    # — Profile fields —
    prof = (
        frappe.db.get_value(
            "Faithful Profile",
            imam.faithful,
            [
                "full_name",
                "date_of_birth",
                "place_of_birth",
                "gender",
                "marital_status",
                "phone",
                "email",
                "profile_image",
                "national_id_number",
                "special_needs_proof",
            ],
            as_dict=1,
        )
        or {}
    )
    data.update(
        {
            "imam_name": prof.get("full_name"),
            "date_of_birth": prof.get("date_of_birth"),
            "place_of_birth": prof.get("place_of_birth"),
            "gender": prof.get("gender"),
            "marital_status": prof.get("marital_status"),
            "phone": prof.get("phone"),
            "email": prof.get("email"),
            "profile_image": prof.get("profile_image"),
            "national_id_number": prof.get("national_id_number"),
            "special_needs_proof": prof.get("special_needs_proof"),
        }
    )

    # — Mosque display name —
    mosque_id = data.get("mosque_assigned")
    data["mosque_name"] = (
        frappe.db.get_value("Mosque", mosque_id, "mosque_name") if mosque_id else None
    )

    # — Flat child-table lists —
    data["teaching_subjects"] = [d.subject for d in imam.get("teaching_subjects", [])]
    data["expertise"] = [d.area for d in imam.get("expertise", [])]
    data["languages"] = [d.language for d in imam.get("languages", [])]

    # — Certifications (trimmed) —
    data["certifications"] = [
        {
            "idx": cert.idx,
            "certification_name": cert.certification_name,
            "issuing_body": cert.issuing_body,
            "date_awarded": cert.date_awarded,
            "attachment": cert.attachment,
        }
        for cert in imam.get("certifications", [])
    ]

    return _response(data)


# ——————————————————————————————————————————————————————————————
# Create / Update / Delete
# ——————————————————————————————————————————————————————————————


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_imam():
    """POST JSON { data: { faithful, mosque, date_appointed, … } }"""
    payload = frappe.local.request.get_json().get("data", {})
    for field in ("faithful", "mosque_assigned", "date_appointed"):
        if not payload.get(field):
            return _error(f"Missing required field `{field}`", 400, 400)
    try:
        doc = frappe.get_doc({"doctype": "Imam", **payload}).insert(
            ignore_permissions=True
        )
        return get_imam(name=doc.name)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "register_imam")
        return _error("Failed to create Imam", 500, 500, {"description": str(e)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_imam():
    """POST JSON { data: { name, field1:val1, certifications: [], … } }"""
    payload = frappe.local.request.get_json().get("data", {})
    name = payload.pop("name", None)
    if not name:
        return _error("Missing `name` for update", 400, 400)

    try:
        doc = frappe.get_doc("Imam", name)

        # Handle certifications
        certifications = payload.pop("certifications", [])
        if certifications:
            doc.set("certifications", [])  # Clear existing

            for cert in certifications:
                attachment = cert.get("attachment")

                if attachment and attachment.startswith("data:"):
                    try:
                        attachment_url = save_base64_file(attachment, "Imam", name)
                        cert["attachment"] = attachment_url
                    except Exception as e:
                        return _error(
                            "Attachment upload failed",
                            400,
                            400,
                            {"description": str(e)},
                        )
                elif not attachment:
                    cert["attachment"] = None

                doc.append("certifications", cert)

        # Update other fields
        doc.update(payload)
        doc.save(ignore_permissions=True)
        return get_imam(name=doc.name)

    except frappe.DoesNotExistError:
        return _error("Imam not found", 404, 404)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "update_imam")
        return _error("Failed to update Imam", 500, 500, {"description": str(e)})


@frappe.whitelist(allow_guest=True)
def delete_imam(name=None):
    if not name:
        return _error("Provide `name` to delete", 400, 400)
    try:
        # Check if document exists
        if not frappe.db.exists("Imam", name):
            return _error(f"Imam {name} not found", 404, 404)

        frappe.delete_doc("Imam", name, force=True)
        return _response({"name": name}, 200, "Imam deleted")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "delete_imam")
        return _error("Failed to delete Imam", 500, 500, {"description": str(e)})


# ——————————————————————————————————————————————————————————————
# Bulk Upload (Excel)
# ——————————————————————————————————————————————————————————————


@frappe.whitelist(allow_guest=True, methods=["POST"])
def bulk_upload_imams():
    """Upload an Excel with columns: faithful, mosque, date_appointed, …"""
    try:
        file = frappe.request.files.get("file")
        if not file:
            raise frappe.ValidationError("No file uploaded under 'file'")
        df = pd.read_excel(file)
        summary = {"total": len(df), "created": 0, "failed": 0}
        errors = []
        for idx, row in df.iterrows():
            data = row.to_dict()
            data.pop("name", None)
            try:
                frappe.get_doc({"doctype": "Imam", **data}).insert(
                    ignore_permissions=True
                )
                summary["created"] += 1
            except Exception as e:
                summary["failed"] += 1
                errors.append({"row": idx + 2, "error": str(e)})
        return _response(
            {"summary": summary, "errors": errors}, 200, "Bulk upload finished"
        )
    except frappe.ValidationError as ve:
        return _error(str(ve), 400, 400)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "bulk_upload_imams")
        return _error("Bulk upload failed", 500, 500, {"description": str(e)})


# ——————————————————————————————————————————————————————————————
# Reassign Imam (change mosque)
# ——————————————————————————————————————————————————————————————


@frappe.whitelist(allow_guest=True, methods=["POST"])
def reassign_imam():
    """
    POST JSON { data: { name, new_mosque, reason }}
    Will log in 'Imam Assignment Log' child table
    """
    data = frappe.local.request.get_json().get("data", {})
    name = data.get("name")
    new_mosque = data.get("new_mosque")
    if not name or not new_mosque:
        return _error("Missing `name` or `new_mosque`", 400, 400)
    try:
        imam = frappe.get_doc("Imam", name)
        old = imam.mosque
        imam.mosque = new_mosque
        imam.save(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Imam Assignment Log",
                "parent": imam.name,
                "parentfield": "assignment_logs",
                "parenttype": "Imam",
                "old_mosque": old,
                "new_mosque": new_mosque,
                "reason": data.get("reason"),
                "moved_by": frappe.session.user,
                "timestamp": now(),
            }
        ).insert(ignore_permissions=True)
        return _response(imam.as_dict(), 200, "Imam reassigned")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "reassign_imam")
        return _error("Failed to reassign Imam", 500, 500, {"description": str(e)})


def save_base64_file(data_url, doctype, docname):
    try:
        match = re.match(r"data:(.*?);base64,(.*)", data_url)
        if not match:
            raise ValueError("Invalid base64 format")

        mime_type, encoded = match.groups()
        ext = mime_type.split("/")[-1] or "bin"
        filedata = base64.b64decode(encoded)
        filename = f"imam_cert_{uuid.uuid4().hex[:8]}.{ext}"

        filepath = os.path.join(get_files_path(), filename)
        with open(filepath, "wb") as f:
            f.write(filedata)

        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": filename,
                "file_url": f"/files/{filename}",
                "is_private": 0,
                "attached_to_doctype": doctype,
                "attached_to_name": docname,
            }
        )
        file_doc.insert(ignore_permissions=True)

        return file_doc.file_url

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_base64_file")
        raise

