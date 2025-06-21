import frappe
from frappe import _
from frappe.utils import now, random_string, get_files_path
import uuid
from werkzeug.wrappers import Response
import json
import pandas as pd
import tempfile
from frappe.utils.file_manager import save_file
import base64
import os

@frappe.whitelist(allow_guest=True)
def get_faithfuls_by_mosque(mosque_id):
    return frappe.get_all("Faithful Profile", filters={"mosque": mosque_id}, fields=["name", "full_name", "phone", "email", "household"])

@frappe.whitelist(allow_guest=True)
def get_faithfuls_by_household(household_id):
    return frappe.get_all("Faithful Profile", filters={"household": household_id}, fields=["name", "full_name", "phone", "email", "mosque"])

@frappe.whitelist(allow_guest=True, methods=["POST"])
def bulk_upload_faithfuls():
    request_id = str(uuid.uuid4())
    timestamp = now()
    created = 0
    duplicates = 0
    failed = 0

    skipped_duplicates = []
    failed_rows = []
    failed_file_url = None

    try:
        file = frappe.request.files.get("file")
        if not file:
            raise frappe.ValidationError("No file uploaded under 'file' key")

        df = pd.read_excel(file)
        required_fields = ["full_name", "email"]

        for idx, row in df.iterrows():
            try:
                payload = row.to_dict()

                email = payload.get("email")
                full_name = payload.get("full_name")

                if not email or not full_name:
                    raise ValueError("Missing email or full_name")

                user_email = email.strip().lower()
                if frappe.db.exists("User", user_email):
                    duplicates += 1
                    skipped_duplicates.append({"row": idx + 2, "email": user_email, "reason": "Duplicate user"})
                    continue

                faithful_doc = frappe.new_doc("Faithful Profile")
                faithful_doc.update(payload)
                faithful_doc.insert(ignore_permissions=True)

                temp_password = random_string(12)
                user_doc = frappe.get_doc({
                    "doctype": "User",
                    "email": user_email,
                    "first_name": full_name,
                    "enabled": 1
                })
                user_doc.new_password = temp_password
                user_doc.flags.ignore_password_reset_email = True
                user_doc.insert(ignore_permissions=True)
                user_doc.add_roles("Customer")

                try:
                    user_doc.reset_password()
                except Exception:
                    frappe.log_error(frappe.get_traceback(), f"Failed to send reset password email for {user_email}")

                created += 1

            except Exception as e:
                failed += 1
                failed_rows.append({
                    "row": idx + 2,
                    "email": payload.get("email"),
                    "full_name": payload.get("full_name"),
                    "error": str(e)
                })

        if failed_rows:
            df_failed = pd.DataFrame(failed_rows)
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                df_failed.to_excel(tmp.name, index=False)
                tmp.seek(0)

        response = {
            "data": {
                "summary": {
                    "total_uploaded": len(df),
                    "created": created,
                    "duplicates_skipped": duplicates,
                    "failed": failed
                },
                "skipped_duplicates": skipped_duplicates,
                "failed_rows": failed_rows,
                "failed_file_url": failed_file_url
            },
            "status": "success",
            "message": f"{created} profiles created. {duplicates} duplicates skipped. {failed} failed."
        }

        return Response(json.dumps(response), status=200, content_type="application/json")

    except frappe.ValidationError as ve:
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Validation failed during file upload.",
            "errors": {"description": str(ve)},
            "meta": {"request_id": request_id, "timestamp": timestamp}
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Bulk Upload Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 500,
            "message": "Failed to process bulk upload.",
            "errors": {"description": str(e)},
            "meta": {"request_id": request_id, "timestamp": timestamp}
        }
        return Response(json.dumps(error), status=500, content_type="application/json")

@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_faithful():
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        data = frappe.local.request.get_json()
        if not data or "data" not in data:
            raise frappe.ValidationError("Missing 'data' object in payload.")

        payload = data["data"]

        email = payload.get("email")
        full_name = payload.get("full_name")
        if not email:
            raise frappe.ValidationError("Missing required field: 'email'")
        if not full_name:
            raise frappe.ValidationError("Missing required field: 'full_name'")

        faithful_doc = frappe.new_doc("Faithful Profile")
        file_fields = ['profile_image', 'national_id_document', 'special_needs_proof']
        file_payloads = {k: payload.pop(k, None) for k in file_fields}
        faithful_doc.update(payload)
        faithful_doc.insert(ignore_permissions=True)

        if file_payloads['profile_image']:
            file_url = save_base64_file(
                base64_data=file_payloads['profile_image'],
                file_name=f"{full_name}_profile_image.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=faithful_doc.name,
                is_private=0
            )
            faithful_doc.profile_image = file_url

        if file_payloads['national_id_document']:
            file_url = save_base64_file(
                base64_data=file_payloads['national_id_document'],
                file_name=f"{full_name}_national_id.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=faithful_doc.name,
                is_private=1
            )
            faithful_doc.national_id_document = file_url

        if file_payloads['special_needs_proof'] and payload.get('special_needs') == 'Yes':
            file_url = save_base64_file(
                base64_data=file_payloads['special_needs_proof'],
                file_name=f"{full_name}_special_needs_proof.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=faithful_doc.name,
                is_private=1
            )
            faithful_doc.special_needs_proof = file_url

        faithful_doc.save(ignore_permissions=True)

        mosque_name = None
        household_name = None

        if faithful_doc.mosque:
            mosque_name = frappe.db.get_value("Mosque", faithful_doc.mosque, "mosque_name") or faithful_doc.mosque

        if faithful_doc.household:
            household_name = frappe.db.get_value("Household", faithful_doc.household, "household_name") or faithful_doc.household

        user_email = email.strip().lower()
        if frappe.db.exists("User", user_email):
            raise frappe.DuplicateEntryError(f"User with email {user_email} already exists.")

        temp_password = random_string(12)
        user_doc = frappe.get_doc({
            "doctype": "User",
            "email": user_email,
            "first_name": full_name,
            "enabled": 1
        })
        user_doc.insert(ignore_permissions=True)
        user_doc.new_password = temp_password
        user_doc.flags.ignore_password_reset_email = True
        user_doc.save(ignore_permissions=True)
        user_doc.add_roles("Faithful User")

        try:
            user_doc.reset_password()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Failed to send Reset Password email")

        def safe_date(val):
            return val.isoformat() if hasattr(val, "isoformat") else val

        response_data = {
            "mosque_name": mosque_name,
            "household_name": household_name,
            **{k: safe_date(v) for k, v in faithful_doc.as_dict().items()},
            "user_created": user_email
        }

        response = {
            "data": response_data,
            "status": "success",
            "code": 201,
            "message": "Faithful profile registered and user account created. Check email to set password.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }

        return Response(json.dumps(response), status=201, content_type="application/json")

    except frappe.DuplicateEntryError as dup_err:
        frappe.log_error(frappe.get_traceback(), "Duplicate Faithful/User Registration")
        error = {
            "data": None,
            "status": "error",
            "code": 409,
            "message": _("Duplicate entry: ") + str(dup_err),
            "errors": {
                "description": str(dup_err)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=409, content_type="application/json")

    except frappe.ValidationError as e:
        frappe.log_error(frappe.get_traceback(), "Validation Failed during Faithful Registration")
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
        frappe.log_error(frappe.get_traceback(), "Faithful Registration & User Creation Failed")
        error = {
            "data": None,
            "status": "error",
            "code": 400,
            "message": "Failed to register faithful profile and create user.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_all_faithfuls():
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        raw_filters = dict(frappe.local.form_dict)
        filters = {k: v.strip() if isinstance(v, str) else v for k, v in raw_filters.items() if k not in ["cmd", "data"] and v}

        records = frappe.get_all(
            "Faithful Profile",
            filters=filters or None,
            fields=[
                "name", "full_name", "user_id", "phone", "gender", "mosque",
                "national_id_number", "marital_status", "occupation", "creation",
                "household", "profile_image", "national_id_document", "special_needs_proof"
            ],
            order_by="creation desc"
        )

        for r in records:
            if hasattr(r["creation"], "isoformat"):
                r["creation"] = r["creation"].isoformat()
            r["mosque_name"] = frappe.db.get_value("Mosque", r["mosque"], "mosque_name") or r["mosque"] if r.get("mosque") else None
            r["household_name"] = frappe.db.get_value("Household", r["household"], "household_name") or r["household"] if r.get("household") else None

        response = {
            "data": records,
            "status": "success",
            "code": 200,
            "message": "Faithful profiles retrieved successfully.",
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp,
                "filters_applied": filters
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
                "filters_applied": raw_filters,
                "request_id": request_id,
                "timestamp": timestamp
            }
        }
        return Response(json.dumps(error), status=400, content_type="application/json")

@frappe.whitelist(allow_guest=True)
def get_faithful(name=None, full_name=None):
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not name and not full_name:
            raise frappe.ValidationError("You must provide either 'name' or 'full_name'")

        if name:
            name = name.strip()

        if full_name:
            full_name = full_name.strip()
            records = frappe.get_all(
                "Faithful Profile",
                filters={"full_name": ["like", f"%{full_name}%"]},
                fields=["*"]
            )
            if not records:
                raise frappe.DoesNotExistError(f"No Faithful Profile found matching full_name '{full_name}'")

            for doc_dict in records:
                for key, value in doc_dict.items():
                    if hasattr(value, "isoformat"):
                        doc_dict[key] = value.isoformat()
                doc_dict["mosque_name"] = frappe.db.get_value("Mosque", doc_dict["mosque"], "mosque_name") or doc_dict["mosque"] if doc_dict.get("mosque") else None
                doc_dict["household_name"] = frappe.db.get_value("Household", doc_dict["household"], "household_name") or doc_dict["household"] if doc_dict.get("household") else None

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

        else:
            doc = frappe.get_doc("Faithful Profile", name)
            doc_dict = doc.as_dict()

            for key, value in doc_dict.items():
                if hasattr(value, "isoformat"):
                    doc_dict[key] = value.isoformat()
            doc_dict["mosque_name"] = frappe.db.get_value("Mosque", doc_dict["mosque"], "mosque_name") or doc_dict["mosque"] if doc_dict.get("mosque") else None
            doc_dict["household_name"] = frappe.db.get_value("Household", doc_dict["household"], "household_name") or doc_dict["household"] if doc_dict.get("household") else None

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

    except frappe.DoesNotExistError as e:
        error = {
            "data": None,
            "status": "error",
            "code": 404,
            "message": "Faithful profile not found.",
            "errors": {
                "description": str(e)
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
            "message": "Invalid request.",
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
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not name and not user_id:
            raise frappe.ValidationError("You must provide either 'name' or 'user_id'")

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

        doc = frappe.get_doc("Faithful Profile", name)
        file_fields = ['profile_image', 'national_id_document', 'special_needs_proof']
        file_payloads = {k: payload.pop(k, None) for k in file_fields}
        doc.update(payload)

        if file_payloads['profile_image']:
            file_url = save_base64_file(
                base64_data=file_payloads['profile_image'],
                file_name=f"{doc.full_name}_profile_image.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=doc.name,
                is_private=0
            )
            doc.profile_image = file_url

        if file_payloads['national_id_document']:
            file_url = save_base64_file(
                base64_data=file_payloads['national_id_document'],
                file_name=f"{doc.full_name}_national_id.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=doc.name,
                is_private=1
            )
            doc.national_id_document = file_url

        if file_payloads['special_needs_proof'] and payload.get('special_needs') == 'Yes':
            file_url = save_base64_file(
                base64_data=file_payloads['special_needs_proof'],
                file_name=f"{doc.full_name}_special_needs_proof.png",
                attached_to_doctype="Faithful Profile",
                attached_to_name=doc.name,
                is_private=1
            )
            doc.special_needs_proof = file_url
        elif payload.get('special_needs') != 'Yes':
            doc.special_needs_proof = None

        doc.save(ignore_permissions=True)

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

@frappe.whitelist(allow_guest=True, methods=["POST"])
def reassign_faithful(data=None):
    request_id = str(uuid.uuid4())
    timestamp = now()

    try:
        if not data:
            data = frappe.form_dict.get("data")

        if isinstance(data, str):
            data = frappe.parse_json(data)

        data = frappe._dict(data)

        if not data.get("new_mosque") and not data.get("new_household"):
            return Response(json.dumps({
                "data": None,
                "status": "error",
                "code": 400,
                "message": "Missing both new_mosque and new_household.",
                "errors": {
                    "description": "You must provide at least a new mosque or a new household."
                },
                "meta": {
                    "request_id": request_id,
                    "timestamp": timestamp
                }
            }), status=400, content_type="application/json")

        faithful = frappe.get_doc("Faithful Profile", data.faithful_id)

        old_mosque = faithful.mosque
        old_household = faithful.household

        if data.get("new_mosque"):
            faithful.mosque = data.new_mosque

        if data.get("new_household"):
            faithful.household = data.new_household

        faithful.save(ignore_permissions=True)

        frappe.get_doc({
            "doctype": "Faithful Movement Log",
            "faithful": faithful.name,
            "previous_mosque": old_mosque,
            "new_mosque": data.get("new_mosque", old_mosque),
            "previous_household": old_household,
            "new_household": data.get("new_household", old_household),
            "reason": data.reason,
            "moved_by": frappe.session.user,
            "timestamp": now()
        }).insert(ignore_permissions=True)

        updated_profile = faithful.as_dict()

        if faithful.mosque:
            updated_profile["mosque_info"] = {
                "name": faithful.mosque,
                "display_name": frappe.db.get_value("Mosque", faithful.mosque, "mosque_name")
            }

        if faithful.household:
            updated_profile["household_info"] = {
                "name": faithful.household,
                "display_name": frappe.db.get_value("Household", faithful.household, "household_name")
            }

        return Response(
            frappe.as_json({
                "data": updated_profile,
                "status": "success",
                "code": 200,
                "message": "Faithful reassigned successfully.",
                "meta": {
                    "request_id": request_id,
                    "timestamp": timestamp
                }
            }),
            status=200,
            content_type="application/json"
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Reassign Faithful Failed")
        return Response(json.dumps({
            "data": None,
            "status": "error",
            "code": 500,
            "message": "Failed to reassign faithful.",
            "errors": {
                "description": str(e)
            },
            "meta": {
                "request_id": request_id,
                "timestamp": timestamp
            }
        }), status=500, content_type="application/json")

def save_base64_file(base64_data, file_name, attached_to_doctype, attached_to_name, is_private=0):
    try:
        if ';base64,' not in base64_data:
            raise frappe.ValidationError("Invalid Base64 data format")

        header, base64_string = base64_data.split(';base64,')
        mime_type = header.split(':')[1]
        allowed_mime_types = ['image/png', 'image/jpeg', 'application/pdf']
        if mime_type not in allowed_mime_types:
            raise frappe.ValidationError(f"Unsupported file type: {mime_type}")

        file_data = base64.b64decode(base64_string)
        max_file_size = 5 * 1024 * 1024
        if len(file_data) > max_file_size:
            raise frappe.ValidationError("File size exceeds 5MB limit")

        base_name, ext = os.path.splitext(file_name)
        unique_file_name = f"{base_name}_{frappe.generate_hash(length=10)}.{ext.lstrip('.') or 'png'}"

        folder_path = get_files_path() if not is_private else frappe.get_site_path('private', 'files')
        file_path = os.path.join(folder_path, unique_file_name)

        os.makedirs(folder_path, exist_ok=True)

        with open(file_path, 'wb') as f:
            f.write(file_data)

        file_doc = frappe.get_doc({
            'doctype': 'File',
            'file_name': unique_file_name,
            'file_url': f'/files/{unique_file_name}' if not is_private else f'/private/files/{unique_file_name}',
            'is_private': is_private,
            'content': None,
            'attached_to_doctype': attached_to_doctype,
            'attached_to_name': attached_to_name
        })
        file_doc.insert(ignore_permissions=True)

        return file_doc.file_url
    except Exception as e:
        frappe.log_error(f"Error saving Base64 file: {str(e)}")
        raise frappe.ValidationError(f"Failed to save file: {str(e)}")