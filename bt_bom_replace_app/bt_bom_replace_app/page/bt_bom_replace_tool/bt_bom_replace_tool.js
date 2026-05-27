/**
 * BT BOM Replace Tool — find BOM links at any level (parent / assembly / RM).
 */
frappe.pages["bt-bom-replace-tool"].on_page_load = function (wrapper) {
	const API = {
		find: "bt_bom_replace_app.bt_bom_replace_app.page.bt_bom_replace_tool.bt_bom_replace_tool.find_bom_links",
		preview:
			"bt_bom_replace_app.bt_bom_replace_app.page.bt_bom_replace_tool.bt_bom_replace_tool.get_replace_preview",
		replace:
			"bt_bom_replace_app.bt_bom_replace_app.page.bt_bom_replace_tool.bt_bom_replace_tool.replace_item_in_all_boms",
		item_details:
			"bt_bom_replace_app.bt_bom_replace_app.page.bt_bom_replace_tool.bt_bom_replace_tool.get_item_display_details",
	};

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("BT BOM Replace Tool"),
		single_column: true,
	});

	page.page_form.hide();
	page.container.addClass("full-width");
	page.main.removeClass("frappe-card").addClass("bt-bom-replace-page");
	$(wrapper).closest(".page-container").addClass("btbr-page-full");
	$(wrapper)
		.find(".layout-main-section-wrapper, .layout-main-section")
		.addClass("btbr-full-width");

	const $root = $('<div class="bt-bom-replace-body"></div>').appendTo(page.main);

	const $top_panels = $(`
		<div class="btbr-top-panels">
			<div class="btbr-panel btbr-panel-left">
				<div class="btbr-panel-title">${__("Search")}</div>
				<div class="btbr-panel-actions">
					<button type="button" class="btn btn-primary btn-sm btn-btbr-find">${__("Find BOM Links")}</button>
					<button type="button" class="btn btn-default btn-sm btn-btbr-clear">${__("Clear")}</button>
				</div>
				<p class="text-muted small btbr-search-help"></p>
				<div class="btbr-search-item-row">
					<div class="btbr-item-image-wrap hide">
						<img class="btbr-item-image" alt="" />
					</div>
					<div class="btbr-search-item-fields">
						<div class="btbr-panel-field btbr-search-field"></div>
						<div class="btbr-item-meta-fields">
							<div class="btbr-panel-field btbr-search-drawing-field"></div>
							<div class="btbr-panel-field btbr-search-itemname-field"></div>
						</div>
					</div>
				</div>
			</div>
			<div class="btbr-panel btbr-panel-right">
				<div class="btbr-panel-title">${__("Replace")}</div>
				<div class="btbr-panel-actions">
					<button type="button" class="btn btn-primary btn-sm btn-btbr-replace">${__("Replace Selected BOMs")}</button>
				</div>
				<p class="text-muted small btbr-replace-help"></p>
				<div class="btbr-replace-item-fields">
					<div class="btbr-panel-field btbr-replace-field"></div>
					<div class="btbr-item-meta-fields btbr-replace-meta-fields">
						<div class="btbr-panel-field btbr-replace-drawing-field"></div>
						<div class="btbr-panel-field btbr-replace-itemname-field"></div>
					</div>
					<div class="btbr-replace-bom-status"></div>
				</div>
			</div>
		</div>
	`).appendTo($root);

	const $list_section = $(`
		<div class="btbr-list-panel">
			<div class="btbr-list-panel-title">${__("BOM Links")}</div>
			<p class="text-muted small btbr-summary"></p>
			<div class="btbr-results"></div>
		</div>
	`).appendTo($root);

	ensure_styles();

	const $search_help = $top_panels.find(".btbr-search-help");
	const $replace_help = $top_panels.find(".btbr-replace-help");
	const $summary = $list_section.find(".btbr-summary");
	const $results = $list_section.find(".btbr-results");
	const $replace_btn = $top_panels.find(".btn-btbr-replace");

	$search_help.text(
		__(
			"Find this item on all BOM material lines (BOM Item, BOM Assembly Items, BOM Hardware Item). Replace moves or updates rows by Item Group (Standard/Specialized/Cutout → BOM Item; Assembly/Sub-Assembly/General Assembly → BOM Assembly Items; Hardware → BOM Hardware Item). The BOM production item on the header is not counted."
		)
	);

	const $item_image_wrap = $top_panels.find(".btbr-item-image-wrap");
	const $item_image = $top_panels.find(".btbr-item-image");
	$replace_help.text(
		__(
			"Select an item on the left, then choose a replacement item. Select BOM rows in the table below (In BOM level only), then click Replace Selected BOMs."
		)
	);

	const item_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-search-field")[0],
		df: {
			fieldtype: "Link",
			fieldname: "item_code",
			label: __("Item"),
			options: "Item",
			reqd: 1,
		},
		render_input: true,
	});

	const drawing_no_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-search-drawing-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "item_drawing_no",
			label: __("Drawing No"),
			read_only: 1,
		},
		render_input: true,
	});

	const item_name_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-search-itemname-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "item_name",
			label: __("Item Name"),
			read_only: 1,
		},
		render_input: true,
	});

	const replace_item_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-replace-field")[0],
		df: {
			fieldtype: "Link",
			fieldname: "new_item_code",
			label: __("Replace With"),
			options: "Item",
			reqd: 0,
			get_query: () => ({}),
		},
		render_input: true,
	});

	const replace_drawing_no_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-replace-drawing-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "replace_item_drawing_no",
			label: __("Drawing No"),
			read_only: 1,
		},
		render_input: true,
	});

	const replace_item_name_field = frappe.ui.form.make_control({
		parent: $top_panels.find(".btbr-replace-itemname-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "replace_item_name",
			label: __("Item Name"),
			read_only: 1,
		},
		render_input: true,
	});

	const $replace_bom_status = $top_panels.find(".btbr-replace-bom-status");

	const BOM_STATUS_COLORS = {
		Available: "green",
		"Not Available": "grey",
		"No Default BOM": "orange",
	};

	function get_bom_status_desc(status, bom_name) {
		const color = BOM_STATUS_COLORS[status] || "orange";
		let bom_html = "";
		if (bom_name && status === "Available") {
			bom_html = ` (<a href="${frappe.utils.get_form_link("BOM", bom_name)}">${frappe.utils.escape_html(
				bom_name
			)}</a>)`;
		} else if (bom_name && status === "No Default BOM") {
			bom_html = ` · ${frappe.utils.escape_html(bom_name)}`;
		}
		return `<div class="d-flex indicator ${color}">
			${__("Replacement item default BOM")}:&nbsp;<strong>${frappe.utils.escape_html(
				__(status)
			)}</strong>${bom_html}
		</div>`;
	}

	function active_bom_filters(item_code) {
		const filters = { item: item_code, docstatus: ["<", 2] };
		if (frappe.meta.has_field("BOM", "is_active")) {
			filters.is_active = 1;
		}
		return filters;
	}

	function field_from_db_row(row, field) {
		if (!row) return "";
		if (row[field] !== undefined && row[field] !== null) return row[field];
		if (row.message && typeof row.message === "object") return row.message[field] || "";
		if (row.message && field === "default_bom") return row.message;
		return "";
	}

	function set_replace_bom_status(html) {
		$replace_bom_status.html(html || "");
	}

	function set_replace_item_details(drawing_no, item_name) {
		replace_drawing_no_field.set_value(drawing_no || "");
		replace_item_name_field.set_value(item_name || "");
	}

	function clear_replace_item_details() {
		set_replace_item_details("", "");
	}

	async function update_replace_item_bom_status(item_code) {
		if (!item_code) {
			set_replace_bom_status("");
			return;
		}

		const item_row = await frappe.db.get_value("Item", item_code, "default_bom");
		const default_bom = field_from_db_row(item_row, "default_bom");

		if (default_bom) {
			const exists = await frappe.db.exists("BOM", default_bom);
			if (exists) {
				set_replace_bom_status(get_bom_status_desc("Available", default_bom));
				return;
			}
		}

		const bom_filters = active_bom_filters(item_code);
		const active_count = await frappe.db.count("BOM", { filters: bom_filters });

		if (active_count > 0) {
			const boms = await frappe.db.get_list("BOM", {
				filters: bom_filters,
				fields: ["name"],
				limit: 1,
				order_by: "modified desc",
			});
			set_replace_bom_status(get_bom_status_desc("No Default BOM", boms[0]?.name || ""));
			return;
		}

		set_replace_bom_status(get_bom_status_desc("Not Available"));
	}

	async function update_replace_item_panel(item_code) {
		if (!item_code) {
			clear_replace_item_details();
			set_replace_bom_status("");
			return;
		}
		try {
			const r = await frappe.call({
				method: API.item_details,
				args: { item_code },
			});
			if (r.message) {
				set_replace_item_details(r.message.item_drawing_no, r.message.item_name);
			}
		} catch (e) {
			clear_replace_item_details();
		}
		await update_replace_item_bom_status(item_code);
	}

	replace_item_field.$input?.on("awesomplete-selectcomplete", () => {
		update_replace_item_panel(replace_item_field.get_value());
	});
	replace_item_field.$input?.on("change", () => {
		update_replace_item_panel(replace_item_field.get_value());
	});

	setTimeout(() => align_input_fields(item_field, replace_item_field), 0);
	set_replace_enabled(false);

	let result_datatable = null;
	let last_search_data = null;
	let current_parent_item_group = null;
	let current_replace_item_group = null;

	item_field.$input?.on("awesomplete-selectcomplete", () => {
		if (item_field.get_value()) {
			run_search();
		}
	});
	item_field.$input?.on("keydown", (e) => {
		if (e.key === "Enter" && item_field.get_value()) {
			run_search();
		}
	});

	function set_replace_enabled(enabled) {
		$replace_btn.prop("disabled", !enabled);
	}

	function set_replace_parent_item_group_filter(parent_item_group, item_group, clear_replace_value) {
		current_parent_item_group = parent_item_group || null;
		current_replace_item_group = item_group || null;
		replace_item_field.df.get_query = () => ({});
		if (clear_replace_value !== false) {
			replace_item_field.set_value("");
			clear_replace_item_details();
			set_replace_bom_status("");
		}
		replace_item_field.refresh();
	}

	function set_replace_help(item_code, parent_item_group) {
		if (!item_code) {
			$replace_help.html(
				__(
					"Select an item on the left, then choose a replacement item. Select BOM rows in the table below (In BOM level only), then click Replace Selected BOMs."
				)
			);
			return;
		}
		const group_html = parent_item_group
			? frappe.utils.escape_html(parent_item_group)
			: __("any compatible item");
		$replace_help.html(
			__(
				"Replace {0} with {1}. Rows are removed from the table where the item was found and added to the table for the replacement item's Item Group. Select BOM rows, then click Replace Selected BOMs.",
				[frappe.utils.escape_html(item_code), group_html]
			)
		);
	}

	function bom_link(name) {
		if (!name) return "";
		return frappe.utils.get_form_link("BOM", name, true);
	}

	function format_replace_result_message(out) {
		if (!out) {
			return `<div>${__("Replace operation finished.")}</div>`;
		}
		const current = frappe.utils.escape_html(out.current_item || "");
		const replacement = frappe.utils.escape_html(out.new_item || "");
		const updated_boms = out.updated_boms || [];
		const skipped = out.skipped || [];
		const failed = out.failed || [];
		const parts = [];

		parts.push(
			`<div>${__("Item replaced")}<br>${current}<br>→ ${replacement}</div>`
		);

		if (out.section) {
			parts.push(
				`<div class="text-muted small" style="margin-top:8px">${__("BOM section")}: ${frappe.utils.escape_html(
					out.section
				)}</div>`
			);
		}

		if (updated_boms.length) {
			const bom_lines = updated_boms
				.slice(0, 25)
				.map((bom) => `<li>${bom_link(bom)}</li>`)
				.join("");
			let list_html = `<div style="margin-top:12px">${__("Updated in")} ${updated_boms.length} ${__(
				"BOM(s)"
			)}</div><ul style="margin:8px 0 0 18px">${bom_lines}</ul>`;
			if (updated_boms.length > 25) {
				list_html += `<div class="text-muted small">${__("…and")} ${
					updated_boms.length - 25
				} ${__("more BOM(s)")}</div>`;
			}
			parts.push(list_html);
		} else {
			parts.push(`<div style="margin-top:12px">${__("No BOMs were updated.")}</div>`);
		}

		if (skipped.length) {
			const lines = skipped
				.slice(0, 10)
				.map(
					(s) =>
						`<li>${frappe.utils.escape_html(s.bom)}: ${frappe.utils.escape_html(
							s.reason
						)}</li>`
				)
				.join("");
			parts.push(
				`<div style="margin-top:12px">${__("Skipped")} (${skipped.length})</div><ul class="text-muted" style="margin:8px 0 0 18px">${lines}</ul>`
			);
		}

		if (failed.length) {
			const lines = failed
				.slice(0, 10)
				.map(
					(f) =>
						`<li>${frappe.utils.escape_html(f.bom)}: ${frappe.utils.escape_html(
							f.reason
						)}</li>`
				)
				.join("");
			parts.push(
				`<div style="margin-top:12px">${__("Failed")} (${failed.length})</div><ul class="text-danger" style="margin:8px 0 0 18px">${lines}</ul>`
			);
		}

		return `<div class="bt-bom-replace-complete-msg">${parts.join("")}</div>`;
	}

	function show_replace_complete_dialog(out) {
		const html =
			format_replace_result_message(out) ||
			`<div>${frappe.utils.escape_html(out?.current_item || "")} → ${frappe.utils.escape_html(
				out?.new_item || ""
			)}</div>`;
		const dialog = new frappe.ui.Dialog({
			title: __("Replace complete"),
			fields: [{ fieldtype: "HTML", fieldname: "result", options: html }],
			primary_action_label: __("OK"),
			primary_action() {
				dialog.hide();
			},
		});
		dialog.show();
	}

	function keep_searched_item_after_replace(searched_item) {
		const meta = last_search_data || {};
		item_field.set_value(searched_item);
		set_search_item_details(meta.item_drawing_no, meta.item_name);
		set_replace_parent_item_group_filter(
			meta.custom_parent_item_group || current_parent_item_group,
			meta.item_group || current_replace_item_group,
			false
		);
		set_replace_help(searched_item, meta.custom_parent_item_group || current_parent_item_group);
	}

	function set_item_image(image_path) {
		if (!image_path) {
			$item_image_wrap.addClass("hide");
			$item_image.attr("src", "");
			return;
		}
		$item_image.attr("src", frappe.utils.get_file_url(image_path));
		$item_image_wrap.removeClass("hide");
	}

	function set_search_item_details(drawing_no, item_name) {
		drawing_no_field.set_value(drawing_no || "");
		item_name_field.set_value(item_name || "");
	}

	function clear_search_item_details() {
		set_search_item_details("", "");
	}

	function render_results(data) {
		set_item_image(data.item_image);
		set_search_item_details(data.item_drawing_no, data.item_name);
		$results.empty();
		$summary.empty();
		last_search_data = data;

		const usage =
			data?.usage_count ?? data?.rows?.filter((r) => r.level === "usage").length ?? 0;

		if (!data?.rows?.length) {
			set_replace_enabled(false);
			set_replace_parent_item_group_filter("");
			set_replace_help("");
			$summary.html(
				__("No BOM links found for {0}.", [
					frappe.utils.escape_html(data.item_code),
				])
			);
			result_datatable = null;
			return;
		}

		set_replace_parent_item_group_filter(
			data.custom_parent_item_group,
			data.item_group
		);
		set_replace_help(data.item_code, data.custom_parent_item_group);
		set_replace_enabled(usage > 0);

		const parent = data.parent_count ?? data.rows.length - usage;
		let summary_html = __("Found {0} row(s) for {1}", [
			data.count,
			frappe.utils.escape_html(data.item_code),
		]);
		if (data.custom_parent_item_group) {
			summary_html += ` · ${__("Parent Item Group")}: ${frappe.utils.escape_html(
				data.custom_parent_item_group
			)}`;
		} else if (data.item_group) {
			summary_html += ` · ${__("Item Group")}: ${frappe.utils.escape_html(data.item_group)}`;
		}
		summary_html += ` (${usage} ${__("in BOM")}, ${parent} ${__("parent level")})`;
		if (data.item_default_bom) {
			summary_html += ` · ${__("Default BOM")}: ${bom_link(data.item_default_bom)}`;
		}
		$summary.html(summary_html);

		const columns = [
			{
				name: __("Drawing Number"),
				id: "custom_drawing_number",
				editable: false,
				width: 200,
			},
			{
				name: __("BOM"),
				id: "bom",
				editable: false,
				width: 480,
				format: (v) => bom_link(v),
			},
			{
				name: __("FG Item"),
				id: "bom_item",
				editable: false,
				width: 360,
			},
			{
				name: __("Section"),
				id: "section",
				editable: false,
				width: 130,
			},
			{
				name: __("Qty"),
				id: "qty",
				editable: false,
				width: 52,
				align: "right",
				format: (v) => (v != null ? String(v) : ""),
			},
		].filter((col) => col.id !== "text-split" && col.id !== "text_split");

		$results.addClass("btbr-results-table");

		const table_rows = data.rows.map((r) => ({
			custom_drawing_number: r.custom_drawing_number || "",
			bom: r.bom,
			bom_item: r.bom_item || "",
			section: r.section || "",
			qty: r.qty,
		}));

		result_datatable = new frappe.DataTable($results[0], {
			columns,
			data: table_rows,
			layout: "fixed",
			cellHeight: 36,
			serialNoColumn: false,
			checkboxColumn: true,
			inlineFilters: true,
			noDataMessage: __("No rows"),
		});

		setTimeout(() => configure_row_checkboxes(data.rows), 50);
	}

	function configure_row_checkboxes(rows) {
		if (!result_datatable?.bodyScrollable) return;
		rows.forEach((row, idx) => {
			const inputs = result_datatable.bodyScrollable.querySelectorAll(
				`.dt-cell--0-${idx} input[type="checkbox"]`
			);
			inputs.forEach((inp) => {
				if (row.level !== "usage") {
					inp.disabled = true;
					inp.checked = false;
					inp.title = __("Only 'In BOM' rows can be selected for replace");
					const cell = inp.closest(".dt-cell");
					if (cell) {
						cell.classList.add("bt-bom-row-not-selectable");
					}
					if (result_datatable.rowmanager?.checkMap) {
						result_datatable.rowmanager.checkMap[idx] = 0;
					}
				}
			});
		});
	}

	function get_selected_boms() {
		if (!result_datatable?.rowmanager || !last_search_data?.rows) {
			return [];
		}
		const indexes = result_datatable.rowmanager.getCheckedRows();
		const boms = new Set();
		indexes.forEach((idx) => {
			const row = last_search_data.rows[Number(idx)];
			if (row?.level === "usage" && row.bom) {
				boms.add(row.bom);
			}
		});
		return [...boms];
	}

	function run_search() {
		const item_code = item_field.get_value();
		if (!item_code) {
			frappe.show_alert({ message: __("Select an Item"), indicator: "orange" });
			return;
		}

		frappe.call({
			method: API.find,
			args: { item_code },
			freeze: true,
			freeze_message: __("Finding BOM links..."),
			callback(r) {
				if (r.exc || !r.message) return;
				render_results(r.message);
			},
		});
	}

	function clear_search() {
		item_field.set_value("");
		clear_search_item_details();
		replace_item_field.set_value("");
		clear_replace_item_details();
		set_replace_bom_status("");
		set_replace_parent_item_group_filter("");
		set_item_image("");
		$results.empty().removeClass("btbr-results-table");
		$summary.empty();
		set_replace_enabled(false);
		set_replace_help("");
		result_datatable = null;
		last_search_data = null;
	}

	function run_replace() {
		const current_item = item_field.get_value();
		const new_item = replace_item_field.get_value();

		if (!current_item) {
			frappe.show_alert({ message: __("Search an item first"), indicator: "orange" });
			return;
		}
		if (!new_item) {
			frappe.show_alert({ message: __("Select replacement item"), indicator: "orange" });
			return;
		}
		if (current_item === new_item) {
			frappe.show_alert({
				message: __("Current and replacement item cannot be the same"),
				indicator: "orange",
			});
			return;
		}

		const bom_list = get_selected_boms();
		if (!bom_list.length) {
			frappe.show_alert({
				message: __("Select at least one BOM row in the table"),
				indicator: "orange",
			});
			return;
		}

		const preview_args = { current_item, new_item, bom_list: JSON.stringify(bom_list) };

		frappe.call({
			method: API.preview,
			args: preview_args,
			freeze: true,
			freeze_message: __("Checking BOMs..."),
			callback(r) {
				if (r.exc || !r.message) return;
				const p = r.message;
				if (!p.bom_count) {
					frappe.msgprint({
						title: __("Nothing to replace"),
						message: __("No material lines found for item {0}", [current_item]),
						indicator: "orange",
					});
					return;
				}

				frappe.confirm(
					__(
						"Replace {0} with {1} in {2} selected BOM(s) ({3} material line(s))? This cannot be undone easily.",
						[p.current_item, p.new_item, p.bom_count, p.line_count]
					),
					() => {
						frappe.call({
							method: API.replace,
							args: preview_args,
							freeze: true,
							freeze_message: __("Replacing item in BOMs..."),
							callback(res) {
								if (res.exc || !res.message) return;
								const out = res.message;
								const searched_item = current_item;
								show_replace_complete_dialog(out);
								keep_searched_item_after_replace(searched_item);
							},
						});
					}
				);
			},
		});
	}

	$top_panels.find(".btn-btbr-find").on("click", () => run_search());
	$top_panels.find(".btn-btbr-clear").on("click", () => clear_search());
	$top_panels.find(".btn-btbr-replace").on("click", () => run_replace());

	function align_input_fields(...controls) {
		const $labels = controls
			.map((c) => c?.$wrapper?.find(".control-label").first())
			.filter(($el) => $el?.length);
		if (!$labels.length) return;

		let max_h = 0;
		$labels.forEach(($lbl) => {
			$lbl.css("min-height", "");
			max_h = Math.max(max_h, $lbl.outerHeight() || 0);
		});
		if (max_h > 0) {
			$labels.forEach(($lbl) => $lbl.css("min-height", `${max_h}px`));
		}
	}

	function ensure_styles() {
		const id = "bt-bom-replace-tool-style";
		$("#" + id).remove();
		$("<style>")
			.attr("id", id)
			.text(`
.btbr-page-full .page-body.full-width,
.btbr-page-full .layout-main,
.btbr-page-full .layout-main-section-wrapper.btbr-full-width,
.btbr-page-full .layout-main-section.btbr-full-width {
	width: 100% !important;
	max-width: 100% !important;
}
.btbr-page-full .layout-main-section.btbr-full-width {
	padding: 8px 12px;
	box-sizing: border-box;
}
.bt-bom-replace-page {
	background: var(--bg-color, #fff);
	padding: 0;
	width: 100%;
	max-width: none;
}
.bt-bom-replace-body {
	padding: 0;
	width: 100%;
	max-width: none;
	box-sizing: border-box;
}
.bt-bom-replace-page .btbr-top-panels {
	display: flex;
	align-items: stretch;
	gap: 14px;
	margin-bottom: 14px;
	width: 100%;
}
.bt-bom-replace-page .btbr-panel {
	flex: 1 1 0;
	min-width: 0;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color, #c8cfd5);
	border-radius: var(--border-radius-md, 8px);
	background: #fff;
	padding: 12px 14px;
	box-sizing: border-box;
}
.bt-bom-replace-page .btbr-panel-title {
	font-size: var(--text-md, 14px);
	font-weight: 600;
	color: var(--text-color, #333);
	margin-bottom: 8px;
}
.bt-bom-replace-page .btbr-panel-actions {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 8px;
	margin-bottom: 8px;
	min-height: 32px;
}
.bt-bom-replace-page .btbr-search-help,
.bt-bom-replace-page .btbr-replace-help {
	margin: 0 0 10px;
	line-height: 1.45;
}
.bt-bom-replace-page .btbr-search-item-row {
	display: flex;
	align-items: flex-start;
	gap: 12px;
}
.bt-bom-replace-page .btbr-item-image-wrap {
	flex: 0 0 auto;
	width: 72px;
	height: 72px;
	border: 1px solid var(--border-color, #d1d8dd);
	border-radius: var(--border-radius-sm, 6px);
	background: var(--control-bg, #f7f7f7);
	overflow: hidden;
	display: flex;
	align-items: center;
	justify-content: center;
}
.bt-bom-replace-page .btbr-item-image-wrap.hide {
	display: none;
}
.bt-bom-replace-page .btbr-item-image {
	max-width: 100%;
	max-height: 100%;
	object-fit: contain;
}
.bt-bom-replace-page .btbr-search-item-fields {
	flex: 1 1 auto;
	min-width: 0;
	display: flex;
	flex-direction: column;
	gap: 0;
}
.bt-bom-replace-page .btbr-replace-item-fields {
	display: flex;
	flex-direction: column;
}
.bt-bom-replace-page .btbr-item-meta-fields {
	display: flex;
	flex-direction: column;
	gap: 0;
	margin-top: 10px;
}
.bt-bom-replace-page .btbr-replace-bom-status {
	margin-top: 8px;
	font-size: var(--text-sm, 12px);
	line-height: 1.45;
}
.bt-bom-replace-page .btbr-replace-bom-status:empty {
	display: none;
}
.bt-bom-replace-page .btbr-search-item-row .btbr-panel-field {
	flex: 1 1 auto;
	min-width: 0;
}
.bt-bom-replace-page .btbr-item-meta-fields .frappe-control input.form-control[readonly] {
	background-color: var(--control-bg, #f7f7f7) !important;
	cursor: default;
}
.bt-bom-replace-page .btbr-panel-field {
	flex: 1 1 auto;
	display: flex;
	flex-direction: column;
	justify-content: flex-end;
}
.bt-bom-replace-page .btbr-panel .frappe-control {
	margin-bottom: 0;
	width: 100%;
}
.bt-bom-replace-page .btbr-panel .control-input-wrapper,
.bt-bom-replace-page .btbr-panel .control-input {
	width: 100%;
}
.bt-bom-replace-page .btbr-panel .frappe-control .control-input,
.bt-bom-replace-page .btbr-panel .frappe-control input.form-control {
	background-color: #fff !important;
	border: 1px solid var(--border-color, #d1d8dd) !important;
	border-radius: var(--border-radius-sm, 6px) !important;
	min-height: 36px;
	width: 100% !important;
	box-sizing: border-box;
}
.bt-bom-replace-page .btbr-panel .frappe-control .control-label {
	display: block;
	font-weight: 500;
	color: var(--text-muted, #6c7680);
	margin-bottom: 6px;
	line-height: 1.35;
	padding: 0;
}
.bt-bom-replace-page .btbr-replace-field .help-box {
	margin-top: 6px;
	font-size: var(--text-sm, 12px);
	line-height: 1.4;
}
.bt-bom-replace-page .btbr-replace-field .help-box .indicator::before {
	margin-right: 6px;
}
.bt-bom-replace-page .btbr-list-panel {
	width: 100%;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color, #c8cfd5);
	border-radius: var(--border-radius-md, 8px);
	background: #fff;
	padding: 12px 14px;
	box-sizing: border-box;
	min-height: calc(100vh - 320px);
}
.bt-bom-replace-page .btbr-list-panel-title {
	font-size: var(--text-md, 14px);
	font-weight: 600;
	color: var(--text-color, #333);
	margin-bottom: 8px;
}
.bt-bom-replace-page .btbr-summary {
	margin: 0 0 8px;
}
.bt-bom-replace-page .btbr-results {
	flex: 1 1 auto;
	min-height: 200px;
	width: 100%;
	border: 1px solid var(--border-color, #e2e6ea);
	border-radius: var(--border-radius-sm, 6px);
	background: #fff;
	overflow: auto;
}
.bt-bom-replace-page .btbr-results-table,
.bt-bom-replace-page .btbr-results-table .dt-scrollable,
.bt-bom-replace-page .btbr-results-table .dt-instance {
	width: 100% !important;
	max-width: 100% !important;
}
.bt-bom-replace-page .btbr-results-table .dt-scrollable {
	overflow-x: auto;
}
.bt-bom-replace-page .btbr-results-table .dt-cell__content {
	white-space: normal;
	word-break: break-word;
	line-height: 1.35;
}
.bt-bom-replace-page .btbr-results-table .bt-bom-row-not-selectable {
	opacity: 0.35;
	cursor: not-allowed;
}
.bt-bom-replace-page .btbr-results-table .bt-bom-row-not-selectable input[type="checkbox"] {
	pointer-events: none;
}
.bt-bom-replace-page .awesomplete > ul {
	z-index: 1051;
	max-height: 240px;
	overflow-y: auto;
}
`)
			.appendTo(document.head);
	}
};
