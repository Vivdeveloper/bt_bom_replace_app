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
	};

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("BT BOM Replace Tool"),
		single_column: true,
	});

	page.page_form.hide();

	const $layout = $(`
		<div class="bt-bom-replace-layout">
			<div class="bt-bom-replace-filter">
				<div class="row align-items-end">
					<div class="col-sm-6 col-md-5">
						<div class="bt-bom-replace-item-field"></div>
					</div>
					<div class="col-sm-6 col-md-7 bt-bom-replace-actions">
						<button type="button" class="btn btn-primary btn-find-bom-links">
							${__("Find BOM Links")}
						</button>
						<button type="button" class="btn btn-default btn-clear-bom-links">
							${__("Clear")}
						</button>
					</div>
				</div>
				<p class="text-muted small bt-bom-replace-hint"></p>
			</div>
			<div class="bt-bom-replace-summary small text-muted"></div>
			<div class="bt-bom-replace-replace is-hidden">
				<div class="row align-items-end g-2">
					<div class="col-sm-8 col-md-6 col-lg-5">
						<div class="bt-bom-replace-new-item-field"></div>
					</div>
					<div class="col-sm-4 col-md-6 col-lg-7 bt-bom-replace-actions">
						<button type="button" class="btn btn-primary btn-replace-selected-boms">
							${__("Replace Selected BOMs")}
						</button>
					</div>
				</div>
				<p class="text-muted small bt-bom-replace-replace-hint"></p>
			</div>
			<div class="bt-bom-replace-results"></div>
		</div>
	`).appendTo(page.main);

	page.main.addClass("frappe-card");
	ensure_styles();

	const $hint = $layout.find(".bt-bom-replace-hint");
	const $summary = $layout.find(".bt-bom-replace-summary");
	const $replace_panel = $layout.find(".bt-bom-replace-replace");
	const $replace_hint = $layout.find(".bt-bom-replace-replace-hint");
	const $results = $layout.find(".bt-bom-replace-results");

	$hint.text(
		__(
			"Find this item in every BOM where it is used (FG, assembly, sub-assembly, hardware, exploded) and show the full parent BOM chain up to the top level."
		)
	);

	const item_field = frappe.ui.form.make_control({
		parent: $layout.find(".bt-bom-replace-item-field")[0],
		df: {
			fieldtype: "Link",
			fieldname: "item_code",
			label: __("Item"),
			options: "Item",
			reqd: 1,
		},
		render_input: true,
	});

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

	let replace_item_field = null;

	function init_replace_field() {
		if (replace_item_field) {
			return replace_item_field;
		}
		const $parent = $layout.find(".bt-bom-replace-new-item-field");
		$parent.empty();
		replace_item_field = frappe.ui.form.make_control({
			parent: $parent[0],
			df: {
				fieldtype: "Link",
				fieldname: "new_item_code",
				label: __("Replace With"),
				options: "Item",
				reqd: 0,
			},
			render_input: true,
		});
		replace_item_field.refresh();
		return replace_item_field;
	}

	function show_replace_panel(item_code) {
		$replace_panel.removeClass("is-hidden");
		init_replace_field();
		$replace_hint.html(
			__(
				"Replace <b>{0}</b> with another item. Select BOM rows in the table (<b>In BOM</b> level only), then click <b>Replace Selected BOMs</b>.",
				[frappe.utils.escape_html(item_code)]
			)
		);
	}

	function hide_replace_panel() {
		$replace_panel.addClass("is-hidden");
	}

	let result_datatable = null;
	let last_search_data = null;

	function bom_link(name) {
		if (!name) return "";
		return frappe.utils.get_form_link("BOM", name, true);
	}

	function render_results(data) {
		$results.empty();
		$summary.empty();
		last_search_data = data;

		const usage =
			data?.usage_count ?? data?.rows?.filter((r) => r.level === "usage").length ?? 0;

		if (!data?.rows?.length) {
			hide_replace_panel();
			$summary.html(
				__("No BOM links found for <b>{0}</b>.", [
					frappe.utils.escape_html(data.item_code),
				])
			);
			return;
		}

		if (usage > 0) {
			show_replace_panel(data.item_code);
		} else {
			hide_replace_panel();
		}

		const parent = data.parent_count ?? data.rows.length - usage;
		let summary_html = __("Found <b>{0}</b> row(s) for <b>{1}</b>", [
			data.count,
			frappe.utils.escape_html(data.item_code),
		]);
		summary_html += ` (${usage} ${__("in BOM")}, ${parent} ${__("parent level")})`;
		if (data.item_default_bom) {
			summary_html += ` · ${__("Default BOM")}: ${bom_link(data.item_default_bom)}`;
		}
		$summary.html(summary_html);

		const columns = [
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
		];

		$results.addClass("bt-bom-replace-results-table");

		const table_rows = data.rows.map((r) => ({
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
			serialNoColumn: true,
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
		if (replace_item_field) {
			replace_item_field.set_value("");
		}
		$results.empty();
		$summary.empty();
		hide_replace_panel();
		result_datatable = null;
		last_search_data = null;
	}

	function run_replace() {
		const current_item = item_field.get_value();
		init_replace_field();
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

		const preview_args = { current_item, new_item };
		if (bom_list?.length) {
			preview_args.bom_list = JSON.stringify(bom_list);
		}

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

				const confirm_msg = __(
					"Replace <b>{0}</b> with <b>{1}</b> in <b>{2}</b> selected BOM(s) ({3} material line(s))? This cannot be undone easily.",
					[p.current_item, p.new_item, p.bom_count, p.line_count]
				);

				frappe.confirm(
					confirm_msg,
					() => {
						const replace_args = { current_item, new_item };
						if (bom_list?.length) {
							replace_args.bom_list = JSON.stringify(bom_list);
						}
						frappe.call({
							method: API.replace,
							args: replace_args,
							freeze: true,
							freeze_message: __("Replacing item in BOMs..."),
							callback(res) {
								if (res.exc || !res.message) return;
								const out = res.message;
								let msg = __("Updated {0} BOM(s).", [out.updated_count]);
								if (out.skipped?.length) {
									msg += "<br>" + __("Skipped: {0}", [out.skipped.length]);
								}
								if (out.failed?.length) {
									msg += "<br>" + __("Failed: {0}", [out.failed.length]);
								}
								frappe.msgprint({
									title: __("Replace complete"),
									message: msg,
									indicator: out.updated_count ? "green" : "orange",
								});
								run_search();
							},
						});
					}
				);
			},
		});
	}

	$layout.find(".btn-find-bom-links").on("click", () => run_search());
	$layout.find(".btn-clear-bom-links").on("click", () => clear_search());
	$layout.find(".btn-replace-selected-boms").on("click", () => run_replace());

	function ensure_styles() {
		const id = "bt-bom-replace-tool-style";
		if (document.getElementById(id)) return;
		$("<style>")
			.attr("id", id)
			.text(`
.bt-bom-replace-layout { padding: 1rem 1.25rem 1.25rem; }
.bt-bom-replace-filter {
	margin-bottom: 1rem;
	padding-bottom: 1rem;
	border-bottom: 1px solid var(--border-color, #d1d8dd);
}
.bt-bom-replace-filter .form-group,
.bt-bom-replace-replace .form-group { margin-bottom: 0; }
.bt-bom-replace-item-field,
.bt-bom-replace-new-item-field {
	min-height: 58px;
	width: 100%;
}
.bt-bom-replace-new-item-field {
	background: var(--card-bg, #fff);
	border: 1px solid var(--border-color, #d1d8dd);
	border-radius: var(--border-radius-sm, 8px);
	padding: 0.4rem 0.65rem 0.25rem;
	box-sizing: border-box;
}
.bt-bom-replace-item-field .control-input-wrapper,
.bt-bom-replace-new-item-field .control-input-wrapper,
.bt-bom-replace-item-field input,
.bt-bom-replace-new-item-field input {
	width: 100% !important;
	max-width: 100%;
}
/* Replace With: white input like Item search (on gray panel) */
.bt-bom-replace-new-item-field .frappe-control {
	width: 100%;
}
.bt-bom-replace-new-item-field .control-input-wrapper,
.bt-bom-replace-new-item-field .control-input,
.bt-bom-replace-new-item-field input.form-control,
.bt-bom-replace-new-item-field .link-field > .awesomplete > input,
.bt-bom-replace-new-item-field .like-disabled-input {
	background-color: var(--card-bg, #fff) !important;
	border: none !important;
	border-radius: 0 !important;
	box-shadow: none !important;
	min-height: 30px;
}
.bt-bom-replace-new-item-field:focus-within {
	border-color: var(--primary, #171717);
	box-shadow: 0 0 0 1px var(--primary, #171717);
}
.bt-bom-replace-actions {
	display: flex;
	flex-wrap: wrap;
	align-items: flex-end;
	gap: 0.5rem;
	padding-bottom: 0.35rem;
	min-height: 58px;
}
.bt-bom-replace-hint {
	margin: 0.75rem 0 0;
	clear: both;
	line-height: 1.45;
}
.bt-bom-replace-summary { margin-bottom: 0.75rem; }
.bt-bom-replace-replace {
	margin-bottom: 1rem;
	padding: 1rem 1.25rem;
	background: var(--control-bg, #f7f7f7);
	border-radius: var(--border-radius, 6px);
	border: 1px solid var(--border-color, #d1d8dd);
	position: relative;
	z-index: 20;
	overflow: visible;
}
.bt-bom-replace-replace.is-hidden {
	display: none;
}
.bt-bom-replace-replace-hint { margin: 0.75rem 0 0; clear: both; }
.bt-bom-replace-results {
	min-height: 120px;
	overflow-x: auto;
	position: relative;
	z-index: 1;
	margin-top: 0.5rem;
}
.bt-bom-replace-layout .awesomplete {
	z-index: 1050;
}
.bt-bom-replace-layout .awesomplete > ul {
	z-index: 1051;
	max-height: 240px;
	overflow-y: auto;
}
.bt-bom-replace-results-table .dt-scrollable {
	overflow-x: auto;
}
.bt-bom-replace-results-table .dt-cell__content {
	white-space: normal;
	word-break: break-word;
	line-height: 1.35;
	padding-top: 4px;
	padding-bottom: 4px;
}
.bt-bom-replace-results-table .dt-cell__content a {
	white-space: normal;
	word-break: break-word;
}
.bt-bom-replace-results-table .bt-bom-row-not-selectable {
	opacity: 0.35;
	cursor: not-allowed;
}
.bt-bom-replace-results-table .bt-bom-row-not-selectable input[type="checkbox"] {
	pointer-events: none;
}
`)
			.appendTo(document.head);
	}
};
