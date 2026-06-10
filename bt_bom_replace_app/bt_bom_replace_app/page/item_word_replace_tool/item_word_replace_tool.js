/**
 * Item Word Replace Tool — Frappe desk page layout.
 */
frappe.pages["item-word-replace-tool"].on_page_load = function (wrapper) {
	const API = {
		search: "bt_bom_replace_app.bt_bom_replace_app.page.item_word_replace_tool.item_word_replace_tool.search_items",
		preview:
			"bt_bom_replace_app.bt_bom_replace_app.page.item_word_replace_tool.item_word_replace_tool.get_replace_preview",
		replace:
			"bt_bom_replace_app.bt_bom_replace_app.page.item_word_replace_tool.item_word_replace_tool.replace_selected_items",
	};

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Item Word Replace Tool"),
		single_column: true,
	});

	page.page_form.hide();
	page.container.addClass("full-width");
	page.main.removeClass("frappe-card").addClass("item-word-replace-page");
	$(wrapper).closest(".page-container").addClass("iwr-page-full");
	$(wrapper).find(".layout-main-section-wrapper, .layout-main-section").addClass("iwr-full-width");

	const $root = $('<div class="item-word-replace-body"></div>').appendTo(page.main);

	// Top: two equal panels (search | replace) — wireframe layout
	const $inputs_section = $(`
		<div class="iwr-top-panels">
			<div class="iwr-panel iwr-panel-left">
				<div class="iwr-panel-actions">
					<button type="button" class="btn btn-primary btn-sm btn-iwr-search">${__("Search")}</button>
					<button type="button" class="btn btn-default btn-sm btn-iwr-show-all">${__("Show All")}</button>
				</div>
				<div class="iwr-panel-field iwr-search-field"></div>
			</div>
			<div class="iwr-panel iwr-panel-right">
				<div class="iwr-panel-actions">
					<button type="button" class="btn btn-primary btn-sm btn-iwr-replace">${__("Replace")}</button>
					<button type="button" class="btn btn-default btn-sm btn-iwr-remove">${__("Remove")}</button>
				</div>
				<div class="iwr-panel-field iwr-replace-with-field"></div>
			</div>
		</div>
	`).appendTo($root);

	// Bottom: full-width list panel
	const $list_section = $(`
		<div class="iwr-list-panel">
			<div class="iwr-list-panel-title">${__("Item List")}</div>
			<p class="text-muted small iwr-summary"></p>
			<div class="iwr-results"></div>
			<div class="iwr-list-panel-footer">
				<label class="checkbox iwr-select-all-label">
					<input type="checkbox" class="iwr-select-all" />
					<span class="label-area">${__("Select All")}</span>
				</label>
			</div>
		</div>
	`).appendTo($root);

	ensure_styles();

	const $summary = $list_section.find(".iwr-summary");
	const $results = $list_section.find(".iwr-results");
	const $select_all = $list_section.find(".iwr-select-all");

	const search_field = frappe.ui.form.make_control({
		parent: $inputs_section.find(".iwr-search-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "search_text",
			label: __("Search Item / Assembly / Sub Assembly / GA / Catalog / Assembly Item"),
			placeholder: __("Type item name or code…"),
			reqd: 0,
		},
		render_input: true,
	});

	const replace_with_field = frappe.ui.form.make_control({
		parent: $inputs_section.find(".iwr-replace-with-field")[0],
		df: {
			fieldtype: "Data",
			fieldname: "replace_with",
			label: __("Replace With"),
			placeholder: __("Type replacement text…"),
			reqd: 0,
		},
		render_input: true,
	});

	setTimeout(() => align_input_fields(search_field, replace_with_field), 0);

	let result_datatable = null;
	let last_search_data = null;
	let last_table_rows = null;

	function item_link(name) {
		if (!name) return "";
		return frappe.utils.get_form_link("Item", name, true);
	}

	function render_results(data) {
		$results.empty();
		$summary.empty();
		last_search_data = data;
		$select_all.prop("checked", false);

		if (!data?.rows?.length) {
			$summary.text(__("No items found."));
			result_datatable = null;
			last_table_rows = null;
			return;
		}

		$summary.text(
			data.show_all
				? __("Showing all {0} item(s) in the system.", [data.count])
				: __("Found {0} item(s) whose name includes your search text.", [data.count])
		);

		const columns = [
			{
				name: __("Full Drawing Number"),
				id: "full_drawing_number",
				editable: false,
				width: 280,
			},
			{
				name: __("Item Code"),
				id: "item_code",
				editable: false,
				width: 240,
				format: (v) => item_link(v),
			},
			{
				name: __("Item Name"),
				id: "item_name",
				editable: false,
				width: 560,
			},
			{
				name: __("Type"),
				id: "type",
				editable: false,
				width: 200,
			},
		];

		$results.addClass("iwr-results-table");

		last_table_rows = data.rows.map((r) => ({
			full_drawing_number: r.full_drawing_number || "",
			item_code: r.item_code || "",
			item_name: r.item_name || "",
			type: r.type || "",
		}));

		result_datatable = new frappe.DataTable($results[0], {
			columns,
			data: last_table_rows,
			layout: "fixed",
			cellHeight: 32,
			serialNoColumn: true,
			checkboxColumn: true,
			inlineFilters: true,
			noDataMessage: __("No Data"),
		});

		setTimeout(() => {
			bind_select_all();
			bind_cell_copy_on_dblclick();
		}, 50);
	}

	function bind_cell_copy_on_dblclick() {
		const $container = $(result_datatable?.bodyScrollable || $results[0]);
		if (!$container.length) return;

		$container.off("dblclick.iwr-copy").on("dblclick.iwr-copy", ".dt-cell", function (e) {
			const $cell = $(this);
			if ($cell.find('input[type="checkbox"]').length) return;
			if ($cell.find("input, select, textarea").length) return;
			if ($cell.closest(".dt-row-filter").length) return;

			const col_match = (this.className || "").match(/dt-cell--(\d+)-/);
			if (col_match && parseInt(col_match[1], 10) <= 1) {
				return;
			}

			const text = ($cell.find(".dt-cell__content").first().text() || "").trim();
			if (!text) return;

			frappe.utils.copy_to_clipboard(text);
			$cell.addClass("iwr-copy-flash");
			setTimeout(() => $cell.removeClass("iwr-copy-flash"), 400);
			frappe.show_alert(
				{ message: __("Copied to clipboard"), indicator: "green" },
				2
			);
			e.preventDefault();
			e.stopPropagation();
		});
	}

	function bind_select_all() {
		if (!result_datatable?.rowmanager) return;
		$select_all.off("change.iwr").on("change.iwr", function () {
			const checked = $(this).prop("checked");
			if (result_datatable.rowmanager.checkAll) {
				result_datatable.rowmanager.checkAll(!!checked);
			}
		});
	}

	function get_selected_item_codes() {
		if (!result_datatable?.rowmanager || !last_table_rows?.length) {
			return [];
		}
		const indexes = result_datatable.rowmanager.getCheckedRows();
		const codes = [];
		indexes.forEach((idx) => {
			const row = last_table_rows[Number(idx)];
			if (row?.item_code) {
				codes.push(row.item_code);
			}
		});
		return [...new Set(codes)];
	}

	function show_replace_result(out) {
		if (out.failed?.length) {
			const details = out.failed
				.map((f) => `${f.item_code}: ${f.reason}`)
				.join("<br>");
			frappe.msgprint({
				title: __("Some items failed"),
				message: details,
				indicator: "orange",
			});
		}
		if (out.skipped?.length) {
			frappe.show_alert({
				message: __("Skipped {0} item(s)", [out.skipped.length]),
				indicator: "orange",
			});
		}
		frappe.show_alert({
			message: __("Updated {0} item(s)", [out.updated_count || 0]),
			indicator: out.updated_count ? "green" : "orange",
		});
	}

	function run_search(show_all) {
		const search_text = search_field.get_value() || "";
		if (!show_all && !String(search_text).trim()) {
			frappe.show_alert({
				message: __("Enter search text or click Show All"),
				indicator: "orange",
			});
			return;
		}

		frappe.call({
			method: API.search,
			args: {
				search_text,
				show_all: show_all ? 1 : 0,
			},
			freeze: true,
			freeze_message: show_all
				? __("Loading all items...")
				: __("Searching items..."),
			callback(r) {
				if (r.exc || !r.message) return;
				render_results(r.message);
			},
		});
	}

	function run_text_update({ replace_text, nothing_title, confirm_message, apply_message }) {
		const search_text = (search_field.get_value() || "").trim();
		const item_codes = get_selected_item_codes();

		if (!search_text) {
			frappe.show_alert({
				message: __("Enter the search text used to find items"),
				indicator: "orange",
			});
			return;
		}
		if (!item_codes.length) {
			frappe.show_alert({
				message: __("Select at least one item"),
				indicator: "orange",
			});
			return;
		}

		const args = {
			search_text,
			replace_text,
			item_codes: JSON.stringify(item_codes),
		};

		frappe.call({
			method: API.preview,
			args,
			freeze: true,
			freeze_message: __("Previewing..."),
			callback(r) {
				if (r.exc || !r.message) return;
				const p = r.message;
				if (!p.row_count) {
					frappe.msgprint({
						title: nothing_title,
						message: __(
							"Selected items do not contain the search text in Item Name or Item Code."
						),
						indicator: "orange",
					});
					return;
				}

				frappe.confirm(confirm_message(p), () => {
					frappe.call({
						method: API.replace,
						args,
						freeze: true,
						freeze_message: apply_message,
						callback(res) {
							if (res.exc || !res.message) return;
							const out = res.message;
							show_replace_result(out);
							if (last_search_data?.show_all) {
								run_search(true);
							} else {
								run_search(false);
							}
						},
					});
				});
			},
		});
	}

	function run_replace() {
		run_text_update({
			replace_text: replace_with_field.get_value() ?? "",
			nothing_title: __("Nothing to replace"),
			confirm_message: (p) =>
				__(
					"Replace <b>{0}</b> with <b>{1}</b> in Item Name and Item Code for <b>{2}</b> item(s)?",
					[
						frappe.utils.escape_html(p.search_text),
						frappe.utils.escape_html(p.replace_text || ""),
						p.row_count,
					]
				),
			apply_message: __("Replacing..."),
		});
	}

	function run_remove() {
		run_text_update({
			replace_text: "",
			nothing_title: __("Nothing to remove"),
			confirm_message: (p) =>
				__(
					"Remove <b>{0}</b> from Item Name and Item Code for <b>{1}</b> item(s)?",
					[frappe.utils.escape_html(p.search_text), p.row_count]
				),
			apply_message: __("Removing..."),
		});
	}

	search_field.$input?.on("keydown", (e) => {
		if (e.key === "Enter") {
			run_search(false);
		}
	});

	$inputs_section.find(".btn-iwr-search").on("click", () => run_search(false));
	$inputs_section.find(".btn-iwr-replace").on("click", () => run_replace());
	$inputs_section.find(".btn-iwr-remove").on("click", () => run_remove());
	$inputs_section.find(".btn-iwr-show-all").on("click", () => run_search(true));

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
		const id = "item-word-replace-tool-style";
		$("#" + id).remove();
		$("<style>")
			.attr("id", id)
			.text(`
.iwr-page-full .page-body.full-width,
.iwr-page-full .layout-main,
.iwr-page-full .layout-main-section-wrapper.iwr-full-width,
.iwr-page-full .layout-main-section.iwr-full-width {
	width: 100% !important;
	max-width: 100% !important;
}
.iwr-page-full .layout-main-section.iwr-full-width {
	padding: 8px 12px;
	box-sizing: border-box;
}
.item-word-replace-page {
	background: var(--bg-color, #fff);
	padding: 0;
	width: 100%;
	max-width: none;
}
.item-word-replace-body {
	padding: 0;
	width: 100%;
	max-width: none;
	box-sizing: border-box;
}
/* Top row — two equal bordered panels */
.item-word-replace-page .iwr-top-panels {
	display: flex;
	align-items: stretch;
	gap: 14px;
	margin-bottom: 14px;
	width: 100%;
}
.item-word-replace-page .iwr-panel {
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
.item-word-replace-page .iwr-panel-actions {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 8px;
	margin-bottom: 10px;
	min-height: 32px;
}
.item-word-replace-page .iwr-panel-field {
	flex: 1 1 auto;
	display: flex;
	flex-direction: column;
	justify-content: flex-end;
}
.item-word-replace-page .iwr-panel .frappe-control {
	margin-bottom: 0;
	width: 100%;
}
.item-word-replace-page .iwr-panel .control-input-wrapper,
.item-word-replace-page .iwr-panel .control-input {
	width: 100%;
}
.item-word-replace-page .iwr-panel .frappe-control .control-input,
.item-word-replace-page .iwr-panel .frappe-control input.form-control {
	background-color: #fff !important;
	border: 1px solid var(--border-color, #d1d8dd) !important;
	border-radius: var(--border-radius-sm, 6px) !important;
	min-height: 36px;
	width: 100% !important;
	box-sizing: border-box;
}
.item-word-replace-page .iwr-panel .frappe-control .control-label {
	display: block;
	font-weight: 500;
	color: var(--text-muted, #6c7680);
	margin-bottom: 6px;
	line-height: 1.35;
	padding: 0;
}
/* Bottom — full-width list panel */
.item-word-replace-page .iwr-list-panel {
	width: 100%;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color, #c8cfd5);
	border-radius: var(--border-radius-md, 8px);
	background: #fff;
	padding: 12px 14px;
	box-sizing: border-box;
	min-height: calc(100vh - 300px);
}
.item-word-replace-page .iwr-list-panel-title {
	font-size: var(--text-md, 14px);
	font-weight: 600;
	color: var(--text-color, #333);
	margin-bottom: 8px;
}
.item-word-replace-page .iwr-summary {
	margin: 0 0 8px;
}
.item-word-replace-page .iwr-results {
	flex: 1 1 auto;
	min-height: 200px;
	width: 100%;
	border: 1px solid var(--border-color, #e2e6ea);
	border-radius: var(--border-radius-sm, 6px);
	background: #fff;
	overflow: auto;
}
.item-word-replace-page .iwr-list-panel-footer {
	margin-top: 10px;
	padding-top: 8px;
	border-top: 1px solid var(--border-color, #e2e6ea);
}
.item-word-replace-page .iwr-select-all-label {
	margin: 0;
}
.item-word-replace-page .iwr-results-table,
.item-word-replace-page .iwr-results-table .dt-scrollable,
.item-word-replace-page .iwr-results-table .dt-instance {
	width: 100% !important;
	max-width: 100% !important;
}
.item-word-replace-page .iwr-results-table .dt-scrollable {
	overflow-x: auto;
}
.item-word-replace-page .iwr-results-table .dt-row .dt-cell .dt-cell__content {
	white-space: normal;
	word-break: break-word;
	line-height: 1.35;
	user-select: text;
	cursor: copy;
}
.item-word-replace-page .iwr-results-table .dt-row .dt-cell--0 .dt-cell__content,
.item-word-replace-page .iwr-results-table .dt-row .dt-cell--1 .dt-cell__content {
	cursor: default;
	user-select: none;
}
.item-word-replace-page .iwr-results-table .dt-row .dt-cell.iwr-copy-flash {
	background-color: var(--highlight-color, #fffce7);
}
`)
			.appendTo(document.head);
	}
};
