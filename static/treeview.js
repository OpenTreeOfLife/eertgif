

var el_by_comp_id = {};
var selected_id_set = new Set();

/////////////////////////////////////////////////////////////////
// following 3 functions modified from https://stackoverflow.com/posts/487049/revisions
function getSearchParamList() {
	return document.location.search.substr(1).split('&');
}

function insertParam(key, value, paramList) {
	key = encodeURIComponent(key);
	value = encodeURIComponent(value);

	// paramList looks like ['key1=value1', 'key2=value2', ...]
	let i=0;

	for(; i<paramList.length; i++){
		if (paramList[i].startsWith(key + '=')) {
			let pair = paramList[i].split('=');
			pair[1] = value;
			paramList[i] = pair.join('=');
			break;
		}
	}

	if(i >= paramList.length){
		paramList[paramList.length] = [key,value].join('=');
	}
	return paramList;
}

function reloadPageWithParamList(paramList) {
	// can return this or...
	let params = paramList.join('&');

	// reload page with new params
	document.location.search = params;
}
/////////////////////////////////////////////////////////////////

//Sets display to "yes" if not hidden and not trashed (or showTrashed is selected)
function displayIfNotHiddenOrTrashed(el) {
	if (el.hasAttribute("hidden")) {
		return;
	}
	if (extract_config.viz_show_trashed || ! el.hasAttribute("trashed")) {
		el.setAttribute("display", "yes");
	}
}

//Sets display to none (without checking for trashed status)
function undisplay(el) {
	el.setAttribute("display", "none");
}

// Takes a dom el, sets colors, if nhfcolor/nhscolor are not None
//	calls displayIfNotHiddenOrTrashed
function colorElIfNHColorNonNone(el, stroke_color, fill_color) {
	var nhf = el.getAttribute("nhfcolor");
	if (nhf !== "none") {
		if (fill_color === "none") {
			el.setAttribute("fill", nhf)
		} else {
			el.setAttribute("fill", fill_color);
		}
	}
	var nhs = el.getAttribute("nhscolor");
	if (nhs !== "none") {
		if (stroke_color === "none") {
			el.setAttribute("stroke", nhs)
		} else {
			el.setAttribute("stroke", stroke_color);
		}
	}
	displayIfNotHiddenOrTrashed(el);
}

function highlightElement(element, color) {
	colorElIfNHColorNonNone(element, color, color);
}

function unhighlightElement(element) {
	var sc = element.getAttribute("nhscolor");
	var fc = element.getAttribute("nhfcolor");
	colorElIfNHColorNonNone(element, sc, fc);
}

function condHighlightElement(out_move, element, color) {
	if (out_move) {
		unhighlightElement(element);
	} else {
		highlightElement(element, color);
	}
}

// calls colorElIfNHColorNonNone for every element with the same component index
// (`comp_id`). Calls setDisplayForGraph with `nonmatching_display` to 
// to allow for setting the display for none for other elements.
//	TEMP. that nonmatching_display stuff is sloppy and could flicker
function setColorsForSameComp(comp_id, color, nonmatching_display, out_move) {
	var el_of_same_comp = el_by_comp_id[comp_id]
	if (typeof el_of_same_comp === 'undefined') {
		return;
	}
	setDisplayForGraph(nonmatching_display);
	var i = 0;
	var el;
	for (; i < el_of_same_comp.length; i++) {
		el = el_of_same_comp[i];
		condHighlightElement(out_move, el, color)
	}
}

// `id_refs` should be a comma separated list of element ids
//	colorElIfNHColorNonNone will be called for each.
function colorComSepList(id_refs, color, out_move) {
	var er;
	var el;
	if (id_refs && id_refs !== "") {
		var edge_list = id_refs.split(",")
		let i=0;
		for (; i < edge_list.length; i++) {
			er = "#" + edge_list[i].trim();
			el = $( er ).get(0);
			condHighlightElement(out_move, el, color);
		}
	}
}

// if nonmatching_display is None, set display of graph elements (paths and circles)
//	to none. Otherwise calls displayIfNotHiddenOrTrashed on them.
function setDisplayForGraph(nonmatching_display) {
	if (nonmatching_display == "none") {
		$("#treeholder svg path, #treeholder svg circle").each(function() {
			undisplay($( this ).get(0));
		});
	} else {
		$("#treeholder svg path, #treeholder svg circle").each(function() {
			displayIfNotHiddenOrTrashed($( this ).get(0));
		});
	}
}

// setDisplayForGraph, then displays all elements referred to in "nodes" or "edges"
//	attributes of "el"
function setColorsForNeighbors(el, color, nonmatching_display, out_move) {
	setDisplayForGraph(nonmatching_display);
	colorComSepList(el.getAttribute("edges"), color, out_move);
	colorComSepList(el.getAttribute("nodes"), color, out_move);
}

function colorElIsSelectionAndNonNone(target, color, out_move) {
	if (out_move) {
		if (! target.hasAttribute('data-selected')) {
			unhighlightElement(target);
		}
	} else {
		highlightElement(target, color);
	}
}


// colors target and other elements (depending on the highlight_mode UI element)/
// `out_move` should be true if this is a move out of the target.
// note that highlight_mode reverts to "element" only if there is an active
//	selection event.
function mouseColorEvent(target, color, out_move) {
	var nonmatching_display;
	var highlight_mode = $("#highlight_mode").val();
	if (selected_id_set.size == 0) {
		if (highlight_mode == "component" || highlight_mode == "component-only") {
			var comp_id = target.getAttribute("component");
			if (typeof comp_id === 'undefined') {
				return;
			}
			if (out_move || highlight_mode == "component" ) {
				nonmatching_display = "yes";
			} else {
				nonmatching_display = "none"
			}
			setColorsForSameComp(comp_id, color, nonmatching_display, out_move);
		} else if (highlight_mode == "neighbors" || highlight_mode == "neighbors-only") {
			if (out_move || highlight_mode == "neighbors" ) {
				nonmatching_display = "yes";
			} else {
				nonmatching_display = "none"
			}
			setColorsForNeighbors(target, color, nonmatching_display, out_move);
		}
		colorElIsSelectionAndNonNone(target, color, out_move);
	} else {
		colorElIsSelectionAndNonNone(target, color, out_move);
	}	
}


function mouseColorEventPaired(target, color, out_move) {
	// if span, treat as mouse event on parent
	if (target.tagName == "tspan") {
		target = target.parentNode;
	}
	var targID = target.getAttribute("id");
	var pairedTo = [];
	var neighbor = null;
	colorElIsSelectionAndNonNone(target, color, out_move);
	if (pairings !== null && pairings.hasOwnProperty(targID)) {
		pairTo = pairings[targID];
		if (pairTo) {
			// If the pairings value is length 3, then the third element is the curve ID
			// the curve is highlighted by the edge ID, so we don't use the curve ID
			// itself
			if (pairTo.length > 0) {
				neighbor = document.getElementById(pairTo[0]);
				if (neighbor) {
					colorElIsSelectionAndNonNone(neighbor, color, out_move);
				}
				if (pairTo.length > 1) {
					neighbor = document.getElementById(pairTo[1]);
					if (neighbor) {
						colorElIsSelectionAndNonNone(neighbor, color, out_move);
					}
				}
			}
		}
	}
}


function mouseOverPairedEdge(target) {
	mouseColorEventPaired(target, "red", false);
}

function mouseOutPairedEdge(target) {
	mouseColorEventPaired(target, null, true);
}


// calls mouseColorEvent with "red"
function mouseOverNode(target) {
	mouseColorEvent(target, "red", false);
}

var mouseOverEdge = mouseOverNode;

// calls mouseColorEvent with non-highlight colors for the target"
function mouseOutNode(target) {
	mouseColorEvent(target, null, true);
}

var mouseOutEdge = mouseOutNode;

function handleClickOnGraph(evt, targetArg) {
	var target = targetArg;
	if (!target) {
		target = evt.target;
	}
	var curve_id_str = "null";
	if (target.hasAttribute("curve_id")) {
		curve_id_str = target.getAttribute("curve_id");
	}
	var pref = "Clicked";
	if (evt.getModifierState("Control")) {
		pref = "Control-clicked"
	}
	console.log(pref + " on " + target.tagName + " id = " + target.getAttribute("id") + " curve_id = ", curve_id_str);
}


function bundleGlobalStateForServer() {
	var val = $('#node_tol_input').val();
	var valf = Number(val);
	if (val === "" || isNaN(valf)) {
		alert("node tolerance for component detection must be a number");
		return null;
	}
	var rval = $('#rect_axis_merge_tol').val();
	var rvalf = Number(rval);
	if (rval === "" || isNaN(rvalf)) {
		alert("Rect axis merge tol must be a number");
		return null;
	}
	extract_config.node_merge_tol = valf
	extract_config.rect_base_intercept_tol = rvalf
	extract_config.viz_highlight_mode = $('#highlight_mode').val();
	extract_config.force_trashed_ids = [];
	var tid = extract_config.force_trashed_ids ;
	$( "[trashed]" ).each(function() {
		tid[tid.length] = $(this).attr("id");
	});
	data = {"config": JSON.stringify(extract_config),
	}
	return data
}
// callback for the "Detect Components" button. packages state that
//	affects backent, does an AJAX POST, and then triggers a page reload.
function detectComponents() {
	var data = bundleGlobalStateForServer();
	if (data === null) {
		return;
	}
	data["action"] = "detect_components";
	postAndReload(data);
}

function postAndReload(data) {
	$.ajax({
		type: "POST",
		url: document.location,
		data: data,
		success: function() {   
			location.reload();  
		}
	});
}


// Success function slightly modified from https://stackoverflow.com/a/23797348
function downloadTree(download_url, tag, page_id) {
	$.ajax({
    	type: "GET",
    	url: download_url,
	    xhrFields: {
	        responseType: 'blob' // to avoid binary data being mangled on charset conversion
	    },
	    success: function(blob, status, xhr) {
	    	// This function slightly modified from https://stackoverflow.com/a/23797348
	        // check for a filename
	        var filename = "";
	        var disposition = xhr.getResponseHeader('Content-Disposition');
	        if (disposition && disposition.indexOf('attachment') !== -1) {
	            var filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
	            var matches = filenameRegex.exec(disposition);
	            if (matches != null && matches[1]) {
	            	filename = matches[1].replace(/['"]/g, '');
	            }
	        } else {
	        	filename = "tree-" + tag + '-' + page_id + '.tre';
	        }
	        if (typeof window.navigator.msSaveBlob !== 'undefined') {
	            // IE workaround for "HTML7007: One or more blob URLs were revoked by closing the blob for which they were created. These URLs will no longer resolve as the data backing the URL has been freed."
	            window.navigator.msSaveBlob(blob, filename);
	        } else {
	            var URL = window.URL || window.webkitURL;
	            var downloadUrl = URL.createObjectURL(blob);

	            if (filename) {
	                // use HTML5 a[download] attribute to specify filename
	                var a = document.createElement("a");
	                // safari doesn't support this yet
	                if (typeof a.download === 'undefined') {
	                    window.location.href = downloadUrl;
	                } else {
	                    a.href = downloadUrl;
	                    a.download = filename;
	                    document.body.appendChild(a);
	                    a.click();
	                }
	            } else {
	                window.location.href = downloadUrl;
	            }

	            setTimeout(function () { URL.revokeObjectURL(downloadUrl); }, 100); // cleanup
	        }
	    }
	});
}

function extractTree() {
	var data = bundleGlobalStateForServer();
	if (data === null) {
		return;
	}
	data["action"] = "extract_trees";
	postAndReload(data);
}

function add_to_map() {
	var comp_id = $( this ).attr("component");
	if (typeof comp_id === 'undefined') {
		return;
	}
	var x = el_by_comp_id[comp_id];
	if (x === undefined) {
		el_by_comp_id[comp_id] = [this];
	} else {
		x[x.length] = this;
	}
}

// Toggles extract_config.is_rect_shape (and UI indicator)
function toggleTreeShape() {
	var rw = $('#rect_tree_shape_icon').attr("width");
	var dw= $('#diag_tree_shape_icon').attr("width");
	var rwn = Number(rw);
	var dwn= Number(dw);
	$('#rect_tree_shape_icon').attr("width", dw);
	$('#diag_tree_shape_icon').attr("width", rw);
	extract_config.is_rect_shape = (dw > rw);
}


// adds "hidden" attr and sets display to "none"
function elHiding() {
	var el = $(this);
	el.attr("hidden", "yes");
	el.attr("display", "none");
}

// removes "hidden" attr and calls displayIfNotHiddenOrTrashed 
function elUnhide() {
	var el = $(this);
	el.removeAttr("hidden");
	displayIfNotHiddenOrTrashed(this);
}

// if `predicate` is true, calls elHiding, else elUnhide. Return predicate.
function hideOrUnhide(predicate, targets) {
	if (predicate) {
		targets.each(elHiding);
	} else {
		targets.each(elUnhide);
	}
	return predicate;
}

function textHiding(checkbx) {
	var targets = $( "#treeholder svg text" );
	extract_config.viz_hide_text = hideOrUnhide(checkbx.checked, targets);
}

function nodeHiding(checkbx) {
	var targets = $( "#treeholder svg circle" );
	extract_config.viz_hide_nodes = hideOrUnhide(checkbx.checked, targets);
}

function edgeHiding(checkbx) {
	var targets = $( "#treeholder svg path" );
	extract_config.viz_hide_edges = hideOrUnhide(checkbx.checked, targets);
}

function trashedShowing(checkbx) {
	if (checkbx.checked) {
		$( "[trashed]" ).each(function() {
			if (! $(this).attr("hidden")) {
				$( this ).attr("display", "yes")
			}
		});
		extract_config.viz_show_trashed = true;
	} else {
		$( "[trashed]" ).each(function() {
			$( this ).attr("display", "none")
		});
		extract_config.viz_show_trashed = false;
	}
}

function toggleCurveSimplify(target) {
	var attrName;
	if (target.checked) {
		attrName = "simp_d";
		extract_config.viz_simplify_curves = true;
	} else {
		attrName = "full_d";
		extract_config.viz_simplify_curves = false;
	}
	$('#treeholder svg path').each(function(){
		var adv =  $( this ).attr(attrName);
		if (adv) {
			$( this ).attr("d", adv);
		}
	 });
}

// modified from https://stackoverflow.com/questions/20061774/rotate-an-image-in-image-source-in-html
function rotate_img_90cw(obj) {
	var deg = obj.data('rotate') || 0;
	deg += 90;
	if (deg >= 360) {
		deg -= 360;
	}
	obj.data('rotate', deg);
	var rotate = 'rotate(' + deg +  'deg)';
	obj.css({ 
		'-webkit-transform': rotate,
		'-moz-transform': rotate,
		'-o-transform': rotate,
		'-ms-transform': rotate,
		'transform': rotate 
	});
}

function rotateOrientationClicked() {
	 rotate_img_90cw($('#rect_tree_shape_icon'));
	 rotate_img_90cw($('#diag_tree_shape_icon'));
	 if (extract_config.orientation == "right") {
		extract_config.orientation = "down";
	 } else if (extract_config.orientation == "down") {
		extract_config.orientation = "left";
	 } else if (extract_config.orientation == "left") {
		extract_config.orientation = "up";
	 } else  {
		extract_config.orientation = "right";
	 }
}


// called on page load to set UI elements based on new, global extract_config
function set_ui_based_on_config(){
	var rect_el = $('#rect_tree_shape_icon');
	if (rect_el.length) {
		var is_rect = extract_config.is_rect_shape;
		toggleTreeShape();
		if (is_rect != extract_config.is_rect_shape) {
			toggleTreeShape();
		}
		while (extract_config.orientation != "right") {
			rotateOrientationClicked();
		}
	}
	var he_chkbz = $( '#hide_edges_btn' );
	if (he_chkbz.length) {
		he_chkbz.prop('checked', extract_config.viz_hide_edges).trigger("change");
	}
	var hn_chkbz = $( '#hide_nodes_btn' );
	if (hn_chkbz.length) {
		hn_chkbz.prop('checked', extract_config.viz_hide_nodes).trigger("change");
	}
	var ht_chkbz = $( '#hide_text_btn' );
	if (ht_chkbz.length) {
		ht_chkbz.prop('checked', extract_config.viz_hide_text).trigger("change");
	}
	var st_chkbz = $( '#show_trashed_btn' );
	if (st_chkbz.length) {
		st_chkbz.prop('checked', extract_config.viz_show_trashed).trigger("change");
	}
	if (!extract_config.viz_simplify_curves) {
		$( '#simplify_paths_btn' ).prop('checked', false).trigger("change");
	}
	$( "#highlight_mode").val(extract_config.viz_highlight_mode).trigger("change");
}

/////////////////////////////////////////////////////
// svg-drag-select code:
function strictIntersectionSelector(context) {
	const dragAreaInSvgCoordinate = context.dragAreaInSvgCoordinate
	return context.getIntersections().filter(function (element) {
	if (context.pointerEvent.target === element) {
		return true
	}
	if (!(element instanceof SVGPathElement)) {
		// strictly check only <path>s.
		return true
	}
	for (let i = 0, len = element.getTotalLength(); i <= len; i += 4 /* arbitrary */) {
		const point = element.getPointAtLength(i)
		const x = point.x
		const y = point.y
		if (
			dragAreaInSvgCoordinate.x <= x && x <= dragAreaInSvgCoordinate.x + dragAreaInSvgCoordinate.width &&
			dragAreaInSvgCoordinate.y <= y && y <= dragAreaInSvgCoordinate.y + dragAreaInSvgCoordinate.height
		) {
		return true
		}
	}
	return false
	})
}

function noOp() {
}

function clearSelection() {
	const selectedElements = window.svgDragSelectOptions.svg.querySelectorAll('[data-selected]');
	for (let i = 0; i < selectedElements.length; i++) {
		selectedElements[i].removeAttribute('data-selected')
		unhighlightElement(selectedElements[i]);
	}
	selected_id_set.clear();
	document.getElementById('selected-items').value = ''
}

function moveSelectionToTrashed() {
	const selectedElements = window.svgDragSelectOptions.svg.querySelectorAll('[data-selected]');
	for (let i = 0; i < selectedElements.length; i++) {
		selectedElements[i].removeAttribute('data-selected')
		selectedElements[i].setAttribute('trashed', 'yes')
	}
	var old_trashed_txt = document.getElementById('trashed-items').value;
	var old_selection_txt =  document.getElementById('selected-items').value;
	if (old_selection_txt !== "") {
		if (old_trashed_txt !== "") {
			document.getElementById('trashed-items').value = old_trashed_txt + "\n" + old_selection_txt;
		} else {
			document.getElementById('trashed-items').value = old_selection_txt;
		}
	}
	trashedShowing($("#show_trashed_btn").get(0));
	clearSelection();
}

function restoreTrashed() {
	document.getElementById('trashed-items').value = '';
	const selectedElements = window.svgDragSelectOptions.svg.querySelectorAll('[trashed]');
	for (let i = 0; i < selectedElements.length; i++) {
		selectedElements[i].removeAttribute('trashed')
		unhighlightElement(selectedElements[i]);
	}
}

window.svgDragSelectOptions = {
	svg: document.getElementsByTagName('svg')[0],
	
	onSelectionStart: function (selectionStart) {
	//console.log("onSelectionStart", selectionStart)
	// const selectedElements = selectionStart.svg.querySelectorAll('[data-selected]')
	// for (let i = 0; i < selectedElements.length; i++) {
	// 	selectedElements[i].removeAttribute('data-selected')
	// 	unhighlightElement(selectedElements[i]);
	// }
	// selected_id_set.clear();
	clearSelection();
	var path = selectionStart.pointerEvent.path;
	if (path && path.length && path[0].tagName !== "svg") {
		handleClickOnGraph(selectionStart.pointerEvent, path[0]);
	}
	},
	
	onSelectionEnd: function (selectionEnd) {
	//console.log("onSelectionEnd", selectionEnd)
	},

	onSelectionChange: function (selectionChange) {
	//console.log("onSelectionChange", selectionChange)
	selectionChange.newlyDeselectedElements.forEach(function (element) {
		element.removeAttribute('data-selected');
		selected_id_set.delete(element.getAttribute('id'));
		unhighlightElement(element);
	})
	selectionChange.newlySelectedElements.forEach(function (element) {
		element.setAttribute('data-selected', '')
		selected_id_set.add(element.getAttribute('id'));
		highlightElement(element, "red");
	})
	document.getElementById('selected-items').value = selectionChange.selectedElements
		.map(function (element) { return element.getAttribute('id') })
		.sort()
		.join('\n');

	selectionChange.pointerEvent.preventDefault();
	},
	
	selector: strictIntersectionSelector
}


$(document).ready(function() {
	if (extract_config !== null) {
		set_ui_based_on_config();
	}
	$("circle").each(add_to_map);
	$("path").each(add_to_map);

	window.svgDragSelect(svgDragSelectOptions);
	window.svgDragSelectOptions.svg.style.visibility = 'visible';
	$(document).on("keydown", function (e) {
		if (e.which == 8 || e.which == 46) { // backspace (8) or DEL key
	    	moveSelectionToTrashed();
	    }
	});
})
;