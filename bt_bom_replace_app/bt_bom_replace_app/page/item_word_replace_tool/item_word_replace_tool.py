# Copyright (c) 2026, BT BOM Replace App and contributors
# MIT License

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, parse_json

_SEARCH_LIMIT = 500
_SHOW_ALL_BATCH_SIZE = 5000
_ITEM_LIST_FIELDS = [
	"name",
	"item_name",
	"item_group",
	"custom_drawing_no",
	"custom_sf_code",
	"custom_revision",
	"custom_sheet",
	"custom_full_drawing_number_",
	"custom_parent_item_group",
]


def _normalize_search(text: str) -> str:
	return (text or "").strip()


def _apply_replace(value: str, search: str, replace: str) -> str:
	if not value or not search:
		return value
	return re.sub(re.escape(search), replace, value, flags=re.IGNORECASE)


def _normalize_replaced_value(value: str) -> str:
	"""Collapse redundant whitespace left after replace/remove."""
	text = cstr(value)
	if not text:
		return text
	return " ".join(text.split())


def _compute_new_values(
	current_name: str, current_code: str, search_text: str, replace_text: str
) -> tuple[str, str]:
	new_name = current_name
	new_code = current_code

	if _text_contains(current_name, search_text):
		new_name = _normalize_replaced_value(
			_apply_replace(current_name, search_text, replace_text)
		)

	if _text_contains(current_code, search_text):
		new_code = _normalize_replaced_value(
			_apply_replace(current_code, search_text, replace_text)
		)

	return new_name, new_code


def _like_pattern(text: str) -> str:
	"""Escape LIKE wildcards in user search text."""
	return (
		text.replace("\\", "\\\\")
		.replace("%", "\\%")
		.replace("_", "\\_")
	)


def _text_contains(haystack: str, needle: str) -> bool:
	"""True if `needle` appears in `haystack` (case-insensitive)."""
	if not needle:
		return False
	return needle.lower() in (haystack or "").lower()


def _item_matches_search(item: dict, search_text: str) -> bool:
	"""Item is included only when item_name or item code contains the full search text."""
	return _text_contains(item.get("item_name"), search_text) or _text_contains(
		item.get("name"), search_text
	)


def _match_rank(item_name: str, search: str) -> int:
	"""Sort key only: exact match first, then starts-with, then contains."""
	name = (item_name or "").strip().lower()
	q = search.lower()
	if name == q:
		return 0
	if name.startswith(q):
		return 1
	if q in name:
		return 2
	return 3


def _full_drawing_number(item: dict) -> str:
	"""Full drawing number from Item field or SF-drawing-revision/sheet pattern (Bartakke)."""
	stored = cstr(item.get("custom_full_drawing_number_") or "").strip()
	if stored:
		return stored

	sf = cstr(item.get("custom_sf_code") or "").strip()
	dn = cstr(item.get("custom_drawing_no") or "").strip()
	if not sf or not dn:
		return ""

	rev = cstr(item.get("custom_revision") or "").strip()
	sheet = cstr(item.get("custom_sheet") or "").strip()
	base = f"{sf}-{dn}-{rev}" if rev else f"{sf}-{dn}"
	return f"{base}/{sheet}" if sheet else base


def _item_row_dict(item: dict) -> dict:
	item_code = item.get("name")
	return {
		"item_code": item_code,
		"item_name": item.get("item_name") or item_code,
		"full_drawing_number": _full_drawing_number(item),
		"type": item.get("item_group") or "",
		"parent_item_group": item.get("custom_parent_item_group") or "",
	}


def _fetch_all_items(fields: list[str]) -> list[dict]:
	"""Load every active Item (no row cap) in batches."""
	candidates: list[dict] = []
	start = 0
	while True:
		chunk = frappe.get_all(
			"Item",
			filters={"disabled": 0},
			fields=fields,
			order_by="name asc",
			limit_start=start,
			limit_page_length=_SHOW_ALL_BATCH_SIZE,
		)
		if not chunk:
			break
		candidates.extend(chunk)
		if len(chunk) < _SHOW_ALL_BATCH_SIZE:
			break
		start += _SHOW_ALL_BATCH_SIZE
	return candidates


def _fetch_items(search_text: str = "", *, show_all: bool = False) -> list[dict]:
	"""All item groups; search mode returns only items whose name/code contains full search text."""
	meta = frappe.get_meta("Item")
	fields = [f for f in _ITEM_LIST_FIELDS if f == "name" or meta.has_field(f)]
	field_sql = ", ".join(f"`{f}`" for f in fields)

	if show_all:
		candidates = _fetch_all_items(fields)
	else:
		pattern = f"%{_like_pattern(search_text)}%"
		candidates = frappe.db.sql(
			f"""
			SELECT {field_sql}
			FROM `tabItem`
			WHERE disabled = 0
				AND (
					LOWER(item_name) LIKE LOWER(%(pattern)s)
					OR LOWER(name) LIKE LOWER(%(pattern)s)
				)
			ORDER BY modified DESC
			LIMIT %(limit)s
			""",
			{"pattern": pattern, "limit": _SEARCH_LIMIT * 2},
			as_dict=True,
		)
		candidates = [c for c in candidates if _item_matches_search(c, search_text)]
		candidates.sort(
			key=lambda c: (
				_match_rank(c.get("item_name") or "", search_text),
				(c.get("item_name") or "").lower(),
			)
		)
		candidates = candidates[:_SEARCH_LIMIT]

	return [_item_row_dict(dict(c)) for c in candidates]


@frappe.whitelist()
def search_items(search_text: str = "", show_all: int = 0):
	"""
	Search Items across all item groups.
	Returns only rows where item_name (or item code) contains the full search text.
	"""
	frappe.has_permission("Item", ptype="read", throw=True)
	search_text = _normalize_search(search_text)
	show_all = cint(show_all)

	if not search_text and not show_all:
		frappe.throw(_("Enter search text or click Show All"))

	rows = _fetch_items(search_text, show_all=bool(show_all))
	return {
		"search_text": search_text,
		"show_all": bool(show_all),
		"rows": rows,
		"count": len(rows),
	}


@frappe.whitelist()
def get_replace_preview(search_text: str, replace_text: str, item_codes=None):
	"""Preview item_name and item code changes for selected items."""
	search_text = _normalize_search(search_text)
	replace_text = replace_text if replace_text is not None else ""
	if not search_text:
		frappe.throw(_("Search text is required"))

	codes = _parse_item_codes(item_codes)
	if not codes:
		frappe.throw(_("Select at least one item"))

	preview_rows = []
	for code in codes:
		current_name = frappe.db.get_value("Item", code, "item_name") or ""
		current_code = code
		if not _text_contains(current_name, search_text) and not _text_contains(
			current_code, search_text
		):
			continue

		new_name, new_code = _compute_new_values(
			current_name, current_code, search_text, replace_text
		)
		if new_name == current_name and new_code == current_code:
			continue

		preview_rows.append(
			{
				"item_code": code,
				"before_name": current_name,
				"after_name": new_name,
				"before_code": current_code,
				"after_code": new_code,
			}
		)

	return {
		"search_text": search_text,
		"replace_text": replace_text,
		"row_count": len(preview_rows),
		"rows": preview_rows,
	}


@frappe.whitelist()
def replace_selected_items(search_text: str, replace_text: str, item_codes=None):
	"""Replace `search_text` with `replace_text` in item_name and item code for selected items."""
	search_text = _normalize_search(search_text)
	replace_text = replace_text if replace_text is not None else ""
	if not search_text:
		frappe.throw(_("Search text is required"))

	frappe.has_permission("Item", ptype="write", throw=True)
	codes = _parse_item_codes(item_codes)
	if not codes:
		frappe.throw(_("Select at least one item"))

	updated: list[str] = []
	skipped: list[dict] = []
	failed: list[dict] = []

	for item_code in sorted(set(codes)):
		try:
			result = _replace_item_name_and_code(item_code, search_text, replace_text)
			if result.get("status") == "updated":
				updated.append(result.get("item_code") or item_code)
			elif result.get("reason"):
				skipped.append({"item_code": item_code, "reason": result["reason"]})
		except Exception as exc:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Item Word Replace failed for {0}").format(item_code),
			)
			failed.append({"item_code": item_code, "reason": str(exc)})

	if not updated:
		_report_no_updates(skipped, failed)

	frappe.msgprint(
		_("Updated {0} item(s). Skipped {1}, failed {2}.").format(
			len(updated), len(skipped), len(failed)
		),
		indicator="green" if updated else "orange",
	)

	return {
		"search_text": search_text,
		"replace_text": replace_text,
		"updated_items": updated,
		"skipped": skipped,
		"failed": failed,
		"updated_count": len(updated),
	}


def _parse_item_codes(item_codes) -> list[str]:
	if item_codes is None or item_codes == "":
		return []
	if isinstance(item_codes, str):
		item_codes = parse_json(item_codes)
	if not isinstance(item_codes, list):
		return []
	return [str(c).strip() for c in item_codes if c and str(c).strip()]


def _report_no_updates(skipped: list[dict], failed: list[dict]) -> None:
	if failed:
		lines = [
			"{0}: {1}".format(f.get("item_code"), f.get("reason")) for f in failed[:15]
		]
		if len(failed) > 15:
			lines.append(_("...and {0} more failure(s)").format(len(failed) - 15))

		message = _("No items were updated.") + "<br><br>" + "<br>".join(
			frappe.utils.escape_html(line) for line in lines
		)
		if skipped:
			message += "<br><br>" + _("Skipped {0} item(s).").format(len(skipped))
		frappe.throw(message)

	if skipped:
		frappe.throw(_("No items were updated. Skipped {0} item(s).").format(len(skipped)))

	frappe.throw(_("No items were updated."))


def _replace_item_name_and_code(
	item_code: str, search_text: str, replace_text: str
) -> dict:
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))

	item = frappe.get_doc("Item", item_code)
	frappe.has_permission("Item", doc=item, ptype="write", throw=True)

	current_name = item.item_name or ""
	current_code = item.name

	if not _text_contains(current_name, search_text) and not _text_contains(
		current_code, search_text
	):
		return {"reason": _("Skipped: search text not found in item name or item code")}

	new_name, new_code = _compute_new_values(
		current_name, current_code, search_text, replace_text
	)

	if new_name == current_name and new_code == current_code:
		return {"reason": _("Skipped: no change after replace")}

	if new_code != current_code:
		if not new_code:
			new_code = current_code
		elif frappe.db.exists("Item", new_code):
			frappe.throw(_("Item {0} already exists").format(new_code))
		else:
			renamed_to = frappe.rename_doc(
				"Item",
				current_code,
				new_code,
				force=False,
				show_alert=False,
			)
			item = frappe.get_doc("Item", renamed_to)

	if new_name != (item.item_name or ""):
		item.item_name = new_name

	item.save(ignore_permissions=False)
	return {"status": "updated", "item_code": item.name}
