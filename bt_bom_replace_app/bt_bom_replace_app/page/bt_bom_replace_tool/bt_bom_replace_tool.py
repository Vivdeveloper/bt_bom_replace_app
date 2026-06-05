# Copyright (c) 2026, BT BOM Replace App and contributors
# MIT License

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, parse_json

# Custom BOM child tables (same contract as bt_bom / bartakke_erp).
_ALL_CUSTOM_TABLES: tuple[tuple[str, str, str], ...] = (
	("custom_bom_assembly_items", "BOM Assembly Item", "BOM Item"),
	("custom_bom_sub_assembly_items", "BOM Sub Assembly Item", "Sub Assembly"),
	("custom_bom_hardware_items", "BOM Hardware Item", "Hardware (RM)"),
)

_PARENTFIELD_TO_CHILD_DT: dict[str, str] = {row[0]: row[1] for row in _ALL_CUSTOM_TABLES}

# Item Group → BOM child table (material_key). Standard / Specialized / Cutout → BOM Item table.
_ITEM_GROUP_TO_MATERIAL_KEY: dict[str, str] = {
	"standard item": "assembly",
	"specialised item": "assembly",
	"specialized item": "assembly",
	"cutout item": "assembly",
	"cut-out item": "assembly",
	"cut out item": "assembly",
	"hardware": "hardware",
	"hardware (rm)": "hardware",
	"hardware(rm)": "hardware",
	"hardware - ss": "hardware",
	"hardware - ms": "hardware",
	"hardware-ms": "hardware",
	"hardware-ss 304": "hardware",
	"hardware-ss 316": "hardware",
	"hardware-brass": "hardware",
	"hardware-aluminum": "hardware",
	"hardware-plastic": "hardware",
	"other hardware": "hardware",
	"assembly": "sub_assembly",
	"sub assembly": "sub_assembly",
	"sub-assembly": "sub_assembly",
	"general assembly": "sub_assembly",
	"custom products": "sub_assembly",
}

# Extra aliases (prefixes, legacy labels) after exact Item Group lookup.
_ITEM_GROUP_CANONICAL_ALIASES: dict[str, str] = {
	"sba": "sub_assembly",
	"ass": "sub_assembly",
	"ga": "sub_assembly",
	"rm": "hardware",
	"raw material": "hardware",
	"bom item": "assembly",
	"bom assembly items": "sub_assembly",
	"bom hardware item": "hardware",
}

_SECTION_CANONICAL: dict[str, str] = {
	"BOM Item": "assembly",
	"Assembly": "assembly",
	"Sub Assembly": "sub_assembly",
	"BOM Assembly Items": "sub_assembly",
	"Hardware (RM)": "hardware",
	"Hardware": "hardware",
}

_CANONICAL_TO_PARENTFIELDS: dict[str, tuple[str, ...]] = {
	"assembly": ("custom_bom_assembly_items",),
	"sub_assembly": ("custom_bom_sub_assembly_items",),
	"hardware": ("custom_bom_hardware_items",),
}


@frappe.whitelist()
def find_bom_links(item_code: str, search_type: str = "all"):
	"""Find an item at every BOM level: direct material lines + parent BOM chain to FG."""
	item_code = (item_code or "").strip()
	if not item_code:
		frappe.throw(_("Item is required"))
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))

	frappe.has_permission("BOM", ptype="read", throw=True)

	material_key = _get_material_key(item_code)

	direct = _find_direct_usages_everywhere(item_code, material_key)
	rows = _expand_with_bom_paths(direct)
	rows.sort(
		key=lambda r: (
			cint(r.get("bom_depth") or 0),
			r.get("level") != "usage",
			r.get("root_bom") or "",
			r.get("bom") or "",
		)
	)

	usage_count = sum(1 for r in rows if r.get("level") == "usage")
	parent_count = len(rows) - usage_count

	return {
		"item_code": item_code,
		"item_name": _get_item_name(item_code),
		"item_drawing_no": _get_item_drawing(item_code),
		"custom_parent_item_group": _get_custom_parent_item_group(item_code),
		"item_group": _get_item_group(item_code),
		"material_key": material_key,
		"item_default_bom": frappe.db.get_value("Item", item_code, "default_bom"),
		"item_image": _get_item_image(item_code),
		"rows": rows,
		"count": len(rows),
		"usage_count": usage_count,
		"parent_count": parent_count,
	}


def _canonical_item_group(item_group: str) -> str:
	"""Normalize Item Group / BOM section labels to assembly | sub_assembly | hardware."""
	key = cstr(item_group or "").strip().lower()
	if not key:
		return ""
	if key in _ITEM_GROUP_TO_MATERIAL_KEY:
		return _ITEM_GROUP_TO_MATERIAL_KEY[key]
	if key.startswith("hardware"):
		return "hardware"
	if key in _ITEM_GROUP_CANONICAL_ALIASES:
		return _ITEM_GROUP_CANONICAL_ALIASES[key]
	section_key = cstr(item_group or "").strip()
	if section_key in _SECTION_CANONICAL:
		return _SECTION_CANONICAL[section_key]
	return key.replace(" ", "_")


def _item_groups_match(group_a: str, group_b: str) -> bool:
	return _canonical_item_group(group_a) == _canonical_item_group(group_b)


def _get_item_group(item_code: str) -> str:
	return cstr(frappe.db.get_value("Item", item_code, "item_group") or "").strip()


def _get_custom_parent_item_group(item_code: str) -> str:
	meta = frappe.get_meta("Item")
	if not meta.has_field("custom_parent_item_group"):
		return ""
	return cstr(frappe.db.get_value("Item", item_code, "custom_parent_item_group") or "").strip()


def _get_material_key(item_code: str) -> str:
	"""Resolve BOM child table from Item.item_group (assembly | sub_assembly | hardware)."""
	key = _canonical_item_group(_get_item_group(item_code))
	if key in _CANONICAL_TO_PARENTFIELDS:
		return key

	# Same rules as the BOM form: Parent Item Group when item_group is not in the map.
	parent_grp = _get_custom_parent_item_group(item_code)
	if parent_grp == "Assembly Item":
		return "assembly"
	if parent_grp == "Products":
		return "sub_assembly"
	if parent_grp:
		return "hardware"

	code = cstr(item_code or "").strip().upper()
	if code.startswith("(SBA)"):
		return "sub_assembly"
	if code.startswith("(ASS)") or code.startswith("(GA)"):
		return "sub_assembly"
	return ""


def _section_label_for_material_key(material_key: str) -> str:
	return {
		"assembly": "BOM Item",
		"sub_assembly": "BOM Assembly Items",
		"hardware": "BOM Hardware Item",
	}.get(material_key, material_key)


def _allowed_parentfields_for_material_key(material_key: str) -> tuple[str, ...]:
	return _CANONICAL_TO_PARENTFIELDS.get(material_key, ())


def _custom_tables_for_material_key(material_key: str) -> list[tuple[str, str, str]]:
	allowed = set(_allowed_parentfields_for_material_key(material_key))
	if not allowed:
		return []
	return [row for row in _ALL_CUSTOM_TABLES if row[0] in allowed]


def _parentfields_for_item_on_bom(bom_name: str, item_code: str, material_key: str) -> tuple[str, ...]:
	"""Tables on this BOM that contain `item_code`; prefer the item's BOM section."""
	found = _parentfields_for_item_on_bom_all(bom_name, item_code)
	if not found:
		allowed = _allowed_parentfields_for_material_key(material_key)
		return allowed
	allowed = set(_allowed_parentfields_for_material_key(material_key))
	matched = [p for p in found if p in allowed]
	return tuple(matched or found)


def _parentfields_for_item_on_bom_all(bom_name: str, item_code: str) -> tuple[str, ...]:
	"""Every custom BOM table on this BOM that contains `item_code`."""
	found: list[str] = []
	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(child_dt):
			continue
		if frappe.db.exists(
			child_dt,
			{
				"parent": bom_name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": item_code,
			},
		):
			found.append(parentfield)
	return tuple(found)


def _find_direct_usages_everywhere(item_code: str, material_key: str) -> list[dict]:
	"""BOMs where `item_code` is a material line (search all custom tables where it exists)."""
	rows: list[dict] = []
	seen: set[tuple] = set()
	item_drawing = _get_item_drawing(item_code)

	# Discover usages in every custom table that contains this item (not only Parent Item Group table).
	for parentfield, child_dt, section_label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(child_dt):
			continue
		if not frappe.db.exists(
			child_dt,
			{"parenttype": "BOM", "parentfield": parentfield, "item_code": item_code},
		):
			continue
		rows.extend(
			_collect_custom_table_rows(
				item_code,
				parentfield,
				child_dt,
				section_label,
				seen,
				item_drawing,
			)
		)

	rows.extend(_collect_bom_item_rows(item_code, seen, item_drawing))
	return rows


def _bom_list_fields() -> list[str]:
	fields = ["name", "item", "item_name", "quantity"]
	if frappe.get_meta("BOM").has_field("custom_drawing_number"):
		fields.append("custom_drawing_number")
	return fields


def _bom_drawing(bom_row: dict | frappe._dict) -> str:
	return cstr(bom_row.get("custom_drawing_number") or "").strip()


def _line_drawing(line: dict, fallback: str = "") -> str:
	drawing = cstr(line.get("custom_drawing_number") or "").strip()
	return drawing or fallback


def _get_item_name(item_code: str) -> str:
	return cstr(frappe.db.get_value("Item", item_code, "item_name") or "").strip()


def _get_item_drawing(item_code: str) -> str:
	"""Drawing number from Item (site may use custom_drawing_number, custom_drawing_no, etc.)."""
	meta = frappe.get_meta("Item")
	fieldnames = (
		"custom_drawing_number",
		"custom_full_drawing_number_",
		"custom_drawing_no",
		"drawing_no",
	)
	for fieldname in fieldnames:
		if meta.has_field(fieldname):
			val = cstr(frappe.db.get_value("Item", item_code, fieldname) or "").strip()
			if val:
				return val
	return ""


def _get_item_image(item_code: str) -> str:
	"""Item image (same source as BOM form `image` when production item is set)."""
	if not item_code:
		return ""
	meta = frappe.get_meta("Item")
	if not meta.has_field("image"):
		return ""
	return cstr(frappe.db.get_value("Item", item_code, "image") or "").strip()


def _is_bom_production_item(bom_name: str, item_code: str) -> bool:
	"""True when `item_code` is the finished good on this BOM (header `item`), not a material line."""
	if not bom_name or not item_code:
		return False
	return cstr(frappe.db.get_value("BOM", bom_name, "item") or "").strip() == item_code


def _item_exists_on_bom_custom_tables(bom_name: str, item_code: str) -> bool:
	"""True if `item_code` is on any custom BOM child table for this BOM."""
	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(child_dt):
			continue
		if frappe.db.exists(
			child_dt,
			{
				"parent": bom_name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": item_code,
			},
		):
			return True
	return False


def _append_usage_row(
	rows: list[dict],
	seen: set[tuple],
	*,
	bom: str,
	bom_meta: dict | frappe._dict,
	section: str,
	qty: float,
	linked_bom: str = "",
	source: str = "",
	child_row: str = "",
	custom_drawing_number: str = "",
) -> None:
	key = (bom, section, child_row, source)
	if key in seen:
		return
	seen.add(key)
	drawing = custom_drawing_number or _bom_drawing(bom_meta)
	rows.append(
		{
			"bom": bom,
			"bom_item": bom_meta.get("item"),
			"bom_item_name": bom_meta.get("item_name"),
			"custom_drawing_number": drawing,
			"section": section,
			"qty": qty,
			"linked_bom": linked_bom or "",
			"level": "usage",
			"bom_depth": 0,
			"bom_path": bom,
			"root_bom": bom,
			"via_bom": "",
			"child_row": child_row,
			"source": source,
		}
	)


def _bom_meta_map(bom_names: list[str]) -> dict[str, dict]:
	if not bom_names:
		return {}
	return {
		b.name: b
		for b in frappe.get_all(
			"BOM",
			filters={"name": ("in", bom_names)},
			fields=_bom_list_fields(),
		)
	}


def _collect_custom_table_rows(
	item_code: str,
	parentfield: str,
	child_dt: str,
	section_label: str,
	seen: set[tuple],
	item_drawing: str = "",
) -> list[dict]:
	meta = frappe.get_meta(child_dt)
	fields = ["name", "parent", "item_code", "qty"]
	if meta.has_field("bom_no"):
		fields.append("bom_no")
	if meta.has_field("custom_drawing_number"):
		fields.append("custom_drawing_number")

	lines = frappe.get_all(
		child_dt,
		filters={
			"parenttype": "BOM",
			"parentfield": parentfield,
			"item_code": item_code,
		},
		fields=fields,
		order_by="parent asc, idx asc",
	)
	if not lines:
		return []

	bom_meta = _bom_meta_map(list({ln.parent for ln in lines}))
	default_bom = frappe.db.get_value("Item", item_code, "default_bom") or ""
	out: list[dict] = []

	for ln in lines:
		bom_name = ln.parent
		if _is_bom_production_item(bom_name, item_code):
			continue
		bom = bom_meta.get(bom_name) or {}
		linked = (ln.get("bom_no") or "").strip() or default_bom
		_append_usage_row(
			out,
			seen,
			bom=bom_name,
			bom_meta=bom,
			section=section_label,
			qty=flt(ln.get("qty")),
			linked_bom=linked,
			source=parentfield,
			child_row=ln.name,
			custom_drawing_number=_bom_drawing(bom),
		)
	return out


def _collect_bom_item_rows(
	item_code: str, seen: set[tuple], item_drawing: str = ""
) -> list[dict]:
	item_meta = frappe.get_meta("BOM Item")
	fields = ["name", "parent", "qty", "bom_no", "custom_item_group"]
	if item_meta.has_field("custom_drawing_number"):
		fields.append("custom_drawing_number")

	lines = frappe.get_all(
		"BOM Item",
		filters={
			"item_code": item_code,
			"parenttype": "BOM",
			"docstatus": ("!=", 2),
		},
		fields=fields,
		order_by="parent asc, idx asc",
	)
	if not lines:
		return []

	bom_meta = _bom_meta_map(list({ln.parent for ln in lines}))
	default_bom = frappe.db.get_value("Item", item_code, "default_bom") or ""
	out: list[dict] = []

	for ln in lines:
		bom_name = ln.parent
		if _is_bom_production_item(bom_name, item_code):
			continue
		if _item_exists_on_bom_custom_tables(bom_name, item_code):
			continue
		bom = bom_meta.get(bom_name) or {}
		linked = (ln.get("bom_no") or "").strip() or default_bom
		line_group = (ln.get("custom_item_group") or "").strip()
		section = line_group or _("BOM Item")
		_append_usage_row(
			out,
			seen,
			bom=bom_name,
			bom_meta=bom,
			section=section,
			qty=flt(ln.get("qty")),
			linked_bom=linked,
			source="bom_item",
			child_row=ln.name,
			custom_drawing_number=_bom_drawing(bom),
		)
	return out


def _expand_with_bom_paths(direct_rows: list[dict]) -> list[dict]:
	"""For each direct usage BOM, add parent BOM rows up to every FG root with path."""
	out: list[dict] = list(direct_rows)
	seen_parent: set[tuple] = set()

	for row in direct_rows:
		usage_bom = row.get("bom")
		if not usage_bom:
			continue

		for path in _all_ancestor_paths(usage_bom):
			# path[0] = top FG root, path[-1] = BOM where item is used
			if len(path) < 2:
				continue

			root_bom = path[0]
			for depth in range(1, len(path)):
				ancestor = path[-(depth + 1)]
				key = (ancestor, usage_bom, depth)
				if key in seen_parent:
					continue
				seen_parent.add(key)

				meta = frappe.db.get_value(
					"BOM",
					ancestor,
					_bom_list_fields(),
					as_dict=True,
				) or {}
				chain = path[-(depth + 1) :]
				path_str = " > ".join(chain)
				child_bom = path[-depth] if depth < len(path) - 1 else usage_bom

				out.append(
					{
						"bom": ancestor,
						"bom_item": meta.get("item"),
						"bom_item_name": meta.get("item_name"),
						"custom_drawing_number": _bom_drawing(meta),
						"section": _("Parent BOM"),
						"qty": flt(meta.get("quantity")),
						"linked_bom": child_bom,
						"level": "parent",
						"bom_depth": depth,
						"bom_path": path_str,
						"root_bom": root_bom,
						"via_bom": usage_bom,
						"child_row": "",
						"source": "ancestor",
					}
				)

	return out


def _all_ancestor_paths(bom_name: str) -> list[list[str]]:
	"""Every path from `bom_name` up to FG root BOMs (handles multiple parents)."""
	paths: list[list[str]] = []
	_walk_ancestor_paths(bom_name, [bom_name], paths, set())
	return paths


def _walk_ancestor_paths(
	current: str,
	path: list[str],
	all_paths: list[list[str]],
	visited: set[str],
) -> None:
	parents = _get_parent_boms(current)
	if not parents:
		all_paths.append(list(path))
		return

	for parent in parents:
		if parent in visited or parent in path:
			all_paths.append(list(path))
			continue
		_walk_ancestor_paths(parent, [parent, *path], all_paths, visited | {parent})


def _get_parent_boms(bom_name: str) -> list[str]:
	bom_item = frappe.qb.DocType("BOM Item")
	return (
		frappe.qb.from_(bom_item)
		.select(bom_item.parent)
		.distinct()
		.where(
			(bom_item.bom_no == bom_name)
			& (bom_item.docstatus < 2)
			& (bom_item.parenttype == "BOM")
		)
		.run(pluck=True)
	)


@frappe.whitelist()
def get_item_display_details(item_code: str) -> dict:
	"""Item Name and Drawing No for desk page read-only fields."""
	item_code = (item_code or "").strip()
	if not item_code:
		return {"item_name": "", "item_drawing_no": ""}
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))
	return {
		"item_name": _get_item_name(item_code),
		"item_drawing_no": _get_item_drawing(item_code),
	}


@frappe.whitelist()
def get_replace_preview(current_item: str, new_item: str, bom_list=None) -> dict:
	"""Count BOMs and material lines that will be updated."""
	current_item, new_item, material_key = _validate_replace_items(current_item, new_item)
	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item, material_key)
	bom_names = _filter_boms_for_replace(all_boms, selected_boms)
	line_count = _line_count_for_boms(current_item, bom_names, material_key)
	return {
		"current_item": current_item,
		"new_item": new_item,
		"custom_parent_item_group": _get_custom_parent_item_group(current_item),
		"item_group": _get_item_group(current_item),
		"material_key": material_key,
		"bom_count": len(bom_names),
		"line_count": line_count,
		"selected_only": bool(selected_boms),
	}


@frappe.whitelist()
def replace_item_in_all_boms(current_item: str, new_item: str, bom_list=None) -> dict:
	"""Replace `current_item` with `new_item` on BOM material lines (all or selected BOMs)."""
	current_item, new_item, material_key = _validate_replace_items(current_item, new_item)
	frappe.has_permission("BOM", ptype="write", throw=True)

	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item, material_key)
	bom_names = _filter_boms_for_replace(all_boms, selected_boms)
	if not bom_names:
		frappe.throw(_("No BOM material lines found for item {0}").format(current_item))

	new_item_name = frappe.db.get_value("Item", new_item, "item_name") or ""
	new_default_bom = frappe.db.get_value("Item", new_item, "default_bom") or ""

	updated: list[str] = []
	skipped: list[dict] = []
	failed: list[dict] = []

	for bom_name in sorted(bom_names):
		try:
			result = _replace_item_in_single_bom(
				bom_name,
				current_item,
				new_item,
				material_key=material_key,
				new_item_name=new_item_name,
				new_default_bom=new_default_bom,
			)
			if result == "updated":
				updated.append(bom_name)
			elif result:
				skipped.append({"bom": bom_name, "reason": result})
		except Exception as exc:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("BOM Replace failed for {0}").format(bom_name),
			)
			failed.append({"bom": bom_name, "reason": str(exc)})

	if not updated and not skipped:
		frappe.throw(_("No BOMs were updated."))

	new_key = _get_material_key(new_item)
	section = _section_label_for_material_key(material_key)
	if new_key and new_key != material_key:
		section = f"{section} → {_section_label_for_material_key(new_key)}"

	return {
		"current_item": current_item,
		"new_item": new_item,
		"section": section,
		"updated_boms": updated,
		"skipped": skipped,
		"failed": failed,
		"updated_count": len(updated),
		"skipped_count": len(skipped),
		"failed_count": len(failed),
		"selected_only": bool(selected_boms),
	}


@frappe.whitelist()
def get_remove_preview(current_item: str, bom_list=None) -> dict:
	"""Count BOMs and material lines that will be removed."""
	current_item = _validate_remove_item(current_item)
	material_key = _get_material_key(current_item) or ""
	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item, material_key)
	bom_names = _filter_boms_for_replace(all_boms, selected_boms)
	line_count = _line_count_for_boms(current_item, bom_names, material_key)
	return {
		"current_item": current_item,
		"custom_parent_item_group": _get_custom_parent_item_group(current_item),
		"item_group": _get_item_group(current_item),
		"bom_count": len(bom_names),
		"line_count": line_count,
		"selected_only": bool(selected_boms),
	}


@frappe.whitelist()
def remove_item_from_selected_boms(current_item: str, bom_list=None) -> dict:
	"""Remove `current_item` from BOM material lines (selected BOMs only)."""
	current_item = _validate_remove_item(current_item)
	frappe.has_permission("BOM", ptype="write", throw=True)

	material_key = _get_material_key(current_item) or ""
	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item, material_key)
	bom_names = _filter_boms_for_replace(all_boms, selected_boms)
	if not bom_names:
		frappe.throw(_("No BOM material lines found for item {0}").format(current_item))

	updated: list[str] = []
	skipped: list[dict] = []
	failed: list[dict] = []

	for bom_name in sorted(bom_names):
		try:
			result = _remove_item_from_single_bom(bom_name, current_item)
			if result == "updated":
				updated.append(bom_name)
			elif result:
				skipped.append({"bom": bom_name, "reason": result})
		except Exception as exc:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("BOM Remove failed for {0}").format(bom_name),
			)
			failed.append({"bom": bom_name, "reason": str(exc)})

	if not updated and not skipped:
		frappe.throw(_("No BOMs were updated."))

	return {
		"current_item": current_item,
		"updated_boms": updated,
		"skipped": skipped,
		"failed": failed,
		"updated_count": len(updated),
		"skipped_count": len(skipped),
		"failed_count": len(failed),
		"selected_only": bool(selected_boms),
	}


def _parse_bom_list(bom_list) -> list[str] | None:
	"""Optional list of BOM names from the desk page (selected rows)."""
	if bom_list is None or bom_list == "":
		return None
	if isinstance(bom_list, str):
		bom_list = parse_json(bom_list)
	if not isinstance(bom_list, list):
		return None
	return [str(b).strip() for b in bom_list if b and str(b).strip()]


def _filter_boms_for_replace(all_boms: list[str], selected_boms: list[str] | None) -> list[str]:
	if not selected_boms:
		return all_boms
	allowed = set(all_boms)
	chosen = [b for b in selected_boms if b in allowed]
	if not chosen:
		frappe.throw(_("None of the selected BOMs contain this item as a material line"))
	return chosen


def _line_count_for_boms(item_code: str, bom_names: list[str], material_key: str) -> int:
	if not bom_names:
		return 0
	count = 0
	for parentfield in _parentfields_for_item_on_boms(item_code, bom_names, material_key):
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt or not frappe.db.table_exists(child_dt):
			continue
		count += frappe.db.count(
			child_dt,
			{
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": item_code,
				"parent": ("in", bom_names),
			},
		)
	return count


def _parentfields_for_item_on_boms(
	item_code: str, bom_names: list[str], material_key: str
) -> tuple[str, ...]:
	"""Union of child tables that contain the item on the given BOMs (for replace counts)."""
	found: set[str] = set()
	for bom_name in bom_names:
		for parentfield in _parentfields_for_item_on_bom_all(bom_name, item_code):
			found.add(parentfield)
	if not found:
		for bom_name in bom_names:
			for parentfield in _parentfields_for_item_on_bom(bom_name, item_code, material_key):
				found.add(parentfield)
	return tuple(found)


def _validate_remove_item(current_item: str) -> str:
	current_item = (current_item or "").strip()
	if not current_item:
		frappe.throw(_("Item is required"))
	if not frappe.db.exists("Item", current_item):
		frappe.throw(_("Item {0} not found").format(current_item))
	return current_item


def _validate_replace_items(current_item: str, new_item: str) -> tuple[str, str, str]:
	current_item = (current_item or "").strip()
	new_item = (new_item or "").strip()
	if not current_item or not new_item:
		frappe.throw(_("Current item and replacement item are required"))
	if current_item == new_item:
		frappe.throw(_("Current item and replacement item cannot be the same"))
	for code, label in ((current_item, _("Current item")), (new_item, _("Replacement item"))):
		if not frappe.db.exists("Item", code):
			frappe.throw(_("{0} {1} not found").format(label, code))

	material_key = _get_material_key(current_item)
	if not material_key:
		frappe.throw(
			_("Could not determine BOM table for item {0} from Item Group").format(current_item)
		)
	if not _get_material_key(new_item):
		frappe.throw(
			_("Could not determine BOM table for replacement item {0} from Item Group").format(new_item)
		)
	return current_item, new_item, material_key


def _boms_with_material_usage(item_code: str, material_key: str) -> tuple[list[str], int]:
	"""BOMs where item is a material line (any custom table; replace uses Parent Item Group tables)."""
	bom_set: set[str] = set()
	line_count = 0

	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(child_dt):
			continue
		rows = frappe.get_all(
			child_dt,
			filters={
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": item_code,
			},
			fields=["parent", "name"],
		)
		for row in rows:
			bom_set.add(row.parent)
			line_count += 1

	for row in frappe.get_all(
		"BOM Item",
		filters={"item_code": item_code, "parenttype": "BOM", "docstatus": ("!=", 2)},
		fields=["parent", "name"],
	):
		if row.parent not in bom_set:
			bom_set.add(row.parent)
			line_count += 1

	material_boms = [
		b
		for b in bom_set
		if frappe.db.get_value("BOM", b, "item") != item_code
		and frappe.db.get_value("BOM", b, "docstatus") != 2
	]
	return material_boms, line_count


def _replace_item_in_single_bom(
	bom_name: str,
	current_item: str,
	new_item: str,
	*,
	material_key: str,
	new_item_name: str,
	new_default_bom: str,
) -> str | None:
	bom = frappe.get_doc("BOM", bom_name)
	frappe.has_permission("BOM", doc=bom, ptype="write", throw=True)

	if bom.item == current_item:
		return _("Skipped: item is the finished good on this BOM")

	new_key = _get_material_key(new_item)
	if _new_item_would_duplicate(bom, new_item, current_item, material_key, new_key):
		return _("Skipped: replacement item already exists on this BOM")

	source_parentfields = _parentfields_for_item_on_bom_all(bom.name, current_item)
	if not source_parentfields:
		source_parentfields = _parentfields_for_item_on_bom(bom.name, current_item, material_key)

	target_parentfields = _allowed_parentfields_for_material_key(new_key)
	if not target_parentfields:
		return _("Skipped: could not determine target BOM table for replacement item")

	if material_key != new_key:
		changed = _move_item_cross_table_db(
			bom.name,
			current_item,
			new_item,
			source_parentfields=source_parentfields,
			target_parentfield=target_parentfields[0],
			new_item_name=new_item_name,
			new_default_bom=new_default_bom,
		)
	else:
		parentfields = tuple(p for p in source_parentfields if p in target_parentfields) or source_parentfields
		changed = _replace_in_custom_tables_db(
			bom.name,
			current_item,
			new_item,
			parentfields=parentfields,
			new_item_name=new_item_name,
			new_default_bom=new_default_bom,
		)

		if not changed and _ensure_current_item_in_custom_tables(bom, current_item, material_key):
			_save_bom_after_replace(bom)
			source_parentfields = _parentfields_for_item_on_bom_all(bom.name, current_item)
			parentfields = tuple(p for p in source_parentfields if p in target_parentfields) or source_parentfields
			changed = _replace_in_custom_tables_db(
				bom.name,
				current_item,
				new_item,
				parentfields=parentfields,
				new_item_name=new_item_name,
				new_default_bom=new_default_bom,
			)

		if not changed:
			if _replace_in_custom_tables(
				bom,
				current_item,
				new_item,
				parentfields=parentfields,
				new_item_name=new_item_name,
				new_default_bom=new_default_bom,
			):
				changed = _persist_custom_tables_from_doc(
					bom,
					current_item,
					new_item,
					parentfields=parentfields,
					new_item_name=new_item_name,
					new_default_bom=new_default_bom,
				)

	if not changed:
		section = _section_label_for_material_key(material_key)
		return _(
			"Skipped: {0} not found in {1} on this BOM (check BOM Item / BOM Assembly Items / Hardware tables)"
		).format(current_item, section)

	bom = frappe.get_doc("BOM", bom_name)
	_sync_bom_items_if_available(bom)
	_finalize_bom_for_save(bom)
	_save_bom_after_replace(bom)
	return "updated"


def _new_item_would_duplicate(
	bom, new_item: str, current_item: str, material_key: str, new_key: str | None = None
) -> bool:
	"""True if replacement would duplicate `new_item` on the target BOM table(s)."""
	new_key = new_key or _get_material_key(new_item)
	if material_key != new_key:
		for parentfield in _allowed_parentfields_for_material_key(new_key):
			for row in bom.get(parentfield) or []:
				if row.item_code == new_item:
					return True
		return False

	seen: set[str] = set()
	for parentfield in _parentfields_for_item_on_bom(bom.name, current_item, material_key):
		for row in bom.get(parentfield) or []:
			code = new_item if row.item_code == current_item else row.item_code
			if not code:
				continue
			if code in seen:
				return True
			seen.add(code)
	return False


def _replace_in_custom_tables(
	bom,
	current_item: str,
	new_item: str,
	*,
	parentfields: tuple[str, ...],
	new_item_name: str,
	new_default_bom: str,
) -> bool:
	changed = False
	for parentfield in parentfields:
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt:
			continue
		meta = frappe.get_meta(child_dt)
		for row in bom.get(parentfield) or []:
			if row.item_code != current_item:
				continue
			row.item_code = new_item
			if meta.has_field("item_name"):
				row.item_name = new_item_name
			if meta.has_field("bom_no"):
				row.bom_no = new_default_bom or ""
			changed = True
	return changed


def _replace_in_custom_tables_db(
	bom_name: str,
	current_item: str,
	new_item: str,
	*,
	parentfields: tuple[str, ...],
	new_item_name: str,
	new_default_bom: str,
) -> bool:
	"""Update custom child rows in the database (source of truth for bt_bom sync)."""
	changed = False
	for parentfield in parentfields:
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt:
			continue
		if not frappe.db.table_exists(child_dt):
			continue
		meta = frappe.get_meta(child_dt)
		updates: dict = {"item_code": new_item}
		if meta.has_field("item_name"):
			updates["item_name"] = new_item_name
		if meta.has_field("bom_no"):
			updates["bom_no"] = new_default_bom or ""

		for name in frappe.get_all(
			child_dt,
			filters={
				"parent": bom_name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": current_item,
			},
			pluck="name",
		):
			frappe.db.set_value(child_dt, name, updates, update_modified=False)
			changed = True
	return changed


def _drawing_fields_for_child_row(child_dt: str, drawing_val: str) -> dict:
	"""Map drawing onto the field that exists on the target custom BOM child DocType."""
	out: dict[str, str] = {}
	if not drawing_val or not child_dt:
		return out
	meta = frappe.get_meta(child_dt)
	if meta.has_field("drawing_no"):
		out["drawing_no"] = drawing_val
	elif meta.has_field("custom_drawing_number"):
		out["custom_drawing_number"] = drawing_val
	return out


def _part_code_for_hardware_item(item_code: str) -> str:
	"""Hardware rows often store the numeric part in part_code (before ':' in link display)."""
	code = cstr(item_code or "").strip()
	if ":" in code:
		return code.split(":", 1)[0].strip()
	return code


def _move_item_cross_table_db(
	bom_name: str,
	current_item: str,
	new_item: str,
	*,
	source_parentfields: tuple[str, ...],
	target_parentfield: str,
	new_item_name: str,
	new_default_bom: str,
) -> bool:
	"""Remove `current_item` from source custom table(s) and insert `new_item` on the target table."""
	target_dt = _PARENTFIELD_TO_CHILD_DT.get(target_parentfield)
	if not target_dt or not frappe.db.table_exists(target_dt):
		return False

	target_meta = frappe.get_meta(target_dt)
	source_rows: list[dict] = []

	for parentfield in source_parentfields:
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt or not frappe.db.table_exists(child_dt):
			continue
		child_meta = frappe.get_meta(child_dt)
		fields = ["name", "qty"]
		if child_meta.has_field("bom_no"):
			fields.append("bom_no")
		if child_meta.has_field("drawing_no"):
			fields.append("drawing_no")
		if child_meta.has_field("custom_drawing_number"):
			fields.append("custom_drawing_number")
		for row in frappe.get_all(
			child_dt,
			filters={
				"parent": bom_name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": current_item,
			},
			fields=fields,
		):
			row["_child_dt"] = child_dt
			source_rows.append(row)

	if not source_rows:
		return False

	for row in source_rows:
		frappe.delete_doc(row["_child_dt"], row["name"], force=1)

	changed = False
	for row in source_rows:
		qty = flt(row.get("qty")) or 1
		draw = (row.get("drawing_no") or row.get("custom_drawing_number") or "").strip()
		child_row: dict = {
			"doctype": target_dt,
			"parent": bom_name,
			"parenttype": "BOM",
			"parentfield": target_parentfield,
			"item_code": new_item,
			"qty": qty,
		}
		if target_meta.has_field("item_name"):
			child_row["item_name"] = new_item_name
		if target_meta.has_field("bom_no"):
			child_row["bom_no"] = (row.get("bom_no") or new_default_bom or "").strip()
		child_row.update(_drawing_fields_for_child_row(target_dt, draw))
		if target_parentfield == "custom_bom_hardware_items" and target_meta.has_field("part_code"):
			child_row["part_code"] = _part_code_for_hardware_item(new_item)

		frappe.get_doc(child_row).insert(ignore_permissions=True)
		changed = True

	return changed


def _persist_custom_tables_from_doc(
	bom,
	current_item: str,
	new_item: str,
	*,
	parentfields: tuple[str, ...],
	new_item_name: str,
	new_default_bom: str,
) -> bool:
	"""Write in-memory custom child row changes to DB (avoids reload wiping unsaved edits)."""
	persisted = False
	for parentfield in parentfields:
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt:
			continue
		meta = frappe.get_meta(child_dt)
		for row in bom.get(parentfield) or []:
			if not row.name:
				continue
			if frappe.db.get_value(child_dt, row.name, "item_code") != current_item:
				continue
			updates: dict = {"item_code": new_item}
			if meta.has_field("item_name"):
				updates["item_name"] = new_item_name
			if meta.has_field("bom_no"):
				updates["bom_no"] = new_default_bom or ""
			frappe.db.set_value(child_dt, row.name, updates, update_modified=False)
			persisted = True
	return persisted


def _ensure_current_item_in_custom_tables(bom, current_item: str, material_key: str) -> bool:
	"""If the item exists only on synced BOM Item rows, copy it into the matching custom table."""
	item_meta = frappe.get_meta("BOM Item")
	fields = ["name", "item_code", "qty", "bom_no"]
	if item_meta.has_field("custom_item_group"):
		fields.append("custom_item_group")
	if item_meta.has_field("custom_drawing_number"):
		fields.append("custom_drawing_number")

	bi_rows = frappe.get_all(
		"BOM Item",
		filters={"parent": bom.name, "parenttype": "BOM", "item_code": current_item},
		fields=fields,
	)
	if not bi_rows:
		return False

	added = False
	for parentfield, child_dt, _label in _custom_tables_for_material_key(material_key):
		if frappe.db.exists(
			child_dt,
			{
				"parent": bom.name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": current_item,
			},
		):
			continue

		child_meta = frappe.get_meta(child_dt)
		for bi in bi_rows:
			line_group = (bi.get("custom_item_group") or "").strip()
			if material_key:
				if line_group and _canonical_item_group(line_group) != material_key:
					continue
				if not line_group and _get_material_key(current_item) != material_key:
					continue

			child_row: dict = {"item_code": current_item, "qty": flt(bi.get("qty")) or 1}
			item_name = frappe.db.get_value("Item", current_item, "item_name")
			if item_name and child_meta.has_field("item_name"):
				child_row["item_name"] = item_name
			if child_meta.has_field("bom_no"):
				child_row["bom_no"] = (bi.get("bom_no") or "").strip()

			draw = (bi.get("custom_drawing_number") or "").strip()
			if draw:
				if child_meta.has_field("custom_drawing_number"):
					child_row["custom_drawing_number"] = draw
				elif child_meta.has_field("drawing_no"):
					child_row["drawing_no"] = draw

			bom.append(parentfield, child_row)
			added = True
	return added


def _sync_bom_items_if_available(bom) -> None:
	try:
		from bt_bom.api.bom_custom import sync_bom_items_from_custom_tables

		sync_bom_items_from_custom_tables(bom)
	except ImportError:
		pass


def _finalize_bom_for_save(bom) -> None:
	"""Refresh rates/UOM on material lines before save."""
	if hasattr(bom, "set_bom_material_details"):
		bom.set_bom_material_details()
	for row in bom.get("items") or []:
		if not row.uom and row.item_code:
			row.uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
		if row.uom and not row.stock_uom:
			row.stock_uom = row.uom


def _remove_item_from_single_bom(bom_name: str, current_item: str) -> str | None:
	bom = frappe.get_doc("BOM", bom_name)
	frappe.has_permission("BOM", doc=bom, ptype="write", throw=True)

	if bom.item == current_item:
		return _("Skipped: item is the finished good on this BOM")

	changed = _remove_from_custom_tables_db(bom_name, current_item)
	if not changed:
		changed = _remove_from_bom_items_db(bom_name, current_item)

	if not changed:
		return _("Skipped: item not found on this BOM")

	bom = frappe.get_doc("BOM", bom_name)
	_sync_bom_items_if_available(bom)
	_finalize_bom_for_save(bom)
	_save_bom_after_replace(bom)
	return "updated"


def _remove_from_custom_tables_db(bom_name: str, item_code: str) -> bool:
	"""Delete all custom BOM child rows for `item_code` on this BOM."""
	changed = False
	for parentfield in _parentfields_for_item_on_bom_all(bom_name, item_code):
		child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
		if not child_dt or not frappe.db.table_exists(child_dt):
			continue
		deleted_any = False
		for name in frappe.get_all(
			child_dt,
			filters={
				"parent": bom_name,
				"parenttype": "BOM",
				"parentfield": parentfield,
				"item_code": item_code,
			},
			pluck="name",
		):
			frappe.delete_doc(child_dt, name, force=1)
			deleted_any = True
			changed = True
		if deleted_any:
			_reindex_bom_child_table(bom_name, parentfield)
	return changed


def _remove_from_bom_items_db(bom_name: str, item_code: str) -> bool:
	"""Delete synced BOM Item rows when the item exists only on the standard table."""
	changed = False
	for name in frappe.get_all(
		"BOM Item",
		filters={
			"parent": bom_name,
			"parenttype": "BOM",
			"item_code": item_code,
			"docstatus": ("!=", 2),
		},
		pluck="name",
	):
		frappe.delete_doc("BOM Item", name, force=1)
		changed = True
	if changed:
		_reindex_bom_items_table(bom_name)
	return changed


def _reindex_bom_child_table(bom_name: str, parentfield: str) -> None:
	"""Renumber idx on a custom BOM child table after row deletion."""
	child_dt = _PARENTFIELD_TO_CHILD_DT.get(parentfield)
	if not child_dt or not frappe.db.table_exists(child_dt):
		return

	rows = frappe.get_all(
		child_dt,
		filters={
			"parent": bom_name,
			"parenttype": "BOM",
			"parentfield": parentfield,
		},
		fields=["name", "idx"],
		order_by="idx asc, name asc",
	)
	for new_idx, row in enumerate(rows, start=1):
		if cint(row.idx) != new_idx:
			frappe.db.set_value(child_dt, row.name, "idx", new_idx, update_modified=False)


def _reindex_bom_items_table(bom_name: str) -> None:
	"""Renumber idx on BOM Item rows after row deletion."""
	rows = frappe.get_all(
		"BOM Item",
		filters={
			"parent": bom_name,
			"parenttype": "BOM",
			"docstatus": ("!=", 2),
		},
		fields=["name", "idx"],
		order_by="idx asc, name asc",
	)
	for new_idx, row in enumerate(rows, start=1):
		if cint(row.idx) != new_idx:
			frappe.db.set_value("BOM Item", row.name, "idx", new_idx, update_modified=False)


def _save_bom_after_replace(bom) -> None:
	"""Save BOM after item replace; allow material line changes on submitted BOMs."""
	# Same flag ERPNext uses in BOM.update_cost for submitted documents.
	if bom.docstatus == 1:
		bom.flags.ignore_validate_update_after_submit = True
	bom.save(ignore_permissions=False)
