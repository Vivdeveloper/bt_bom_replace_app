# Copyright (c) 2026, BT BOM Replace App and contributors
# MIT License

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, parse_json

# Custom BOM child tables (same contract as bt_bom / bartakke_erp).
_ALL_CUSTOM_TABLES: tuple[tuple[str, str, str], ...] = (
	("custom_bom_assembly_items", "BOM Assembly Item", "Assembly"),
	("custom_bom_sub_assembly_items", "BOM Sub Assembly Item", "Sub Assembly"),
	("custom_bom_hardware_items", "BOM Hardware Item", "Hardware (RM)"),
)


@frappe.whitelist()
def find_bom_links(item_code: str, search_type: str = "all"):
	"""Find an item at every BOM level: direct material lines + parent BOM chain to FG."""
	item_code = (item_code or "").strip()
	if not item_code:
		frappe.throw(_("Item is required"))
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found").format(item_code))

	frappe.has_permission("BOM", ptype="read", throw=True)

	direct = _find_direct_usages_everywhere(item_code)
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
		"item_default_bom": frappe.db.get_value("Item", item_code, "default_bom"),
		"rows": rows,
		"count": len(rows),
		"usage_count": usage_count,
		"parent_count": parent_count,
	}


def _find_direct_usages_everywhere(item_code: str) -> list[dict]:
	"""All BOMs where `item_code` appears directly (any section / table)."""
	rows: list[dict] = []
	seen: set[tuple] = set()

	for bom in frappe.get_all(
		"BOM",
		filters={"item": item_code, "docstatus": ("!=", 2)},
		fields=["name", "item", "item_name", "quantity"],
		order_by="modified desc",
	):
		_append_usage_row(
			rows,
			seen,
			bom=bom.name,
			bom_meta=bom,
			section=_("Parent / FG"),
			qty=flt(bom.quantity),
			linked_bom=bom.name,
			source="bom_fg",
		)

	for parentfield, child_dt, section_label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(f"tab{child_dt}"):
			continue
		rows.extend(
			_collect_custom_table_rows(item_code, parentfield, child_dt, section_label, seen)
		)

	rows.extend(_collect_bom_item_rows(item_code, seen))
	rows.extend(_collect_exploded_item_rows(item_code, seen))
	return rows


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
) -> None:
	key = (bom, section, child_row, source)
	if key in seen:
		return
	seen.add(key)
	rows.append(
		{
			"bom": bom,
			"bom_item": bom_meta.get("item"),
			"bom_item_name": bom_meta.get("item_name"),
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
			fields=["name", "item", "item_name", "quantity"],
		)
	}


def _collect_custom_table_rows(
	item_code: str,
	parentfield: str,
	child_dt: str,
	section_label: str,
	seen: set[tuple],
) -> list[dict]:
	meta = frappe.get_meta(child_dt)
	fields = ["name", "parent", "item_code", "qty"]
	if meta.has_field("bom_no"):
		fields.append("bom_no")

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
		)
	return out


def _collect_bom_item_rows(item_code: str, seen: set[tuple]) -> list[dict]:
	lines = frappe.get_all(
		"BOM Item",
		filters={
			"item_code": item_code,
			"parenttype": "BOM",
			"docstatus": ("!=", 2),
		},
		fields=["name", "parent", "qty", "bom_no", "custom_item_group"],
		order_by="parent asc, idx asc",
	)
	if not lines:
		return []

	bom_meta = _bom_meta_map(list({ln.parent for ln in lines}))
	default_bom = frappe.db.get_value("Item", item_code, "default_bom") or ""
	out: list[dict] = []

	for ln in lines:
		bom = bom_meta.get(ln.parent) or {}
		linked = (ln.get("bom_no") or "").strip() or default_bom
		section = (ln.get("custom_item_group") or "").strip() or _("BOM Item")
		_append_usage_row(
			out,
			seen,
			bom=ln.parent,
			bom_meta=bom,
			section=section,
			qty=flt(ln.get("qty")),
			linked_bom=linked,
			source="bom_item",
			child_row=ln.name,
		)
	return out


def _collect_exploded_item_rows(item_code: str, seen: set[tuple]) -> list[dict]:
	if not frappe.db.table_exists("tabBOM Explosion Item"):
		return []

	lines = frappe.get_all(
		"BOM Explosion Item",
		filters={"item_code": item_code, "parenttype": "BOM", "docstatus": ("!=", 2)},
		fields=["name", "parent", "stock_qty", "qty"],
		order_by="parent asc, idx asc",
	)
	if not lines:
		return []

	bom_meta = _bom_meta_map(list({ln.parent for ln in lines}))
	out: list[dict] = []

	for ln in lines:
		bom = bom_meta.get(ln.parent) or {}
		_append_usage_row(
			out,
			seen,
			bom=ln.parent,
			bom_meta=bom,
			section=_("Exploded"),
			qty=flt(ln.get("stock_qty") or ln.get("qty")),
			linked_bom="",
			source="exploded",
			child_row=ln.name,
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
					["item", "item_name", "quantity"],
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
def get_replace_preview(current_item: str, new_item: str, bom_list=None) -> dict:
	"""Count BOMs and material lines that will be updated."""
	current_item, new_item = _validate_replace_items(current_item, new_item)
	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item)
	bom_names = _filter_boms_for_replace(all_boms, selected_boms)
	line_count = _line_count_for_boms(current_item, bom_names)
	return {
		"current_item": current_item,
		"new_item": new_item,
		"bom_count": len(bom_names),
		"line_count": line_count,
		"selected_only": bool(selected_boms),
	}


@frappe.whitelist()
def replace_item_in_all_boms(current_item: str, new_item: str, bom_list=None) -> dict:
	"""Replace `current_item` with `new_item` on BOM material lines (all or selected BOMs)."""
	current_item, new_item = _validate_replace_items(current_item, new_item)
	frappe.has_permission("BOM", ptype="write", throw=True)

	selected_boms = _parse_bom_list(bom_list)
	all_boms, _line_count = _boms_with_material_usage(current_item)
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

	frappe.msgprint(
		_("Updated {0} BOM(s). Skipped {1}, failed {2}.").format(
			len(updated), len(skipped), len(failed)
		),
		indicator="green" if updated else "orange",
	)

	return {
		"current_item": current_item,
		"new_item": new_item,
		"updated_boms": updated,
		"skipped": skipped,
		"failed": failed,
		"updated_count": len(updated),
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


def _line_count_for_boms(item_code: str, bom_names: list[str]) -> int:
	if not bom_names:
		return 0
	bom_set = set(bom_names)
	count = 0
	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(f"tab{child_dt}"):
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
	count += frappe.db.count(
		"BOM Item",
		{
			"item_code": item_code,
			"parenttype": "BOM",
			"docstatus": ("!=", 2),
			"parent": ("in", bom_names),
		},
	)
	return count


def _validate_replace_items(current_item: str, new_item: str) -> tuple[str, str]:
	current_item = (current_item or "").strip()
	new_item = (new_item or "").strip()
	if not current_item or not new_item:
		frappe.throw(_("Current item and replacement item are required"))
	if current_item == new_item:
		frappe.throw(_("Current item and replacement item cannot be the same"))
	for code, label in ((current_item, _("Current item")), (new_item, _("Replacement item"))):
		if not frappe.db.exists("Item", code):
			frappe.throw(_("{0} {1} not found").format(label, code))
	return current_item, new_item


def _boms_with_material_usage(item_code: str) -> tuple[list[str], int]:
	"""BOMs where item is a material line (not FG parent), and total line count."""
	bom_set: set[str] = set()
	line_count = 0

	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not frappe.db.table_exists(f"tab{child_dt}"):
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
		bom_set.add(row.parent)
		line_count += 1

	# Drop BOMs where item is only the finished good (not a material line to replace).
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
	new_item_name: str,
	new_default_bom: str,
) -> str | None:
	bom = frappe.get_doc("BOM", bom_name)
	frappe.has_permission("BOM", doc=bom, ptype="write", throw=True)

	if bom.item == current_item:
		return _("Skipped: item is the finished good on this BOM")

	if _new_item_would_duplicate(bom, new_item, current_item):
		return _("Skipped: replacement item already exists on this BOM")

	changed = _replace_in_custom_tables(
		bom, current_item, new_item, new_item_name=new_item_name, new_default_bom=new_default_bom
	)
	if not changed:
		return _("Skipped: no material lines matched")

	_sync_bom_items_if_available(bom)
	_finalize_bom_for_save(bom)
	_save_bom_after_replace(bom)
	return "updated"


def _new_item_would_duplicate(bom, new_item: str, current_item: str) -> bool:
	"""True if replacing would leave the same item_code twice on this BOM."""
	seen: set[str] = set()
	for parentfield, _child_dt, _label in _ALL_CUSTOM_TABLES:
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
	new_item_name: str,
	new_default_bom: str,
) -> bool:
	changed = False
	for parentfield, child_dt, _label in _ALL_CUSTOM_TABLES:
		if not bom.get(parentfield):
			continue
		meta = frappe.get_meta(child_dt)
		for row in bom.get(parentfield):
			if row.item_code != current_item:
				continue
			row.item_code = new_item
			if meta.has_field("item_name"):
				row.item_name = new_item_name
			if meta.has_field("bom_no"):
				row.bom_no = new_default_bom or ""
			changed = True
	return changed


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


def _save_bom_after_replace(bom) -> None:
	"""Save BOM after item replace; allow material line changes on submitted BOMs."""
	# Same flag ERPNext uses in BOM.update_cost for submitted documents.
	if bom.docstatus == 1:
		bom.flags.ignore_validate_update_after_submit = True
	bom.save(ignore_permissions=False)
